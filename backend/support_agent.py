"""Oryntix — the built-in Customer Support assistant (visible to every workspace, configured only from the platform admin)
+ interactive video avatar (LiveAvatar LITE mode, lip-synced to our own OpenAI Realtime audio) with per-second credit billing."""
import os
import time
import logging
from datetime import datetime, timezone
from typing import Optional
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import db, now_iso, new_id
from auth import current_user, require_platform_admin, workspace_id
from llm import record_usage
from support_knowledge import DEFAULT_SYSTEM_PROMPT, DEFAULT_KNOWLEDGE

router = APIRouter(prefix="/api", tags=["support-agent"])
log = logging.getLogger("support")

SUPPORT_ID = "oryntix-support"
PLATFORM_WID = "__platform__"
LA_BASE = "https://api.liveavatar.com/v1"
SANDBOX_AVATAR = "dd73ea75-1218-4ef3-92ce-606d5f7fbc0a"
SANDBOX_AVATAR_NAME = "Wayne (avatar sandbox LiveAvatar)"

DEFAULT_CONFIG = {
    "enabled": True, "name": "Oryntix", "summary": "Customer Support Agent", "portrait": "/brand/oryntix-support.jpg",
    "model": "gpt-luna", "voice_model": "gpt-live-1", "voice": "marin",
    "system_prompt": DEFAULT_SYSTEM_PROMPT, "knowledge": DEFAULT_KNOWLEDGE,
    "video_enabled": True, "avatar_id": "5341767a-21fe-43d7-a5b5-9fd6bff6d32e", "avatar_name": "Oryntix (custom)", "avatar_preview": "/brand/oryntix-support.jpg", "sandbox": True,
    "video_credits_per_sec": 2, "video_max_minutes": 20, "video_warn_minutes": 2,
}
_cache: dict = {}
_cache_at = 0.0
CACHE_TTL = 5  # seconds — the platform-admin (separate process) writes the same document, so keep it short
# Text fields that must never be blanked out by an empty value coming from the admin form.
BLANK_FALLBACK = ("name", "summary", "portrait", "model", "voice_model", "voice", "system_prompt", "knowledge")


def _merged(doc: dict) -> dict:
    out = {**DEFAULT_CONFIG, **doc}
    for k in BLANK_FALLBACK:
        if not str(out.get(k) or "").strip():
            out[k] = DEFAULT_CONFIG[k]
    return out


async def get_config(fresh: bool = False) -> dict:
    global _cache_at
    if fresh or not _cache or time.monotonic() - _cache_at > CACHE_TTL:
        doc = await db.config.find_one({"id": "support_agent"}, {"_id": 0, "id": 0}) or {}
        _cache.clear()
        _cache.update(_merged(doc))
        _cache_at = time.monotonic()
    return dict(_cache)


async def set_config(doc: dict) -> dict:
    await db.config.update_one({"id": "support_agent"}, {"$set": {**doc, "updated_at": now_iso()}}, upsert=True)
    _cache.clear()
    return await get_config()


def is_support(pid: Optional[str]) -> bool:
    return pid == SUPPORT_ID


