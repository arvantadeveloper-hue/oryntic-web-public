import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import current_user, workspace_id
from chat import _persona_system, _save_ai_msg, _get_personas, _owner_settings
from db import db, now_iso, new_id, clean
from llm import llm_text, record_usage, text_credits
from tools import OFFER_TEXT, route_model

log = logging.getLogger("aivora")
router = APIRouter(prefix="/api", tags=["assignments"])
_running: set = set()


def _utc(iso: Optional[str]) -> Optional[str]:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def when_text(iso: Optional[str], tz: str) -> str:
    if not iso:
        return "sekarang juga"
    from zoneinfo import ZoneInfo
    try:
        d = datetime.fromisoformat(iso).astimezone(ZoneInfo(tz or "Asia/Jakarta"))
        return "pada " + d.strftime("%A, %d %b %Y pukul %H:%M").replace("Monday", "Senin").replace("Tuesday", "Selasa").replace("Wednesday", "Rabu").replace("Thursday", "Kamis").replace("Friday", "Jumat").replace("Saturday", "Sabtu").replace("Sunday", "Minggu")
    except Exception:
        return "sesuai jadwal"


def offer_text(plan: dict, u: dict) -> str:
    tz = (u.get("settings") or {}).get("timezone") or "Asia/Jakarta"
    return OFFER_TEXT.format(uname=u.get("name") or "", title=plan.get("title") or "tugas ini", when=when_text(plan.get("scheduled_at"), tz))


async def create_assigned_task(u: dict, persona: dict, conv: dict, plan: dict, source: str) -> dict:
    sched = _utc(plan.get("scheduled_at"))
    future = bool(sched) and sched > now_iso()
    task = {"id": new_id(), "user_id": u["id"], "workspace_id": workspace_id(u), "goal": plan.get("title") or (plan.get("brief") or "")[:80],
            "brief": plan.get("brief") or plan.get("title") or "", "type": "assigned", "status": "scheduled" if future else "queued", "scheduled_at": sched,
            "steps": [], "summary": f"Ditugaskan dari {source}", "final_output": "", "credits_used": 0, "persona_id": persona["id"], "persona_name": persona["name"],
            "source": source, "conversation_ids": [conv["id"]] if conv else [], "version": 1, "notified": False, "created_at": now_iso(), "updated_at": now_iso()}
    await db.tasks.insert_one(dict(task))
    if not future:
        asyncio.create_task(execute_assigned_task(task["id"]))
    return task


async def execute_assigned_task(tid: str):
    if tid in _running:
        return
    _running.add(tid)
    try:
        t = await db.tasks.find_one({"id": tid}, {"_id": 0})
        if not t or t.get("status") in ("completed", "running", "cancelled"):
            return
        await db.tasks.update_one({"id": tid}, {"$set": {"status": "running", "started_at": now_iso(), "updated_at": now_iso()}})
        u = await db.users.find_one({"id": t["user_id"]}, {"_id": 0}) or {}
        persona = await db.personas.find_one({"id": t.get("persona_id")}, {"_id": 0}) or {"name": "Asisten", "model": None}
        system = (await _persona_system(persona, u, None) if persona.get("id") else "You are a diligent assistant.") + \
            "\n\nYou are now EXECUTING a delegated task. Produce the COMPLETE deliverable in well-structured markdown (headings, lists, tables where useful). No preamble, no questions."
        prompt = f"Task: {t.get('goal')}\nDetails: {t.get('brief') or ''}"
        model_key, _ = await route_model(persona.get("model"), prompt, 0, await _owner_settings(u) if u else {})
        out = await llm_text(system, prompt, model_key)
        used = text_credits(prompt, out)
        await record_usage(t["user_id"], "assigned_task", used, {"task_id": tid})
        await db.tasks.update_one({"id": tid}, {"$set": {"status": "completed", "final_output": out, "credits_used": used, "model": model_key,
                                                         "completed_at": now_iso(), "updated_at": now_iso(), "summary": f"Dikerjakan oleh {persona.get('name')}"}})
        for cid in t.get("conversation_ids") or []:
            await _save_ai_msg(cid, persona, f"Tugas **{t.get('goal')}** sudah selesai ✅ dan tersimpan di Ruang Kerja — [buka hasilnya](/workspace/{tid}).\n\n"
                               f"Kalau mau, buat panggilan dari Ruang Kerja dan saya paparkan hasilnya, atau minta revisi langsung di sini.", 0, "text",
                               {"tool": "task_done", "task_id": tid})
    except Exception as e:
        log.error("assigned task %s failed: %s", tid, e)
        await db.tasks.update_one({"id": tid}, {"$set": {"status": "failed", "error": str(e)[:300], "updated_at": now_iso()}})
    finally:
        _running.discard(tid)


