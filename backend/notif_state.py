"""Badge + bell-feed snapshots, shared by the GET endpoints and by WebSocket events (so clients update without re-fetching)."""
from db import db, now_iso


async def compute_badges(uid: str) -> dict:
    friend_requests = await db.friends.count_documents({"addressee_id": uid, "status": "pending"})
    unread = 0
    async for c in db.conversations.find({"$or": [{"user_id": uid}, {"participants": uid}], "archived_conv": {"$ne": True}, "last_message": {"$nin": ["", None]}},
                                         {"_id": 0, "updated_at": 1, "read_at": 1, "last_sender_id": 1}):
        if c.get("last_sender_id") == uid:
            continue
        if (c.get("updated_at") or "") > ((c.get("read_at") or {}).get(uid) or ""):
            unread += 1
    return {"friend_requests": friend_requests, "unread_chats": unread, "at": now_iso()}


async def compute_feed(uid: str) -> dict:
    u = await db.users.find_one({"id": uid}, {"_id": 0, "notifications_seen_at": 1}) or {}
    seen = (u.get("notifications_seen_at") or "")
    items = [dict(r, read=r["created_at"] <= seen) for r in await db.notifications.find({"user_id": uid}, {"_id": 0}).sort("created_at", -1).to_list(30)]
    for r in await db.reminders.find({"user_id": uid, "status": "ringing"}, {"_id": 0, "id": 1, "title": 1, "remind_at": 1}).to_list(5):
        items.insert(0, {"id": f"rem-{r['id']}", "kind": "reminders", "title": f"Pengingat berbunyi: {r.get('title') or 'Agenda'}", "body": "Asisten siap menelepon Anda.", "link": "/reminders", "created_at": r.get("remind_at") or now_iso(), "read": False, "live": True})
    reqs = await db.friends.find({"addressee_id": uid, "status": "pending"}, {"_id": 0, "id": 1, "requester_id": 1, "created_at": 1}).to_list(10)
    if reqs:
        people = {p["id"]: p async for p in db.users.find({"id": {"$in": [r["requester_id"] for r in reqs]}}, {"_id": 0, "id": 1, "name": 1, "email": 1})}
        for r in reqs:
            p = people.get(r["requester_id"]) or {}
            items.insert(0, {"id": f"fr-{r['id']}", "kind": "friends", "title": f"Permintaan pertemanan dari {p.get('name') or p.get('email') or 'seseorang'}", "body": "Terima atau tolak di halaman Teman.", "link": "/friends", "created_at": r.get("created_at") or now_iso(), "read": False, "live": True})
    return {"items": items, "unseen": sum(1 for i in items if not i["read"]), "seen_at": seen or None}


async def conversation_row(cid: str, uid: str) -> dict | None:
    """The same shape as one row of GET /conversations, for message_new events."""
    c = await db.conversations.find_one({"id": cid}, {"_id": 0, "invite_token": 0})
    if not c:
        return None
    c["unread"] = bool(c.get("last_message")) and (c.get("updated_at") or "") > ((c.get("read_at") or {}).get(uid) or "")
    t = (c.get("titles") or {}).get(uid)
    return {**c, "title": t} if t else c


async def task_row(task_id: str) -> dict | None:
    return await db.tasks.find_one({"id": task_id}, {"_id": 0, "id": 1, "status": 1, "goal": 1, "title": 1, "summary": 1, "steps": 1, "updated_at": 1, "type": 1, "persona_id": 1})
