import base64
import csv
import hashlib
import io
import os
import re
import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
import httpx
import jwt
from cryptography.fernet import Fernet
from db import db, now_iso, new_id
from auth import current_user, JWT_SECRET, app_url
from ratelimit import get_limits

# Integrations hub. Stage 1: Google Drive / Docs / Sheets with the least-privilege `drive.file` scope:
# Oryntix only sees files it created itself or files the user explicitly picked via the Google Picker.
router = APIRouter(prefix="/api/integrations", tags=["integrations"])
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
SCOPES = f"{DRIVE_SCOPE} openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile"
GAUTH, GTOKEN, GREVOKE = "https://accounts.google.com/o/oauth2/v2/auth", "https://oauth2.googleapis.com/token", "https://oauth2.googleapis.com/revoke"
DRIVE, UPLOAD, DOCS = "https://www.googleapis.com/drive/v3", "https://www.googleapis.com/upload/drive/v3", "https://docs.googleapis.com/v1"
GDOC, GSHEET = "application/vnd.google-apps.document", "application/vnd.google-apps.spreadsheet"
_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(("drive:" + JWT_SECRET).encode()).digest()))


def configured() -> bool:
    return bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))


def _redirect_uri(request: Request) -> str:
    return os.environ.get("GOOGLE_DRIVE_REDIRECT_URI") or f"{app_url(request)}/api/integrations/google/callback"


async def storage_usage(uid: str) -> dict:
    row = await db.storage_usage.find_one({"user_id": uid}, {"_id": 0, "bytes": 1}) or {}
    quota = int((await get_limits()).get("storage_quota_mb") or 50) * 1024 * 1024
    used = int(row.get("bytes") or 0)
    return {"used_bytes": used, "quota_bytes": quota, "pct": min(100, round(used * 100 / max(quota, 1)))}


async def add_storage(uid: str, nbytes: int) -> None:
    await db.storage_usage.update_one({"user_id": uid}, {"$inc": {"bytes": int(nbytes)}, "$set": {"updated_at": now_iso()}}, upsert=True)


async def assert_quota(uid: str, incoming: int) -> None:
    s = await storage_usage(uid)
    if s["used_bytes"] + incoming > s["quota_bytes"]:
        raise HTTPException(413, f"Penyimpanan platform penuh ({s['quota_bytes'] // 1048576} MB). Hubungkan Google Drive di menu Integrasi agar dokumen tersimpan di Drive Anda tanpa batas.")


# ---------- OAuth ----------
@router.get("")
async def list_integrations(u: dict = Depends(current_user)):
    g = await db.drive_credentials.find_one({"user_id": u["id"]}, {"_id": 0, "email": 1, "name": 1, "picture": 1, "connected_at": 1, "folder_id": 1})
    return {"items": [{"id": "google_drive", "name": "Google Drive & Docs", "configured": configured(), "connected": bool(g),
                       "account_email": (g or {}).get("email"), "account_name": (g or {}).get("name"), "account_picture": (g or {}).get("picture"), "folder_link": f"https://drive.google.com/drive/folders/{g['folder_id']}" if (g or {}).get("folder_id") else None, "connected_at": (g or {}).get("connected_at"), "scope": "drive.file", "picker": bool(os.environ.get("GOOGLE_API_KEY")),
                       "capabilities": ["Simpan dokumen/gambar ke Drive", "Update Google Docs & Sheets buatan Oryntix", "Kirim tautan Drive", "Lampirkan file Drive pilihan Anda di chat", "Pengetahuan asisten dari file Drive pilihan Anda"]}],
            "coming_soon": ["Notion", "Slack", "GitHub", "WhatsApp Business"], "storage": await storage_usage(u["id"])}


@router.get("/google/connect")
async def google_connect(request: Request, u: dict = Depends(current_user)):
    if not configured():
        raise HTTPException(503, "Integrasi Google belum dikonfigurasi oleh admin platform (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET).")
    state = jwt.encode({"sub": u["id"], "exp": int(time.time()) + 600, "purpose": "gdrive"}, JWT_SECRET, algorithm="HS256")
    row = await db.users.find_one({"id": u["id"]}, {"_id": 0, "google_email": 1}) or {}
    params = {"client_id": os.environ["GOOGLE_CLIENT_ID"], "redirect_uri": _redirect_uri(request), "response_type": "code", "scope": SCOPES,
              "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": state}
    if row.get("google_email"):  # already signed in with Google → incremental auth: Google only asks for the Drive permission
        params["login_hint"] = row["google_email"]
    q = httpx.QueryParams(params)
    return {"authorization_url": f"{GAUTH}?{q}", "redirect_uri": _redirect_uri(request)}


