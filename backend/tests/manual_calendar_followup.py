import json, requests, sys, asyncio
API = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip() + "/api"
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv; load_dotenv("/app/backend/.env")


async def main():
    from db import db
    from auth import make_token
    u = await db.users.find_one({"email": "demo@aivora.ai"})
    H = {"Authorization": f"Bearer {make_token(u['id'], 'admin')}"}
    p = requests.get(f"{API}/personas", headers=H).json()[0]
    cid = requests.post(f"{API}/conversations/direct", headers=H, json={"persona_id": p["id"]}).json()["id"]
    def send(text):
        final = None
        with requests.post(f"{API}/conversations/{cid}/send", headers=H, json={"content": text}, stream=True, timeout=120) as s:
            for line in s.iter_lines():
                if line and line.startswith(b"data: "):
                    try: ev = json.loads(line[6:])
                    except Exception: continue
                    if ev.get("final"): final = ev
        return final or {}
    f1 = send("Ingatkan saya minggu depan untuk bayar listrik, telepon saja")
    print("1:", f1.get("tool"), f1.get("content", "")[:120])
    f2 = send("Selasa jam 9 pagi")
    print("2:", f2.get("tool"), f2.get("content", "")[:200].replace("\n", " "))
    evd = await db.events.find_one({"user_id": u["id"], "title": {"$regex": "listrik", "$options": "i"}}, sort=[("created_at", -1)])
    print("event:", evd and (evd["title"], evd["start_at"], evd["remind"]))
    if evd: requests.delete(f"{API}/events/{evd['id']}", headers=H)
    conv = await db.conversations.find_one({"id": cid}, {"_id": 0, "pending_calendar": 1}); print("pending cleared:", conv.get("pending_calendar") is None)
    f3 = send("Terima kasih, apa kabar hari ini?")
    print("3 (normal):", f3.get("tool"), f3.get("content", "")[:80])
asyncio.run(main())
