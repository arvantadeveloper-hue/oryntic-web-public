"""VoIP push (PushKit) sent straight to APNs over HTTP/2 with an ES256 provider token.

FCM cannot deliver PushKit pushes, so incoming calls need this direct path to wake a terminated iOS app
and let it report the call to CallKit. Stays a no-op until APNS_* is configured.
"""
import asyncio
import json
import logging
import os
import time
from typing import Optional

import httpx
import jwt

from db import db, now_iso

log = logging.getLogger("apns")
HOSTS = {"sandbox": "https://api.sandbox.push.apple.com", "production": "https://api.push.apple.com"}
DEAD_REASONS = {"BadDeviceToken", "Unregistered", "DeviceTokenNotForTopic", "TopicDisallowed"}
_jwt: dict = {"token": None, "iat": 0.0, "kid": None}
_client: dict = {"inst": None}
_lock = asyncio.Lock()


def cfg() -> dict:
    return {"key_id": os.environ.get("APNS_KEY_ID", "").strip(), "team_id": os.environ.get("APNS_TEAM_ID", "").strip(),
            "bundle_id": os.environ.get("APNS_BUNDLE_ID", "").strip(), "env": (os.environ.get("APNS_ENV") or "sandbox").strip(),
            "p8": os.environ.get("APNS_P8", "").replace("\\n", "\n").strip()}


def configured() -> bool:
    c = cfg()
    return all((c["key_id"], c["team_id"], c["bundle_id"], c["p8"]))


def _http() -> httpx.AsyncClient:
    if _client["inst"] is None:
        _client["inst"] = httpx.AsyncClient(http2=True, timeout=httpx.Timeout(10.0))
    return _client["inst"]


async def _provider_token(c: dict, refresh: bool = False) -> str:
    """APNs provider tokens are valid for 1 hour; regenerate every 50 minutes."""
    async with _lock:
        if refresh or not _jwt["token"] or _jwt["kid"] != c["key_id"] or time.time() - _jwt["iat"] > 50 * 60:
            now = int(time.time())
            _jwt.update({"token": jwt.encode({"iss": c["team_id"], "iat": now}, c["p8"], algorithm="ES256", headers={"kid": c["key_id"]}),
                         "iat": now, "kid": c["key_id"]})
        return _jwt["token"]


async def _post(c: dict, token: str, environment: str, body: bytes, expiration: int, retry: bool = True) -> tuple[int, dict]:
    headers = {"authorization": f"bearer {await _provider_token(c)}", "apns-push-type": "voip", "apns-priority": "10",
               "apns-topic": f"{c['bundle_id']}.voip", "apns-expiration": str(expiration), "content-type": "application/json"}
    host = HOSTS.get(environment) or HOSTS["sandbox"]
    r = await _http().post(f"{host}/3/device/{token}", headers=headers, content=body)
    try:
        data = r.json() if r.content else {}
    except ValueError:
        data = {"raw": r.text[:200]}
    if retry and data.get("reason") in ("ExpiredProviderToken", "InvalidProviderToken"):
        await _provider_token(c, refresh=True)
        return await _post(c, token, environment, body, expiration, retry=False)
    return r.status_code, data


async def send_voip(uid: str, call: dict, ttl: int = 45) -> dict:
    """Ring every registered iOS device of a user. `call` is merged next to the `aps` block."""
    if not configured():
        return {"sent": 0, "devices": 0, "skipped": "APNS_* belum dikonfigurasi"}
    rows = [r async for r in db.voip_tokens.find({"user_id": uid, "active": {"$ne": False}}, {"_id": 0, "token": 1, "environment": 1})]
    if not rows:
        return {"sent": 0, "devices": 0}
    c = cfg()
    body = json.dumps({"aps": {"content-available": 1}, **call}, separators=(",", ":"), ensure_ascii=False).encode()
    if len(body) > 5000:
        log.error("VoIP payload too large: %s bytes", len(body))
        return {"sent": 0, "devices": len(rows), "error": "payload_too_large"}
    expiration = int(time.time()) + ttl
    sent, dead, errors = 0, [], []
    for r in rows:
        try:
            status, data = await _post(c, r["token"], r.get("environment") or c["env"], body, expiration)
        except Exception as e:  # noqa: BLE001
            log.error("VoIP send failed: %s", e)
            errors.append(str(e)[:120])
            continue
        if 200 <= status < 300:
            sent += 1
            continue
        reason = data.get("reason") or f"http_{status}"
        errors.append(reason)
        if status == 410 or reason in DEAD_REASONS:
            dead.append(r["token"])
        else:
            log.error("VoIP rejected (%s): %s", status, reason)
    if dead:
        await db.voip_tokens.delete_many({"user_id": uid, "token": {"$in": dead}})
    return {"sent": sent, "devices": len(rows), "pruned": len(dead), "errors": errors[:5]}


async def register(uid: str, token: str, environment: str, bundle_id: Optional[str]) -> None:
    await db.voip_tokens.update_one({"user_id": uid, "token": token},
                                    {"$set": {"environment": environment, "bundle_id": bundle_id or cfg()["bundle_id"], "platform": "ios",
                                              "active": True, "updated_at": now_iso()}, "$setOnInsert": {"created_at": now_iso()}}, upsert=True)


async def unregister(uid: str, token: str) -> None:
    await db.voip_tokens.delete_one({"user_id": uid, "token": token})
