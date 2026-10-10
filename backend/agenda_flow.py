"""Agenda flows in chat: confirm (when · what time · call or chat) BEFORE recording a calendar entry/reminder, and
confirm BEFORE deleting when the user says an agenda is cancelled. State lives in conversations.pending_calendar / pending_cancel."""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from db import db, now_iso
from tools import plan_calendar, llm_json, CAL_RE

YES_RE = re.compile(r"^\W*(ya|iya|yap|yup|yes|ok|oke|okay|okey|sip|siap|betul|benar|bener|boleh|lanjut|gas|silakan|setuju|mantap|y|hapus( saja| aja)?|catat( saja| aja)?|simpan)\b", re.I)
NO_RE = re.compile(r"^\W*(tidak|tdk|nggak|ngga|gak|ga|enggak|jangan|batal(kan)?|no|nope|skip|gausah|ga usah|nggak usah|tidak usah|belum|tahan|biarkan)\b", re.I)
CANCEL_RE = re.compile(r"\b(batal|dibatalkan|batalkan|cancel(l?ed)?|dicancel|(gak|ga|nggak|ngga|tidak|ndak|enggak) jadi|ditunda|hapus(kan)? (pengingat|agenda|jadwal|event|acara|reminder|rapat|meeting|janji))\b", re.I)
RESCHEDULE_RE = re.compile(r"\b(diundur|dimundurkan|dimajukan|digeser|geser|pindah(kan)?|dipindah(kan)?|reschedule|ubah (jadwal|jam|waktu|harinya|jamnya)|ganti (jam|hari|waktu|jadwal)|(ditunda|diubah|jadi|mundur|maju) (ke |jam |hari |tanggal |besok|lusa))", re.I)
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
REPEAT_ID = {"daily": "setiap hari", "weekly": "setiap minggu", "monthly": "setiap bulan"}


def _tz(user: dict) -> str:
    return (user.get("settings") or {}).get("timezone") or "Asia/Jakarta"


def when_label(iso: str, tz: str) -> str:
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ZoneInfo(tz))
    except Exception:
        return iso
    return f"{HARI[d.weekday()]}, {d.day} {BULAN[d.month - 1]} {d.year} {d:%H:%M}"


def _minutes(m: int) -> str:
    return f"{m // 1440} hari" if m % 1440 == 0 else f"{m // 60} jam" if m % 60 == 0 else f"{m} menit"


def _remind_line(mode, offsets, repeat) -> str:
    rep = f" · {REPEAT_ID[repeat]}" if repeat in REPEAT_ID else ""
    if not (mode and offsets):
        return "🔕 Tanpa pengingat" + rep
    via = "panggilan telepon dari saya" if mode == "call" else "pesan chat"
    return f"🔔 Pengingat via **{via}**, " + ", ".join(f"{_minutes(m)} sebelum" for m in offsets) + rep


PENDING_KEYS = ("pending_calendar", "pending_cancel", "pending_reschedule")


def wants_agenda(text: str) -> bool:
    return bool(CAL_RE.search(text or "") or CANCEL_RE.search(text or "") or RESCHEDULE_RE.search(text or ""))


async def agenda_turn(ctx):
    """Entry point from the chat intercepts. Yields nothing when the message is not about the user's agenda."""
    from chat import _emit_final
    conv = await db.conversations.find_one({"id": ctx.cid}, {"_id": 0, **{k: 1 for k in PENDING_KEYS}}) or {}
    text = ctx.user_text
    if conv.get("pending_calendar"):
        gen = _calendar_turn(ctx, conv["pending_calendar"], _emit_final)
    elif conv.get("pending_reschedule") or (not conv.get("pending_cancel") and RESCHEDULE_RE.search(text)):
        gen = _reschedule_turn(ctx, conv.get("pending_reschedule"), _emit_final)
    elif conv.get("pending_cancel") or CANCEL_RE.search(text):
        gen = _cancel_turn(ctx, conv.get("pending_cancel"), _emit_final)
    else:
        gen = _calendar_turn(ctx, None, _emit_final)
    async for ev in gen:
        yield ev


# ---------------- record: ask what is missing → confirm → create ----------------
async def _set_pending(cid: str, key: str, value):
    await db.conversations.update_one({"id": cid}, {"$set": {key: value}})