async def tasks_tick():
    """Called by the server scheduler loop: start scheduled tasks whose time has come (and re-queue stale ones)."""
    now = now_iso()
    async for t in db.tasks.find({"status": "scheduled", "scheduled_at": {"$lte": now}}, {"_id": 0, "id": 1}):
        await db.tasks.update_one({"id": t["id"]}, {"$set": {"status": "queued"}})
        asyncio.create_task(execute_assigned_task(t["id"]))
    await digest_tick()
    stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    async for t in db.tasks.find({"type": "assigned", "status": {"$in": ["queued", "running"]}, "updated_at": {"$lte": stale}}, {"_id": 0, "id": 1}):
        if t["id"] not in _running:
            await db.tasks.update_one({"id": t["id"]}, {"$set": {"status": "queued", "updated_at": now}})
            asyncio.create_task(execute_assigned_task(t["id"]))


async def accept_pending(conv: dict, u: dict, mode: str) -> dict:
    """mode: delegate (terima beres) | discuss (bahas satu per satu). Returns the assistant message."""
    plan = conv.get("pending_task")
    if not plan:
        raise HTTPException(400, "Tidak ada tawaran tugas yang menunggu")
    persona = (await _get_personas([plan.get("persona_id") or conv.get("persona_id")]) or [None])[0]
    if not persona:
        raise HTTPException(400, "Asisten tidak ditemukan")
    await db.conversations.update_one({"id": conv["id"]}, {"$set": {"pending_task": None}})
    tz = (u.get("settings") or {}).get("timezone") or "Asia/Jakarta"
    if mode == "delegate":
        task = await create_assigned_task(u, persona, conv, plan, "chat")
        text = (f"Beres! Tugas **{task['goal']}** sudah masuk ke Ruang Kerja dan akan saya kerjakan {when_text(task.get('scheduled_at'), tz)}. "
                f"Begitu selesai, saya kabari di sini — dan Anda bisa buat panggilan dari Ruang Kerja supaya saya paparkan hasilnya. [Lihat di Ruang Kerja](/workspace/{task['id']})")
        return await _save_ai_msg(conv["id"], persona, text, 0, "text", {"tool": "task_assigned", "task_id": task["id"]})
    system = await _persona_system(persona, u, None)
    out = await llm_text(system + "\n\nThe user chose to work through the task together step by step. Propose a short plan (3-6 steps) and ask which step to start with. Keep it brief.",
                         f"Task: {plan.get('title')}\n{plan.get('brief') or ''}")
    used = text_credits(plan.get("brief") or "", out)
    await record_usage(u["id"], "chat", used, {"conversation_id": conv["id"]})
    return await _save_ai_msg(conv["id"], persona, out, used, "text", {})


class AcceptIn(BaseModel):
    mode: str = Field(pattern="^(delegate|discuss)$")


@router.post("/conversations/{cid}/tasks/accept")
async def accept_task_offer(cid: str, x: AcceptIn, u: dict = Depends(current_user)):
    conv = await db.conversations.find_one({"id": cid, "workspace_id": workspace_id(u)}, {"_id": 0})
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return await accept_pending(conv, u, x.mode)


class AssignIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    brief: Optional[str] = Field(default=None, max_length=4000)
    scheduled_at: Optional[str] = None
    persona_id: Optional[str] = None


@router.post("/conversations/{cid}/tasks")
async def assign_task(cid: str, x: AssignIn, u: dict = Depends(current_user)):
    """Direct assignment (used by the Realtime `assign_task` voice tool and the meeting chat)."""
    conv = await db.conversations.find_one({"id": cid, "workspace_id": workspace_id(u)}, {"_id": 0})
    if not conv:
        raise HTTPException(404, "Conversation not found")
    pid = x.persona_id if x.persona_id in (conv.get("persona_ids") or []) else conv.get("persona_id") or (conv.get("persona_ids") or [None])[0]
    persona = (await _get_personas([pid]) or [None])[0]
    if not persona:
        raise HTTPException(400, "Asisten tidak ditemukan")
    task = await create_assigned_task(u, persona, conv, {"title": x.title, "brief": x.brief, "scheduled_at": x.scheduled_at}, "meeting" if conv.get("type") == "meeting" else "call")
    tz = (u.get("settings") or {}).get("timezone") or "Asia/Jakarta"
    await _save_ai_msg(cid, persona, f"📌 Tugas **{task['goal']}** dicatat ke Ruang Kerja, dikerjakan {when_text(task.get('scheduled_at'), tz)}. [Lihat](/workspace/{task['id']})", 0, "text", {"tool": "task_assigned", "task_id": task["id"]})
    return {"task_id": task["id"], "status": task["status"], "when": when_text(task.get("scheduled_at"), tz), "assistant": persona["name"]}


