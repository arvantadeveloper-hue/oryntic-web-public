"""GitHub Connect (Level 1): the user pastes a fine-grained Personal Access Token; the assistant can list repos,
read files/trees/issues and open pull requests with LLM-authored changes. Token stored encrypted (Fernet keyed from JWT_SECRET)."""
import base64
import hashlib
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import httpx
from cryptography.fernet import Fernet
from db import db, now_iso, new_id
from auth import current_user, JWT_SECRET

router = APIRouter(prefix="/api/integrations/github", tags=["github"])
API = "https://api.github.com"
_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(("github:" + JWT_SECRET).encode()).digest()))
MAX_FILE = 60_000


async def gh_status(uid: str) -> dict:
    g = await db.github_credentials.find_one({"user_id": uid}, {"_id": 0, "login": 1, "name": 1, "avatar": 1, "connected_at": 1})
    return {"connected": bool(g), **(g or {})}


async def gh_connected(uid: str) -> bool:
    return bool(await db.github_credentials.find_one({"user_id": uid}, {"_id": 1}))


async def _token(uid: str) -> str:
    g = await db.github_credentials.find_one({"user_id": uid}, {"_id": 0, "token": 1})
    if not g:
        raise HTTPException(400, "GitHub belum terhubung. Hubungkan di menu Integrasi.")
    return _fernet.decrypt(g["token"].encode()).decode()


async def _gh(token: str, method: str, path: str, **kw):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.request(method, path if path.startswith("http") else API + path, headers=headers, **kw)
    if r.status_code == 404:
        raise HTTPException(404, "Tidak ditemukan di GitHub (periksa nama repo/path dan izin token).")
    if r.status_code >= 400:
        msg = (r.json().get("message") if r.headers.get("content-type", "").startswith("application/json") else r.text[:200]) or r.text[:200]
        raise HTTPException(502, f"GitHub menolak permintaan: {msg}")
    return r.json() if r.content else {}


def _repo(full: str) -> str:
    full = (full or "").strip().removeprefix("https://github.com/").strip("/")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", full):
        raise HTTPException(400, f"Nama repo tidak valid: '{full}' (format owner/repo)")
    return full


# ---------- operations (shared by chat tools, voice tools and REST) ----------
async def gh_repos(uid: str, q: str = "", limit: int = 30) -> list:
    tok = await _token(uid)
    rows = await _gh(tok, "GET", "/user/repos", params={"per_page": 100, "sort": "updated", "affiliation": "owner,collaborator,organization_member"})
    out = [{"full_name": r["full_name"], "private": r["private"], "description": r.get("description") or "", "default_branch": r.get("default_branch"),
            "language": r.get("language"), "updated_at": r.get("updated_at"), "url": r["html_url"], "open_issues": r.get("open_issues_count", 0)} for r in rows]
    if q:
        ql = q.lower()
        out = [r for r in out if ql in r["full_name"].lower() or ql in r["description"].lower()]
    return out[:limit]


async def gh_tree(uid: str, repo: str, ref: Optional[str] = None, limit: int = 300) -> dict:
    tok = await _token(uid)
    repo = _repo(repo)
    if not ref:
        ref = (await _gh(tok, "GET", f"/repos/{repo}")).get("default_branch", "main")
    t = await _gh(tok, "GET", f"/repos/{repo}/git/trees/{ref}", params={"recursive": "1"})
    paths = [x["path"] for x in t.get("tree", []) if x["type"] == "blob" and not re.search(r"(^|/)(node_modules|\.git|dist|build|__pycache__)(/|$)", x["path"])]
    return {"repo": repo, "ref": ref, "count": len(paths), "truncated": len(paths) > limit, "paths": paths[:limit]}


async def gh_read(uid: str, repo: str, path: str, ref: Optional[str] = None) -> dict:
    tok = await _token(uid)
    repo = _repo(repo)
    d = await _gh(tok, "GET", f"/repos/{repo}/contents/{path.strip('/')}", params={"ref": ref} if ref else None)
    if isinstance(d, list):
        return {"repo": repo, "path": path, "dir": True, "entries": [{"name": x["name"], "type": x["type"], "path": x["path"]} for x in d][:200]}
    raw = base64.b64decode(d.get("content") or "") if d.get("encoding") == "base64" else b""
    text = raw.decode("utf-8", errors="replace")
    return {"repo": repo, "path": d["path"], "sha": d["sha"], "size": d.get("size"), "url": d.get("html_url"), "truncated": len(text) > MAX_FILE, "content": text[:MAX_FILE]}


