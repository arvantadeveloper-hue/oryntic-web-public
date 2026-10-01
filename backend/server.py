import os
import asyncio
import logging

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from db import db, ensure_indexes
from auth import router as auth_router, seed_admin
from personas import router as personas_router
from chat import router as chat_router
from agents import router as agents_router
from reminders import router as reminders_router, scheduler_tick
from wallet import router as wallet_router
from admin import router as admin_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("aivora")

app = FastAPI(title="Aivora API")


@app.get("/api/")
async def root():
    return {"message": "Aivora API", "status": "ok"}


app.include_router(auth_router)
app.include_router(personas_router)
app.include_router(chat_router)
app.include_router(agents_router)
app.include_router(reminders_router)
app.include_router(wallet_router)
app.include_router(admin_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

_scheduler_task = None


async def _scheduler_loop():
    while True:
        try:
            await scheduler_tick()
        except Exception as e:
            logger.error(f"scheduler error: {e}")
        await asyncio.sleep(20)


@app.on_event("startup")
async def startup():
    await ensure_indexes()
    await seed_admin()
    global _scheduler_task
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info("Aivora API started")


@app.on_event("shutdown")
async def shutdown():
    if _scheduler_task:
        _scheduler_task.cancel()
    db.client.close() if hasattr(db, "client") else None
