import asyncio
import io
import re
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from auth import current_user
from db import db, now_iso, new_id, clean
from files import _path_parts, _same_workspace
from storage import get_object
from workspace import EXPORTS, has_tables, task_access

router = APIRouter(prefix="/api", tags=["shares"])
HOURS = (1, 24, 168, 720)


class ShareIn(BaseModel):
    kind: str = Field(pattern="^(document|image|video|file)$")
    name: str = Field(min_length=1, max_length=200)
    path: Optional[str] = None
    task_id: Optional[str] = None
    hours: int = 24


async def _check_owner(x: ShareIn, u: dict):
    if x.kind == "document":
        t = await db.tasks.find_one({"id": x.task_id, **task_access(u)}, {"_id": 0, "id": 1})
        if not t:
            raise HTTPException(404, "Dokumen tidak ditemukan")
    else:
        parts = _path_parts(x.path or "")
        if parts[2] != u["id"] and not await _same_workspace(u["id"], parts[2]):
            raise HTTPException(403, "Bukan berkas Anda")


@router.post("/shares")
async def create_share(x: ShareIn, u: dict = Depends(current_user)):
    """Public, expiring link for a gallery item: /s/<code>."""
    if x.hours not in HOURS:
        raise HTTPException(400, "Masa berlaku tidak valid")
    await _check_owner(x, u)
    doc = {"id": new_id(), "code": secrets.token_urlsafe(9), "user_id": u["id"], "kind": x.kind, "name": x.name, "path": x.path, "task_id": x.task_id,
           "hours": x.hours, "expires_at": (datetime.now(timezone.utc) + timedelta(hours=x.hours)).isoformat(), "revoked": False, "views": 0, "created_at": now_iso()}
    await db.shares.insert_one(dict(doc))
    return clean(doc)


@router.get("/shares")
async def my_shares(u: dict = Depends(current_user)):
    rows = await db.shares.find({"user_id": u["id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    for r in rows:
        r["active"] = not r.get("revoked") and r.get("expires_at", "") > now_iso()
    return rows


@router.delete("/shares/{code}")
async def revoke_share(code: str, u: dict = Depends(current_user)):
    r = await db.shares.update_one({"code": code, "user_id": u["id"]}, {"$set": {"revoked": True, "revoked_at": now_iso()}})
    if not r.matched_count:
        raise HTTPException(404, "Tautan tidak ditemukan")
    return {"ok": True}


async def _live(code: str) -> dict:
    s = await db.shares.find_one({"code": code}, {"_id": 0})
    if not s or s.get("revoked") or s.get("expires_at", "") < now_iso():
        raise HTTPException(404, "Tautan tidak valid atau sudah kedaluwarsa")
    return s


@router.get("/public/share/{code}")
async def public_share(code: str):
    s = await _live(code)
    await db.shares.update_one({"code": code}, {"$inc": {"views": 1}})
    owner = await db.users.find_one({"id": s["user_id"]}, {"_id": 0, "name": 1}) or {}
    out = {"code": code, "kind": s["kind"], "name": s["name"], "expires_at": s["expires_at"], "shared_by": owner.get("name") or "Pengguna Oryntix"}
    if s["kind"] == "document":
        t = await db.tasks.find_one({"id": s["task_id"]}, {"_id": 0, "goal": 1, "final_output": 1, "persona_name": 1, "updated_at": 1}) or {}
        out.update({"title": t.get("goal") or s["name"], "content": t.get("final_output") or "", "persona_name": t.get("persona_name"), "has_tables": has_tables(t.get("final_output") or "")})
    return out


@router.get("/public/share/{code}/file")
async def public_share_file(code: str, download: int = 0):
    s = await _live(code)
    if not s.get("path"):
        raise HTTPException(404, "Bukan berkas")
    try:
        data, ctype = await asyncio.to_thread(get_object, s["path"])
    except Exception as exc:
        raise HTTPException(404, "Berkas tidak ditemukan") from exc
    headers = {"Content-Disposition": f'attachment; filename="{s["name"]}"'} if download else {}
    return Response(content=data, media_type=ctype, headers=headers)


@router.get("/public/share/{code}/export/{fmt}")
async def public_share_export(code: str, fmt: str):
    s = await _live(code)
    if s["kind"] != "document" or fmt not in EXPORTS:
        raise HTTPException(400, "Format tidak didukung")
    t = await db.tasks.find_one({"id": s["task_id"]}, {"_id": 0, "goal": 1, "final_output": 1}) or {}
    md = t.get("final_output") or ""
    if fmt == "xlsx" and not has_tables(md):
        raise HTTPException(400, "Tidak ada tabel")
    mime, builder = EXPORTS[fmt]
    title = (t.get("goal") or s["name"])[:80]
    safe = re.sub(r"[^\w\- ]+", "", title).strip().replace(" ", "-")[:40] or "dokumen"
    return StreamingResponse(io.BytesIO(builder(title, md)), media_type=mime, headers={"Content-Disposition": f'attachment; filename="{safe}.{fmt}"'})
