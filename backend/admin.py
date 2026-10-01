from fastapi import APIRouter, Depends
from db import db
from auth import require_admin
from wallet import get_packages
from llm import GPT_MODEL, IMAGE_MODEL, TEXT_CREDITS_PER_1K_CHARS, IMAGE_CREDITS, PROFILE_CREDITS

router = APIRouter(prefix="/api/admin", tags=["admin"])


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
