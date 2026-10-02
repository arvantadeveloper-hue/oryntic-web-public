import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Annotated, Optional

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field

from pricing import get_trial
from ratelimit import login_allowed
from db import db, now_iso, new_id
from mailer import send_email, verification_email, debug_links

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ISSUER = "aivora-api"
ACCESS_DAYS = 7
STARTING_CREDITS = 500

router = APIRouter(prefix="/api/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


# ---------- helpers ----------
def pw_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def pw_ok(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def make_token(user_id: str, role: str) -> str:
    t = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user_id,
            "role": role,
            "iss": JWT_ISSUER,
            "iat": t,
            "exp": t + timedelta(days=ACCESS_DAYS),
        },
        JWT_SECRET,
        algorithm="HS256",
    )


def public_user(u: dict) -> dict:
    return {
        "id": u["id"],
        "email": u["email"],
        "name": u.get("name"),
        "role": u.get("role", "user"),
        "owner_id": u.get("owner_id") or u["id"],
        "is_admin": u.get("role") == "admin",
        "is_home_workspace": (u.get("owner_id") or u["id"]) == u["id"],
        "verified": u.get("verified", True),
        "onboarded": u.get("onboarded", False),
        "settings": u.get("settings", {}),
        "credits": u.get("credits", 0),
        "is_platform_admin": is_platform_admin(u),
        "plan": u.get("plan") or ("paid" if u.get("role") == "admin" else "member"),
        "trial_ends_at": u.get("trial_ends_at"),
        "daily_credit_limit": int(u.get("daily_credit_limit") or 0),
    }


def is_platform_admin(u: dict) -> bool:
    return (u.get("email") or "").lower() == os.environ["ADMIN_EMAIL"].lower()


def workspace_id(user: dict) -> str:
    """The id of the active workspace's owner. Every account owns its own (home) workspace and may join others."""
    return user.get("owner_id") or user["id"]


async def member_ids(wid: str) -> list:
    """Owner + everyone who accepted an invitation to this workspace."""
    rows = await db.workspace_members.find({"workspace_id": wid, "status": "joined"}, {"_id": 0, "user_id": 1}).to_list(1000)
    return [wid] + [r["user_id"] for r in rows if r["user_id"] != wid]


async def is_member(user_id: str, wid: str) -> bool:
    return user_id == wid or bool(await db.workspace_members.find_one({"workspace_id": wid, "user_id": user_id, "status": "joined"}))


def role_for(u: dict) -> str:
    return "admin" if (u.get("owner_id") or u["id"]) == u["id"] else "user"


def app_url(request: Request, hint: Optional[str] = None) -> str:
    """Public frontend URL for email links: APP_URL env (production), else the URL the browser reports, else Origin."""
    return (os.environ.get("APP_URL") or hint or request.headers.get("origin") or "").rstrip("/")


def token_hash(raw: str) -> str:
    return sha256(raw.encode()).hexdigest()


async def issue_verification(user: dict, base_url: str) -> dict:
    raw = secrets.token_urlsafe(32)
    await db.email_tokens.delete_many({"purpose": "verify", "email": user["email"]})
    await db.email_tokens.insert_one({"purpose": "verify", "email": user["email"], "token_hash": token_hash(raw), "created_at": now_iso()})
    link = f"{base_url}/verify-email?token={raw}"
    subject, html, text = verification_email(user.get("name") or "", link)
    sent = await send_email(user["email"], subject, html, text)
    return {"mail_sent": sent, **({"debug_link": link} if debug_links() else {})}


LANG_NAMES = {"id": "Bahasa Indonesia", "en": "English", "es": "Spanish", "fr": "French",
              "de": "German", "pt": "Portuguese", "ar": "Arabic", "ja": "Japanese",
              "ko": "Korean", "zh": "Chinese", "hi": "Hindi", "ru": "Russian", "it": "Italian"}


def _lang_name(user: dict) -> str:
    code = ((user.get("settings", {}) or {}).get("conversation_language") or "id").lower()
    return LANG_NAMES.get(code, LANG_NAMES.get(code.split("-")[0], "Bahasa Indonesia"))