def _plan_parts(plan: dict):
    offsets = [int(o) for o in (plan.get("remind_offsets") or []) if isinstance(o, (int, float))]
    no_reminder = offsets == [0]
    offsets = [o for o in offsets if o > 0]
    mode = plan.get("remind_mode") if plan.get("remind_mode") in ("call", "chat") else None
    repeat = plan.get("repeat") if plan.get("repeat") in REPEAT_ID else "none"
    return offsets, no_reminder, mode, repeat


def _missing_question(plan: dict, missing_time: bool, missing_mode: bool, tz: str) -> str:
    title = plan.get("title") or "kegiatan ini"
    if missing_time and missing_mode:
        return f"Siap, «{title}» akan saya catat. Tanggal & jam berapa tepatnya, dan mau diingatkan lewat **panggilan telepon** dari saya atau cukup lewat **chat**? (bisa juga tanpa pengingat)"
    if missing_time:
        return plan.get("question") or f"Siap, saya catat «{title}». Tanggal dan jam berapa tepatnya?"
    return f"«{title}» pada **{when_label(plan['start_at'], tz)}**. Mau saya ingatkan lewat **panggilan telepon** atau cukup lewat **chat**? Atau tanpa pengingat?"


async def _create_from_plan(ctx, plan: dict) -> tuple:
    from assignments import EventIn, create_event_doc, event_markdown
    ev = await create_event_doc(ctx.user, EventIn(title=plan["title"], start_at=plan["start_at"], notes=plan.get("notes") or "", remind_mode=plan["mode"] if plan["offsets"] else None,
                                                  remind_offsets=plan["offsets"], persona_id=ctx.persona["id"], repeat=plan["repeat"]))
    tail = "\n\n📞 Saya akan **menelepon Anda otomatis** sesuai jadwal pengingat — pastikan notifikasi Oryntix aktif." if plan["mode"] == "call" and plan["offsets"] else ""
    return event_markdown(ev) + tail, ev


async def _calendar_turn(ctx, pending, emit):
    tz = _tz(ctx.user)
    text = ctx.user_text
    if pending and pending.get("stage") == "confirm":
        if NO_RE.match(text):
            await _set_pending(ctx.cid, "pending_calendar", None)
            yield ctx.sse(start=True)
            async for ev in emit(ctx, "Baik, tidak jadi saya catat. Kalau berubah pikiran, tinggal bilang ya.", 0, {"tool": "calendar_question"}):
                yield ev
            return
        if YES_RE.match(text):
            await _set_pending(ctx.cid, "pending_calendar", None)
            yield ctx.sse(start=True)
            try:
                msg, ev_doc = await _create_from_plan(ctx, pending["plan"])
            except Exception:
                async for ev in emit(ctx, "Maaf, waktunya belum bisa saya simpan. Bisa sebutkan lagi tanggal dan jamnya?", 0, {"tool": "calendar_question"}):
                    yield ev
                return
            async for ev in emit(ctx, msg, 0, {"tool": "calendar_event", "event": ev_doc, "cta": {"label": "Buka Kalender", "href": "/calendar"}}):
                yield ev
            return
    merged = f"{pending['text']}\nJawaban/koreksi user atas «{pending['question']}»: {text}" if pending else text
    plan = await plan_calendar(merged, tz, ctx.prompt[-600:] if ctx.prompt else "", force=bool(pending))
    if pending:
        await _set_pending(ctx.cid, "pending_calendar", None)
    if not plan:
        return
    yield ctx.sse(start=True)
    offsets, no_reminder, mode, repeat = _plan_parts(plan)
    missing_time = not plan.get("start_at") or bool(plan.get("question"))
    missing_mode = not no_reminder and mode is None
    if missing_time or missing_mode:
        q = _missing_question(plan, missing_time, missing_mode, tz)
        await _set_pending(ctx.cid, "pending_calendar", {"text": merged[:1500], "question": q[:400], "stage": "ask", "at": now_iso()})
        async for ev in emit(ctx, q, 0, {"tool": "calendar_question"}):
            yield ev
        return
    final = {"title": (plan.get("title") or text[:80]).strip()[:200], "start_at": plan["start_at"], "notes": (plan.get("notes") or "")[:2000],
             "mode": mode, "offsets": offsets or ([] if no_reminder else [30]), "repeat": repeat}
    summary = (f"Saya rangkum dulu ya:\n📅 **{final['title']}**\n🕒 {when_label(final['start_at'], tz)}\n{_remind_line(final['mode'], final['offsets'], repeat)}"
               + (f"\n📝 {final['notes']}" if final["notes"] else "")
               + "\n\nSudah benar? Balas **ya** untuk saya catat ke kalender, atau sebutkan yang perlu diubah.")
    await _set_pending(ctx.cid, "pending_calendar", {"text": merged[:1500], "question": summary[:600], "stage": "confirm", "plan": final, "at": now_iso()})
    async for ev in emit(ctx, summary, 0, {"tool": "calendar_confirm", "pending_calendar": final}):
        yield ev


