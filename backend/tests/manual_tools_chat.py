import json, os, sys, time, requests
API = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip() + "/api"
tok = requests.post(f"{API}/auth/login", json={"email": "demo@aivora.ai", "password": "demo123456"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
personas = requests.get(f"{API}/personas", headers=H).json()
model_key = sys.argv[1] if len(sys.argv) > 1 else "gpt-terra"
tools = sys.argv[2].split(",") if len(sys.argv) > 2 else ["openai:web_search", "openai:code_interpreter"]
q = sys.argv[3] if len(sys.argv) > 3 else "Cari di web: siapa juara Piala Dunia FIFA terakhir dan tahun berapa? Lalu hitung secara presisi akar kuadrat dari 987654321 (4 desimal)."
p = personas[0]
print("persona", p["name"], "model→", model_key, "tools→", tools)
r = requests.put(f"{API}/personas/{p['id']}", headers=H, json={"profile": p["profile"], "model": model_key, "tools": tools})
assert r.json()["tools"] == tools, r.json().get("tools")
conv = requests.post(f"{API}/conversations/direct", headers=H, json={"persona_id": p["id"]}).json()
cid = conv.get("id") or conv.get("conversation", {}).get("id")
w = requests.get(f"{API}/wallet", headers=H).json(); bal0 = w.get("credits") or w.get("balance")
t0 = time.time()
with requests.post(f"{API}/conversations/{cid}/send", headers=H, json={"content": q}, stream=True, timeout=180) as s:
    final = None
    for line in s.iter_lines():
        if line and line.startswith(b"data: "):
            try: ev = json.loads(line[6:])
            except Exception: continue
            if ev.get("status"): print("status:", ev["status"])
            if ev.get("final"): final = ev
print(f"took {time.time()-t0:.1f}s")
msgs = requests.get(f"{API}/conversations/{cid}/messages?limit=2", headers=H).json()["messages"]
m = [x for x in msgs if x["role"] == "assistant"][-1]
print("content:", m["content"][:400])
print("tools_used:", m.get("tools_used"))
print("citations:", [c["url"][:60] for c in m.get("citations", [])][:3])
print("media:", m.get("media"))
print("credits msg:", m.get("credits"), "balance:", bal0, "→", (lambda w: w.get("credits") or w.get("balance"))(requests.get(f"{API}/wallet", headers=H).json()))
ev = requests.get(f"{API}/wallet/transactions", headers=H)
items = ev.json() if isinstance(ev.json(), list) else ev.json().get("items", [])
print("recent usage:", [(t.get("description"), t.get("amount")) for t in items[:4]])
