import base64
import io
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import current_user, workspace_id
from db import db, now_iso, new_id

router = APIRouter(prefix="/api", tags=["knowledge"])
MAX_BYTES = 8 * 1024 * 1024
MAX_CHARS = 200_000
CHUNK = 800
STOP = set("yang dan di ke dari untuk dengan pada adalah ini itu atau juga akan tidak ada sebagai oleh dalam the and for with that this from are was were have has not you your".split())


def _kw(text: str) -> set:
    return {w for w in re.findall(r"[a-zA-Z0-9\u00C0-\u024F]{3,}", (text or "").lower()) if w not in STOP}


def _html_to_text(html: str) -> str:
    t = re.sub(r"<(br|/p|/div|/li|/h[1-6])[^>]*>", "\n", html or "", flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _extract(name: str, data_b64: str) -> str:
    raw = base64.b64decode(data_b64.split(",")[-1])
    if len(raw) > MAX_BYTES:
        raise HTTPException(400, "Berkas lebih dari 8 MB")
    ext = (name or "").rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(raw)).pages)
    if ext == "docx":
        from docx import Document
        return "\n".join(p.text for p in Document(io.BytesIO(raw)).paragraphs)
    if ext in ("txt", "md", "markdown", "csv", "json", "html", "htm"):
        txt = raw.decode("utf-8", "ignore")
        return _html_to_text(txt) if ext in ("html", "htm") else txt
    raise HTTPException(400, "Format tidak didukung (PDF, Word, TXT, MD)")


def _chunks(text: str) -> list:
    text = re.sub(r"[ \t]+", " ", text)[:MAX_CHARS].strip()
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n(?=#)", text) if p.strip()]
    out, buf = [], ""
    for p in paras:
        if len(buf) + len(p) + 1 <= CHUNK:
            buf = f"{buf}\n{p}".strip()
        else:
            if buf:
                out.append(buf)
            while len(p) > CHUNK:
                out.append(p[:CHUNK]); p = p[CHUNK:]
            buf = p
    if buf:
        out.append(buf)
    return [{"i": i, "text": c, "kw": sorted(_kw(c))} for i, c in enumerate(out)]


class KnowledgeIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    html: Optional[str] = Field(default=None, max_length=400_000)
    text: Optional[str] = Field(default=None, max_length=MAX_CHARS)
    file_name: Optional[str] = None
    file_data: Optional[str] = None  # base64


async def _persona_of(pid: str, u: dict) -> dict:
    p = await db.personas.find_one({"id": pid, "user_id": workspace_id(u), "deleted": {"$ne": True}}, {"_id": 0, "id": 1, "user_id": 1})
    if not p:
        raise HTTPException(404, "Asisten tidak ditemukan")
    return p


def _pub(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "chunks"} | {"chunk_count": len(d.get("chunks") or [])}


@router.get("/personas/{pid}/knowledge")
async def list_knowledge(pid: str, u: dict = Depends(current_user)):
    await _persona_of(pid, u)
    return [_pub(d) async for d in db.knowledge_docs.find({"persona_id": pid}, {"_id": 0}).sort("created_at", -1)]


@router.post("/personas/{pid}/knowledge")
async def add_knowledge(pid: str, x: KnowledgeIn, u: dict = Depends(current_user)):
    """Reference knowledge for an assistant (upload or editor). Never 'priority': only the few chunks relevant to a message are injected."""
    p = await _persona_of(pid, u)
    if x.file_data:
        text, source, html = _extract(x.file_name or "", x.file_data), "upload", None
    elif x.html:
        text, source, html = _html_to_text(x.html), "editor", x.html
    else:
        text, source, html = x.text or "", "editor", None
    if len(text.strip()) < 20:
        raise HTTPException(400, "Isi dokumen terlalu pendek atau tidak terbaca")
    doc = {"id": new_id(), "user_id": p["user_id"], "persona_id": pid, "title": x.title.strip(), "source": source, "file_name": x.file_name, "html": html,
           "chars": len(text), "chunks": _chunks(text), "enabled": True, "created_at": now_iso(), "updated_at": now_iso()}
    await db.knowledge_docs.insert_one(dict(doc))
    return _pub(doc)


class KnowledgeUpdate(BaseModel):
    enabled: Optional[bool] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=160)
    html: Optional[str] = Field(default=None, max_length=400_000)


@router.put("/personas/{pid}/knowledge/{kid}")
async def update_knowledge(pid: str, kid: str, x: KnowledgeUpdate, u: dict = Depends(current_user)):
    await _persona_of(pid, u)
    fields = {"updated_at": now_iso()}
    if x.enabled is not None:
        fields["enabled"] = x.enabled
    if x.title:
        fields["title"] = x.title.strip()
    if x.html is not None:
        text = _html_to_text(x.html)
        fields.update({"html": x.html, "chars": len(text), "chunks": _chunks(text)})
    r = await db.knowledge_docs.find_one_and_update({"id": kid, "persona_id": pid}, {"$set": fields}, projection={"_id": 0}, return_document=True)
    if not r:
        raise HTTPException(404, "Dokumen tidak ditemukan")
    return _pub(r)


@router.get("/personas/{pid}/knowledge/{kid}")
async def get_knowledge(pid: str, kid: str, u: dict = Depends(current_user)):
    await _persona_of(pid, u)
    d = await db.knowledge_docs.find_one({"id": kid, "persona_id": pid}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Dokumen tidak ditemukan")
    return {**_pub(d), "text": "\n\n".join(c["text"] for c in d.get("chunks") or [])}


@router.delete("/personas/{pid}/knowledge/{kid}")
async def delete_knowledge(pid: str, kid: str, u: dict = Depends(current_user)):
    await _persona_of(pid, u)
    await db.knowledge_docs.delete_one({"id": kid, "persona_id": pid})
    return {"ok": True}


async def relevant_knowledge(persona_id: str, query: str, k: int = 3) -> list:
    """Top-k chunks sharing keywords with the message (>=2 overlaps). Cheap lexical retrieval, no embeddings."""
    q = _kw(query)
    if len(q) < 1:
        return []
    scored = []
    async for d in db.knowledge_docs.find({"persona_id": persona_id, "enabled": True}, {"_id": 0, "title": 1, "chunks": 1}):
        for c in d.get("chunks") or []:
            s = len(q & set(c.get("kw") or []))
            if s >= 2 or (s >= 1 and len(q) <= 2):
                scored.append((s, d["title"], c["text"]))
    scored.sort(key=lambda t: -t[0])
    return [{"title": t, "text": x} for _, t, x in scored[:k]]
