import json, requests, sys
API = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip() + "/api"
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
import asyncio
from db import db
from auth import make_token
async def _u(): return await db.users.find_one({"email": "demo@aivora.ai"})
u = asyncio.run(_u())
H = {"Authorization": f"Bearer {make_token(u['id'], 'admin')}"}
p = requests.get(f"{API}/personas", headers=H).json()[0]
requests.put(f"{API}/personas/{p['id']}", headers=H, json={"profile": p["profile"], "model": "gpt-terra", "tools": ["openai:web_search"]})
cid = requests.post(f"{API}/conversations/direct", headers=H, json={"persona_id": p["id"]}).json()["id"]
call = requests.post(f"{API}/realtime/calls", headers=H, json={"conversation_id": cid}).json()
print("call:", call.get("call_id"), call.get("model"))
r = requests.post(f"{API}/realtime/calls/{call['call_id']}/web-search", headers=H, json={"query": "harga emas Antam hari ini per gram"}, timeout=120)
print(r.status_code, json.dumps(r.json(), ensure_ascii=False)[:600])
msgs = requests.get(f"{API}/conversations/{cid}/messages?limit=1", headers=H).json()["messages"]
m = msgs[-1]
print("saved msg tool:", m.get("tool"), "via:", m.get("via"), "credits:", m.get("credits"), "cites:", len(m.get("citations", [])))
# disable → 400
requests.put(f"{API}/personas/{p['id']}", headers=H, json={"profile": p["profile"], "tools": []})
r2 = requests.post(f"{API}/realtime/calls/{call['call_id']}/web-search", headers=H, json={"query": "tes"})
print("disabled →", r2.status_code, r2.json().get("detail"))
requests.post(f"{API}/realtime/calls/{call['call_id']}/end", headers=H, json={"elapsed_seconds": 0})
