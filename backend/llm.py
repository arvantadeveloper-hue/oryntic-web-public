import os
import json
from typing import Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from emergentintegrations.llm.openai import OpenAISpeechToText, OpenAITextToSpeech
import io
from datetime import datetime, timezone

from pricing import RATES
from db import db, now_iso, new_id

EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
GPT_MODEL = os.environ.get("GPT_MODEL", "gpt-5.4")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gemini-3.1-flash-image-preview")

# Model catalog — the selectable "brain" for each persona (grouped by provider in the UI).
MODEL_CATALOG = [
    {"id": "gpt-astra", "label": "GPT Astra", "provider": "openai", "model": "gpt-6-astra",
     "tagline": "Paling cerdas untuk tugas kompleks", "accent": "#7C3AED"},
    {"id": "gpt-luna", "label": "GPT Luna", "provider": "openai", "model": "gpt-6-luna",
     "tagline": "Seimbang, kreatif & ekspresif", "accent": "#2F6BFF"},
    {"id": "gpt-terra", "label": "GPT Terra", "provider": "openai", "model": "gpt-5.6-terra",
     "tagline": "Cepat & efisien untuk harian", "accent": "#22B8FF"},
    {"id": "gpt-5-5", "label": "GPT 5.5", "provider": "openai", "model": "gpt-5.5",
     "tagline": "Generasi sebelumnya, stabil & hemat", "accent": "#60A5FA"},
    {"id": "claude-opus-5-5", "label": "Claude Opus 5.5", "provider": "anthropic", "model": "claude-opus-5-5",
     "tagline": "Flagship Anthropic — reasoning terdalam", "accent": "#D97706"},
    {"id": "claude-sonnet", "label": "Claude Sonnet 5.5", "provider": "anthropic", "model": "claude-sonnet-5-5",
     "tagline": "Penulisan & analisis mendalam", "accent": "#F59E0B"},
    {"id": "claude-opus-5", "label": "Claude Opus 5", "provider": "anthropic", "model": "claude-opus-5",
     "tagline": "Opus generasi 5, sangat teliti", "accent": "#B45309"},
    {"id": "claude-sonnet-5", "label": "Claude Sonnet 5", "provider": "anthropic", "model": "claude-sonnet-5",
     "tagline": "Sonnet generasi 5, seimbang", "accent": "#FBBF24"},
    {"id": "claude-opus-4-8", "label": "Claude Opus 4.8", "provider": "anthropic", "model": "claude-opus-4-8",
     "tagline": "Coding & agentic yang matang", "accent": "#92400E"},
    {"id": "claude-haiku", "label": "Claude Haiku 4.5", "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
     "tagline": "Sangat cepat & ringan", "accent": "#FCD34D"},
    {"id": "claude-fable", "label": "Claude Fable 5.1", "provider": "anthropic", "model": "claude-fable-5-1",
     "tagline": "Kreatif untuk cerita & naskah", "accent": "#F97316"},
    {"id": "gemini-pro", "label": "Gemini 3.1 Pro", "provider": "gemini", "model": "gemini-3.1-pro-preview",
     "tagline": "Multimodal & reasoning kuat", "accent": "#10B981"},
    {"id": "gemini-3-8-flash", "label": "Gemini 3.8 Flash", "provider": "gemini", "model": "gemini-3.8-flash",
     "tagline": "Flash terbaru, cepat & cerdas", "accent": "#059669"},
    {"id": "gemini-3-7-flash", "label": "Gemini 3.7 Flash", "provider": "gemini", "model": "gemini-3.7-flash",
     "tagline": "Flash cepat untuk tugas harian", "accent": "#34D399"},
    {"id": "gemini-3-6-flash", "label": "Gemini 3.6 Flash", "provider": "gemini", "model": "gemini-3.6-flash",
     "tagline": "Flash hemat dengan konteks besar", "accent": "#6EE7B7"},
    {"id": "gemini-3-5-flash", "label": "Gemini 3.5 Flash", "provider": "gemini", "model": "gemini-3.5-flash",
     "tagline": "Cepat, hemat & multimodal", "accent": "#2DD4BF"},
    {"id": "gemini-3-flash", "label": "Gemini 3 Flash", "provider": "gemini", "model": "gemini-3-flash-preview",
     "tagline": "Flash generasi 3", "accent": "#14B8A6"},
]
PROVIDERS = {"openai": {"label": "OpenAI", "env": "OPENAI_API_KEY"}, "anthropic": {"label": "Anthropic Claude", "env": "ANTHROPIC_API_KEY"}, "gemini": {"label": "Google Gemini", "env": "GEMINI_API_KEY"}}
DEFAULT_MODEL_KEY = "gpt-terra"
_MODEL_BY_ID = {m["id"]: m for m in MODEL_CATALOG}


