import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import current_user, workspace_id, lang_rule, _lang_name
from chat import _persona_system, _save_ai_msg, _get_personas, _can_access
from db import db, now_iso, new_id, clean
from llm import llm_text, record_usage, text_credits
from tools import OFFER_TEXT

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
            "\n\nYou are now EXECUTING a delegated task. Produce the COMPLETE deliverable in well-structured markdown (headings, lists, tables where useful). No preamble, no questions.\n\n" + lang_rule(u)
        prompt = f"Task: {t.get('goal')}\nDetails: {t.get('brief') or ''}\n\n(Reminder: {lang_rule(u)})"
        model_key = t.get("model") or persona.get("model")  # never switch models silently: only a model the user confirmed (task.model) or the assistant's own
        out = await llm_text(system, prompt, model_key)
        used = text_credits(prompt, out)
        await record_usage(t["user_id"], "assigned_task", used, {"task_id": tid})
        await db.tasks.update_one({"id": tid}, {"$set": {"status": "completed", "final_output": out, "credits_used": used, "model": model_key,
                                                         "completed_at": now_iso(), "updated_at": now_iso(), "summary": f"Dikerjakan oleh {persona.get('name')}"}})
        if t.get("parent_id"):
            await _maybe_assemble(t["parent_id"])
        from realtime import notify_user
        from push import send_push
        await notify_user(t["user_id"], {"type": "task_update", "task_id": tid, "status": "completed", "goal": t.get("goal")})
        await send_push(t["user_id"], f"Tugas selesai: {(t.get('goal') or '')[:60]}", f"{persona.get('name')} sudah menyelesaikan tugas ini di Ruang Kerja.", {"link": f"/workspace/{tid}", "tag": f"task-{tid}"}, kind="tasks")
        for cid in t.get("conversation_ids") or []:
            await _save_ai_msg(cid, persona, f"Tugas **{t.get('goal')}** sudah selesai ✅ dan tersimpan di Ruang Kerja — [buka hasilnya](/workspace/{tid}).\n\n"
                               f"Kalau mau, buat panggilan dari Ruang Kerja dan saya paparkan hasilnya, atau minta revisi langsung di sini.", 0, "text",
                               {"tool": "task_done", "task_id": tid})
    except Exception as e:
        log.error("assigned task %s failed: %s", tid, e)
        await db.tasks.update_one({"id": tid}, {"$set": {"status": "failed", "error": str(e)[:300], "updated_at": now_iso()}})
        t = await db.tasks.find_one({"id": tid}, {"_id": 0, "parent_id": 1}) or {}
        if t.get("parent_id"):
            await _maybe_assemble(t["parent_id"])
    finally:
        _running.discard(tid)


