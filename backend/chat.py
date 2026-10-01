import json
import asyncio
import base64
import io
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, EmailStr

from db import db, now_iso, new_id, clean
from auth import current_user, workspace_id, _lang_name, pw_hash, make_token, public_user
from llm import quota_message, llm_text, record_usage, text_credits, describe_image, VISION_CREDITS, quota_exceeded
from realtime import notify
from ratelimit import rate_limit
import secrets
from datetime import datetime, timezone, timedelta

INVITE_TTL_DAYS = 7
INVITE_DEFAULT_DAILY_LIMIT = 200
MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024

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
                if len(raw) > MAX_ATTACHMENT_BYTES:
                    raise ValueError("attachment too large")
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
    moderator: bool = True  # legacy flag (ignored): Moderator now only interjects when the discussion is stuck
    voice_mode: bool = False  # spoken conversation: short, warm, human-like replies (no markdown)
    interrupted: bool = False  # the user barged in while the assistant was speaking


class MemIn(BaseModel):
    persona_id: Optional[str] = None
    content: str = Field(min_length=1, max_length=1000)


async def _get_personas(ids, wid=None):
    out = []
    for pid in ids:
        q = {"id": pid}
        if wid:
            q["user_id"] = wid
        p = await db.personas.find_one(q, {"_id": 0})
        if p:
            out.append(p)
    return out


# ---------- conversations ----------
def _conv_title(ctype: str, personas: list) -> str:
    names = ", ".join(p["name"] for p in personas)
    if ctype == "meeting":
        return "Meeting: " + names
    if ctype == "group":
        return "Grup: " + names
    return f"Chat dengan {personas[0]['name']}"


async def _resolve_participants(u: dict, ids: list) -> list:
    """Creator + invited humans from the same workspace (deduplicated)."""
    participants = [u["id"]]
    if ids:
        valid = await db.users.find({"id": {"$in": ids}, "owner_id": workspace_id(u)}, {"_id": 0, "id": 1}).to_list(50)
        participants += [v["id"] for v in valid if v["id"] not in participants]
    return participants


@router.post("/conversations")
async def create_conv(x: ConvIn, u: dict = Depends(current_user)):
    personas = await _get_personas(x.persona_ids, workspace_id(u))
    if not personas:
        raise HTTPException(400, "Pilih minimal satu persona untuk memulai percakapan")
    multi = x.type in ("group", "meeting") and (len(personas) > 1 or x.type == "meeting")
    ctype = x.type if multi else "private"
    participants = await _resolve_participants(u, x.participant_ids if ctype == "meeting" else [])
    doc = {
        "id": new_id(), "user_id": u["id"], "workspace_id": workspace_id(u),
        "participants": participants,
        "type": ctype,
        "persona_ids": [p["id"] for p in personas],
        "persona_id": personas[0]["id"],
        "members": [{"id": p["id"], "name": p["name"], "portrait": p.get("portrait"), "voice": p.get("voice", "alloy")} for p in personas],
        "title": x.title or _conv_title(ctype, personas), "created_at": now_iso(), "updated_at": now_iso(), "last_message": "",
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


@router.post("/conversations/{cid}/invite-link")
async def create_invite_link(cid: str, u: dict = Depends(current_user)):
    conv = await db.conversations.find_one({"id": cid})
    if not _can_access(conv, u):
        raise HTTPException(404, "Conversation not found")
    if conv.get("user_id") != u["id"] and u.get("role") != "admin":
        raise HTTPException(403, "Hanya pembuat atau admin yang bisa membuat tautan")
    if conv.get("type") == "private":
        raise HTTPException(400, "Tautan hanya untuk grup atau meeting")
    token = conv.get("invite_token")
    exp = conv.get("invite_expires_at")
    if not token or not exp or exp < now_iso():
        token = secrets.token_urlsafe(24)
        exp = (datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)).isoformat()
        await db.conversations.update_one({"id": cid}, {"$set": {"invite_token": token, "invite_expires_at": exp}})
    return {"token": token, "path": f"/join/{token}", "expires_at": exp}


async def _conv_by_invite(token: str):
    conv = await db.conversations.find_one({"invite_token": token})
    if not conv or (conv.get("invite_expires_at") or "") < now_iso():
        raise HTTPException(404, "Undangan tidak valid atau sudah kedaluwarsa")
    return conv


@router.get("/invites/{token}")
async def invite_info(token: str):
    conv = await _conv_by_invite(token)
    owner = await db.users.find_one({"id": conv.get("workspace_id")}, {"_id": 0})
    return {
        "title": conv.get("title"),
        "type": conv.get("type"),
        "members": [{"name": m.get("name"), "portrait": m.get("portrait")} for m in conv.get("members", [])],
        "workspace": (owner or {}).get("name") or "Oryntix",
    }


