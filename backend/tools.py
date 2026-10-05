import io
import os
import re
import base64
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from db import db, now_iso, new_id
from auth import require_platform_admin
from llm import llm_text, llm_json, generate_image, text_credits, _MODEL_BY_ID, model_label
from pricing import rate
from storage import put_object

router = APIRouter(prefix="/api", tags=["tools"])

DEFAULT_ROUTING = {"enabled": True, "it_model": "claude-sonnet", "research_model": "gemini-pro", "confirm_threshold": 20}
_routing_cache = {"doc": None, "at": 0.0}

IT_RE = re.compile(r"\b(kode|code|coding|bug|error|exception|stack ?trace|python|javascript|typescript|react|node|sql|query|api|endpoint|server|deploy|docker|kubernetes|database|regex|git|html|css|fungsi|function|script|debug|compile|library|framework|algoritma|algorithm|json|yaml|linux|terminal|command|npm|pip)\b", re.I)
RESEARCH_RE = re.compile(r"\b(riset|research|penelitian|analisis mendalam|analisa mendalam|literatur|kajian|bandingkan secara|studi kasus|laporan lengkap|ringkas(kan)? dokumen|whitepaper|jurnal|tinjauan)\b", re.I)
TOOL_RE = re.compile(r"\b(gambar|image|ilustrasi|foto|logo|poster|banner|visual|sketsa|lukisan|dokumen|document|laporan|proposal|docx|pdf|word|file|surat|artikel|template|makalah|ringkasan tertulis|notulen)\b", re.I)
CREATE_RE = re.compile(r"\b(buat|buatkan|bikin|bikinkan|generate|tolong buat|susun|susunkan|tuliskan|rancang|desain|design|create|make|draw|gambarkan|ekspor|export|unduh|download)\b", re.I)


async def get_routing() -> dict:
    import time
    if _routing_cache["doc"] and time.time() - _routing_cache["at"] < 30:
        return _routing_cache["doc"]
    cfg = await db.config.find_one({"id": "model_routing"}, {"_id": 0, "id": 0, "updated_at": 0}) or {}
    doc = {**DEFAULT_ROUTING, **cfg}
    _routing_cache.update(doc=doc, at=time.time())
    return doc


class RoutingIn(BaseModel):
    enabled: bool = True
    it_model: str = Field(pattern="^[a-z0-9-]+$")
    research_model: str = Field(pattern="^[a-z0-9-]+$")
    confirm_threshold: int = Field(ge=0, le=1000)


@router.get("/admin/model-routing")
async def admin_get_routing(_: dict = Depends(require_platform_admin)):
    return {**(await get_routing()), "models": [{"id": m["id"], "label": m["label"]} for m in _MODEL_BY_ID.values()]}


@router.put("/admin/model-routing")
async def admin_set_routing(x: RoutingIn, _: dict = Depends(require_platform_admin)):
    doc = x.model_dump()
    if doc["it_model"] not in _MODEL_BY_ID or doc["research_model"] not in _MODEL_BY_ID:
        from fastapi import HTTPException
        raise HTTPException(400, "Model tidak dikenal")
    await db.config.update_one({"id": "model_routing"}, {"$set": {**doc, "updated_at": now_iso()}}, upsert=True)
    _routing_cache["doc"] = None
    return await admin_get_routing(_)


async def route_model(persona_model: Optional[str], text: str, extra_len: int, owner_settings: dict):
    """Pick the best model for this turn while the persona stays the same. Returns (model_key, reason|None)."""
    cfg = await get_routing()
    if not cfg["enabled"] or not (owner_settings or {}).get("smart_routing", True):
        return persona_model, None
    t = text or ""
    if IT_RE.search(t) or "```" in t:
        return cfg["it_model"], "it"
    if RESEARCH_RE.search(t) or len(t) + extra_len > 3500:
        return cfg["research_model"], "research"
    return persona_model, None


DRIVE_RE = re.compile(r"\b(google ?drive|drive|gdrive|google ?docs?|spreadsheet|google ?sheets?)\b", re.I)


def wants_tool(text: str) -> bool:
    return bool(text) and ((bool(TOOL_RE.search(text)) and bool(CREATE_RE.search(text))) or bool(DRIVE_RE.search(text)))