@router.get("/google/callback")
async def google_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    base = app_url(request)
    if error or not code or not state:
        return RedirectResponse(f"{base}/integrations?error={error or 'cancelled'}")
    try:
        claims = jwt.decode(state, JWT_SECRET, algorithms=["HS256"])
        if claims.get("purpose") != "gdrive" or not claims.get("sub"):
            raise jwt.InvalidTokenError()
        uid = claims["sub"]
    except jwt.InvalidTokenError:
        return RedirectResponse(f"{base}/integrations?error=state")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(GTOKEN, data={"code": code, "client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"], "redirect_uri": _redirect_uri(request), "grant_type": "authorization_code"})
        if r.status_code != 200:
            return RedirectResponse(f"{base}/integrations?error=token")
        tok = r.json()
        granted = set((tok.get("scope") or "").split())
        if not granted & {DRIVE_SCOPE, "https://www.googleapis.com/auth/drive"}:  # the Drive (file) scope is required
            return RedirectResponse(f"{base}/integrations?error=scope")
        me = (await c.get("https://www.googleapis.com/oauth2/v3/userinfo", headers={"Authorization": f"Bearer {tok['access_token']}"})).json()
    old = await db.drive_credentials.find_one({"user_id": uid}, {"_id": 0, "refresh_token": 1})
    refresh = tok.get("refresh_token") or (old or {}).get("refresh_token")
    if not refresh:
        return RedirectResponse(f"{base}/integrations?error=refresh")
    await db.drive_credentials.update_one({"user_id": uid}, {"$set": {"user_id": uid, "email": me.get("email"), "name": me.get("name"), "picture": me.get("picture"), "access_token": _fernet.encrypt(tok["access_token"].encode()).decode(),
                                          "refresh_token": refresh if refresh.startswith("gAAAA") else _fernet.encrypt(refresh.encode()).decode(), "expires_at": time.time() + int(tok.get("expires_in") or 3600) - 60,
                                          "scopes": sorted(granted), "connected_at": now_iso(), "updated_at": now_iso()}}, upsert=True)
    return RedirectResponse(f"{base}/integrations?connected=google")


@router.delete("/google")
async def google_disconnect(u: dict = Depends(current_user)):
    row = await db.drive_credentials.find_one({"user_id": u["id"]}, {"_id": 0})
    if row:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post(GREVOKE, params={"token": _fernet.decrypt(row["refresh_token"].encode()).decode()})
        except Exception:
            pass
        await db.drive_credentials.delete_one({"user_id": u["id"]})
    return {"ok": True}


async def access_token(uid: str) -> str:
    row = await db.drive_credentials.find_one({"user_id": uid}, {"_id": 0})
    if not row:
        raise HTTPException(400, "Google Drive belum terhubung. Hubungkan dulu di menu Integrasi.")
    if row.get("expires_at", 0) > time.time():
        return _fernet.decrypt(row["access_token"].encode()).decode()
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(GTOKEN, data={"client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"], "grant_type": "refresh_token",
                                       "refresh_token": _fernet.decrypt(row["refresh_token"].encode()).decode()})
    if r.status_code != 200:
        raise HTTPException(400, "Sesi Google Drive kedaluwarsa. Hubungkan ulang di menu Integrasi.")
    tok = r.json()
    await db.drive_credentials.update_one({"user_id": uid}, {"$set": {"access_token": _fernet.encrypt(tok["access_token"].encode()).decode(), "expires_at": time.time() + int(tok.get("expires_in") or 3600) - 60, "updated_at": now_iso()}})
    return tok["access_token"]


async def _g(uid: str, method: str, url: str, **kw) -> dict:
    tk = await access_token(uid)
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.request(method, url, headers={"Authorization": f"Bearer {tk}", **kw.pop("headers", {})}, **kw)
    if r.status_code >= 400:
        raise HTTPException(400, f"Google API error {r.status_code}: {r.text[:200]}")
    return r.json() if r.content and "json" in (r.headers.get("content-type") or "") else {"text": r.text}


# ---------- Drive operations (also used by assistant tools) ----------
def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", _esc(s))
    return re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"<i>\1</i>", s)


