import math
import time
from db import db, now_iso

# Platform-wide tariff: provider cost (USD) × (1 + margin) × (1 + tax) × FX ÷ credit value → credits (rounded up).
DEFAULT_PRICING = {
    "margin_pct": 30.0, "tax_pct": 11.0, "usd_to_idr": 16500.0, "idr_per_credit": 80.0,
    "text_usd_per_1k_chars": 0.00675, "image_usd": 0.084, "profile_usd": 0.026,
    "stt_usd": 0.0165, "tts_usd": 0.013, "provider_usd_per_min": 0.02,
    # 1 credit = $0.001 (1,000 credits = $1). idr_per_credit is kept for display only.
    "usd_per_credit": 0.001,
    # OpenAI gpt-realtime list prices (USD per 1M tokens): billed per response from the usage report
    "rt_audio_in_usd_1m": 32.0, "rt_audio_out_usd_1m": 64.0, "rt_text_in_usd_1m": 4.0, "rt_text_out_usd_1m": 16.0, "rt_cached_in_usd_1m": 0.4,
    "video_usd_per_sec": 0.062,
}
DEFAULT_TRIAL = {"trial_days": 7, "trial_daily_limit": 100, "trial_credits": 700}

_cache = {"at": 0.0, "pricing": dict(DEFAULT_PRICING), "trial": dict(DEFAULT_TRIAL)}
RATES = {"text_per_1k": 2.0, "image": 25, "profile": 8, "stt": 5, "tts": 4, "realtime_per_min": 75}


def usd_to_credits(p: dict, usd: float) -> float:
    """Provider cost × (1 + margin) × (1 + tax) ÷ value of one credit (exact, un-rounded)."""
    return usd * (1 + p["margin_pct"] / 100) * (1 + p["tax_pct"] / 100) / max(float(p.get("usd_per_credit") or 0.001), 1e-6)


def _credits(p: dict, usd: float) -> int:
    return max(1, math.ceil(usd_to_credits(p, usd)))


def realtime_usage_usd(p: dict, usage: dict) -> float:
    """Raw provider cost of one Realtime response from OpenAI's usage report."""
    i, o = usage.get("input_token_details") or {}, usage.get("output_token_details") or {}
    cached = int((i.get("cached_tokens_details") or {}).get("audio_tokens") or 0) + int((i.get("cached_tokens_details") or {}).get("text_tokens") or 0) or int(i.get("cached_tokens") or 0)
    return (max(0, int(i.get("audio_tokens") or 0) - 0) * p["rt_audio_in_usd_1m"] + int(i.get("text_tokens") or 0) * p["rt_text_in_usd_1m"]
            + int(o.get("audio_tokens") or 0) * p["rt_audio_out_usd_1m"] + int(o.get("text_tokens") or 0) * p["rt_text_out_usd_1m"]
            + cached * p["rt_cached_in_usd_1m"]) / 1_000_000


def compute_rates(p: dict) -> dict:
    return {
        "text_per_1k": round(max(0.1, usd_to_credits(p, p["text_usd_per_1k_chars"])), 2),
        "image": _credits(p, p["image_usd"]), "profile": _credits(p, p["profile_usd"]),
        "stt": _credits(p, p["stt_usd"]), "tts": _credits(p, p["tts_usd"]),
        "realtime_per_min": _credits(p, p["provider_usd_per_min"]),
        "video_per_sec": round(usd_to_credits(p, p["video_usd_per_sec"]), 2),
    }


async def refresh(force: bool = False):
    if not force and time.time() - _cache["at"] < 30:
        return
    cfg = await db.config.find_one({"id": "platform_pricing"}, {"_id": 0, "id": 0, "updated_at": 0})
    tr = await db.config.find_one({"id": "trial_config"}, {"_id": 0, "id": 0, "updated_at": 0})
    _cache["pricing"] = {**DEFAULT_PRICING, **(cfg or {})}
    _cache["trial"] = {**DEFAULT_TRIAL, **(tr or {})}
    _cache["at"] = time.time()
    RATES.update(compute_rates(_cache["pricing"]))


async def get_pricing() -> dict:
    await refresh()
    return dict(_cache["pricing"])


async def get_trial() -> dict:
    await refresh()
    return dict(_cache["trial"])


async def set_pricing(doc: dict) -> dict:
    await db.config.update_one({"id": "platform_pricing"}, {"$set": {**doc, "updated_at": now_iso()}}, upsert=True)
    await refresh(force=True)
    return dict(_cache["pricing"])


async def set_trial(doc: dict) -> dict:
    await db.config.update_one({"id": "trial_config"}, {"$set": {**doc, "updated_at": now_iso()}}, upsert=True)
    await refresh(force=True)
    return dict(_cache["trial"])


def rate(key: str) -> int:
    return int(RATES[key])
