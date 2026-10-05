import base64
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from auth import current_user
from db import db, now_iso
from realtime import user_manager

# Web push via Firebase Cloud Messaging (HTTP v1 through firebase-admin). Service account comes from FCM_SERVICE_ACCOUNT_B64 (base64 of the JSON key).
router = APIRouter(prefix="/api/push", tags=["push"])
log = logging.getLogger("push")
KINDS = ("reminders", "calls", "messages", "tasks")
_app = {"inst": None, "tried": False}


def configured() -> bool:
    return bool(os.environ.get("FCM_SERVICE_ACCOUNT_B64"))


def _firebase():
    if _app["inst"] or _app["tried"]:
        return _app["inst"]
    _app["tried"] = True
    try:
        import firebase_admin
        from firebase_admin import credentials
        info = json.loads(base64.b64decode(os.environ["FCM_SERVICE_ACCOUNT_B64"]))
        _app["inst"] = firebase_admin.get_app() if firebase_admin._apps else firebase_admin.initialize_app(credentials.Certificate(info))
    except Exception as e:  # noqa: BLE001
        log.error("FCM init failed: %s", e)
    return _app["inst"]


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=4096)
    platform: str = Field(default="web", max_length=20)
    ua: Optional[str] = Field(default=None, max_length=300)


class PrefsIn(BaseModel):
    reminders: bool = True
    calls: bool = True
    messages: bool = True
    tasks: bool = True


async def _prefs(uid: str) -> dict:
    row = await db.users.find_one({"id": uid}, {"_id": 0, "push_prefs": 1})
    return {k: True for k in KINDS} | ((row or {}).get("push_prefs") or {})


@router.get("/status")
async def status(u: dict = Depends(current_user)):
    n = await db.push_tokens.count_documents({"user_id": u["id"]})
    return {"configured": configured(), "devices": n, "prefs": await _prefs(u["id"])}


@router.post("/tokens")
async def register(x: TokenIn, u: dict = Depends(current_user)):
    await db.push_tokens.update_one({"token": x.token}, {"$set": {"user_id": u["id"], "platform": x.platform, "ua": x.ua, "last_seen": now_iso()},
                                                        "$setOnInsert": {"created_at": now_iso()}}, upsert=True)
    return {"ok": True}


@router.delete("/tokens")
async def unregister(x: TokenIn, u: dict = Depends(current_user)):
    await db.push_tokens.delete_one({"token": x.token, "user_id": u["id"]})
    return {"ok": True}


@router.put("/prefs")
async def set_prefs(x: PrefsIn, u: dict = Depends(current_user)):
    await db.users.update_one({"id": u["id"]}, {"$set": {"push_prefs": x.model_dump()}})
    return {"ok": True, "prefs": x.model_dump()}


@router.post("/test")
async def test_push(u: dict = Depends(current_user)):
    sent = await send_push(u["id"], "Oryntix", "Notifikasi push aktif di perangkat ini.", {"link": "/home"}, kind=None, force=True)
    return {"sent": sent}


async def send_push(uid: str, title: str, body: str, data: Optional[dict] = None, kind: Optional[str] = "messages", force: bool = False) -> int:
    """Push to all devices of a user. Skipped when the user is live on the per-user WebSocket (they already see it in-app), unless force."""
    if not configured() or not _firebase():
        return 0
    if kind and not (await _prefs(uid)).get(kind, True):
        return 0
    if not force and user_manager.online(uid):
        return 0
    rows = [r async for r in db.push_tokens.find({"user_id": uid}, {"_id": 0, "token": 1, "platform": 1})]
    tokens = [r["token"] for r in rows]
    any_native = any((r.get("platform") or "web") != "web" for r in rows)
    if not tokens:
        return 0
    from firebase_admin import messaging
    link = (data or {}).get("link") or "/home"
    msg = messaging.MulticastMessage(
        tokens=tokens,
        data={k: str(v) for k, v in {**(data or {}), "title": title, "body": body, "kind": kind or "system"}.items()},
        notification=messaging.Notification(title=title, body=body[:300]) if any_native else None,  # Android/iOS system tray; web uses webpush below
        android=messaging.AndroidConfig(priority="high", notification=messaging.AndroidNotification(tag=(data or {}).get("tag"), click_action="FLUTTER_NOTIFICATION_CLICK")) if any_native else None,
        apns=messaging.APNSConfig(payload=messaging.APNSPayload(aps=messaging.Aps(sound="default", thread_id=(data or {}).get("tag")))) if any_native else None,
        webpush=messaging.WebpushConfig(
            notification=messaging.WebpushNotification(title=title, body=body[:300], icon="/brand/mark-512.png", badge="/brand/mark-512.png", tag=(data or {}).get("tag"), renotify=bool((data or {}).get("tag"))),
            fcm_options=messaging.WebpushFCMOptions(link=link if link.startswith("http") else f"{os.environ.get('APP_URL', '').rstrip('/')}{link}" if os.environ.get("APP_URL") else link)),
    )
    try:
        res = messaging.send_each_for_multicast(msg)
    except Exception as e:  # noqa: BLE001
        log.error("FCM send failed: %s", e)
        return 0
    dead = [tokens[i] for i, r in enumerate(res.responses) if not r.success and r.exception is not None
            and ("registration-token-not-registered" in str(getattr(r.exception, "code", "")) or "Requested entity was not found" in str(r.exception) or "SenderId mismatch" in str(r.exception))]
    if dead:
        await db.push_tokens.delete_many({"token": {"$in": dead}})
    return res.success_count
