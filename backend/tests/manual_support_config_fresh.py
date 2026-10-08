"""Verify the main app picks up config.support_agent changes written by an external process (oryntix-admin) without restart."""
import asyncio
import os
import sys
import time

import httpx
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
from auth import make_token  # noqa: E402

API = os.environ.get("API_URL", "http://localhost:8001")
DEMO_ID = os.environ.get("DEMO_USER_ID", "")


async def main():
    mongo = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    if not DEMO_ID:
        u = await mongo.users.find_one({"email": "demo@aivora.ai"}, {"_id": 0, "id": 1})
        uid = u["id"]
    else:
        uid = DEMO_ID
    h = {"Authorization": f"Bearer {make_token(uid, 'admin')}"}
    before = await mongo.config.find_one({"id": "support_agent"}, {"_id": 0}) or {}

    async with httpx.AsyncClient(timeout=30) as c:
        r0 = (await c.get(f"{API}/api/personas", headers=h)).json()
        sp0 = next(p for p in r0 if p.get("builtin"))
        print("before:", sp0["name"], sp0["portrait"], sp0.get("video_avatar"))
        vc0 = (await c.get(f"{API}/api/support/video-config", headers=h)).json()
        print("video-config before:", vc0)

        # external write (what oryntix-admin does)
        await mongo.config.update_one({"id": "support_agent"}, {"$set": {
            "name": "Oryntix QA", "portrait": "https://example.com/qa.jpg", "avatar_id": "qa-avatar-0001", "avatar_name": "QA Avatar",
            "avatar_preview": "https://example.com/qa-prev.jpg", "video_credits_per_sec": 7, "video_max_minutes": 11, "video_warn_minutes": 3, "sandbox": False}}, upsert=True)

        deadline = time.time() + 45
        ok = False
        while time.time() < deadline:
            r1 = (await c.get(f"{API}/api/personas", headers=h)).json()
            sp1 = next(p for p in r1 if p.get("builtin"))
            vc1 = (await c.get(f"{API}/api/support/video-config", headers=h)).json()
            if sp1["name"] == "Oryntix QA" and sp1["portrait"] == "https://example.com/qa.jpg" and vc1["credits_per_sec"] == 7 and vc1["max_minutes"] == 11 and vc1["avatar_name"] == "QA Avatar" and vc1["sandbox"] is False:
                ok = True
                print("after (fresh):", sp1["name"], sp1["portrait"], vc1)
                break
            await asyncio.sleep(3)
        assert ok, "main app did not pick up external config change within 45s"
        assert vc1["max_cost"] == 7 * 11 * 60

    # restore
    if before:
        await mongo.config.replace_one({"id": "support_agent"}, before)
    else:
        await mongo.config.delete_one({"id": "support_agent"})
    print("restored. OK")


asyncio.run(main())
