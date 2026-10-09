"""Application lifecycle: startup migrations/seeds, the 20-second scheduler loop (reminders, assigned tasks, archives, scheduled social posts) and shutdown."""
import asyncio
import logging

from archives import archive_tick
from assignments import tasks_tick
from auth import seed_admin
from chat import migrate_direct_chats
from db import db, ensure_indexes
from portraits import migrate_portraits
from reminders import scheduler_tick
from social import social_tick
from storage import init_storage

logger = logging.getLogger("aivora")
_scheduler_task = None


async def _scheduler_loop():
    while True:
        try:
            await scheduler_tick()
            await tasks_tick()
            await archive_tick()
            await social_tick()
        except Exception as e:
            logger.error(f"scheduler error: {e}")
        await asyncio.sleep(20)


async def on_startup():
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
    asyncio.create_task(migrate_portraits())
    logger.info("Oryntix API started")


async def on_shutdown():
    if _scheduler_task:
        _scheduler_task.cancel()
    db.client.close() if hasattr(db, "client") else None


def register_lifecycle(app) -> None:
    app.add_event_handler("startup", on_startup)
    app.add_event_handler("shutdown", on_shutdown)