@router.get("/task-notifications")
async def task_notifications(u: dict = Depends(current_user)):
    rows = await db.tasks.find({"user_id": u["id"], "status": {"$in": ["completed", "failed"]}, "notified": False, "type": "assigned"},
                               {"_id": 0, "id": 1, "goal": 1, "status": 1, "persona_name": 1, "completed_at": 1}).to_list(20)
    return rows


@router.post("/task-notifications/ack")
async def ack_notifications(u: dict = Depends(current_user)):
    await db.tasks.update_many({"user_id": u["id"], "notified": False}, {"$set": {"notified": True}})
    return {"ok": True}


# ---------- calendar ----------
class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start_at: str
    end_at: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


@router.post("/events")
async def create_event(x: EventIn, u: dict = Depends(current_user)):
    start = _utc(x.start_at)
    if not start:
        raise HTTPException(400, "Waktu mulai tidak valid")
    doc = {"id": new_id(), "user_id": u["id"], "workspace_id": workspace_id(u), "title": x.title, "start_at": start, "end_at": _utc(x.end_at), "notes": x.notes or "", "created_at": now_iso()}
    await db.events.insert_one(dict(doc))
    return clean(doc)


@router.delete("/events/{eid}")
async def delete_event(eid: str, u: dict = Depends(current_user)):
    res = await db.events.delete_one({"id": eid, "user_id": u["id"]})
    if not res.deleted_count:
        raise HTTPException(404, "Event tidak ditemukan")
    return {"ok": True}


@router.get("/calendar")
async def calendar(start: str, end: str, u: dict = Depends(current_user)):
    """Everything with a time in [start, end): scheduled/finished tasks, reminders, meetings, manual events."""
    s, e = _utc(start), _utc(end)
    if not s or not e:
        raise HTTPException(400, "Rentang tanggal tidak valid")
    return await calendar_items(u, s, e)


async def calendar_items(u: dict, s: str, e: str) -> list:
    wid = workspace_id(u)
    items = []
    async for t in db.tasks.find({"workspace_id": wid, "$or": [{"scheduled_at": {"$gte": s, "$lt": e}}, {"completed_at": {"$gte": s, "$lt": e}}]},
                                 {"_id": 0, "id": 1, "goal": 1, "status": 1, "scheduled_at": 1, "completed_at": 1, "persona_name": 1}):
        items.append({"kind": "task", "id": t["id"], "title": t["goal"], "at": t.get("scheduled_at") if t.get("status") == "scheduled" else (t.get("completed_at") or t.get("scheduled_at")),
                      "status": t.get("status"), "who": t.get("persona_name"), "link": f"/workspace/{t['id']}"})
    async for r in db.reminders.find({"user_id": u["id"], "start_at": {"$gte": s, "$lt": e}}, {"_id": 0, "id": 1, "title": 1, "start_at": 1, "status": 1}):
        items.append({"kind": "reminder", "id": r["id"], "title": r["title"], "at": r["start_at"], "status": r.get("status"), "link": "/reminders"})
    async for c in db.conversations.find({"workspace_id": wid, "type": "meeting", "participants": u["id"], "updated_at": {"$gte": s, "$lt": e}},
                                         {"_id": 0, "id": 1, "title": 1, "updated_at": 1, "members": 1}):
        items.append({"kind": "meeting", "id": c["id"], "title": c["title"], "at": c["updated_at"], "who": ", ".join(m["name"] for m in c.get("members") or []), "link": f"/chat/{c['id']}"})
    async for ev in db.events.find({"workspace_id": wid, "start_at": {"$gte": s, "$lt": e}}, {"_id": 0}):
        items.append({"kind": "event", "id": ev["id"], "title": ev["title"], "at": ev["start_at"], "end_at": ev.get("end_at"), "notes": ev.get("notes"), "mine": ev["user_id"] == u["id"]})
    items.sort(key=lambda i: i.get("at") or "")
    return items


# ---------- daily digest ----------
DIGEST_WINDOW_H = 3


def _local_now(tz: str):
    from zoneinfo import ZoneInfo
    try:
        return datetime.now(ZoneInfo(tz or "Asia/Jakarta"))
    except Exception:
        return datetime.now(ZoneInfo("Asia/Jakarta"))


