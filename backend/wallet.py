from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import db, now_iso, new_id
from auth import current_user, require_admin, workspace_id
from pricing import get_pricing, build_packages

router = APIRouter(prefix="/api/wallet", tags=["wallet"])


class TopupIn(BaseModel):
    package_id: str


async def get_packages():
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


def _sess_key(ev: dict) -> str:
    m = ev.get("meta") or {}
    return m.get("call_session_id") or f"bw-{m.get('conversation_id')}-{(ev.get('created_at') or '')[:13]}"


async def _call_groups(wid: str, uid: str) -> dict:
    """One row per call session: assistant credits from realtime_calls + data/snapshot credits from usage events."""
    rows = {}

    def row(key, cid):
        return rows.setdefault(key, {"id": key, "conversation_id": cid, "started_at": None, "ended_at": None, "seconds": 0, "assistant_credits": 0,
                                     "data_credits": 0, "data_mb": 0.0, "snapshot_count": 0, "snapshot_credits": 0, "personas": [], "with_ai": False})

    async for c in db.realtime_calls.find({"user_id": {"$in": [wid, uid]}}, {"_id": 0, "call_session_id": 1, "group_id": 1, "conversation_id": 1, "created_at": 1, "started_at": 1, "ended_at": 1, "seconds": 1, "credits": 1, "snapshots": 1, "snapshot_credits": 1, "persona_name": 1}).sort("created_at", -1).limit(1500):
        r = row(c.get("call_session_id") or c.get("group_id"), c.get("conversation_id"))
        st = c.get("started_at") or c.get("created_at")
        r["started_at"] = min(r["started_at"] or st, st); r["ended_at"] = max(r["ended_at"] or "", c.get("ended_at") or st)
        r["seconds"] = max(r["seconds"], int(c.get("seconds") or 0)); r["assistant_credits"] += int(c.get("credits") or 0)
        r["snapshot_count"] += int(c.get("snapshots") or 0); r["snapshot_credits"] += int(c.get("snapshot_credits") or 0); r["with_ai"] = True
        if c.get("persona_name") and c["persona_name"] not in r["personas"]:
            r["personas"].append(c["persona_name"])
    async for e in db.usage_events.find({"user_id": wid, "feature": "call_bandwidth"}, {"_id": 0, "meta": 1, "credits": 1, "created_at": 1}).sort("created_at", -1).limit(3000):
        r = row(_sess_key(e), (e.get("meta") or {}).get("conversation_id"))
        r["data_credits"] += int(e.get("credits") or 0); r["data_mb"] += float((e.get("meta") or {}).get("mb") or 0)
        at = e.get("created_at") or ""
        if not r["with_ai"]:
            r["started_at"] = min(r["started_at"] or at, at); r["ended_at"] = max(r["ended_at"] or "", at)
    return rows


@router.get("/calls")
async def call_report(before: str | None = None, limit: int = 20, u: dict = Depends(current_user)):
    """Per-call cost breakdown (assistant tokens, WebRTC data, screen snapshots) for the Credits page."""
    rows = await _call_groups(workspace_id(u), u["id"])
    items = sorted((r for r in rows.values() if r["assistant_credits"] or r["data_credits"] or r["snapshot_credits"] or r["seconds"]), key=lambda r: r["started_at"] or "", reverse=True)
    if before:
        items = [r for r in items if (r["started_at"] or "") < before]
    page, has_more = items[:max(1, min(limit, 100))], len(items) > limit
    titles = {c["id"]: c async for c in db.conversations.find({"id": {"$in": list({r["conversation_id"] for r in page if r["conversation_id"]})}}, {"_id": 0, "id": 1, "title": 1, "titles": 1, "type": 1})}
    for r in page:
        c = titles.get(r["conversation_id"]) or {}
        r["title"] = (c.get("titles") or {}).get(u["id"]) or c.get("title") or "Panggilan"
        r["type"] = c.get("type")
        if not r["with_ai"] and r["started_at"] and r["ended_at"]:
            from datetime import datetime
            r["seconds"] = int((datetime.fromisoformat(r["ended_at"]) - datetime.fromisoformat(r["started_at"])).total_seconds()) + 30
        r["data_mb"] = round(r["data_mb"], 2)
        r["total"] = r["assistant_credits"] + r["data_credits"] + r["snapshot_credits"]
    return {"items": page, "has_more": has_more, "next_before": page[-1]["started_at"] if has_more and page else None}


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
