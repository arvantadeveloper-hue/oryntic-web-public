"""Persona characters: the platform-managed presets a user picks when creating a persona ("Karakter Persona").
The built-in default is assistant_persona.CORE_SECTIONS; any other character REPLACES that core prompt for the persona."""
import time
from typing import Optional
from fastapi import HTTPException
from pydantic import BaseModel, Field

from db import db, now_iso, new_id
from assistant_persona import CORE_SECTIONS

DEFAULT_ID = "default"
DEFAULT_CHARACTER = {"id": DEFAULT_ID, "name": "Asisten Oryntix (bawaan)", "description": "Asisten pribadi yang hangat, jujur, dan dapat diandalkan — gaya teman tepercaya yang membantu tanpa menggurui.",
                     "enabled": True, "sort": 0, "builtin": True}
_cache: dict = {"at": 0.0, "items": []}


class CharacterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=600)
    prompt: str = Field(min_length=20, max_length=20000)
    enabled: bool = True
    sort: int = Field(default=100, ge=0, le=10000)


def _public(c: dict) -> dict:
    return {k: c.get(k) for k in ("id", "name", "description", "enabled", "sort", "builtin")}


async def all_characters(fresh: bool = False) -> list:
    """Default first, then the admin-defined ones (cached 60 s; prompts included)."""
    if fresh or time.time() - _cache["at"] > 60:
        rows = await db.persona_characters.find({}, {"_id": 0}).sort([("sort", 1), ("name", 1)]).to_list(200)
        _cache.update(at=time.time(), items=[{**DEFAULT_CHARACTER, "prompt": CORE_SECTIONS}] + rows)
    return _cache["items"]


async def public_characters() -> list:
    return [_public(c) for c in await all_characters() if c.get("enabled")]


async def character_prompt(character_id: Optional[str]) -> str:
    """Core prompt for a persona: the chosen character's prompt, or the built-in sections when unset/unknown/disabled."""
    if not character_id or character_id == DEFAULT_ID:
        return CORE_SECTIONS
    c = next((x for x in await all_characters() if x["id"] == character_id and x.get("enabled")), None)
    return c["prompt"] if c else CORE_SECTIONS


async def character_summary(character_id: Optional[str]) -> Optional[dict]:
    return next((_public(x) for x in await all_characters() if x["id"] == (character_id or DEFAULT_ID)), None)


async def valid_character_id(character_id: Optional[str]) -> str:
    cid = character_id or DEFAULT_ID
    if cid != DEFAULT_ID and not any(x["id"] == cid and x.get("enabled") for x in await all_characters(fresh=True)):
        raise HTTPException(400, "Karakter persona tidak ditemukan atau dinonaktifkan")
    return cid


# ---- admin management (used by platform_api) ----
async def create_character(x: CharacterIn) -> dict:
    doc = {"id": new_id(), **x.model_dump(), "builtin": False, "created_at": now_iso(), "updated_at": now_iso()}
    await db.persona_characters.insert_one(dict(doc))
    _cache["at"] = 0.0
    return doc


async def update_character(cid: str, x: CharacterIn) -> dict:
    if cid == DEFAULT_ID:
        raise HTTPException(400, "Karakter bawaan tidak bisa diubah — buat karakter baru untuk menimpanya")
    r = await db.persona_characters.find_one_and_update({"id": cid}, {"$set": {**x.model_dump(), "updated_at": now_iso()}}, projection={"_id": 0}, return_document=True)
    if not r:
        raise HTTPException(404, "Karakter tidak ditemukan")
    _cache["at"] = 0.0
    return r


async def delete_character(cid: str) -> dict:
    if cid == DEFAULT_ID:
        raise HTTPException(400, "Karakter bawaan tidak bisa dihapus")
    r = await db.persona_characters.delete_one({"id": cid})
    if not r.deleted_count:
        raise HTTPException(404, "Karakter tidak ditemukan")
    n = await db.personas.count_documents({"character_id": cid, "deleted": {"$ne": True}})
    await db.personas.update_many({"character_id": cid}, {"$set": {"character_id": DEFAULT_ID}})  # those personas fall back to the built-in prompt
    _cache["at"] = 0.0
    return {"ok": True, "personas_reset": n}
