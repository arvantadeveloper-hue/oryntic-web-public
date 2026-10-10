import asyncio
import os
from db import db, now_iso, new_id
from auth import pw_hash

EMAIL = os.getenv("SEED_FINANCE_EMAIL")
PASSWORD = os.getenv("SEED_FINANCE_PASSWORD")


async def main():
    if not EMAIL or not PASSWORD:
        raise SystemExit("Set SEED_FINANCE_EMAIL and SEED_FINANCE_PASSWORD env vars before running this seeder.")
    existing = await db.users.find_one({"email": EMAIL})
    if existing:
        # Never reset an existing account's password on reseed; only (re)grant the finance role.
        await db.users.update_one({"id": existing["id"]}, {"$set": {"platform_role": "finance", "disabled": False, "updated_at": now_iso()}})
        print("granted finance role to existing user (password unchanged):", EMAIL)
    else:
        uid = new_id()
        doc = {"id": uid, "email": EMAIL, "password_hash": pw_hash(PASSWORD), "name": "Oryntix Finance", "role": "admin", "owner_id": uid,
               "onboarded": True, "verified": True, "platform_role": "finance", "credits": 0, "plan": "staff",
               "settings": {"app_language": "id", "conversation_language": "id", "timezone": "Asia/Jakarta"}, "created_at": now_iso()}
        await db.users.insert_one(doc)
        print("created finance staff:", EMAIL)


asyncio.run(main())
