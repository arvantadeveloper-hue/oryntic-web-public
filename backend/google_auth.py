import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
import httpx
import jwt
from db import db, now_iso, new_id
from auth import JWT_SECRET, make_token, public_user, role_for, current_user, get_trial, convert_email_invites

# "Masuk dengan Google" via the owner's own OAuth client (authorization-code flow, backend exchanges the code).
# REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
# The redirect_uri is always sent by the browser as window.location.origin + "/auth/google".
router = APIRouter(prefix="/api/auth/google", tags=["auth-google"])
GAUTH, GTOKEN, USERINFO = "https://accounts.google.com/o/oauth2/v2/auth", "https://oauth2.googleapis.com/token", "https://www.googleapis.com/oauth2/v3/userinfo"
LOGIN_SCOPES = "openid email profile"


def configured() -> bool:
    return bool(os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"))


class StartIn(BaseModel):
    redirect_uri: str = Field(min_length=10, max_length=300)


class ExchangeIn(BaseModel):
    code: str = Field(min_length=4, max_length=2000)
    state: str = Field(min_length=10, max_length=2000)
    redirect_uri: str = Field(min_length=10, max_length=300)


@router.get("/status")
async def status():
    return {"enabled": configured()}


@router.post("/start")
async def start(x: StartIn):
    if not configured():
        raise HTTPException(503, "Login Google belum dikonfigurasi (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET).")
    state = jwt.encode({"purpose": "glogin", "exp": int(time.time()) + 600, "nonce": new_id()}, JWT_SECRET, algorithm="HS256")
    q = httpx.QueryParams({"client_id": os.environ["GOOGLE_CLIENT_ID"], "redirect_uri": x.redirect_uri, "response_type": "code", "scope": LOGIN_SCOPES,
                           "state": state, "prompt": "select_account", "include_granted_scopes": "true"})
    return {"authorization_url": f"{GAUTH}?{q}"}


async def _google_identity(code: str, redirect_uri: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(GTOKEN, data={"code": code, "client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"], "redirect_uri": redirect_uri, "grant_type": "authorization_code"})
        if r.status_code != 200:
            raise HTTPException(400, "Kode Google tidak valid atau kedaluwarsa. Coba masuk lagi.")
        me = (await c.get(USERINFO, headers={"Authorization": f"Bearer {r.json()['access_token']}"})).json()
    if not me.get("sub") or not me.get("email"):
        raise HTTPException(400, "Google tidak mengembalikan identitas akun")
    if not me.get("email_verified", False):
        raise HTTPException(403, "Email akun Google ini belum diverifikasi oleh Google")
    return me


async def _new_google_user(me: dict) -> dict:
    trial = await get_trial()
    uid = new_id()
    doc = {"plan": "trial", "trial_ends_at": (datetime.now(timezone.utc) + timedelta(days=int(trial["trial_days"]))).isoformat(), "daily_credit_limit": int(trial["trial_daily_limit"]),
           "id": uid, "email": me["email"].lower(), "password_hash": None, "name": me.get("name") or me["email"].split("@")[0], "avatar": me.get("picture"),
           "role": "admin", "owner_id": uid, "onboarded": False, "verified": True, "verified_at": now_iso(), "credits": int(trial["trial_credits"]),
           "google_sub": me["sub"], "google_email": me["email"].lower(), "google_picture": me.get("picture"), "auth_provider": "google",
           "settings": {"app_language": "id", "conversation_language": "id", "timezone": "Asia/Jakarta", "theme": "dark"}, "created_at": now_iso()}
    await db.users.insert_one(dict(doc))
    await convert_email_invites(doc)
    await db.credit_transactions.insert_one({"id": new_id(), "user_id": uid, "type": "grant", "amount": int(trial["trial_credits"]), "balance_after": int(trial["trial_credits"]),
                                             "description": f"Paket percobaan {trial['trial_days']} hari", "created_at": now_iso()})
    return doc


@router.post("/exchange")
async def exchange(x: ExchangeIn):
    """Browser lands on /auth/google?code&state → sends both here → we verify, upsert the user and return our JWT."""
    try:
        if jwt.decode(x.state, JWT_SECRET, algorithms=["HS256"]).get("purpose") != "glogin":
            raise jwt.InvalidTokenError()
    except jwt.InvalidTokenError:
        raise HTTPException(400, "Sesi login Google tidak valid. Coba lagi.")
    me = await _google_identity(x.code, x.redirect_uri)
    email = me["email"].lower()
    u = await db.users.find_one({"google_sub": me["sub"]}) or await db.users.find_one({"email": email})
    created = False
    if u:
        if u.get("disabled"):
            raise HTTPException(403, "Akun ini dinonaktifkan. Hubungi dukungan Oryntix.")
        upd = {"google_sub": me["sub"], "google_email": email, "google_picture": me.get("picture"), "last_login_at": now_iso()}
        if not u.get("verified", True):
            upd.update(verified=True, verified_at=now_iso())  # Google already verified this email
        await db.users.update_one({"id": u["id"]}, {"$set": upd})
        u = await db.users.find_one({"id": u["id"]})
    else:
        u, created = await _new_google_user(me), True
    u["role"] = role_for(u)
    return {"access_token": make_token(u["id"], u["role"]), "user": public_user(u), "created": created}


@router.get("/linked")
async def linked(u: dict = Depends(current_user)):
    row = await db.users.find_one({"id": u["id"]}, {"_id": 0, "google_email": 1, "google_picture": 1})
    return {"linked": bool((row or {}).get("google_email")), "email": (row or {}).get("google_email"), "picture": (row or {}).get("google_picture")}
