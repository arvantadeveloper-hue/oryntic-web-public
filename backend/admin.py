from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from db import db
from auth import require_admin, require_platform_admin, require_platform_staff, workspace_id, public_user, member_ids
from wallet import get_packages
from llm import GPT_MODEL, IMAGE_MODEL, user_today_usage
from pricing import get_pricing, set_pricing, get_trial, set_trial, compute_rates, RATES, DEFAULT_PRICING, FEATURES, feature_table, build_packages, model_table
from llm import MODEL_CATALOG


class PackageTierIn(BaseModel):
    id: str = Field(min_length=1, max_length=32, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=40)
    usd: float = Field(gt=0, le=100000)
    discount_pct: float = Field(default=0, ge=0, le=100)
    best_value: bool = False

router = APIRouter(prefix="/api/admin", tags=["admin"])


class CreateUserIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)
    name: str | None = None


class UpdateUserIn(BaseModel):
    daily_credit_limit: int | None = None
    name: str | None = None


@router.get("/workspace-users")
async def workspace_users(admin: dict = Depends(require_admin)):
    wid = workspace_id(admin)
    ids = await member_ids(wid)
    items = await db.users.find({"id": {"$in": ids}}, {"_id": 0, "password_hash": 0}).to_list(500)
    items.sort(key=lambda i: (i["id"] != wid, i.get("created_at") or ""))
    out = []
    for i in items:
        pu = public_user(i)
        pu["is_admin"] = i["id"] == wid
        pu["role"] = "admin" if i["id"] == wid else "user"
        pu["daily_credit_limit"] = int(i.get("daily_credit_limit") or 0)
        pu["today_usage"] = await user_today_usage(i["id"])
        out.append(pu)
    return out


async def _member_or_404(uid: str, admin: dict) -> dict:
    target = await db.users.find_one({"id": uid})
    if not target or uid not in await member_ids(workspace_id(admin)):
        raise HTTPException(404, "Pengguna tidak ditemukan di workspace ini")
    return target


@router.patch("/users/{uid}")
async def update_workspace_user(uid: str, x: UpdateUserIn, admin: dict = Depends(require_admin)):
    await _member_or_404(uid, admin)
    fields = {}
    if x.daily_credit_limit is not None:
        fields["daily_credit_limit"] = max(0, int(x.daily_credit_limit))
    if x.name is not None:
        fields["name"] = x.name
    if fields:
        await db.users.update_one({"id": uid}, {"$set": fields})
    doc = await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0})
    pu = public_user(doc)
    pu["daily_credit_limit"] = int(doc.get("daily_credit_limit") or 0)
    pu["today_usage"] = await user_today_usage(uid)
    return pu


@router.get("/overview")
async def overview(_: dict = Depends(require_platform_admin)):
    users = await db.users.count_documents({})
    personas = await db.personas.count_documents({"deleted": {"$ne": True}})
    tasks = await db.tasks.count_documents({})
    conversations = await db.conversations.count_documents({})
    completed = await db.tasks.count_documents({"status": "completed"})
    failed = await db.tasks.count_documents({"status": "failed"})
    reminders = await db.reminders.count_documents({})
    # credit consumption
    consumed = 0
    breakdown = {}
    async for e in db.usage_events.find({}):
        consumed += e.get("credits", 0)
        breakdown[e["feature"]] = breakdown.get(e["feature"], 0) + e.get("credits", 0)
    return {
        "users": users, "personas": personas, "tasks": tasks, "conversations": conversations,
        "reminders": reminders, "tasks_completed": completed, "tasks_failed": failed,
        "credits_consumed": consumed,
        "usage_breakdown": [{"feature": k, "credits": v} for k, v in breakdown.items()],
    }


@router.get("/users")
async def users(_: dict = Depends(require_platform_admin)):
    items = await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)
    return items


@router.get("/personas")
async def personas(admin: dict = Depends(require_admin)):
    return await db.personas.find({"user_id": workspace_id(admin), "deleted": {"$ne": True}}, {"_id": 0, "portrait": 0, "reference_photo": 0}).sort("updated_at", -1).to_list(500)