# ---------------- cancel: find the recorded agenda → confirm → delete ----------------
async def upcoming_items(uid: str, tz: str, q: str = "", limit: int = 40) -> list:
    """Events + standalone reminders from yesterday onwards; optional fuzzy title filter (falls back to all when nothing matches)."""
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    items = []
    async for e in db.events.find({"user_id": uid, "start_at": {"$gte": since}}, {"_id": 0}).sort("start_at", 1).limit(limit):
        rem = e.get("remind") or {}
        items.append({"id": e["id"], "kind": "event", "title": e["title"], "start_at": e["start_at"], "when": when_label(e["start_at"], tz), "remind_mode": rem.get("mode"), "repeat": rem.get("repeat") or "none"})
    async for r in db.reminders.find({"user_id": uid, "event_id": None, "start_at": {"$gte": since}}, {"_id": 0}).sort("start_at", 1).limit(limit):
        items.append({"id": r["id"], "kind": "reminder", "title": r["title"], "start_at": r["start_at"], "when": when_label(r["start_at"], tz), "remind_mode": r.get("mode"), "repeat": r.get("repeat") or "none"})
    items.sort(key=lambda x: x["start_at"])
    words = [w for w in re.findall(r"\w+", (q or "").lower()) if len(w) > 2]
    if words:
        hit = [i for i in items if any(w in i["title"].lower() for w in words)]
        return hit or items
    return items


async def plan_cancel(text: str, tz: str, items: list, history: str = "") -> dict:
    listing = "\n".join(f"- id={i['id']} | {i['title']} | {i['when']} | {i['kind']}" for i in items) or "(none recorded)"
    try:
        now = datetime.now(ZoneInfo(tz))
    except Exception:
        now = datetime.now(timezone.utc)
    try:
        r = await llm_json(
            "The user says a plan/agenda is cancelled or postponed, or asks to remove a reminder. Decide which of THEIR RECORDED items they mean. Reply JSON only: "
            "{\"is_cancel\": bool, \"match_id\": str|null, \"title\": str, \"question\": str|null}. is_cancel=false when the message is not about cancelling/removing an agenda, "
            "meeting, appointment or reminder (e.g. cancelling an order or a subscription, or unrelated chat). match_id: the id of the ONE recorded item that clearly matches by title and/or "
            "time; null when nothing matches or several are equally plausible. title: short Indonesian name of the agenda as the user calls it. question: when several items are plausible, "
            "ONE short Indonesian question listing them so the user can pick; else null.",
            f"Now: {now.isoformat()} ({tz}).\nRecorded items:\n{listing}\nRecent context: {history[-500:]}\nUser message: {text}")
    except Exception:
        return {}
    return r if isinstance(r, dict) else {}


async def delete_item(uid: str, item: dict) -> None:
    from assignments import delete_event_doc
    if item["kind"] == "event":
        await delete_event_doc(item["id"], uid)
    else:
        await db.reminders.delete_one({"id": item["id"], "user_id": uid})


