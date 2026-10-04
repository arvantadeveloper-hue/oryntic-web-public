import math
import time
from db import db, now_iso

# Platform-wide tariff engine. ONE rule for every feature:
#   credits = provider_cost_USD × (1 + margin) × (1 + tax) ÷ usd_per_credit   (rounded up)
# margin = margin_overrides[feature] when set by the platform admin, else the global margin_pct.
DEFAULT_PRICING = {
    "margin_pct": 30.0, "tax_pct": 11.0, "usd_to_idr": 18000.0, "idr_per_credit": 80.0,
    # 1 credit = $0.001 (1,000 credits = $1). idr_per_credit is kept for display only.
    "usd_per_credit": 0.001,
    # per-feature margin overrides (percent). Empty → global margin. Keys = FEATURES below.
    "margin_overrides": {"call_bandwidth": 50.0},
    # provider costs (USD)
    "text_usd_per_1k_chars": 0.00675, "image_usd": 0.084, "profile_usd": 0.026,
    "stt_usd": 0.0165, "tts_usd": 0.013, "provider_usd_per_min": 0.02,
    "vision_usd": 0.006,            # one screen snapshot shown to the assistant (~1.1k image tokens)
    "bandwidth_usd_per_gb": 0.5,    # TURN relay cost for friend calls; +50% margin → $0.75/GB
    # OpenAI gpt-realtime list prices (USD per 1M tokens): billed per response from the usage report
    "rt_audio_in_usd_1m": 32.0, "rt_audio_out_usd_1m": 64.0, "rt_text_in_usd_1m": 4.0, "rt_text_out_usd_1m": 16.0, "rt_cached_in_usd_1m": 0.4,
    "video_usd_per_sec": 0.062,
    # credit packages: price_idr = usd × (1 + package_margin − discount) × (1 + tax) × fx, rounded to package_round_idr
    "package_margin_pct": 15.0, "package_round_idr": 1000,
    "packages": [
        {"id": "starter", "name": "Starter", "usd": 3, "discount_pct": 0, "best_value": False},
        {"id": "basic", "name": "Basic", "usd": 5, "discount_pct": 0, "best_value": False},
        {"id": "plus", "name": "Plus", "usd": 10, "discount_pct": 5, "best_value": True},
        {"id": "pro", "name": "Pro", "usd": 25, "discount_pct": 10, "best_value": False},
        {"id": "ultimate", "name": "Ultimate", "usd": 50, "discount_pct": 15, "best_value": False},
    ],
}
# feature key → (label, provider-cost field, unit) — the admin platform shows "provider cost → credits charged" per row
FEATURES = {
    "text": ("Teks / chat", "text_usd_per_1k_chars", "1k karakter"),
    "image": ("Gambar", "image_usd", "gambar"),
    "profile": ("Profil persona", "profile_usd", "profil"),
    "stt": ("Transkripsi suara", "stt_usd", "permintaan"),
    "tts": ("Suara TTS", "tts_usd", "permintaan"),
    "realtime_call": ("Koneksi Realtime", "provider_usd_per_min", "menit"),
    "vision": ("Cuplikan layar ke asisten", "vision_usd", "cuplikan"),
    "call_bandwidth": ("Data panggilan teman", "bandwidth_usd_per_gb", "GB"),
    "video": ("Video Seedance", "video_usd_per_sec", "detik"),
}
DEFAULT_TRIAL = {"trial_days": 7, "trial_daily_limit": 100, "trial_credits": 700}

_cache = {"at": 0.0, "pricing": dict(DEFAULT_PRICING), "trial": dict(DEFAULT_TRIAL)}
RATES = {"text_per_1k": 2.0, "image": 25, "profile": 8, "stt": 5, "tts": 4, "realtime_per_min": 75, "vision": 9, "bandwidth_per_mb": 0.9}


def margin_for(p: dict, feature: str | None) -> float:
    ov = p.get("margin_overrides") or {}
    v = ov.get(feature) if feature else None
    return float(v if v is not None else p["margin_pct"])


