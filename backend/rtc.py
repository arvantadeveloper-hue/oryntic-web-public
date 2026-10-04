import os

import httpx
from fastapi import APIRouter, Depends, HTTPException

from auth import current_user
from db import db, now_iso

router = APIRouter(prefix="/api", tags=["rtc"])
STUN_ONLY = [{"urls": "stun:stun.l.google.com:19302"}, {"urls": "stun:stun1.l.google.com:19302"}]


@router.get("/rtc/ice-servers")
async def ice_servers(u: dict = Depends(current_user)):
    """ICE servers for human↔human WebRTC audio. Metered TURN when configured (secret stays server-side), else STUN only."""
    app_name, key = os.environ.get("METERED_APP_NAME"), os.environ.get("METERED_CREDENTIAL_API_KEY")
    if not app_name or not key:
        return {"iceServers": STUN_ONLY, "turn": False}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"https://{app_name}.metered.live/api/v1/turn/credentials", params={"apiKey": key})
            r.raise_for_status()
            servers = r.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(502, "Penyedia TURN menolak permintaan") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "Penyedia TURN tidak tersedia") from exc
    if not isinstance(servers, list) or not all(isinstance(x, dict) and "urls" in x for x in servers):
        raise HTTPException(502, "Respons TURN tidak valid")
    return {"iceServers": servers, "turn": True}


@router.get("/notifications/badges")
async def badges(u: dict = Depends(current_user)):
    """Sidebar badges: pending friend requests + unread chats."""
    friend_requests = await db.friends.count_documents({"addressee_id": u["id"], "status": "pending"})
    unread = 0
    async for c in db.conversations.find({"$or": [{"user_id": u["id"]}, {"participants": u["id"]}], "archived_conv": {"$ne": True}, "last_message": {"$nin": ["", None]}},
                                         {"_id": 0, "updated_at": 1, "read_at": 1, "last_sender_id": 1}):
        if c.get("last_sender_id") == u["id"]:
            continue
        if (c.get("updated_at") or "") > ((c.get("read_at") or {}).get(u["id"]) or ""):
            unread += 1
    return {"friend_requests": friend_requests, "unread_chats": unread, "at": now_iso()}


CALL_TTL_SEC = 120


@router.post("/conversations/{cid}/call/presence")
async def call_presence(cid: str, u: dict = Depends(current_user)):
    """Heartbeat (every ~30s) while the user is inside the call room → other participants get an incoming-call ring."""
    from chat import _can_access
    conv = await db.conversations.find_one({"id": cid}, {"_id": 0})
    if not conv or not _can_access(conv, u):
        raise HTTPException(404, "Conversation not found")
    await db.conversations.update_one({"id": cid}, {"$set": {f"active_call.{u['id']}": {"name": u.get("name") or "Peserta", "at": now_iso()}}})
    return {"ok": True}


@router.post("/conversations/{cid}/call/leave")
async def call_leave(cid: str, u: dict = Depends(current_user)):
    await db.conversations.update_one({"id": cid}, {"$unset": {f"active_call.{u['id']}": ""}})
    return {"ok": True}


@router.get("/calls/incoming")
async def incoming_calls(u: dict = Depends(current_user)):
    """Group/DM calls that other humans are currently in (fresh heartbeat) and I have not joined."""
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=CALL_TTL_SEC)).isoformat()
    out = []
    async for c in db.conversations.find({"participants": u["id"], "active_call": {"$exists": True, "$ne": {}}, "archived_conv": {"$ne": True}},
                                         {"_id": 0, "id": 1, "title": 1, "titles": 1, "type": 1, "members": 1, "active_call": 1, "persona_ids": 1}):
        live = {uid: p for uid, p in (c.get("active_call") or {}).items() if (p.get("at") or "") > cutoff}
        if not live or u["id"] in live:
            continue
        out.append({"conversation_id": c["id"], "title": (c.get("titles") or {}).get(u["id"]) or c.get("title"), "type": c.get("type"),
                    "callers": [p["name"] for p in live.values()], "assistants": [m["name"] for m in c.get("members") or []], "started_at": min(p["at"] for p in live.values())})
    return out