async def tasks_tick():
    """Called by the server scheduler loop: start scheduled tasks whose time has come (and re-queue stale ones)."""
    now = now_iso()
    async for t in db.tasks.find({"status": "scheduled", "scheduled_at": {"$lte": now}}, {"_id": 0, "id": 1, "team": 1}):
        if t.get("team"):
            await db.tasks.update_one({"id": t["id"]}, {"$set": {"status": "running", "updated_at": now}})
            continue  # children are scheduled individually
        await db.tasks.update_one({"id": t["id"]}, {"$set": {"status": "queued"}})
        asyncio.create_task(execute_assigned_task(t["id"]))
    await digest_tick()
    stale = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    async for t in db.tasks.find({"type": "assigned", "team": {"$ne": True}, "status": {"$in": ["queued", "running"]}, "updated_at": {"$lte": stale}}, {"_id": 0, "id": 1}):
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
    if mode == "team":
        task = await create_team_task(u, persona, conv, plan, "chat")
        text = (f"Siap, tugas **{task['goal']}** saya bagi ke tim dan masuk Ruang Kerja. {team_summary(task)} "
                f"Dikerjakan {when_text(task.get('scheduled_at'), tz)}; setelah semua bagian selesai saya rangkai jadi satu dan kabari di sini. [Lihat di Ruang Kerja](/workspace/{task['id']})")
        return await _save_ai_msg(conv["id"], persona, text, 0, "text", {"tool": "task_assigned", "task_id": task["id"]})
    if mode == "delegate":
        task = await create_assigned_task(u, persona, conv, plan, "chat")
        text = (f"Beres! Tugas **{task['goal']}** sudah masuk ke Ruang Kerja dan akan saya kerjakan {when_text(task.get('scheduled_at'), tz)}. "
                f"Begitu selesai, saya kabari di sini — dan Anda bisa buat panggilan dari Ruang Kerja supaya saya paparkan hasilnya. [Lihat di Ruang Kerja](/workspace/{task['id']})")
        return await _save_ai_msg(conv["id"], persona, text, 0, "text", {"tool": "task_assigned", "task_id": task["id"]})
    system = await _persona_system(persona, u, None)
    out = await llm_text(system + "\n\nThe user chose to work through the task together step by step. Propose a short plan (3-6 steps) and ask which step to start with. Keep it brief.\n\n" + lang_rule(u),
                         f"Task: {plan.get('title')}\n{plan.get('brief') or ''}")
    used = text_credits(plan.get("brief") or "", out)
    await record_usage(u["id"], "chat", used, {"conversation_id": conv["id"]})
    return await _save_ai_msg(conv["id"], persona, out, used, "text", {})


class AcceptIn(BaseModel):
    mode: str = Field(pattern="^(delegate|discuss|team)$")


@router.post("/conversations/{cid}/tasks/accept")
async def accept_task_offer(cid: str, x: AcceptIn, u: dict = Depends(current_user)):
    conv = await db.conversations.find_one({"id": cid}, {"_id": 0})
    if not conv or not _can_access(conv, u):
        raise HTTPException(404, "Conversation not found")
    return await accept_pending(conv, u, x.mode)


class AssignIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    brief: Optional[str] = Field(default=None, max_length=4000)
    scheduled_at: Optional[str] = None
    persona_id: Optional[str] = None
    team: bool = False
    assignments: Optional[list] = Field(default=None, max_length=10)  # [{assistant, part}] explicit "bagian X minta Nova"
    model: Optional[str] = Field(default=None, pattern="^[a-z0-9_-]+$")  # model the user confirmed for this task; omitted = the assistant's own model


async def _target_persona(conv: dict, requested: Optional[str]) -> dict:
    ids = conv.get("persona_ids") or []
    pid = requested if requested in ids else conv.get("persona_id") or (ids or [None])[0]
    persona = (await _get_personas([pid]) or [None])[0]
    if not persona:
        raise HTTPException(400, "Asisten tidak ditemukan")
    return persona


async def _assignable_conv(cid: str, u: dict) -> dict:
    conv = await db.conversations.find_one({"id": cid}, {"_id": 0})
    if not conv or not _can_access(conv, u):
        raise HTTPException(404, "Conversation not found")
    return conv


async def _create_from_assign(u: dict, persona: dict, conv: dict, x: AssignIn) -> dict:
    """Solo or team task from the assignment payload; the user-confirmed model is pinned on solo tasks."""
    assignments = [a for a in (x.assignments or []) if isinstance(a, dict) and a.get("assistant")]
    plan = {"title": x.title, "brief": x.brief, "scheduled_at": x.scheduled_at, "assignments": assignments}
    src = "meeting" if conv.get("type") == "meeting" else "call"
    create = create_team_task if (x.team or assignments) else create_assigned_task
    task = await create(u, persona, conv, plan, src)
    if x.model and x.model != "__own__" and not task.get("team"):
        await db.tasks.update_one({"id": task["id"]}, {"$set": {"model": x.model}})
        task["model"] = x.model
    return task