# ---------- models ----------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)
    name: Optional[str] = None
    app_url: Optional[str] = Field(default=None, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class OnboardIn(BaseModel):
    name: Optional[str] = None
    app_language: str = "id"
    conversation_language: str = "id"
    timezone: str = "Asia/Jakarta"
    voice: Optional[str] = None
    interests: Optional[str] = None


# ---------- dependency ----------
async def current_user(
    creds: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer)]
) -> dict:
    if not creds:
        raise HTTPException(401, "Not authenticated")
    try:
        p = jwt.decode(
            creds.credentials,
            JWT_SECRET,
            algorithms=["HS256"],
            issuer=JWT_ISSUER,
            options={"require": ["sub", "exp", "iat", "iss"]},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid or expired token")
    u = await db.users.find_one({"id": p["sub"]}, {"_id": 0})
    if not u:
        raise HTTPException(401, "User not found")
    u["role"] = role_for(u)
    return u


async def optional_user(creds: Annotated[Optional[HTTPAuthorizationCredentials], Depends(bearer)]) -> Optional[dict]:
    if not creds:
        return None
    try:
        return await current_user(creds)
    except HTTPException:
        return None


async def require_admin(u: dict = Depends(current_user)) -> dict:
    if u.get("role") != "admin":
        raise HTTPException(403, "Admin access required")
    return u


async def require_platform_admin(u: dict = Depends(current_user)) -> dict:
    """Platform operator (ADMIN_EMAIL): global tariffs, rate limits, trial config, cross-workspace views."""
    if not is_platform_admin(u):
        raise HTTPException(403, "Platform admin access required")
    return u


# ---------- routes ----------
@router.post("/register")
async def register(x: RegisterIn, request: Request):
    email = str(x.email).lower()
    existing = await db.users.find_one({"email": email})
    if existing and existing.get("verified", True):
        raise HTTPException(409, "Email already registered")
    if existing:  # unverified leftover: refresh credentials and resend the link
        await db.users.update_one({"id": existing["id"]}, {"$set": {"password_hash": pw_hash(x.password), "name": x.name or existing.get("name")}})
        out = await issue_verification({**existing, "name": x.name or existing.get("name")}, app_url(request, x.app_url))
        return {"pending_verification": True, "email": email, **out}
    trial = await get_trial()
    uid = new_id()
    doc = {
        "plan": "trial",
        "trial_ends_at": (datetime.now(timezone.utc) + timedelta(days=int(trial["trial_days"]))).isoformat(),
        "daily_credit_limit": int(trial["trial_daily_limit"]),
        "id": uid,
        "email": email,
        "password_hash": pw_hash(x.password),
        "name": x.name or email.split("@")[0],
        "role": "admin",  # self-registered accounts own their workspace; in other workspaces they act as members
        "owner_id": uid,
        "onboarded": False,
        "verified": False,
        "credits": int(trial["trial_credits"]),
        "settings": {
            "app_language": "id",
            "conversation_language": "id",
            "timezone": "Asia/Jakarta",
            "theme": "dark",
        },
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    await db.credit_transactions.insert_one({
        "id": new_id(), "user_id": uid, "type": "grant", "amount": int(trial["trial_credits"]),
        "balance_after": int(trial["trial_credits"]), "description": f"Paket percobaan {trial['trial_days']} hari", "created_at": now_iso(),
    })
    out = await issue_verification(doc, app_url(request, x.app_url))
    return {"pending_verification": True, "email": email, **out}


class EmailIn(BaseModel):
    email: EmailStr
    app_url: Optional[str] = Field(default=None, max_length=200)


@router.post("/resend-verification")
async def resend_verification(x: EmailIn, request: Request):
    ip = (request.headers.get("x-forwarded-for") or request.client.host or "?").split(",")[0].strip()
    email = str(x.email).lower()
    if not login_allowed(ip, email):
        raise HTTPException(429, "Terlalu banyak percobaan. Coba lagi dalam 5 menit.")
    u = await db.users.find_one({"email": email}, {"_id": 0})
    out = await issue_verification(u, app_url(request, x.app_url)) if u and not u.get("verified", True) else {}
    return {"ok": True, **out}


@router.get("/verify-email")
async def verify_email(token: str):
    row = await db.email_tokens.find_one_and_delete({"purpose": "verify", "token_hash": token_hash(token)})
    if not row:
        raise HTTPException(400, "Tautan verifikasi tidak valid atau sudah dipakai")
    await db.users.update_one({"email": row["email"]}, {"$set": {"verified": True, "verified_at": now_iso()}})
    u = await db.users.find_one({"email": row["email"]}, {"_id": 0})
    if not u:
        raise HTTPException(404, "Akun tidak ditemukan")
    u["role"] = role_for(u)
    return {"access_token": make_token(u["id"], u["role"]), "user": public_user(u)}


@router.post("/login")
async def login(x: LoginIn, request: Request):
    email = str(x.email).lower()
    ip = (request.headers.get("x-forwarded-for") or request.client.host or "?").split(",")[0].strip()
    if not login_allowed(ip, email):
        raise HTTPException(429, "Terlalu banyak percobaan login. Coba lagi dalam 5 menit.")
    u = await db.users.find_one({"email": email})
    if not u or not pw_ok(x.password, u["password_hash"]):
        raise HTTPException(401, "Incorrect email or password")
    if not u.get("verified", True):
        raise HTTPException(403, {"code": "unverified", "message": "Email belum diverifikasi. Cek kotak masuk Anda atau kirim ulang tautan verifikasi."})
    u["role"] = role_for(u)
    return {"access_token": make_token(u["id"], u["role"]), "user": public_user(u)}


@router.get("/workspaces")
async def my_workspaces(u: dict = Depends(current_user)):
    """Home workspace + every workspace the user has joined."""
    rows = await db.workspace_members.find({"user_id": u["id"], "status": "joined"}, {"_id": 0, "workspace_id": 1, "joined_at": 1}).to_list(100)
    ids = [u["id"]] + [r["workspace_id"] for r in rows if r["workspace_id"] != u["id"]]
    owners = {o["id"]: o async for o in db.users.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "email": 1})}
    active = workspace_id(u)
    return [{"id": wid, "name": (owners.get(wid) or {}).get("name") or "Workspace", "owner_email": (owners.get(wid) or {}).get("email"),
             "is_home": wid == u["id"], "active": wid == active, "role": "admin" if wid == u["id"] else "user"} for wid in ids if wid in owners]


