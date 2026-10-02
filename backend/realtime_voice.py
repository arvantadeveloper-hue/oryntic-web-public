import math
import os
import json
import httpx
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from db import db, now_iso, new_id
from auth import current_user, require_platform_admin, workspace_id
from llm import record_usage, quota_exceeded, quota_message
from chat import _can_access, _persona_system, _history_text
from realtime import notify
from ratelimit import rate_limit, get_limits, set_limits
from pricing import usd_to_credits, realtime_usage_usd, get_pricing as platform_pricing, set_pricing as platform_set_pricing, compute_rates

router = APIRouter(prefix="/api", tags=["realtime-voice"])

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
REALTIME_MODEL = os.environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime")

# TTS voice (persona.voice) -> Realtime voice
VOICE_MAP = {"alloy": "alloy", "echo": "echo", "shimmer": "shimmer", "nova": "coral", "onyx": "ash", "fable": "ballad",
             "ash": "ash", "coral": "coral", "sage": "sage", "verse": "verse", "marin": "marin", "cedar": "cedar", "ballad": "ballad"}
MODERATOR_OPENING = ("YOU OPEN THE MEETING as the Moderator: greet {uname} warmly by name, name the participants ({roster}), state the "
                     "meeting's purpose in one sentence (title: \"{title}\"), then invite {uname} to start. 3-4 short spoken sentences.")
NO_REPEAT = ("Listen to what the other participants already said. NEVER repeat or paraphrase a point someone else has made; "
             "if you agree, say so in a few words and ADD something new (a different angle, risk, example, or decision). "
             "If you have nothing new, say briefly that you have nothing to add.")

async def get_pricing() -> dict:
    return await platform_pricing()


def credits_per_min(p: dict) -> int:
    return compute_rates(p)["realtime_per_min"]


def enabled() -> bool:
    return bool(OPENAI_API_KEY)


@router.get("/realtime/status")
async def status(u: dict = Depends(current_user)):
    p = await get_pricing()
    return {"enabled": enabled(), "model": REALTIME_MODEL, "credits_per_min": credits_per_min(p)}


class PricingIn(BaseModel):
    provider_usd_per_min: float = Field(gt=0)
    margin_pct: float = Field(ge=0, le=500)
    tax_pct: float = Field(ge=0, le=100)
    usd_to_idr: float = Field(gt=0)
    idr_per_credit: float = Field(gt=0)


@router.get("/admin/realtime-pricing")
async def admin_pricing(_: dict = Depends(require_platform_admin)):
    p = await get_pricing()
    return {**p, "credits_per_min": credits_per_min(p), "model": REALTIME_MODEL, "enabled": enabled()}


@router.put("/admin/realtime-pricing")
async def admin_set_pricing(x: PricingIn, _: dict = Depends(require_platform_admin)):
    doc = await platform_set_pricing(x.model_dump())
    return {**doc, "credits_per_min": credits_per_min(doc)}


class LimitsIn(BaseModel):
    chat_per_min: int = Field(ge=1, le=1000)
    voice_per_min: int = Field(ge=1, le=1000)
    calls_per_hour: int = Field(ge=1, le=1000)
    max_call_minutes: int = Field(ge=1, le=600)
    generation_per_hour: int = Field(ge=1, le=1000)


@router.get("/admin/rate-limits")
async def admin_limits(_: dict = Depends(require_platform_admin)):
    return await get_limits()


@router.put("/admin/rate-limits")
async def admin_set_limits(x: LimitsIn, _: dict = Depends(require_platform_admin)):
    return await set_limits(x.model_dump())


MULTI_STYLE = ("You are in a LIVE SPOKEN MEETING with the user and other AI assistants: {others}. You hear the user directly. "
               "What the other assistants say is delivered to you as text messages prefixed with their name in brackets. "
               "Speak ONLY when a response is requested from you. Keep each turn to 1-3 short spoken sentences, build on what "
               "others said without repeating them, never speak for them, and address the user by name now and then.")


