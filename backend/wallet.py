from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import db, now_iso, new_id
from auth import current_user, require_admin, workspace_id

router = APIRouter(prefix="/api/wallet", tags=["wallet"])

# Price = USD × (1 + margin 15%) × (1 + tax) × FX; tiers 3-5 give back part of the margin as a discount. Shown as one total.
PACKAGE_TIERS = [("starter", "Starter", 3, 0.0), ("basic", "Basic", 5, 0.0), ("plus", "Plus", 10, 0.05), ("pro", "Pro", 25, 0.10), ("ultimate", "Ultimate", 50, 0.15)]
PACKAGE_MARGIN = 0.15


def build_packages(p: dict) -> list:
    fx = float(p.get("usd_to_idr") or 16500)
    tax = float(p.get("tax_pct") or 11) / 100
    usd_per_credit = max(float(p.get("usd_per_credit") or 0.001), 1e-6)
    out = []
    for pid, name, usd, disc in PACKAGE_TIERS:
        price = usd * (1 + PACKAGE_MARGIN - disc) * (1 + tax) * fx
        out.append({"id": pid, "name": name, "usd": usd, "credits": int(round(usd / usd_per_credit)), "price_idr": int(round(price / 1000.0) * 1000),
                    "discount_pct": int(disc * 100), "best_value": pid == "plus"})
    return out


class TopupIn(BaseModel):
    package_id: str


async def get_packages():
    from pricing import get_pricing
    return build_packages(await get_pricing())


@router.get("")
async def wallet(u: dict = Depends(current_user)):
    wid = workspace_id(u)
    user = await db.users.find_one({"id": wid}, {"_id": 0})
    txns = await db.credit_transactions.find({"user_id": wid}, {"_id": 0}).sort("created_at", -1).to_list(50)
    consumed = 0
    breakdown = {}
    events = await db.usage_events.find({"user_id": wid}, {"_id": 0}).to_list(2000)
    for e in events:
        consumed += e.get("credits", 0)
        breakdown[e["feature"]] = breakdown.get(e["feature"], 0) + e.get("credits", 0)
    return {
        "available": user.get("credits", 0) if user else 0,
        "reserved": 0,
        "consumed": consumed,
        "transactions": txns,
        "breakdown": [{"feature": k, "credits": v} for k, v in breakdown.items()],
    }


@router.get("/transactions")
async def transactions(u: dict = Depends(current_user)):
    return await db.credit_transactions.find({"user_id": workspace_id(u)}, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.get("/packages")
async def packages():
    return await get_packages()


@router.post("/topup")
async def topup(x: TopupIn, u: dict = Depends(require_admin)):
    pkgs = await get_packages()
    pkg = next((p for p in pkgs if p["id"] == x.package_id), None)
    if not pkg:
        raise HTTPException(404, "Package not found")
    wid = workspace_id(u)
    user = await db.users.find_one({"id": wid})
    new_balance = int(user.get("credits", 0)) + pkg["credits"]
    await db.users.update_one({"id": wid}, {"$set": {"credits": new_balance, "plan": "paid", "daily_credit_limit": 0}})
    await db.credit_transactions.insert_one({
        "id": new_id(), "user_id": wid, "type": "topup", "amount": pkg["credits"],
        "balance_after": new_balance, "description": f"Top-up {pkg['name']} (simulated)",
        "meta": {"package": pkg["id"], "price_idr": pkg["price_idr"], "simulated": True},
        "created_at": now_iso(),
    })
    return {"credits": new_balance, "added": pkg["credits"], "package": pkg["name"], "simulated": True}
