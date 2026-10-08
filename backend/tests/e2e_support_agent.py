import json, sys, requests

API = [l.split("=", 1)[1].strip() for l in open("/app/frontend/.env") if l.startswith("REACT_APP_BACKEND_URL")][0] + "/api"
tok = requests.post(f"{API}/auth/login", json={"email": "demo@aivora.ai", "password": "demo123456"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
r = requests.post(f"{API}/conversations", json={"persona_ids": ["oryntix-support"], "type": "private"}, headers=H)
print("conv", r.status_code, r.json().get("title"), r.json().get("members", [{}])[0].get("builtin"))
cid = r.json()["id"]
bad = requests.post(f"{API}/conversations", json={"persona_ids": ["oryntix-support"], "type": "group"}, headers=H)
print("group guard", bad.status_code, bad.json().get("detail"))
if "--chat" in sys.argv:
    rr = requests.post(f"{API}/conversations/{cid}/send", json={"content": "Bagaimana cara membuat gambar dengan rasio potret di Oryntix? Jawab singkat."}, headers=H, stream=True, timeout=120)
    final = None
    for line in rr.iter_lines():
        if line and line.startswith(b"data:"):
            try: ev = json.loads(line[5:].strip())
            except Exception: continue
            if ev.get("final"): final = ev
    print("chat:", (final or {}).get("content", "")[:300].replace("\n", " "), "| pending_tool:", bool((final or {}).get("pending_tool")))
c = requests.post(f"{API}/realtime/calls", json={"conversation_id": cid}, headers=H)
print("call", c.status_code, c.json().get("model"), c.json().get("persona", {}).get("name"), c.json().get("credits_per_min"))
call_id = c.json()["call_id"]
v = requests.post(f"{API}/realtime/calls/{call_id}/video/start", headers=H, timeout=60)
print("video start", v.status_code, {k: (str(val)[:40]) for k, val in v.json().items()})
t = requests.post(f"{API}/realtime/calls/{call_id}/video/tick", json={"elapsed_seconds": 20}, headers=H)
print("tick", t.status_code, t.json())
s = requests.post(f"{API}/realtime/calls/{call_id}/video/stop", json={"elapsed_seconds": 35}, headers=H)
print("stop", s.status_code, s.json())
requests.post(f"{API}/realtime/calls/{call_id}/end", json={"elapsed_seconds": 0}, headers=H)