async def plan_tool(text: str, history: str) -> dict:
    sys = ('Decide if the user\'s LAST message explicitly asks the assistant to CREATE a deliverable. Reply JSON only: '
           '{"tool":"image"|"document"|"drive_save"|"drive_update"|"drive_link"|"none","image_prompt":str,"title":str,"instructions":str,"file":str,"text":str,"mode":"append"|"replace","kind":"doc"|"sheet"}. '
           '"image" = the user wants a picture/illustration/logo/poster generated. "document" = the user wants a written file '
           '(report, proposal, letter, article, notulen, template) they can download. Otherwise "none" (questions, explanations, '
           'tables shown inline, code snippets are NOT documents). image_prompt: detailed English prompt for an image model. '
           'title: short document title in the user\'s language. instructions: what the document must contain. '
           '"drive_save" = user asks to save/store something (the current document, a table, the discussed content) to Google Drive/Docs/Sheets '
           '(kind "sheet" when they want a spreadsheet, else "doc"; text = the content to save if they described it). '
           '"drive_update" = user asks to update/edit/append to an existing Google Doc on Drive (file = document name or id as the user said it; '
           'text = the exact content to add/write; mode "replace" only if they want to overwrite). '
           '"drive_link" = user asks for the Drive link of a document (file = name).')
    plan: dict = {}
    try:
        plan = await llm_json(sys, f"Recent conversation:\n{history[-2500:]}\n\nLAST MESSAGE: {text}")
    except Exception:
        plan = {}
    if plan.get("tool") not in ("image", "document", "drive_save", "drive_update", "drive_link"):
        return {"tool": "none"}
    return plan


def _md_blocks(md: str):
    for raw in md.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            yield ("blank", "")
        elif line.startswith("```"):
            yield ("fence", "")
        elif re.match(r"^#{1,3}\s", line):
            yield ("h%d" % len(re.match(r"^#+", line).group()), re.sub(r"^#+\s", "", line))
        elif re.match(r"^\s*[-*]\s", line):
            yield ("li", re.sub(r"^\s*[-*]\s", "", line))
        elif re.match(r"^\s*\d+\.\s", line):
            yield ("li", re.sub(r"^\s*", "", line))
        elif re.match(r"^\s*\|.*\|\s*$", line):
            if not re.match(r"^\s*\|[\s:|-]+\|\s*$", line):
                yield ("row", [c.strip() for c in line.strip()[1:-1].split("|")])
        else:
            yield ("p", line)


_inline = re.compile(r"\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`")


def _plain(s: str) -> str:
    return _inline.sub(lambda m: m.group(1) or m.group(2) or m.group(3), s)


def build_docx(title: str, md: str) -> bytes:
    from docx import Document
    doc = Document()
    doc.add_heading(title, 0)
    table_rows = []

    def flush_table():
        if not table_rows:
            return
        t = doc.add_table(rows=0, cols=max(len(r) for r in table_rows))
        t.style = "Table Grid"
        for r in table_rows:
            cells = t.add_row().cells
            for i, c in enumerate(r):
                cells[i].text = _plain(c)
        table_rows.clear()

    for kind, val in _md_blocks(md):
        if kind != "row":
            flush_table()
        if kind == "row":
            table_rows.append(val)
        elif kind.startswith("h"):
            doc.add_heading(_plain(val), int(kind[1]))
        elif kind == "li":
            doc.add_paragraph(_plain(val), style="List Bullet")
        elif kind == "p":
            doc.add_paragraph(_plain(val))
    flush_table()
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def build_pdf(title: str, md: str) -> bytes:
    from fpdf import FPDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    reg, bold = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    fam = "Helvetica"
    if os.path.exists(reg):
        pdf.add_font("Lib", "", reg)
        pdf.add_font("Lib", "B", bold if os.path.exists(bold) else reg)
        fam = "Lib"
    w = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_font(fam, "B", 18)
    pdf.multi_cell(w, 9, title)
    pdf.ln(2)
    rows = []

    def flush_rows():
        if not rows:
            return
        cols = max(len(r) for r in rows)
        cw = w / cols
        for ri, r in enumerate(rows):
            pdf.set_font(fam, "B" if ri == 0 else "", 9)
            cells = [_plain(r[i]) if i < len(r) else "" for i in range(cols)]
            h = 5 * max(1, max(len(pdf.multi_cell(cw - 2, 5, c, dry_run=True, output="LINES")) for c in cells))
            if pdf.get_y() + h > pdf.page_break_trigger:
                pdf.add_page()
            y0 = pdf.get_y()
            for i, c in enumerate(cells):
                x = pdf.l_margin + i * cw
                pdf.rect(x, y0, cw, h)
                pdf.set_xy(x + 1, y0)
                pdf.multi_cell(cw - 2, 5, c, border=0, new_x="RIGHT", new_y="TOP")
            pdf.set_xy(pdf.l_margin, y0 + h)
        rows.clear()
        pdf.ln(2)

    for kind, val in _md_blocks(md):
        if kind != "row":
            flush_rows()
        if kind == "row":
            rows.append(val)
        elif kind.startswith("h"):
            pdf.ln(2)
            pdf.set_font(fam, "B", {1: 15, 2: 13, 3: 11}[int(kind[1])])
            pdf.multi_cell(w, 7, _plain(val))
        elif kind == "li":
            pdf.set_font(fam, "", 10.5)
            pdf.multi_cell(w, 6, "•  " + _plain(val))
        elif kind == "p":
            pdf.set_font(fam, "", 10.5)
            pdf.multi_cell(w, 6, _plain(val))
        elif kind == "blank":
            pdf.ln(2)
    flush_rows()
    return bytes(pdf.output())


