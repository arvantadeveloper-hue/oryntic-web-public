"""Iteration 37 — Paket 6 provider built-in tools regression tests."""
import os
import time
import json
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

DEMO = {"email": "demo@aivora.ai", "password": "demo123456"}
ADMIN = {"email": "admin@aivora.ai", "password": "Aivora!Admin2026"}
NADIA_PID = "77f5be90-dd50-407c-b9b9-5f604e13447c"

EXPECTED_CREDITS = {
    "openai:web_search": 15, "openai:code_interpreter": 44, "openai:image_generation": 58,
    "gemini:google_search": 51, "gemini:code_execution": 0,
    "anthropic:web_search": 15, "anthropic:code_execution": 8,
}

_token_cache = {}


def _login(creds):
    key = creds["email"]
    if key in _token_cache:
        return _token_cache[key]
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login {key}: {r.status_code} {r.text}"
    tok = r.json()["access_token"]
    _token_cache[key] = tok
    return tok


@pytest.fixture(scope="module")
def demo_token():
    return _login(DEMO)


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# --- GET /api/tools ---------------------------------------------------------

def test_get_tools(demo_token):
    r = requests.get(f"{BASE_URL}/api/tools", headers=_h(demo_token), timeout=15)
    assert r.status_code == 200, r.text
    tools = r.json()["tools"]
    assert len(tools) == 7
    by_id = {t["id"]: t for t in tools}
    for tid, credits in EXPECTED_CREDITS.items():
        assert tid in by_id, f"missing tool {tid}"
        t = by_id[tid]
        for k in ("provider", "label", "desc", "unit", "usd", "credits", "available", "provider_label"):
            assert k in t, f"{tid} missing field {k}"
        assert t["credits"] == credits, f"{tid}: credits {t['credits']} != {credits}"
        assert t["available"] is True, f"{tid}: available should be True"


# --- Persona tools persistence ---------------------------------------------

def test_put_persona_tools_validation(demo_token):
    body = {"profile": "ignored-field-just-for-shape", "tools": ["openai:web_search", "openai:web_search", "bogus:tool", "gemini:google_search"]}
    # keep existing profile to not break anything
    get_r = requests.get(f"{BASE_URL}/api/personas/{NADIA_PID}", headers=_h(demo_token), timeout=15)
    assert get_r.status_code == 200
    original = get_r.json()
    original_tools = original.get("tools") or []
    try:
        r = requests.put(f"{BASE_URL}/api/personas/{NADIA_PID}", headers=_h(demo_token),
                         json={"profile": original.get("profile", ""), "tools": body["tools"]}, timeout=15)
        assert r.status_code == 200, r.text
        g = requests.get(f"{BASE_URL}/api/personas/{NADIA_PID}", headers=_h(demo_token), timeout=15).json()
        tools = g.get("tools") or []
        assert "bogus:tool" not in tools
        assert tools.count("openai:web_search") == 1
        assert set(tools) == {"openai:web_search", "gemini:google_search"}

        # PUT without tools key keeps existing
        r2 = requests.put(f"{BASE_URL}/api/personas/{NADIA_PID}", headers=_h(demo_token),
                          json={"profile": original.get("profile", "")}, timeout=15)
        assert r2.status_code == 200
        g2 = requests.get(f"{BASE_URL}/api/personas/{NADIA_PID}", headers=_h(demo_token), timeout=15).json()
        assert set(g2.get("tools") or []) == {"openai:web_search", "gemini:google_search"}
    finally:
        # restore original tools (should be [])
        requests.put(f"{BASE_URL}/api/personas/{NADIA_PID}", headers=_h(demo_token),
                     json={"profile": original.get("profile", ""), "tools": original_tools}, timeout=15)


def test_create_persona_with_tools_and_delete(demo_token):
    payload = {"profile": {"identity": {"name": "TEST_tools_persona", "summary": "t"}}, "tools": ["openai:web_search", "unknown:x", "openai:web_search"]}
    r = requests.post(f"{BASE_URL}/api/personas", headers=_h(demo_token), json=payload, timeout=15)
    assert r.status_code in (200, 201), r.text
    pid = r.json().get("id")
    try:
        g = requests.get(f"{BASE_URL}/api/personas/{pid}", headers=_h(demo_token), timeout=15).json()
        assert g.get("tools") == ["openai:web_search"]
    finally:
        d = requests.delete(f"{BASE_URL}/api/personas/{pid}", headers=_h(demo_token), timeout=15)
        assert d.status_code in (200, 204)


# --- Platform pricing round-trip -------------------------------------------

