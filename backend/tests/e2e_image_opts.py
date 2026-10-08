import json, os, sys, requests

API = [l.split("=", 1)[1].strip() for l in open("/app/frontend/.env") if l.startswith("REACT_APP_BACKEND_URL")][0] + "/api"
tok = requests.post(f"{API}/auth/login", json={"email": "demo@aivora.ai", "password": "demo123456"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}
convs = requests.get(f"{API}/conversations", headers=H).json()
conv = next(c for c in (convs if isinstance(convs, list) else convs.get("items", [])) if c.get("type") == "private")
cid = conv["id"]
print("conv", cid, conv.get("title"))
text = sys.argv[1] if len(sys.argv) > 1 else "Buat gambar potret kucing oranye memakai topi detektif, kualitas tinggi"
r = requests.post(f"{API}/conversations/{cid}/send", json={"content": text}, headers=H, stream=True, timeout=120)
final = None
for line in r.iter_lines():
    if line and line.startswith(b"data:"):
        try:
            ev = json.loads(line[5:].strip())
        except Exception:
            continue
        if ev.get("final"):
            final = ev
pt = (final or {}).get("pending_tool")
print("pending_tool:", json.dumps({k: v for k, v in (pt or {}).items() if k != "options"}, ensure_ascii=False))
print("options:", [(o["id"], o["available"], o["prices"]["standar"]["21:9"]) for o in (pt or {}).get("options", [])]); print("presets:", (pt or {}).get("presets"))
if pt and len(sys.argv) > 2:
    mid = final["message_id"]
    aspect, quality = sys.argv[2], sys.argv[3]; preset = sys.argv[4] if len(sys.argv) > 4 else None
    rr = requests.post(f"{API}/conversations/{cid}/messages/{mid}/run-tool", params={"choice": "gemini-image", "aspect": aspect, "quality": quality, "preset": preset, "app_url": "http://x"}, headers=H, timeout=180)
    print("run-tool", rr.status_code, json.dumps({k: rr.json().get(k) for k in ("content", "credits", "media")}, ensure_ascii=False)[:600])
