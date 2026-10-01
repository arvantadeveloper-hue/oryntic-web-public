from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import db, now_iso, new_id, clean
from auth import current_user
from llm import llm_json, generate_image, record_usage, text_credits, PROFILE_CREDITS, IMAGE_CREDITS

router = APIRouter(prefix="/api/personas", tags=["personas"])


class GenerateProfileIn(BaseModel):
    description: str = Field(min_length=1, max_length=4000)
    method: str = "describe"  # describe | photo | combine
    photo_b64: Optional[str] = None


class PersonaIn(BaseModel):
    profile: dict
    model: str = "gpt-5.4"
    reference_photo: Optional[str] = None


class PortraitIn(BaseModel):
    style: str = "cinematic realistic"
    extra: Optional[str] = None
    use_reference: bool = True


class EditIn(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)


PROFILE_SYS = (
    "You are a character designer for an AI companion platform. Turn the user's request into a "
    "structured persona profile. The personality and traits must come ONLY from the user's explicit "
    "instructions. If a photo description is provided, use it strictly for VISUAL appearance, never to "
    "infer personality, ethnicity, religion, health, or any sensitive attribute. Keep ages adult (18+). "
    "Respond with JSON matching exactly this schema:\n"
    "{\n"
    '  "identity": {"name": str, "age_range": str, "gender_presentation": str, "background": str, "occupation": str, "summary": str},\n'
    '  "personality": {"primary_traits": [str], "communication_style": str, "humor": str, "formality": str, "attitude": str, "boundaries": str},\n'
    '  "appearance": {"face": str, "hair": str, "eyes": str, "skin": str, "build": str, "clothing": str, "distinctive": str, "visual_style": str},\n'
    '  "voice": {"character": str, "language": str, "accent": str, "pace": str},\n'
    '  "language": {"primary": str, "additional": [str]},\n'
    '  "system_instructions": str\n'
    "}"
)


@router.post("/generate-profile")
async def generate_profile(x: GenerateProfileIn, u: dict = Depends(current_user)):
    prompt = f"Create method: {x.method}\nUser request:\n{x.description}"
    if x.photo_b64:
        prompt += "\n\n(The user uploaded a reference photo. Describe only neutral visual appearance cues.)"
    profile = await llm_json(PROFILE_SYS, prompt)
    if not profile:
        raise HTTPException(502, "Could not generate profile, please try again")
    await record_usage(u["id"], "persona_profile", PROFILE_CREDITS, {"method": x.method})
    bal = (await db.users.find_one({"id": u["id"]}))["credits"]
    return {"profile": profile, "credits_used": PROFILE_CREDITS, "credits": bal}