@router.get("/tasks")
async def tasks(_: dict = Depends(require_platform_admin)):
    return await db.tasks.find({}, {"_id": 0, "steps": 0, "final_output": 0}).sort("created_at", -1).to_list(500)


class PlatformPricingIn(BaseModel):
    margin_pct: float = Field(ge=0, le=500)
    tax_pct: float = Field(ge=0, le=100)
    usd_to_idr: float = Field(gt=0)
    idr_per_credit: float = Field(gt=0)
    text_usd_per_1k_chars: float = Field(gt=0)
    image_usd: float = Field(gt=0)
    profile_usd: float = Field(gt=0)
    stt_usd: float = Field(gt=0)
    tts_usd: float = Field(gt=0)
    provider_usd_per_min: float = Field(gt=0)
    usd_per_credit: float = Field(default=0.001, gt=0)
    rt_audio_in_usd_1m: float = Field(default=32.0, ge=0)
    rt_audio_out_usd_1m: float = Field(default=64.0, ge=0)
    rt_text_in_usd_1m: float = Field(default=4.0, ge=0)
    rt_text_out_usd_1m: float = Field(default=24.0, ge=0)
    rt_cached_in_usd_1m: float = Field(default=0.4, ge=0)
    video_usd_per_sec: float = Field(default=0.80, ge=0)
    video20_usd_per_sec: float = Field(default=0.60, ge=0)
    video_res_480_mult: float = Field(default=0.6, gt=0, le=5)
    video_res_1080_mult: float = Field(default=1.6, gt=0, le=10)
    video_real_person_mult: float = Field(default=1.45, gt=0, le=10)
    video_audio_mult: float = Field(default=1.0, gt=0, le=10)
    vision_usd: float = Field(default=0.006, ge=0)
    bandwidth_usd_per_gb: float = Field(default=0.5, ge=0)
    margin_overrides: dict[str, float] = Field(default_factory=lambda: {"call_bandwidth": 50.0})
    chars_per_token: float = Field(default=4.0, ge=1, le=10)
    model_prices: dict[str, dict[str, float]] = Field(default_factory=lambda: dict(DEFAULT_PRICING["model_prices"]))
    package_margin_pct: float = Field(default=15.0, ge=0, le=500)
    package_round_idr: int = Field(default=1000, ge=1, le=1_000_000)
    packages: list[PackageTierIn] = Field(default_factory=lambda: [PackageTierIn(**t) for t in DEFAULT_PRICING["packages"]], min_length=1, max_length=12)

    @field_validator("margin_overrides")
    @classmethod
    def _known_features(cls, v: dict) -> dict:
        bad = [k for k in v if k not in FEATURES]
        if bad:
            raise ValueError(f"Fitur tidak dikenal: {', '.join(bad)}")
        if any(not (0 <= float(x) <= 500) for x in v.values()):
            raise ValueError("Margin harus 0–500%")
        return {k: float(x) for k, x in v.items()}

    @field_validator("packages")
    @classmethod
    def _unique_ids(cls, v: list) -> list:
        if len({t.id for t in v}) != len(v):
            raise ValueError("ID paket harus unik")
        return v


class TrialIn(BaseModel):
    trial_days: int = Field(ge=0, le=365)
    trial_daily_limit: int = Field(ge=0, le=100000)
    trial_credits: int = Field(ge=0, le=1000000)


@router.get("/pricing")
async def pricing(_: dict = Depends(require_platform_staff)):
    p = await get_pricing()
    return {
        "packages": await get_packages(),
        "pricing": p,
        "rates": compute_rates(p),
        "features": feature_table(p),
        "models": model_table(p, MODEL_CATALOG),
        "trial": await get_trial(),
        "providers": [
            {"provider": "OpenAI", "model": GPT_MODEL, "capability": "text", "unit": "1k chars", "rate_credits_per_1k_chars": RATES["text_per_1k"], "status": "active"},
            {"provider": "Gemini (Nano Banana)", "model": IMAGE_MODEL, "capability": "image", "unit": "image", "rate_credits": RATES["image"], "status": "active"},
            {"provider": "OpenAI", "model": "gpt-realtime-2", "capability": "realtime voice", "unit": "minute", "rate_credits": RATES["realtime_per_min"], "status": "active"},
        ],
        "tariff": {
            "profile_generation_credits": RATES["profile"], "image_generation_credits": RATES["image"],
            "text_credits_per_1k_chars": RATES["text_per_1k"],
            "method": "biaya provider × (1 + margin[fitur] atau margin global) × (1 + PPN) ÷ nilai kredit (USD); paket: USD × (1 + margin paket − diskon) × (1 + PPN) × kurs",
        },
    }