class CallIn(BaseModel):
    conversation_id: str
    opening: Optional[str] = Field(default=None, max_length=1500)  # e.g. reminder the assistant must deliver first


async def _call_personas(conv: dict, u: dict) -> list:
    pids = conv.get("persona_ids") or ([conv["persona_id"]] if conv.get("persona_id") else [])
    personas = [p async for p in db.personas.find({"id": {"$in": pids}, "user_id": workspace_id(u), "deleted": {"$ne": True}}, {"_id": 0})]
    personas.sort(key=lambda p: pids.index(p["id"]))
    if not personas:
        raise HTTPException(400, "Percakapan ini tidak memiliki persona")
    return personas


async def _ensure_affordable(u: dict, n_sessions: int, cpm: int):
    over = await quota_exceeded(u)
    if over:
        raise HTTPException(402, quota_message(over))
    owner = await db.users.find_one({"id": workspace_id(u)}, {"_id": 0, "credits": 1}) or {}
    if (owner.get("credits") or 0) < cpm * n_sessions:
        raise HTTPException(402, "Kredit workspace tidak cukup untuk memulai panggilan")


async def _close_stale_calls(user_id: str):
    """Calls left open by a dropped tab (>2 min old); no extra charge beyond what ticks already billed."""
    stale_before = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    await db.realtime_calls.update_many({"user_id": user_id, "status": {"$in": ["created", "active"]}, "created_at": {"$lt": stale_before}},
                                        {"$set": {"status": "ended", "ended_at": now_iso(), "stale": True}})


async def _session_instructions(persona: dict, u: dict, roster: list, history: str, opening, is_first: bool, title: str = "") -> str:
    text = await _persona_system(persona, u, None, voice_mode=True)
    if len(roster) > 1:
        text += "\n\n" + MULTI_STYLE.format(others=", ".join(n for n in roster if n != persona["name"])) + "\n" + NO_REPEAT
    if history.strip():
        text += f"\n\nRecent conversation with the user (for context):\n{history[-3000:]}"
    uname = u.get("name") or "the user"
    if is_first and opening:
        text += (f"\n\nYOU ARE CALLING THE USER. Open the call immediately by delivering this reminder warmly in 2-3 short "
                 f"spoken sentences, greeting {uname} by name, then ask if they need anything: {opening}")
    elif is_first and len(roster) > 1:
        text += "\n\n" + MODERATOR_OPENING.format(uname=uname, roster=", ".join(roster), title=title or "meeting")
    elif is_first:
        text += f"\n\nThe user just joined. Greet {uname} briefly and warmly, then let them talk."
    return text


@router.post("/realtime/calls")
async def create_call(x: CallIn, u: dict = Depends(current_user)):
    if not enabled():
        raise HTTPException(503, "Mode Realtime belum diaktifkan (OPENAI_API_KEY belum diatur)")
    conv = await db.conversations.find_one({"id": x.conversation_id}, {"_id": 0})
    if not _can_access(conv, u):
        raise HTTPException(404, "Conversation not found")
    await rate_limit(u, "calls")
    personas = await _call_personas(conv, u)
    cpm = credits_per_min(await get_pricing())
    await _ensure_affordable(u, len(personas), cpm)
    await _close_stale_calls(u["id"])

    history = await _history_text(conv["id"], limit=12)
    roster = [q["name"] for q in personas]
    group_id = new_id()
    sessions = []
    for i, persona in enumerate(personas):
        call = {"id": new_id(), "group_id": group_id, "conversation_id": conv["id"], "user_id": u["id"], "persona_id": persona["id"],
                "voice": VOICE_MAP.get(persona.get("voice", "alloy"), "marin"),
                "instructions": await _session_instructions(persona, u, roster, history, x.opening, i == 0, conv.get("title", "")),
                "multi": len(personas) > 1, "primary": i == 0, "status": "created", "billed_minutes": 0, "credits": 0, "credits_per_min": cpm,
                "created_at": now_iso(), "started_at": None, "ended_at": None, "seconds": 0}
        await db.realtime_calls.insert_one(dict(call))
        sessions.append({"call_id": call["id"], "voice": call["voice"], "primary": i == 0,
                         "persona": {"id": persona["id"], "name": persona["name"], "portrait": persona.get("portrait")}})
    first = sessions[0]
    return {"call_id": first["call_id"], "voice": first["voice"], "persona": first["persona"], "model": REALTIME_MODEL,
            "credits_per_min": cpm, "credits_per_min_total": cpm * len(sessions), "multi": len(personas) > 1, "group_id": group_id,
            "sessions": sessions, "language": ((u.get("settings") or {}).get("conversation_language") or "id")}