def _safe_name(title: str) -> str:
    s = re.sub(r"[^\w\- ]+", "", title or "dokumen").strip().replace(" ", "_")
    return (s or "dokumen")[:60]


async def run_image_tool(uid: str, prompt: str) -> dict:
    data_url = await generate_image(prompt)
    if not data_url:
        raise RuntimeError("image generation returned nothing")
    header, b64 = data_url.split(",", 1)
    mime = header.split(":")[1].split(";")[0]
    ext = "png" if "png" in mime else "jpg"
    path = f"aivora/images/{uid}/{new_id()}.{ext}"
    from integrations import assert_quota, add_storage
    raw = base64.b64decode(b64)
    await assert_quota(uid, len(raw))
    await asyncio.to_thread(put_object, path, raw, mime)
    await add_storage(uid, len(raw))
    return {"media": [{"type": "image", "path": path, "name": f"gambar.{ext}"}], "credits": rate("image")}


async def run_document_tool(uid: str, system: str, title: str, instructions: str, history: str, model_key: Optional[str]) -> dict:
    sys = system + ("\n\nDOCUMENT MODE: write the COMPLETE document content in well-structured markdown (headings, lists, tables "
                    "where useful). No preface, no closing chit-chat — only the document body.")
    prompt = f"Context:\n{history[-3000:]}\n\nDocument title: {title}\nRequirements: {instructions}\n\nWrite the full document now."
    md = await llm_text(sys, prompt, model_key)
    base = _safe_name(title)
    docx_b, pdf_b = await asyncio.gather(asyncio.to_thread(build_docx, title, md), asyncio.to_thread(build_pdf, title, md))
    did = new_id()
    files = [("docx", docx_b, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
             ("pdf", pdf_b, "application/pdf"), ("md", md.encode("utf-8"), "text/markdown")]
    media = []
    from integrations import assert_quota, add_storage
    await assert_quota(uid, sum(len(d) for _, d, _ in files))
    for ext, data, ctype in files:
        path = f"aivora/docs/{uid}/{did}/{base}.{ext}"
        await asyncio.to_thread(put_object, path, data, ctype)
        await add_storage(uid, len(data))
        media.append({"type": "file", "path": path, "name": f"{base}.{ext}", "format": ext})
    return {"media": media, "credits": text_credits(prompt, md), "markdown": md, "model_label": model_label(model_key)}


# ---------- workspace tasks: shared context & revisions ----------
TABLE_RE = re.compile(r"^\s*\|.+\|\s*$", re.M)
TASK_CONTEXT = ("\n\nWORKSPACE TASK UNDER DISCUSSION (id {tid}, version {ver}, status {status}; the ONLY valid link to it is /workspace/{tid} — never invent other URLs):\nTitle: {goal}\n--- CURRENT RESULT ---\n{body}\n--- END ---\n"
                "The user may ask questions about this result or request changes. Discuss it in context; when they ask for a change, the system "
                "saves a revised version to the Workspace automatically — confirm briefly what changed.")
REVISE_RE = re.compile(r"\b(revisi|ubah|ganti|perbaiki|tambah(kan)?|hapus|kurangi|perbarui|update|rapikan|singkat|perpanjang|sesuaikan|koreksi|edit|rewrite|revise|change|tulis ulang)\b", re.I)


def has_tables(md: str) -> bool:
    return len(TABLE_RE.findall(md or "")) >= 2



async def save_revision(task: dict, new_md: str, note: str, persona: Optional[dict]) -> int:
    """Archive the current result as a version and store the revised text. Returns the new version number."""
    cur = int(task.get("version") or 1)
    old = {"version": cur, "content": task.get("final_output") or "", "created_at": task.get("updated_at") or task.get("created_at"), "note": task.get("revision_note") or "Versi awal"}
    await db.tasks.update_one({"id": task["id"]}, {"$push": {"versions": old},
                                                   "$set": {"final_output": new_md, "version": cur + 1, "revision_note": note[:300], "updated_at": now_iso(),
                                                            "status": "completed", **({"persona_id": persona["id"], "persona_name": persona["name"]} if persona else {})}})
    return cur + 1


async def revise_with_llm(task: dict, request: str, system: str, model_key: Optional[str]) -> tuple:
    """Returns (new_markdown, change_summary, credits)."""
    sys = system + ("\n\nYou are REVISING a workspace deliverable. Output the COMPLETE revised document in markdown (keep everything that was "
                    "not asked to change), then on the very last line write exactly: RINGKASAN PERUBAHAN: <1-2 sentences>.")
    prompt = f"CURRENT DOCUMENT:\n{(task.get('final_output') or '')[:15000]}\n\nREVISION REQUEST: {request}"
    out = await llm_text(sys, prompt, model_key)
    summary = ""
    if "RINGKASAN PERUBAHAN:" in out:
        out, summary = out.rsplit("RINGKASAN PERUBAHAN:", 1)
    return out.strip(), summary.strip(), text_credits(prompt, out)




# ---------- task assignment from chat / meeting ----------
TASK_RE = re.compile(r"\b(tolong|bisa|minta|buatkan|buatlah|kerjakan|susun(kan)?|siapkan|rancang|analisis|analisa|riset|teliti|rangkum|ringkas|terjemahkan|"
                     r"laporan|proposal|rencana|roadmap|strategi|artikel|esai|modul|kurikulum|presentasi|jadwalkan|nanti|besok|lusa|minggu depan|jam \d|pukul \d|deadline|tenggat)\b", re.I)
OFFER_TEXT = ("Siap, {uname}! Tugas ini cukup besar: **{title}**.\n\nMau kita **bahas satu per satu** di sini, atau **terima beres** saja? "
              "Kalau terima beres, tugas saya masukkan ke Ruang Kerja dan kerjakan {when}; setelah selesai saya kabari di chat ini, dan Anda bisa buat panggilan supaya saya paparkan hasilnya.")


async def plan_task(text: str, tz: str, history: str = "") -> dict:
    """Decide whether the message delegates a (long) piece of work and when it should be done."""
    if not TASK_RE.search(text or "") or len(text) < 25:
        return {"is_task": False}
    from zoneinfo import ZoneInfo
    from datetime import datetime
    try:
        now = datetime.now(ZoneInfo(tz or "Asia/Jakarta"))
    except Exception:
        now = datetime.now(ZoneInfo("Asia/Jakarta"))
    try:
        r = await llm_json(
            "You classify whether a user's chat message DELEGATES work to the assistant (a deliverable: document, plan, analysis, research, report, "
            "code module, etc.) versus a quick question. Reply JSON only: {\"is_task\": bool, \"long\": bool, \"title\": str, \"brief\": str, \"scheduled_at\": str|null}. "
            "long=true when the deliverable needs more than ~2 paragraphs of real work. title: short Indonesian title (max 10 words). brief: 1-3 sentences "
            "restating exactly what must be produced. scheduled_at: ISO-8601 with timezone offset if the user names a time/day to do it (e.g. 'besok jam 9', "
            "'Senin depan'), else null.",
            f"Now: {now.isoformat()} ({tz}).\nRecent context: {history[-600:]}\nUser message: {text}")
    except Exception:
        return {"is_task": False}
    return r if isinstance(r, dict) else {"is_task": False}
