"""Files produced by provider tools (Code Interpreter charts/CSV, GPT Image) are HELD temporarily in MongoDB GridFS (shared across replicas, 2 h TTL)
and only written to the user's storage — or Google Drive — after the user presses "Simpan" on the chat card."""
import asyncio
import re
import time
from typing import Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from pydantic import BaseModel
from db import db, now_iso, new_id
from auth import current_user, current_user_q
from storage import put_object

router = APIRouter(prefix="/api/pending-files", tags=["pending-files"])
TTL = 2 * 3600
IMAGE_MIMES = ("image/png", "image/jpeg", "image/webp", "image/gif")
_bucket = AsyncIOMotorGridFSBucket(db, bucket_name="pending_blobs")


def _kind(mime: str) -> str:
    return "image" if (mime or "").lower() in IMAGE_MIMES else "file"


def _safe_name(name: str) -> str:
    return re.sub(r"[^\w.\- ()]+", "_", name or "berkas")[:120] or "berkas"


async def _drop_blob(f: dict):
    try:
        await _bucket.delete(ObjectId(f["blob_id"]))
    except Exception:
        pass


async def _sweep():
    cutoff = time.time() - TTL
    old = await db.pending_files.find({"created_ts": {"$lt": cutoff}}, {"_id": 0, "id": 1, "blob_id": 1}).to_list(500)
    for f in old:
        await _drop_blob(f)
    if old:
        await db.pending_files.delete_many({"id": {"$in": [f["id"] for f in old]}})


async def hold_file(uid: str, name: str, mime: str, data: bytes, meta: Optional[dict] = None) -> dict:
    """Park the bytes in GridFS; returns the card payload {id, name, mime, size, kind, ...meta}."""
    await _sweep()
    fid = new_id()
    name = _safe_name(name)
    blob_id = await _bucket.upload_from_stream(name, data, metadata={"user_id": uid, "pending_id": fid})
    doc = {"id": fid, "user_id": uid, "blob_id": str(blob_id), "name": name, "mime": mime or "application/octet-stream", "size": len(data), "kind": _kind(mime), **(meta or {}),
           "created_at": now_iso(), "created_ts": time.time()}
    await db.pending_files.insert_one(dict(doc))
    return {k: v for k, v in doc.items() if k not in ("user_id", "created_ts", "blob_id", "_id")}


async def _owned(fid: str, uid: str) -> dict:
    f = await db.pending_files.find_one({"id": fid, "user_id": uid}, {"_id": 0})
    if not f:
        raise HTTPException(404, "Berkas sementara sudah kedaluwarsa (2 jam). Minta asisten membuatnya lagi.")
    return f


async def _read(f: dict) -> bytes:
    try:
        stream = await _bucket.open_download_stream(ObjectId(f["blob_id"]))
        return await stream.read()
    except Exception:
        raise HTTPException(404, "Berkas sementara sudah kedaluwarsa (2 jam). Minta asisten membuatnya lagi.")


async def _own_message(message_id: str, u: dict) -> dict:
    from chat import _can_access
    msg = await db.messages.find_one({"id": message_id}, {"_id": 0, "id": 1, "conversation_id": 1})
    conv = msg and await db.conversations.find_one({"id": msg["conversation_id"]}, {"_id": 0, "user_id": 1, "participants": 1, "workspace_id": 1})
    if not msg or not _can_access(conv, u):
        raise HTTPException(404, "Pesan tidak ditemukan")
    return msg


@router.get("/{fid}")
async def preview(fid: str, u: dict = Depends(current_user_q)):
    f = await _owned(fid, u["id"])
    data = await _read(f)
    return Response(content=data, media_type=f["mime"], headers={"Content-Disposition": f"inline; filename=\"{_safe_name(f['name'])}\"", "Cache-Control": "private, max-age=600"})


class SaveIn(BaseModel):
    message_id: str
    target: str = "storage"  # storage | drive


@router.post("/{fid}/save")
async def save(fid: str, x: SaveIn, u: dict = Depends(current_user)):
    """Persist a held file: platform storage (quota-checked → 413 with the Drive hint) or the user's Google Drive. Updates the chat message's media[]."""
    from integrations import assert_quota, add_storage, drive_save, drive_connected
    f = await _owned(fid, u["id"])
    await _own_message(x.message_id, u)
    data = await _read(f)
    if x.target == "drive" and not await drive_connected(u["id"]):
        raise HTTPException(400, "Google Drive belum terhubung. Hubungkan di menu Integrasi.")
    if x.target != "drive":
        await assert_quota(u["id"], len(data))
    claimed = await db.pending_files.find_one_and_update({"id": fid, "claimed": {"$ne": True}}, {"$set": {"claimed": True}})
    if not claimed:
        raise HTTPException(409, "Berkas ini sedang/sudah disimpan.")
    try:
        if x.target == "drive":
            item = await drive_save(u["id"], f["name"], kind="file", data=data, mime=f["mime"], source={"kind": "tool_file", "message_id": x.message_id})
            media = {"type": f["kind"], "drive_id": item["drive_id"], "link": item.get("link"), "name": f["name"], "prompt": f.get("prompt")}
        else:
            ext = re.sub(r"^.*(\.[A-Za-z0-9]{1,5})$", r"\1", f["name"]) if "." in f["name"] else (".png" if f["kind"] == "image" else "")
            folder = "images" if f["kind"] == "image" else "files"
            path = f"aivora/{folder}/{u['id']}/{new_id()}{ext}"
            await asyncio.to_thread(put_object, path, data, f["mime"])
            await add_storage(u["id"], len(data))
            media = {"type": f["kind"], "path": path, "name": f["name"], "prompt": f.get("prompt"), **({"format": ext.lstrip(".")} if f["kind"] == "file" and ext else {})}
    except Exception:
        await db.pending_files.update_one({"id": fid}, {"$unset": {"claimed": ""}})
        raise
    media = {k: v for k, v in media.items() if v is not None}
    await db.messages.update_one({"id": x.message_id}, {"$push": {"media": media}, "$pull": {"pending_files": {"id": fid}}})
    await db.pending_files.delete_one({"id": fid})
    await _drop_blob(f)
    return {"ok": True, "media": media, "target": x.target}


@router.delete("/{fid}")
async def discard(fid: str, message_id: str, u: dict = Depends(current_user)):
    f = await _owned(fid, u["id"])
    await _own_message(message_id, u)
    await db.messages.update_one({"id": message_id}, {"$pull": {"pending_files": {"id": fid}}})
    await db.pending_files.delete_one({"id": fid})
    await _drop_blob(f)
    return {"ok": True}