class SwitchIn(BaseModel):
    workspace_id: str


@router.post("/switch-workspace")
async def switch_workspace(x: SwitchIn, u: dict = Depends(current_user)):
    if not await is_member(u["id"], x.workspace_id):
        raise HTTPException(403, "Anda bukan anggota workspace ini")
    await db.users.update_one({"id": u["id"]}, {"$set": {"owner_id": x.workspace_id, "role": "admin" if x.workspace_id == u["id"] else "user"}})
    u2 = await db.users.find_one({"id": u["id"]}, {"_id": 0})
    u2["role"] = role_for(u2)
    return {"access_token": make_token(u2["id"], u2["role"]), "user": public_user(u2)}


@router.get("/me")
async def me(u: dict = Depends(current_user)):
    return public_user(u)


class SettingsIn(BaseModel):
    mic_sensitivity: Optional[str] = Field(default=None, pattern="^(low|medium|high)$")
    noise_suppression: Optional[bool] = None
    smart_routing: Optional[bool] = None  # workspace owner: auto-route topics to the best model
    notulen_fields: Optional[list] = Field(default=None, max_length=12)  # [{name, required}]
    daily_digest: Optional[dict] = None  # {enabled, channel: chat|call|both, time: "HH:MM", persona_id}


@router.put("/settings")
async def update_settings(x: SettingsIn, u: dict = Depends(current_user)):
    settings = u.get("settings", {}) or {}
    data = x.model_dump()
    if data.get("notulen_fields") is not None:
        data["notulen_fields"] = [{"name": str(f.get("name", ""))[:60].strip(), "required": bool(f.get("required"))} for f in data["notulen_fields"] if str(f.get("name", "")).strip()]
    if data.get("daily_digest") is not None:
        d = data["daily_digest"]
        ch = d.get("channel") if d.get("channel") in ("chat", "call", "both") else "chat"
        tm = str(d.get("time") or "07:00")
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", tm):
            raise HTTPException(400, "Format jam harus HH:MM")
        data["daily_digest"] = {"enabled": bool(d.get("enabled")), "channel": ch, "time": tm, "persona_id": d.get("persona_id") or None}
    settings.update({k: v for k, v in data.items() if v is not None})
    await db.users.update_one({"id": u["id"]}, {"$set": {"settings": settings}})
    return public_user(await db.users.find_one({"id": u["id"]}, {"_id": 0}))


