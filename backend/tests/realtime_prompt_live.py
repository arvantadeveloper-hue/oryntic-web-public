"""Validate the stored-prompt Realtime session config against OpenAI (no WebRTC). Run: python tests/realtime_prompt_live.py"""
import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from auth import make_token  # noqa: E402

API = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip() + "/api"
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def main():
    uid = sys.argv[1] if len(sys.argv) > 1 else "3c4bd726-168e-4e36-9515-a6a7d22fd8ef"
    h = {"Authorization": f"Bearer {make_token(uid, 'admin')}"}
    conv = await db.conversations.find_one({"user_id": uid, "type": "private"}, {"_id": 0, "id": 1})
    async with httpx.AsyncClient(timeout=60) as c:
        st = (await c.get(f"{API}/realtime/status", headers=h)).json()
        print("status:", st)
        r = await c.post(f"{API}/realtime/calls", headers=h, json={"conversation_id": conv["id"]})
        print("create call", r.status_code, r.json().get("call_id"))
        call = await db.realtime_calls.find_one({"id": r.json()["call_id"]}, {"_id": 0, "prompt_variables": 1, "voice": 1})
        v = call["prompt_variables"]
        print("variables:", {k: (val[:60] if isinstance(val, str) else val) for k, val in v.items()})
        session = {"type": "realtime", "output_modalities": ["audio"], "audio": {"output": {"voice": call["voice"]}},
                   "prompt": {"id": os.environ["OPENAI_REALTIME_PROMPT_ID"], **({"version": os.environ["OPENAI_REALTIME_PROMPT_VERSION"]} if os.environ.get("OPENAI_REALTIME_PROMPT_VERSION") else {}), "variables": {k: {"type": "input_text", "text": str(val)} for k, val in v.items()}}}
        r2 = await c.post("https://api.openai.com/v1/realtime/client_secrets", headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}, json={"session": session})
        print("client_secrets:", r2.status_code, r2.text[:700])
        await c.post(f"{API}/realtime/calls/{r.json()['call_id']}/end", headers=h, json={"seconds": 0})
        print("PASS" if r2.status_code == 200 else "FAIL")


asyncio.run(main())