async def _announce_task(cid: str, persona: dict, task: dict, when: str) -> None:
    detail = f" {team_summary(task)}" if task.get("team") else ""
    await _save_ai_msg(cid, persona, f"📌 Tugas **{task['goal']}** dicatat ke Ruang Kerja, dikerjakan {when}.{detail} [Lihat](/workspace/{task['id']})", 0, "text",
                       {"tool": "task_assigned", "task_id": task["id"]})


@router.post("/conversations/{cid}/tasks")
async def assign_task(cid: str, x: AssignIn, u: dict = Depends(current_user)):
    """Direct assignment (used by the Realtime `assign_task` voice tool and the meeting chat)."""
    conv = await _assignable_conv(cid, u)
    persona = await _target_persona(conv, x.persona_id)
    task = await _create_from_assign(u, persona, conv, x)
    when = when_text(task.get("scheduled_at"), (u.get("settings") or {}).get("timezone") or "Asia/Jakarta")
    await _announce_task(cid, persona, task, when)
    return {"task_id": task["id"], "status": task["status"], "when": when, "assistant": persona["name"],
            "subtasks": [f"{s['persona_name']}: {s['title']}" for s in task.get("subtasks") or []], "unmatched_assistants": task.get("unmatched") or []}


@router.get("/task-notifications")
async def task_notifications(u: dict = Depends(current_user)):
    rows = await db.tasks.find({"user_id": u["id"], "status": {"$in": ["completed", "failed"]}, "notified": False, "type": "assigned"},
                               {"_id": 0, "id": 1, "goal": 1, "status": 1, "persona_name": 1, "completed_at": 1}).to_list(20)
    return rows


@router.post("/task-notifications/ack")
async def ack_notifications(u: dict = Depends(current_user)):
    await db.tasks.update_many({"user_id": u["id"], "notified": False, "type": "assigned"}, {"$set": {"notified": True}})
    return {"ok": True}


# ---------- calendar ----------
class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start_at: str
    end_at: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=2000)
    remind_mode: Optional[str] = None  # call | chat → creates a linked reminder
    remind_offsets: list[int] = Field(default_factory=list)  # minutes before start, e.g. [30, 60]
    persona_id: Optional[str] = None
    repeat: str = "none"  # none | daily | weekly | monthly (applies to the linked reminder; the event shows its next occurrence)
    conversation_id: Optional[str] = None  # when created by the assistant (chat/voice tool): post a confirmation card there


async def create_event_doc(u: dict, x: EventIn) -> dict:
    from reminders import create_reminder_doc, _parse
    start = _utc(x.start_at)
    if not start:
        raise HTTPException(400, "Waktu mulai tidak valid")
    eid = new_id()
    doc = {"id": eid, "user_id": u["id"], "workspace_id": workspace_id(u), "title": x.title, "start_at": start, "end_at": _utc(x.end_at), "notes": x.notes or "",
           "remind": None, "reminder_id": None, "created_at": now_iso()}
    if x.remind_mode in ("call", "chat") and x.remind_offsets:
        rem = await create_reminder_doc(u["id"], x.title, x.notes or "", _parse(start), x.remind_offsets, x.remind_mode, x.persona_id, event_id=eid, repeat=x.repeat)
        doc["remind"] = {"mode": rem["mode"], "offsets": rem["offsets"], "persona_id": x.persona_id, "repeat": rem["repeat"]}
        doc["start_at"] = rem["start_at"]
        doc["reminder_id"] = rem["id"]
    await db.events.insert_one(dict(doc))
    return clean(doc)


@router.post("/events")
async def create_event(x: EventIn, u: dict = Depends(current_user)):
    ev = await create_event_doc(u, x)
    if x.conversation_id:
        conv = await db.conversations.find_one({"id": x.conversation_id, "participants": u["id"]}, {"_id": 0, "persona_id": 1, "persona_ids": 1})
        pid = conv and ((conv.get("persona_ids") or [conv.get("persona_id")])[0])
        persona = pid and await db.personas.find_one({"id": pid}, {"_id": 0})
        if persona:
            from chat import _save_ai_msg, notify
            await _save_ai_msg(x.conversation_id, persona, event_markdown(ev), 0, "meeting_chat", {"tool": "calendar_event", "event": ev, "cta": {"label": "Buka Kalender", "href": "/calendar"}})
            await notify(x.conversation_id, {"type": "message", "role": "assistant"})
    return ev


