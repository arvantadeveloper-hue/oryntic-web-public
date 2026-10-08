"""Oryntix built-in Customer Support Agent — platform-admin configuration (shares config.support_agent with the main backend)."""
import os
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import db, now_iso
from auth import require_platform_admin, require_platform_staff
from support_knowledge import DEFAULT_SYSTEM_PROMPT, DEFAULT_KNOWLEDGE

router = APIRouter(prefix="/api/admin", tags=["support-agent"])
LA_BASE = "https://api.liveavatar.com/v1"

DEFAULT_CONFIG = {
    "enabled": True, "name": "Oryntix", "summary": "Customer Support Agent", "portrait": "/brand/oryntix-support.jpg",
    "model": "gpt-luna", "voice_model": "gpt-realtime-2.1-mini", "voice": "marin",
    "system_prompt": DEFAULT_SYSTEM_PROMPT, "knowledge": DEFAULT_KNOWLEDGE,
    "video_enabled": True, "avatar_id": "5341767a-21fe-43d7-a5b5-9fd6bff6d32e", "avatar_name": "Oryntix (custom)", "avatar_preview": "/brand/oryntix-support.jpg", "sandbox": True,
    "video_credits_per_sec": 2, "video_max_minutes": 20, "video_warn_minutes": 2,
}


class SupportConfigIn(BaseModel):
    enabled: bool = True
    name: str = Field(default="Oryntix", min_length=1, max_length=40)
    summary: str = Field(default="Customer Support Agent", max_length=120)
    portrait: str = Field(default="/brand/oryntix-support.jpg", max_length=500)
    model: str = Field(default="gpt-luna", pattern="^[a-z0-9.-]+$")
    voice_model: str = Field(default="gpt-realtime-2.1-mini", pattern="^[a-z0-9.-]+$")
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


async def get_config() -> dict:
    doc = await db.config.find_one({"id": "support_agent"}, {"_id": 0, "id": 0}) or {}
    return {**DEFAULT_CONFIG, **doc}


@router.get("/support-agent")
async def admin_get(_: dict = Depends(require_platform_staff)):
    return {**(await get_config()), "liveavatar_key_set": bool(os.environ.get("LIVEAVATAR_API_KEY", "").strip())}


@router.put("/support-agent")
async def admin_set(x: SupportConfigIn, _: dict = Depends(require_platform_admin)):
    await db.config.update_one({"id": "support_agent"}, {"$set": {**x.model_dump(), "updated_at": now_iso()}}, upsert=True)
    return await get_config()


@router.get("/support-agent/avatars")
async def admin_avatars(page: int = 1, page_size: int = 24, mine: bool = False, _: dict = Depends(require_platform_staff)):
    key = os.environ.get("LIVEAVATAR_API_KEY", "").strip()
    if not key:
        raise HTTPException(503, "LIVEAVATAR_API_KEY belum diatur di backend admin")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{LA_BASE}/avatars" if mine else f"{LA_BASE}/avatars/public", params={"page": page, "page_size": min(page_size, 100)}, headers={"X-API-KEY": key})
    if r.status_code >= 300:
        raise HTTPException(503, "Gagal memuat daftar avatar LiveAvatar")
    d = (r.json().get("data") or {})
    return {"count": d.get("count", 0), "has_more": bool(d.get("next")),
            "items": [{"id": a["id"], "name": a["name"], "preview": a.get("preview_url"), "status": a.get("status"), "is_1080p": a.get("is_1080p")} for a in d.get("results", [])]}
