import os
import math
import json
import httpx
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from db import db, now_iso, new_id
from auth import current_user, require_admin, workspace_id
from llm import record_usage, quota_exceeded
from chat import _can_access, _persona_system, _history_text
from realtime import notify

router = APIRouter(prefix="/api", tags=["realtime-voice"])

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
REALTIME_MODEL = os.environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime")

# TTS voice (persona.voice) -> Realtime voice
VOICE_MAP = {"alloy": "alloy", "echo": "echo", "shimmer": "shimmer", "nova": "coral", "onyx": "ash", "fable": "ballad",
             "ash": "ash", "coral": "coral", "sage": "sage", "verse": "verse", "marin": "marin", "cedar": "cedar"}

DEFAULT_PRICING = {"provider_usd_per_min": 0.25, "margin_pct": 30.0, "tax_pct": 11.0, "usd_to_idr": 16500.0, "idr_per_credit": 80.0}


async def get_pricing() -> dict:
    cfg = await db.config.find_one({"id": "realtime_pricing"}, {"_id": 0, "id": 0})
    return {**DEFAULT_PRICING, **(cfg or {})}


def credits_per_min(p: dict) -> int:
    idr = p["provider_usd_per_min"] * (1 + p["margin_pct"] / 100) * (1 + p["tax_pct"] / 100) * p["usd_to_idr"]
    return max(1, math.ceil(idr / max(p["idr_per_credit"], 0.01)))


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
async def admin_pricing(_: dict = Depends(require_admin)):
    p = await get_pricing()
    return {**p, "credits_per_min": credits_per_min(p), "model": REALTIME_MODEL, "enabled": enabled()}


@router.put("/admin/realtime-pricing")
async def admin_set_pricing(x: PricingIn, _: dict = Depends(require_admin)):
    doc = x.model_dump()
    await db.config.update_one({"id": "realtime_pricing"}, {"$set": {**doc, "updated_at": now_iso()}}, upsert=True)
    return {**doc, "credits_per_min": credits_per_min(doc)}


class CallIn(BaseModel):
    conversation_id: str
    opening: Optional[str] = Field(default=None, max_length=1500)  # e.g. reminder the assistant must deliver first


@router.post("/realtime/calls")
async def create_call(x: CallIn, u: dict = Depends(current_user)):
    if not enabled():
        raise HTTPException(503, "Mode Realtime belum diaktifkan (OPENAI_API_KEY belum diatur)")
    conv = await db.conversations.find_one({"id": x.conversation_id}, {"_id": 0})
    if not _can_access(conv, u):
        raise HTTPException(404, "Conversation not found")
    over = await quota_exceeded(u)
    if over:
        raise HTTPException(402, f"Kuota kredit harian Anda habis ({over['used']}/{over['limit']})")
    persona = await db.personas.find_one({"id": conv.get("persona_id"), "user_id": workspace_id(u)}, {"_id": 0})
    if not persona:
        raise HTTPException(400, "Percakapan ini tidak memiliki persona")
    p = await get_pricing()
    cpm = credits_per_min(p)
    owner = await db.users.find_one({"id": workspace_id(u)}, {"_id": 0, "credits": 1}) or {}
    if (owner.get("credits") or 0) < cpm:
        raise HTTPException(402, "Kredit workspace tidak cukup untuk memulai panggilan")

    system = await _persona_system(persona, u, None, voice_mode=True)
    history = await _history_text(conv["id"], limit=12)
    instructions = system
    if history.strip():
        instructions += f"\n\nRecent conversation with the user (for context):\n{history[-3000:]}"
    if x.opening:
        instructions += (f"\n\nYOU ARE CALLING THE USER. Open the call immediately by delivering this reminder warmly in 2-3 short "
                         f"spoken sentences, greeting {u.get('name') or 'the user'} by name, then ask if they need anything: {x.opening}")
    else:
        instructions += f"\n\nThe user just picked up the call. Greet {u.get('name') or 'the user'} briefly and warmly, then let them talk."

    call = {"id": new_id(), "conversation_id": conv["id"], "user_id": u["id"], "persona_id": persona["id"],
            "voice": VOICE_MAP.get(persona.get("voice", "alloy"), "marin"), "instructions": instructions,
            "status": "created", "billed_minutes": 0, "credits": 0, "credits_per_min": cpm,
            "created_at": now_iso(), "started_at": None, "ended_at": None, "seconds": 0}
    await db.realtime_calls.insert_one(dict(call))
    return {"call_id": call["id"], "voice": call["voice"], "model": REALTIME_MODEL, "credits_per_min": cpm,
            "language": ((u.get("settings") or {}).get("conversation_language") or "id"),
            "persona": {"id": persona["id"], "name": persona["name"], "portrait": persona.get("portrait")}}


async def _own_call(call_id: str, u: dict) -> dict:
    call = await db.realtime_calls.find_one({"id": call_id, "user_id": u["id"]}, {"_id": 0})
    if not call:
        raise HTTPException(404, "Call not found")
    return call


@router.post("/realtime/calls/{call_id}/negotiate", response_class=PlainTextResponse)
async def negotiate(call_id: str, request: Request, u: dict = Depends(current_user)):
    call = await _own_call(call_id, u)
    if call["status"] == "ended":
        raise HTTPException(400, "Call already ended")
    sdp_offer = (await request.body()).decode()
    lang = ((u.get("settings") or {}).get("conversation_language") or "id")
    session = {
        "type": "realtime",
        "model": REALTIME_MODEL,
        "instructions": call["instructions"],
        "output_modalities": ["audio"],
        "audio": {
            "input": {
                "transcription": {"model": "gpt-4o-mini-transcribe", "language": lang},
                "turn_detection": {"type": "server_vad", "threshold": 0.5, "prefix_padding_ms": 300,
                                   "silence_duration_ms": 650, "create_response": True, "interrupt_response": True},
            },
            "output": {"voice": call["voice"]},
        },
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
