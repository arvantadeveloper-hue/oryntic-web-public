import os
import json
import base64
import math
from typing import Optional

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

from db import db, now_iso, new_id

EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
GPT_MODEL = os.environ.get("GPT_MODEL", "gpt-5.4")
IMAGE_MODEL = os.environ.get("IMAGE_MODEL", "gemini-3.1-flash-image-preview")

# Model catalog — the selectable "brain" for each persona.
MODEL_CATALOG = [
    {"id": "gpt-astra", "label": "GPT Astra", "provider": "openai", "model": "gpt-6-astra",
     "tagline": "Paling cerdas untuk tugas kompleks", "accent": "#7C3AED"},
    {"id": "gpt-luna", "label": "GPT Luna", "provider": "openai", "model": "gpt-6-luna",
     "tagline": "Seimbang, kreatif & ekspresif", "accent": "#2F6BFF"},
    {"id": "gpt-terra", "label": "GPT Terra", "provider": "openai", "model": "gpt-5.6-terra",
     "tagline": "Cepat & efisien untuk harian", "accent": "#22B8FF"},
    {"id": "claude-sonnet", "label": "Claude Sonnet", "provider": "anthropic", "model": "claude-sonnet-5-5",
     "tagline": "Penulisan & analisis mendalam", "accent": "#F59E0B"},
    {"id": "gemini-pro", "label": "Gemini Pro", "provider": "gemini", "model": "gemini-3.1-pro-preview",
     "tagline": "Multimodal & reasoning kuat", "accent": "#10B981"},
]
DEFAULT_MODEL_KEY = "gpt-terra"
_MODEL_BY_ID = {m["id"]: m for m in MODEL_CATALOG}


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
MIN_CREDITS = 1


def _extract_text(resp) -> str:
    if resp is None:
        return ""
    if isinstance(resp, str):
        return resp
    return getattr(resp, "text", None) or getattr(resp, "content", None) or str(resp)


def text_credits(input_text: str, output_text: str) -> int:
    chars = len(input_text or "") + len(output_text or "")
    return max(MIN_CREDITS, math.ceil(chars / 1000 * TEXT_CREDITS_PER_1K_CHARS))


async def record_usage(user_id: str, feature: str, credits: int, meta: dict | None = None):
    """Record a usage event and deduct credits from the wallet ledger. Returns balance_after."""
    user = await db.users.find_one({"id": user_id})
    balance = int(user.get("credits", 0)) if user else 0
    new_balance = max(0, balance - credits)
    await db.users.update_one({"id": user_id}, {"$set": {"credits": new_balance}})
    await db.usage_events.insert_one({
        "id": new_id(), "user_id": user_id, "feature": feature, "credits": credits,
        "meta": meta or {}, "created_at": now_iso(),
    })
    await db.credit_transactions.insert_one({
        "id": new_id(), "user_id": user_id, "type": "usage", "amount": -credits,
        "balance_after": new_balance, "description": f"Usage: {feature}",
        "meta": meta or {}, "created_at": now_iso(),
    })
    return new_balance


async def llm_text(system_message: str, user_text: str, model_key: str | None = None) -> str:
    provider, model = resolve_model(model_key)
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=new_id(),
        system_message=system_message,
    ).with_model(provider, model)
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


async def generate_image(prompt: str, reference_b64: Optional[str] = None) -> Optional[str]:
    """Returns a data URL string (data:image/png;base64,...) or None."""
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=new_id(),
        system_message="You are an expert character portrait artist.",
    ).with_model("gemini", IMAGE_MODEL).with_params(modalities=["image", "text"])

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