def event_markdown(ev: dict) -> str:
    from reminders import _minutes_label
    from zoneinfo import ZoneInfo
    hari = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    bulan = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
    try:
        d = datetime.fromisoformat(ev["start_at"]).astimezone(ZoneInfo("Asia/Jakarta"))
        when = f"{hari[d.weekday()]}, {d.day} {bulan[d.month - 1]} {d.year} {d:%H:%M} WIB"
    except Exception:
        when = ev["start_at"]
    rem = ev.get("remind")
    rep = {"daily": " · berulang setiap hari", "weekly": " · berulang setiap minggu", "monthly": " · berulang setiap bulan"}.get((rem or {}).get("repeat") or "", "")
    line = (f"\n🔔 Ingatkan via **{'panggilan' if rem['mode'] == 'call' else 'chat'}** " + ", ".join(f"{_minutes_label(m)} sebelum" for m in rem["offsets"]) + rep) if rem else "\n🔕 Tanpa pengingat"
    return f"📅 **Tercatat di kalender:** {ev['title']}\n🕒 {when}{line}" + (f"\n📝 {ev['notes']}" if ev.get("notes") else "")


async def delete_event_doc(eid: str, uid: str) -> None:
    """Remove an event together with its linked reminder(s)."""
    ev = await db.events.find_one({"id": eid, "user_id": uid}, {"_id": 0, "reminder_id": 1})
    res = await db.events.delete_one({"id": eid, "user_id": uid})
    if not res.deleted_count:
        raise HTTPException(404, "Event tidak ditemukan")
    await db.reminders.delete_many({"$or": [{"event_id": eid}, {"id": ev.get("reminder_id") or "-"}], "user_id": uid})


@router.get("/events/upcoming")
async def events_upcoming(q: str = "", u: dict = Depends(current_user)):
    """Voice tool `find_calendar_event`: the user's recorded agenda (events + standalone reminders), optionally filtered by title words."""
    from agenda_flow import upcoming_items, _tz
    return {"items": (await upcoming_items(u["id"], _tz(u), q))[:15]}


class CancelAgendaIn(BaseModel):
    id: str
    kind: str = Field(pattern="^(event|reminder)$")
    conversation_id: Optional[str] = None


@router.post("/events/cancel")
async def events_cancel(x: CancelAgendaIn, u: dict = Depends(current_user)):
    """Voice tool `cancel_calendar_event` (after the user confirmed aloud): delete the agenda + reminder and post a card to the chat."""
    from agenda_flow import upcoming_items, delete_item, _tz
    item = next((i for i in await upcoming_items(u["id"], _tz(u)) if i["id"] == x.id and i["kind"] == x.kind), None)
    if not item:
        raise HTTPException(404, "Agenda tidak ditemukan")
    await delete_item(u["id"], item)
    if x.conversation_id:
        conv = await db.conversations.find_one({"id": x.conversation_id, "participants": u["id"]}, {"_id": 0, "persona_id": 1, "persona_ids": 1})
        pid = conv and ((conv.get("persona_ids") or [conv.get("persona_id")])[0])
        persona = pid and await db.personas.find_one({"id": pid}, {"_id": 0})
        if persona:
            from chat import notify
            await _save_ai_msg(x.conversation_id, persona, f"Agenda **{item['title']}** ({item['when']}) {'beserta pengingatnya ' if item.get('remind_mode') else ''}sudah dihapus ✅ dari kalender Oryntix.", 0, "voice",
                               {"tool": "calendar_cancelled", "item": item, "cta": {"label": "Buka Kalender", "href": "/calendar"}})
            await notify(x.conversation_id, {"type": "message", "role": "assistant"})
    return {"ok": True, "item": item}