async def _cancel_turn(ctx, pending, emit):
    tz = _tz(ctx.user)
    text = ctx.user_text
    if pending and pending.get("stage") == "confirm":
        item = pending["item"]
        if NO_RE.match(text) or YES_RE.match(text):
            await _set_pending(ctx.cid, "pending_cancel", None)
            yield ctx.sse(start=True)
            if NO_RE.match(text):
                msg, extra = f"Baik, agenda **{item['title']}** ({item['when']}) tetap tersimpan di kalender.", {"tool": "calendar_cancel_kept"}
            else:
                await delete_item(ctx.user["id"], item)
                msg = f"Agenda **{item['title']}** ({item['when']}) {'beserta pengingatnya ' if item.get('remind_mode') else ''}sudah saya hapus ✅ dari kalender Oryntix."
                extra = {"tool": "calendar_cancelled", "item": item, "cta": {"label": "Buka Kalender", "href": "/calendar"}}
            async for ev in emit(ctx, msg, 0, extra):
                yield ev
            return
    merged = f"{pending['text']}\nJawaban user atas «{pending['question']}»: {text}" if pending else text
    items = await upcoming_items(ctx.user["id"], tz)
    plan = await plan_cancel(merged, tz, items, ctx.prompt[-500:] if ctx.prompt else "") if items else {"is_cancel": bool(CANCEL_RE.search(text))}
    if pending:
        await _set_pending(ctx.cid, "pending_cancel", None)
    if not plan.get("is_cancel"):
        return
    yield ctx.sse(start=True)
    title = plan.get("title") or ""
    named = f"agenda «{title}»" if title else "agenda yang Anda maksud"
    item = next((i for i in items if i["id"] == plan.get("match_id")), None)
    if item:
        via = {"call": " beserta pengingat via panggilan", "chat": " beserta pengingat via chat"}.get(item.get("remind_mode") or "", "")
        q = f"Saya cek, agenda **{item['title']}** pada **{item['when']}** memang tercatat di Oryntix{via}. Mau saya hapus dari kalender{' beserta pengingatnya' if via else ''}?"
        await _set_pending(ctx.cid, "pending_cancel", {"stage": "confirm", "item": item, "text": merged[:1500], "question": q[:400], "at": now_iso()})
        async for ev in emit(ctx, q, 0, {"tool": "calendar_cancel_confirm", "item": item}):
            yield ev
        return
    if not items or pending:
        msg = f"Saya cek, {named} tidak tercatat di kalender Oryntix — jadi tidak ada yang perlu dihapus. Kalau ada jadwal penggantinya, saya bisa bantu catat."
        async for ev in emit(ctx, msg, 0, {"tool": "calendar_cancel_none"}):
            yield ev
        return
    q = plan.get("question") or f"Saya cek, {named} tidak saya temukan di kalender Oryntix. Apakah dulu pernah dicatat dengan nama atau waktu lain? Sebutkan saja, nanti saya hapuskan."
    await _set_pending(ctx.cid, "pending_cancel", {"stage": "ask", "text": merged[:1500], "question": q[:400], "at": now_iso()})
    async for ev in emit(ctx, q, 0, {"tool": "calendar_cancel_question"}):
        yield ev


# ---------------- reschedule: find the recorded agenda → new time → confirm → move ----------------
async def plan_reschedule(text: str, tz: str, items: list, history: str = "") -> dict:
    listing = "\n".join(f"- id={i['id']} | {i['title']} | {i['when']} | {i['kind']}" for i in items) or "(none recorded)"
    try:
        now = datetime.now(ZoneInfo(tz))
    except Exception:
        now = datetime.now(timezone.utc)
    try:
        r = await llm_json(
            "The user wants to move (postpone/bring forward/reschedule) one of THEIR RECORDED agenda items. Reply JSON only: "
            "{\"is_reschedule\": bool, \"match_id\": str|null, \"new_start\": str|null, \"title\": str, \"question\": str|null}. "
            "is_reschedule=false when the message is not about moving an agenda/meeting/appointment/reminder to another time. match_id: id of the ONE recorded item that clearly matches by title "
            "and/or current time (null if none or ambiguous). new_start: the NEW local date-time as \"YYYY-MM-DDTHH:MM\" resolved against Now (keep the item's current time of day when the user only "
            "gives a new day, keep the day when they only give a new time); null if the user did not say when. title: short Indonesian name of the agenda. question: ONE short Indonesian "
            "question only when several recorded items are plausible (list them); else null.",
            f"Now: {now.strftime('%A %Y-%m-%dT%H:%M')} ({tz}).\nRecorded items:\n{listing}\nRecent context: {history[-500:]}\nUser message: {text}")
    except Exception:
        return {}
    return r if isinstance(r, dict) else {}


