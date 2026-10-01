import json
import asyncio
import base64
import io
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from db import db, now_iso, new_id, clean
from auth import current_user, workspace_id
from llm import llm_text, record_usage, text_credits, describe_image, VISION_CREDITS
from realtime import notify

router = APIRouter(prefix="/api", tags=["chat"])


async def _process_attachments(attachments, user_id):
    """Return (context_text, light_meta_list). Extracts text from pdf/text, vision-describes images."""
    ctx, meta = [], []
    for a in (attachments or [])[:5]:
        atype = a.get("type", "text")
        name = a.get("name", "file")
        data = a.get("data", "")
        meta.append({"type": atype, "name": name})
        try:
            if atype == "image":
                desc = await describe_image(data.split(",")[-1])
                if desc:
                    await record_usage(user_id, "vision", VISION_CREDITS, {"name": name})
                    ctx.append(f"[Gambar '{name}']: {desc}")
            elif atype == "pdf":
                from pypdf import PdfReader
                raw = base64.b64decode(data.split(",")[-1])
                reader = PdfReader(io.BytesIO(raw))
                txt = "".join((p.extract_text() or "") + "\n" for p in reader.pages[:20])
                ctx.append(f"[PDF '{name}']:\n{txt[:6000]}")
            else:
                ctx.append(f"[Berkas '{name}']:\n{str(data)[:6000]}")
        except Exception:
            ctx.append(f"[Lampiran '{name}' tidak dapat diproses]")
    return ("\n\n".join(ctx), meta)


class ConvIn(BaseModel):
    persona_ids: list = []
    type: str = "private"  # private | group | meeting
    title: Optional[str] = None
    participant_ids: list = []  # other workspace humans invited to a meeting


def _can_access(conv: dict, u: dict) -> bool:
    if not conv:
        return False
    if conv.get("user_id") == u["id"]:
        return True
    if u["id"] in (conv.get("participants") or []):
        return True
    if u.get("role") == "admin" and conv.get("workspace_id") == workspace_id(u):
        return True
    return False


