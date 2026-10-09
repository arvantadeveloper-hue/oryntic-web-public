import base64
import json
import logging
import os
import time
from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import apns_voip
from auth import current_user
from db import db, now_iso, new_id
from realtime import user_manager

# Web push via Firebase Cloud Messaging (HTTP v1 through firebase-admin). Service account comes from FCM_SERVICE_ACCOUNT_B64 (base64 of the JSON key).
router = APIRouter(prefix="/api/push", tags=["push"])
log = logging.getLogger("push")
KINDS = ("reminders", "calls", "messages", "tasks")
# Android notification channels the mobile app must create with matching ids (calls = IMPORTANCE_HIGH + full-screen intent).
CHANNELS = {"calls": "oryntix_calls", "reminders": "oryntix_reminders", "messages": "oryntix_messages", "tasks": "oryntix_tasks", "friends": "oryntix_social"}
CATEGORIES = {"calls": "ORYNTIX_CALL", "reminders": "ORYNTIX_REMINDER", "messages": "ORYNTIX_MESSAGE", "tasks": "ORYNTIX_TASK", "friends": "ORYNTIX_SOCIAL"}
CALL_TTL_SEC = 45
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
    voip = await db.voip_tokens.count_documents({"user_id": u["id"], "active": {"$ne": False}})
    return {"configured": configured(), "devices": n, "prefs": await _prefs(u["id"]),
            "voip_configured": apns_voip.configured(), "voip_devices": voip, "voip_env": apns_voip.cfg()["env"]}


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


class VoipTokenIn(BaseModel):
    token: str = Field(min_length=32, max_length=512, pattern="^[0-9a-fA-F]+$")  # PushKit token as lowercase hex
    environment: Literal["sandbox", "production"] = "sandbox"
    bundle_id: Optional[str] = Field(default=None, max_length=120)


@router.post("/voip-tokens")
async def register_voip(x: VoipTokenIn, u: dict = Depends(current_user)):
    await apns_voip.register(u["id"], x.token.lower(), x.environment, x.bundle_id)
    return {"ok": True, "configured": apns_voip.configured()}


@router.delete("/voip-tokens")
async def unregister_voip(x: VoipTokenIn, u: dict = Depends(current_user)):
    await apns_voip.unregister(u["id"], x.token.lower())
    return {"ok": True}


@router.post("/voip-test")
async def test_voip(u: dict = Depends(current_user)):
    """Rings this user's own iPhone with a VoIP push so the mobile app can verify PushKit + CallKit."""
    return await apns_voip.send_voip(u["id"], {"call_id": new_id(), "conversation_id": "", "caller": "Oryntix", "caller_id": u["id"],
                                               "handle": u.get("email") or "oryntix", "kind": "calls", "test": "1", "link": "/home"})


async def send_call_push(uid: str, *, caller: str, conversation_id: str, call_id: str, persona_id: Optional[str] = None,
                         title: Optional[str] = None, body: Optional[str] = None) -> dict:
    """Ring one user: PushKit VoIP (iOS, works with the app terminated) + high-priority FCM (Android/web)."""
    data = {"link": f"/chat/{conversation_id}", "tag": f"call-{conversation_id}", "call_id": call_id,
            "conversation_id": conversation_id, "caller": caller, "handle": caller}
    if persona_id:
        data["persona_id"] = persona_id
    voip = await apns_voip.send_voip(uid, {**data, "kind": "calls"})
    fcm = await send_push(uid, title or f"Panggilan masuk dari {caller}", body or "Ketuk untuk bergabung", data, kind="calls")
    return {"voip": voip, "fcm": fcm}


async def log_notification(uid: str, title: str, body: str, data: Optional[dict], kind: Optional[str]) -> None:
    """In-app notification log (feeds the bell panel). Same source as FCM pushes; tag → one entry per conversation/thread."""
    from realtime import notify_user
    data = data or {}
    doc = {"user_id": uid, "title": title, "body": (body or "")[:300], "link": data.get("link") or "/home", "kind": kind or "system", "tag": data.get("tag"), "created_at": now_iso()}
    if doc["tag"]:
        await db.notifications.update_one({"user_id": uid, "tag": doc["tag"]}, {"$set": doc, "$setOnInsert": {"id": new_id()}}, upsert=True)
    else:
        await db.notifications.insert_one({"id": new_id(), **doc})
    await notify_user(uid, {"type": "notification", "title": title, "kind": doc["kind"], "link": doc["link"]})


async def send_push(uid: str, title: str, body: str, data: Optional[dict] = None, kind: Optional[str] = "messages", force: bool = False) -> int:
    """Push to all devices of a user. Skipped when the user is live on the per-user WebSocket (they already see it in-app), unless force."""
    if kind:
        await log_notification(uid, title, body, data, kind)
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
    urow = await db.users.find_one({"id": uid}, {"_id": 0, "settings": 1}) or {}
    muted = bool((urow.get("settings") or {}).get("mute_sounds"))
    from firebase_admin import messaging
    link = (data or {}).get("link") or "/home"
    tag = (data or {}).get("tag")
    is_call = kind == "calls"
    channel = CHANNELS.get(kind or "", "oryntix_default")
    bundle = os.environ.get("APNS_BUNDLE_ID", "").strip()
    apns_headers = {"apns-priority": "10", "apns-push-type": "alert"}
    if bundle:
        apns_headers["apns-topic"] = bundle
    if tag:
        apns_headers["apns-collapse-id"] = str(tag)[:64]
    if is_call:
        apns_headers["apns-expiration"] = str(int(time.time()) + CALL_TTL_SEC)
    msg = messaging.MulticastMessage(
        tokens=tokens,
        data={k: str(v) for k, v in {**(data or {}), "title": title, "body": body, "kind": kind or "system", "silent": "1" if muted else "0"}.items()},
        notification=messaging.Notification(title=title, body=body[:300]) if any_native else None,  # Android/iOS system tray; web uses webpush below
        android=messaging.AndroidConfig(
            priority="high",  # wake the app even when swiped away / in Doze
            ttl=timedelta(seconds=CALL_TTL_SEC) if is_call else timedelta(hours=6),
            collapse_key=str(tag) if tag else None,
            direct_boot_ok=True,
            notification=messaging.AndroidNotification(
                tag=tag, channel_id=channel, priority="max" if is_call else "high", visibility="public",
                notification_count=None, icon="ic_notification", color="#2F6BFF",
                **({"default_sound": False, "default_vibrate_timings": False} if muted else {"default_sound": True, "default_vibrate_timings": True}))) if any_native else None,
        apns=messaging.APNSConfig(
            headers=apns_headers,
            payload=messaging.APNSPayload(aps=messaging.Aps(
                alert=messaging.ApsAlert(title=title, body=body[:300]),
                sound=None if muted else "default",
                content_available=True,   # lets the app refresh state in the background
                mutable_content=True,     # notification-service-extension can enrich (avatar, caller photo)
                category=CATEGORIES.get(kind or "", "ORYNTIX"),
                thread_id=tag))) if any_native else None,
        webpush=messaging.WebpushConfig(
            notification=messaging.WebpushNotification(title=title, body=body[:300], icon="/brand/mark-512.png", badge="/brand/mark-512.png", tag=tag, renotify=bool(tag) and not muted, silent=muted, vibrate=[] if muted else None),
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
