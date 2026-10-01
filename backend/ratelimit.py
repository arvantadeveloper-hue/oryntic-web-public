import time
from collections import deque
from fastapi import HTTPException
from db import db, now_iso

# Per-user sliding-window rate limits (in-process). Keys: chat_per_min, voice_per_min, calls_per_hour, max_call_minutes.
DEFAULT_LIMITS = {"chat_per_min": 20, "voice_per_min": 30, "calls_per_hour": 20, "max_call_minutes": 60, "generation_per_hour": 30}
_cache = {"at": 0.0, "limits": dict(DEFAULT_LIMITS)}
_hits: dict = {}


async def get_limits() -> dict:
    if time.time() - _cache["at"] > 30:
        cfg = await db.config.find_one({"id": "rate_limits"}, {"_id": 0, "id": 0, "updated_at": 0})
        _cache["limits"] = {**DEFAULT_LIMITS, **(cfg or {})}
        _cache["at"] = time.time()
    return _cache["limits"]


async def set_limits(doc: dict) -> dict:
    await db.config.update_one({"id": "rate_limits"}, {"$set": {**doc, "updated_at": now_iso()}}, upsert=True)
    _cache["at"] = 0.0
    return await get_limits()


def _allow(key: str, limit: int, window: float) -> bool:
    now = time.time()
    q = _hits.setdefault(key, deque())
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


async def rate_limit(user: dict, bucket: str):
    """bucket: chat | voice | calls | generation. Raises 429 when the user's window is exhausted."""
    lim = await get_limits()
    spec = {"chat": (lim["chat_per_min"], 60, "pesan"), "voice": (lim["voice_per_min"], 60, "permintaan suara"),
            "calls": (lim["calls_per_hour"], 3600, "panggilan"), "generation": (lim["generation_per_hour"], 3600, "pembuatan")}[bucket]
    if not _allow(f"{user['id']}:{bucket}", spec[0], spec[1]):
        per = "menit" if spec[1] == 60 else "jam"
        raise HTTPException(429, f"Terlalu banyak {spec[2]} ({spec[0]}/{per}). Tunggu sebentar lalu coba lagi.")
