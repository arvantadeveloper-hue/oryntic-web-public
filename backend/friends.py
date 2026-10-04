from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr

from auth import current_user, app_url
from db import db, now_iso, new_id, clean
from mailer import send_email, friend_request_email, friend_invite_email, debug_links

router = APIRouter(prefix="/api/friends", tags=["friends"])


def _pub(u: dict) -> dict:
    return {"id": u["id"], "name": u.get("name") or u.get("email", "").split("@")[0], "email": u.get("email"), "avatar": u.get("avatar")}


async def friend_ids(uid: str) -> list:
    rows = await db.friends.find({"status": "accepted", "$or": [{"requester_id": uid}, {"addressee_id": uid}]}, {"_id": 0}).to_list(1000)
    return [r["addressee_id"] if r["requester_id"] == uid else r["requester_id"] for r in rows]


async def are_friends(a: str, b: str) -> bool:
    return bool(await db.friends.find_one({"status": "accepted", "$or": [{"requester_id": a, "addressee_id": b}, {"requester_id": b, "addressee_id": a}]}, {"_id": 0, "id": 1}))


async def _users(ids: list) -> dict:
    return {x["id"]: _pub(x) async for x in db.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1, "avatar": 1})}


@router.get("")
async def list_friends(u: dict = Depends(current_user)):
    uid = u["id"]
    rows = await db.friends.find({"$or": [{"requester_id": uid}, {"addressee_id": uid}], "status": {"$in": ["accepted", "pending"]}}, {"_id": 0}).sort("updated_at", -1).to_list(1000)
    people = await _users(list({r["requester_id"] for r in rows} | {r["addressee_id"] for r in rows}))
    out = {"friends": [], "incoming": [], "outgoing": [], "email_invites": []}
    for r in rows:
        other = people.get(r["addressee_id"] if r["requester_id"] == uid else r["requester_id"])
        if not other:
            continue
        if r["status"] == "accepted":
            out["friends"].append({**other, "since": r.get("updated_at")})
        elif r["addressee_id"] == uid:
            out["incoming"].append({"request_id": r["id"], **other, "created_at": r["created_at"]})
        else:
            out["outgoing"].append({"request_id": r["id"], **other, "created_at": r["created_at"]})
    out["email_invites"] = await db.friend_email_invites.find({"inviter_id": uid, "status": "pending"}, {"_id": 0, "email": 1, "created_at": 1}).sort("created_at", -1).to_list(100)
    return out


class InviteIn(BaseModel):
    email: EmailStr
    app_url: Optional[str] = None


@router.post("/invite")
async def invite(x: InviteIn, request: Request, u: dict = Depends(current_user)):
    """Registered → friend request (needs approval). Not registered → email invite; the request is created automatically once they sign up."""
    email = str(x.email).lower()
    if email == (u.get("email") or "").lower():
        raise HTTPException(400, "Itu email Anda sendiri")
    base = app_url(request, x.app_url)
    target = await db.users.find_one({"email": email}, {"_id": 0, "id": 1, "name": 1, "email": 1})
    if not target:
        await db.friend_email_invites.update_one({"inviter_id": u["id"], "email": email}, {"$set": {"status": "pending", "updated_at": now_iso()}, "$setOnInsert": {"id": new_id(), "created_at": now_iso()}}, upsert=True)
        subject, html, text = friend_invite_email(u.get("name") or u["email"], f"{base}/?friend_from={u['id']}")
        sent = await send_email(email, subject, html, text)
        return {"status": "emailed", "mail_sent": sent, **({"debug_link": f"{base}/"} if debug_links(request) else {})}
    if target["id"] == u["id"]:
        raise HTTPException(400, "Itu akun Anda sendiri")
    existing = await db.friends.find_one({"$or": [{"requester_id": u["id"], "addressee_id": target["id"]}, {"requester_id": target["id"], "addressee_id": u["id"]}]}, {"_id": 0})
    if existing and existing["status"] == "accepted":
        raise HTTPException(400, "Sudah berteman")
    if existing and existing["status"] == "pending":
        if existing["addressee_id"] == u["id"]:  # they already asked us → accept
            await db.friends.update_one({"id": existing["id"]}, {"$set": {"status": "accepted", "updated_at": now_iso()}})
            return {"status": "accepted"}
        raise HTTPException(400, "Permintaan sudah dikirim, menunggu persetujuan")
    doc = {"id": new_id(), "requester_id": u["id"], "addressee_id": target["id"], "status": "pending", "created_at": now_iso(), "updated_at": now_iso()}
    await db.friends.update_one({"requester_id": u["id"], "addressee_id": target["id"]}, {"$set": doc}, upsert=True)
    subject, html, text = friend_request_email(u.get("name") or u["email"], f"{base}/friends")
    sent = await send_email(target["email"], subject, html, text)
    return {"status": "requested", "request_id": doc["id"], "mail_sent": sent}


