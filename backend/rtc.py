import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import current_user
from db import db, now_iso, new_id

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


class PresenceIn(BaseModel):
    bytes_delta: int = Field(default=0, ge=0, le=50_000_000_000)


@router.post("/conversations/{cid}/call/presence")
async def call_presence(cid: str, x: PresenceIn = PresenceIn(), u: dict = Depends(current_user)):
    """Heartbeat (every ~30s) while in the call room. The first person in becomes the call host and pays the
    WebRTC bandwidth (provider $/GB + margin from the platform tariff → credits) reported by their browser; others join for free."""
    from chat import _can_access
    from datetime import datetime, timezone, timedelta
    from llm import record_usage
    from pricing import get_pricing, compute_rates
    conv = await db.conversations.find_one({"id": cid}, {"_id": 0})
    if not conv or not _can_access(conv, u):
        raise HTTPException(404, "Conversation not found")
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=CALL_TTL_SEC)).isoformat()
    live = {k: v for k, v in (conv.get("active_call") or {}).items() if (v.get("at") or "") > cutoff}
    host = conv.get("call_host") if conv.get("call_host") in live else None
    session_id = conv.get("call_session_id") if live else None
    if not host:
        host = u["id"]
    if not session_id:
        session_id = new_id()
    upd = {f"active_call.{u['id']}": {"name": u.get("name") or "Peserta", "at": now_iso()}, "call_host": host, "call_session_id": session_id}
    charged = 0
    if host == u["id"] and x.bytes_delta:
        p = await get_pricing()
        pending = float(conv.get("call_pending_mb") or 0) + x.bytes_delta / 1e6
        per_mb = compute_rates(p)["bandwidth_per_mb"]
        charged = int(pending * per_mb)
        if charged:
            await record_usage(u["id"], "call_bandwidth", charged, {"conversation_id": cid, "call_session_id": session_id, "mb": round(charged / per_mb, 2)})
            pending -= charged / per_mb
        upd["call_pending_mb"] = pending
    await db.conversations.update_one({"id": cid}, {"$set": upd})
    return {"ok": True, "host": host, "is_host": host == u["id"], "charged": charged, "call_session_id": session_id}


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
