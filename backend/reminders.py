from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import db, now_iso, new_id, clean
from auth import current_user, _lang_name
from llm import llm_text, record_usage, text_credits
from realtime import notify_user

router = APIRouter(prefix="/api/reminders", tags=["reminders"])
MODES = ("call", "chat")
OFFSETS = (5, 10, 15, 30, 60, 120, 1440)


class ReminderIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = ""
    start_at: str  # ISO datetime
    remind_minutes: int = 30  # legacy single offset
    offsets: Optional[list[int]] = None  # e.g. [30, 60] → 30 min AND 1 h before
    mode: str = "call"  # call = assistant rings; chat = assistant sends a message
    persona_id: Optional[str] = None


async def _reminder_persona(r: dict, u: dict):
    """Persona attached to the reminder, else the workspace's first active persona (so the call always has a voice)."""
    wid = u.get("owner_id") or u["id"]
    p = None
    if r.get("persona_id"):
        p = await db.personas.find_one({"id": r["persona_id"], "deleted": {"$ne": True}}, {"_id": 0})
    if not p:
        p = await db.personas.find_one({"user_id": wid, "deleted": {"$ne": True}}, {"_id": 0}, sort=[("updated_at", -1)])
    return p


class RespondIn(BaseModel):
    action: str  # accept | decline
    realtime: bool = False  # client will open a Realtime voice call; skip pre-generated TTS message