@router.delete("/events/{eid}")
async def delete_event(eid: str, u: dict = Depends(current_user)):
    await delete_event_doc(eid, u["id"])
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
    async for r in db.reminders.find({"user_id": u["id"], "start_at": {"$gte": s, "$lt": e}, "event_id": {"$in": [None, ""]}}, {"_id": 0, "id": 1, "title": 1, "start_at": 1, "status": 1, "mode": 1, "offsets": 1}):
        items.append({"kind": "reminder", "id": r["id"], "title": r["title"], "at": r["start_at"], "status": r.get("status"), "link": "/reminders",
                      "remind": {"mode": r.get("mode", "call"), "offsets": r.get("offsets") or [r.get("remind_minutes", 30)]}})
    async for c in db.conversations.find({"workspace_id": wid, "type": "meeting", "participants": u["id"], "updated_at": {"$gte": s, "$lt": e}},
                                         {"_id": 0, "id": 1, "title": 1, "updated_at": 1, "members": 1}):
        items.append({"kind": "meeting", "id": c["id"], "title": c["title"], "at": c["updated_at"], "who": ", ".join(m["name"] for m in c.get("members") or []), "link": f"/chat/{c['id']}"})
    async for ev in db.events.find({"workspace_id": wid, "start_at": {"$gte": s, "$lt": e}}, {"_id": 0}):
        items.append({"kind": "event", "id": ev["id"], "title": ev["title"], "at": ev["start_at"], "end_at": ev.get("end_at"), "notes": ev.get("notes"), "mine": ev["user_id"] == u["id"],
                      "remind": ev.get("remind"), "link": "/reminders" if ev.get("remind") else None})
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
                                                        "Use ONLY the data given; never invent items. Max ~180 words.\n\n" + lang_rule(u))
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
        await db.users.update_one({"id": u["id"]}, {"$set": {"digest_last_date": _local_now((u.get("settings") or {}).get("timezone")).strftime("%Y-%m-%d")}})
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
            # claim today's slot first, then generate in the background so reminders/tasks are not delayed
            await db.users.update_one({"id": u["id"]}, {"$set": {"digest_last_date": today}})
            asyncio.create_task(_digest_bg(u))


async def _digest_bg(u: dict):
    try:
        await send_digest(u)
    except Exception as e:
        log.error("digest for %s failed: %s", u.get("email"), e)


@router.post("/digest/send-now")
async def digest_now(u: dict = Depends(current_user)):
    """Preview/manual trigger from the Calendar settings card."""
    return await send_digest(u, force=True)


# ---------- workspace search (keyword) ----------
SEARCH_STOP = set("tolong carikan cari carilah temukan ada apakah dokumen hasil file berkas yang tentang mengenai di ruang kerja workspace saya kita punya nggak gak tidak sudah pernah dibuat buatan minggu lalu kemarin bulan ini itu dong ya please find search for the a an of in my our is there any".split())


def _keywords(q: str) -> list:
    words = [w.strip("?.,!:;\"'()").lower() for w in (q or "").split()]
    return [w for w in words if len(w) > 2 and w not in SEARCH_STOP][:8]


