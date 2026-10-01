"""Oryntix iteration-12 backend tests: rate limits + realtime multi-meeting + tick max duration."""
import os
import time
import pytest
import requests
from pathlib import Path

def _load_base():
    env = Path("/app/frontend/.env").read_text()
    for line in env.splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

BASE = _load_base()
ADMIN = {"email": "demo@aivora.ai", "password": os.environ.get("TEST_ADMIN_PASSWORD", "demo123456")}
BUDI = {"email": "budi@aivora.ai", "password": os.environ.get("TEST_BUDI_PASSWORD", "budi123456")}


def _login(creds):
    r = requests.post(f"{BASE}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_h():
    return {"Authorization": f"Bearer {_login(ADMIN)}"}


@pytest.fixture(scope="module")
def budi_h():
    return {"Authorization": f"Bearer {_login(BUDI)}"}


# ----- rate-limits admin endpoints -----
def test_rate_limits_defaults_and_rbac(admin_h, budi_h):
    r = requests.get(f"{BASE}/api/admin/rate-limits", headers=admin_h, timeout=20)
    assert r.status_code == 200
    d = r.json()
    for k, v in {"chat_per_min": 20, "voice_per_min": 30, "calls_per_hour": 20,
                 "max_call_minutes": 60, "generation_per_hour": 30}.items():
        assert d.get(k) == v, f"{k}={d.get(k)}"

    # budi forbidden
    r = requests.get(f"{BASE}/api/admin/rate-limits", headers=budi_h, timeout=20)
    assert r.status_code == 403
    r = requests.put(f"{BASE}/api/admin/rate-limits", headers=budi_h, json=d, timeout=20)
    assert r.status_code == 403

    # validation
    r = requests.put(f"{BASE}/api/admin/rate-limits", headers=admin_h,
                     json={**d, "chat_per_min": 0}, timeout=20)
    assert r.status_code == 422

    # PUT update to 3
    r = requests.put(f"{BASE}/api/admin/rate-limits", headers=admin_h,
                     json={"chat_per_min": 3, "voice_per_min": 30, "calls_per_hour": 20,
                           "max_call_minutes": 60, "generation_per_hour": 30}, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["chat_per_min"] == 3


# ----- chat rate limiting -----
def test_chat_rate_limit_429(admin_h, budi_h):
    # ensure chat_per_min=3 set
    r = requests.put(f"{BASE}/api/admin/rate-limits", headers=admin_h,
                     json={"chat_per_min": 3, "voice_per_min": 30, "calls_per_hour": 20,
                           "max_call_minutes": 60, "generation_per_hour": 30}, timeout=20)
    assert r.status_code == 200

    # wait 35s for cache
    time.sleep(35)

    # budi needs a conversation with a persona. list conversations or create one.
    # Get workspace personas visible to budi
    r = requests.get(f"{BASE}/api/personas", headers=budi_h, timeout=20)
    assert r.status_code == 200
    personas = r.json()
    assert personas, "Budi needs ≥1 persona"
    pid = personas[0]["id"]

    # Create private conv
    r = requests.post(f"{BASE}/api/conversations", headers=budi_h,
                     json={"type": "private", "persona_ids": [pid], "title": "TEST_rl_budi"}, timeout=20)
    assert r.status_code in (200, 201), r.text
    cid = r.json()["id"]

    codes = []
    for i in range(4):
        r = requests.post(f"{BASE}/api/conversations/{cid}/send", headers=budi_h,
                         json={"content": f"hi {i}"}, timeout=60, stream=True)
        codes.append(r.status_code)
        # consume quickly to free the connection
        try:
            for _ in r.iter_content(chunk_size=4096):
                break
        except Exception:
            pass
        r.close()
    print("codes:", codes)
    assert codes[-1] == 429, f"expected last=429, got {codes}"
    # verify Indonesian detail on a fresh call
    r = requests.post(f"{BASE}/api/conversations/{cid}/send", headers=budi_h,
                     json={"content": "x"}, timeout=20)
    assert r.status_code == 429
    assert "Terlalu banyak" in r.text and "3/menit" in r.text


# ----- admin not rate-limited at same low number (per-user bucket, admin has own counter but same limit=3; so admin would also be limited). The task says 'Regression: admin not limited at 20/min' — ensure we RESTORE to 20 first then verify admin burst is OK.
def test_restore_and_admin_regression(admin_h):
    r = requests.put(f"{BASE}/api/admin/rate-limits", headers=admin_h,
                     json={"chat_per_min": 20, "voice_per_min": 30, "calls_per_hour": 20,
                           "max_call_minutes": 60, "generation_per_hour": 30}, timeout=20)
    assert r.status_code == 200
    time.sleep(35)

    r = requests.get(f"{BASE}/api/personas", headers=admin_h, timeout=20)
    personas = r.json()
    pid = personas[0]["id"]
    r = requests.post(f"{BASE}/api/conversations", headers=admin_h,
                     json={"type": "private", "persona_ids": [pid], "title": "TEST_rl_admin"}, timeout=20)
    cid = r.json()["id"]
    # 5 sends should all stream (not 429) under limit=20
    for i in range(5):
        r = requests.post(f"{BASE}/api/conversations/{cid}/send", headers=admin_h,
                         json={"content": f"ok {i}"}, timeout=60, stream=True)
        assert r.status_code == 200, f"iter={i} code={r.status_code} body={r.text[:200]}"
        for _ in r.iter_content(chunk_size=4096):
            break
        r.close()


# ----- voice tts smoke -----
def test_voice_tts_ok(admin_h):
    r = requests.post(f"{BASE}/api/voice/tts", headers=admin_h,
                     json={"text": "halo", "voice": "nova"}, timeout=30)
    assert r.status_code == 200, r.text


# ----- realtime calls: multi and single -----
def test_realtime_calls_multi_and_single(admin_h):
    r = requests.get(f"{BASE}/api/personas", headers=admin_h, timeout=20)
    personas = [p for p in r.json() if not p.get("deleted")]
    assert len(personas) >= 2, "need 2 personas for multi meeting"
    p1, p2 = personas[0]["id"], personas[1]["id"]

    # MEETING conv with 2 personas
    r = requests.post(f"{BASE}/api/conversations", headers=admin_h,
                     json={"type": "meeting", "persona_ids": [p1, p2], "title": "TEST_meet_multi"}, timeout=20)
    assert r.status_code in (200, 201), r.text
    mcid = r.json()["id"]

    r = requests.post(f"{BASE}/api/realtime/calls", headers=admin_h,
                     json={"conversation_id": mcid}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["multi"] is True
    assert len(body["sessions"]) == 2
    assert sum(1 for s in body["sessions"] if s["primary"]) == 1
    assert body["credits_per_min_total"] == 2 * body["credits_per_min"]
    assert body.get("group_id")
    for s in body["sessions"]:
        assert s["persona"]["id"] and s["persona"]["name"]
        # cleanup
        er = requests.post(f"{BASE}/api/realtime/calls/{s['call_id']}/end", headers=admin_h,
                          json={"elapsed_seconds": 0}, timeout=20)
        assert er.status_code == 200, er.text

    # PRIVATE conv → multi:false
    r = requests.post(f"{BASE}/api/conversations", headers=admin_h,
                     json={"type": "private", "persona_ids": [p1], "title": "TEST_meet_single"}, timeout=20)
    pcid = r.json()["id"]
    r = requests.post(f"{BASE}/api/realtime/calls", headers=admin_h,
                     json={"conversation_id": pcid}, timeout=30)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["multi"] is False
    assert len(b["sessions"]) == 1
    requests.post(f"{BASE}/api/realtime/calls/{b['sessions'][0]['call_id']}/end",
                 headers=admin_h, json={"elapsed_seconds": 0}, timeout=20)


# ----- tick max duration -----
def test_tick_max_duration_402(admin_h):
    # check admin credits first
    me = requests.get(f"{BASE}/api/auth/me", headers=admin_h, timeout=20).json()
    credits = me.get("credits", 0)
    if credits < 5000:
        pytest.skip(f"admin credits {credits} < 5000, skipping max-duration bill test")

    r = requests.get(f"{BASE}/api/personas", headers=admin_h, timeout=20)
    pid = r.json()[0]["id"]
    r = requests.post(f"{BASE}/api/conversations", headers=admin_h,
                     json={"type": "private", "persona_ids": [pid], "title": "TEST_tick_max"}, timeout=20)
    pcid = r.json()["id"]
    r = requests.post(f"{BASE}/api/realtime/calls", headers=admin_h,
                     json={"conversation_id": pcid}, timeout=30)
    call_id = r.json()["sessions"][0]["call_id"]

    r = requests.post(f"{BASE}/api/realtime/calls/{call_id}/tick", headers=admin_h,
                     json={"elapsed_seconds": 3601}, timeout=30)
    assert r.status_code == 402, r.text
    assert "Durasi maksimal" in r.text
