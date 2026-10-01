import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field

from pricing import get_trial
from db import db, now_iso, new_id

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
    """The id of the workspace owner (admin). Admins own their own workspace."""
    return user.get("owner_id") or user["id"]


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
    return u


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
async def register(x: RegisterIn):
    email = str(x.email).lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "Email already registered")
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
        "role": "admin",  # self-registered accounts own their workspace; invited members get role "user"
        "owner_id": uid,
        "onboarded": False,
        "verified": True,
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
    return {"access_token": make_token(uid, "user"), "user": public_user(doc)}


@router.post("/login")
async def login(x: LoginIn):
    u = await db.users.find_one({"email": str(x.email).lower()})
    if not u or not pw_ok(x.password, u["password_hash"]):
        raise HTTPException(401, "Incorrect email or password")
    return {"access_token": make_token(u["id"], u.get("role", "user")), "user": public_user(u)}


@router.get("/me")
async def me(u: dict = Depends(current_user)):
    return public_user(u)


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
