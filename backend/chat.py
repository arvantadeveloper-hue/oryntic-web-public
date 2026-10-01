import json
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from db import db, now_iso, new_id, clean
from auth import current_user, JWT_SECRET, JWT_ISSUER
from llm import llm_text, record_usage, text_credits, GPT_MODEL
import jwt as _jwt

router = APIRouter(prefix="/api", tags=["chat"])


class ConvIn(BaseModel):
    persona_id: Optional[str] = None
    title: Optional[str] = None


class MsgIn(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    attachments: list = []


class MemIn(BaseModel):
    persona_id: Optional[str] = None
    content: str = Field(min_length=1, max_length=1000)


# ---------- conversations ----------
@router.post("/conversations")
async def create_conv(x: ConvIn, u: dict = Depends(current_user)):
    cid = new_id()
    doc = {
        "id": cid, "user_id": u["id"], "persona_id": x.persona_id,
        "title": x.title or "New conversation", "created_at": now_iso(), "updated_at": now_iso(),
        "last_message": "",
    }
    await db.conversations.insert_one(doc)
    return clean(doc)


@router.get("/conversations")
async def list_conv(q: Optional[str] = None, u: dict = Depends(current_user)):
    query = {"user_id": u["id"]}
    if q:
        query["$or"] = [{"title": {"$regex": q, "$options": "i"}}, {"last_message": {"$regex": q, "$options": "i"}}]
    items = await db.conversations.find(query, {"_id": 0}).sort("updated_at", -1).to_list(200)
    return items


@router.get("/conversations/{cid}/messages")
async def get_messages(cid: str, u: dict = Depends(current_user)):
    conv = await db.conversations.find_one({"id": cid, "user_id": u["id"]}, {"_id": 0})
    if not conv:
        raise HTTPException(404, "Conversation not found")
    msgs = await db.messages.find({"conversation_id": cid}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    return {"conversation": conv, "messages": msgs}


@router.delete("/conversations/{cid}")
async def del_conv(cid: str, u: dict = Depends(current_user)):
    await db.conversations.delete_one({"id": cid, "user_id": u["id"]})
    await db.messages.delete_many({"conversation_id": cid})
    return {"ok": True}


async def _build_context(conv: dict, user: dict) -> str:
    parts = []
    persona = None
    if conv.get("persona_id"):
        persona = await db.personas.find_one({"id": conv["persona_id"]})
    if persona:
        prof = persona.get("profile", {})
        parts.append(f"You are '{persona['name']}', an AI persona. {prof.get('system_instructions','')}")
        pers = prof.get("personality", {})
        parts.append(f"Communication style: {pers.get('communication_style','')}. Formality: {pers.get('formality','')}. Attitude: {pers.get('attitude','')}.")
        parts.append("You are an AI and must not claim to have real human feelings or needs. Be warm but honest.")
        # memory
        mems = await db.memory_items.find({"user_id": user["id"], "persona_id": persona["id"], "enabled": True}).to_list(50)
        if mems:
            parts.append("Relevant saved memory about the user: " + "; ".join(m["content"] for m in mems))
    else:
        parts.append("You are Aivora, a helpful, concise AI personal assistant.")
    lang = user.get("settings", {}).get("conversation_language", "id")
    parts.append(f"Default conversation language: {lang} (follow the user's language if they switch).")
    return "\n".join(parts)


async def _history_text(cid: str) -> str:
    msgs = await db.messages.find({"conversation_id": cid}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    recent = msgs[-12:]
    lines = []
    for m in recent:
        role = "User" if m["role"] == "user" else "Assistant"
        lines.append(f"{role}: {m['content']}")
    return "\n".join(lines)


@router.post("/conversations/{cid}/send")
async def send_message(cid: str, x: MsgIn, u: dict = Depends(current_user)):
    conv = await db.conversations.find_one({"id": cid, "user_id": u["id"]})
    if not conv:
        raise HTTPException(404, "Conversation not found")

    user_msg = {
        "id": new_id(), "conversation_id": cid, "role": "user", "content": x.content,
        "attachments": x.attachments, "created_at": now_iso(),
    }
    await db.messages.insert_one(dict(user_msg))

    system = await _build_context(conv, u)
    history = await _history_text(cid)
    prompt = f"{history}\nUser: {x.content}\nAssistant:"

    async def stream():
        full = ""
        try:
            full = await llm_text(system, prompt, conv.get("model") or GPT_MODEL)
        except Exception:
            full = "Maaf, terjadi gangguan saat menghasilkan jawaban. Silakan coba lagi."
        # chunk-stream for UX
        words = full.split(" ")
        buf = ""
        for i, w in enumerate(words):
            buf = w if i == 0 else " " + w
            yield f"data: {json.dumps({'delta': buf})}\n\n"
            await asyncio.sleep(0.012)
        used = text_credits(prompt, full)
        bal = await record_usage(u["id"], "chat", used, {"conversation_id": cid})
        ai_msg = {
            "id": new_id(), "conversation_id": cid, "role": "assistant", "content": full,
            "credits": used, "created_at": now_iso(),
        }
        await db.messages.insert_one(dict(ai_msg))
        title = conv["title"]
        set_fields = {"updated_at": now_iso(), "last_message": full[:120]}
        if title == "New conversation":
            set_fields["title"] = x.content[:40]
        await db.conversations.update_one({"id": cid}, {"$set": set_fields})
        yield f"data: {json.dumps({'done': True, 'message_id': ai_msg['id'], 'credits_used': used, 'credits': bal})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/conversations/{cid}/messages/{mid}/regenerate")
async def regenerate(cid: str, mid: str, u: dict = Depends(current_user)):
    conv = await db.conversations.find_one({"id": cid, "user_id": u["id"]})
    if not conv:
        raise HTTPException(404, "Conversation not found")
    await db.messages.delete_one({"id": mid, "conversation_id": cid})
    # find last user message
    msgs = await db.messages.find({"conversation_id": cid}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    last_user = next((m for m in reversed(msgs) if m["role"] == "user"), None)
    if not last_user:
        raise HTTPException(400, "Nothing to regenerate")
    system = await _build_context(conv, u)
    history = "\n".join(f"{'User' if m['role']=='user' else 'Assistant'}: {m['content']}" for m in msgs[-12:])
    full = await llm_text(system, history + "\nAssistant:", conv.get("model") or GPT_MODEL)
    used = text_credits(history, full)
    bal = await record_usage(u["id"], "chat", used, {"conversation_id": cid, "regenerate": True})
    ai_msg = {"id": new_id(), "conversation_id": cid, "role": "assistant", "content": full,
              "credits": used, "created_at": now_iso()}
    await db.messages.insert_one(dict(ai_msg))
    return {"message": clean(ai_msg), "credits": bal}


# ---------- memory ----------
@router.get("/memory")
async def list_memory(persona_id: Optional[str] = None, u: dict = Depends(current_user)):
    query = {"user_id": u["id"]}
    if persona_id:
        query["persona_id"] = persona_id
    return await db.memory_items.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.post("/memory")
async def add_memory(x: MemIn, u: dict = Depends(current_user)):
    doc = {"id": new_id(), "user_id": u["id"], "persona_id": x.persona_id,
           "content": x.content, "enabled": True, "created_at": now_iso()}
    await db.memory_items.insert_one(dict(doc))
    return clean(doc)


@router.put("/memory/{mid}")
async def update_memory(mid: str, body: dict, u: dict = Depends(current_user)):
    fields = {}
    if "content" in body:
        fields["content"] = body["content"]
    if "enabled" in body:
        fields["enabled"] = bool(body["enabled"])
    await db.memory_items.update_one({"id": mid, "user_id": u["id"]}, {"$set": fields})
    return await db.memory_items.find_one({"id": mid}, {"_id": 0})


@router.delete("/memory/{mid}")
async def del_memory(mid: str, u: dict = Depends(current_user)):
    await db.memory_items.delete_one({"id": mid, "user_id": u["id"]})
    return {"ok": True}
