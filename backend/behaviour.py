"""Realtime conversation behaviour (turn-taking) — platform-wide, editable from the back-office; stored in config.realtime_behaviour."""
from typing import Optional
from pydantic import BaseModel, Field
from db import db, now_iso

DEFAULT_BEHAVIOUR = {"turn_detection": "semantic_vad", "eagerness": "low", "interrupt_response": False, "create_response": True,
                     "threshold": 0.5, "prefix_padding_ms": 300, "silence_duration_ms": 500,
                     "barge_confirm_ms": 1300, "backchannel_resume": True, "backchannel_window_ms": 8000}
_cache: dict = {}


class BehaviourIn(BaseModel):
    turn_detection: str = Field(pattern="^(semantic_vad|server_vad)$")
    eagerness: str = Field(pattern="^(low|medium|high|auto)$")
    interrupt_response: bool = False
    create_response: bool = True
    threshold: float = Field(default=0.5, ge=0, le=1)
    prefix_padding_ms: int = Field(default=300, ge=0, le=2000)
    silence_duration_ms: int = Field(default=500, ge=100, le=5000)
    barge_confirm_ms: int = Field(default=1300, ge=200, le=5000)
    backchannel_resume: bool = True
    backchannel_window_ms: int = Field(default=8000, ge=1000, le=30000)
    note: Optional[str] = Field(default=None, max_length=300)


async def get_behaviour() -> dict:
    if not _cache:
        doc = await db.config.find_one({"id": "realtime_behaviour"}, {"_id": 0, "id": 0}) or {}
        _cache.update({**DEFAULT_BEHAVIOUR, **doc})
    return dict(_cache)


async def set_behaviour(doc: dict) -> dict:
    await db.config.update_one({"id": "realtime_behaviour"}, {"$set": {**doc, "updated_at": now_iso()}}, upsert=True)
    _cache.clear()
    return await get_behaviour()


def turn_detection(b: dict, multi: bool) -> dict:
    """OpenAI Realtime turn_detection block from the behaviour config (panelists in a meeting pass None instead)."""
    base = {"create_response": bool(b.get("create_response", True)) and not multi, "interrupt_response": bool(b.get("interrupt_response", False))}
    if b.get("turn_detection") == "server_vad":
        return {"type": "server_vad", "threshold": b["threshold"], "prefix_padding_ms": b["prefix_padding_ms"], "silence_duration_ms": b["silence_duration_ms"], **base}
    return {"type": "semantic_vad", "eagerness": b.get("eagerness", "low"), **base}
