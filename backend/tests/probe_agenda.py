"""E2E probe for the agenda confirm/cancel chat flow (run manually: PYTHONPATH=/app/backend python tests/probe_agenda.py)."""
import json
import os
import sys
import time
import requests

API = os.environ.get("API") or [l.split("=", 1)[1].strip() for l in open("/app/frontend/.env") if l.startswith("REACT_APP_BACKEND_URL")][0]
TOK = requests.post(f"{API}/api/auth/login", json={"email": "demo@aivora.ai", "password": "demo123456"}).json()["access_token"]
H = {"Authorization": f"Bearer {TOK}"}


def send(cid, text):
    r = requests.post(f"{API}/api/conversations/{cid}/send", json={"content": text}, headers=H, stream=True, timeout=120)
    final = {}
    if r.status_code != 200:
        return {"tool": f"HTTP {r.status_code}", "content": r.text[:300]}
    for line in r.iter_lines():
        if line and line.startswith(b"data:"):
            try:
                ev = json.loads(line[5:])
            except Exception:
                continue
            if ev.get("final"):
                final = ev
    return final


convs = requests.get(f"{API}/api/conversations", headers=H).json()
convs = convs.get("items", convs) if isinstance(convs, dict) else convs
cid = next(c["id"] for c in convs if (c.get("persona_ids") or c.get("persona_id")) and not c.get("group") and "oryntix-support" not in (c.get("persona_ids") or [c.get("persona_id")]))
print("conv", cid)
for step in sys.argv[1:] or ["Ingatkan saya rapat tim besok", "jam 10 pagi, via telepon aja", "ya", "rapat tim besok batal", "ya"]:
    time.sleep(2)
    t = time.time()
    f = send(cid, step)
    print(f"\n> {step}\n[{f.get('tool')}] ({time.time() - t:.1f}s)\n{(f.get('content') or '')[:500]}")
