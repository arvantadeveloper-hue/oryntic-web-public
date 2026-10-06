from fastapi import APIRouter
from llm import MODEL_CATALOG, DEFAULT_MODEL_KEY, PROVIDERS, provider_status

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models")
async def list_models() -> dict:
    labels = {k: v["label"] for k, v in PROVIDERS.items()}
    return {"models": [{**m, "provider_label": labels.get(m["provider"], m["provider"])} for m in MODEL_CATALOG], "default": DEFAULT_MODEL_KEY, "providers": provider_status()}
