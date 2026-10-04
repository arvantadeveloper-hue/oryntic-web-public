import os
import asyncio
import logging

import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.middleware.cors import CORSMiddleware

from db import db, ensure_indexes
from auth import router as auth_router, seed_admin, user_from_token
from personas import router as personas_router
from chat import router as chat_router, _can_access, migrate_direct_chats
from agents import router as agents_router
from reminders import router as reminders_router, scheduler_tick
from wallet import router as wallet_router
from admin import router as admin_router
from platform_admin import router as platform_router
from gallery import router as gallery_router
from archives import router as archives_router, archive_tick
from shares import router as shares_router
from friends import router as friends_router
from rtc import router as rtc_router
from knowledge import router as knowledge_router
from workspace import router as workspace_router
from assignments import router as assignments_router, tasks_tick
from models import router as models_router
from voice import router as voice_router
from files import router as files_router
from storage import init_storage
from realtime import manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("aivora")

app = FastAPI(title="Oryntix API")


@app.get("/api/")
async def root():
    return {"message": "Oryntix API", "status": "ok"}


app.include_router(auth_router)
app.include_router(personas_router)
app.include_router(chat_router)
app.include_router(agents_router)
app.include_router(reminders_router)
app.include_router(wallet_router)
app.include_router(admin_router)
app.include_router(platform_router)
app.include_router(gallery_router)
app.include_router(archives_router)
app.include_router(shares_router)
app.include_router(friends_router)
app.include_router(rtc_router)
app.include_router(knowledge_router)
app.include_router(workspace_router)
app.include_router(assignments_router)
app.include_router(models_router)
app.include_router(voice_router)
app.include_router(files_router)
from realtime_voice import router as realtime_voice_router  # noqa: E402
from tools import router as tools_router  # noqa: E402
app.include_router(realtime_voice_router)
app.include_router(tools_router)


@app.websocket("/api/ws/{cid}")
async def ws_meeting(ws: WebSocket, cid: str, token: str = ""):
    u = await user_from_token(token)
    if not u:
        await ws.close(code=4401)
        return
    conv = await db.conversations.find_one({"id": cid}, {"_id": 0})
    if not _can_access(conv, u):
        await ws.close(code=4403)
        return
    await manager.connect(cid, ws)
    me = {"from": u["id"], "from_name": u.get("name") or "Peserta"}
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if isinstance(msg, dict) and msg.get("type") == "rtc":  # WebRTC signaling relay (offer/answer/ice/join/leave)
                await manager.broadcast(cid, {**msg, **me}, exclude=ws)
    except WebSocketDisconnect:
        await manager.broadcast(cid, {"type": "rtc", "kind": "leave", **me})
        await manager.disconnect(cid, ws)
    except Exception:
        await manager.broadcast(cid, {"type": "rtc", "kind": "leave", **me})
        await manager.disconnect(cid, ws)

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
            await tasks_tick()
            await archive_tick()
        except Exception as e:
            logger.error(f"scheduler error: {e}")
        await asyncio.sleep(20)


@app.on_event("startup")
async def startup():
    await ensure_indexes()
    await seed_admin()
    await migrate_direct_chats()
    from pricing import refresh as refresh_pricing
    await refresh_pricing(force=True)
    try:
        await asyncio.to_thread(init_storage)
        logger.info("Object storage initialized")
    except Exception as e:
        logger.error(f"Object storage init failed: {e}")
    global _scheduler_task
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info("Oryntix API started")


@app.on_event("shutdown")
async def shutdown():
    if _scheduler_task:
        _scheduler_task.cancel()
    db.client.close() if hasattr(db, "client") else None
