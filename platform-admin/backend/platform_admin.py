import os
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from db import db, now_iso, new_id
from auth import (require_platform_admin, require_platform_staff, platform_role, PLATFORM_ROLES, public_user,
                  issue_reset_link, app_url, pw_hash)
from mailer import send_email, debug_links
from labels import FEATURE_LABELS

# Platform back-office API (separate admin website). Roles: super_admin (everything) · finance (read-only reports).
router = APIRouter(prefix="/api/platform", tags=["platform"])
ROLE_LABELS = {"super_admin": "Super Admin", "finance": "Finance"}


async def _audit(actor: dict, action: str, target: Optional[str] = None, meta: Optional[dict] = None) -> None:
    await db.platform_audit.insert_one({"id": new_id(), "actor_id": actor["id"], "actor_email": actor["email"], "action": action,
                                        "target": target, "meta": meta or {}, "created_at": now_iso()})


def _staff_pub(u: dict) -> dict:
    return {"id": u["id"], "email": u["email"], "name": u.get("name"), "platform_role": platform_role(u), "is_owner": platform_role(u) == "super_admin" and not u.get("platform_role"),
            "created_at": u.get("created_at"), "last_login_at": u.get("last_login_at"), "disabled": bool(u.get("disabled"))}


@router.get("/me")
async def me(u: dict = Depends(require_platform_staff)):
    return {**public_user(u), "platform_role": u["platform_role"], "roles": [{"id": r, "label": ROLE_LABELS[r]} for r in PLATFORM_ROLES]}


# ---------- dashboard ----------
@router.get("/stats")
async def stats(days: int = 30, u: dict = Depends(require_platform_staff)):
    days = max(1, min(days, 365))
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).isoformat()
    users_total = await db.users.count_documents({})
    users_new = await db.users.count_documents({"created_at": {"$gte": since}})
    sold, revenue_idr, topups = 0, 0, 0
    async for t in db.credit_transactions.find({"type": "topup", "created_at": {"$gte": since}}, {"_id": 0, "amount": 1, "meta": 1}):
        sold += int(t.get("amount") or 0); revenue_idr += int((t.get("meta") or {}).get("price_idr") or 0); topups += 1
    consumed, by_feature, daily = 0, {}, {}
    async for e in db.usage_events.find({"created_at": {"$gte": since}}, {"_id": 0, "feature": 1, "credits": 1, "created_at": 1}):
        c = int(e.get("credits") or 0); consumed += c
        by_feature[e["feature"]] = by_feature.get(e["feature"], 0) + c
        d = (e.get("created_at") or "")[:10]; daily[d] = daily.get(d, 0) + c
    live_cutoff = (now - timedelta(minutes=2)).isoformat()
    active_calls = await db.realtime_calls.count_documents({"status": {"$ne": "ended"}, "created_at": {"$gte": (now - timedelta(hours=6)).isoformat()}})
    active_rooms = await db.conversations.count_documents({"active_call": {"$exists": True, "$ne": {}}, "updated_at": {"$gte": live_cutoff}})
    balance_total = 0
    async for x in db.users.aggregate([{"$group": {"_id": None, "s": {"$sum": "$credits"}}}]):
        balance_total = int(x["s"] or 0)
    return {"days": days, "users_total": users_total, "users_new": users_new, "credits_sold": sold, "topups": topups, "revenue_idr": revenue_idr,
            "credits_consumed": consumed, "credits_outstanding": balance_total, "active_calls": active_calls, "active_rooms": active_rooms,
            "by_feature": sorted([{"feature": f, "label": FEATURE_LABELS.get(f, f.replace("_", " ").title()), "credits": c} for f, c in by_feature.items()], key=lambda x: -x["credits"]),
            "daily": [{"date": d, "credits": daily.get(d, 0)} for d in ((now - timedelta(days=i)).date().isoformat() for i in range(days - 1, -1, -1))]}


# ---------- staff & roles ----------
class StaffIn(BaseModel):
    email: EmailStr
    role: str = Field(pattern=r"^(super_admin|finance)$")
    name: Optional[str] = Field(default=None, max_length=80)


class RoleIn(BaseModel):
    role: str = Field(pattern=r"^(super_admin|finance)$")


