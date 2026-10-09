import math
import time
import pricing_catalog as pc
from db import db, now_iso

# Platform-wide tariff engine. Provider prices live ONLY in the price catalog (pricing_catalog.py / config.pricing_catalog);
# this document holds the global multipliers:
#   credits = provider_cost_USD × (1 + margin) × (1 + tax) ÷ usd_per_credit
# margin = margin_overrides[feature] when set by the platform admin, else the global margin_pct.
DEFAULT_PRICING = {
    "margin_pct": 30.0, "tax_pct": 11.0, "usd_to_idr": 18000.0, "idr_per_credit": 80.0,
    # 1 credit = $0.001 (1,000 credits = $1). idr_per_credit is kept for display only.
    "usd_per_credit": 0.001,
    # per-feature margin overrides (percent). Empty → global margin. Keys = FEATURES below.
    "margin_overrides": {"call_bandwidth": 50.0},
    # video option multipliers on the 720p/normal per-second price (provider: real-person ≈ ×1.43–1.44)
    "video_res_480_mult": 0.6, "video_res_1080_mult": 1.6, "video_real_person_mult": 1.45, "video_audio_mult": 1.0,
    "chars_per_token": 4.0,  # ~4 chars per token when billing text by characters
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
# feature key → (label, unit) — provider cost comes from pc.FEATURE_COMPONENT[feature]
FEATURES = {
    "text": ("Teks / chat (model tanpa harga)", "1k karakter"),
    "image": ("Gambar", "gambar"),
    "profile": ("Profil persona", "profil"),
    "stt": ("Transkripsi suara", "permintaan"),
    "tts": ("Suara TTS", "permintaan"),
    "realtime_call": ("Panggilan suara GPT-Live", "menit"),
    "vision": ("Cuplikan layar ke asisten", "cuplikan"),
    "call_bandwidth": ("Data panggilan teman", "GB"),
    "video20": ("Video Seedance 2.0", "detik"),
    "video": ("Video Seedance 2.5", "detik"),
}
LEGACY_PRICE_KEYS = ("text_usd_per_1k_chars", "image_usd", "profile_usd", "stt_usd", "tts_usd", "provider_usd_per_min", "vision_usd", "bandwidth_usd_per_gb",
                     "rt_audio_in_usd_1m", "rt_audio_out_usd_1m", "rt_text_in_usd_1m", "rt_text_out_usd_1m", "rt_cached_in_usd_1m",
                     "video_usd_per_sec", "video20_usd_per_sec", "model_prices", "tool_prices", "realtime_models")
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


TOKEN_CAP_FREE = 4096  # OpenAI Realtime max per response; balances that cover this many output tokens get no cap at all


def affordable_tokens(p: dict, remaining_credits: float, usd_per_1m_out: float, feature: str, cap: int = TOKEN_CAP_FREE) -> int | None:
    """Output tokens the remaining balance can still pay for. None = don't cap (balance covers ≥ cap tokens)."""
    per_token = usd_to_credits(p, float(usd_per_1m_out or 0) / 1_000_000, feature)
    if per_token <= 0:
        return None
    n = int(max(0.0, float(remaining_credits or 0)) / per_token)
    return None if n >= cap else max(1, n)


def _credits(p: dict, usd: float, feature: str) -> int:
    return max(1, math.ceil(usd_to_credits(p, usd, feature)))


def _cost(p: dict, key: str) -> float:
    return float(p.get(key) if p.get(key) is not None else DEFAULT_PRICING[key])


def feature_cost(p: dict, feature: str) -> float:
    """Provider cost of one unit of a feature, from the price catalog (0 when the component is missing/disabled)."""
    usd = pc.feature_usd(feature, p)
    return usd if usd is not None else 0.0


# Realtime voice models (labels only — every price comes from the catalog service with the same id; gpt-live-1 → catalog "gpt-live")
REALTIME_MODELS = {
    "gpt-live-1": {"label": "GPT-Live", "tagline": "Model suara terbaru (default)", "catalog_id": "gpt-live"},
    "gpt-realtime-2.1": {"label": "GPT Realtime 2.1", "tagline": "Kualitas terbaik"},
    "gpt-realtime-2.1-mini": {"label": "GPT Realtime 2.1 Mini", "tagline": "Cepat & hemat"},
    "gpt-realtime-2.0": {"label": "GPT Realtime 2.0", "tagline": "Generasi sebelumnya"},
}
DEFAULT_REALTIME_MODEL = "gpt-live-1"
LIVE_MODEL = "gpt-live-1"


def is_live_model(model: str | None) -> bool:
    return (model or "").startswith("gpt-live")


def realtime_model_prices(p: dict, model: str | None) -> dict:
    """Catalog prices of a Realtime model: per-1M-token components (legacy models) or per_min_usd (GPT-Live)."""
    key = model or DEFAULT_REALTIME_MODEL
    base = REALTIME_MODELS.get(key) or REALTIME_MODELS[DEFAULT_REALTIME_MODEL]
    out = {**base, "audio_in": 0.0, "audio_out": 0.0, "text_in": 0.0, "text_out": 0.0, "cached_in": 0.0}
    for field in ("audio_in", "audio_out", "text_in", "text_out", "cached_in"):
        hit = pc.find(key, field)
        if hit:
            out[field] = float(hit[2]["usd"])
    pm = pc.find(base.get("catalog_id") or key, "per_minute")
    if pm:
        out["per_min_usd"] = float(pm[2]["usd"])
    return out


def realtime_credits_per_min(p: dict, model: str | None) -> int:
    """Credits/minute shown in the UI (and charged per second by the tick)."""
    m = realtime_model_prices(p, model)
    if m.get("per_min_usd") is not None:  # GPT-Live: flat per-minute session price
        return max(1, math.ceil(usd_to_credits(p, m["per_min_usd"], "realtime_call")))
    # legacy token-billed Realtime models: ~1 min of speech ≈ 600 audio-in + 1,200 audio-out tokens → shown as an estimate
    return max(1, math.ceil(usd_to_credits(p, (600 * m["audio_in"] + 1200 * m["audio_out"]) / 1_000_000, "realtime_call")))


def realtime_usage_usd(p: dict, usage: dict, model: str | None = None) -> float:
    """Raw provider cost of one Realtime response from OpenAI's usage report (prices of the session's model)."""
    i, o = usage.get("input_token_details") or {}, usage.get("output_token_details") or {}
    if is_live_model(model):
        return 0.0  # voice is billed per second by the tick; backend tokens via backend_usage_usd
    cached = int((i.get("cached_tokens_details") or {}).get("audio_tokens") or 0) + int((i.get("cached_tokens_details") or {}).get("text_tokens") or 0) or int(i.get("cached_tokens") or 0)
    m = realtime_model_prices(p, model)
    return (int(i.get("audio_tokens") or 0) * m["audio_in"] + int(i.get("text_tokens") or 0) * m["text_in"]
            + int(o.get("audio_tokens") or 0) * m["audio_out"] + int(o.get("text_tokens") or 0) * m["text_out"]
            + cached * m["cached_in"]) / 1_000_000


def backend_usage_usd(p: dict, usage: dict, model_key: str | None) -> float:
    """Provider cost of one GPT-Live delegated Responses call (Responses usage shape) on the persona's brain model."""
    mp = model_price(p, model_key) or {"in": 0.0, "out": 0.0}
    cached = int((usage.get("input_tokens_details") or {}).get("cached_tokens") or 0)
    ci = pc.find(model_key or "", "cached_in")
    cached_usd = float(ci[2]["usd"]) if ci else mp["in"] * 0.1
    return (max(0, int(usage.get("input_tokens") or 0) - cached) * mp["in"] + int(usage.get("output_tokens") or 0) * mp["out"] + cached * cached_usd) / 1_000_000


def model_price(p: dict, model_key: str | None) -> dict | None:
    """In/out USD per 1M tokens for a persona brain, from the price catalog (None when the model is not listed)."""
    ci, co = pc.find(model_key or "", "text_in"), pc.find(model_key or "", "text_out")
    if ci and co:
        return {"in": float(ci[2]["usd"]), "out": float(co[2]["usd"])}
    return None


def model_text_credits(p: dict, model_key: str | None, in_chars: int, out_chars: int) -> float | None:
    """Exact credits for one exchange on a specific model (None when the model has no catalog price → caller falls back to the text-default rate)."""
    cpt = max(1.0, float(p.get("chars_per_token") or 4.0))
    ci = pc.credits(model_key or "", "text_in", in_chars / cpt, p, "text")
    co = pc.credits(model_key or "", "text_out", out_chars / cpt, p, "text")
    if ci is not None and co is not None:
        return ci + co
    return None


# Provider-hosted tools a persona can switch on (id = "provider:tool"); the model decides when to call them.
TOOL_CATALOG = [
    {"id": "openai:web_search", "provider": "openai", "label": "Pencarian web", "desc": "Mencari informasi terbaru di internet dengan sitasi.", "unit": "pencarian"},
    {"id": "openai:code_interpreter", "provider": "openai", "label": "Code Interpreter", "desc": "Menjalankan Python untuk hitungan, analisis data & grafik.", "unit": "sesi"},
    {"id": "openai:file_search", "provider": "openai", "label": "Pencarian dokumen", "desc": "Menjawab dari dokumen pengetahuan asisten lewat vector store OpenAI (unggah di tab Pengetahuan).", "unit": "pencarian"},
    {"id": "openai:image_generation", "provider": "openai", "label": "Pembuatan gambar (GPT Image)", "desc": "Membuat/mengedit gambar langsung di dalam jawaban.", "unit": "gambar"},
    {"id": "gemini:google_search", "provider": "gemini", "label": "Google Search", "desc": "Grounding jawaban dengan hasil Google Search terbaru.", "unit": "permintaan"},
    {"id": "gemini:code_execution", "provider": "gemini", "label": "Eksekusi kode", "desc": "Menjalankan Python di sandbox Google (hanya biaya token).", "unit": "permintaan"},
    {"id": "anthropic:web_search", "provider": "anthropic", "label": "Pencarian web", "desc": "Claude mencari di web dan mengutip sumbernya.", "unit": "pencarian"},
    {"id": "anthropic:code_execution", "provider": "anthropic", "label": "Eksekusi kode", "desc": "Menjalankan Python di sandbox Anthropic.", "unit": "permintaan"},
]
TOOL_BY_ID = {t["id"]: t for t in TOOL_CATALOG}


def tool_usd(p: dict, tool_id: str) -> float:
    """Provider cost of ONE use of a provider tool, from the catalog (0 when unlisted/disabled = billed as tokens only)."""
    hit = pc.find(tool_id, "per_call") or pc.find(tool_id, "per_search") or pc.find(tool_id, "per_request") \
        or pc.find(tool_id, "per_session") or pc.find(tool_id, "per_image") or pc.find(tool_id, "per_hour")
    if hit:
        _, s, c = hit
        q = pc.quote(s["id"], c["id"], 1, p, "text")
        if q:
            return q["base_usd"]
    return 0.0


def tool_credits(p: dict, tool_id: str) -> int:
    """Credits charged for ONE use of a provider tool (0 when the provider bills it as tokens only)."""
    usd = tool_usd(p, tool_id)
    return math.ceil(usd_to_credits(p, usd, "text")) if usd > 0 else 0


def tool_table(p: dict) -> list:
    return [{**t, "usd": tool_usd(p, t["id"]), "credits": tool_credits(p, t["id"])} for t in TOOL_CATALOG]


def model_table(p: dict, catalog: list) -> list:
    """Admin platform view: per model → list price in/out, credits per 1k chars in/out and for a typical exchange (2k in + 600 out chars)."""
    out = []
    for m in catalog:
        mp = model_price(p, m["id"]) or {"in": 0.0, "out": 0.0}
        out.append({"id": m["id"], "label": m["label"], "provider": m["provider"], "in_usd_1m": mp["in"], "out_usd_1m": mp["out"],
                    "credits_in_per_1k": round(model_text_credits(p, m["id"], 1000, 0) or 0, 3), "credits_out_per_1k": round(model_text_credits(p, m["id"], 0, 1000) or 0, 3),
                    "credits_typical": max(1, math.ceil(model_text_credits(p, m["id"], 2000, 600) or 0))})
    return out


def compute_rates(p: dict) -> dict:
    return {
        "text_per_1k": round(max(0.1, usd_to_credits(p, feature_cost(p, "text"), "text")), 2),
        "image": _credits(p, feature_cost(p, "image"), "image"), "profile": _credits(p, feature_cost(p, "profile"), "profile"),
        "stt": _credits(p, feature_cost(p, "stt"), "stt"), "tts": _credits(p, feature_cost(p, "tts"), "tts"),
        "realtime_per_min": _credits(p, feature_cost(p, "realtime_call"), "realtime_call"),
        "vision": _credits(p, feature_cost(p, "vision"), "vision"),
        "bandwidth_per_mb": round(usd_to_credits(p, feature_cost(p, "call_bandwidth") / 1024, "call_bandwidth"), 4),
        "video_per_sec": round(usd_to_credits(p, feature_cost(p, "video"), "video"), 2),
        "video20_per_sec": round(usd_to_credits(p, feature_cost(p, "video20"), "video20"), 2),
        "video_res_mult": {"480p": float(p.get("video_res_480_mult") or 0.6), "720p": 1.0, "1080p": float(p.get("video_res_1080_mult") or 1.6)},
        "video_real_person_mult": float(p.get("video_real_person_mult") or 1.45),
        "video_audio_mult": float(p.get("video_audio_mult") or 1.0),
    }


def feature_table(p: dict) -> list:
    """Admin platform view: per feature → provider cost, margin applied, credits charged (exact + rounded)."""
    out = []
    for key, (label, unit) in FEATURES.items():
        usd = feature_cost(p, key)
        exact = usd_to_credits(p, usd, key)
        src = pc.FEATURE_COMPONENT.get(key)
        out.append({"feature": key, "label": label, "unit": unit, "provider_usd": usd, "margin_pct": margin_for(p, key),
                    "source": f"{src[0]}/{src[1]}" if src and pc.find(src[0], src[1]) else "tidak ada di katalog",
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
    if cfg and any(k in cfg for k in LEGACY_PRICE_KEYS):  # one-off: provider prices moved to the catalog
        await db.config.update_one({"id": "platform_pricing"}, {"$unset": {k: "" for k in LEGACY_PRICE_KEYS}})
        cfg = {k: v for k, v in cfg.items() if k not in LEGACY_PRICE_KEYS}
    tr = await db.config.find_one({"id": "trial_config"}, {"_id": 0, "id": 0, "updated_at": 0})
    await pc.refresh(force=force)
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
