import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import current_user
from chat import _can_access, _merge_summary, _save_ai_msg, _get_personas
from db import db, now_iso, new_id, clean
from llm import record_usage

log = logging.getLogger("aivora")
router = APIRouter(prefix="/api", tags=["archives"])
DEFAULT_ARCHIVE_HOURS = 24
MIN_LIVE_MSGS = 2
ACTIVE_TASK = ("queued", "running", "scheduled", "assembling")


def archive_hours(u: dict) -> int:
    v = (u.get("settings") or {}).get("auto_archive_hours")
    return DEFAULT_ARCHIVE_HOURS if v is None else int(v)


async def archive_conversation(conv: dict, u: dict, reason: str) -> Optional[dict]:
    """Summarize the live thread into conversation memory, archive the raw messages and record an archive entry."""
    cid = conv["id"]
    live = await db.messages.find({"conversation_id": cid, "archived": {"$ne": True}, "is_summary": {"$ne": True}}, {"_id": 0, "id": 1, "created_at": 1}).sort("created_at", 1).to_list(5000)
    if len(live) < MIN_LIVE_MSGS:
        return None
    core, summary, used = await _merge_summary(cid, u, conv, "Summarize this conversation so the assistant can continue it later without the raw transcript.")
    await record_usage(u["id"], "chat_summary", used, {"conversation_id": cid})
    aid = new_id()
    ids = [m["id"] for m in live]
    await db.messages.update_many({"id": {"$in": ids}}, {"$set": {"archived": True, "archive_id": aid}})
    hours = archive_hours(u)
    why = f"diarsipkan otomatis setelah {hours} jam tidak aktif" if reason == "auto" else "diarsipkan"
    note = {"id": new_id(), "conversation_id": cid, "role": "assistant", "content": f"📝 **Rangkuman percakapan sebelumnya**\n\n{summary}\n\n_{len(ids)} pesan {why} — cari & pulihkan di menu Arsip._",
            "persona_id": "__system__", "persona_name": "Rangkuman", "is_summary": True, "archive_id": aid, "portrait": None, "credits": used, "created_at": now_iso()}
    await db.messages.insert_one(dict(note))
    entry = {"id": aid, "user_id": conv.get("user_id") or u["id"], "conversation_id": cid, "title": conv.get("title") or "Percakapan", "conversation_type": conv.get("type"),
             "persona_names": [m["name"] for m in conv.get("members") or []], "period_start": live[0]["created_at"], "period_end": live[-1]["created_at"],
             "summary": summary, "core": core, "message_ids": ids, "message_count": len(ids), "reason": reason, "restored": False, "created_at": now_iso()}
    await db.chat_archives.insert_one(dict(entry))
    await db.conversations.update_one({"id": cid}, {"$set": {"memory_summary": core, "summary_snoozed_at_count": 0, "archive_checked_at": now_iso()}})
    return clean(entry)


async def archive_tick():
    """Scheduler: archive chats idle longer than the owner's auto_archive_hours (0 = off)."""
    async for u in db.users.find({"settings.auto_archive_hours": {"$ne": 0}}, {"_id": 0, "password_hash": 0}):
        hours = archive_hours(u)
        if hours <= 0:
            continue
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        q = {"user_id": u["id"], "archived_conv": {"$ne": True}, "updated_at": {"$lt": cutoff},
             "$or": [{"archive_checked_at": {"$exists": False}}, {"$expr": {"$lt": ["$archive_checked_at", "$updated_at"]}}]}
        async for conv in db.conversations.find(q, {"_id": 0}).limit(5):
            await db.conversations.update_one({"id": conv["id"]}, {"$set": {"archive_checked_at": now_iso()}})
            if conv.get("task_id") and await db.tasks.find_one({"id": conv["task_id"], "status": {"$in": ACTIVE_TASK}}, {"_id": 0, "id": 1}):
                continue
            try:
                await archive_conversation(conv, u, "auto")
            except Exception as e:
                log.error("auto-archive %s failed: %s", conv["id"], e)


# ---------- search / restore ----------
STOP = set("tolong cari carikan temukan arsip archive percakapan chat lama sebelumnya tentang mengenai soal yang di dan dengan pulihkan restore kembalikan saya kita dong ya please the a of".split())


def _kws(q: str) -> list:
    return [w.strip("?.,!:;\"'()").lower() for w in (q or "").split() if len(w.strip("?.,!:;\"'()")) > 2 and w.lower() not in STOP][:8]


async def search_archives(u: dict, q: str, limit: int = 10, before: Optional[str] = None) -> list:
    base = {"user_id": u["id"]}
    if before:
        base["created_at"] = {"$lt": before}
    kws = _kws(q)
    if kws:
        ors = []
        for k in kws:
            rx = {"$regex": re.escape(k), "$options": "i"}
            ors += [{"title": rx}, {"summary": rx}, {"persona_names": rx}]
        hit_ids = await db.messages.distinct("archive_id", {"archive_id": {"$exists": True}, "content": {"$regex": "|".join(re.escape(k) for k in kws), "$options": "i"}})
        if hit_ids:
            ors.append({"id": {"$in": hit_ids}})
        base["$or"] = ors
    rows = await db.chat_archives.find(base, {"_id": 0, "message_ids": 0}).sort("created_at", -1).to_list(limit)
    return rows