async def gh_issues(uid: str, repo: str, state: str = "open", limit: int = 20) -> list:
    tok = await _token(uid)
    rows = await _gh(tok, "GET", f"/repos/{_repo(repo)}/issues", params={"state": state if state in ("open", "closed", "all") else "open", "per_page": limit})
    return [{"number": r["number"], "title": r["title"], "state": r["state"], "is_pr": "pull_request" in r, "url": r["html_url"], "author": (r.get("user") or {}).get("login"),
             "labels": [x["name"] for x in r.get("labels", [])], "body": (r.get("body") or "")[:600], "updated_at": r.get("updated_at")} for r in rows]


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "update").lower()).strip("-")[:40] or "update"


async def gh_create_pr(uid: str, repo: str, title: str, body: str, changes: list, base: Optional[str] = None) -> dict:
    """changes: [{path, content}] (full new file content; content null/'' with delete=true removes the file)."""
    tok = await _token(uid)
    repo = _repo(repo)
    if not changes:
        raise HTTPException(400, "Tidak ada perubahan berkas untuk PR.")
    info = await _gh(tok, "GET", f"/repos/{repo}")
    base = base or info.get("default_branch", "main")
    base_sha = (await _gh(tok, "GET", f"/repos/{repo}/git/ref/heads/{base}"))["object"]["sha"]
    branch = f"oryntix/{_slug(title)}-{new_id()[:6]}"
    await _gh(tok, "POST", f"/repos/{repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": base_sha})
    for ch in changes:
        path = (ch.get("path") or "").strip("/")
        if not path:
            continue
        sha = None
        try:
            cur = await _gh(tok, "GET", f"/repos/{repo}/contents/{path}", params={"ref": branch})
            sha = cur.get("sha") if isinstance(cur, dict) else None
        except HTTPException:
            sha = None
        if ch.get("delete"):
            if sha:
                await _gh(tok, "DELETE", f"/repos/{repo}/contents/{path}", json={"message": f"{title}: hapus {path}", "sha": sha, "branch": branch})
            continue
        payload = {"message": f"{title}: {path}", "content": base64.b64encode((ch.get("content") or "").encode("utf-8")).decode(), "branch": branch}
        if sha:
            payload["sha"] = sha
        await _gh(tok, "PUT", f"/repos/{repo}/contents/{path}", json=payload)
    pr = await _gh(tok, "POST", f"/repos/{repo}/pulls", json={"title": title[:200], "body": (body or "") + "\n\n_Dibuat oleh asisten Oryntix._", "head": branch, "base": base})
    return {"repo": repo, "number": pr["number"], "url": pr["html_url"], "branch": branch, "base": base, "title": pr["title"], "files": [c.get("path") for c in changes if c.get("path")]}


# ---------- REST ----------
class ConnectIn(BaseModel):
    token: str = Field(min_length=20, max_length=400)


class RepoIn(BaseModel):
    repo: str = Field(max_length=200)
    path: Optional[str] = Field(default="", max_length=500)
    ref: Optional[str] = Field(default=None, max_length=120)
    state: Optional[str] = Field(default="open", max_length=10)


class PrIn(BaseModel):
    repo: str = Field(max_length=200)
    title: str = Field(min_length=3, max_length=200)
    body: str = Field(default="", max_length=10000)
    changes: list = Field(min_length=1, max_length=20)
    base: Optional[str] = Field(default=None, max_length=120)


@router.get("/status")
async def status(u: dict = Depends(current_user)):
    return await gh_status(u["id"])


@router.post("")
async def connect(x: ConnectIn, u: dict = Depends(current_user)):
    tok = x.token.strip()
    try:
        me = await _gh(tok, "GET", "/user")
    except HTTPException as e:
        raise HTTPException(400, "Token GitHub tidak valid atau kedaluwarsa.") from e
    await db.github_credentials.update_one({"user_id": u["id"]}, {"$set": {"user_id": u["id"], "token": _fernet.encrypt(tok.encode()).decode(), "login": me.get("login"),
                                                                           "name": me.get("name"), "avatar": me.get("avatar_url"), "connected_at": now_iso()}}, upsert=True)
    return await gh_status(u["id"])


@router.delete("")
async def disconnect(u: dict = Depends(current_user)):
    await db.github_credentials.delete_one({"user_id": u["id"]})
    return {"ok": True}


@router.get("/repos")
async def repos(q: str = "", u: dict = Depends(current_user)):
    return {"items": await gh_repos(u["id"], q)}


@router.post("/tree")
async def tree(x: RepoIn, u: dict = Depends(current_user)):
    return await gh_tree(u["id"], x.repo, x.ref)


@router.post("/read")
async def read(x: RepoIn, u: dict = Depends(current_user)):
    return await gh_read(u["id"], x.repo, x.path or "", x.ref)


@router.post("/issues")
async def issues(x: RepoIn, u: dict = Depends(current_user)):
    return {"items": await gh_issues(u["id"], x.repo, x.state or "open")}


@router.post("/pr")
async def create_pr(x: PrIn, u: dict = Depends(current_user)):
    return await gh_create_pr(u["id"], x.repo, x.title, x.body, x.changes, x.base)