@router.post("/invites/{token}/join")
async def invite_join(token: str, u: dict = Depends(current_user)):
    conv = await _conv_by_invite(token)
    if (u.get("owner_id") or u["id"]) != conv.get("workspace_id"):
        raise HTTPException(403, "Akun Anda bukan bagian dari workspace ini")
    await db.conversations.update_one({"id": conv["id"]}, {"$addToSet": {"participants": u["id"]}})
    await notify(conv["id"], {"type": "participants"})
    return {"conversation_id": conv["id"]}


class InviteRegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)


@router.post("/invites/{token}/register")
async def invite_register(token: str, x: InviteRegisterIn):
    conv = await _conv_by_invite(token)
    email = str(x.email).lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "Email sudah terdaftar. Silakan masuk lalu buka tautan lagi.")
    wid = conv.get("workspace_id")
    owner = await db.users.find_one({"id": wid}) or {}
    uid = new_id()
    doc = {
        "id": uid, "email": email, "password_hash": pw_hash(x.password),
        "name": x.name, "role": "user", "owner_id": wid, "onboarded": True, "verified": True, "credits": 0,
        "daily_credit_limit": INVITE_DEFAULT_DAILY_LIMIT, "joined_via_invite": True,
        "settings": {
            "app_language": owner.get("settings", {}).get("app_language", "id"),
            "conversation_language": owner.get("settings", {}).get("conversation_language", "id"),
            "timezone": owner.get("settings", {}).get("timezone", "Asia/Jakarta"), "theme": "light",
        },
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    await db.conversations.update_one({"id": conv["id"]}, {"$addToSet": {"participants": uid}})
    await notify(conv["id"], {"type": "participants"})
    return {"access_token": make_token(uid, "user"), "user": public_user(doc), "conversation_id": conv["id"]}


@router.get("/conversations")
async def list_conv(q: Optional[str] = None, u: dict = Depends(current_user)):
    query = {"$or": [{"user_id": u["id"]}, {"participants": u["id"]}]}
    if q:
        query["title"] = {"$regex": q, "$options": "i"}
    return await db.conversations.find(query, {"_id": 0, "invite_token": 0}).sort("updated_at", -1).to_list(200)


@router.get("/conversations/{cid}/messages")
async def get_messages(cid: str, u: dict = Depends(current_user)):
    conv = await db.conversations.find_one({"id": cid}, {"_id": 0, "invite_token": 0})
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


VOICE_STYLE = ("SPOKEN CONVERSATION MODE: your words will be read aloud by text-to-speech. Talk like a warm, friendly, "
               "attentive human in a live conversation: natural spoken sentences, 1-3 short sentences per turn (max ~60 words), "
               "no markdown, no bullet points, no headings, no emojis, no URLs. Use light conversational fillers sparingly "
               "(e.g. 'oke', 'hmm', 'baik') and acknowledge what the user said before answering. Ask one short follow-up question "
               "when it helps. If the user interrupted you, stop your previous thought gracefully and respond to what they just said.")


async def _persona_system(persona, user, roster=None, voice_mode=False):
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
    if voice_mode:
        parts.append(VOICE_STYLE)
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


async def _load_ai_conv(cid: str, u: dict):
    """Access + quota + persona checks shared by the AI endpoints. Returns (conv, personas)."""
    conv = await db.conversations.find_one({"id": cid})
    if not _can_access(conv, u):
        raise HTTPException(404, "Conversation not found")
    over = await quota_exceeded(u)
    if over:
        raise HTTPException(402, quota_message(over))
    personas = await _get_personas(conv.get("persona_ids", []))
    if not personas:
        raise HTTPException(400, "Percakapan ini tidak memiliki persona")
    return conv, personas


def _mentioned(content: str, personas: list) -> list:
    """@mention routing: personas explicitly named with @ in the message."""
    lower = content.lower()
    return [p for p in personas if ("@" + p["name"].lower().replace(" ", "")) in lower.replace(" ", "") or ("@" + p["name"].lower()) in lower]


async def _persona_reply(cid: str, u: dict, persona: dict, roster, prompt: str, voice_mode: bool, meta_extra: dict):
    """Stream one persona reply as SSE strings; the last yielded item is the int credits used."""
    meta = {"persona_id": persona["id"], "persona_name": persona["name"], "portrait": persona.get("portrait"), "voice": persona.get("voice", "alloy")}
    yield f"data: {json.dumps({**meta, 'start': True})}\n\n"
    system = await _persona_system(persona, u, roster, voice_mode=voice_mode)
    try:
        full = await llm_text(system, prompt, persona.get("model"))
    except Exception:
        full = "Maaf, terjadi gangguan saat menghasilkan jawaban. Silakan coba lagi."
    for i, w in enumerate(full.split(" ")):
        yield f"data: {json.dumps({**meta, 'delta': (w if i == 0 else ' ' + w)})}\n\n"
        await asyncio.sleep(0.01)
    used = text_credits(prompt, full)
    await record_usage(u["id"], "chat", used, {"conversation_id": cid, "persona_id": persona["id"], **meta_extra})
    ai_msg = {"id": new_id(), "conversation_id": cid, "role": "assistant", "content": full,
              "persona_id": persona["id"], "persona_name": persona["name"],
              "portrait": persona.get("portrait"), "credits": used, "created_at": now_iso()}
    await db.messages.insert_one(dict(ai_msg))
    yield f"data: {json.dumps({**meta, 'final': True, 'message_id': ai_msg['id'], 'content': full})}\n\n"
    await notify(cid, {"type": "message", "role": "assistant", "persona_id": persona["id"]})
    yield used


async def _finish_stream(cid: str, u: dict, total: int, last_message: str):
    bal = (await db.users.find_one({"id": u["id"]}))["credits"]
    await db.conversations.update_one({"id": cid}, {"$set": {"updated_at": now_iso(), "last_message": last_message[:120]}})
    return f"data: {json.dumps({'done': True, 'credits_used': total, 'credits': bal})}\n\ndata: [DONE]\n\n"


def _sse(gen):
    return StreamingResponse(gen, media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/conversations/{cid}/send")
async def send_message(cid: str, x: MsgIn, u: dict = Depends(current_user)):
    await rate_limit(u, "chat")
    conv, personas = await _load_ai_conv(cid, u)
    attach_text, attach_meta = await _process_attachments(x.attachments, u["id"])
    user_msg = {"id": new_id(), "conversation_id": cid, "role": "user", "content": x.content,
                "attachments": attach_meta, "sender_user_id": u["id"], "sender_name": u.get("name") or "User",
                "created_at": now_iso()}
    await db.messages.insert_one(dict(user_msg))
    await notify(cid, {"type": "message", "role": "user", "sender_name": user_msg["sender_name"]})

    responders = _mentioned(x.content, personas) or personas
    roster = [p["name"] for p in personas] if len(personas) > 1 else None
    extra = (f"\n\n[Lampiran dari user]:\n{attach_text}" if attach_text else "")
    if x.interrupted:
        extra += "\n[Catatan: user baru saja menyela saat asisten sedang berbicara. Tanggapi langsung apa yang user katakan.]"

    async def stream():
        total = 0
        for persona in responders:
            prompt = (await _history_text(cid)) + extra + f"\n{persona['name']}:"
            async for ev in _persona_reply(cid, u, persona, roster, prompt, x.voice_mode, {}):
                if isinstance(ev, int):
                    total += ev
                else:
                    yield ev
        # meeting: the Moderator only steps in when the discussion is stuck; notulen is on demand via /summary
        if conv.get("type") == "meeting" and len(responders) > 1:
            user_turns = await db.messages.count_documents({"conversation_id": cid, "role": "user"})
            if user_turns >= 2 and await _is_stuck(cid):
                async for ev in _moderator_interject(cid, u, roster, "stuck"):
                    if isinstance(ev, int):
                        total += ev
                    else:
                        yield ev
        yield await _finish_stream(cid, u, total, x.content)

    return _sse(stream())


MOD_META = {"persona_id": "__moderator__", "persona_name": "Moderator", "portrait": None, "is_moderator": True, "moderator_kind": "interject", "voice": "onyx"}


async def _is_stuck(cid: str) -> bool:
    """Cheap LLM check: are the assistants disagreeing without resolution or going in circles?"""
    history = await _history_text(cid, limit=10)
    sys = ("You are a silent meeting observer. Decide if the discussion is STUCK: participants clearly disagree without "
           "converging, keep repeating the same points, or talk past the user's question. Answer with exactly one word: YES or NO.")
    ans = ""
    try:
        ans = (await llm_text(sys, f"Diskusi:\n{history}\n\nStuck?")).strip().upper()
    except Exception:
        return False
    return ans.startswith("YES") or ans.startswith("YA")


async def _moderator_text(cid: str, u: dict, roster: list, reason: str):
    """Generate + persist a short Moderator interjection. Returns (text, credits_used); text is '' when nothing to say."""
    history = await _history_text(cid, limit=12)
    if reason == "silence":
        goal = ("The user has been quiet for a while. In 1-2 warm, short spoken sentences: briefly note what has been agreed so far "
                "(one clause), then gently ask the user whether they want to continue, decide, or wrap up.")
    else:
        goal = ("The discussion is stuck (disagreement or going in circles). In 1-2 short spoken sentences: name the core disagreement "
                "neutrally, then propose a concrete way forward or ask the user to decide. Do NOT summarize everything.")
    sys = (f"You are the meeting Moderator facilitating a LIVE spoken discussion. You MUST write entirely in {_lang_name(u)}. "
           f"{goal} Plain spoken text, no markdown, friendly and natural.")
    try:
        inter = await llm_text(sys, f"Peserta: {', '.join(roster)}\n\nDiskusi terakhir:\n{history}\n\nModerator (singkat):")
    except Exception:
        inter = ""
    if not inter.strip():
        return "", 0
    used = text_credits(history, inter)
    await record_usage(u["id"], "meeting_moderation", used, {"conversation_id": cid, "reason": reason})
    imsg = {"id": new_id(), "conversation_id": cid, "role": "assistant", "content": inter,
            "persona_id": "__moderator__", "persona_name": "Moderator", "is_moderator": True,
            "portrait": None, "credits": used, "created_at": now_iso()}
    await db.messages.insert_one(dict(imsg))
    await notify(cid, {"type": "message", "role": "assistant", "persona_id": "__moderator__"})
    return inter, used


async def _moderator_interject(cid: str, u: dict, roster: list, reason: str):
    """Yield SSE events for a short Moderator interjection; the final yielded item is the int credits used."""
    inter, used = await _moderator_text(cid, u, roster, reason)
    if not inter:
        yield 0
        return
    yield f"data: {json.dumps({**MOD_META, 'start': True})}\n\n"
    for i, w in enumerate(inter.split(" ")):
        yield f"data: {json.dumps({**MOD_META, 'delta': (w if i == 0 else ' ' + w)})}\n\n"
        await asyncio.sleep(0.008)
    yield f"data: {json.dumps({**MOD_META, 'final': True, 'content': inter})}\n\n"
    yield used


class ModerateIn(BaseModel):
    reason: str = Field(pattern="^(silence|stuck)$")


@router.post("/conversations/{cid}/moderate")
async def moderate(cid: str, x: ModerateIn, u: dict = Depends(current_user)):
    """Realtime meeting: Moderator speaks only when stuck (LLM check) or after long silence. Returns text (or null)."""
    await rate_limit(u, "chat")
    conv, personas = await _load_ai_conv(cid, u)
    if conv.get("type") == "private":
        raise HTTPException(400, "Moderator hanya untuk meeting")
    user_turns = await db.messages.count_documents({"conversation_id": cid, "role": "user"})
    needed = 2 if x.reason == "stuck" else 1
    if len(personas) < 2 or user_turns < needed or (x.reason == "stuck" and not await _is_stuck(cid)):
        return {"content": None, "voice": "onyx"}
    text, used = await _moderator_text(cid, u, [p["name"] for p in personas], x.reason)
    return {"content": text or None, "voice": "onyx", "credits_used": used}


@router.post("/conversations/{cid}/nudge")
async def nudge(cid: str, u: dict = Depends(current_user)):
    """Silence in a live meeting/call: Moderator (meeting) or the persona (private) gently checks in. Streams SSE."""
    await rate_limit(u, "chat")
    conv, personas = await _load_ai_conv(cid, u)
    history = await _history_text(cid, limit=12)
    if not history.strip():
        raise HTTPException(400, "Belum ada percakapan")
    roster = [p["name"] for p in personas]
    use_mod = conv.get("type") == "meeting" and len(personas) > 1
    persona = personas[0]
    prompt = (f"{history}\n[Catatan: user terdiam cukup lama. Sapa dengan hangat dalam satu kalimat pendek: tanyakan apakah masih ada, "
              f"atau tawarkan bantuan lanjutan. Jangan mengulang jawaban sebelumnya.]\n{persona['name']}:")

    async def stream():
        total = 0
        gen = _moderator_interject(cid, u, roster, "silence") if use_mod else \
            _persona_reply(cid, u, persona, roster if len(personas) > 1 else None, prompt, True, {"reason": "silence"})
        async for ev in gen:
            if isinstance(ev, int):
                total += ev
            else:
                yield ev
        yield f"data: {json.dumps({'done': True, 'credits_used': total})}\n\ndata: [DONE]\n\n"

    return _sse(stream())


@router.post("/conversations/{cid}/summary")
async def meeting_summary(cid: str, u: dict = Depends(current_user)):
    """Generate a closing Moderator summary, save it to the conversation and as a Workspace notulen."""
    conv = await db.conversations.find_one({"id": cid})
    if not _can_access(conv, u):
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
        "type": "meeting_notes", "status": "completed", "steps": [], "summary": "Ringkasan & action items meeting",
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
