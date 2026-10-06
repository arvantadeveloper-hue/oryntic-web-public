"""GitLab Connect (Level 1, incl. self-hosted instances): Personal Access Token (scope api) + instance URL.
Same capabilities as github.py — list projects, read tree/files/issues/MRs, commit changes on a branch and open a Merge Request."""
import base64
import hashlib
import re
from typing import Optional
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import httpx
from cryptography.fernet import Fernet
from db import db, now_iso, new_id
from auth import current_user, JWT_SECRET

router = APIRouter(prefix="/api/integrations/gitlab", tags=["gitlab"])
_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(("gitlab:" + JWT_SECRET).encode()).digest()))
MAX_FILE = 60_000
DEFAULT_URL = "https://gitlab.com"


def _norm_url(u: Optional[str]) -> str:
    u = (u or DEFAULT_URL).strip().rstrip("/")
    if not u.startswith("http"):
        u = "https://" + u
    if not re.fullmatch(r"https?://[\w.-]+(:\d+)?(/[\w.-]+)*", u):
        raise HTTPException(400, "URL instance GitLab tidak valid")
    return u


async def gl_status(uid: str) -> dict:
    g = await db.gitlab_credentials.find_one({"user_id": uid}, {"_id": 0, "login": 1, "name": 1, "avatar": 1, "connected_at": 1, "base_url": 1})
    return {"connected": bool(g), **(g or {})}


async def gl_connected(uid: str) -> bool:
    return bool(await db.gitlab_credentials.find_one({"user_id": uid}, {"_id": 1}))


async def _cred(uid: str) -> tuple:
    g = await db.gitlab_credentials.find_one({"user_id": uid}, {"_id": 0, "token": 1, "base_url": 1})
    if not g:
        raise HTTPException(400, "GitLab belum terhubung. Hubungkan di menu Integrasi.")
    return _fernet.decrypt(g["token"].encode()).decode(), g.get("base_url") or DEFAULT_URL


async def _gl(token: str, base: str, method: str, path: str, **kw):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.request(method, f"{base}/api/v4{path}", headers={"PRIVATE-TOKEN": token}, **kw)
    if r.status_code == 404:
        raise HTTPException(404, "Tidak ditemukan di GitLab (periksa nama proyek/path dan izin token).")
    if r.status_code >= 400:
        try:
            msg = r.json().get("message") or r.json().get("error") or r.text[:200]
        except Exception:
            msg = r.text[:200]
        raise HTTPException(502, f"GitLab menolak permintaan: {msg}")
    return r.json() if r.content else {}


def _pid(project: str) -> str:
    project = (project or "").strip().strip("/")
    project = re.sub(r"^https?://[^/]+/", "", project)
    if not re.fullmatch(r"[\w.-]+(/[\w.-]+)+", project) and not project.isdigit():
        raise HTTPException(400, f"Nama proyek tidak valid: '{project}' (format namespace/project)")
    return quote(project, safe="")


# ---------- operations (same shape as github.py) ----------
async def gl_projects(uid: str, q: str = "", limit: int = 30) -> list:
    tok, base = await _cred(uid)
    rows = await _gl(tok, base, "GET", "/projects", params={"membership": "true", "per_page": 100, "order_by": "last_activity_at", "simple": "true", **({"search": q} if q else {})})
    return [{"full_name": r["path_with_namespace"], "private": r.get("visibility") != "public", "description": r.get("description") or "", "default_branch": r.get("default_branch"),
             "url": r["web_url"], "updated_at": r.get("last_activity_at"), "open_issues": r.get("open_issues_count", 0)} for r in rows][:limit]


async def gl_tree(uid: str, project: str, ref: Optional[str] = None, limit: int = 300) -> dict:
    tok, base = await _cred(uid)
    pid = _pid(project)
    if not ref:
        ref = (await _gl(tok, base, "GET", f"/projects/{pid}")).get("default_branch", "main")
    paths = []
    for page in range(1, 6):
        rows = await _gl(tok, base, "GET", f"/projects/{pid}/repository/tree", params={"ref": ref, "recursive": "true", "per_page": 100, "page": page})
        paths += [x["path"] for x in rows if x["type"] == "blob" and not re.search(r"(^|/)(node_modules|\.git|dist|build|__pycache__)(/|$)", x["path"])]
        if len(rows) < 100:
            break
    return {"repo": project, "ref": ref, "count": len(paths), "truncated": len(paths) > limit, "paths": paths[:limit]}