async def search_workspace(u: dict, q: str, limit: int = 8) -> list:
    kws = _keywords(q)
    if not kws:
        return []
    import re as _re
    cond = [{"$or": [{"goal": {"$regex": _re.escape(k), "$options": "i"}}, {"summary": {"$regex": _re.escape(k), "$options": "i"}}, {"final_output": {"$regex": _re.escape(k), "$options": "i"}}]} for k in kws]
    rows = await db.tasks.find({"workspace_id": workspace_id(u), "status": "completed", "$or": cond},
                               {"_id": 0, "id": 1, "goal": 1, "type": 1, "status": 1, "persona_name": 1, "updated_at": 1, "version": 1, "final_output": 1, "summary": 1}).sort("updated_at", -1).to_list(60)
    out = []
    for r in rows:
        body = (r.get("final_output") or "")
        score = sum(body.lower().count(k) + 5 * (k in (r.get("goal") or "").lower()) for k in kws)
        pos = next((body.lower().find(k) for k in kws if body.lower().find(k) >= 0), 0)
        snippet = body[max(0, pos - 80): pos + 160].replace("\n", " ").strip()
        out.append({"id": r["id"], "title": r.get("goal"), "type": r.get("type"), "persona_name": r.get("persona_name"), "updated_at": r.get("updated_at"),
                    "version": r.get("version") or 1, "snippet": snippet, "link": f"/workspace/{r['id']}", "_score": score})
    out.sort(key=lambda x: -x["_score"])
    return [{k: v for k, v in o.items() if k != "_score"} for o in out[:limit]]


@router.get("/workspace/search")
async def workspace_search(q: str, u: dict = Depends(current_user)):
    return await search_workspace(u, q)


def results_markdown(results: list, q: str) -> str:
    if not results:
        return f"Saya sudah mencari di Ruang Kerja untuk «{q}», tapi belum menemukan hasil yang cocok. Coba kata kunci lain, atau mau saya buatkan?"
    lines = [f"Saya menemukan {len(results)} item di Ruang Kerja untuk «{q}»:"]
    for r in results:
        who = f" · {r['persona_name']}" if r.get("persona_name") else ""
        lines.append(f"- [{r['title']}]({r['link']}) (v{r['version']}{who}) — {r['snippet'][:120]}…" if r.get("snippet") else f"- [{r['title']}]({r['link']}) (v{r['version']}{who})")
    lines.append("Klik judulnya untuk membuka, atau tanyakan isinya langsung ke saya.")
    return "\n".join(lines)


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=300)


@router.post("/conversations/{cid}/workspace-search")
async def conv_workspace_search(cid: str, x: SearchIn, u: dict = Depends(current_user)):
    """Voice tool / meeting chat: search and drop the links as an assistant message into the conversation."""
    conv = await db.conversations.find_one({"id": cid}, {"_id": 0})
    if not conv or not _can_access(conv, u):
        raise HTTPException(404, "Conversation not found")
    results = await search_workspace(u, x.query)
    persona = (await _get_personas([conv.get("persona_id") or (conv.get("persona_ids") or [None])[0]]) or [None])[0]
    if persona:
        await _save_ai_msg(cid, persona, results_markdown(results, x.query), 0, "text", {"tool": "workspace_search", "results": results})
    return {"count": len(results), "results": [{"title": r["title"], "id": r["id"], "assistant": r.get("persona_name")} for r in results]}


# ---------- team delegation (lead splits a task into sub-tasks for other assistants) ----------
def _find_persona(name: Optional[str], personas: list) -> Optional[dict]:
    n = (name or "").strip().lower()
    if not n:
        return None
    return next((p for p in personas if p["name"].lower() == n), None) or next((p for p in personas if n in p["name"].lower() or p["name"].lower().split()[0] == n), None)


def names_mentioned(text: str, personas: list, exclude_id: Optional[str] = None) -> list:
    import re as _re
    low = (text or "").lower()
    return [p["name"] for p in personas if p["id"] != exclude_id and _re.search(r"\b" + _re.escape(p["name"].lower()) + r"\b", low)]