@router.post("/{rid}/accept")
async def accept(rid: str, u: dict = Depends(current_user)):
    r = await db.friends.update_one({"id": rid, "addressee_id": u["id"], "status": "pending"}, {"$set": {"status": "accepted", "updated_at": now_iso()}})
    if not r.matched_count:
        raise HTTPException(404, "Permintaan tidak ditemukan")
    return {"ok": True}


@router.post("/{rid}/reject")
async def reject(rid: str, u: dict = Depends(current_user)):
    r = await db.friends.update_one({"id": rid, "addressee_id": u["id"], "status": "pending"}, {"$set": {"status": "rejected", "updated_at": now_iso()}})
    if not r.matched_count:
        raise HTTPException(404, "Permintaan tidak ditemukan")
    return {"ok": True}


@router.delete("/{uid}")
async def unfriend(uid: str, u: dict = Depends(current_user)):
    await db.friends.delete_many({"$or": [{"requester_id": u["id"], "addressee_id": uid}, {"requester_id": uid, "addressee_id": u["id"]}]})
    return {"ok": True}


@router.post("/{uid}/chat")
async def friend_chat(uid: str, u: dict = Depends(current_user)):
    """One direct (human ↔ human) chat per friend; assistants can be added later."""
    if not await are_friends(u["id"], uid):
        raise HTTPException(403, "Belum berteman")
    pair = sorted([u["id"], uid])
    conv = await db.conversations.find_one({"type": "dm", "pair": pair, "archived_conv": {"$ne": True}}, {"_id": 0})
    if not conv:
        people = await _users(pair)
        conv = {"id": new_id(), "user_id": u["id"], "workspace_id": u.get("owner_id") or u["id"], "participants": pair, "pair": pair, "type": "dm", "persona_ids": [], "persona_id": None,
                "members": [], "humans": [people[i] for i in pair if i in people], "titles": {i: people[pair[1 - k]]["name"] for k, i in enumerate(pair) if pair[1 - k] in people},
                "title": " & ".join(people[i]["name"] for i in pair if i in people), "created_at": now_iso(), "updated_at": now_iso(), "last_message": ""}
        await db.conversations.insert_one(dict(conv))
    return clean(conv)


async def convert_email_invites(user: dict):
    """Called after sign-up: pending email invites for this address become friend requests."""
    async for inv in db.friend_email_invites.find({"email": (user.get("email") or "").lower(), "status": "pending"}, {"_id": 0}):
        await db.friends.update_one({"requester_id": inv["inviter_id"], "addressee_id": user["id"]},
                                    {"$setOnInsert": {"id": new_id(), "requester_id": inv["inviter_id"], "addressee_id": user["id"], "status": "pending", "created_at": now_iso()}, "$set": {"updated_at": now_iso()}}, upsert=True)
        await db.friend_email_invites.update_one({"id": inv["id"]}, {"$set": {"status": "converted", "updated_at": now_iso()}})
