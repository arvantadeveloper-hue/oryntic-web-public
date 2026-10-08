import json, requests, sys, asyncio
API = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip() + "/api"
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
from db import db
from auth import make_token
async def _u(): return await db.users.find_one({"email": "demo@aivora.ai"})
u = asyncio.run(_u())
H = {"Authorization": f"Bearer {make_token(u['id'], 'admin')}"}
p = requests.get(f"{API}/personas", headers=H).json()[0]
cid = requests.post(f"{API}/conversations/direct", headers=H, json={"persona_id": p["id"]}).json()["id"]
cases = [("gpt-terra", ["openai:code_interpreter"]), ("claude-sonnet", ["anthropic:code_execution"]), ("gemini-3-8-flash", ["gemini:code_execution"])]
for model, tools in cases[: int(sys.argv[1]) if len(sys.argv) > 1 else 3]:
    requests.put(f"{API}/personas/{p['id']}", headers=H, json={"profile": p["profile"], "model": model, "tools": tools})
    call = requests.post(f"{API}/realtime/calls", headers=H, json={"conversation_id": cid}).json()
    r = requests.post(f"{API}/realtime/calls/{call['call_id']}/run-code", headers=H, json={"task": "Cicilan bulanan pinjaman 250 juta rupiah, bunga 9 persen per tahun, tenor 5 tahun (anuitas)."}, timeout=150)
    d = r.json()
    print(model, r.status_code, "answer:", (d.get("answer") or d.get("detail"))[:220].replace("\n", " "), "| credits:", d.get("credits"))
    requests.post(f"{API}/realtime/calls/{call['call_id']}/end", headers=H, json={"elapsed_seconds": 0})
m = requests.get(f"{API}/conversations/{cid}/messages?limit=1", headers=H).json()["messages"][-1]
print("last card tool:", m.get("tool"), "tools_used:", m.get("tools_used"))
requests.put(f"{API}/personas/{p['id']}", headers=H, json={"profile": p["profile"], "model": "gpt-terra", "tools": []})
call = requests.post(f"{API}/realtime/calls", headers=H, json={"conversation_id": cid}).json()
r = requests.post(f"{API}/realtime/calls/{call['call_id']}/run-code", headers=H, json={"task": "2+2"})
print("disabled →", r.status_code, r.json().get("detail"))
requests.post(f"{API}/realtime/calls/{call['call_id']}/end", headers=H, json={"elapsed_seconds": 0})
