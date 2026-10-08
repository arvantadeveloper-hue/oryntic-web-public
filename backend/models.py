from fastapi import APIRouter
from llm import MODEL_CATALOG, DEFAULT_MODEL_KEY, PROVIDERS, provider_status
from pricing import get_pricing, model_table, tool_table
import os

router = APIRouter(prefix="/api", tags=["models"])
_TOOL_ENV = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY"}


@router.get("/tools")
async def list_tools() -> dict:
    """Provider built-in tools a persona can enable, with credits per use; `available` = platform key for that provider is configured."""
    labels = {k: v["label"] for k, v in PROVIDERS.items()}
    items = [{**t, "provider_label": labels.get(t["provider"], t["provider"]), "available": bool(os.environ.get(_TOOL_ENV[t["provider"]], "").strip())} for t in tool_table(await get_pricing())]
    return {"tools": items}


@router.get("/models")
async def list_models() -> dict:
    labels = {k: v["label"] for k, v in PROVIDERS.items()}
    typical = {t["id"]: t["credits_typical"] for t in model_table(await get_pricing(), MODEL_CATALOG)}
    return {"models": [{**m, "provider_label": labels.get(m["provider"], m["provider"]), "credits_typical": typical.get(m["id"])} for m in MODEL_CATALOG], "default": DEFAULT_MODEL_KEY, "providers": provider_status()}
