from typing import Optional
import io
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from auth import current_user, current_user_q, workspace_id, lang_rule
from chat import _conv_title
from db import db, now_iso, new_id, clean
from llm import record_usage
from tools import TABLE_RE, build_docx, build_pdf, has_tables, save_revision, revise_with_llm

router = APIRouter(prefix="/api", tags=["workspace"])

def task_access(u: dict) -> dict:
    return {"$or": [{"user_id": u["id"]}, {"workspace_id": workspace_id(u)}]}


async def get_task_for(tid: str, u: dict) -> dict:
    t = await db.tasks.find_one({"id": tid, **task_access(u)}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Task not found")
    return t


def task_view(t: dict) -> dict:
    t = clean(t)
    t["has_tables"] = has_tables(t.get("final_output") or "")
    t["version"] = int(t.get("version") or 1)
    t["versions"] = [{k: v for k, v in x.items() if k != "content"} for x in (t.get("versions") or [])]
    return t


def _md_tables(md: str) -> list:
    tables, cur = [], []
    for line in (md or "").splitlines():
        if TABLE_RE.match(line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            cur.append(cells)
        elif cur:
            tables.append(cur); cur = []
    if cur:
        tables.append(cur)
    return tables


def build_xlsx(title: str, md: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook(); wb.remove(wb.active)
    for i, rows in enumerate(_md_tables(md), 1):
        ws = wb.create_sheet(f"Tabel {i}")
        for r, row in enumerate(rows, 1):
            for c, val in enumerate(row, 1):
                cell = ws.cell(row=r, column=c, value=val)
                if r == 1:
                    cell.font = Font(bold=True)
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(60, max(12, max(len(str(c.value or "")) for c in col) + 2))
    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue()


EXPORTS = {"docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", build_docx),
           "pdf": ("application/pdf", build_pdf),
           "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", build_xlsx),
           "md": ("text/markdown", lambda title, md: f"# {title}\n\n{md}".encode())}


@router.get("/tasks/{tid}/export/{fmt}")
async def export_task(tid: str, fmt: str, u: dict = Depends(current_user_q)):
    """Convert the text result on demand (nothing is pre-generated)."""
    if fmt not in EXPORTS:
        raise HTTPException(400, "Format tidak didukung")
    t = await get_task_for(tid, u)
    md = t.get("final_output") or ""
    if fmt == "xlsx" and not has_tables(md):
        raise HTTPException(400, "Hasil ini tidak memiliki tabel untuk diekspor ke Excel")
    mime, builder = EXPORTS[fmt]
    title = (t.get("goal") or "Hasil tugas")[:80]
    data = builder(title, md)
    safe = re.sub(r"[^\w\- ]+", "", title).strip().replace(" ", "-")[:40] or "hasil"
    return StreamingResponse(io.BytesIO(data), media_type=mime, headers={"Content-Disposition": f'attachment; filename="{safe}.{fmt}"'})


@router.get("/tasks/{tid}/versions/{ver}")
async def task_version(tid: str, ver: int, u: dict = Depends(current_user)):
    t = await get_task_for(tid, u)
    if ver == int(t.get("version") or 1):
        return {"version": ver, "content": t.get("final_output") or "", "created_at": t.get("updated_at")}
    v = next((x for x in t.get("versions") or [] if int(x.get("version")) == ver), None)
    if not v:
        raise HTTPException(404, "Versi tidak ditemukan")
    return v


class ReviseIn(BaseModel):
    instruction: str = Field(min_length=1, max_length=4000)


@router.post("/tasks/{tid}/revise")
async def revise_task(tid: str, x: ReviseIn, u: dict = Depends(current_user)):
    """Direct revision from the Workspace page (no chat)."""
    t = await get_task_for(tid, u)
    persona = await db.personas.find_one({"id": t.get("persona_id")}, {"_id": 0}) if t.get("persona_id") else None
    new_md, summary, used = await revise_with_llm(t, x.instruction, "You are a careful editor.\n\n" + lang_rule(u), t.get("model"))
    ver = await save_revision(t, new_md, summary or x.instruction, persona)
    await record_usage(u["id"], "task_revision", used, {"task_id": tid})
    return {"version": ver, "summary": summary, "credits_used": used}


@router.post("/tasks/{tid}/versions/{ver}/restore")
async def restore_version(tid: str, ver: int, u: dict = Depends(current_user)):
    """Non-destructive rollback: the old content is saved as a NEW version, history stays intact."""
    t = await get_task_for(tid, u)
    if ver == int(t.get("version") or 1):
        raise HTTPException(400, "Versi ini sudah yang terbaru")
    v = next((x for x in t.get("versions") or [] if int(x.get("version")) == ver), None)
    if not v:
        raise HTTPException(404, "Versi tidak ditemukan")
    persona = await db.personas.find_one({"id": t.get("persona_id")}, {"_id": 0}) if t.get("persona_id") else None
    new_ver = await save_revision(t, v.get("content") or "", f"Dikembalikan ke v{ver} oleh {u.get('name') or 'pengguna'}", persona)
    return {"version": new_ver, "restored_from": ver}


async def _task_personas(t: dict, u: dict) -> list:
    wid = workspace_id(u)
    ids = [p for p in [t.get("persona_id"), *(t.get("persona_ids") or [])] if p]
    personas = [p async for p in db.personas.find({"id": {"$in": ids}, "user_id": wid, "deleted": {"$ne": True}}, {"_id": 0})] if ids else []
    if not personas:
        first = await db.personas.find_one({"user_id": wid, "deleted": {"$ne": True}}, {"_id": 0}, sort=[("created_at", 1)])
        if not first:
            raise HTTPException(400, "Belum ada asisten di workspace ini")
        personas = [first]
        await db.tasks.update_one({"id": t["id"]}, {"$set": {"persona_id": first["id"], "persona_name": first["name"]}})
    return personas


async def _task_team(t: dict, u: dict) -> list:
    """Lead assistant + everyone who worked on sub-tasks."""
    personas = await _task_personas(t, u)
    sub_ids = [k["persona_id"] async for k in db.tasks.find({"parent_id": t["id"]}, {"_id": 0, "persona_id": 1}) if k.get("persona_id")]
    extra = [p async for p in db.personas.find({"id": {"$in": [i for i in sub_ids if i not in {x["id"] for x in personas}]}, "deleted": {"$ne": True}}, {"_id": 0})]
    return personas + extra


@router.get("/tasks/{tid}/chat-target")
async def chat_target(tid: str, u: dict = Depends(current_user)):
    """Who should the chat/call about this task involve, and does a matching group already exist?"""
    t = await get_task_for(tid, u)
    team = await _task_team(t, u)
    ids = sorted(p["id"] for p in team)
    out = {"personas": [{"id": p["id"], "name": p["name"], "portrait": p.get("portrait")} for p in team], "single": len(team) == 1, "default_title": (t.get("goal") or "Grup tugas")[:60]}
    if len(team) > 1:
        q = {"user_id": u["id"], "type": {"$in": ["group", "meeting"]}, "archived_conv": {"$ne": True}}
        groups = await db.conversations.find(q, {"_id": 0, "id": 1, "title": 1, "persona_ids": 1, "task_id": 1}).sort("updated_at", -1).to_list(200)
        exact = [g for g in groups if sorted(g.get("persona_ids") or []) == ids]
        out["group"] = exact[0] if exact else None
        out["other_groups"] = [g for g in groups if not exact or g["id"] != exact[0]["id"]][:10]
    return out


class DiscussIn(BaseModel):
    mode: str = Field(pattern="^(chat|call|meeting)$")
    conversation_id: Optional[str] = None  # reuse this group
    group_title: Optional[str] = Field(default=None, max_length=80)  # create a new group with these members
    persona_ids: Optional[list] = None


@router.post("/tasks/{tid}/discuss")
async def discuss_task(tid: str, x: DiscussIn, u: dict = Depends(current_user)):
    """Attach the task as shared context to the assistant's chat (single) or to a group (existing or newly created), then open it."""
    t = await get_task_for(tid, u)
    team = await _task_team(t, u)
    conv = None
    if x.conversation_id:
        conv = await db.conversations.find_one({"id": x.conversation_id, "user_id": u["id"], "archived_conv": {"$ne": True}}, {"_id": 0})
        if not conv:
            raise HTTPException(404, "Grup tidak ditemukan")
    elif len(team) == 1 and not x.persona_ids:
        from chat import direct_conv, DirectIn
        conv = await direct_conv(DirectIn(persona_id=team[0]["id"]), u)
    else:
        wanted = set(x.persona_ids or [p["id"] for p in team])
        members = [p for p in team if p["id"] in wanted] or team
        if len(members) == 1:
            from chat import direct_conv, DirectIn
            conv = await direct_conv(DirectIn(persona_id=members[0]["id"]), u)
        else:
            conv = {"id": new_id(), "user_id": u["id"], "workspace_id": workspace_id(u), "participants": [u["id"]], "type": "group",
                    "persona_ids": [p["id"] for p in members], "persona_id": members[0]["id"],
                    "members": [{"id": p["id"], "name": p["name"], "portrait": p.get("portrait"), "voice": p.get("voice", "alloy")} for p in members],
                    "title": (x.group_title or "").strip() or (t.get("goal") or "Grup tugas")[:60], "created_at": now_iso(), "updated_at": now_iso(), "last_message": ""}
            await db.conversations.insert_one(dict(conv))
    await db.conversations.update_one({"id": conv["id"]}, {"$set": {"task_id": tid, "updated_at": now_iso()}})
    await db.tasks.update_one({"id": tid}, {"$addToSet": {"conversation_ids": conv["id"]}})
    await _quote_task_into_chat(conv, t, u, team, x.mode)
    return {"conversation_id": conv["id"], "open_call": x.mode in ("call", "meeting")}


async def _quote_task_into_chat(conv: dict, t: dict, u: dict, team: list, mode: str) -> None:
    """Drop the Workspace document into the chat as a quoted message, then the assistant confirms it has read the FULL content (so revisions can start right away)."""
    from chat import _persona_system, _save_ai_msg
    from llm import llm_text, record_usage, text_credits
    from auth import lang_rule
    from realtime import notify
    body = (t.get("final_output") or "").strip()
    excerpt = body.replace("#", "").replace("**", "").strip()[:400] or "(belum ada hasil)"
    user_msg = {"id": new_id(), "conversation_id": conv["id"], "role": "user", "sender_user_id": u["id"], "sender_name": u.get("name") or "User", "created_at": now_iso(),
                "content": "Ini dokumen dari Ruang Kerja. Tolong baca isinya secara lengkap; kalau nanti saya minta revisi, langsung ubah dan simpan versi barunya.",
                "reply_to": {"id": t["id"], "name": f"Ruang Kerja · {t.get('goal') or 'Dokumen'} (v{t.get('version') or 1})", "content": excerpt, "link": f"/workspace/{t['id']}"},
                "attachments": [{"type": "file", "name": (t.get("goal") or "Dokumen")[:80], "task_id": t["id"]}], "task_quote": True}
    await db.messages.insert_one(dict(user_msg))
    await notify(conv["id"], {"type": "message", "role": "user", "sender_name": user_msg["sender_name"], "message": clean(user_msg)})
    if mode != "chat" or not team or not body:
        return
    persona = await db.personas.find_one({"id": team[0]["id"]}, {"_id": 0}) or team[0]
    system = (await _persona_system(persona, u, None) +
              "\n\nThe user just dropped a Workspace document into this chat (full text below). Reply in 2-4 short sentences: confirm you have read it, name its title and the 2-3 key points it contains, "
              "and say they can ask for any revision and you will update it directly in the Workspace. No long summary, no list.\n\n" + lang_rule(u))
    prompt = f"WORKSPACE DOCUMENT (version {t.get('version') or 1}) — '{t.get('goal')}':\n{body[:24000]}"
    try:
        text = await llm_text(system, prompt, persona.get("model"))
    except Exception:
        text = f"Dokumen **{t.get('goal')}** sudah saya baca. Sebutkan saja bagian yang mau direvisi, nanti langsung saya ubah dan simpan di Ruang Kerja."
    used = text_credits(prompt, text, persona.get("model"))
    if used:
        await record_usage(u["id"], "chat", used, {"conversation_id": conv["id"], "persona_id": persona.get("id"), "task_id": t["id"]})
    await _save_ai_msg(conv["id"], persona, text, used, "text", {"task_id": t["id"]})


class AddPersonaIn(BaseModel):
    persona_id: str


@router.post("/conversations/{cid}/personas")
async def add_persona(cid: str, x: AddPersonaIn, u: dict = Depends(current_user)):
    """Invite another assistant into an existing chat/meeting."""
    conv = await db.conversations.find_one({"id": cid, "$or": [{"workspace_id": workspace_id(u)}, {"participants": u["id"]}]}, {"_id": 0})
    if not conv:
        raise HTTPException(404, "Conversation not found")
    p = await db.personas.find_one({"id": x.persona_id, "user_id": workspace_id(u), "deleted": {"$ne": True}}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Asisten tidak ditemukan")
    if p["id"] in (conv.get("persona_ids") or []):
        raise HTTPException(409, "Asisten sudah ada di percakapan ini")
    members = (conv.get("members") or []) + [{"id": p["id"], "name": p["name"], "portrait": p.get("portrait"), "voice": p.get("voice", "alloy")}]
    ctype = "group" if conv.get("type") == "private" else conv.get("type")
    upd = {"members": members, "type": ctype, "updated_at": now_iso()}
    if not conv.get("persona_id"):
        upd["persona_id"] = p["id"]
    if conv.get("type") == "private":
        upd["title"] = _conv_title("group", [{"name": m["name"]} for m in members])
    await db.conversations.update_one({"id": cid}, {"$addToSet": {"persona_ids": p["id"]}, "$set": upd})
    await db.messages.insert_one({"id": new_id(), "conversation_id": cid, "role": "assistant", "content": f"👋 **{p['name']}** bergabung ke percakapan.",
                                  "persona_id": "__system__", "persona_name": "Sistem", "is_summary": True, "portrait": None, "credits": 0, "created_at": now_iso()})
    return clean(await db.conversations.find_one({"id": cid}, {"_id": 0}))


class AddMembersIn(BaseModel):
    persona_ids: list[str] = Field(default_factory=list, max_length=10)
    friend_ids: list[str] = Field(default_factory=list, max_length=10)


@router.post("/conversations/{cid}/members")
async def add_members(cid: str, x: AddMembersIn, u: dict = Depends(current_user)):
    """Host invites friends and/or assistants into a running chat or call. A private/DM chat becomes a group."""
    from datetime import datetime, timezone, timedelta
    from chat import _fanout_message
    from friends import friend_ids
    from push import send_push
    from realtime import notify, notify_users
    from rtc import CALL_TTL_SEC
    conv = await db.conversations.find_one({"id": cid}, {"_id": 0})
    if not conv or not (conv.get("user_id") == u["id"] or u["id"] in (conv.get("participants") or [])):
        raise HTTPException(404, "Conversation not found")
    if conv.get("user_id") != u["id"]:
        raise HTTPException(403, "Hanya host (pemulai percakapan) yang bisa mengundang")
    have_p = set(conv.get("persona_ids") or [])
    personas = [p async for p in db.personas.find({"id": {"$in": [i for i in x.persona_ids if i not in have_p]}, "user_id": workspace_id(u), "deleted": {"$ne": True}}, {"_id": 0})]
    have_h = set(conv.get("participants") or [])
    allowed = set(await friend_ids(u["id"]))
    new_ids = [i for i in dict.fromkeys(x.friend_ids) if i in allowed and i not in have_h]
    new_humans = [h async for h in db.users.find({"id": {"$in": new_ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1, "avatar": 1})]
    if not personas and not new_humans:
        raise HTTPException(400, "Tidak ada teman atau asisten baru untuk diundang")
    new_members = [{"id": p["id"], "name": p["name"], "portrait": p.get("portrait"), "voice": p.get("voice", "alloy")} for p in personas]
    members = (conv.get("members") or []) + new_members
    participants = (conv.get("participants") or [u["id"]]) + [h["id"] for h in new_humans]
    upd = {"updated_at": now_iso()}
    if not conv.get("persona_id") and members:
        upd["persona_id"] = members[0]["id"]
    if conv.get("type") in ("private", "dm"):
        upd["type"] = "group"
        upd["title"] = _conv_title("group", members) if members else "Grup " + ", ".join(h["name"] for h in new_humans)
    # atomic merges so a concurrent add_persona/add_members cannot clobber each other's roster
    await db.conversations.update_one({"id": cid}, {"$set": upd, "$unset": {"titles": ""},
                                                     "$addToSet": {"persona_ids": {"$each": [p["id"] for p in personas]}, "members": {"$each": new_members},
                                                                   "participants": {"$each": [h["id"] for h in new_humans]}}})
    fresh = await db.conversations.find_one({"id": cid}, {"_id": 0, "participants": 1}) or {}
    all_parts = fresh.get("participants") or participants
    humans = [h async for h in db.users.find({"id": {"$in": all_parts}}, {"_id": 0, "id": 1, "name": 1, "email": 1, "avatar": 1})] if len(all_parts) > 1 else []
    await db.conversations.update_one({"id": cid}, {"$set": {"humans": humans}})
    names = ", ".join([f"**{h['name']}**" for h in new_humans] + [f"**{p['name']}**" for p in personas])
    text = f"👋 {u.get('name') or 'Host'} mengundang {names} ke percakapan."
    await db.messages.insert_one({"id": new_id(), "conversation_id": cid, "role": "assistant", "content": text, "persona_id": "__system__", "persona_name": "Sistem",
                                  "is_summary": True, "portrait": None, "credits": 0, "created_at": now_iso()})
    await _fanout_message(cid, u["id"], u.get("name") or "Host", text.replace("**", ""))
    await notify(cid, {"type": "participants", "conversation_id": cid})
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=CALL_TTL_SEC)).isoformat()
    live = any((v.get("at") or "") > cutoff for v in (conv.get("active_call") or {}).values())
    if live and new_humans:  # call already running → ring the newcomers right away
        title = upd.get("title") or conv.get("title")
        await notify_users([h["id"] for h in new_humans], {"type": "incoming_call", "conversation_id": cid, "from_name": u.get("name") or "Teman", "title": title})
        for h in new_humans:
            await send_push(h["id"], f"Panggilan masuk dari {u.get('name') or 'teman'}", title or "Ketuk untuk bergabung", {"link": f"/chat/{cid}", "tag": f"call-{cid}"}, kind="calls")
    return clean(await db.conversations.find_one({"id": cid}, {"_id": 0}))