@router.put("/pricing")
async def put_pricing(x: PlatformPricingIn, _: dict = Depends(require_platform_admin)):
    p = await set_pricing(x.model_dump())
    return {"pricing": p, "rates": compute_rates(p), "features": feature_table(p), "models": model_table(p, MODEL_CATALOG), "packages": build_packages(p)}


@router.post("/pricing/preview")
async def preview_pricing(x: PlatformPricingIn, _: dict = Depends(require_platform_admin)):
    """What-if calculation for the admin platform: nothing is saved."""
    p = {**DEFAULT_PRICING, **x.model_dump()}
    return {"rates": compute_rates(p), "features": feature_table(p), "models": model_table(p, MODEL_CATALOG), "packages": build_packages(p)}


@router.put("/trial")
async def put_trial(x: TrialIn, _: dict = Depends(require_platform_admin)):
    return {"trial": await set_trial(x.model_dump())}


FEATURE_LABELS = {"chat": "Chat", "meeting_moderation": "Moderator", "meeting_summary": "Notulen", "realtime_call": "Panggilan Realtime",
                  "voice_tts": "Suara (TTS)", "voice_stt": "Transkripsi (STT)", "tts": "Suara (TTS)", "stt": "Transkripsi (STT)", "reminder_call": "Panggilan Pengingat", "image_generation": "Gambar",
                  "persona_profile": "Profil Persona", "persona_portrait": "Potret Persona", "persona_edit": "Edit Persona", "profile_generation": "Profil Persona", "video_generation": "Video", "multi_agent_task": "Tugas Agen", "task": "Tugas"}


def _aggregate_usage(events: list, wid: str):
    by_user, by_feature, daily = {}, {}, {}
    for e in events:
        actor = (e.get("meta") or {}).get("actor_id") or wid
        feat = e.get("feature") or "lainnya"
        c = int(e.get("credits") or 0)
        by_user[actor] = by_user.get(actor, 0) + c
        by_feature[feat] = by_feature.get(feat, 0) + c
        d = (e.get("created_at") or "")[:10]
        daily[d] = daily.get(d, 0) + c
    return by_user, by_feature, daily


@router.get("/usage-report")
async def usage_report(days: int = 30, admin: dict = Depends(require_admin)):
    from datetime import datetime, timezone, timedelta
    days = max(1, min(days, 365))
    wid = workspace_id(admin)
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).isoformat()
    events = await db.usage_events.find({"user_id": wid, "created_at": {"$gte": since}}, {"_id": 0, "feature": 1, "credits": 1, "meta": 1, "created_at": 1}).to_list(50000)
    members = await db.users.find({"id": {"$in": await member_ids(wid)}}, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}).to_list(500)
    names = {m["id"]: m for m in members}
    by_user, by_feature, daily = _aggregate_usage(events, wid)
    users_out = sorted([{"user_id": uid, "name": names.get(uid, {}).get("name") or "Pengguna terhapus", "email": names.get(uid, {}).get("email"),
                         "role": names.get(uid, {}).get("role") or "user", "credits": c} for uid, c in by_user.items()], key=lambda x: -x["credits"])
    feat_out = sorted([{"feature": f, "label": FEATURE_LABELS.get(f, f.replace("_", " ").title()), "credits": c} for f, c in by_feature.items()], key=lambda x: -x["credits"])
    day_list = [{"date": d, "credits": daily.get(d, 0)} for d in ((now - timedelta(days=i)).date().isoformat() for i in range(days - 1, -1, -1))]
    return {"days": days, "total": sum(by_user.values()), "events": len(events), "by_user": users_out, "by_feature": feat_out, "daily": day_list}
