"""Oryntix Platform back-office API — everything the separate admin website needs, under /api/platform/*.
Moved here from the standalone `oryntix-web-admin` backend; shares auth, db, storage and the tariff engine with the main app."""
from platform_api.console import router as console_router
from platform_api.finance import router as finance_router
from platform_api.expenses import router as expenses_router
from platform_api.crons import router as cron_router
from platform_api.support import router as support_router
from platform_api.pricing_routes import router as pricing_router, legacy as legacy_pricing_router

routers = (console_router, finance_router, expenses_router, cron_router, support_router, pricing_router, legacy_pricing_router)