async def build_digest(u: dict, persona: dict) -> tuple:
    """(markdown for chat, plain spoken text for calls, credits)."""
    from zoneinfo import ZoneInfo
    tz = (u.get("settings") or {}).get("timezone") or "Asia/Jakarta"
    now = _local_now(tz)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    agenda = await calendar_items(u, day_start.astimezone(timezone.utc).isoformat(), day_end.astimezone(timezone.utc).isoformat())
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    done = await db.tasks.find({"workspace_id": workspace_id(u), "status": "completed", "completed_at": {"$gte": since}}, {"_id": 0, "goal": 1, "persona_name": 1}).to_list(20)
    running = await db.tasks.count_documents({"workspace_id": workspace_id(u), "status": {"$in": ["queued", "running", "scheduled"]}})

    def fmt(it):
        t = datetime.fromisoformat(it["at"]).astimezone(ZoneInfo(tz)).strftime("%H:%M") if it.get("at") else "-"
        return f"- {t} [{it['kind']}] {it['title']}" + (f" ({it.get('status')})" if it.get("status") else "")
    data = (f"Date: {now.strftime('%A, %d %B %Y')} ({tz}). User: {u.get('name')}.\n"
            f"TODAY'S AGENDA ({len(agenda)}):\n" + ("\n".join(fmt(i) for i in agenda) or "- (kosong)") +
            f"\n\nTASKS COMPLETED IN THE LAST 24H ({len(done)}):\n" + ("\n".join(f"- {d['goal']} (oleh {d.get('persona_name') or 'asisten'})" for d in done) or "- (tidak ada)") +
            f"\n\nTasks still in progress/scheduled: {running}.")
    system = await _persona_system(persona, u, None) + ("\n\nWrite the user's DAILY DIGEST as a warm, concise morning briefing in markdown: greeting with the user's name, "
                                                        "today's agenda in order (times), tasks completed since yesterday, what is still in progress, and ONE short encouraging closing line. "
                                                        "Use ONLY the data given; never invent items. Max ~180 words.")
    md = await llm_text(system, data)
    used = text_credits(data, md)
    await record_usage(u["id"], "daily_digest", used, {})
    import re as _re
    spoken = _re.sub(r"[#*_`>\[\]()]+", "", md)
    return md, spoken, used


async def send_digest(u: dict, force: bool = False) -> dict:
    from reminders import _private_conv, _store_opening
    cfg = (u.get("settings") or {}).get("daily_digest") or {}
    if not (cfg.get("enabled") or force):
        return {"sent": False, "reason": "disabled"}
    wid = workspace_id(u)
    persona = await db.personas.find_one({"id": cfg.get("persona_id"), "deleted": {"$ne": True}}, {"_id": 0}) if cfg.get("persona_id") else None
    persona = persona or await db.personas.find_one({"user_id": wid, "deleted": {"$ne": True}}, {"_id": 0}, sort=[("created_at", 1)])
    if not persona:
        return {"sent": False, "reason": "no persona"}
    md, spoken, used = await build_digest(u, persona)
    channel = cfg.get("channel") or "chat"
    out = {"sent": True, "channel": channel, "credits_used": used}
    if channel in ("chat", "both"):
        conv = await _private_conv(u, persona)
        await _store_opening(conv, persona, md, used)
        out["conversation_id"] = conv["id"]
    if channel in ("call", "both"):
        now = now_iso()
        rem = {"id": new_id(), "user_id": u["id"], "title": "Ringkasan harian", "description": spoken[:1500], "start_at": now, "remind_minutes": 0,
               "remind_at": now, "persona_id": persona["id"], "status": "ringing", "ringing_at": now, "message": "", "kind": "digest", "created_at": now}
        await db.reminders.insert_one(dict(rem))
        out["reminder_id"] = rem["id"]
    await db.users.update_one({"id": u["id"]}, {"$set": {"digest_last_date": _local_now((u.get("settings") or {}).get("timezone")).strftime("%Y-%m-%d"), "digest_last_at": now_iso()}})
    return out


async def digest_tick():
    async for u in db.users.find({"settings.daily_digest.enabled": True}, {"_id": 0, "password_hash": 0}):
        cfg = u["settings"]["daily_digest"]
        now = _local_now(u["settings"].get("timezone"))
        today = now.strftime("%Y-%m-%d")
        if u.get("digest_last_date") == today:
            continue
        try:
            hh, mm = (cfg.get("time") or "07:00").split(":")
            due = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        except Exception:
            continue
        if due <= now < due + timedelta(hours=DIGEST_WINDOW_H):
            try:
                await send_digest(u)
            except Exception as e:
                log.error("digest for %s failed: %s", u.get("email"), e)
                await db.users.update_one({"id": u["id"]}, {"$set": {"digest_last_date": today}})


@router.post("/digest/send-now")
async def digest_now(u: dict = Depends(current_user)):
    """Preview/manual trigger from the Calendar settings card."""
    return await send_digest(u, force=True)
