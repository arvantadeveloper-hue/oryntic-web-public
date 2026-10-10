"""Oryntix built-in support assistant settings for the platform console — mounted at /api/platform/support-agent.
Reads/writes the shared `config` document (id "support_agent") through the main app's handlers (support_agent.py);
finance staff may read, only super_admin may change. Adds a chat preview that uses the configured model."""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import support_agent as sa
from auth import require_platform_admin, require_platform_staff
from knowledge import KnowledgeIn, KnowledgeUpdate, add_doc, list_docs, get_doc, update_doc, refresh_doc, delete_doc
from llm import llm_text
from platform_api.common import _audit

router = APIRouter(prefix="/api/platform/support-agent", tags=["platform-support-agent"])


@router.get("", summary="Konfigurasi Asisten Oryntix")
async def get_support_agent(_: dict = Depends(require_platform_staff)):
    return await sa.admin_get(_)


@router.put("", summary="Simpan konfigurasi Asisten Oryntix")
async def put_support_agent(x: sa.SupportConfigIn, u: dict = Depends(require_platform_admin)):
    res = await sa.admin_set(x, u)
    await _audit(u, "support_agent.update", "Asisten Oryntix", {"model": x.model, "sandbox": x.sandbox, "video_enabled": x.video_enabled})
    return res


@router.get("/avatars", summary="Daftar avatar LiveAvatar (mine=true → milik akun)")
async def list_avatars(page: int = 1, page_size: int = 24, mine: bool = False, u: dict = Depends(require_platform_staff)):
    return await sa.admin_avatars(page, page_size, mine, u)


class PreviewIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=64)


@router.post("/preview", summary="Uji cepat persona + knowledge dengan model yang dikonfigurasi")
async def preview_chat(x: PreviewIn, _: dict = Depends(require_platform_admin)):
    cfg = await sa.get_config(fresh=True)
    system_message = f"{cfg.get('system_prompt') or ''}\n\n# Oryntix Knowledge Base\n{(cfg.get('knowledge') or '')[:12000]}"
    try:
        reply = await llm_text(system_message, x.message, cfg.get("model"))
    except Exception as exc:
        raise HTTPException(502, f"Gagal menghasilkan balasan: {str(exc)[:200]}") from exc
    return {"reply": reply, "session_id": x.session_id or f"preview-{uuid.uuid4().hex[:12]}", "model": cfg.get("model")}


# ---- knowledge documents (one or more) — same pipeline as persona knowledge, scoped to the virtual support persona ----
@router.get("/knowledge", summary="Daftar dokumen pengetahuan Asisten Oryntix")
async def support_knowledge_list(_: dict = Depends(require_platform_staff)):
    return await list_docs(sa.SUPPORT_ID)


@router.post("/knowledge", summary="Tambah dokumen pengetahuan (upload / teks / HTML / URL)", status_code=201)
async def support_knowledge_add(x: KnowledgeIn, u: dict = Depends(require_platform_admin)):
    if x.drive_id:
        raise HTTPException(400, "Sumber Google Drive tidak tersedia untuk Asisten Oryntix — unggah file, teks, atau URL")
    doc = await add_doc(sa.SUPPORT_ID, "platform", x, u)
    await _audit(u, "support_knowledge.add", doc["title"], {"id": doc["id"], "source": doc["source"], "chars": doc["chars"]})
    return doc


@router.get("/knowledge/{kid}", summary="Detail dokumen + teks lengkap")
async def support_knowledge_get(kid: str, _: dict = Depends(require_platform_staff)):
    return await get_doc(sa.SUPPORT_ID, kid)


@router.put("/knowledge/{kid}", summary="Ubah judul / aktif / isi HTML")
async def support_knowledge_update(kid: str, x: KnowledgeUpdate, u: dict = Depends(require_platform_admin)):
    doc = await update_doc(sa.SUPPORT_ID, kid, x)
    await _audit(u, "support_knowledge.update", doc["title"], {"id": kid, **{k: v for k, v in x.model_dump().items() if v is not None and k != "html"}})
    return doc


@router.post("/knowledge/{kid}/refresh", summary="Unduh ulang dokumen bersumber URL")
async def support_knowledge_refresh(kid: str, u: dict = Depends(require_platform_admin)):
    doc = await refresh_doc(sa.SUPPORT_ID, kid, u)
    await _audit(u, "support_knowledge.refresh", doc["title"], {"id": kid})
    return doc


@router.delete("/knowledge/{kid}", summary="Hapus dokumen pengetahuan")
async def support_knowledge_delete(kid: str, u: dict = Depends(require_platform_admin)):
    res = await delete_doc(sa.SUPPORT_ID, kid)
    await _audit(u, "support_knowledge.delete", kid, {})
    return res
