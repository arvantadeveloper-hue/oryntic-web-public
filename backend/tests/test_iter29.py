"""Iter29 — Metered TURN ICE, call presence/leave/incoming."""
import os
import re
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
DM_CID = "5e6c2fc5-1f37-4c25-9932-2ca64929dfa8"  # demo <-> budi DM


def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def demo_token():
    return _login("demo@aivora.ai", "demo123456")


@pytest.fixture(scope="module")
def budi_token():
    return _login("budi@aivora.ai", "budi123456")


def H(t):
    return {"Authorization": f"Bearer {t}"}


# ---------- ICE / TURN ----------
def test_ice_servers_turn_true(demo_token):
    r = requests.get(f"{BASE}/api/rtc/ice-servers", headers=H(demo_token), timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["turn"] is True, data
    urls = []
    for srv in data["iceServers"]:
        u = srv.get("urls")
        urls.extend(u if isinstance(u, list) else [u])
    assert any(str(u).startswith("turn:") for u in urls), urls
    # at least one TURN entry has username+credential
    has_cred = any(("username" in s and "credential" in s) for s in data["iceServers"] if any(str(u).startswith("turn:") for u in ([s.get("urls")] if isinstance(s.get("urls"), str) else s.get("urls") or [])))
    assert has_cred, data


def test_ice_servers_unauth():
    r = requests.get(f"{BASE}/api/rtc/ice-servers", timeout=10)
    assert r.status_code in (401, 403)


# ---------- call presence/leave/incoming ----------
def test_presence_then_incoming_for_budi(demo_token, budi_token):
    # ensure clean: both leave
    requests.post(f"{BASE}/api/conversations/{DM_CID}/call/leave", headers=H(demo_token), timeout=10)
    requests.post(f"{BASE}/api/conversations/{DM_CID}/call/leave", headers=H(budi_token), timeout=10)

    r = requests.post(f"{BASE}/api/conversations/{DM_CID}/call/presence", headers=H(demo_token), timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    # budi sees incoming
    r = requests.get(f"{BASE}/api/calls/incoming", headers=H(budi_token), timeout=10)
    assert r.status_code == 200, r.text
    items = r.json()
    match = [x for x in items if x["conversation_id"] == DM_CID]
    assert match, items
    it = match[0]
    assert "Demo" in it["callers"], it
    assert it["title"]  # should be some title; from budi's perspective it's the DM title

    # demo sees own-call excluded
    r2 = requests.get(f"{BASE}/api/calls/incoming", headers=H(demo_token), timeout=10)
    assert r2.status_code == 200
    assert not any(x["conversation_id"] == DM_CID for x in r2.json())


def test_leave_removes_incoming(demo_token, budi_token):
    requests.post(f"{BASE}/api/conversations/{DM_CID}/call/presence", headers=H(demo_token), timeout=10)
    r = requests.post(f"{BASE}/api/conversations/{DM_CID}/call/leave", headers=H(demo_token), timeout=10)
    assert r.status_code == 200
    r2 = requests.get(f"{BASE}/api/calls/incoming", headers=H(budi_token), timeout=10)
    assert not any(x["conversation_id"] == DM_CID for x in r2.json())


def test_presence_404_on_non_participant(demo_token, budi_token):
    budi_me = requests.get(f"{BASE}/api/auth/me", headers=H(budi_token), timeout=10).json()
    budi_id = budi_me["id"]
    r = requests.get(f"{BASE}/api/conversations", headers=H(demo_token), timeout=15)
    convs = r.json() if isinstance(r.json(), list) else r.json().get("conversations", [])
    private_cid = None
    for c in convs:
        if c["id"] == DM_CID:
            continue
        parts = c.get("participants") or []
        if budi_id not in parts:
            private_cid = c["id"]; break
    assert private_cid, "no demo conversation found that excludes budi"
    r = requests.post(f"{BASE}/api/conversations/{private_cid}/call/presence", headers=H(budi_token), timeout=10)
    assert r.status_code == 404, (r.status_code, r.text)


def test_incoming_shape(demo_token, budi_token):
    requests.post(f"{BASE}/api/conversations/{DM_CID}/call/leave", headers=H(budi_token), timeout=10)
    requests.post(f"{BASE}/api/conversations/{DM_CID}/call/presence", headers=H(demo_token), timeout=10)
    r = requests.get(f"{BASE}/api/calls/incoming", headers=H(budi_token), timeout=10)
    items = [x for x in r.json() if x["conversation_id"] == DM_CID]
    assert items
    it = items[0]
    for k in ("conversation_id", "callers", "title", "started_at"):
        assert k in it, it
    assert isinstance(it["callers"], list) and len(it["callers"]) >= 1
    requests.post(f"{BASE}/api/conversations/{DM_CID}/call/leave", headers=H(demo_token), timeout=10)