def provider_key(provider: str) -> str:
    """Platform's own provider key when configured, else the Emergent universal key."""
    return os.environ.get(PROVIDERS.get(provider, {}).get("env", ""), "").strip() or EMERGENT_LLM_KEY


def provider_status() -> list:
    return [{"id": k, "label": v["label"], "key_source": "platform" if os.environ.get(v["env"], "").strip() else "universal"} for k, v in PROVIDERS.items()]


def resolve_model(model_key: str | None):
    m = _MODEL_BY_ID.get(model_key or DEFAULT_MODEL_KEY) or _MODEL_BY_ID[DEFAULT_MODEL_KEY]
    return m["provider"], m["model"]


def model_label(model_key: str | None) -> str:
    m = _MODEL_BY_ID.get(model_key or DEFAULT_MODEL_KEY) or _MODEL_BY_ID[DEFAULT_MODEL_KEY]
    return m["label"]

# credit metering (credits are usage units, not money)
TEXT_CREDITS_PER_1K_CHARS = 2.0   # applied on input+output chars
IMAGE_CREDITS = 25
PROFILE_CREDITS = 8
STT_CREDITS = 5
TTS_CREDITS = 4
VISION_CREDITS = 6


def _extract_text(resp) -> str:
    if resp is None:
        return ""
    if isinstance(resp, str):
        return resp
    return getattr(resp, "text", None) or getattr(resp, "content", None) or str(resp)


def text_credits(input_text: str, output_text: str, model_key: str | None = None) -> float:
    """Exact (fractional) credits for one text exchange — no rounding, no minimum; the wallet carries the remainder."""
    from pricing import model_text_credits, _cache as _pricing_cache
    exact = model_text_credits(_pricing_cache["pricing"], model_key, len(input_text or ""), len(output_text or "")) if model_key else None
    if exact is None:
        chars = len(input_text or "") + len(output_text or "")
        exact = chars / 1000 * RATES["text_per_1k"]
    return round(max(0.0, float(exact)), 6)


