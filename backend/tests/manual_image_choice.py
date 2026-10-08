import json, requests, sys, asyncio, time
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
    final = None
    with requests.post(f"{API}/conversations/{cid}/send", headers=H, json={"content": "Buatkan gambar ikon kucing oranye bertopi, kartun minimalis."}, stream=True, timeout=120) as s:
        for line in s.iter_lines():
            if line and line.startswith(b"data: "):
                try: ev = json.loads(line[6:])
                except Exception: continue
                if ev.get("final"): final = ev
    pt = (final or {}).get("pending_tool") or {}
    print("card kind:", pt.get("kind"), "options:", [(o["id"], o["credits"], o["available"]) for o in pt.get("options", [])])
    print("text:", (final or {}).get("content", "")[:90])
    mid = final["id"] if final and final.get("id") else (await db.messages.find_one({"conversation_id": cid, "pending_tool": {"$exists": True}}, sort=[("created_at", -1)]))["id"]
    model = sys.argv[1] if len(sys.argv) > 1 else "gpt-image"
    t0 = time.time()
    r = requests.post(f"{API}/conversations/{cid}/messages/{mid}/run-tool", headers=H, params={"choice": model, "app_url": "https://x"}, timeout=180)
    d = r.json()
    print(f"run-tool {model} → {r.status_code} in {time.time()-t0:.0f}s | tool:", d.get("tool"), "credits:", d.get("credits"), "media model:", d.get("media", [{}])[0].get("model"), "path:", d.get("media", [{}])[0].get("path", "")[:30])
    tx = requests.get(f"{API}/wallet/transactions", headers=H).json()
    items = tx if isinstance(tx, list) else tx.get("items", [])
    print("last usage:", [(t.get("description"), t.get("amount")) for t in items[:1]])
asyncio.run(main())
