from db import db, now_iso, new_id


async def convert_email_invites(user: dict) -> None:
    """Called after sign-up: pending email invites for this address become friend requests."""
    async for inv in db.friend_email_invites.find({"email": (user.get("email") or "").lower(), "status": "pending"}, {"_id": 0}):
        await db.friends.update_one({"requester_id": inv["inviter_id"], "addressee_id": user["id"]},
                                    {"$setOnInsert": {"id": new_id(), "requester_id": inv["inviter_id"], "addressee_id": user["id"], "status": "pending", "created_at": now_iso()}, "$set": {"updated_at": now_iso()}}, upsert=True)
        await db.friend_email_invites.update_one({"id": inv["id"]}, {"$set": {"status": "converted", "updated_at": now_iso()}})