@router.get("/archives")
async def list_archives(q: Optional[str] = None, before: Optional[str] = None, limit: int = Query(20, ge=1, le=50), u: dict = Depends(current_user)):
    items = await search_archives(u, q or "", limit + 1, before)
    has_more = len(items) > limit
    items = items[:limit]
    return {"items": items, "has_more": has_more, "next_before": items[-1]["created_at"] if items and has_more else None}


@router.get("/archives/{aid}")
async def get_archive(aid: str, u: dict = Depends(current_user)):
    a = await db.chat_archives.find_one({"id": aid, "user_id": u["id"]}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Arsip tidak ditemukan")
    msgs = await db.messages.find({"id": {"$in": a.get("message_ids") or []}}, {"_id": 0, "id": 1, "role": 1, "content": 1, "persona_name": 1, "sender_name": 1, "created_at": 1, "media": 1}).sort("created_at", 1).to_list(5000)
    return {**{k: v for k, v in a.items() if k != "message_ids"}, "messages": msgs}


async def restore_archive(aid: str, u: dict) -> dict:
    a = await db.chat_archives.find_one({"id": aid, "user_id": u["id"]}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Arsip tidak ditemukan")
    conv = await db.conversations.find_one({"id": a["conversation_id"]}, {"_id": 0})
    if not conv or not _can_access(conv, u):
        raise HTTPException(404, "Percakapan asal tidak ditemukan")
    target = conv["id"] if not conv.get("archived_conv") else conv.get("merged_into") or conv["id"]
    await db.messages.update_many({"id": {"$in": a.get("message_ids") or []}}, {"$set": {"archived": False, "conversation_id": target}, "$unset": {"archive_id": ""}})
    await db.messages.delete_many({"conversation_id": target, "is_summary": True, "archive_id": aid})
    await db.chat_archives.update_one({"id": aid}, {"$set": {"restored": True, "restored_at": now_iso()}})
    await db.conversations.update_one({"id": target}, {"$set": {"updated_at": now_iso(), "archive_checked_at": now_iso()}})
    return {"ok": True, "conversation_id": target, "restored": a.get("message_count", 0), "title": a.get("title")}


@router.post("/archives/{aid}/restore")
async def restore_archive_ep(aid: str, u: dict = Depends(current_user)):
    return await restore_archive(aid, u)


class RemindIn(BaseModel):
    start_at: str
    title: Optional[str] = Field(default=None, max_length=200)


@router.post("/archives/{aid}/remind")
async def archive_to_reminder(aid: str, x: RemindIn, u: dict = Depends(current_user)):
    """Turn an archived conversation into a reminder (the summary becomes the reminder's description)."""
    a = await db.chat_archives.find_one({"id": aid, "user_id": u["id"]}, {"_id": 0})
    if not a:
        raise HTTPException(404, "Arsip tidak ditemukan")
    try:
        start = datetime.fromisoformat(x.start_at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, "Waktu tidak valid")
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    conv = await db.conversations.find_one({"id": a["conversation_id"]}, {"_id": 0, "persona_id": 1}) or {}
    doc = {"id": new_id(), "user_id": u["id"], "title": (x.title or f"Lanjutkan: {a['title']}")[:200], "description": (a.get("summary") or "")[:1500],
           "start_at": start.isoformat(), "remind_minutes": 0, "remind_at": start.isoformat(), "persona_id": conv.get("persona_id"), "status": "scheduled",
           "message": "", "archive_id": aid, "created_at": now_iso()}
    await db.reminders.insert_one(dict(doc))
    return clean(doc)


# ---------- assistant tools (chat text + voice) ----------
ARCHIVE_RE = re.compile(r"\b(arsip|archive|percakapan (lama|sebelumnya|yang lalu)|chat (lama|sebelumnya)|obrolan (lama|sebelumnya))\b", re.I)
RESTORE_RE = re.compile(r"\b(pulihkan|restore|kembalikan|buka lagi|munculkan lagi)\b", re.I)
YES_RE = re.compile(r"^\s*(ya|iya|yes|ok|oke|boleh|silakan|lanjut(kan)?|pulihkan|setuju)\b", re.I)
NO_RE = re.compile(r"^\s*(tidak|jangan|batal|no|nggak|gak|enggak)\b", re.I)


def _fmt_period(a: dict) -> str:
    def d(iso):
        try:
            return datetime.fromisoformat(iso).strftime("%d %b %Y")
        except Exception:
            return "-"
    s, e = d(a.get("period_start")), d(a.get("period_end"))
    return s if s == e else f"{s} – {e}"


def archive_results_markdown(results: list, q: str, ask_restore: bool) -> str:
    if not results:
        return f"Saya sudah mencari di Arsip untuk «{q}», tapi belum menemukan percakapan yang cocok. Coba kata kunci lain."
    lines = [f"Saya menemukan {len(results)} arsip untuk «{q}»:"]
    for i, a in enumerate(results, 1):
        lines.append(f"{i}. **{a['title']}** ({_fmt_period(a)}, {a.get('message_count', 0)} pesan) — {(a.get('summary') or '')[:140].replace(chr(10), ' ')}…")
    if ask_restore:
        lines.append(f"\nMau saya **pulihkan arsip «{results[0]['title']}»** ke chat ini? Jawab *ya* untuk memulihkan, atau sebut nomor arsip lain.")
    else:
        lines.append("\nBilang «pulihkan nomor 1» (atau klik tombolnya) kalau mau saya kembalikan ke chat — saya akan konfirmasi dulu sebelum memulihkan.")
    return "\n".join(lines)


async def archive_turn_text(ctx) -> Optional[dict]:
    """Handle archive search / restore intents in chat. Returns {content, extra} or None (let the normal reply flow run)."""
    text = ctx.user_text or ""
    conv = await db.conversations.find_one({"id": ctx.cid}, {"_id": 0, "pending_restore": 1}) or {}
    pending = conv.get("pending_restore")
    if pending:
        await db.conversations.update_one({"id": ctx.cid}, {"$set": {"pending_restore": None}})
        if YES_RE.search(text) or RESTORE_RE.search(text):
            r = await restore_archive(pending["id"], ctx.user)
            where = "ke chat ini — pesan lamanya kini tampil kembali di atas" if r["conversation_id"] == ctx.cid else f"ke percakapan asalnya: [buka percakapan](/chat/{r['conversation_id']})"
            return {"content": f"Siap — arsip **{r['title']}** ({r['restored']} pesan) sudah saya pulihkan {where} ✅.", "extra": {"tool": "archive_restored", "archive_id": pending["id"]}}
        if NO_RE.search(text):
            return {"content": "Baik, arsip tidak jadi dipulihkan. Ada lagi yang bisa saya bantu?", "extra": {"tool": "archive_cancel"}}
    if not ARCHIVE_RE.search(text):
        return None
    m = re.search(r"(?:nomor|no\.?|#)\s*(\d+)", text, re.I)
    want_restore = bool(RESTORE_RE.search(text))
    results = await search_archives(ctx.user, text, 5)
    if want_restore and results:
        idx = int(m.group(1)) - 1 if m else 0
        pick = results[idx] if 0 <= idx < len(results) else results[0]
        await db.conversations.update_one({"id": ctx.cid}, {"$set": {"pending_restore": {"id": pick["id"], "title": pick["title"]}}})
        return {"content": f"Saya menemukan arsip **{pick['title']}** ({_fmt_period(pick)}, {pick.get('message_count', 0)} pesan): {(pick.get('summary') or '')[:200]}…\n\n"
                           f"Pulihkan arsip ini {'ke chat ini' if pick.get('conversation_id') == ctx.cid else 'ke percakapan asalnya'} sekarang? Jawab **ya** untuk melanjutkan atau **tidak** untuk membatalkan.",
                "extra": {"tool": "archive_confirm", "pending_restore": {"id": pick["id"], "title": pick["title"]}, "results": results}}
    return {"content": archive_results_markdown(results, text[:60], False), "extra": {"tool": "archive_search", "results": results}}


class VoiceSearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=300)


@router.post("/conversations/{cid}/archive-search")
async def conv_archive_search(cid: str, x: VoiceSearchIn, u: dict = Depends(current_user)):
    conv = await db.conversations.find_one({"id": cid}, {"_id": 0})
    if not conv or not _can_access(conv, u):
        raise HTTPException(404, "Conversation not found")
    results = await search_archives(u, x.query, 5)
    persona = (await _get_personas([conv.get("persona_id") or (conv.get("persona_ids") or [None])[0]]) or [None])[0]
    if persona:
        await _save_ai_msg(cid, persona, archive_results_markdown(results, x.query, False), 0, "text", {"tool": "archive_search", "results": results})
    return {"count": len(results), "results": [{"id": a["id"], "title": a["title"], "period": _fmt_period(a), "messages": a.get("message_count", 0), "summary": (a.get("summary") or "")[:200]} for a in results]}


class VoiceRestoreIn(BaseModel):
    archive_id: str
    confirmed: bool = False


@router.post("/conversations/{cid}/archive-restore")
async def conv_archive_restore(cid: str, x: VoiceRestoreIn, u: dict = Depends(current_user)):
    """Voice tool: the assistant must have asked the user for confirmation first (confirmed=true)."""
    if not x.confirmed:
        return {"ok": False, "need_confirmation": True, "say": "Tanyakan dulu ke pengguna apakah arsip ini benar ingin dipulihkan, lalu panggil lagi dengan confirmed=true."}
    r = await restore_archive(x.archive_id, u)
    conv = await db.conversations.find_one({"id": cid}, {"_id": 0})
    persona = (await _get_personas([conv.get("persona_id") or (conv.get("persona_ids") or [None])[0]]) or [None])[0] if conv else None
    if persona:
        await _save_ai_msg(cid, persona, f"Arsip **{r['title']}** ({r['restored']} pesan) sudah dipulihkan ✅.", 0, "text", {"tool": "archive_restored", "archive_id": x.archive_id})
    return r

