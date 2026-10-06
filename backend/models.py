from fastapi import APIRouter
from llm import MODEL_CATALOG, DEFAULT_MODEL_KEY, PROVIDERS, provider_status
from pricing import get_pricing, model_table

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models")
async def list_models() -> dict:
    labels = {k: v["label"] for k, v in PROVIDERS.items()}
    typical = {t["id"]: t["credits_typical"] for t in model_table(await get_pricing(), MODEL_CATALOG)}
    return {"models": [{**m, "provider_label": labels.get(m["provider"], m["provider"]), "credits_typical": typical.get(m["id"])} for m in MODEL_CATALOG], "default": DEFAULT_MODEL_KEY, "providers": provider_status()}
