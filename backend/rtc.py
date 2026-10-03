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
