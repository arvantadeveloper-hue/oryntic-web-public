"""Assistant portraits as cacheable, content-addressed URLs instead of ~1 MB base64 strings embedded in every persona / conversation / message document."""
import asyncio
import base64
import hashlib
import logging
from collections import OrderedDict
from typing import Optional, Tuple

from fastapi import APIRouter, HTTPException, Response
from db import db
from storage import put_object, get_object

router = APIRouter(prefix="/portraits")
log = logging.getLogger("portraits")
_mem: "OrderedDict[str, Tuple[bytes, str]]" = OrderedDict()
_MEM_MAX = 60
EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def is_data_url(v) -> bool:
    return isinstance(v, str) and v.startswith("data:")


def _decode(data_url: str) -> Tuple[bytes, str, str]:
    head, b64 = data_url.split(",", 1)
    ctype = head[5:].split(";")[0] or "image/jpeg"
    return base64.b64decode(b64), ctype, EXT.get(ctype, "jpg")


async def save_portrait(pid: str, data_url: str) -> str:
    """Store the image once (content hash in the path → browser can cache it forever) and return the public URL to keep in `portrait`."""
    data, ctype, ext = _decode(data_url)
    h = hashlib.sha1(data).hexdigest()[:16]
    name = f"{h}.{ext}"
    await asyncio.to_thread(put_object, f"aivora/portraits/{pid}/{name}", data, ctype)
    _remember(f"{pid}/{name}", data, ctype)
    return f"/api/portraits/{pid}/{name}"


def _remember(key: str, data: bytes, ctype: str):
    _mem[key] = (data, ctype)
    _mem.move_to_end(key)
    while len(_mem) > _MEM_MAX:
        _mem.popitem(last=False)


@router.get("/{pid}/{name}")
async def serve_portrait(pid: str, name: str, request_etag: Optional[str] = None):
    key = f"{pid}/{name}"
    hit = _mem.get(key)
    if not hit:
        try:
            data, ctype = await asyncio.to_thread(get_object, f"aivora/portraits/{key}")
        except Exception as exc:
            raise HTTPException(404, "Portrait not found") from exc
        _remember(key, data, ctype)
        hit = (data, ctype)
    data, ctype = hit
    return Response(content=data, media_type=ctype or "image/jpeg",
                    headers={"Cache-Control": "public, max-age=31536000, immutable", "ETag": f'"{name.split(".")[0]}"'})


async def migrate_portraits():
    """One-off, idempotent: move base64 portraits out of personas, conversation members and messages."""
    n = 0
    async for p in db.personas.find({"portrait": {"$regex": "^data:"}}, {"_id": 0, "id": 1, "portrait": 1}):
        try:
            url = await save_portrait(p["id"], p["portrait"])
        except Exception as exc:
            log.warning("portrait migration failed for %s: %s", p["id"], exc)
            continue
        await db.personas.update_one({"id": p["id"]}, {"$set": {"portrait": url}})
        await db.conversations.update_many({"members.id": p["id"]}, {"$set": {"members.$[m].portrait": url}}, array_filters=[{"m.id": p["id"]}])
        await db.messages.update_many({"persona_id": p["id"], "portrait": {"$regex": "^data:"}}, {"$set": {"portrait": url}})
        n += 1
    # stray copies whose persona is gone or already migrated
    await db.messages.update_many({"portrait": {"$regex": "^data:"}}, {"$set": {"portrait": None}})
    await db.conversations.update_many({"members.portrait": {"$regex": "^data:"}}, {"$set": {"members.$[m].portrait": None}}, array_filters=[{"m.portrait": {"$regex": "^data:"}}])
    if n:
        log.info("migrated %d portraits to object storage", n)