class MsgIn(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    attachments: list = []
    moderator: bool = True  # meeting: when False, skip the per-turn moderator summary (used by Video Room)


class MemIn(BaseModel):
    persona_id: Optional[str] = None
    content: str = Field(min_length=1, max_length=1000)


async def _get_personas(ids):
    out = []
    for pid in ids:
        p = await db.personas.find_one({"id": pid}, {"_id": 0})
        if p:
            out.append(p)
    return out


# ---------- conversations ----------
@router.post("/conversations")
async def create_conv(x: ConvIn, u: dict = Depends(current_user)):
    personas = await _get_personas(x.persona_ids)
    if not personas:
        raise HTTPException(400, "Pilih minimal satu persona untuk memulai percakapan")
    multi = len(personas) > 1 and x.type in ("group", "meeting")
    ctype = x.type if multi else "private"
    title = x.title
    if not title:
        if ctype == "meeting":
            title = "Meeting: " + ", ".join(p["name"] for p in personas)
        elif ctype == "group":
            title = "Grup: " + ", ".join(p["name"] for p in personas)
        else:
            title = f"Chat dengan {personas[0]['name']}"
    cid = new_id()
    # resolve invited human participants (must be in the same workspace)
    participants = [u["id"]]
    if x.participant_ids and ctype == "meeting":
        wid = workspace_id(u)
        valid = await db.users.find({"id": {"$in": x.participant_ids}, "owner_id": wid}, {"_id": 0, "id": 1}).to_list(50)
        for v in valid:
            if v["id"] not in participants:
                participants.append(v["id"])
    doc = {
        "id": cid, "user_id": u["id"], "workspace_id": workspace_id(u),
        "participants": participants,
        "type": ctype,
        "persona_ids": [p["id"] for p in personas],
        "persona_id": personas[0]["id"],
        "members": [{"id": p["id"], "name": p["name"], "portrait": p.get("portrait"), "voice": p.get("voice", "alloy")} for p in personas],
        "title": title, "created_at": now_iso(), "updated_at": now_iso(), "last_message": "",
    }
    await db.conversations.insert_one(dict(doc))
    return clean(doc)


class InviteIn(BaseModel):
    user_ids: list = []


@router.get("/conversations/{cid}/participants")
async def list_participants(cid: str, u: dict = Depends(current_user)):
    conv = await db.conversations.find_one({"id": cid}, {"_id": 0})
    if not _can_access(conv, u):
        raise HTTPException(404, "Conversation not found")
    ids = conv.get("participants") or [conv.get("user_id")]
    users = await db.users.find({"id": {"$in": ids}}, {"_id": 0, "password_hash": 0}).to_list(50)
    return [{"id": x["id"], "name": x.get("name"), "email": x.get("email"), "is_owner": x["id"] == conv.get("user_id")} for x in users]


@router.post("/conversations/{cid}/participants")
async def add_participants(cid: str, x: InviteIn, u: dict = Depends(current_user)):
    conv = await db.conversations.find_one({"id": cid})
    if not _can_access(conv, u):
        raise HTTPException(404, "Conversation not found")
    if conv.get("user_id") != u["id"] and u.get("role") != "admin":
        raise HTTPException(403, "Hanya pembuat atau admin yang bisa mengundang")
    if conv.get("type") == "private":
        raise HTTPException(400, "Undangan hanya untuk grup atau meeting")
    wid = workspace_id(u)
    valid = await db.users.find({"id": {"$in": x.user_ids}, "owner_id": wid}, {"_id": 0, "id": 1}).to_list(50)
    add = [v["id"] for v in valid]
    await db.conversations.update_one({"id": cid}, {"$addToSet": {"participants": {"$each": add}}, "$set": {"updated_at": now_iso()}})
    await notify(cid, {"type": "participants"})
    return {"ok": True, "added": add}


@router.get("/conversations")
async def list_conv(q: Optional[str] = None, u: dict = Depends(current_user)):
    query = {"$or": [{"user_id": u["id"]}, {"participants": u["id"]}]}
    if q:
        query["title"] = {"$regex": q, "$options": "i"}
    return await db.conversations.find(query, {"_id": 0}).sort("updated_at", -1).to_list(200)


@router.get("/conversations/{cid}/messages")
async def get_messages(cid: str, u: dict = Depends(current_user)):
    conv = await db.conversations.find_one({"id": cid}, {"_id": 0})
    if not _can_access(conv, u):
        raise HTTPException(404, "Conversation not found")
    msgs = await db.messages.find({"conversation_id": cid}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    return {"conversation": conv, "messages": msgs}


@router.delete("/conversations/{cid}")
async def del_conv(cid: str, u: dict = Depends(current_user)):
    conv = await db.conversations.find_one({"id": cid})
    if not conv:
        return {"ok": True}
    if conv.get("user_id") != u["id"] and u.get("role") != "admin":
        # a non-owner participant just leaves the conversation
        await db.conversations.update_one({"id": cid}, {"$pull": {"participants": u["id"]}})
        return {"ok": True, "left": True}
    await db.conversations.delete_one({"id": cid})
    await db.messages.delete_many({"conversation_id": cid})
    return {"ok": True}


LANG_NAMES = {"id": "Bahasa Indonesia", "en": "English", "es": "Spanish", "fr": "French",
              "de": "German", "pt": "Portuguese", "ar": "Arabic", "ja": "Japanese",
              "ko": "Korean", "zh": "Chinese", "hi": "Hindi", "ru": "Russian", "it": "Italian"}


def _lang_name(user) -> str:
    code = ((user.get("settings", {}) or {}).get("conversation_language") or "id").lower()
    return LANG_NAMES.get(code, LANG_NAMES.get(code.split("-")[0], "Bahasa Indonesia"))


async def _persona_system(persona, user, roster=None):
    prof = persona.get("profile", {})
    lang_name = _lang_name(user)
    parts = [f"CRITICAL: You MUST always write every reply in {lang_name}, no matter what language these instructions or the persona profile are written in. Never switch to another language unless the user themselves writes in a different language."]
    parts.append(f"You are '{persona['name']}', an AI persona. {prof.get('system_instructions','')}")
    pers = prof.get("personality", {})
    parts.append(f"Communication style: {pers.get('communication_style','')}. Formality: {pers.get('formality','')}. Attitude: {pers.get('attitude','')}.")
    parts.append("You are an AI and must not claim to have real human feelings or needs. Be warm but honest.")
    mems = await db.memory_items.find({"user_id": user["id"], "persona_id": persona["id"], "enabled": True}).to_list(50)
    if mems:
        parts.append("Saved memory about the user: " + "; ".join(m["content"] for m in mems))
    if roster:
        others = [n for n in roster if n != persona["name"]]
        if others:
            parts.append(f"You are in a group conversation with the user and other AI assistants: {', '.join(others)}. "
                         f"Respond only as {persona['name']}, keep it concise, build on what others said without repeating them, and do not speak for the others.")
    parts.append(f"Reminder: reply in {lang_name}.")
    return "\n".join(parts)


async def _history_text(cid: str, limit=14) -> str:
    msgs = await db.messages.find({"conversation_id": cid}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    lines = []
    for m in msgs[-limit:]:
        if m["role"] == "user":
            who = m.get("sender_name") or "User"
        else:
            who = m.get("persona_name") or "Assistant"
        lines.append(f"{who}: {m['content']}")
    return "\n".join(lines)


@router.post("/conversations/{cid}/send")
async def send_message(cid: str, x: MsgIn, u: dict = Depends(current_user)):
    conv = await db.conversations.find_one({"id": cid})
    if not _can_access(conv, u):
        raise HTTPException(404, "Conversation not found")
    personas = await _get_personas(conv.get("persona_ids", []))
    if not personas:
        raise HTTPException(400, "Percakapan ini tidak memiliki persona")

    attach_text, attach_meta = await _process_attachments(x.attachments, u["id"])
    user_msg = {"id": new_id(), "conversation_id": cid, "role": "user", "content": x.content,
                "attachments": attach_meta, "sender_user_id": u["id"], "sender_name": u.get("name") or "User",
                "created_at": now_iso()}
    await db.messages.insert_one(dict(user_msg))
    await notify(cid, {"type": "message", "role": "user", "sender_name": user_msg["sender_name"]})

    # @mention routing: if the user names specific personas, only they respond
    lower = x.content.lower()
    mentioned = [p for p in personas if ("@" + p["name"].lower().replace(" ", "")) in lower.replace(" ", "")
                 or ("@" + p["name"].lower()) in lower]
    responders = mentioned if mentioned else personas
    roster = [p["name"] for p in personas]
    ctype = conv.get("type", "private")

    async def stream():
        total = 0
        for persona in responders:
            meta = {"persona_id": persona["id"], "persona_name": persona["name"], "portrait": persona.get("portrait"), "voice": persona.get("voice", "alloy")}
            yield f"data: {json.dumps({**meta, 'start': True})}\n\n"
            system = await _persona_system(persona, u, roster if len(personas) > 1 else None)
            history = await _history_text(cid)
            prompt = history
            if attach_text:
                prompt += f"\n\n[Lampiran dari user]:\n{attach_text}"
            prompt += f"\n{persona['name']}:"
            try:
                full = await llm_text(system, prompt, persona.get("model"))
            except Exception:
                full = "Maaf, terjadi gangguan saat menghasilkan jawaban. Silakan coba lagi."
            words = full.split(" ")
            for i, w in enumerate(words):
                chunk = w if i == 0 else " " + w
                yield f"data: {json.dumps({**meta, 'delta': chunk})}\n\n"
                await asyncio.sleep(0.01)
            used = text_credits(prompt, full)
            total += used
            await record_usage(u["id"], "chat", used, {"conversation_id": cid, "persona_id": persona["id"]})
            ai_msg = {"id": new_id(), "conversation_id": cid, "role": "assistant", "content": full,
                      "persona_id": persona["id"], "persona_name": persona["name"],
                      "portrait": persona.get("portrait"), "credits": used, "created_at": now_iso()}
            await db.messages.insert_one(dict(ai_msg))
            yield f"data: {json.dumps({**meta, 'final': True, 'message_id': ai_msg['id'], 'content': full})}\n\n"
            await notify(cid, {"type": "message", "role": "assistant", "persona_id": persona["id"]})

        # meeting moderator summary
        if ctype == "meeting" and len(responders) > 1 and x.moderator:
            mod_meta = {"persona_id": "__moderator__", "persona_name": "Moderator", "portrait": None, "is_moderator": True}
            yield f"data: {json.dumps({**mod_meta, 'start': True})}\n\n"
            history = await _history_text(cid, limit=20)
            sys = (f"You are the meeting Moderator. You MUST write entirely in {_lang_name(u)}. Summarize the discussion so far into: key points, agreements, "
                   "disagreements, and clear action items. Be concise and neutral. Use markdown.")
            summary = await llm_text(sys, f"Topik: {x.content}\n\nDiskusi:\n{history}\n\nModerator summary:")
            words = summary.split(" ")
            for i, w in enumerate(words):
                yield f"data: {json.dumps({**mod_meta, 'delta': (w if i == 0 else ' ' + w)})}\n\n"
                await asyncio.sleep(0.008)
            used = text_credits(history, summary)
            total += used
            await record_usage(u["id"], "meeting_summary", used, {"conversation_id": cid})
            msg = {"id": new_id(), "conversation_id": cid, "role": "assistant", "content": summary,
                   "persona_id": "__moderator__", "persona_name": "Moderator", "is_moderator": True,
                   "portrait": None, "credits": used, "created_at": now_iso()}
            await db.messages.insert_one(dict(msg))
            await db.tasks.insert_one({
                "id": new_id(), "user_id": u["id"], "goal": f"Notulen meeting: {conv['title']}",
                "type": "meeting_notes", "status": "completed", "steps": [], "summary": "Ringkasan & action items meeting",
                "model": None, "final_output": summary, "credits_used": used, "video_url": None,
                "created_at": now_iso(), "updated_at": now_iso(),
            })
            yield f"data: {json.dumps({**mod_meta, 'final': True, 'message_id': msg['id'], 'content': summary})}\n\n"

        # video-room: occasional live Moderator facilitation (every 2nd user turn), no notulen task
        elif ctype == "meeting" and len(responders) > 1 and not x.moderator:
            user_turns = await db.messages.count_documents({"conversation_id": cid, "role": "user"})
            if user_turns % 2 == 0:
                mod_meta = {"persona_id": "__moderator__", "persona_name": "Moderator", "portrait": None, "is_moderator": True, "moderator_kind": "interject", "voice": "onyx"}
                yield f"data: {json.dumps({**mod_meta, 'start': True})}\n\n"
                history = await _history_text(cid, limit=12)
                sys = (f"You are the meeting Moderator facilitating a LIVE discussion. You MUST write entirely in {_lang_name(u)}. "
                       "In 1-2 short sentences only, gently steer the conversation: acknowledge a key point, ask one sharp "
                       "follow-up question, or invite a specific participant to respond by name. Warm, concise, natural. "
                       "Do NOT summarize everything.")
                inter = await llm_text(sys, f"Peserta: {', '.join(roster)}\n\nDiskusi terakhir:\n{history}\n\nModerator (singkat):")
                for i, w in enumerate(inter.split(" ")):
                    yield f"data: {json.dumps({**mod_meta, 'delta': (w if i == 0 else ' ' + w)})}\n\n"
                    await asyncio.sleep(0.008)
                used = text_credits(history, inter)
                total += used
                await record_usage(u["id"], "meeting_moderation", used, {"conversation_id": cid})
                imsg = {"id": new_id(), "conversation_id": cid, "role": "assistant", "content": inter,
                        "persona_id": "__moderator__", "persona_name": "Moderator", "is_moderator": True,
                        "portrait": None, "credits": used, "created_at": now_iso()}
                await db.messages.insert_one(dict(imsg))
                yield f"data: {json.dumps({**mod_meta, 'final': True, 'message_id': imsg['id'], 'content': inter})}\n\n"

        bal = (await db.users.find_one({"id": u["id"]}))["credits"]
        await db.conversations.update_one({"id": cid}, {"$set": {"updated_at": now_iso(), "last_message": x.content[:120]}})
        yield f"data: {json.dumps({'done': True, 'credits_used': total, 'credits': bal})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/conversations/{cid}/summary")
async def meeting_summary(cid: str, u: dict = Depends(current_user)):
    """Generate a closing Moderator summary, save it to the conversation and as a Workspace notulen."""
    conv = await db.conversations.find_one({"id": cid, "user_id": u["id"]})
    if not conv:
        raise HTTPException(404, "Conversation not found")
    if conv.get("type") == "private":
        raise HTTPException(400, "Notulen hanya untuk percakapan grup atau meeting")
    history = await _history_text(cid, limit=40)
    if not history.strip():
        raise HTTPException(400, "Belum ada diskusi untuk diringkas")
    sys = (f"You are the meeting Moderator. You MUST write entirely in {_lang_name(u)}. Summarize the whole discussion into: key points, agreements, "
           "disagreements, and clear action items. Be concise, warm and neutral. Use markdown.")
    summary = await llm_text(sys, f"Diskusi rapat:\n{history}\n\nRingkasan moderator:")
    used = text_credits(history, summary)
    await record_usage(u["id"], "meeting_summary", used, {"conversation_id": cid})
    msg = {"id": new_id(), "conversation_id": cid, "role": "assistant", "content": summary,
           "persona_id": "__moderator__", "persona_name": "Moderator", "is_moderator": True,
           "portrait": None, "credits": used, "created_at": now_iso()}
    await db.messages.insert_one(dict(msg))
    await db.tasks.insert_one({
        "id": new_id(), "user_id": u["id"], "goal": f"Notulen rapat: {conv['title']}",
        "type": "meeting_notes", "status": "completed", "steps": [], "summary": "Ringkasan & action items rapat (video call)",
        "model": None, "final_output": summary, "credits_used": used, "video_url": None,
        "created_at": now_iso(), "updated_at": now_iso(),
    })
    await db.conversations.update_one({"id": cid}, {"$set": {"updated_at": now_iso()}})
    return {"summary": summary, "message_id": msg["id"], "credits_used": used}


@router.post("/conversations/{cid}/messages/{mid}/regenerate")
async def regenerate(cid: str, mid: str, u: dict = Depends(current_user)):
    conv = await db.conversations.find_one({"id": cid, "user_id": u["id"]})
    if not conv:
        raise HTTPException(404, "Conversation not found")
    old = await db.messages.find_one({"id": mid, "conversation_id": cid}, {"_id": 0})
    if not old:
        raise HTTPException(404, "Message not found")
    persona = await db.personas.find_one({"id": old.get("persona_id")}, {"_id": 0})
    if not persona:
        persona = (await _get_personas(conv.get("persona_ids", [])))[0]
    await db.messages.delete_one({"id": mid, "conversation_id": cid})
    system = await _persona_system(persona, u)
    history = await _history_text(cid)
    full = await llm_text(system, f"{history}\n{persona['name']}:", persona.get("model"))
    used = text_credits(history, full)
    bal = await record_usage(u["id"], "chat", used, {"conversation_id": cid, "regenerate": True})
    ai_msg = {"id": new_id(), "conversation_id": cid, "role": "assistant", "content": full,
              "persona_id": persona["id"], "persona_name": persona["name"],
              "portrait": persona.get("portrait"), "credits": used, "created_at": now_iso()}
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
