"""
Backend tests for Oryntix support agent (persona + conversation + video) + admin.
"""
import os, json, time
import pytest
import requests
import sys as _sys; _sys.path.insert(0, '/app/backend/tests')  # noqa: E702
from creds import DEMO_PASSWORD, ADMIN_PASSWORD, BUDI_PASSWORD  # noqa: E402,F401

BASE = os.environ.get("REACT_APP_BACKEND_URL") or [
    l.split("=", 1)[1].strip() for l in open("/app/frontend/.env") if l.startswith("REACT_APP_BACKEND_URL")
][0]
API = BASE.rstrip("/") + "/api"

DEMO = {"email": "demo@aivora.ai", "password": DEMO_PASSWORD}
ADMIN = {"email": "admin@aivora.ai", "password": ADMIN_PASSWORD}


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{API}/auth/login", json=DEMO, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# --- Personas ---
def test_personas_lists_oryntix_first(demo_token):
    r = requests.get(f"{API}/personas", headers=H(demo_token), timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) > 0
    p = data[0]
    assert p["id"] == "oryntix-support"
    assert p.get("builtin") is True
    assert p["name"] == "Oryntix"
    assert p["model"] == "gpt-luna"
    assert p.get("voice_model") == "gpt-realtime-2.1-mini"
    assert p.get("tools") == []
    assert p.get("video_avatar") is True


def test_persona_detail_oryntix(demo_token):
    r = requests.get(f"{API}/personas/oryntix-support", headers=H(demo_token), timeout=20)
    assert r.status_code == 200
    assert r.json()["id"] == "oryntix-support"


def test_persona_update_oryntix_forbidden(demo_token):
    r = requests.put(f"{API}/personas/oryntix-support", headers=H(demo_token), json={"name": "x"}, timeout=20)
    assert r.status_code in (403, 404)


def test_persona_delete_oryntix_forbidden(demo_token):
    r = requests.delete(f"{API}/personas/oryntix-support", headers=H(demo_token), timeout=20)
    assert r.status_code in (403, 404)


