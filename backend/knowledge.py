import base64
import io
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import current_user, workspace_id
from db import db, now_iso, new_id

router = APIRouter(prefix="/api", tags=["knowledge"])
MAX_BYTES = 8 * 1024 * 1024
MAX_CHARS = 200_000
CHUNK = 800
STOP = set("yang dan di ke dari untuk dengan pada adalah ini itu atau juga akan tidak ada sebagai oleh dalam the and for with that this from are was were have has not you your".split())


def _kw(text: str) -> set:
    return {w for w in re.findall(r"[a-zA-Z0-9\u00C0-\u024F]{3,}", (text or "").lower()) if w not in STOP}


def _html_to_text(html: str) -> str:
    t = re.sub(r"<(br|/p|/div|/li|/h[1-6])[^>]*>", "\n", html or "", flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _extract(name: str, data_b64: str) -> str:
    raw = base64.b64decode(data_b64.split(",")[-1])
    if len(raw) > MAX_BYTES:
        raise HTTPException(400, "Berkas lebih dari 8 MB")
    ext = (name or "").rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(raw)).pages)
    if ext == "docx":
        from docx import Document
        return "\n".join(p.text for p in Document(io.BytesIO(raw)).paragraphs)
    if ext in ("txt", "md", "markdown", "csv", "json", "html", "htm"):
        txt = raw.decode("utf-8", "ignore")
        return _html_to_text(txt) if ext in ("html", "htm") else txt
    raise HTTPException(400, "Format tidak didukung (PDF, Word, TXT, MD)")


def _chunks(text: str) -> list:
    text = re.sub(r"[ \t]+", " ", text)[:MAX_CHARS].strip()
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?=#)", text) if p.strip()]
    out, buf = [], ""
    for p in paras:
        if len(buf) + len(p) + 1 <= CHUNK:
            buf = f"{buf}\n{p}".strip()
        else:
            if buf:
                out.append(buf)
            while len(p) > CHUNK:
                out.append(p[:CHUNK]); p = p[CHUNK:]
            buf = p
    if buf:
        out.append(buf)
    return [{"i": i, "text": c, "kw": sorted(_kw(c))} for i, c in enumerate(out)]


class KnowledgeIn(BaseModel):
    title: str = Field(default="", max_length=160)
    html: Optional[str] = Field(default=None, max_length=400_000)
    text: Optional[str] = Field(default=None, max_length=MAX_CHARS)
    file_name: Optional[str] = None
    file_data: Optional[str] = None  # base64
    url: Optional[str] = Field(default=None, max_length=2000)
    drive_id: Optional[str] = Field(default=None, max_length=200)


async def _drive_text(uid: str, drive_id: str) -> tuple:
    """(file meta, text) from the user's Google Drive — requires the Drive integration to be connected."""
    from integrations import drive_content
    f = await drive_content(uid, drive_id)
    if f.get("image_b64"):
        raise HTTPException(400, "Gambar tidak bisa dijadikan pengetahuan; pilih dokumen/teks")
    return f, f.get("text") or ""


def _host_is_public(host: str) -> bool:
    """Resolve the host and refuse loopback/private/link-local/metadata/reserved addresses (SSRF guard)."""
    import ipaddress
    import socket
    host = (host or "").strip("[]").lower()
    if not host or host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
        return False
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified or (ip.version == 6 and ip.ipv4_mapped and not _host_is_public(str(ip.ipv4_mapped))):
            return False
    return True


def _check_url(url: str) -> None:
    from urllib.parse import urlsplit
    s = urlsplit(url)
    if s.scheme not in ("http", "https") or not s.hostname:
        raise HTTPException(400, "Tautan harus diawali http:// atau https://")
    if s.port not in (None, 80, 443) or s.username or s.password:
        raise HTTPException(400, "Tautan dengan port khusus atau kredensial tidak diizinkan")
    if not _host_is_public(s.hostname):
        raise HTTPException(400, "Tautan ke jaringan internal/privat tidak diizinkan")