def test_admin_pricing_tools(admin_token):
    r = requests.get(f"{BASE_URL}/api/admin/pricing", headers=_h(admin_token), timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "tools" in data and len(data["tools"]) == 7
    assert "tool_prices" in data["pricing"]
    orig_price = float(data["pricing"]["tool_prices"].get("openai:web_search", 0.01))

    # preview
    body = dict(data["pricing"])
    body["tool_prices"] = {**body["tool_prices"], "openai:web_search": 0.02}
    pv = requests.post(f"{BASE_URL}/api/admin/pricing/preview", headers=_h(admin_token), json=body, timeout=15)
    assert pv.status_code == 200
    pv_tools = {t["id"]: t for t in pv.json()["tools"]}
    assert pv_tools["openai:web_search"]["credits"] == 29

    # confirm preview didn't persist
    reread = requests.get(f"{BASE_URL}/api/admin/pricing", headers=_h(admin_token), timeout=15).json()
    assert reread["pricing"]["tool_prices"]["openai:web_search"] == orig_price

    # PUT
    try:
        up = requests.put(f"{BASE_URL}/api/admin/pricing", headers=_h(admin_token), json=body, timeout=15)
        assert up.status_code == 200, up.text
        up_tools = {t["id"]: t for t in up.json()["tools"]}
        assert up_tools["openai:web_search"]["credits"] == 29

        # verify GET /api/tools reflects it
        time.sleep(1)
        gt = requests.get(f"{BASE_URL}/api/tools", headers=_h(admin_token), timeout=15).json()
        gt_by = {t["id"]: t for t in gt["tools"]}
        assert gt_by["openai:web_search"]["credits"] == 29
    finally:
        body["tool_prices"]["openai:web_search"] = orig_price
        restore = requests.put(f"{BASE_URL}/api/admin/pricing", headers=_h(admin_token), json=body, timeout=15)
        assert restore.status_code == 200
        time.sleep(1)
        gt2 = requests.get(f"{BASE_URL}/api/tools", headers=_h(admin_token), timeout=15).json()
        gt2_by = {t["id"]: t for t in gt2["tools"]}
        assert gt2_by["openai:web_search"]["credits"] == 15


# --- Fallback when no tools or wrong provider -----------------------------

def test_fallback_no_tools(demo_token):
    """Persona with no tools → normal reply, no tools_used, no status event."""
    # get current persona and ensure tools=[]
    g = requests.get(f"{BASE_URL}/api/personas/{NADIA_PID}", headers=_h(demo_token), timeout=15).json()
    orig_tools = g.get("tools") or []
    orig_model = g.get("model_key") or "gpt-terra"
    requests.put(f"{BASE_URL}/api/personas/{NADIA_PID}", headers=_h(demo_token),
                 json={"profile": g.get("profile", ""), "tools": [], "model_key": "gpt-terra"}, timeout=15)
    try:
        c = requests.post(f"{BASE_URL}/api/conversations/direct", headers=_h(demo_token),
                          json={"persona_id": NADIA_PID}, timeout=15)
        assert c.status_code in (200, 201), c.text
        cid = c.json().get("id") or c.json().get("conversation_id")
        # Simple small prompt (minimize cost)
        s = requests.post(f"{BASE_URL}/api/conversations/{cid}/send",
                          headers=_h(demo_token), json={"content": "Halo, balas 'ok'."}, stream=True, timeout=60)
        assert s.status_code == 200
        saw_tool_status = False
        for line in s.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                try:
                    ev = json.loads(line[5:].strip())
                except Exception:
                    continue
                if ev.get("status") and "alat bawaan" in (ev.get("status") or "").lower():
                    saw_tool_status = True
                if ev.get("final") or ev.get("type") == "done":
                    break
        s.close()
        assert not saw_tool_status, "should not have shown tool status when no tools enabled"

        # last assistant message should have no tools_used
        time.sleep(1)
        m = requests.get(f"{BASE_URL}/api/conversations/{cid}/messages?limit=2",
                         headers=_h(demo_token), timeout=15).json()
        msgs = m.get("messages") or m
        asst = [x for x in msgs if x.get("role") == "assistant"]
        assert asst, "no assistant message"
        assert not asst[-1].get("tools_used"), f"should not have tools_used: {asst[-1].get('tools_used')}"
    finally:
        requests.put(f"{BASE_URL}/api/personas/{NADIA_PID}", headers=_h(demo_token),
                     json={"profile": g.get("profile", ""), "tools": orig_tools, "model_key": orig_model}, timeout=15)


# --- SEARCH_RE must not intercept "cari di web…" --------------------------

def test_workspace_search_still_works(demo_token):
    """'cari dokumen notulen di ruang kerja' should still trigger workspace_search tool card."""
    g = requests.get(f"{BASE_URL}/api/personas/{NADIA_PID}", headers=_h(demo_token), timeout=15).json()
    c = requests.post(f"{BASE_URL}/api/conversations/direct", headers=_h(demo_token),
                      json={"persona_id": NADIA_PID}, timeout=15)
    cid = c.json().get("id") or c.json().get("conversation_id")
    s = requests.post(f"{BASE_URL}/api/conversations/{cid}/send", headers=_h(demo_token),
                      json={"content": "cari dokumen notulen di ruang kerja"}, stream=True, timeout=30)
    tool_card = None
    for line in s.iter_lines(decode_unicode=True):
        if line and line.startswith("data:"):
            try:
                ev = json.loads(line[5:].strip())
            except Exception:
                continue
            if ev.get("type") == "done":
                break
    s.close()
    time.sleep(1)
    m = requests.get(f"{BASE_URL}/api/conversations/{cid}/messages?limit=3",
                     headers=_h(demo_token), timeout=15).json()
    msgs = m.get("messages") or m
    found_ws = False
    for msg in msgs:
        extras = msg.get("extras") or {}
        if (msg.get("tool") == "workspace_search") or (extras.get("tool") == "workspace_search"):
            found_ws = True
        # Also check metadata or payload
        if msg.get("type") == "workspace_search" or extras.get("type") == "workspace_search":
            found_ws = True
    assert found_ws, f"expected workspace_search tool card; got messages: {msgs}"