async def gl_read(uid: str, project: str, path: str, ref: Optional[str] = None) -> dict:
    tok, base = await _cred(uid)
    pid = _pid(project)
    if not ref:
        ref = (await _gl(tok, base, "GET", f"/projects/{pid}")).get("default_branch", "main")
    path = path.strip("/")
    entries = await _gl(tok, base, "GET", f"/projects/{pid}/repository/tree", params={"ref": ref, "path": path, "per_page": 100})
    if entries and not any(e["path"] == path and e["type"] == "blob" for e in entries):
        return {"repo": project, "path": path, "dir": True, "entries": [{"name": e["name"], "type": "dir" if e["type"] == "tree" else "file", "path": e["path"]} for e in entries][:200]}
    d = await _gl(tok, base, "GET", f"/projects/{pid}/repository/files/{quote(path, safe='')}", params={"ref": ref})
    text = base64.b64decode(d.get("content") or "").decode("utf-8", errors="replace")
    return {"repo": project, "path": path, "sha": d.get("blob_id"), "size": d.get("size"), "url": f"{base}/{project.strip('/')}/-/blob/{ref}/{path}", "truncated": len(text) > MAX_FILE, "content": text[:MAX_FILE]}


async def gl_issues(uid: str, project: str, state: str = "open", limit: int = 20) -> list:
    tok, base = await _cred(uid)
    pid = _pid(project)
    st = {"open": "opened", "closed": "closed", "all": "all"}.get(state, "opened")
    issues = await _gl(tok, base, "GET", f"/projects/{pid}/issues", params={"state": st, "per_page": limit})
    mrs = await _gl(tok, base, "GET", f"/projects/{pid}/merge_requests", params={"state": st, "per_page": limit})
    fmt = lambda r, is_mr: {"number": r["iid"], "title": r["title"], "state": r["state"], "is_pr": is_mr, "url": r["web_url"], "author": (r.get("author") or {}).get("username"),
                            "labels": r.get("labels", []), "body": (r.get("description") or "")[:600], "updated_at": r.get("updated_at")}
    return [fmt(r, False) for r in issues] + [fmt(r, True) for r in mrs]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "update").lower()).strip("-")[:40] or "update"


async def gl_create_mr(uid: str, project: str, title: str, body: str, changes: list, base_branch: Optional[str] = None) -> dict:
    """One commit with all file changes on a new branch, then a Merge Request."""
    tok, base = await _cred(uid)
    pid = _pid(project)
    if not changes:
        raise HTTPException(400, "Tidak ada perubahan berkas untuk merge request.")
    target = base_branch or (await _gl(tok, base, "GET", f"/projects/{pid}")).get("default_branch", "main")
    branch = f"oryntix/{_slug(title)}-{new_id()[:6]}"
    await _gl(tok, base, "POST", f"/projects/{pid}/repository/branches", params={"branch": branch, "ref": target})
    existing = set((await gl_tree(uid, project, target, limit=100000))["paths"])
    actions = []
    for ch in changes:
        path = (ch.get("path") or "").strip("/")
        if not path:
            continue
        if ch.get("delete"):
            if path in existing:
                actions.append({"action": "delete", "file_path": path})
            continue
        actions.append({"action": "update" if path in existing else "create", "file_path": path, "content": ch.get("content") or ""})
    await _gl(tok, base, "POST", f"/projects/{pid}/repository/commits", json={"branch": branch, "commit_message": title[:200], "actions": actions})
    mr = await _gl(tok, base, "POST", f"/projects/{pid}/merge_requests", json={"source_branch": branch, "target_branch": target, "title": title[:200],
                                                                               "description": (body or "") + "\n\n_Dibuat oleh asisten Oryntix._", "remove_source_branch": True})
    return {"repo": project, "number": mr["iid"], "url": mr["web_url"], "branch": branch, "base": target, "title": mr["title"], "files": [a["file_path"] for a in actions]}


