from fastapi import APIRouter
from llm import MODEL_CATALOG, DEFAULT_MODEL_KEY

router = APIRouter(prefix="/api", tags=["models"])


@router.get("/models")
async def list_models() -> dict:
    return {"models": MODEL_CATALOG, "default": DEFAULT_MODEL_KEY}
