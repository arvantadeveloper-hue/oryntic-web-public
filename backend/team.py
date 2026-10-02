import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from auth import (current_user, optional_user, require_admin, workspace_id, member_ids, pw_hash, public_user, make_token,
                  role_for, app_url, token_hash)
from db import db, now_iso, new_id, clean
from mailer import send_email, invite_email, debug_links

router = APIRouter(prefix="/api/team", tags=["team"])
INVITE_DEFAULT_DAILY_LIMIT = 100


class InviteIn(BaseModel):
    email: EmailStr


class AcceptIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    password: Optional[str] = Field(default=None, min_length=6, max_length=72)


def _public_invite(inv: dict) -> dict:
    return {k: v for k, v in clean(inv).items() if k != "token_hash"}


async def _send_invite(inv: dict, admin: dict, base_url: str) -> dict:
    raw = secrets.token_urlsafe(32)
    await db.workspace_invites.update_one({"id": inv["id"]}, {"$set": {"token_hash": token_hash(raw), "sent_at": now_iso(), "updated_at": now_iso()}})
    link = f"{base_url}/invite/{raw}"
    subject, html, text = invite_email(admin.get("name") or admin["email"], admin.get("name") or "Oryntix", link)
    sent = await send_email(inv["email"], subject, html, text)
    return {"mail_sent": sent, **({"debug_link": link} if debug_links() else {})}


@router.get("/invites")
async def list_invites(admin: dict = Depends(require_admin)):
    rows = await db.workspace_invites.find({"workspace_id": workspace_id(admin)}, {"_id": 0, "token_hash": 0}).sort("created_at", -1).to_list(500)
    return rows


@router.post("/invites")
async def create_invite(x: InviteIn, request: Request, admin: dict = Depends(require_admin)):
    wid = workspace_id(admin)
    email = str(x.email).lower()
    if email == admin["email"]:
        raise HTTPException(400, "Itu email Anda sendiri")
    target = await db.users.find_one({"email": email}, {"_id": 0, "id": 1})
    if target and target["id"] in await member_ids(wid):
        raise HTTPException(409, "Pengguna ini sudah menjadi anggota workspace")
    inv = await db.workspace_invites.find_one({"workspace_id": wid, "email": email}, {"_id": 0})
    if inv and inv.get("status") == "joined":
        raise HTTPException(409, "Pengguna ini sudah bergabung")
    if not inv:
        inv = {"id": new_id(), "workspace_id": wid, "email": email, "status": "pending", "invited_by": admin["id"],
               "inviter_name": admin.get("name") or admin["email"], "user_id": (target or {}).get("id"), "created_at": now_iso(), "updated_at": now_iso()}
        await db.workspace_invites.insert_one(dict(inv))
    else:
        await db.workspace_invites.update_one({"id": inv["id"]}, {"$set": {"status": "pending", "user_id": (target or {}).get("id"), "responded_at": None, "updated_at": now_iso()}})
        inv["status"] = "pending"
    out = await _send_invite(inv, admin, app_url(request))
    return {**_public_invite(await db.workspace_invites.find_one({"id": inv["id"]}, {"_id": 0})), **out, "existing_user": bool(target)}


@router.post("/invites/{iid}/resend")
async def resend_invite(iid: str, request: Request, admin: dict = Depends(require_admin)):
    inv = await db.workspace_invites.find_one({"id": iid, "workspace_id": workspace_id(admin)}, {"_id": 0})
    if not inv or inv.get("status") not in ("pending", "rejected"):
        raise HTTPException(404, "Undangan tidak ditemukan atau sudah bergabung")
    await db.workspace_invites.update_one({"id": iid}, {"$set": {"status": "pending", "responded_at": None}})
    return {"ok": True, **(await _send_invite(inv, admin, app_url(request)))}


@router.delete("/invites/{iid}")
async def cancel_invite(iid: str, admin: dict = Depends(require_admin)):
    res = await db.workspace_invites.delete_one({"id": iid, "workspace_id": workspace_id(admin), "status": {"$ne": "joined"}})
    if not res.deleted_count:
        raise HTTPException(404, "Undangan tidak ditemukan")
    return {"ok": True}


