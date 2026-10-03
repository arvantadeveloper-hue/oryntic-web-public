import io
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from auth import current_user, current_user_q, workspace_id
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
    new_md, summary, used = await revise_with_llm(t, x.instruction, "You are a careful editor.", t.get("model"))
    ver = await save_revision(t, new_md, summary or x.instruction, persona)
    await record_usage(u["id"], "task_revision", used, {"task_id": tid})
    return {"version": ver, "summary": summary, "credits_used": used}


class DiscussIn(BaseModel):
    mode: str = Field(pattern="^(chat|call|meeting)$")


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


@router.post("/tasks/{tid}/discuss")
async def discuss_task(tid: str, x: DiscussIn, u: dict = Depends(current_user)):
    """Open (or reuse) a conversation with the task's assistant(s); the task becomes the shared context."""
    t = await get_task_for(tid, u)
    personas = await _task_personas(t, u)
    ctype = "meeting" if x.mode == "meeting" else "private"
    if ctype == "private":
        personas = personas[:1]
    q = {"task_id": tid, "type": ctype, "user_id": u["id"], "persona_ids": [p["id"] for p in personas]}
    conv = await db.conversations.find_one(q, {"_id": 0})
    if not conv:
        conv = {"id": new_id(), "user_id": u["id"], "workspace_id": workspace_id(u), "participants": [u["id"]], "type": ctype,
                "persona_ids": [p["id"] for p in personas], "persona_id": personas[0]["id"], "task_id": tid,
                "members": [{"id": p["id"], "name": p["name"], "portrait": p.get("portrait"), "voice": p.get("voice", "alloy")} for p in personas],
                "title": f"{'Panggilan' if ctype == 'meeting' else 'Diskusi'}: {(t.get('goal') or '')[:60]}", "created_at": now_iso(), "updated_at": now_iso(), "last_message": ""}
        await db.conversations.insert_one(dict(conv))
        await db.tasks.update_one({"id": tid}, {"$addToSet": {"conversation_ids": conv["id"]}})
    return {"conversation_id": conv["id"], "open_call": x.mode in ("call", "meeting")}


class AddPersonaIn(BaseModel):
    persona_id: str


@router.post("/conversations/{cid}/personas")
async def add_persona(cid: str, x: AddPersonaIn, u: dict = Depends(current_user)):
    """Invite another assistant into an existing chat/meeting."""
    conv = await db.conversations.find_one({"id": cid, "workspace_id": workspace_id(u)}, {"_id": 0})
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
    if conv.get("type") == "private":
        upd["title"] = _conv_title("group", [{"name": m["name"]} for m in members])
    await db.conversations.update_one({"id": cid}, {"$addToSet": {"persona_ids": p["id"]}, "$set": upd})
    await db.messages.insert_one({"id": new_id(), "conversation_id": cid, "role": "assistant", "content": f"👋 **{p['name']}** bergabung ke percakapan.",
                                  "persona_id": "__system__", "persona_name": "Sistem", "is_summary": True, "portrait": None, "credits": 0, "created_at": now_iso()})
    return clean(await db.conversations.find_one({"id": cid}, {"_id": 0}))