def _md_tables(md: str) -> list:
    from tools import _md_blocks
    tables, cur = [], []
    for kind, val in list(_md_blocks(md)) + [("blank", "")]:
        if kind == "row":
            if not (cur and all(re.fullmatch(r":?-{2,}:?", c) for c in val)):
                cur.append(val)
        elif cur:
            tables.append(cur); cur = []
    return tables


def _md_to_html(md: str) -> str:
    from tools import _md_blocks
    out, in_ul, in_tbl = [], False, False
    for kind, val in list(_md_blocks(md)) + [("blank", "")]:
        if in_ul and kind != "li":
            out.append("</ul>"); in_ul = False
        if in_tbl and kind != "row":
            out.append("</table>"); in_tbl = False
        if kind.startswith("h"):
            out.append(f"<{kind}>{_inline(val)}</{kind}>")
        elif kind == "li":
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append(f"<li>{_inline(val)}</li>")
        elif kind == "row":
            if all(re.fullmatch(r":?-{2,}:?", c) for c in val):
                continue
            if not in_tbl:
                out.append("<table border='1' cellpadding='4'>"); in_tbl = True
            out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in val) + "</tr>")
        elif kind == "p":
            out.append(f"<p>{_inline(val)}</p>")
    return "<html><body>" + "".join(out) + "</body></html>"


GFOLDER = "application/vnd.google-apps.folder"
APP_FOLDER = "Oryntix"


async def _app_folder(uid: str) -> Optional[str]:
    """Id of the user's "Oryntix" Drive folder (created once, cached on the credentials row, re-created if the user deleted it)."""
    cred = await db.drive_credentials.find_one({"user_id": uid}, {"_id": 0, "folder_id": 1})
    fid = (cred or {}).get("folder_id")
    if fid:
        try:
            f = await _g(uid, "GET", f"{DRIVE}/files/{fid}", params={"fields": "id,trashed"})
            if not f.get("trashed"):
                return fid
        except HTTPException:
            pass
    try:
        found = (await _g(uid, "GET", f"{DRIVE}/files", params={"q": f"name = '{APP_FOLDER}' and mimeType = '{GFOLDER}' and trashed = false", "fields": "files(id)", "pageSize": 1})).get("files", [])
        fid = found[0]["id"] if found else (await _g(uid, "POST", f"{DRIVE}/files", json={"name": APP_FOLDER, "mimeType": GFOLDER}, params={"fields": "id"}))["id"]
    except HTTPException:
        return None  # folder is a nicety: never block the save itself
    await db.drive_credentials.update_one({"user_id": uid}, {"$set": {"folder_id": fid}})
    return fid


async def _multipart_upload(uid: str, name: str, data: bytes, src_mime: str, target_mime: Optional[str]) -> dict:
    folder = await _app_folder(uid)
    meta = {"name": name, **({"mimeType": target_mime} if target_mime else {}), **({"parents": [folder]} if folder else {})}
    files = {"metadata": ("metadata", io.BytesIO(__import__("json").dumps(meta).encode()), "application/json; charset=UTF-8"), "file": (name, io.BytesIO(data), src_mime)}
    tk = await access_token(uid)
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{UPLOAD}/files?uploadType=multipart&fields=id,name,mimeType,webViewLink", headers={"Authorization": f"Bearer {tk}"}, files=files)
    if r.status_code >= 400:
        raise HTTPException(400, f"Upload Drive gagal ({r.status_code}): {r.text[:200]}")
    return r.json()


async def drive_search(uid: str, q: str, limit: int = 8) -> list:
    safe = q.replace("'", "\\'")
    r = await _g(uid, "GET", f"{DRIVE}/files", params={"q": f"name contains '{safe}' and trashed = false", "pageSize": limit, "fields": "files(id,name,mimeType,webViewLink,modifiedTime)", "orderBy": "modifiedTime desc"})
    return r.get("files", [])


async def drive_find(uid: str, name_or_id: str) -> dict:
    if re.fullmatch(r"[\w-]{20,}", name_or_id):
        return await _g(uid, "GET", f"{DRIVE}/files/{name_or_id}", params={"fields": "id,name,mimeType,webViewLink"})
    hits = await drive_search(uid, name_or_id, 1)
    if not hits:
        raise HTTPException(404, f"Tidak ada file Drive bernama '{name_or_id}'")
    return hits[0]


async def _record(uid: str, f: dict, source: dict) -> dict:
    item = {"id": new_id(), "user_id": uid, "kind": "drive", "name": f["name"], "drive_id": f["id"], "mime": f.get("mimeType"), "link": f.get("webViewLink"), "source": source, "created_at": now_iso()}
    await db.drive_items.insert_one(dict(item))
    item.pop("user_id")
    return item