def usd_to_credits(p: dict, usd: float, feature: str | None = None) -> float:
    """Provider cost × (1 + margin[feature]) × (1 + tax) ÷ value of one credit (exact, un-rounded)."""
    return usd * (1 + margin_for(p, feature) / 100) * (1 + p["tax_pct"] / 100) / max(float(p.get("usd_per_credit") or 0.001), 1e-6)


def _credits(p: dict, usd: float, feature: str) -> int:
    return max(1, math.ceil(usd_to_credits(p, usd, feature)))


def _cost(p: dict, key: str) -> float:
    return float(p.get(key) if p.get(key) is not None else DEFAULT_PRICING[key])


def realtime_usage_usd(p: dict, usage: dict) -> float:
    """Raw provider cost of one Realtime response from OpenAI's usage report."""
    i, o = usage.get("input_token_details") or {}, usage.get("output_token_details") or {}
    cached = int((i.get("cached_tokens_details") or {}).get("audio_tokens") or 0) + int((i.get("cached_tokens_details") or {}).get("text_tokens") or 0) or int(i.get("cached_tokens") or 0)
    return (max(0, int(i.get("audio_tokens") or 0) - 0) * p["rt_audio_in_usd_1m"] + int(i.get("text_tokens") or 0) * p["rt_text_in_usd_1m"]
            + int(o.get("audio_tokens") or 0) * p["rt_audio_out_usd_1m"] + int(o.get("text_tokens") or 0) * p["rt_text_out_usd_1m"]
            + cached * p["rt_cached_in_usd_1m"]) / 1_000_000


def compute_rates(p: dict) -> dict:
    return {
        "text_per_1k": round(max(0.1, usd_to_credits(p, _cost(p, "text_usd_per_1k_chars"), "text")), 2),
        "image": _credits(p, _cost(p, "image_usd"), "image"), "profile": _credits(p, _cost(p, "profile_usd"), "profile"),
        "stt": _credits(p, _cost(p, "stt_usd"), "stt"), "tts": _credits(p, _cost(p, "tts_usd"), "tts"),
        "realtime_per_min": _credits(p, _cost(p, "provider_usd_per_min"), "realtime_call"),
        "vision": _credits(p, _cost(p, "vision_usd"), "vision"),
        "bandwidth_per_mb": round(usd_to_credits(p, _cost(p, "bandwidth_usd_per_gb") / 1024, "call_bandwidth"), 4),
        "video_per_sec": round(usd_to_credits(p, _cost(p, "video_usd_per_sec"), "video"), 2),
    }


def feature_table(p: dict) -> list:
    """Admin platform view: per feature → provider cost, margin applied, credits charged (exact + rounded)."""
    out = []
    for key, (label, field, unit) in FEATURES.items():
        usd = _cost(p, field)
        exact = usd_to_credits(p, usd, key)
        out.append({"feature": key, "label": label, "unit": unit, "provider_usd": usd, "margin_pct": margin_for(p, key),
                    "override": key in (p.get("margin_overrides") or {}), "credits_exact": round(exact, 4), "credits": max(1, math.ceil(exact))})
    return out


def build_packages(p: dict) -> list:
    fx = _cost(p, "usd_to_idr")
    tax = _cost(p, "tax_pct") / 100
    pm = _cost(p, "package_margin_pct") / 100
    step = max(1, int(_cost(p, "package_round_idr")))
    usd_per_credit = max(float(p.get("usd_per_credit") or 0.001), 1e-6)
    out = []
    for t in p.get("packages") or DEFAULT_PRICING["packages"]:
        usd, disc = float(t["usd"]), float(t.get("discount_pct") or 0) / 100
        price = usd * (1 + pm - disc) * (1 + tax) * fx
        out.append({"id": t["id"], "name": t["name"], "usd": usd, "credits": int(round(usd / usd_per_credit)), "price_idr": int(round(price / step) * step),
                    "discount_pct": int(round(disc * 100)), "best_value": bool(t.get("best_value"))})
    return out


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