async def gl_mr_diff(uid: str, project: str, number: Optional[int] = None, max_chars: int = 45_000) -> dict:
    """MR metadata + per-file diffs for code review (latest open MR when number is omitted)."""
    tok, base = await _cred(uid)
    pid = _pid(project)
    if not number:
        rows = await _gl(tok, base, "GET", f"/projects/{pid}/merge_requests", params={"state": "opened", "order_by": "updated_at", "per_page": 1})
        if not rows:
            raise HTTPException(404, f"Tidak ada merge request terbuka di {project}.")
        number = rows[0]["iid"]
    mr = await _gl(tok, base, "GET", f"/projects/{pid}/merge_requests/{number}")
    ch = await _gl(tok, base, "GET", f"/projects/{pid}/merge_requests/{number}/changes")
    out, used = [], 0
    changes = ch.get("changes") or []
    for f in changes:
        patch = f.get("diff") or "(binary / tanpa diff)"
        if used + len(patch) > max_chars:
            patch = patch[: max(0, max_chars - used)] + "\n... (dipotong)"
        used += len(patch)
        status = "added" if f.get("new_file") else "removed" if f.get("deleted_file") else "renamed" if f.get("renamed_file") else "modified"
        out.append({"path": f.get("new_path") or f.get("old_path"), "status": status, "additions": None, "deletions": None, "patch": patch})
        if used >= max_chars:
            break
    return {"repo": project, "number": number, "title": mr["title"], "body": (mr.get("description") or "")[:3000], "author": (mr.get("author") or {}).get("username"), "url": mr["web_url"],
            "base": mr.get("target_branch"), "head": mr.get("source_branch"), "state": mr.get("state"), "changed_files": len(changes), "additions": None, "deletions": None,
            "files": out, "truncated": len(out) < len(changes) or used >= max_chars}


# ---------- REST ----------
class ConnectIn(BaseModel):
    token: str = Field(min_length=10, max_length=400)
    base_url: Optional[str] = Field(default=None, max_length=200)


class RepoIn(BaseModel):
    repo: str = Field(max_length=200)
    path: Optional[str] = Field(default="", max_length=500)
    ref: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default="open", max_length=10)


class MrIn(BaseModel):
    repo: str = Field(max_length=200)
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(default="", max_length=10000)
    changes: list = Field(min_length=1, max_length=20)
    base: Optional[str] = Field(default=None, max_length=120)


@router.get("/status")
async def status(u: dict = Depends(current_user)):
    return await gl_status(u["id"])


@router.post("")
async def connect(x: ConnectIn, u: dict = Depends(current_user)):
    base = _norm_url(x.base_url)
    tok = x.token.strip()
    try:
        me = await _gl(tok, base, "GET", "/user")
    except (HTTPException, httpx.HTTPError) as e:
        raise HTTPException(400, f"Token GitLab tidak valid, kedaluwarsa, atau instance {base} tidak bisa dihubungi.") from e
    await db.gitlab_credentials.update_one({"user_id": u["id"]}, {"$set": {"user_id": u["id"], "token": _fernet.encrypt(tok.encode()).decode(), "base_url": base, "login": me.get("username"),
                                                                           "name": me.get("name"), "avatar": me.get("avatar_url"), "connected_at": now_iso()}}, upsert=True)
    return await gl_status(u["id"])


@router.delete("")
async def disconnect(u: dict = Depends(current_user)):
    await db.gitlab_credentials.delete_one({"user_id": u["id"]})
    return {"ok": True}


@router.get("/repos")
async def repos(q: str = "", u: dict = Depends(current_user)):
    return {"items": await gl_projects(u["id"], q)}


@router.post("/tree")
async def tree(x: RepoIn, u: dict = Depends(current_user)):
    return await gl_tree(u["id"], x.repo, x.ref)


@router.post("/read")
async def read(x: RepoIn, u: dict = Depends(current_user)):
    return await gl_read(u["id"], x.repo, x.path or "", x.ref)


@router.post("/issues")
async def issues(x: RepoIn, u: dict = Depends(current_user)):
    return {"items": await gl_issues(u["id"], x.repo, x.state or "open")}


@router.post("/pr")
async def create_mr(x: MrIn, u: dict = Depends(current_user)):
    return await gl_create_mr(u["id"], x.repo, x.title, x.body, x.changes, x.base)


class ReviewIn(BaseModel):
    repo: str = Field(max_length=200)
    number: Optional[int] = None


@router.post("/pr-diff")
async def mr_diff(x: ReviewIn, u: dict = Depends(current_user)):
    return await gl_mr_diff(u["id"], x.repo, x.number)
