"""Platform tariff, trial and rate-limit endpoints (mirrors /api/admin/* of the main Oryntix backend; both share the same MongoDB config collection)."""
from fastapi import APIRouter, Depends
from typing import Optional
from pydantic import BaseModel, Field, field_validator

from auth import require_platform_admin, require_platform_staff
from model_catalog import MODEL_CATALOG, GPT_MODEL, IMAGE_MODEL
from pricing import get_pricing, set_pricing, get_trial, set_trial, compute_rates, RATES, DEFAULT_PRICING, FEATURES, feature_table, build_packages, model_table, REALTIME_MODELS, realtime_model_prices, realtime_credits_per_min, tool_table
from ratelimit import get_limits, set_limits
from behaviour import get_behaviour, set_behaviour, BehaviourIn

router = APIRouter(prefix="/api/admin", tags=["admin-pricing"])


async def get_packages():
    return build_packages(await get_pricing())


class PackageTierIn(BaseModel):
    id: str = Field(min_length=1, max_length=32, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=40)
    usd: float = Field(gt=0, le=100000)
    discount_pct: float = Field(default=0, ge=0, le=100)
    best_value: bool = False

router = APIRouter(prefix="/api/admin", tags=["admin"])


class PlatformPricingIn(BaseModel):
    margin_pct: float = Field(ge=0, le=500)
    tax_pct: float = Field(ge=0, le=100)
    usd_to_idr: float = Field(gt=0)
    realtime_models: Optional[dict] = None  # {model_id: {audio_in, audio_out, text_in, text_out, cached_in}} USD/1M overrides per voice model
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
    tool_prices: dict[str, float] = Field(default_factory=lambda: dict(DEFAULT_PRICING["tool_prices"]))  # USD per use of a provider built-in tool
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
        "realtime_models": [{"id": k, **realtime_model_prices(p, k), "credits_per_min": realtime_credits_per_min(p, k)} for k in REALTIME_MODELS],
        "tools": tool_table(p),
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
    return {"pricing": p, "rates": compute_rates(p), "features": feature_table(p), "models": model_table(p, MODEL_CATALOG), "packages": build_packages(p), "tools": tool_table(p)}


@router.post("/pricing/preview")
async def preview_pricing(x: PlatformPricingIn, _: dict = Depends(require_platform_admin)):
    """What-if calculation for the admin platform: nothing is saved."""
    p = {**DEFAULT_PRICING, **x.model_dump()}
    return {"rates": compute_rates(p), "features": feature_table(p), "models": model_table(p, MODEL_CATALOG), "packages": build_packages(p), "tools": tool_table(p)}


@router.put("/trial")
async def put_trial(x: TrialIn, _: dict = Depends(require_platform_admin)):
    return {"trial": await set_trial(x.model_dump())}


class LimitsIn(BaseModel):
    chat_per_min: int = Field(ge=1, le=1000)
    chat_per_hour: int = Field(default=300, ge=1, le=100_000)
    chat_min_interval_ms: int = Field(default=1500, ge=0, le=60_000)
    chat_max_inflight: int = Field(default=4, ge=1, le=50)
    chat_dup_per_30s: int = Field(default=3, ge=1, le=100)
    voice_per_min: int = Field(ge=1, le=1000)
    calls_per_hour: int = Field(ge=1, le=1000)
    max_call_minutes: int = Field(ge=1, le=600)
    generation_per_hour: int = Field(ge=1, le=1000)
    storage_quota_mb: int = Field(default=50, ge=1, le=100_000)


@router.get("/admin/rate-limits")
async def admin_limits(_: dict = Depends(require_platform_admin)):
    return await get_limits()


@router.put("/admin/rate-limits")
async def admin_set_limits(x: LimitsIn, _: dict = Depends(require_platform_admin)):
    return await set_limits(x.model_dump())


@router.get("/rate-limits")
async def admin_limits(_: dict = Depends(require_platform_admin)):
    return await get_limits()


@router.put("/rate-limits")
async def admin_set_limits(x: LimitsIn, _: dict = Depends(require_platform_admin)):
    return await set_limits(x.model_dump())


@router.get("/realtime-behaviour")
async def admin_behaviour(_: dict = Depends(require_platform_staff)):
    return await get_behaviour()


@router.put("/realtime-behaviour")
async def admin_set_behaviour(x: BehaviourIn, _: dict = Depends(require_platform_admin)):
    return await set_behaviour(x.model_dump())