def _parse(dt: str) -> datetime:
    d = datetime.fromisoformat(dt.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def _offsets(offsets, legacy: int) -> list:
    vals = sorted({int(o) for o in (offsets if offsets else [legacy]) if 0 < int(o) <= 7 * 1440})
    return vals or [30]


def build_alerts(start: datetime, offsets: list) -> list:
    return [{"minutes": m, "remind_at": (start - timedelta(minutes=m)).isoformat(), "status": "scheduled"} for m in offsets]


async def create_reminder_doc(uid: str, title: str, description: str, start: datetime, offsets: list, mode: str, persona_id: Optional[str], event_id: Optional[str] = None) -> dict:
    """Shared by the Reminders form, calendar events and the assistant's calendar tool."""
    offsets = _offsets(offsets, 30)
    mode = mode if mode in MODES else "call"
    doc = {
        "id": new_id(), "user_id": uid, "title": title, "description": description or "",
        "start_at": start.isoformat(), "remind_minutes": min(offsets), "offsets": offsets, "mode": mode,
        "remind_at": (start - timedelta(minutes=min(offsets))).isoformat(), "alerts": build_alerts(start, offsets),
        "persona_id": persona_id, "event_id": event_id,
        "status": "scheduled", "message": "", "created_at": now_iso(),
    }
    await db.reminders.insert_one(dict(doc))
    return clean(doc)


@router.post("")
async def create_reminder(x: ReminderIn, u: dict = Depends(current_user)):
    return await create_reminder_doc(u["id"], x.title, x.description or "", _parse(x.start_at), _offsets(x.offsets, x.remind_minutes), x.mode, x.persona_id)


@router.get("")
async def list_reminders(u: dict = Depends(current_user)):
    return await db.reminders.find({"user_id": u["id"]}, {"_id": 0}).sort("start_at", 1).to_list(500)


@router.get("/incoming")
async def incoming(u: dict = Depends(current_user)):
    items = await db.reminders.find({"user_id": u["id"], "status": "ringing"}, {"_id": 0}).sort("remind_at", 1).to_list(10)
    for it in items:
        p = await _reminder_persona(it, u)
        if p:
            it["persona"] = {"name": p["name"], "portrait": p.get("portrait")} if p else None
    return items


@router.put("/{rid}")
async def update_reminder(rid: str, body: dict, u: dict = Depends(current_user)):
    r = await db.reminders.find_one({"id": rid, "user_id": u["id"]})
    if not r:
        raise HTTPException(404, "Reminder not found")
    fields = {}
    for k in ("title", "description", "persona_id"):
        if k in body:
            fields[k] = body[k]
    if body.get("mode") in MODES:
        fields["mode"] = body["mode"]
    start = _parse(body["start_at"]) if "start_at" in body else _parse(r["start_at"])
    if "start_at" in body or "offsets" in body or "remind_minutes" in body:
        offsets = _offsets(body.get("offsets", r.get("offsets")), body.get("remind_minutes", r.get("remind_minutes", 30)))
        fields.update({"start_at": start.isoformat(), "offsets": offsets, "remind_minutes": min(offsets), "remind_at": (start - timedelta(minutes=min(offsets))).isoformat(),
                       "alerts": build_alerts(start, offsets), "status": "scheduled"})
    await db.reminders.update_one({"id": rid}, {"$set": fields})
    if r.get("event_id"):
        ev_fields = {k: v for k, v in fields.items() if k in ("title", "start_at")}
        if "description" in fields:
            ev_fields["notes"] = fields["description"]
        if "mode" in fields or "offsets" in fields or "persona_id" in fields:
            ev_fields["remind"] = {"mode": fields.get("mode", r.get("mode", "call")), "offsets": fields.get("offsets", r.get("offsets") or [r.get("remind_minutes", 30)]),
                                   "persona_id": fields.get("persona_id", r.get("persona_id"))}
        if ev_fields:
            await db.events.update_one({"id": r["event_id"]}, {"$set": ev_fields})
    return await db.reminders.find_one({"id": rid}, {"_id": 0})


@router.delete("/{rid}")
async def delete_reminder(rid: str, u: dict = Depends(current_user)):
    r = await db.reminders.find_one({"id": rid, "user_id": u["id"]}, {"_id": 0, "event_id": 1})
    await db.reminders.delete_one({"id": rid, "user_id": u["id"]})
    if r and r.get("event_id"):
        await db.events.delete_one({"id": r["event_id"], "user_id": u["id"]})
    return {"ok": True}


def _minutes_label(m: int) -> str:
    return f"{m // 1440} hari" if m >= 1440 and m % 1440 == 0 else (f"{m // 60} jam" if m >= 60 and m % 60 == 0 else f"{m} menit")


async def _reminder_message(r: dict, u: dict, persona_name: str, pending: int, minutes: Optional[int] = None, chat: bool = False):
    """LLM-spoken reminder (TTS / chat path). Returns (message, credits)."""
    channel = "a short, warm, friendly PROACTIVE chat message" if chat else "a short, warm, friendly PROACTIVE VOICE reminder, as if speaking on a phone call"
    sys = (
        f"You are {persona_name}, delivering {channel}. "
        f"You MUST write in {_lang_name(u)}. Sound human, caring and natural (not robotic). Greet the user by name. "
        "Use ONLY the data given. Do not invent agenda items, flight status, or completed tasks. 2-3 short sentences."
    )
    lead = f" This reminder fires {_minutes_label(minutes)} before the start." if minutes else ""
    prompt = (
        f"User name: {u.get('name')}. Reminder title: {r['title']}. Details: {r.get('description') or '-'}. "
        f"Scheduled start: {r['start_at']}.{lead} The user currently has {pending} task(s) still in progress."
    )
    msg = await llm_text(sys, prompt)
    used = text_credits(prompt, msg)
    await record_usage(u["id"], "reminder_call", used, {"reminder_id": r["id"]})
    return msg, used


async def _private_conv(u: dict, persona: dict) -> dict:
    """Find or create the 1:1 conversation used for the reminder call."""
    conv = await db.conversations.find_one({"user_id": u["id"], "type": "private", "persona_id": persona["id"]}, {"_id": 0})
    if conv:
        return conv
    conv = {
        "id": new_id(), "user_id": u["id"], "workspace_id": u.get("owner_id") or u["id"],
        "participants": [u["id"]], "type": "private",
        "persona_ids": [persona["id"]], "persona_id": persona["id"],
        "members": [{"id": persona["id"], "name": persona["name"], "portrait": persona.get("portrait"), "voice": persona.get("voice", "alloy")}],
        "title": f"Chat dengan {persona['name']}", "created_at": now_iso(), "updated_at": now_iso(), "last_message": "",
    }
    await db.conversations.insert_one(dict(conv))
    return conv


async def _store_opening(conv: dict, persona: dict, msg: str, used: int, extra: Optional[dict] = None):
    await db.messages.insert_one({
        "id": new_id(), "conversation_id": conv["id"], "role": "assistant", "content": msg,
        "persona_id": persona["id"], "persona_name": persona["name"], "portrait": persona.get("portrait"),
        "credits": used, "created_at": now_iso(), **(extra or {}),
    })
    await db.conversations.update_one({"id": conv["id"]}, {"$set": {"updated_at": now_iso(), "last_message": msg[:120]}})


@router.post("/{rid}/respond")
async def respond(rid: str, x: RespondIn, u: dict = Depends(current_user)):
    r = await db.reminders.find_one({"id": rid, "user_id": u["id"]})
    if not r:
        raise HTTPException(404, "Reminder not found")
    if x.action == "decline":
        await db.reminders.update_one({"id": rid}, {"$set": {"status": "declined"}})
        return {"status": "declined"}
    persona = await _reminder_persona(r, u)
    persona_name = persona["name"] if persona else "Asisten"
    pending = await db.tasks.count_documents({"user_id": u["id"], "status": {"$in": ["queued", "running"]}})
    opening = (f"Judul pengingat: {r['title']}. Detail: {r.get('description') or '-'}. Jadwal mulai: {r['start_at']}. "
               f"Tugas yang masih berjalan: {pending}.")
    msg, used = (None, 0) if (x.realtime and persona) else await _reminder_message(r, u, persona_name, pending, r.get("ringing_minutes"))
    await db.reminders.update_one({"id": rid}, {"$set": {"status": "answered", "message": msg or ""}})
    result = {"status": "answered", "message": msg, "persona_name": persona_name, "opening": opening}
    if persona:
        conv = await _private_conv(u, persona)
        if msg:
            await _store_opening(conv, persona, msg, used)
        result["persona"] = {"id": persona["id"], "name": persona["name"], "portrait": persona.get("portrait"), "voice": persona.get("voice", "alloy")}
        result["conversation"] = conv
    return result


# ---------- scheduler (called from server loop) ----------
async def _fire_chat(r: dict, u: dict, minutes: int):
    """Chat mode: the persona posts the reminder into the 1:1 chat + in-app/push notification."""
    persona = await _reminder_persona(r, u)
    if not persona:
        return
    pending = await db.tasks.count_documents({"user_id": u["id"], "status": {"$in": ["queued", "running"]}})
    try:
        msg, used = await _reminder_message(r, u, persona["name"], pending, minutes, chat=True)
    except Exception:
        msg, used = f"Halo {u.get('name') or ''}! Pengingat: {r['title']} dimulai {_minutes_label(minutes)} lagi.", 0
    conv = await _private_conv(u, persona)
    await _store_opening(conv, persona, msg, used, {"tool": "reminder", "reminder": {"id": r["id"], "title": r["title"], "start_at": r["start_at"], "minutes": minutes},
                                                    "cta": {"label": "Lihat pengingat", "href": "/reminders"}})
    await notify_user(u["id"], {"type": "message_new", "conversation_id": conv["id"]})
    await notify_user(u["id"], {"type": "notification"})
    from push import send_push
    await send_push(u["id"], f"Pengingat: {r.get('title') or 'Agenda'}", f"{persona['name']}: dimulai {_minutes_label(minutes)} lagi.", {"link": f"/chat/{conv['id']}", "tag": f"reminder-{r['id']}-{minutes}"}, kind="reminders")


async def scheduler_tick():
    now = datetime.now(timezone.utc)
    now_s = now.isoformat()
    q = {"$or": [{"alerts": {"$elemMatch": {"status": "scheduled", "remind_at": {"$lte": now_s}}}},
                 {"alerts": {"$exists": False}, "status": "scheduled", "remind_at": {"$lte": now_s}}]}
    async for r in db.reminders.find(q):
        try:
            start = _parse(r["start_at"])
        except Exception:
            start = now
        if start < now - timedelta(hours=6):  # stale → do not spam
            await db.reminders.update_one({"id": r["id"]}, {"$set": {"status": "missed", "alerts.$[a].status": "missed"}}, array_filters=[{"a.status": "scheduled"}])
            continue
        alerts = r.get("alerts") or [{"minutes": r.get("remind_minutes", 30), "remind_at": r.get("remind_at"), "status": "scheduled"}]
        due = [a for a in alerts if a["status"] == "scheduled" and a["remind_at"] <= now_s]
        if not due:
            continue
        minutes = min(a["minutes"] for a in due)
        for a in alerts:
            if a in due:
                a["status"] = "fired"
        user = await db.users.find_one({"id": r["user_id"]}, {"_id": 0})
        if not user:
            continue
        if r.get("mode") == "chat":
            await db.reminders.update_one({"id": r["id"]}, {"$set": {"alerts": alerts, "status": "sent", "last_fired_at": now_s}})
            await _fire_chat(r, user, minutes)
            continue
        await db.reminders.update_one({"id": r["id"]}, {"$set": {"alerts": alerts, "status": "ringing", "ringing_at": now_s, "ringing_minutes": minutes}})
        await notify_user(r["user_id"], {"type": "reminder_due", "reminder_id": r["id"], "title": r.get("title")})
        from push import send_push
        await send_push(r["user_id"], f"Pengingat: {r.get('title') or 'Agenda'}", f"Asisten Anda siap menelepon ({_minutes_label(minutes)} sebelum mulai).", {"link": "/reminders", "tag": f"reminder-{r['id']}"}, kind="reminders")