async def _own_call(call_id: str, u: dict) -> dict:
    call = await db.realtime_calls.find_one({"id": call_id, "user_id": u["id"]}, {"_id": 0})
    if not call:
        raise HTTPException(404, "Call not found")
    return call


def vad_config(sensitivity: str, multi: bool) -> dict:
    """Semantic VAD judges whether the audio is meaningful speech; eagerness follows the user's mic sensitivity.
    interrupt_response is off: the browser confirms a real barge-in (noise gate open ≥300ms) before cancelling."""
    eager = {"low": "low", "medium": "medium", "high": "high"}.get(sensitivity or "medium", "medium")
    return {"type": "semantic_vad", "eagerness": eager, "create_response": not multi, "interrupt_response": False}


@router.post("/realtime/calls/{call_id}/negotiate", response_class=PlainTextResponse)
async def negotiate(call_id: str, request: Request, u: dict = Depends(current_user)):
    call = await _own_call(call_id, u)
    if call["status"] == "ended":
        raise HTTPException(400, "Call already ended")
    sdp_offer = (await request.body()).decode()
    settings = u.get("settings") or {}
    lang = settings.get("conversation_language") or "id"
    multi = bool(call.get("multi"))
    audio_in = {"turn_detection": vad_config(request.query_params.get("sensitivity") or settings.get("mic_sensitivity"), multi)}
    if not multi or call.get("primary"):
        audio_in["transcription"] = {"model": "gpt-4o-mini-transcribe", "language": lang}
    session = {
        "type": "realtime",
        "model": REALTIME_MODEL,
        "instructions": call["instructions"],
        "output_modalities": ["audio"],
        "audio": {"input": audio_in, "output": {"voice": call["voice"]}},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post("https://api.openai.com/v1/realtime/calls",
                              headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                              files={"sdp": (None, sdp_offer), "session": (None, json.dumps(session))})
    if r.status_code >= 300:
        raise HTTPException(502, "Negosiasi Realtime gagal, coba lagi")
    await db.realtime_calls.update_one({"id": call_id}, {"$set": {"status": "active", "started_at": now_iso(),
                                                                  "openai_call_id": r.headers.get("Location", "").rsplit("/", 1)[-1]}})
    return PlainTextResponse(r.text, media_type="application/sdp")


class TranscriptIn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=8000)


@router.post("/realtime/calls/{call_id}/transcript")
async def transcript(call_id: str, x: TranscriptIn, u: dict = Depends(current_user)):
    call = await _own_call(call_id, u)
    cid = call["conversation_id"]
    if x.role == "user":
        msg = {"id": new_id(), "conversation_id": cid, "role": "user", "content": x.content, "attachments": [],
               "sender_user_id": u["id"], "sender_name": u.get("name") or "User", "via": "realtime", "created_at": now_iso()}
    else:
        persona = await db.personas.find_one({"id": call["persona_id"]}, {"_id": 0}) or {}
        msg = {"id": new_id(), "conversation_id": cid, "role": "assistant", "content": x.content,
               "persona_id": call["persona_id"], "persona_name": persona.get("name") or "Asisten",
               "portrait": persona.get("portrait"), "credits": 0, "via": "realtime", "created_at": now_iso()}
    await db.messages.insert_one(dict(msg))
    await db.conversations.update_one({"id": cid}, {"$set": {"updated_at": now_iso(), "last_message": x.content[:120]}})
    await notify(cid, {"type": "message", "role": x.role})
    return {"ok": True, "message_id": msg["id"]}