async def plan_subtasks(title: str, brief: str, personas: list, directives: str = "", u: Optional[dict] = None) -> list:
    from llm import llm_json
    roster = "\n".join(f"- {p['name']} (model {p.get('model')})" for p in personas)
    try:
        r = await llm_json("Split the task into 2-5 independent sub-tasks for a team of AI assistants. Reply JSON {\"subtasks\":[{\"title\":str,\"brief\":str,\"specialty\":\"it\"|\"research\"|\"writing\"|\"general\",\"assignee\":str|null}]}. "
                           f"Titles and briefs in {_lang_name(u or {})}. assignee: when the user EXPLICITLY names which assistant should handle a part (e.g. 'bagian keuangan minta Nova'), create a sub-task for that part and set assignee to the exact name as the user wrote it; "
                           "every other sub-task gets assignee null. Never invent assignees.",
                           f"Task: {title}\nDetails: {brief}\nUser's assignment instructions: {directives or '(none)'}\nTeam:\n{roster}")
        subs = r.get("subtasks") if isinstance(r, dict) else None
        return [s for s in (subs or []) if s.get("title")][:5]
    except Exception:
        return []


async def _assign_personas(subtasks: list, personas: list, lead: dict) -> tuple:
    """Honor explicit assignees first; others by specialty / round-robin. Returns ([(subtask, persona)], unmatched_names)."""
    from tools import get_routing
    routing = await get_routing()
    by_spec = {"it": [p for p in personas if p.get("model") == routing.get("it_model")], "research": [p for p in personas if p.get("model") == routing.get("research_model")]}
    others = [p for p in personas if p["id"] != lead["id"]] or [lead]
    out, unmatched, i = [], [], 0
    for s in subtasks:
        chosen = _find_persona(s.get("assignee"), personas)
        s["_pinned"] = chosen is not None
        if s.get("assignee") and not chosen:
            unmatched.append(str(s["assignee"]).strip())
        if not chosen:
            pool = by_spec.get(s.get("specialty")) or others
            chosen = pool[i % len(pool)]; i += 1
        out.append((s, chosen))
    return out, list(dict.fromkeys(unmatched))


def _directives(plan: dict) -> str:
    parts = [plan.get("directives") or ""]
    parts += [f"{a.get('assistant')}: {a.get('part')}" for a in (plan.get("assignments") or []) if a.get("assistant")]
    return "\n".join(p for p in parts if p).strip()


def team_summary(task: dict) -> str:
    who = ", ".join(f"{s['persona_name']} → {s['title']}" for s in task.get("subtasks") or [])
    note = f" Catatan: {', '.join(task['unmatched'])} tidak ada di tim, jadi bagian itu saya pilihkan asisten otomatis." if task.get("unmatched") else ""
    return f"Pembagian: {who or 'saya kerjakan sendiri'}.{note}"


async def create_team_task(u: dict, lead: dict, conv: dict, plan: dict, source: str) -> dict:
    wid = workspace_id(u)
    personas = await db.personas.find({"user_id": wid, "deleted": {"$ne": True}}, {"_id": 0}).to_list(50)
    subs = plan.get("subtasks") or await plan_subtasks(plan.get("title") or "", plan.get("brief") or "", personas, _directives(plan), u)
    if len(subs) < 2:
        return await create_assigned_task(u, lead, conv, plan, source)
    sched = _utc(plan.get("scheduled_at"))
    future = bool(sched) and sched > now_iso()
    assigned, unmatched = await _assign_personas(subs, personas, lead)
    parent = {"id": new_id(), "user_id": u["id"], "workspace_id": wid, "goal": plan.get("title") or "", "brief": plan.get("brief") or "", "type": "assigned", "team": True,
              "status": "scheduled" if future else "running", "scheduled_at": sched, "steps": [], "summary": f"Dibagi ke tim oleh {lead['name']}", "final_output": "", "credits_used": 0,
              "persona_id": lead["id"], "persona_name": lead["name"], "source": source, "conversation_ids": [conv["id"]] if conv else [], "version": 1, "notified": False,
              "subtasks": [], "unmatched": unmatched, "created_at": now_iso(), "updated_at": now_iso()}
    for s, p in assigned:
        child = {"id": new_id(), "user_id": u["id"], "workspace_id": wid, "goal": s["title"], "brief": s.get("brief") or "", "type": "assigned", "parent_id": parent["id"],
                 "status": "scheduled" if future else "queued", "scheduled_at": sched, "steps": [], "summary": f"Sub-tugas dari «{parent['goal']}»", "final_output": "", "credits_used": 0,
                 "persona_id": p["id"], "persona_name": p["name"], "source": source, "conversation_ids": [], "version": 1, "notified": True, "pinned": bool(s.get("_pinned")), "created_at": now_iso(), "updated_at": now_iso()}
        await db.tasks.insert_one(dict(child))
        parent["subtasks"].append({"id": child["id"], "title": child["goal"], "persona_id": p["id"], "persona_name": p["name"], "status": child["status"], "pinned": child["pinned"]})
        if not future:
            asyncio.create_task(execute_assigned_task(child["id"]))
    await db.tasks.insert_one(dict(parent))
    return parent


