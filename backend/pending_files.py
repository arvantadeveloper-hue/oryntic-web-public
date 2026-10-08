"""Files produced by provider tools (Code Interpreter charts/CSV, GPT Image) are HELD temporarily (disk + db.pending_files, 2 h) and only
written to the user's storage — or Google Drive — after the user presses "Simpan" on the chat card."""
import asyncio
import os
import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from db import db, now_iso, new_id
from auth import current_user, current_user_q
from storage import put_object

router = APIRouter(prefix="/api/pending-files", tags=["pending-files"])
TMP_DIR = os.environ.get("PENDING_FILES_DIR", "/tmp/oryntix_pending")
TTL = 2 * 3600
IMAGE_MIMES = ("image/png", "image/jpeg", "image/webp", "image/gif")


def _kind(mime: str) -> str:
    return "image" if (mime or "").lower() in IMAGE_MIMES else "file"


async def _sweep():
    cutoff = time.time() - TTL
    old = await db.pending_files.find({"created_ts": {"$lt": cutoff}}, {"_id": 0, "id": 1}).to_list(500)
    for f in old:
        try:
            os.remove(os.path.join(TMP_DIR, f["id"]))
        except OSError:
            pass
    if old:
        await db.pending_files.delete_many({"id": {"$in": [f["id"] for f in old]}})


async def hold_file(uid: str, name: str, mime: str, data: bytes, meta: Optional[dict] = None) -> dict:
    """Park the bytes on disk; returns the card payload {id, name, mime, size, kind, ...meta}."""
    os.makedirs(TMP_DIR, exist_ok=True)
    await _sweep()
    fid = new_id()
    await asyncio.to_thread(lambda: open(os.path.join(TMP_DIR, fid), "wb").write(data))
    doc = {"id": fid, "user_id": uid, "name": name or "berkas", "mime": mime or "application/octet-stream", "size": len(data), "kind": _kind(mime), **(meta or {}),
           "created_at": now_iso(), "created_ts": time.time()}
    await db.pending_files.insert_one(dict(doc))
    return {k: v for k, v in doc.items() if k not in ("user_id", "created_ts")}


async def _owned(fid: str, uid: str) -> dict:
    f = await db.pending_files.find_one({"id": fid, "user_id": uid}, {"_id": 0})
    if not f or not os.path.exists(os.path.join(TMP_DIR, fid)):
        raise HTTPException(404, "Berkas sementara sudah kedaluwarsa (2 jam). Minta asisten membuatnya lagi.")
    return f


@router.get("/{fid}")
async def preview(fid: str, u: dict = Depends(current_user_q)):
    f = await _owned(fid, u["id"])
    data = await asyncio.to_thread(lambda: open(os.path.join(TMP_DIR, fid), "rb").read())
    return Response(content=data, media_type=f["mime"], headers={"Content-Disposition": f"inline; filename=\"{f['name']}\"", "Cache-Control": "private, max-age=600"})


class SaveIn(BaseModel):
    message_id: str
    target: str = "storage"  # storage | drive


@router.post("/{fid}/save")
async def save(fid: str, x: SaveIn, u: dict = Depends(current_user)):
    """Persist a held file: platform storage (quota-checked → 413 with the Drive hint) or the user's Google Drive. Updates the chat message's media[]."""
    from integrations import assert_quota, add_storage, drive_save, drive_connected
    f = await _owned(fid, u["id"])
    msg = await db.messages.find_one({"id": x.message_id}, {"_id": 0, "id": 1, "pending_files": 1, "media": 1})
    if not msg:
        raise HTTPException(404, "Pesan tidak ditemukan")
    data = await asyncio.to_thread(lambda: open(os.path.join(TMP_DIR, fid), "rb").read())
    ext = os.path.splitext(f["name"])[1] or (".png" if f["kind"] == "image" else "")
    if x.target == "drive":
        if not await drive_connected(u["id"]):
            raise HTTPException(400, "Google Drive belum terhubung. Hubungkan di menu Integrasi.")
        item = await drive_save(u["id"], f["name"], kind="file", data=data, mime=f["mime"], source={"kind": "tool_file", "message_id": x.message_id})
        media = {"type": f["kind"], "drive_id": item["drive_id"], "link": item.get("link"), "name": f["name"], "prompt": f.get("prompt")}
    else:
        await assert_quota(u["id"], len(data))
        folder = "images" if f["kind"] == "image" else "files"
        path = f"aivora/{folder}/{u['id']}/{new_id()}{ext}"
        await asyncio.to_thread(put_object, path, data, f["mime"])
        await add_storage(u["id"], len(data))
        media = {"type": f["kind"], "path": path, "name": f["name"], "prompt": f.get("prompt"), **({"format": ext.lstrip(".")} if f["kind"] == "file" else {})}
    media = {k: v for k, v in media.items() if v is not None}
    await db.messages.update_one({"id": x.message_id}, {"$push": {"media": media}, "$pull": {"pending_files": {"id": fid}}})
    await db.pending_files.delete_one({"id": fid})
    try:
        os.remove(os.path.join(TMP_DIR, fid))
    except OSError:
        pass
    return {"ok": True, "media": media, "target": x.target}


@router.delete("/{fid}")
async def discard(fid: str, message_id: str, u: dict = Depends(current_user)):
    await _owned(fid, u["id"])
    await db.messages.update_one({"id": message_id}, {"$pull": {"pending_files": {"id": fid}}})
    await db.pending_files.delete_one({"id": fid})
    try:
        os.remove(os.path.join(TMP_DIR, fid))
    except OSError:
        pass
    return {"ok": True}
