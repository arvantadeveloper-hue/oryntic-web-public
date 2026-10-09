"""Live single-provider chat-with-tools smoke (OpenAI web_search). Costs ~15-30 credits + model text."""
import os, json, time, requests, pytest
import sys as _sys; _sys.path.insert(0, '/app/backend/tests')  # noqa: E702
from creds import DEMO_PASSWORD, ADMIN_PASSWORD, BUDI_PASSWORD  # noqa: E402,F401

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

NADIA_PID = "77f5be90-dd50-407c-b9b9-5f604e13447c"


def _login():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "demo@aivora.ai", "password": DEMO_PASSWORD}, timeout=20)
    assert r.status_code == 200
    return r.json()["access_token"]


def test_openai_web_search_live():
    tok = _login()
    h = {"Authorization": f"Bearer {tok}"}
    # fetch persona
    g = requests.get(f"{BASE_URL}/api/personas/{NADIA_PID}", headers=h, timeout=15).json()
    orig_tools = g.get("tools") or []
    orig_model = g.get("model") or "gpt-terra"
    requests.put(f"{BASE_URL}/api/personas/{NADIA_PID}", headers=h,
                 json={"profile": g["profile"], "tools": ["openai:web_search", "openai:code_interpreter"], "model": "gpt-terra"}, timeout=15)
    try:
        c = requests.post(f"{BASE_URL}/api/conversations/direct", headers=h,
                          json={"persona_id": NADIA_PID}, timeout=15)
        cid = c.json().get("id") or c.json().get("conversation_id")
        prompt = "Cari di web: siapa juara Piala Dunia FIFA terakhir dan tahun berapa? Jawab 1 kalimat dengan sumber."
        s = requests.post(f"{BASE_URL}/api/conversations/{cid}/send", headers=h,
                          json={"content": prompt}, stream=True, timeout=120)
        assert s.status_code == 200
        saw_status = False
        for line in s.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                try:
                    ev = json.loads(line[5:].strip())
                except Exception:
                    continue
                if ev.get("status"):
                    txt = (ev.get("status") or "").lower()
                    if "alat bawaan" in txt:
                        saw_status = True
                if ev.get("final") or ev.get("type") == "done":
                    break
        s.close()
        time.sleep(2)
        m = requests.get(f"{BASE_URL}/api/conversations/{cid}/messages?limit=2", headers=h, timeout=15).json()
        msgs = m.get("messages") or m
        asst = [x for x in msgs if x.get("role") == "assistant"][-1]
        tools_used = asst.get("tools_used") or (asst.get("extras") or {}).get("tools_used") or []
        citations = asst.get("citations") or (asst.get("extras") or {}).get("citations") or []
        print(f"saw_status={saw_status} tools_used={tools_used} citations_n={len(citations)}")
        assert saw_status, "expected 'Menggunakan alat bawaan model…' status event"
        ws = [t for t in tools_used if t.get("id") == "openai:web_search"]
        assert ws, f"expected openai:web_search in tools_used, got {tools_used}"
        assert ws[0]["count"] >= 1
        assert ws[0]["credits"] == 15 * ws[0]["count"]
        assert len(citations) > 0
        # wallet transaction
        tx = requests.get(f"{BASE_URL}/api/wallet/transactions", headers=h, timeout=15).json()
        items = tx if isinstance(tx, list) else (tx.get("items") or tx.get("transactions") or [])
        found_tx = any("tool:openai:web_search" in (it.get("feature") or it.get("note") or it.get("description") or "") for it in items)
        print(f"tool tx found={found_tx}")
        assert found_tx, "expected a 'tool:openai:web_search' wallet transaction"
    finally:
        requests.put(f"{BASE_URL}/api/personas/{NADIA_PID}", headers=h,
                     json={"profile": g["profile"], "tools": orig_tools, "model": orig_model}, timeout=15)