class TickIn(BaseModel):
    elapsed_seconds: int = Field(ge=0, le=6 * 3600)


class UsageIn(BaseModel):
    usage: dict  # OpenAI `response.done` → response.usage


@router.post("/realtime/calls/{call_id}/usage")
async def report_usage(call_id: str, x: UsageIn, u: dict = Depends(current_user)):
    """Bill one Realtime response from its real token usage (audio in/out, text, cached) × margin."""
    call = await _own_call(call_id, u)
    p = await get_pricing()
    usd = realtime_usage_usd(p, x.usage or {})
    exact = usd_to_credits(p, usd)
    acc = float(call.get("usage_credits_exact") or 0) + exact
    charged = int(acc) - int(call.get("usage_credits_billed") or 0)
    if charged > 0:
        await record_usage(u["id"], "realtime_call", charged, {"call_id": call["id"], "conversation_id": call["conversation_id"], "usd": round(usd, 6)})
    await db.realtime_calls.update_one({"id": call["id"]}, {"$set": {"usage_credits_exact": acc, "usage_credits_billed": int(acc)},
                                                            "$inc": {"credits": charged, "usage_usd": usd}})
    return {"charged_now": charged, "credits_total": int(call.get("credits") or 0) + charged, "usd": round(usd, 6)}


async def _bill(call: dict, elapsed: int, u: dict) -> dict:
    minutes = max(1, math.ceil(elapsed / 60)) if elapsed > 0 else 0
    delta = minutes - int(call.get("billed_minutes") or 0)
    charged = 0
    if delta > 0:
        charged = delta * int(call["credits_per_min"])
        await record_usage(u["id"], "realtime_call", charged, {"call_id": call["id"], "conversation_id": call["conversation_id"], "minutes": delta})
    await db.realtime_calls.update_one({"id": call["id"]}, {"$set": {"billed_minutes": minutes, "seconds": elapsed},
                                                            "$inc": {"credits": charged}})
    return {"billed_minutes": minutes, "credits_total": int(call.get("credits") or 0) + charged, "charged_now": charged}


@router.post("/realtime/calls/{call_id}/tick")
async def tick(call_id: str, x: TickIn, u: dict = Depends(current_user)):
    call = await _own_call(call_id, u)
    if call["status"] == "ended":
        raise HTTPException(400, "Call already ended")
    out = await _bill(call, x.elapsed_seconds, u)
    lim = await get_limits()
    if x.elapsed_seconds >= lim["max_call_minutes"] * 60:
        await db.realtime_calls.update_one({"id": call_id}, {"$set": {"status": "ended", "ended_at": now_iso(), "reason": "max_duration"}})
        raise HTTPException(402, f"Durasi maksimal panggilan ({lim['max_call_minutes']} menit) tercapai")
    over = await quota_exceeded(u)
    owner = await db.users.find_one({"id": workspace_id(u)}, {"_id": 0, "credits": 1}) or {}
    if over or (owner.get("credits") or 0) <= 0:
        raise HTTPException(402, "Kuota/kredit habis — panggilan diakhiri")
    return out


@router.post("/realtime/calls/{call_id}/end")
async def end_call(call_id: str, x: TickIn, u: dict = Depends(current_user)):
    call = await _own_call(call_id, u)
    if call["status"] == "ended":
        return {"ok": True, "credits_total": call.get("credits", 0), "seconds": call.get("seconds", 0)}
    out = await _bill(call, x.elapsed_seconds, u)
    await db.realtime_calls.update_one({"id": call_id}, {"$set": {"status": "ended", "ended_at": now_iso()}})
    return {"ok": True, **out, "seconds": x.elapsed_seconds}
