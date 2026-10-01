from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import db, now_iso, new_id, clean
from auth import current_user
from llm import llm_text, record_usage, text_credits

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


class ReminderIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = ""
    start_at: str  # ISO datetime
    remind_minutes: int = 30
    persona_id: Optional[str] = None


class RespondIn(BaseModel):
    action: str  # accept | decline


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
        if it.get("persona_id"):
            p = await db.personas.find_one({"id": it["persona_id"]}, {"_id": 0})
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
    persona_name = "Asisten"
    if r.get("persona_id"):
        p = await db.personas.find_one({"id": r["persona_id"]})
        if p:
            persona_name = p["name"]
    pending = await db.tasks.count_documents({"user_id": u["id"], "status": {"$in": ["queued", "running"]}})
    sys = (
        f"You are {persona_name}, delivering a short, warm proactive voice reminder. Use ONLY the data given. "
        "Do not invent agenda items, flight status, or completed tasks. Keep it to 2-3 sentences, spoken style."
    )
    prompt = (
        f"User name: {u.get('name')}. Reminder title: {r['title']}. Details: {r['description']}. "
        f"Scheduled start: {r['start_at']}. The user currently has {pending} task(s) still in progress."
    )
    msg = await llm_text(sys, prompt)
    used = text_credits(prompt, msg)
    await record_usage(u["id"], "reminder_call", used, {"reminder_id": rid})
    await db.reminders.update_one({"id": rid}, {"$set": {"status": "answered", "message": msg}})
    return {"status": "answered", "message": msg, "persona_name": persona_name}


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
