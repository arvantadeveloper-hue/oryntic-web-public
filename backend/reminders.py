from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import db, now_iso, new_id, clean
from auth import current_user, _lang_name
from llm import llm_text, record_usage, text_credits

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


class ReminderIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = ""
    start_at: str  # ISO datetime
    remind_minutes: int = 30
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


@router.post("")
async def create_reminder(x: ReminderIn, u: dict = Depends(current_user)):
    start = _parse(x.start_at)
    remind_at = start - timedelta(minutes=x.remind_minutes)
    rid = new_id()
    doc = {
        "id": rid, "user_id": u["id"], "title": x.title, "description": x.description or "",
        "start_at": start.isoformat(), "remind_minutes": x.remind_minutes,
        "remind_at": remind_at.isoformat(), "persona_id": x.persona_id,
        "status": "scheduled", "message": "", "created_at": now_iso(),
    }
    await db.reminders.insert_one(dict(doc))
    return clean(doc)


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
    for k in ("title", "description", "remind_minutes", "persona_id"):
        if k in body:
            fields[k] = body[k]
    if "start_at" in body:
        start = _parse(body["start_at"])
        fields["start_at"] = start.isoformat()
        mins = body.get("remind_minutes", r["remind_minutes"])
        fields["remind_at"] = (start - timedelta(minutes=mins)).isoformat()
        fields["status"] = "scheduled"
    await db.reminders.update_one({"id": rid}, {"$set": fields})
    return await db.reminders.find_one({"id": rid}, {"_id": 0})


@router.delete("/{rid}")
async def delete_reminder(rid: str, u: dict = Depends(current_user)):
    await db.reminders.delete_one({"id": rid, "user_id": u["id"]})
    return {"ok": True}


@router.post("/{rid}/respond")
async def respond(rid: str, x: RespondIn, u: dict = Depends(current_user)):
    r = await db.reminders.find_one({"id": rid, "user_id": u["id"]})
    if not r:
        raise HTTPException(404, "Reminder not found")
    if x.action == "decline":
        await db.reminders.update_one({"id": rid}, {"$set": {"status": "declined"}})
        return {"status": "declined"}
    # accept -> generate reminder message from real data only
    persona = await _reminder_persona(r, u)
    persona_name = persona["name"] if persona else "Asisten"
    pending = await db.tasks.count_documents({"user_id": u["id"], "status": {"$in": ["queued", "running"]}})
    sys = (
        f"You are {persona_name}, delivering a short, warm, friendly PROACTIVE VOICE reminder, as if speaking on a phone call. "
        f"You MUST speak in {_lang_name(u)}. Sound human, caring and natural (not robotic). Greet the user by name. "
        "Use ONLY the data given. Do not invent agenda items, flight status, or completed tasks. 2-3 short spoken sentences."
    )
    prompt = (
        f"User name: {u.get('name')}. Reminder title: {r['title']}. Details: {r['description']}. "
        f"Scheduled start: {r['start_at']}. The user currently has {pending} task(s) still in progress."
    )
    opening = (f"Judul pengingat: {r['title']}. Detail: {r.get('description') or '-'}. Jadwal mulai: {r['start_at']}. "
               f"Tugas yang masih berjalan: {pending}.")
    if x.realtime and persona:
        msg, used = None, 0
    else:
        msg = await llm_text(sys, prompt)
        used = text_credits(prompt, msg)
        await record_usage(u["id"], "reminder_call", used, {"reminder_id": rid})
    await db.reminders.update_one({"id": rid}, {"$set": {"status": "answered", "message": msg or ""}})

    result = {"status": "answered", "message": msg, "persona_name": persona_name, "opening": opening}
    # If a persona is attached, set up/continue a real voice call conversation
    if persona:
        conv = await db.conversations.find_one({"user_id": u["id"], "type": "private", "persona_id": persona["id"]}, {"_id": 0})
        if not conv:
            cid = new_id()
            conv = {
                "id": cid, "user_id": u["id"], "workspace_id": u.get("owner_id") or u["id"],
                "participants": [u["id"]], "type": "private",
                "persona_ids": [persona["id"]], "persona_id": persona["id"],
                "members": [{"id": persona["id"], "name": persona["name"], "portrait": persona.get("portrait"), "voice": persona.get("voice", "alloy")}],
                "title": f"Chat dengan {persona['name']}", "created_at": now_iso(), "updated_at": now_iso(), "last_message": "",
            }
            await db.conversations.insert_one(dict(conv))
        if msg:
            # store the spoken reminder as the assistant's opening message in the call
            await db.messages.insert_one({
                "id": new_id(), "conversation_id": conv["id"], "role": "assistant", "content": msg,
                "persona_id": persona["id"], "persona_name": persona["name"], "portrait": persona.get("portrait"),
                "credits": used, "created_at": now_iso(),
            })
            await db.conversations.update_one({"id": conv["id"]}, {"$set": {"updated_at": now_iso(), "last_message": msg[:120]}})
        result["persona"] = {"id": persona["id"], "name": persona["name"], "portrait": persona.get("portrait"), "voice": persona.get("voice", "alloy")}
        result["conversation"] = conv
    return result


# ---------- scheduler (called from server loop) ----------
async def scheduler_tick():
    now = datetime.now(timezone.utc)
    cursor = db.reminders.find({"status": "scheduled", "remind_at": {"$lte": now.isoformat()}})
    async for r in cursor:
        # skip reminders whose start is far in the past (>1 day) to avoid old spam
        try:
            start = _parse(r["start_at"])
        except Exception:
            start = now
        if start < now - timedelta(hours=6):
            await db.reminders.update_one({"id": r["id"]}, {"$set": {"status": "missed"}})
            continue
        await db.reminders.update_one({"id": r["id"]}, {"$set": {"status": "ringing", "ringing_at": now.isoformat()}})
