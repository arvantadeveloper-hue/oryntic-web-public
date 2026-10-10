"""Pricing / trial / rate-limit / catalog endpoints for the platform console, mounted under /api/platform.
The tariff engine itself lives in the main app (pricing.py, pricing_catalog.py, admin.py) — this module only re-exposes
those handlers at the platform path and adds an audit trail + the rate-limit settings. Legacy /api/admin/* paths stay valid."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import admin
import tools
from auth import require_platform_admin, require_platform_staff
from behaviour import BehaviourIn
from pricing import get_pricing, get_trial
from ratelimit import get_limits, set_limits
from platform_api.common import _audit, _diff_summary

router = APIRouter(prefix="/api/platform", tags=["platform-pricing"])
legacy = APIRouter(prefix="/api/admin", tags=["admin"])


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


# ---- writes: same engine as /api/admin/*, plus an audit entry ----
@router.put("/pricing", summary="Simpan tarif & margin global")
async def put_pricing(x: admin.PlatformPricingIn, u: dict = Depends(require_platform_admin)):
    old = await get_pricing()
    res = await admin.put_pricing(x, u)
    await _audit(u, "pricing.update", "Tarif & Margin", {"changed": _diff_summary(old, x.model_dump())})
    return res


@router.get("/trial", summary="Konfigurasi trial saat ini")
async def read_trial(_: dict = Depends(require_platform_staff)):
    return {"trial": await get_trial()}


@router.put("/trial", summary="Simpan konfigurasi trial")
async def put_trial(x: admin.TrialIn, u: dict = Depends(require_platform_admin)):
    old = await get_trial()
    res = await admin.put_trial(x, u)
    await _audit(u, "trial.update", "Trial & Batas", {"changed": _diff_summary(old, x.model_dump())})
    return res


@router.put("/pricing-catalog", summary="Simpan katalog harga (provider → layanan → komponen)")
async def put_pricing_catalog(x: admin.CatalogIn, u: dict = Depends(require_platform_admin)):
    res = await admin.put_pricing_catalog(x, u)
    await _audit(u, "catalog.update", "Pricing", {"providers": len(x.providers)})
    return res


@router.post("/pricing-catalog/import/apply", summary="Terapkan hasil impor harga provider")
async def apply_import(x: admin.ImportApplyIn, u: dict = Depends(require_platform_admin)):
    res = await admin.apply_pricing_catalog_import(x, u)
    await _audit(u, "catalog.import", x.provider_id, {"rows": len(x.rows)})
    return res


@router.put("/realtime-behaviour", summary="Simpan perilaku percakapan Realtime")
async def put_behaviour(x: BehaviourIn, u: dict = Depends(require_platform_admin)):
    res = await admin.admin_set_behaviour(x, u)
    await _audit(u, "behaviour.update", "Conversation Behaviour", {})
    return res


# ---- reads: the handlers from admin.py, unchanged ----
for path, fn, methods in (
    ("/pricing", admin.pricing, ["GET"]),
    ("/pricing/preview", admin.preview_pricing, ["POST"]),
    ("/pricing-catalog", admin.get_pricing_catalog, ["GET"]),
    ("/pricing-catalog/quote", admin.quote_component, ["POST"]),
    ("/pricing-catalog/import", admin.import_pricing_catalog, ["POST"]),
    ("/realtime-behaviour", admin.admin_behaviour, ["GET"]),
    ("/model-routing", tools.admin_get_routing, ["GET"]),
    ("/model-routing", tools.admin_set_routing, ["PUT"]),
):
    router.add_api_route(path, fn, methods=methods, name=f"platform_{fn.__name__}")


# ---- rate limits (new in the main backend; /api/admin/rate-limits kept as alias) ----
async def get_rate_limits(_: dict = Depends(require_platform_staff)):
    return await get_limits()


async def put_rate_limits(x: LimitsIn, u: dict = Depends(require_platform_admin)):
    old = await get_limits()
    res = await set_limits(x.model_dump())
    await _audit(u, "rate_limits.update", "Batas & Rate Limit", {"changed": _diff_summary(old, x.model_dump())})
    return res


for r in (router, legacy):
    r.add_api_route("/rate-limits", get_rate_limits, methods=["GET"], summary="Batas & rate limit platform")
    r.add_api_route("/rate-limits", put_rate_limits, methods=["PUT"], summary="Simpan batas & rate limit")
