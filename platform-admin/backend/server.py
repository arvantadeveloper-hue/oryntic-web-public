import os
import logging
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from db import db, ensure_indexes
from auth import router as auth_router, seed_admin
from platform_admin import router as platform_router
from platform_finance import router as finance_router
from pricing_admin import router as pricing_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

app = FastAPI(title="Oryntix Platform Admin API")


@app.get("/api/")
async def root():
    return {"message": "Oryntix Platform Admin API", "status": "ok"}


@app.get("/api/health")
async def health():
    await db.command("ping")
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(platform_router)
app.include_router(finance_router)
app.include_router(pricing_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await ensure_indexes()
    await seed_admin()