async def _by_token(token: str) -> dict:
    inv = await db.workspace_invites.find_one({"token_hash": token_hash(token)}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Undangan tidak valid atau sudah dibatalkan")
    return inv


async def _invite_info(inv: dict) -> dict:
    owner = await db.users.find_one({"id": inv["workspace_id"]}, {"_id": 0, "name": 1, "email": 1}) or {}
    existing = await db.users.find_one({"email": inv["email"]}, {"_id": 0, "id": 1, "verified": 1})
    return {"id": inv["id"], "email": inv["email"], "status": inv.get("status"), "workspace_name": owner.get("name") or "Workspace",
            "inviter_name": inv.get("inviter_name"), "existing_user": bool(existing), "created_at": inv.get("created_at")}


@router.get("/invites/by-token/{token}")
async def invite_by_token(token: str):
    return await _invite_info(await _by_token(token))


async def _join(inv: dict, user: dict) -> dict:
    wid = inv["workspace_id"]
    await db.workspace_members.update_one({"workspace_id": wid, "user_id": user["id"]},
                                          {"$set": {"email": user["email"], "status": "joined", "joined_at": now_iso()}, "$setOnInsert": {"id": new_id()}}, upsert=True)
    await db.workspace_invites.update_one({"id": inv["id"]}, {"$set": {"status": "joined", "user_id": user["id"], "responded_at": now_iso(), "updated_at": now_iso()}})
    if not user.get("daily_credit_limit"):
        await db.users.update_one({"id": user["id"]}, {"$set": {"daily_credit_limit": INVITE_DEFAULT_DAILY_LIMIT}})
    # switch the member into the workspace they just joined
    await db.users.update_one({"id": user["id"]}, {"$set": {"owner_id": wid, "role": "user"}})
    u2 = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    u2["role"] = role_for(u2)
    return {"access_token": make_token(u2["id"], u2["role"]), "user": public_user(u2), "workspace_id": wid}


async def _reject(inv: dict) -> dict:
    await db.workspace_invites.update_one({"id": inv["id"]}, {"$set": {"status": "rejected", "responded_at": now_iso(), "updated_at": now_iso()}})
    return {"ok": True, "status": "rejected"}


def _ensure_open(inv: dict):
    if inv.get("status") == "joined":
        raise HTTPException(400, "Undangan ini sudah diterima")


@router.post("/invites/by-token/{token}/accept")
async def accept_by_token(token: str, x: AcceptIn, u: Optional[dict] = Depends(optional_user)):
    inv = await _by_token(token)
    _ensure_open(inv)
    existing = await db.users.find_one({"email": inv["email"]}, {"_id": 0})
    if existing:
        if not u or u["email"] != inv["email"]:
            raise HTTPException(401, {"code": "login_required", "message": f"Masuk dengan akun {inv['email']} untuk menerima undangan ini"})
        return await _join(inv, existing)
    if not x.password:
        raise HTTPException(400, "Buat kata sandi (min 6 karakter) untuk membuat akun Anda")
    owner = await db.users.find_one({"id": inv["workspace_id"]}, {"_id": 0, "settings": 1}) or {}
    uid = new_id()
    doc = {"id": uid, "email": inv["email"], "password_hash": pw_hash(x.password), "name": x.name or inv["email"].split("@")[0],
           "role": "user", "owner_id": inv["workspace_id"], "onboarded": True, "verified": True, "verified_at": now_iso(), "credits": 0,
           "plan": "member", "daily_credit_limit": INVITE_DEFAULT_DAILY_LIMIT, "joined_via_invite": True,
           "settings": {"app_language": (owner.get("settings") or {}).get("app_language", "id"),
                        "conversation_language": (owner.get("settings") or {}).get("conversation_language", "id"),
                        "timezone": (owner.get("settings") or {}).get("timezone", "Asia/Jakarta"), "theme": "light"},
           "created_at": now_iso()}
    await db.users.insert_one(dict(doc))
    return await _join(inv, doc)


@router.post("/invites/by-token/{token}/reject")
async def reject_by_token(token: str):
    inv = await _by_token(token)
    _ensure_open(inv)
    return await _reject(inv)


@router.get("/my-invites")
async def my_invites(u: dict = Depends(current_user)):
    rows = await db.workspace_invites.find({"email": u["email"], "status": "pending"}, {"_id": 0, "token_hash": 0}).sort("created_at", -1).to_list(50)
    return [await _invite_info(r) for r in rows]


async def _my_pending(iid: str, u: dict) -> dict:
    inv = await db.workspace_invites.find_one({"id": iid, "email": u["email"]}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Undangan tidak ditemukan")
    _ensure_open(inv)
    return inv


@router.post("/my-invites/{iid}/accept")
async def accept_mine(iid: str, u: dict = Depends(current_user)):
    return await _join(await _my_pending(iid, u), u)


@router.post("/my-invites/{iid}/reject")
async def reject_mine(iid: str, u: dict = Depends(current_user)):
    return await _reject(await _my_pending(iid, u))


@router.delete("/members/{uid}")
async def remove_member(uid: str, admin: dict = Depends(require_admin)):
    wid = workspace_id(admin)
    if uid == admin["id"]:
        raise HTTPException(400, "Tidak bisa mengeluarkan diri sendiri")
    res = await db.workspace_members.delete_one({"workspace_id": wid, "user_id": uid})
    if not res.deleted_count:
        raise HTTPException(404, "Anggota tidak ditemukan di workspace ini")
    await db.workspace_invites.update_many({"workspace_id": wid, "user_id": uid}, {"$set": {"status": "removed", "updated_at": now_iso()}})
    # send them back to their own workspace if they were active here
    await db.users.update_one({"id": uid, "owner_id": wid}, [{"$set": {"owner_id": "$id", "role": "admin"}}])
    await db.conversations.update_many({"workspace_id": wid, "participants": uid}, {"$pull": {"participants": uid}})
    return {"ok": True}
