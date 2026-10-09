import asyncio
import json
import os
import subprocess
import websockets
import sys as _sys; _sys.path.insert(0, '/app/backend/tests')  # noqa: E702
from creds import DEMO_PASSWORD, ADMIN_PASSWORD, BUDI_PASSWORD  # noqa: E402,F401

API = "https://ai-companion-test-5.preview.emergentagent.com/api"
WS_BASE = "wss://ai-companion-test-5.preview.emergentagent.com/api/ws/"


def login(email, pw):
    out = subprocess.check_output([
        "curl", "-s", "-X", "POST", f"{API}/auth/login",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"email": email, "password": pw})])
    return json.loads(out)["access_token"]


async def main():
    cid = open("/tmp/mcid.txt").read().strip()
    admin = login("demo@aivora.ai", os.environ.get("TEST_ADMIN_PASSWORD", DEMO_PASSWORD))
    budi = login("budi@aivora.ai", os.environ.get("TEST_BUDI_PASSWORD", BUDI_PASSWORD))
    url = f"{WS_BASE}{cid}?token={budi}"
    async with websockets.connect(url, open_timeout=15) as ws:
        print("budi WS connected")
        # fire admin send via curl in a thread
        def send():
            subprocess.run(["curl", "-s", "-o", "/dev/null", "-X", "POST",
                            f"{API}/conversations/{cid}/send",
                            "-H", f"Authorization: Bearer {admin}",
                            "-H", "Content-Type: application/json",
                            "-d", json.dumps({"content": "Uji realtime ke Budi.", "attachments": [], "moderator": False})])
        asyncio.get_event_loop().run_in_executor(None, send)
        got = []
        try:
            while len(got) < 5:
                msg = await asyncio.wait_for(ws.recv(), timeout=30)
                got.append(json.loads(msg))
                print("budi received:", got[-1])
        except asyncio.TimeoutError:
            pass
        print("TOTAL events:", len(got))
        assert len(got) >= 1, "budi received no realtime events!"
        print("WS REALTIME OK")

asyncio.run(main())