async def drive_save(uid: str, title: str, markdown: str = "", kind: str = "doc", data: Optional[bytes] = None, mime: str = "application/octet-stream", source: Optional[dict] = None) -> dict:
    """Create a Google Doc (markdown→HTML→Docs), a Sheet (first markdown table → CSV→Sheets) or upload raw bytes. Gallery keeps only the link."""
    if kind == "sheet":
        tables = _md_tables(markdown)
        if not tables:
            raise HTTPException(400, "Tidak ada tabel untuk dijadikan Spreadsheet")
        buf = io.StringIO(); csv.writer(buf).writerows(tables[0])
        f = await _multipart_upload(uid, title, buf.getvalue().encode(), "text/csv", GSHEET)
    elif kind == "file" and data is not None:
        f = await _multipart_upload(uid, title, data, mime, None)
    else:
        f = await _multipart_upload(uid, title, _md_to_html(markdown).encode(), "text/html", GDOC)
    return await _record(uid, f, source or {})


async def drive_read(uid: str, name_or_id: str) -> dict:
    f = await drive_find(uid, name_or_id)
    if f.get("mimeType") == GDOC:
        txt = (await _g(uid, "GET", f"{DRIVE}/files/{f['id']}/export", params={"mimeType": "text/plain"}))["text"]
    elif f.get("mimeType") == GSHEET:
        txt = (await _g(uid, "GET", f"{DRIVE}/files/{f['id']}/export", params={"mimeType": "text/csv"}))["text"]
    else:
        txt = (await _g(uid, "GET", f"{DRIVE}/files/{f['id']}", params={"alt": "media"}))["text"]
    return {**f, "text": txt[:60000]}


MAX_DRIVE_BYTES = 8 * 1024 * 1024
GSLIDES = "application/vnd.google-apps.presentation"
FILE_FIELDS = "id,name,mimeType,webViewLink,modifiedTime,size,iconLink"


async def _g_bytes(uid: str, url: str, params: dict) -> bytes:
    tk = await access_token(uid)
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.get(url, headers={"Authorization": f"Bearer {tk}"}, params=params)
    if r.status_code >= 400:
        raise HTTPException(400, f"Google API error {r.status_code}: {r.text[:200]}")
    if len(r.content) > MAX_DRIVE_BYTES:
        raise HTTPException(400, "Berkas Drive lebih dari 8 MB")
    return r.content


def _bytes_text(data: bytes, mime: str, name: str) -> str:
    ext = (name or "").rsplit(".", 1)[-1].lower()
    if "pdf" in mime or ext == "pdf":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages[:40])
    if "wordprocessingml" in mime or ext == "docx":
        from docx import Document
        return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    if mime.startswith("text/") or "json" in mime or ext in ("txt", "md", "markdown", "csv", "json", "html", "htm"):
        return data.decode("utf-8", "ignore")
    raise HTTPException(400, f"Format Drive tidak didukung ({mime or ext}). Gunakan Google Docs/Sheets/Slides, PDF, Word, teks, atau gambar.")


async def drive_content(uid: str, file_id: str) -> dict:
    """Read a Drive file by id for the assistant: Google Docs/Sheets/Slides are exported, PDF/Word/text parsed, images returned as base64."""
    f = await _g(uid, "GET", f"{DRIVE}/files/{file_id}", params={"fields": FILE_FIELDS})
    mime = f.get("mimeType") or ""
    if int(f.get("size") or 0) > MAX_DRIVE_BYTES:
        raise HTTPException(400, "Berkas Drive lebih dari 8 MB")
    if mime in (GDOC, GSHEET, GSLIDES):
        exp = "text/csv" if mime == GSHEET else "text/plain"
        return {**f, "text": (await _g_bytes(uid, f"{DRIVE}/files/{file_id}/export", {"mimeType": exp})).decode("utf-8", "ignore")}
    data = await _g_bytes(uid, f"{DRIVE}/files/{file_id}", {"alt": "media"})
    if mime.startswith("image/"):
        return {**f, "image_b64": base64.b64encode(data).decode()}
    return {**f, "text": _bytes_text(data, mime, f.get("name") or "")}


async def drive_connected(uid: str) -> bool:
    return bool(await db.drive_credentials.find_one({"user_id": uid}, {"_id": 1}))


