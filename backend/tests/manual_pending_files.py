import json, requests, sys, asyncio, time
API = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip() + "/api"
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv; load_dotenv("/app/backend/.env")
from db import db
from auth import make_token
async def _u(): return await db.users.find_one({"email": "demo@aivora.ai"})
u = asyncio.run(_u())
H = {"Authorization": f"Bearer {make_token(u['id'], 'admin')}"}
p = requests.get(f"{API}/personas", headers=H).json()[0]
requests.put(f"{API}/personas/{p['id']}", headers=H, json={"profile": p["profile"], "model": "gpt-terra", "tools": ["openai:code_interpreter"]})
cid = requests.post(f"{API}/conversations/direct", headers=H, json={"persona_id": p["id"]}).json()["id"]
call = requests.post(f"{API}/realtime/calls", headers=H, json={"conversation_id": cid}).json()
t0 = time.time()
r = requests.post(f"{API}/realtime/calls/{call['call_id']}/run-code", headers=H, json={"task": "Penjualan per bulan Jan 120, Feb 150, Mar 90, Apr 200, Mei 170 juta. Hitung total dan rata-rata, dan buat grafik batangnya."}, timeout=170)
d = r.json(); print(r.status_code, f"{time.time()-t0:.0f}s", "answer:", (d.get("answer") or d.get("detail"))[:200].replace("\n", " "), "| files:", d.get("files"), "| credits:", d.get("credits"))
requests.post(f"{API}/realtime/calls/{call['call_id']}/end", headers=H, json={"elapsed_seconds": 0})
m = requests.get(f"{API}/conversations/{cid}/messages?limit=1", headers=H).json()["messages"][-1]
pf = m.get("pending_files") or []
print("card tool:", m.get("tool"), "pending:", [(f["name"], f["kind"], f["size"]) for f in pf])
if pf:
    f = pf[0]
    pr = requests.get(f"{API}/pending-files/{f['id']}", headers=H); print("preview:", pr.status_code, pr.headers.get("content-type"), len(pr.content))
    sv = requests.post(f"{API}/pending-files/{f['id']}/save", headers=H, json={"message_id": m["id"], "target": "storage"}); print("save:", sv.status_code, sv.json())
    m2 = requests.get(f"{API}/conversations/{cid}/messages?limit=1", headers=H).json()["messages"][-1]
    print("after save → media:", [(x["type"], x.get("path", "")[:40]) for x in m2.get("media", [])], "pending left:", len(m2.get("pending_files") or []))
    again = requests.post(f"{API}/pending-files/{f['id']}/save", headers=H, json={"message_id": m["id"], "target": "storage"}); print("save again →", again.status_code)
    for g in (m2.get("pending_files") or []):
        dl = requests.delete(f"{API}/pending-files/{g['id']}", headers=H, params={"message_id": m["id"]}); print("discard", g["name"], dl.status_code)
requests.put(f"{API}/personas/{p['id']}", headers=H, json={"profile": p["profile"], "tools": []})