async def _assemble_team_output(parent: dict, kids: list) -> None:
    """Team lead merges finished sub-task results into the parent's final document and announces it."""
    parent_id = parent["id"]
    u = await db.users.find_one({"id": parent["user_id"]}, {"_id": 0}) or {}
    lead = await db.personas.find_one({"id": parent.get("persona_id")}, {"_id": 0}) or {"name": "Asisten"}
    parts = "\n\n".join(f"## {k['goal']} (oleh {k.get('persona_name')})\n{k.get('final_output') or '(gagal)'}" for k in kids)
    system = (await _persona_system(lead, u, None) if lead.get("id") else "") + "\n\nYou are the TEAM LEAD assembling your team's sub-task results into ONE coherent, complete deliverable in markdown. Keep all substantive content, remove duplication, add a short executive summary at the top and credit each assistant's section.\n\n" + lang_rule(u) + " Translate any section that is in the wrong language."
    prompt = f"Task: {parent.get('goal')}\nDetails: {parent.get('brief')}\n\nSUB-TASK RESULTS:\n{parts[:40000]}"
    try:
        out = await llm_text(system, prompt, parent.get("model"))
    except Exception as e:
        await db.tasks.update_one({"id": parent_id}, {"$set": {"status": "failed", "error": str(e)[:300]}})
        return
    used = text_credits(prompt, out)
    await record_usage(parent["user_id"], "assigned_task", used, {"task_id": parent_id})
    await db.tasks.update_one({"id": parent_id}, {"$set": {"status": "completed", "final_output": out, "credits_used": used + sum(k.get("credits_used") or 0 for k in kids), "completed_at": now_iso(), "updated_at": now_iso()}})
    who = ", ".join(f"{k.get('persona_name')} ({k['goal']})" for k in kids)
    for cid in parent.get("conversation_ids") or []:
        await _save_ai_msg(cid, lead, f"Tugas tim **{parent.get('goal')}** selesai ✅ — bagian dikerjakan oleh {who}; saya rangkai jadi satu dokumen di Ruang Kerja: [buka hasilnya](/workspace/{parent_id}).", 0, "text", {"tool": "task_done", "task_id": parent_id})


async def _maybe_assemble(parent_id: str):
    parent = await db.tasks.find_one({"id": parent_id}, {"_id": 0})
    if not parent or parent.get("status") == "completed":
        return
    kids = await db.tasks.find({"parent_id": parent_id}, {"_id": 0}).to_list(20)
    subtasks = [{"id": k["id"], "title": k["goal"], "persona_id": k.get("persona_id"), "persona_name": k.get("persona_name"), "status": k["status"], "pinned": bool(k.get("pinned"))} for k in kids]
    await db.tasks.update_one({"id": parent_id}, {"$set": {"subtasks": subtasks, "updated_at": now_iso()}})
    if any(k["status"] not in ("completed", "failed") for k in kids):
        return
    claimed = await db.tasks.find_one_and_update({"id": parent_id, "status": {"$nin": ["assembling", "completed"]}}, {"$set": {"status": "assembling"}})
    if claimed:  # otherwise another child's completion is already assembling
        await _assemble_team_output(parent, kids)