async def record_usage(user_id: str, feature: str, credits: float, meta: dict | None = None):
    """Record a metered usage event and deduct credits from the WORKSPACE OWNER's wallet.

    Credits are billed as exact fractions: only whole credits leave the wallet, the remainder is carried
    in `users.credits_frac` until it reaches 1. Returns balance_after (whole credits).
    """
    exact = round(max(0.0, float(credits or 0)), 6)
    actor = await db.users.find_one({"id": user_id})
    owner_id = (actor.get("owner_id") if actor else None) or user_id
    owner = await db.users.find_one({"id": owner_id}) or actor
    balance = int(owner.get("credits", 0)) if owner else 0
    carried = float(owner.get("credits_frac") or 0.0) if owner else 0.0
    total = carried + exact
    whole = int(total // 1)
    frac = round(total - whole, 6)
    new_balance = max(0, balance - whole)
    await db.users.update_one({"id": owner_id}, {"$set": {"credits": new_balance, "credits_frac": frac}})
    meta = dict(meta or {})
    if owner_id != user_id:
        meta["actor_id"] = user_id
    await db.usage_events.insert_one({
        "id": new_id(), "user_id": owner_id, "feature": feature, "credits": whole, "credits_exact": exact,
        "meta": meta, "created_at": now_iso(),
    })
    if whole:
        await db.credit_transactions.insert_one({
            "id": new_id(), "user_id": owner_id, "type": "usage", "amount": -whole,
            "balance_after": new_balance, "description": f"Usage: {feature}",
            "meta": meta, "created_at": now_iso(),
        })
    return new_balance


async def user_today_usage(user_id: str) -> float:
    """Exact credits consumed by this user (as actor) so far today (UTC), fractions included."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    q = {"created_at": {"$gte": today}, "$or": [
        {"meta.actor_id": user_id},
        {"$and": [{"user_id": user_id}, {"meta.actor_id": {"$exists": False}}]},
    ]}
    events = await db.usage_events.find(q).to_list(10000)
    return round(sum(float(e.get("credits_exact", e.get("credits", 0)) or 0) for e in events), 4)


def quota_message(over: dict) -> str:
    if over.get("trial_expired"):
        return "Masa percobaan workspace Anda telah berakhir. Beli paket kredit di menu Kredit untuk melanjutkan."
    return f"Kuota kredit harian Anda habis ({round(float(over['used']))}/{over['limit']}). Hubungi admin atau coba lagi besok."


async def _workspace_owner(user: dict) -> dict:
    if user.get("role") == "admin":
        return user
    return await db.users.find_one({"id": user.get("owner_id")}, {"_id": 0, "plan": 1, "trial_ends_at": 1}) or {}


def _trial_expired(owner: dict) -> bool:
    ends = owner.get("trial_ends_at") or ""
    return owner.get("plan") == "trial" and bool(ends) and ends < now_iso()


async def _daily_limit_hit(user: dict):
    limit = int(user.get("daily_credit_limit") or 0)
    if limit <= 0:
        return None
    used = await user_today_usage(user["id"])
    return {"used": used, "limit": limit} if used >= limit else None


async def quota_exceeded(user: dict):
    """Return {used, limit} if the user is over their daily credit quota (members, and owners on a trial plan), else None."""
    if _trial_expired(await _workspace_owner(user)):
        return {"used": 0, "limit": 0, "trial_expired": True}
    if user.get("role") == "admin" and user.get("plan") != "trial":
        return None
    return await _daily_limit_hit(user)


async def owner_balance_exact(user: dict) -> float:
    """Workspace wallet balance including the carried fraction (whole credits + credits_frac)."""
    owner_id = user.get("owner_id") or user["id"]
    owner = await db.users.find_one({"id": owner_id}, {"_id": 0, "credits": 1, "credits_frac": 1}) or {}
    return float(owner.get("credits") or 0) + float(owner.get("credits_frac") or 0)


async def llm_text(system_message: str, user_text: str, model_key: str | None = None, max_tokens: int | None = None) -> str:
    provider, model = resolve_model(model_key)
    chat = LlmChat(
        api_key=provider_key(provider),
        session_id=new_id(),
        system_message=system_message,
    ).with_model(provider, model)
    if max_tokens:
        chat = chat.with_params(max_completion_tokens=int(max_tokens))
    resp = await chat.send_message(UserMessage(text=user_text))
    return _extract_text(resp).strip()


async def llm_json(system_message: str, user_text: str, model_key: str | None = None) -> dict:
    sys = system_message + "\n\nYou MUST respond with ONLY valid JSON. No markdown fences, no commentary."
    raw = await llm_text(sys, user_text, model_key)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    # extract the outermost JSON object
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start:end + 1]
    try:
        return json.loads(raw)
    except Exception:
        return {}


async def generate_image(prompt: str, reference_b64: Optional[str] = None, aspect_ratio: Optional[str] = None, image_size: Optional[str] = None) -> Optional[str]:
    """Returns a data URL string (data:image/png;base64,...) or None."""
    params = {"modalities": ["image", "text"]}
    if aspect_ratio or image_size:
        params["image_config"] = {k: v for k, v in (("aspect_ratio", aspect_ratio), ("image_size", image_size)) if v}
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=new_id(),
        system_message="You are an expert character portrait artist.",
    ).with_model("gemini", IMAGE_MODEL).with_params(**params)

    if reference_b64:
        msg = UserMessage(text=prompt, file_contents=[ImageContent(reference_b64)])
    else:
        msg = UserMessage(text=prompt)

    text, images = await chat.send_message_multimodal_response(msg)
    if images:
        img = images[0]
        mime = img.get("mime_type", "image/png")
        return f"data:{mime};base64,{img['data']}"
    return None


async def transcribe_audio(data: bytes, filename: str = "audio.webm", language: str = "id") -> str:
    stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
    f = io.BytesIO(data)
    f.name = filename
    kwargs = {"file": f, "model": "whisper-1", "response_format": "json", "temperature": 0}
    if language:
        kwargs["language"] = language
    resp = await stt.transcribe(**kwargs)
    return (getattr(resp, "text", None) or "").strip()


async def synthesize_speech(text: str, voice: str = "alloy") -> bytes:
    tts = OpenAITextToSpeech(api_key=EMERGENT_LLM_KEY)
    return await tts.generate_speech(text=text[:4096], model="tts-1", voice=voice)


async def describe_image(b64: str) -> str:
    chat = LlmChat(api_key=provider_key("gemini"), session_id=new_id(),
                   system_message="You describe images factually for use as chat context.").with_model("gemini", "gemini-3.1-pro-preview")
    try:
        resp = await chat.send_message(UserMessage(text="Describe this image in detail (objects, text, context).", file_contents=[ImageContent(b64)]))
        return _extract_text(resp).strip()
    except Exception:
        return ""