async def _fetch_url(url: str) -> tuple:
    """Download a public web page and keep only its main text (trafilatura) → (title, text). Every hop is SSRF-checked, body capped at 8 MB."""
    import httpx
    import trafilatura
    import asyncio
    await asyncio.to_thread(_check_url, url)
    content, ctype, encoding = b"", "", "utf-8"
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept-Language": "id,en;q=0.8"}) as client:
            for _ in range(5):
                async with client.stream("GET", url) as r:
                    if r.is_redirect and r.headers.get("location"):
                        url = str(r.url.join(r.headers["location"]))
                        await asyncio.to_thread(_check_url, url)
                        continue
                    r.raise_for_status()
                    ctype = (r.headers.get("content-type") or "").lower()
                    body = bytearray()
                    async for chunk in r.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            raise HTTPException(400, "Halaman lebih dari 8 MB")
                    content, encoding = bytes(body), r.encoding or "utf-8"
                    break
            else:
                raise HTTPException(400, "Terlalu banyak pengalihan")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(400, f"Situs menolak permintaan (HTTP {exc.response.status_code})") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(400, "Tautan tidak dapat diakses") from exc
    text_body = content.decode(encoding, "ignore")
    if "html" in ctype or not ctype:
        html = text_body
        text = trafilatura.extract(html, include_comments=False, include_tables=True, favor_recall=True) or _html_to_text(html)
        m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
        title = _html_to_text(m.group(1)).strip()[:160] if m else ""
        return title, text
    if ctype.startswith("text/") or "json" in ctype or "markdown" in ctype:
        return "", text_body
    if "pdf" in ctype:
        from pypdf import PdfReader
        return "", "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(content)).pages)
    raise HTTPException(400, "Tautan bukan halaman web/teks/PDF")


async def _persona_of(pid: str, u: dict) -> dict:
    p = await db.personas.find_one({"id": pid, "user_id": workspace_id(u), "deleted": {"$ne": True}}, {"_id": 0, "id": 1, "user_id": 1})
    if not p:
        raise HTTPException(404, "Asisten tidak ditemukan")
    return p


def _pub(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "chunks"} | {"chunk_count": len(d.get("chunks") or [])}


@router.get("/personas/{pid}/knowledge")
async def list_knowledge(pid: str, u: dict = Depends(current_user)):
    await _persona_of(pid, u)
    return [_pub(d) async for d in db.knowledge_docs.find({"persona_id": pid}, {"_id": 0}).sort("created_at", -1)]


@router.post("/personas/{pid}/knowledge")
async def add_knowledge(pid: str, x: KnowledgeIn, u: dict = Depends(current_user)):
    """Reference knowledge for an assistant (upload or editor). Never 'priority': only the few chunks relevant to a message are injected."""
    p = await _persona_of(pid, u)
    url, page_title, drive = None, "", {}
    if x.drive_id:
        drive, text = await _drive_text(u["id"], x.drive_id)
        page_title, source, html = drive.get("name") or "", "drive", None
    elif x.url:
        url = x.url.strip()
        page_title, text = await _fetch_url(url)
        source, html = "url", None
    elif x.file_data:
        text, source, html = _extract(x.file_name or "", x.file_data), "upload", None
    elif x.html:
        text, source, html = _html_to_text(x.html), "editor", x.html
    else:
        text, source, html = x.text or "", "editor", None
    title = x.title.strip() or page_title or (x.file_name or "").strip() or (url or "")[:160]
    if not title:
        raise HTTPException(400, "Isi judul dokumen")
    if len(text.strip()) < 20:
        raise HTTPException(400, "Isi dokumen terlalu pendek atau tidak terbaca")
    doc = {"id": new_id(), "user_id": p["user_id"], "persona_id": pid, "title": title, "source": source, "file_name": x.file_name, "url": url, "html": html,
           "drive_id": drive.get("id"), "drive_link": drive.get("webViewLink"), "drive_mime": drive.get("mimeType"), "drive_user_id": u["id"] if drive else None,
           "chars": len(text), "chunks": _chunks(text), "enabled": True, "created_at": now_iso(), "updated_at": now_iso()}
    await db.knowledge_docs.insert_one(dict(doc))
    return _pub(doc)


