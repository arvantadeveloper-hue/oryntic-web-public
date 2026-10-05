"""End-to-end Realtime negotiation test with a real WebRTC SDP offer (aiortc). Run: python tests/realtime_negotiate_live.py"""
import asyncio
import os
import sys

import httpx
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole
from aiortc.mediastreams import AudioStreamTrack
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
    pc = RTCPeerConnection()
    pc.addTrack(AudioStreamTrack())
    pc.createDataChannel("oai-events")
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(f"{API}/realtime/calls", headers=h, json={"conversation_id": conv["id"]})
        cid = r.json()["call_id"]
        print("create call", r.status_code, cid)
        r = await c.post(f"{API}/realtime/calls/{cid}/negotiate", headers={**h, "Content-Type": "application/sdp"}, content=pc.localDescription.sdp)
        print("negotiate", r.status_code, r.text[:160].replace("\n", " "))
        ok = r.status_code == 200 and r.text.startswith("v=0")
        if ok:
            await pc.setRemoteDescription(RTCSessionDescription(sdp=r.text, type="answer"))
            await asyncio.sleep(4)
            print("ice/connection state:", pc.iceConnectionState, pc.connectionState)
        await c.post(f"{API}/realtime/calls/{cid}/end", headers=h, json={"seconds": 1})
    await pc.close()
    print("PASS" if ok else "FAIL")


asyncio.run(main())
