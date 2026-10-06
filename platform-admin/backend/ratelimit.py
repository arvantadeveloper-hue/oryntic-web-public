import time
from collections import deque
from fastapi import HTTPException
from db import db, now_iso

# Per-user sliding-window rate limits (in-process). Keys: chat_per_min, voice_per_min, calls_per_hour, max_call_minutes.
DEFAULT_LIMITS = {"chat_per_min": 20, "chat_per_hour": 300, "chat_min_interval_ms": 1500, "chat_max_inflight": 4, "chat_dup_per_30s": 3,
                  "voice_per_min": 30, "calls_per_hour": 20, "max_call_minutes": 60, "generation_per_hour": 30, "storage_quota_mb": 50}
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


_last_prune = {"at": 0.0}


def _prune(now: float):
    if now - _last_prune["at"] < 300:
        return
    _last_prune["at"] = now
    for k in [k for k, q in _hits.items() if not q or q[-1] < now - 3600]:
        _hits.pop(k, None)


def _allow(key: str, limit: int, window: float) -> bool:
    now = time.time()
    _prune(now)
    q = _hits.setdefault(key, deque())
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def login_allowed(ip: str, email: str) -> bool:
    """Brute-force guard: 10 attempts / 5 min per IP and per account."""
    return _allow(f"login:ip:{ip}", 10, 300) and _allow(f"login:acct:{email}", 10, 300)


async def rate_limit(user: dict, bucket: str):
    """bucket: chat | voice | calls | generation. Raises 429 when the user's window is exhausted."""
    lim = await get_limits()
    spec = {"chat": (lim["chat_per_min"], 60, "pesan"), "voice": (lim["voice_per_min"], 60, "permintaan suara"),
            "calls": (lim["calls_per_hour"], 3600, "panggilan"), "generation": (lim["generation_per_hour"], 3600, "pembuatan")}[bucket]
    if not _allow(f"{user['id']}:{bucket}", spec[0], spec[1]):
        per = "menit" if spec[1] == 60 else "jam"
        raise HTTPException(429, f"Terlalu banyak {spec[2]} ({spec[0]}/{per}). Tunggu sebentar lalu coba lagi.", headers={"Retry-After": "5" if spec[1] == 60 else "60"})


# ---------- message throttling (layered, per user) ----------
_last_msg: dict = {}       # user -> monotonic time of last accepted message
_inflight: dict = {}       # user -> number of replies currently streaming
_recent_text: dict = {}    # user -> deque[(time, hash)]


def _too_many(msg: str, retry: int):
    raise HTTPException(429, msg, headers={"Retry-After": str(max(1, retry))})


async def throttle_message(user: dict, content: str):
    """Burst guard (min interval), per-minute + per-hour windows, duplicate-spam guard. Call before accepting a chat message."""
    lim = await get_limits()
    uid = user["id"]
    now = time.time()
    gap = int(lim.get("chat_min_interval_ms", 1500)) / 1000
    since = now - _last_msg.get(uid, 0)
    if since < gap:
        _too_many("Pelan-pelan ya — tunggu sebentar sebelum mengirim pesan berikutnya.", 1)
    if not _allow(f"{uid}:chat", int(lim["chat_per_min"]), 60):
        _too_many(f"Terlalu banyak pesan ({lim['chat_per_min']}/menit). Tunggu sebentar lalu coba lagi.", 10)
    if not _allow(f"{uid}:chat_hour", int(lim.get("chat_per_hour", 300)), 3600):
        _too_many(f"Batas {lim.get('chat_per_hour', 300)} pesan/jam tercapai. Coba lagi nanti.", 300)
    if int(_inflight.get(uid, 0)) >= int(lim.get("chat_max_inflight", 4)):
        _too_many("Masih ada beberapa balasan yang sedang diproses. Tunggu salah satunya selesai.", 3)
    q = _recent_text.setdefault(uid, deque())
    h = hash((content or "").strip().lower())
    while q and q[0][0] < now - 30:
        q.popleft()
    if sum(1 for _, x in q if x == h) >= int(lim.get("chat_dup_per_30s", 3)):
        _too_many("Pesan yang sama dikirim berulang kali. Tunggu 30 detik.", 30)
    q.append((now, h))
    _last_msg[uid] = now


def inflight_start(uid: str):
    _inflight[uid] = _inflight.get(uid, 0) + 1


def inflight_end(uid: str):
    _inflight[uid] = max(0, _inflight.get(uid, 0) - 1)