async def _super_admin_count() -> int:
    return await db.users.count_documents({"platform_role": "super_admin"})


@router.get("/staff")
async def list_staff(u: dict = Depends(require_platform_admin)):
    rows = await db.users.find({"$or": [{"platform_role": {"$in": list(PLATFORM_ROLES)}}, {"email": os.environ["ADMIN_EMAIL"].lower()}]}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return {"items": [_staff_pub(r) for r in rows], "roles": [{"id": r, "label": ROLE_LABELS[r]} for r in PLATFORM_ROLES]}


@router.post("/staff")
async def add_staff(x: StaffIn, request: Request, u: dict = Depends(require_platform_admin)):
    """Grant a platform role. Existing accounts are upgraded; new ones are created and receive a set-password link."""
    email = str(x.email).lower()
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    out = {"created": False}
    if existing:
        if existing.get("disabled"):
            raise HTTPException(400, "Akun ini dinonaktifkan; aktifkan dulu")
        await db.users.update_one({"id": existing["id"]}, {"$set": {"platform_role": x.role, "updated_at": now_iso()}})
        target = {**existing, "platform_role": x.role}
    else:
        uid = new_id()
        target = {"id": uid, "email": email, "password_hash": pw_hash(new_id() + new_id()), "name": x.name or email.split("@")[0], "role": "admin", "owner_id": uid,
                  "onboarded": True, "verified": True, "platform_role": x.role, "credits": 0, "plan": "staff",
                  "settings": {"app_language": "id", "conversation_language": "id", "timezone": "Asia/Jakarta"}, "created_at": now_iso()}
        await db.users.insert_one(dict(target))
        link = await issue_reset_link(email, app_url(request))
        html = f"<p>Anda diundang sebagai <b>{ROLE_LABELS[x.role]}</b> di Oryntix Platform.</p><p><a href='{link}'>Atur password Anda</a> (berlaku 1 jam).</p>"
        out["mail_sent"] = await send_email(email, "Undangan staf Oryntix Platform", html, f"Undangan {ROLE_LABELS[x.role]} Oryntix Platform. Atur password: {link}")
        if debug_links(request):
            out["debug_link"] = link
        out["created"] = True
    await _audit(u, "staff.grant", email, {"role": x.role, "created": out["created"]})
    return {**out, "staff": _staff_pub(target)}


@router.put("/staff/{uid}")
async def set_role(uid: str, x: RoleIn, u: dict = Depends(require_platform_admin)):
    if uid == u["id"]:
        raise HTTPException(400, "Anda tidak dapat mengubah peran sendiri")
    t = await db.users.find_one({"id": uid}, {"_id": 0})
    if not t or not platform_role(t):
        raise HTTPException(404, "Staf tidak ditemukan")
    if platform_role(t) == "super_admin" and not t.get("platform_role"):
        raise HTTPException(400, "Pemilik platform (ADMIN_EMAIL) tidak dapat diubah")
    if t.get("platform_role") == "super_admin" and x.role != "super_admin" and await _super_admin_count() <= 1:
        raise HTTPException(400, "Harus tersisa minimal satu Super Admin")
    await db.users.update_one({"id": uid}, {"$set": {"platform_role": x.role, "updated_at": now_iso()}})
    await _audit(u, "staff.role", t["email"], {"from": t.get("platform_role"), "to": x.role})
    return {"staff": _staff_pub({**t, "platform_role": x.role})}


@router.delete("/staff/{uid}")
async def revoke_staff(uid: str, u: dict = Depends(require_platform_admin)):
    if uid == u["id"]:
        raise HTTPException(400, "Anda tidak dapat mencabut akses sendiri")
    t = await db.users.find_one({"id": uid}, {"_id": 0})
    if not t or not platform_role(t):
        raise HTTPException(404, "Staf tidak ditemukan")
    if not t.get("platform_role"):
        raise HTTPException(400, "Pemilik platform (ADMIN_EMAIL) tidak dapat dicabut")
    if t["platform_role"] == "super_admin" and await _super_admin_count() <= 1:
        raise HTTPException(400, "Harus tersisa minimal satu Super Admin")
    await db.users.update_one({"id": uid}, {"$unset": {"platform_role": ""}, "$set": {"updated_at": now_iso()}})
    await _audit(u, "staff.revoke", t["email"], {"role": t["platform_role"]})
    return {"ok": True}


# ---------- end users ----------
@router.get("/users")
async def list_users(q: Optional[str] = None, before: Optional[str] = None, limit: int = 30, u: dict = Depends(require_platform_staff)):
    limit = max(1, min(limit, 100))
    query = {}
    if q:
        import re
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"email": rx}, {"name": rx}]
    if before:
        query["created_at"] = {"$lt": before}
    rows = await db.users.find(query, {"_id": 0, "id": 1, "email": 1, "name": 1, "credits": 1, "plan": 1, "created_at": 1, "disabled": 1, "platform_role": 1, "verified": 1, "last_login_at": 1}).sort("created_at", -1).to_list(limit + 1)
    has_more = len(rows) > limit
    rows = rows[:limit]
    ids = [r["id"] for r in rows]
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    used = {x["_id"]: int(x["c"] or 0) async for x in db.usage_events.aggregate([{"$match": {"user_id": {"$in": ids}, "created_at": {"$gte": since}}}, {"$group": {"_id": "$user_id", "c": {"$sum": "$credits"}}}])}
    personas = {x["_id"]: int(x["c"]) async for x in db.personas.aggregate([{"$match": {"user_id": {"$in": ids}, "deleted": {"$ne": True}}}, {"$group": {"_id": "$user_id", "c": {"$sum": 1}}}])}
    for r in rows:
        r["used_30d"] = used.get(r["id"], 0); r["personas"] = personas.get(r["id"], 0); r["disabled"] = bool(r.get("disabled")); r["credits"] = int(r.get("credits") or 0)
    return {"items": rows, "has_more": has_more, "next_before": rows[-1]["created_at"] if has_more and rows else None}