@router.get("")
async def list_personas(u: dict = Depends(current_user)):
    items = await db.personas.find({"user_id": u["id"], "deleted": {"$ne": True}}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    return items


@router.post("")
async def create_persona(x: PersonaIn, u: dict = Depends(current_user)):
    ident = x.profile.get("identity", {})
    pid = new_id()
    doc = {
        "id": pid, "user_id": u["id"],
        "name": ident.get("name", "Untitled Persona"),
        "summary": ident.get("summary", ""),
        "profile": x.profile,
        "model": x.model,
        "portrait": None,
        "reference_photo": x.reference_photo,
        "version": 1,
        "versions": [],
        "deleted": False,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.personas.insert_one(doc)
    return clean(doc)


@router.get("/{pid}")
async def get_persona(pid: str, u: dict = Depends(current_user)):
    p = await db.personas.find_one({"id": pid, "user_id": u["id"]}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Persona not found")
    return p


@router.post("/{pid}/portrait")
async def gen_portrait(pid: str, x: PortraitIn, u: dict = Depends(current_user)):
    p = await db.personas.find_one({"id": pid, "user_id": u["id"]})
    if not p:
        raise HTTPException(404, "Persona not found")
    ap = p["profile"].get("appearance", {})
    ident = p["profile"].get("identity", {})
    desc = (
        f"A high quality {x.style} character portrait. "
        f"Name context: {ident.get('name','')}. {ident.get('summary','')}. "
        f"Face: {ap.get('face','')}. Hair: {ap.get('hair','')}. Eyes: {ap.get('eyes','')}. "
        f"Skin: {ap.get('skin','')}. Build: {ap.get('build','')}. Clothing: {ap.get('clothing','')}. "
        f"Distinctive: {ap.get('distinctive','')}. Visual style: {ap.get('visual_style','')}. "
        f"Portrait framing, head and shoulders, studio lighting, detailed, premium look."
    )
    if x.extra:
        desc += f" Additional: {x.extra}"
    ref = p.get("reference_photo") if x.use_reference else None
    ref_b64 = None
    if ref and "," in ref:
        ref_b64 = ref.split(",", 1)[1]
    try:
        data_url = await generate_image(desc, ref_b64)
    except Exception as e:
        raise HTTPException(502, f"Image generation failed: {str(e)[:120]}")
    if not data_url:
        raise HTTPException(502, "No image returned")
    await record_usage(u["id"], "persona_portrait", IMAGE_CREDITS, {"persona_id": pid})
    await db.personas.update_one({"id": pid}, {"$set": {"portrait": data_url, "updated_at": now_iso()}})
    bal = (await db.users.find_one({"id": u["id"]}))["credits"]
    return {"portrait": data_url, "credits_used": IMAGE_CREDITS, "credits": bal}


@router.put("/{pid}")
async def update_persona(pid: str, body: dict, u: dict = Depends(current_user)):
    p = await db.personas.find_one({"id": pid, "user_id": u["id"]})
    if not p:
        raise HTTPException(404, "Persona not found")
    versions = p.get("versions", [])
    versions.append({"version": p.get("version", 1), "profile": p["profile"], "at": now_iso()})
    new_profile = body.get("profile", p["profile"])
    ident = new_profile.get("identity", {})
    await db.personas.update_one({"id": pid}, {"$set": {
        "profile": new_profile,
        "name": ident.get("name", p["name"]),
        "summary": ident.get("summary", p.get("summary", "")),
        "model": body.get("model", p.get("model")),
        "version": p.get("version", 1) + 1,
        "versions": versions[-10:],
        "updated_at": now_iso(),
    }})
    return await db.personas.find_one({"id": pid}, {"_id": 0})


@router.post("/{pid}/edit")
async def edit_persona_nl(pid: str, x: EditIn, u: dict = Depends(current_user)):
    p = await db.personas.find_one({"id": pid, "user_id": u["id"]})
    if not p:
        raise HTTPException(404, "Persona not found")
    import json as _json
    sys = (
        "You edit an existing structured persona profile based on a natural language instruction. "
        "Only change the components implied by the instruction, keep everything else identical. "
        "Return the FULL updated profile as JSON with the same schema."
    )
    prompt = f"Current profile JSON:\n{_json.dumps(p['profile'])}\n\nInstruction: {x.instruction}"
    updated = await llm_json(sys, prompt)
    if not updated:
        raise HTTPException(502, "Could not apply edit")
    used = text_credits(prompt, _json.dumps(updated))
    await record_usage(u["id"], "persona_edit", used, {"persona_id": pid})
    versions = p.get("versions", [])
    versions.append({"version": p.get("version", 1), "profile": p["profile"], "at": now_iso()})
    ident = updated.get("identity", {})
    await db.personas.update_one({"id": pid}, {"$set": {
        "profile": updated, "name": ident.get("name", p["name"]),
        "summary": ident.get("summary", p.get("summary", "")),
        "version": p.get("version", 1) + 1, "versions": versions[-10:], "updated_at": now_iso(),
    }})
    return await db.personas.find_one({"id": pid}, {"_id": 0})


@router.post("/{pid}/duplicate")
async def duplicate_persona(pid: str, u: dict = Depends(current_user)):
    p = await db.personas.find_one({"id": pid, "user_id": u["id"]}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Persona not found")
    nid = new_id()
    p.update({"id": nid, "name": p["name"] + " (Copy)", "version": 1, "versions": [],
              "created_at": now_iso(), "updated_at": now_iso()})
    await db.personas.insert_one(dict(p))
    return clean(p)


@router.delete("/{pid}")
async def delete_persona(pid: str, u: dict = Depends(current_user)):
    r = await db.personas.update_one({"id": pid, "user_id": u["id"]}, {"$set": {"deleted": True, "updated_at": now_iso()}})
    if r.matched_count == 0:
        raise HTTPException(404, "Persona not found")
    return {"ok": True}