@router.post("/onboard")
async def onboard(x: OnboardIn, u: dict = Depends(current_user)):
    settings = u.get("settings", {})
    settings.update({
        "app_language": x.app_language,
        "conversation_language": x.conversation_language,
        "timezone": x.timezone,
        "voice": x.voice,
        "interests": x.interests,
    })
    update = {"onboarded": True, "settings": settings}
    if x.name:
        update["name"] = x.name
    await db.users.update_one({"id": u["id"]}, {"$set": update})
    u2 = await db.users.find_one({"id": u["id"]}, {"_id": 0})
    return public_user(u2)


async def seed_admin():
    email = os.environ["ADMIN_EMAIL"].lower()
    existing = await db.users.find_one({"email": email})
    if not existing:
        uid = new_id()
        await db.users.insert_one({
            "id": uid, "email": email, "password_hash": pw_hash(os.environ["ADMIN_PASSWORD"]),
            "name": "Oryntix Admin", "role": "admin", "owner_id": uid, "onboarded": True, "verified": True,
            "credits": 100000,
            "settings": {"app_language": "en", "conversation_language": "en", "timezone": "Asia/Jakarta", "theme": "dark"},
            "created_at": now_iso(),
        })
    await migrate_workspace()


async def migrate_workspace():
    """Promote the demo account to admin and backfill owner_id so every account owns a workspace."""
    demo = await db.users.find_one({"email": "demo@aivora.ai"})
    if demo:
        await db.users.update_one({"id": demo["id"]}, {"$set": {"role": "admin", "owner_id": demo["id"]}})
    # any user without an owner_id becomes the owner of their own workspace
    await db.users.update_many({"owner_id": {"$exists": False}}, [{"$set": {"owner_id": "$id"}}])
    # workspace owners (owner_id == own id) are admins of their workspace
    await db.users.update_many({"role": {"$ne": "admin"}, "$expr": {"$eq": ["$owner_id", "$id"]}}, {"$set": {"role": "admin"}})
    # tasks created before multi-workspace: attach to the creator's workspace
    async for t in db.tasks.find({"workspace_id": {"$exists": False}}, {"_id": 0, "id": 1, "user_id": 1}):
        owner = await db.users.find_one({"id": t["user_id"]}, {"_id": 0, "owner_id": 1}) or {}
        await db.tasks.update_one({"id": t["id"]}, {"$set": {"workspace_id": owner.get("owner_id") or t["user_id"]}})
    # UI wording: "Meeting" → "Panggilan" in stored conversation titles
    async for c in db.conversations.find({"title": {"$regex": "^Meeting: "}}, {"_id": 0, "id": 1, "title": 1}):
        await db.conversations.update_one({"id": c["id"]}, {"$set": {"title": "Panggilan: " + c["title"][len("Meeting: "):]}})
    # accounts created before email verification existed stay active
    await db.users.update_many({"verified": {"$exists": False}}, {"$set": {"verified": True}})
    # legacy members (owner_id != id) get an explicit joined membership so they can also use their home workspace
    async for m in db.users.find({"$expr": {"$ne": ["$owner_id", "$id"]}}, {"_id": 0, "id": 1, "owner_id": 1, "email": 1, "created_at": 1}):
        await db.workspace_members.update_one({"workspace_id": m["owner_id"], "user_id": m["id"]},
                                              {"$setOnInsert": {"id": new_id(), "email": m["email"], "status": "joined", "joined_at": m.get("created_at") or now_iso(), "legacy": True}}, upsert=True)