@router.post("/personas/{pid}/knowledge/{kid}/refresh")
async def refresh_knowledge(pid: str, kid: str, u: dict = Depends(current_user)):
    """Re-download a URL- or Drive-sourced document so the assistant sees the latest content."""
    await _persona_of(pid, u)
    d = await db.knowledge_docs.find_one({"id": kid, "persona_id": pid}, {"_id": 0, "url": 1, "drive_id": 1, "drive_user_id": 1})
    if not d or not (d.get("url") or d.get("drive_id")):
        raise HTTPException(404, "Dokumen dari tautan/Drive tidak ditemukan")
    if d.get("drive_id"):
        _, text = await _drive_text(d.get("drive_user_id") or u["id"], d["drive_id"])
    else:
        _, text = await _fetch_url(d["url"])
    if len(text.strip()) < 20:
        raise HTTPException(400, "Isi halaman terlalu pendek atau tidak terbaca")
    r = await db.knowledge_docs.find_one_and_update({"id": kid}, {"$set": {"chars": len(text), "chunks": _chunks(text), "updated_at": now_iso()}}, projection={"_id": 0}, return_document=True)
    return _pub(r)


class KnowledgeUpdate(BaseModel):
    enabled: Optional[bool] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=160)
    html: Optional[str] = Field(default=None, max_length=400_000)


@router.put("/personas/{pid}/knowledge/{kid}")
async def update_knowledge(pid: str, kid: str, x: KnowledgeUpdate, u: dict = Depends(current_user)):
    await _persona_of(pid, u)
    fields = {"updated_at": now_iso()}
    if x.enabled is not None:
        fields["enabled"] = x.enabled
    if x.title:
        fields["title"] = x.title.strip()
    if x.html is not None:
        text = _html_to_text(x.html)
        fields.update({"html": x.html, "chars": len(text), "chunks": _chunks(text)})
    r = await db.knowledge_docs.find_one_and_update({"id": kid, "persona_id": pid}, {"$set": fields}, projection={"_id": 0}, return_document=True)
    if not r:
        raise HTTPException(404, "Dokumen tidak ditemukan")
    return _pub(r)


@router.get("/personas/{pid}/knowledge/{kid}")
async def get_knowledge(pid: str, kid: str, u: dict = Depends(current_user)):
    await _persona_of(pid, u)
    d = await db.knowledge_docs.find_one({"id": kid, "persona_id": pid}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Dokumen tidak ditemukan")
    return {**_pub(d), "text": "\n\n".join(c["text"] for c in d.get("chunks") or [])}


@router.delete("/personas/{pid}/knowledge/{kid}")
async def delete_knowledge(pid: str, kid: str, u: dict = Depends(current_user)):
    await _persona_of(pid, u)
    await db.knowledge_docs.delete_one({"id": kid, "persona_id": pid})
    return {"ok": True}


async def relevant_knowledge(persona_id: str, query: str, k: int = 3) -> list:
    """Top-k chunks sharing keywords with the message (>=2 overlaps). Cheap lexical retrieval, no embeddings."""
    q = _kw(query)
    if len(q) < 1:
        return []
    scored = []
    async for d in db.knowledge_docs.find({"persona_id": persona_id, "enabled": True}, {"_id": 0, "title": 1, "chunks": 1}):
        for c in d.get("chunks") or []:
            s = len(q & set(c.get("kw") or []))
            if s >= 2 or (s >= 1 and len(q) <= 2):
                scored.append((s, d["title"], c["text"]))
    scored.sort(key=lambda t: -t[0])
    return [{"title": t, "text": x} for _, t, x in scored[:k]]
