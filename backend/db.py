import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def clean(doc: dict) -> dict:
    """Strip Mongo _id from a document."""
    if doc and "_id" in doc:
        doc = {k: v for k, v in doc.items() if k != "_id"}
    return doc


async def ensure_indexes():
    await db.users.create_index("email", unique=True)
    await db.conversations.create_index("user_id")
    await db.messages.create_index("conversation_id")
    await db.personas.create_index("user_id")
    await db.tasks.create_index("user_id")
    await db.reminders.create_index("user_id")
    await db.credit_transactions.create_index("user_id")
    await db.usage_events.create_index("user_id")
    await db.memory_items.create_index("user_id")
