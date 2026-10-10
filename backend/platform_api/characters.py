"""Platform console: manage the "Karakter Persona" presets users pick when creating a persona — /api/platform/persona-characters."""
from fastapi import APIRouter, Depends

from auth import require_platform_admin, require_platform_staff
from persona_characters import CharacterIn, all_characters, create_character, update_character, delete_character
from platform_api.common import _audit

router = APIRouter(prefix="/api/platform/persona-characters", tags=["platform-persona-characters"])


@router.get("", summary="Daftar karakter persona (termasuk bawaan, dengan prompt)")
async def list_characters(_: dict = Depends(require_platform_staff)):
    return {"items": await all_characters(fresh=True)}


@router.post("", summary="Tambah karakter persona", status_code=201)
async def add_character(x: CharacterIn, u: dict = Depends(require_platform_admin)):
    doc = await create_character(x)
    await _audit(u, "persona_character.create", doc["name"], {"id": doc["id"], "enabled": doc["enabled"]})
    return doc


@router.put("/{cid}", summary="Ubah karakter persona")
async def edit_character(cid: str, x: CharacterIn, u: dict = Depends(require_platform_admin)):
    doc = await update_character(cid, x)
    await _audit(u, "persona_character.update", doc["name"], {"id": cid, "enabled": doc["enabled"]})
    return doc


@router.delete("/{cid}", summary="Hapus karakter persona (persona pengguna kembali ke bawaan)")
async def remove_character(cid: str, u: dict = Depends(require_platform_admin)):
    res = await delete_character(cid)
    await _audit(u, "persona_character.delete", cid, res)
    return res
