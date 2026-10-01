from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import db, now_iso, new_id
from auth import current_user

router = APIRouter(prefix="/api/wallet", tags=["wallet"])

DEFAULT_PACKAGES = [
    {"id": "starter", "name": "Starter", "credits": 500, "price_idr": 49000, "margin": 0.50, "best_value": False},
    {"id": "basic", "name": "Basic", "credits": 1200, "price_idr": 99000, "margin": 0.45, "best_value": False},
    {"id": "plus", "name": "Plus", "credits": 2800, "price_idr": 199000, "margin": 0.40, "best_value": True},
    {"id": "pro", "name": "Pro", "credits": 6000, "price_idr": 399000, "margin": 0.35, "best_value": False},
    {"id": "ultimate", "name": "Ultimate", "credits": 16000, "price_idr": 899000, "margin": 0.30, "best_value": False},
]


class TopupIn(BaseModel):
    package_id: str


async def get_packages():
    cfg = await db.config.find_one({"id": "credit_packages"})
    if not cfg:
        return DEFAULT_PACKAGES
    return cfg.get("packages", DEFAULT_PACKAGES)


@router.get("")
async def wallet(u: dict = Depends(current_user)):
    user = await db.users.find_one({"id": u["id"]}, {"_id": 0})
    txns = await db.credit_transactions.find({"user_id": u["id"]}, {"_id": 0}).sort("created_at", -1).to_list(50)
    consumed = 0
    breakdown = {}
    events = await db.usage_events.find({"user_id": u["id"]}, {"_id": 0}).to_list(2000)
    for e in events:
        consumed += e.get("credits", 0)
        breakdown[e["feature"]] = breakdown.get(e["feature"], 0) + e.get("credits", 0)
    return {
        "available": user.get("credits", 0),
        "reserved": 0,
        "consumed": consumed,
        "transactions": txns,
        "breakdown": [{"feature": k, "credits": v} for k, v in breakdown.items()],
    }


@router.get("/transactions")
async def transactions(u: dict = Depends(current_user)):
    return await db.credit_transactions.find({"user_id": u["id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.get("/packages")
async def packages():
    return await get_packages()


@router.post("/topup")
async def topup(x: TopupIn, u: dict = Depends(current_user)):
    pkgs = await get_packages()
    pkg = next((p for p in pkgs if p["id"] == x.package_id), None)
    if not pkg:
        raise HTTPException(404, "Package not found")
    user = await db.users.find_one({"id": u["id"]})
    new_balance = int(user.get("credits", 0)) + pkg["credits"]
    await db.users.update_one({"id": u["id"]}, {"$set": {"credits": new_balance}})
    await db.credit_transactions.insert_one({
        "id": new_id(), "user_id": u["id"], "type": "topup", "amount": pkg["credits"],
        "balance_after": new_balance, "description": f"Top-up {pkg['name']} (simulated)",
        "meta": {"package": pkg["id"], "price_idr": pkg["price_idr"], "simulated": True},
        "created_at": now_iso(),
    })
    return {"credits": new_balance, "added": pkg["credits"], "package": pkg["name"], "simulated": True}