# --- Conversations ---
@pytest.fixture(scope="module")
def support_cid(demo_token):
    r = requests.post(
        f"{API}/conversations",
        json={"persona_ids": ["oryntix-support"], "type": "private"},
        headers=H(demo_token), timeout=20
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["members"][0].get("builtin") is True
    return data["id"]


def test_support_conv_group_rejected(demo_token):
    r = requests.post(f"{API}/conversations",
                      json={"persona_ids": ["oryntix-support"], "type": "group"},
                      headers=H(demo_token), timeout=20)
    assert r.status_code == 400
    assert "privat" in (r.json().get("detail") or "").lower()


def test_support_conv_with_other_persona_rejected(demo_token):
    # grab a non-support persona
    plist = requests.get(f"{API}/personas", headers=H(demo_token)).json()
    other = next((p["id"] for p in plist if p["id"] != "oryntix-support"), None)
    assert other
    r = requests.post(f"{API}/conversations",
                      json={"persona_ids": ["oryntix-support", other], "type": "private"},
                      headers=H(demo_token), timeout=20)
    assert r.status_code == 400


# --- Chat (SSE) on support ---
def _stream_final(demo_token, cid, text):
    rr = requests.post(f"{API}/conversations/{cid}/send",
                       json={"content": text},
                       headers=H(demo_token), stream=True, timeout=180)
    final = None
    for line in rr.iter_lines():
        if line and line.startswith(b"data:"):
            try:
                ev = json.loads(line[5:].strip())
            except Exception:
                continue
            if ev.get("final"):
                final = ev
    return final


@pytest.mark.slow
def test_support_chat_knowledge(demo_token, support_cid):
    final = _stream_final(demo_token, support_cid,
        "Bagaimana cara membuat pengingat berulang di Oryntix? jawab singkat")
    assert final is not None, "no final SSE event"
    content = (final.get("content") or "").lower()
    assert len(content) > 10
    assert "pengingat" in content or "reminder" in content
    assert not final.get("pending_tool")


@pytest.mark.slow
def test_support_chat_no_image_tool(demo_token, support_cid):
    final = _stream_final(demo_token, support_cid, "buat gambar kucing")
    assert final is not None
    assert not final.get("pending_tool"), f"support should not emit image pending_tool, got: {final.get('pending_tool')}"
    assert (final.get("content") or "").strip() != ""


# --- Support video-config ---
def test_video_config(demo_token):
    r = requests.get(f"{API}/support/video-config", headers=H(demo_token), timeout=20)
    assert r.status_code == 200
    d = r.json()
    assert d["enabled"] is True
    assert d["credits_per_sec"] == 2
    assert d["max_minutes"] == 20
    assert d["warn_minutes"] == 2
    assert d["max_cost"] == 2400
    assert d["sandbox"] is True


# --- Realtime call + video flow ---
@pytest.fixture(scope="module")
def call_id(demo_token, support_cid):
    r = requests.post(f"{API}/realtime/calls",
                      json={"conversation_id": support_cid},
                      headers=H(demo_token), timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["model"] == "gpt-realtime-2.1-mini"
    assert j["persona"]["name"] == "Oryntix"
    yield j["call_id"]
    try:
        requests.post(f"{API}/realtime/calls/{j['call_id']}/end",
                      json={"elapsed_seconds": 0}, headers=H(demo_token), timeout=20)
    except Exception:
        pass


def test_video_start_and_lifecycle(demo_token, call_id):
    v = requests.post(f"{API}/realtime/calls/{call_id}/video/start",
                      headers=H(demo_token), timeout=60)
    assert v.status_code == 200, v.text
    j = v.json()
    assert j.get("livekit_url") and j.get("livekit_client_token") and j.get("ws_url")
    assert j.get("max_seconds") == 60  # sandbox
    assert j.get("warn_seconds") == 45
    assert j.get("credits_per_sec") == 2

    # second start -> 409
    v2 = requests.post(f"{API}/realtime/calls/{call_id}/video/start",
                       headers=H(demo_token), timeout=30)
    assert v2.status_code == 409

    # tick
    t = requests.post(f"{API}/realtime/calls/{call_id}/video/tick",
                      json={"elapsed_seconds": 20}, headers=H(demo_token), timeout=20)
    assert t.status_code == 200, t.text
    jt = t.json()
    assert jt.get("ended") is False
    assert jt.get("credits") == 40
    assert jt.get("remaining") == 40

    # stop
    s = requests.post(f"{API}/realtime/calls/{call_id}/video/stop",
                      json={"elapsed_seconds": 35}, headers=H(demo_token), timeout=20)
    assert s.status_code == 200, s.text
    js = s.json()
    assert js.get("credits") == 70
    assert js.get("seconds") == 35

    # tick after stop -> 404
    t2 = requests.post(f"{API}/realtime/calls/{call_id}/video/tick",
                       json={"elapsed_seconds": 40}, headers=H(demo_token), timeout=20)
    assert t2.status_code == 404


def test_video_start_on_non_support_call_404(demo_token):
    # pick a non-support persona and open a private conv + call
    plist = requests.get(f"{API}/personas", headers=H(demo_token)).json()
    other = next((p for p in plist if p["id"] != "oryntix-support"), None)
    assert other
    cv = requests.post(f"{API}/conversations",
                       json={"persona_ids": [other["id"]], "type": "private"},
                       headers=H(demo_token), timeout=20)
    assert cv.status_code == 200
    cid = cv.json()["id"]
    rc = requests.post(f"{API}/realtime/calls",
                       json={"conversation_id": cid},
                       headers=H(demo_token), timeout=30)
    assert rc.status_code == 200
    cid_call = rc.json()["call_id"]
    try:
        v = requests.post(f"{API}/realtime/calls/{cid_call}/video/start",
                          headers=H(demo_token), timeout=20)
        assert v.status_code == 404
    finally:
        requests.post(f"{API}/realtime/calls/{cid_call}/end",
                      json={"elapsed_seconds": 0}, headers=H(demo_token), timeout=20)


# --- Admin ---
def test_admin_support_agent_requires_platform_admin(demo_token, admin_token):
    r = requests.get(f"{API}/admin/support-agent", headers=H(demo_token), timeout=20)
    assert r.status_code == 403

    r2 = requests.get(f"{API}/admin/support-agent", headers=H(admin_token), timeout=20)
    assert r2.status_code == 200, r2.text
    d = r2.json()
    assert d.get("liveavatar_key_set") is True
    assert d.get("avatar_id") == "5341767a-21fe-43d7-a5b5-9fd6bff6d32e"


def test_admin_support_agent_update_credits(admin_token, demo_token):
    try:
        r = requests.put(f"{API}/admin/support-agent",
                         json={"video_credits_per_sec": 3},
                         headers=H(admin_token), timeout=20)
        assert r.status_code == 200, r.text
        # check propagation
        cfg = requests.get(f"{API}/support/video-config", headers=H(demo_token), timeout=20).json()
        assert cfg["credits_per_sec"] == 3
    finally:
        # restore
        requests.put(f"{API}/admin/support-agent",
                     json={"video_credits_per_sec": 2},
                     headers=H(admin_token), timeout=20)
        cfg = requests.get(f"{API}/support/video-config", headers=H(demo_token), timeout=20).json()
        assert cfg["credits_per_sec"] == 2


def test_admin_support_agent_avatars_list(admin_token):
    r = requests.get(f"{API}/admin/support-agent/avatars?mine=true",
                     headers=H(admin_token), timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert "items" in d
    assert isinstance(d["items"], list)