class CreditAdjustIn(BaseModel):
    delta: int = Field(ge=-1_000_000, le=1_000_000)
    note: str = Field(default="", max_length=200)


@router.post("/users/{uid}/credits")
async def adjust_credits(uid: str, x: CreditAdjustIn, u: dict = Depends(require_platform_admin)):
    if x.delta == 0:
        raise HTTPException(400, "Jumlah tidak boleh 0")
    t = await db.users.find_one({"id": uid}, {"_id": 0, "credits": 1, "email": 1})
    if not t:
        raise HTTPException(404, "Pengguna tidak ditemukan")
    new_balance = max(0, int(t.get("credits") or 0) + x.delta)
    await db.users.update_one({"id": uid}, {"$set": {"credits": new_balance}})
    await db.credit_transactions.insert_one({"id": new_id(), "user_id": uid, "type": "adjustment", "amount": new_balance - int(t.get("credits") or 0), "balance_after": new_balance,
                                             "description": x.note or ("Penyesuaian oleh Oryntix Platform"), "meta": {"by": u["email"]}, "created_at": now_iso()})
    await _audit(u, "user.credits", t["email"], {"delta": x.delta, "note": x.note, "balance_after": new_balance})
    return {"credits": new_balance}


class DisableIn(BaseModel):
    disabled: bool
    reason: str = Field(default="", max_length=200)


@router.post("/users/{uid}/disable")
async def disable_user(uid: str, x: DisableIn, u: dict = Depends(require_platform_admin)):
    if uid == u["id"]:
        raise HTTPException(400, "Tidak dapat menonaktifkan akun sendiri")
    t = await db.users.find_one({"id": uid}, {"_id": 0, "email": 1, "platform_role": 1})
    if not t:
        raise HTTPException(404, "Pengguna tidak ditemukan")
    if platform_role(t) == "super_admin":
        raise HTTPException(400, "Super Admin tidak dapat dinonaktifkan; cabut perannya dulu")
    await db.users.update_one({"id": uid}, {"$set": {"disabled": x.disabled, "disabled_reason": x.reason if x.disabled else "", "updated_at": now_iso()}})
    await _audit(u, "user.disable" if x.disabled else "user.enable", t["email"], {"reason": x.reason})
    return {"ok": True, "disabled": x.disabled}


@router.get("/audit")
async def audit_log(limit: int = 50, u: dict = Depends(require_platform_admin)):
    return {"items": await db.platform_audit.find({}, {"_id": 0}).sort("created_at", -1).to_list(max(1, min(limit, 200)))}