async def drive_update(uid: str, name_or_id: str, text: str, mode: str = "append") -> dict:
    f = await drive_find(uid, name_or_id)
    if f.get("mimeType") != GDOC:
        raise HTTPException(400, "Saat ini hanya Google Docs yang bisa diubah oleh asisten")
    doc = await _g(uid, "GET", f"{DOCS}/documents/{f['id']}")
    end = max(1, int(doc["body"]["content"][-1]["endIndex"]) - 1)
    reqs = []
    if mode == "replace" and end > 1:
        reqs.append({"deleteContentRange": {"range": {"startIndex": 1, "endIndex": end}}})
        end = 1
    reqs.append({"insertText": {"location": {"index": end}, "text": ("\n" if end > 1 else "") + text}})
    await _g(uid, "POST", f"{DOCS}/documents/{f['id']}:batchUpdate", json={"requests": reqs})
    return f


async def drive_link(uid: str, name_or_id: str, share: bool = False) -> dict:
    f = await drive_find(uid, name_or_id)
    if share:
        await _g(uid, "POST", f"{DRIVE}/files/{f['id']}/permissions", json={"role": "reader", "type": "anyone"})
    return {**f, "shared": share}


# ---------- REST endpoints (UI + voice tools) ----------
class SaveIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="doc", pattern="^(doc|sheet)$")
    task_id: Optional[str] = None
    conversation_id: Optional[str] = None  # voice tool: save the task under discussion in this chat
    content: Optional[str] = Field(default=None, max_length=200_000)


class UpdateIn(BaseModel):
    file: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=50_000)
    mode: str = Field(default="append", pattern="^(append|replace)$")


class LinkIn(BaseModel):
    file: str = Field(min_length=1, max_length=300)
    share: bool = False


@router.get("/google/status")
async def google_status(u: dict = Depends(current_user)):
    return {"configured": configured(), "connected": await drive_connected(u["id"]), "picker": bool(os.environ.get("GOOGLE_API_KEY"))}


@router.get("/google/picker-token")
async def picker_token(u: dict = Depends(current_user)):
    """Short-lived access token for the Google Picker in the browser (drive.file: only files the user picks become visible to Oryntix)."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(503, "Google Picker belum dikonfigurasi (GOOGLE_API_KEY).")
    return {"access_token": await access_token(u["id"]), "api_key": api_key, "app_id": os.environ["GOOGLE_CLIENT_ID"].split("-")[0]}


@router.get("/google/files")
async def files(q: str = "", limit: int = 20, u: dict = Depends(current_user)):
    safe = q.replace("\\", "").replace("'", "\\'")
    query = f"name contains '{safe}' and trashed = false" if q else "trashed = false and mimeType != 'application/vnd.google-apps.folder'"
    r = await _g(u["id"], "GET", f"{DRIVE}/files", params={"pageSize": max(1, min(limit, 50)), "q": query, "orderBy": "modifiedTime desc", "fields": f"files({FILE_FIELDS})"})
    return {"files": r.get("files", [])}


@router.get("/google/content")
async def content(file_id: str, u: dict = Depends(current_user)):
    out = await drive_content(u["id"], file_id)
    out.pop("image_b64", None)
    return {**out, "text": (out.get("text") or "")[:20000]}


@router.post("/google/save")
async def save(x: SaveIn, u: dict = Depends(current_user)):
    md = x.content or ""
    if not md and not x.task_id and x.conversation_id:
        conv = await db.conversations.find_one({"id": x.conversation_id}, {"_id": 0, "task_id": 1})
        x.task_id = (conv or {}).get("task_id")
    if x.task_id:
        from workspace import task_access
        t = await db.tasks.find_one({"id": x.task_id, **task_access(u)}, {"_id": 0, "final_output": 1, "goal": 1})
        if not t:
            raise HTTPException(404, "Dokumen tidak ditemukan")
        md = t.get("final_output") or ""
    if len(md.strip()) < 2:
        raise HTTPException(400, "Isi dokumen kosong")
    return await drive_save(u["id"], x.title, md, x.kind, source={"task_id": x.task_id})


@router.post("/google/update")
async def update(x: UpdateIn, u: dict = Depends(current_user)):
    return await drive_update(u["id"], x.file, x.text, x.mode)


@router.post("/google/link")
async def link(x: LinkIn, u: dict = Depends(current_user)):
    return await drive_link(u["id"], x.file, x.share)


@router.get("/google/read")
async def read(file: str, u: dict = Depends(current_user)):
    return await drive_read(u["id"], file)