def _local_to_utc(local: str, tz: str):
    try:
        return datetime.fromisoformat(local[:16]).replace(tzinfo=ZoneInfo(tz)).astimezone(timezone.utc).isoformat()
    except Exception:
        return None


async def _reschedule_turn(ctx, pending, emit):
    from assignments import move_agenda_doc
    tz = _tz(ctx.user)
    text = ctx.user_text
    if pending and pending.get("stage") == "confirm" and (NO_RE.match(text) or YES_RE.match(text)):
        item = pending["item"]
        await _set_pending(ctx.cid, "pending_reschedule", None)
        yield ctx.sse(start=True)
        if NO_RE.match(text):
            msg, extra = f"Baik, agenda **{item['title']}** tetap pada **{item['when']}**.", {"tool": "calendar_move_kept"}
        else:
            moved = await move_agenda_doc(ctx.user["id"], item, pending["new_start"])
            moved["when"] = when_label(pending["new_start"], tz)
            msg = (f"Agenda **{item['title']}** sudah dipindahkan dari {item['when']} ke **{moved['when']}**"
                   + (" — pengingatnya ikut saya geser" if item.get("remind_mode") else "") + " ✅.")
            extra = {"tool": "calendar_moved", "item": moved, "cta": {"label": "Buka Kalender", "href": "/calendar"}}
        async for ev in emit(ctx, msg, 0, extra):
            yield ev
        return
    merged = f"{pending['text']}\nJawaban user atas «{pending['question']}»: {text}" if pending else text
    items = await upcoming_items(ctx.user["id"], tz)
    plan = await plan_reschedule(merged, tz, items, ctx.prompt[-500:] if ctx.prompt else "") if items else {"is_reschedule": bool(RESCHEDULE_RE.search(text))}
    if pending:
        await _set_pending(ctx.cid, "pending_reschedule", None)
    if not plan.get("is_reschedule"):
        return
    yield ctx.sse(start=True)
    title = plan.get("title") or ""
    named = f"agenda «{title}»" if title else "agenda yang Anda maksud"
    item = next((i for i in items if i["id"] == plan.get("match_id")), None)
    new_start = _local_to_utc(plan.get("new_start") or "", tz) if plan.get("new_start") else None
    if item and new_start:
        if new_start <= datetime.now(timezone.utc).isoformat():
            q = f"Waktu barunya sudah lewat. **{item['title']}** mau dipindah ke kapan? (mis. \"Rabu jam 14.00\")"
            await _set_pending(ctx.cid, "pending_reschedule", {"stage": "ask", "text": merged[:1500], "question": q[:400], "at": now_iso()})
        else:
            via = " beserta pengingatnya" if item.get("remind_mode") else ""
            q = f"Agenda **{item['title']}** saat ini tercatat **{item['when']}**. Pindahkan ke **{when_label(new_start, tz)}**{via}?"
            await _set_pending(ctx.cid, "pending_reschedule", {"stage": "confirm", "item": item, "new_start": new_start, "text": merged[:1500], "question": q[:400], "at": now_iso()})
        async for ev in emit(ctx, q, 0, {"tool": "calendar_move_confirm", "item": item, "new_start": new_start}):
            yield ev
        return
    if item:
        q = f"Agenda **{item['title']}** ({item['when']}) mau dipindah ke hari dan jam berapa?"
    elif not items or pending:
        msg = f"Saya cek, {named} tidak tercatat di kalender Oryntix — tidak ada yang bisa digeser. Kalau mau, saya bisa catat jadwal barunya."
        async for ev in emit(ctx, msg, 0, {"tool": "calendar_move_none"}):
            yield ev
        return
    else:
        q = plan.get("question") or f"Saya cek, {named} tidak saya temukan di kalender Oryntix. Apakah dulu dicatat dengan nama atau waktu lain? Sebutkan saja beserta waktu barunya."
    await _set_pending(ctx.cid, "pending_reschedule", {"stage": "ask", "text": merged[:1500], "question": q[:400], "at": now_iso()})
    async for ev in emit(ctx, q, 0, {"tool": "calendar_move_question"}):
        yield ev
