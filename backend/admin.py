from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from db import db, now_iso, new_id
from auth import require_admin, workspace_id, pw_hash, public_user
from wallet import get_packages
from llm import GPT_MODEL, IMAGE_MODEL, TEXT_CREDITS_PER_1K_CHARS, IMAGE_CREDITS, PROFILE_CREDITS, user_today_usage

router = APIRouter(prefix="/api/admin", tags=["admin"])


class CreateUserIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)
    name: str | None = None


class UpdateUserIn(BaseModel):
    daily_credit_limit: int | None = None
    name: str | None = None


@router.get("/workspace-users")
async def workspace_users(admin: dict = Depends(require_admin)):
    wid = workspace_id(admin)
    items = await db.users.find({"owner_id": wid}, {"_id": 0, "password_hash": 0}).sort("created_at", 1).to_list(500)
    out = []
    for i in items:
        pu = public_user(i)
        pu["daily_credit_limit"] = int(i.get("daily_credit_limit") or 0)
        pu["today_usage"] = await user_today_usage(i["id"])
        out.append(pu)
    return out


@router.patch("/users/{uid}")
async def update_workspace_user(uid: str, x: UpdateUserIn, admin: dict = Depends(require_admin)):
    target = await db.users.find_one({"id": uid})
    if not target or target.get("owner_id") != workspace_id(admin):
        raise HTTPException(404, "Pengguna tidak ditemukan di workspace ini")
    fields = {}
    if x.daily_credit_limit is not None:
        fields["daily_credit_limit"] = max(0, int(x.daily_credit_limit))
    if x.name is not None:
        fields["name"] = x.name
    if fields:
        await db.users.update_one({"id": uid}, {"$set": fields})
    doc = await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0})
    pu = public_user(doc)
    pu["daily_credit_limit"] = int(doc.get("daily_credit_limit") or 0)
    pu["today_usage"] = await user_today_usage(uid)
    return pu


@router.post("/users")
async def create_workspace_user(x: CreateUserIn, admin: dict = Depends(require_admin)):
    email = str(x.email).lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "Email sudah terdaftar")
    wid = workspace_id(admin)
    uid = new_id()
    doc = {
        "id": uid, "email": email, "password_hash": pw_hash(x.password),
        "name": x.name or email.split("@")[0], "role": "user", "owner_id": wid,
        "onboarded": True, "verified": True, "credits": 0,
        "settings": {
            "app_language": admin.get("settings", {}).get("app_language", "id"),
            "conversation_language": admin.get("settings", {}).get("conversation_language", "id"),
            "timezone": admin.get("settings", {}).get("timezone", "Asia/Jakarta"),
            "theme": "light",
        },
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    return public_user(doc)


@router.delete("/users/{uid}")
async def delete_workspace_user(uid: str, admin: dict = Depends(require_admin)):
    if uid == admin["id"]:
        raise HTTPException(400, "Tidak bisa menghapus akun sendiri")
    target = await db.users.find_one({"id": uid})
    if not target or target.get("owner_id") != workspace_id(admin):
        raise HTTPException(404, "Pengguna tidak ditemukan di workspace ini")
    await db.users.delete_one({"id": uid})
    await db.conversations.update_many({"participants": uid}, {"$pull": {"participants": uid}})
    return {"ok": True}


@router.get("/overview")
async def overview(_: dict = Depends(require_admin)):
    users = await db.users.count_documents({})
    personas = await db.personas.count_documents({"deleted": {"$ne": True}})
    tasks = await db.tasks.count_documents({})
    conversations = await db.conversations.count_documents({})
    completed = await db.tasks.count_documents({"status": "completed"})
    failed = await db.tasks.count_documents({"status": "failed"})
    reminders = await db.reminders.count_documents({})
    # credit consumption
    consumed = 0
    breakdown = {}
    async for e in db.usage_events.find({}):
        consumed += e.get("credits", 0)
        breakdown[e["feature"]] = breakdown.get(e["feature"], 0) + e.get("credits", 0)
    return {
        "users": users, "personas": personas, "tasks": tasks, "conversations": conversations,
        "reminders": reminders, "tasks_completed": completed, "tasks_failed": failed,
        "credits_consumed": consumed,
        "usage_breakdown": [{"feature": k, "credits": v} for k, v in breakdown.items()],
    }


@router.get("/users")
async def users(_: dict = Depends(require_admin)):
    items = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    return items


@router.get("/personas")
async def personas(_: dict = Depends(require_admin)):
    return await db.personas.find({"deleted": {"$ne": True}}, {"_id": 0, "portrait": 0, "reference_photo": 0}).sort("updated_at", -1).to_list(500)


@router.get("/tasks")
async def tasks(_: dict = Depends(require_admin)):
    return await db.tasks.find({}, {"_id": 0, "steps": 0, "final_output": 0}).sort("created_at", -1).to_list(500)


@router.get("/pricing")
async def pricing(_: dict = Depends(require_admin)):
    pkgs = await get_packages()
    return {
        "packages": pkgs,
        "providers": [
            {"provider": "OpenAI", "model": GPT_MODEL, "capability": "text", "unit": "chars",
             "rate_credits_per_1k_chars": TEXT_CREDITS_PER_1K_CHARS, "status": "active"},
            {"provider": "Gemini (Nano Banana)", "model": IMAGE_MODEL, "capability": "image",
             "unit": "image", "rate_credits": IMAGE_CREDITS, "status": "active"},
        ],
        "tariff": {
            "profile_generation_credits": PROFILE_CREDITS,
            "image_generation_credits": IMAGE_CREDITS,
            "text_credits_per_1k_chars": TEXT_CREDITS_PER_1K_CHARS,
            "method": "usage-based metering (credits = usage units)",
        },
    }