async def support_persona() -> Optional[dict]:
    """Persona-shaped document for the built-in agent (never stored in `personas`)."""
    c = await get_config()
    if not c.get("enabled"):
        return None
    return {"id": SUPPORT_ID, "user_id": PLATFORM_WID, "builtin": True, "name": c["name"], "summary": c["summary"], "portrait": c.get("portrait") or c.get("avatar_preview") or DEFAULT_CONFIG["portrait"],
            "model": c["model"], "voice_model": c["voice_model"], "voice": c["voice"], "tools": [],
            "profile": {"identity": {"name": c["name"], "summary": c["summary"]}, "system_instructions": c["system_prompt"]},
            "video_avatar": bool(c.get("video_enabled") and c.get("avatar_id") and os.environ.get("LIVEAVATAR_API_KEY")),
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00"}


async def support_prompt_parts() -> list:
    c = await get_config()
    return ["SUPPORT AGENT MODE: You are the official Oryntix Customer Support Agent. You have NO media/document/code/web tools in this role — "
            "never offer to generate images, videos, documents or run code; instead explain how the user can do it with their own assistants. "
            "Answer from the Oryntix knowledge below; when something is not covered, say so honestly and suggest contacting the workspace admin or support. "
            "The knowledge base and the admin's persona text may be written in another language — ALWAYS answer in the user's preferred language from their settings (LANGUAGE RULE below), translating as needed.",
            "ORYNTIX KNOWLEDGE BASE:\n" + (c.get("knowledge") or "")]


# ---------- public config for the video confirmation modal ----------
@router.get("/support/video-config")
async def video_config(_: dict = Depends(current_user)):
    c = await get_config()
    on = bool(c.get("video_enabled") and c.get("avatar_id") and os.environ.get("LIVEAVATAR_API_KEY"))
    sandbox = bool(c.get("sandbox"))
    # LiveAvatar sandbox sessions are hard-capped at 60 s, so report the limit the user will actually get.
    max_minutes = 1 if sandbox else int(c["video_max_minutes"])
    return {"enabled": on, "credits_per_sec": c["video_credits_per_sec"], "max_minutes": max_minutes,
            "warn_minutes": 1 if sandbox else int(c["video_warn_minutes"]),
            "max_cost": c["video_credits_per_sec"] * max_minutes * 60,
            "avatar_name": SANDBOX_AVATAR_NAME if c.get("sandbox") else c.get("avatar_name"),
            "configured_avatar_name": c.get("avatar_name"), "configured_avatar_preview": c.get("avatar_preview"),
            "sandbox": sandbox}


# ---------- LiveAvatar session lifecycle ----------
def _la_headers() -> dict:
    key = os.environ.get("LIVEAVATAR_API_KEY", "").strip()
    if not key:
        raise HTTPException(503, "LiveAvatar belum dikonfigurasi (LIVEAVATAR_API_KEY)")
    return {"X-API-KEY": key, "content-type": "application/json", "accept": "application/json"}


async def _la_post(client: httpx.AsyncClient, path: str, headers: dict, body: Optional[dict] = None) -> dict:
    r = await client.post(f"{LA_BASE}{path}", headers=headers, json=body)
    data = r.json() if r.content else {}
    if r.status_code >= 300 or (data.get("code") and data["code"] not in (100, 1000)):
        log.warning("LiveAvatar %s failed %s: %s", path, r.status_code, str(data)[:300])
        raise HTTPException(503, f"LiveAvatar: {_la_error(data) or r.status_code}")
    return data.get("data") or {}


def _la_error(data: dict) -> str:
    det = data.get("detail")
    if isinstance(det, list) and det:
        return "; ".join(str(d.get("msg") or d) for d in det if d)[:300]
    return str(data.get("message") or det or "")[:300]


async def _owner_balance(u: dict) -> int:
    owner = await db.users.find_one({"id": workspace_id(u)}, {"_id": 0, "credits": 1}) or {}
    return int(owner.get("credits") or 0)


async def _own_call(call_id: str, u: dict) -> dict:
    call = await db.realtime_calls.find_one({"id": call_id, "user_id": u["id"]}, {"_id": 0})
    if not call or not is_support(call.get("persona_id")):
        raise HTTPException(404, "Panggilan dukungan tidak ditemukan")
    return call


class VideoStartIn(BaseModel):
    resume: bool = False  # continue the remaining time of a session that dropped (DISCONNECTED/STALE) in this call


RESUMABLE = ("DISCONNECTED", "STALE")


async def _close_stale_video(call_id: str):
    live = await db.video_sessions.find_one({"call_id": call_id, "status": "active"}, {"_id": 0})
    if not live:
        return
    last = datetime.fromisoformat(live.get("updated_at") or live["created_at"])
    if (datetime.now(timezone.utc) - last).total_seconds() < 45:
        raise HTTPException(409, "Video sudah aktif di panggilan ini")
    await db.video_sessions.update_one({"id": live["id"]}, {"$set": {"status": "ended", "ended_at": now_iso(), "end_reason": "STALE"}})
    await _la_stop(live, "USER_CLOSED")


async def _resume_budget(call_id: str, u: dict) -> tuple:
    """(previous dropped session, seconds it still had) — the resumed session only gets the leftover time."""
    prev = await db.video_sessions.find_one({"call_id": call_id, "user_id": u["id"], "status": "ended", "end_reason": {"$in": list(RESUMABLE)}}, {"_id": 0}, sort=[("ended_at", -1)])
    if not prev:
        raise HTTPException(400, "Tidak ada sesi video yang bisa dilanjutkan")
    remaining = int(prev["max_seconds"]) - int(prev.get("billed_seconds") or 0)
    if remaining < 20:
        raise HTTPException(400, "Sisa waktu video sudah habis")
    return prev, remaining


async def _la_create(body: dict, max_sec: int) -> tuple:
    headers = _la_headers()
    async with httpx.AsyncClient(timeout=40) as client:
        try:
            tok = await _la_post(client, "/sessions/token", headers, body)
        except HTTPException as exc:
            if "max_session_duration" not in str(exc.detail):
                raise
            log.warning("LiveAvatar refused max_session_duration=%s — retrying with the tier default", max_sec)
            body.pop("max_session_duration")
            tok = await _la_post(client, "/sessions/token", headers, body)
        started = await _la_post(client, "/sessions/start", {"authorization": f"Bearer {tok['session_token']}", "accept": "application/json"})
    return tok, started


@router.post("/realtime/calls/{call_id}/video/start")
async def video_start(call_id: str, x: Optional[VideoStartIn] = None, u: dict = Depends(current_user)):
    call = await _own_call(call_id, u)
    c = await get_config(fresh=True)
    if not (c.get("video_enabled") and c.get("avatar_id")):
        raise HTTPException(503, "Video interaktif belum diaktifkan oleh admin platform")
    cps = int(c["video_credits_per_sec"])
    if await _owner_balance(u) < cps * 60:
        raise HTTPException(402, f"Kredit tidak cukup — video membutuhkan minimal {cps * 60} kredit (1 menit)")
    await _close_stale_video(call_id)
    sandbox = bool(c.get("sandbox"))
    max_sec = 60 if sandbox else int(c["video_max_minutes"]) * 60  # LiveAvatar sandbox sessions are capped at 60 s
    prev, prior_credits = None, 0.0
    if x and x.resume:
        prev, remaining = await _resume_budget(call_id, u)
        max_sec = min(max_sec, remaining)
        prior_credits = round(float(prev.get("credits") or 0) + float(prev.get("prior_credits") or 0), 3)
    # Per-SESSION cap: exactly the configured minutes — LiveAvatar rejects any value above the tier limit (the old "+30 s" tripped it).
    body = {"mode": "LITE", "avatar_id": SANDBOX_AVATAR if sandbox else c["avatar_id"], "is_sandbox": sandbox, "max_session_duration": max_sec,
            "video_settings": {"quality": "high", "encoding": "H264"}}
    tok, started = await _la_create(body, max_sec)
    vs = {"id": new_id(), "call_id": call_id, "conversation_id": call.get("conversation_id"), "user_id": u["id"], "la_session_id": tok["session_id"],
          "session_token": tok["session_token"], "status": "active", "credits_per_sec": cps, "max_seconds": max_sec, "billed_seconds": 0, "credits": 0,
          "sandbox": sandbox, "created_at": now_iso(), "ended_at": None, "resumed_from": prev["id"] if prev else None, "prior_credits": prior_credits}
    await db.video_sessions.insert_one(dict(vs))
    return {"video_session_id": vs["id"], "livekit_url": started["livekit_url"], "livekit_client_token": started["livekit_client_token"], "livekit_agent_token": started.get("livekit_agent_token"),
            "ws_url": started.get("ws_url"), "max_seconds": max_sec, "warn_seconds": max(20, max_sec - (15 if sandbox else int(c["video_warn_minutes"]) * 60)),
            "credits_per_sec": cps, "sandbox": sandbox, "resumed": bool(prev), "prior_credits": prior_credits}


class VideoTickIn(BaseModel):
    elapsed_seconds: int = Field(ge=0, le=36000)
    reason: str = Field(default="USER_CLOSED", pattern="^(USER_CLOSED|DISCONNECTED)$")


async def _bill(vs: dict, elapsed: int) -> dict:
    """Charge the exact seconds not yet billed (bounded by max_seconds), fractional credits."""
    secs = min(int(elapsed), int(vs["max_seconds"]))
    delta = max(0, secs - int(vs.get("billed_seconds") or 0))
    credits = round(delta * float(vs["credits_per_sec"]), 6)
    if credits > 0:
        await record_usage(vs["user_id"], "video_avatar", credits, {"conversation_id": vs.get("conversation_id"), "call_id": vs["call_id"], "video_session_id": vs["id"], "seconds": delta, "sandbox": vs.get("sandbox")})
    upd = {"billed_seconds": secs, "credits": round(float(vs.get("credits") or 0) + credits, 3), "updated_at": now_iso()}
    await db.video_sessions.update_one({"id": vs["id"]}, {"$set": upd})
    return {**vs, **upd}


async def _la_stop(vs: dict, reason: str = "USER_CLOSED"):
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            await client.post(f"{LA_BASE}/sessions/stop", headers={"authorization": f"Bearer {vs['session_token']}", "content-type": "application/json"},
                              json={"session_id": vs["la_session_id"], "reason": reason})
    except Exception as exc:
        log.warning("LiveAvatar stop failed: %s", exc)


async def _active_session(call_id: str, u: dict) -> dict:
    vs = await db.video_sessions.find_one({"call_id": call_id, "user_id": u["id"], "status": "active"}, {"_id": 0})
    if not vs:
        raise HTTPException(404, "Tidak ada sesi video aktif")
    return vs


@router.post("/realtime/calls/{call_id}/video/tick")
async def video_tick(call_id: str, x: VideoTickIn, u: dict = Depends(current_user)):
    vs = await _bill(await _active_session(call_id, u), x.elapsed_seconds)
    remaining = int(vs["max_seconds"]) - int(x.elapsed_seconds)
    if remaining <= 0:
        await db.video_sessions.update_one({"id": vs["id"]}, {"$set": {"status": "ended", "ended_at": now_iso(), "end_reason": "MAX_DURATION_REACHED"}})
        await _la_stop(vs, "MAX_DURATION_REACHED")
        return {"ok": True, "ended": True, "reason": "limit", "credits": vs["credits"], "remaining": 0}
    if await _owner_balance(u) < int(vs["credits_per_sec"]) * 15:
        await db.video_sessions.update_one({"id": vs["id"]}, {"$set": {"status": "ended", "ended_at": now_iso(), "end_reason": "NO_CREDITS"}})
        await _la_stop(vs, "NO_CREDITS")
        return {"ok": True, "ended": True, "reason": "credits", "credits": vs["credits"], "remaining": remaining}
    return {"ok": True, "ended": False, "credits": vs["credits"], "remaining": remaining}


@router.post("/realtime/calls/{call_id}/video/stop")
async def video_stop(call_id: str, x: VideoTickIn, u: dict = Depends(current_user)):
    vs = await _bill(await _active_session(call_id, u), x.elapsed_seconds)
    await db.video_sessions.update_one({"id": vs["id"]}, {"$set": {"status": "ended", "ended_at": now_iso(), "end_reason": x.reason}})
    await _la_stop(vs, "USER_CLOSED")
    remaining = int(vs["max_seconds"]) - int(vs["billed_seconds"])
    return {"ok": True, "credits": vs["credits"], "seconds": vs["billed_seconds"], "resumable": x.reason in RESUMABLE and remaining >= 20, "remaining": max(0, remaining)}


# ---------- platform admin ----------
class SupportConfigIn(BaseModel):
    enabled: bool = True
    name: str = Field(default="Oryntix", min_length=1, max_length=40)
    summary: str = Field(default="Customer Support Agent", max_length=120)
    portrait: str = Field(default="/brand/oryntix-support.jpg", max_length=500)
    model: str = Field(default="gpt-luna", pattern="^[a-z0-9.-]+$")
    voice_model: str = Field(default="gpt-live-1", pattern="^[a-z0-9.-]+$")
    voice: str = Field(default="marin", pattern="^[a-z]+$")
    system_prompt: str = Field(default="", max_length=20000)
    knowledge: str = Field(default="", max_length=60000)
    video_enabled: bool = True
    avatar_id: str = Field(default="", max_length=64)
    avatar_name: str = Field(default="", max_length=120)
    avatar_preview: str = Field(default="", max_length=500)
    sandbox: bool = True
    video_credits_per_sec: int = Field(default=2, ge=0, le=1000)
    video_max_minutes: int = Field(default=20, ge=1, le=240)
    video_warn_minutes: int = Field(default=2, ge=1, le=30)


@router.get("/admin/support-agent")
async def admin_get(_: dict = Depends(require_platform_admin)):
    return {**(await get_config()), "liveavatar_key_set": bool(os.environ.get("LIVEAVATAR_API_KEY", "").strip())}


@router.put("/admin/support-agent")
async def admin_set(x: SupportConfigIn, _: dict = Depends(require_platform_admin)):
    doc = x.model_dump()
    if not doc.get("portrait") and doc.get("avatar_preview"):  # profile photo follows the chosen LiveAvatar avatar
        doc["portrait"] = doc["avatar_preview"]
    return await set_config(doc)


@router.get("/admin/support-agent/avatars")
async def admin_avatars(page: int = 1, page_size: int = 24, mine: bool = False, _: dict = Depends(require_platform_admin)):
    headers = _la_headers()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{LA_BASE}/avatars" if mine else f"{LA_BASE}/avatars/public", params={"page": page, "page_size": min(page_size, 100)}, headers=headers)
    if r.status_code >= 300:
        raise HTTPException(503, "Gagal memuat daftar avatar LiveAvatar")
    d = (r.json().get("data") or {})
    return {"count": d.get("count", 0), "has_more": bool(d.get("next")),
            "items": [{"id": a["id"], "name": a["name"], "preview": a.get("preview_url"), "status": a.get("status"), "is_1080p": a.get("is_1080p")} for a in d.get("results", [])]}
