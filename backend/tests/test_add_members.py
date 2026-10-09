"""Tests for POST /api/conversations/{cid}/members (host invites friends/personas mid-call)."""
import os
import pytest
import requests
from dotenv import load_dotenv
import sys as _sys; _sys.path.insert(0, '/app/backend/tests')  # noqa: E702
from creds import DEMO_PASSWORD, ADMIN_PASSWORD, BUDI_PASSWORD  # noqa: E402,F401

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
DEMO = {"email": "demo@aivora.ai", "password": DEMO_PASSWORD}
BUDI = {"email": "budi@aivora.ai", "password": BUDI_PASSWORD}
BUDI_ID = "0a0e91ef-25fc-4900-b74e-dfe988a5b031"
RIO = "e93a66a6-59b1-4a12-8c16-0c9dba6c3348"
NOVA = "4d4b348c-ce16-431d-8927-5a76d66ae9ef"
NADIA = "77f5be90-dd50-407c-b9b9-5f604e13447c"


def _login(creds):
    r = requests.post(f"{BASE}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def demo_tok():
    return _login(DEMO)


@pytest.fixture(scope="module")
def budi_tok():
    return _login(BUDI)


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _mk_private(tok, persona_id):
    """Create a fresh private conv explicitly (not direct, which may reuse)."""
    r = requests.post(f"{BASE}/api/conversations",
                      json={"type": "private", "persona_ids": [persona_id]},
                      headers=_h(tok), timeout=20)
    assert r.status_code in (200, 201), r.text
    conv = r.json()
    assert conv["type"] == "private"
    return conv


class TestAddMembersHappyPath:
    def test_host_invites_friend_and_persona_converts_to_group(self, demo_tok):
        conv = _mk_private(demo_tok, NADIA)
        cid = conv["id"]
        r = requests.post(f"{BASE}/api/conversations/{cid}/members",
                          json={"friend_ids": [BUDI_ID], "persona_ids": [RIO]},
                          headers=_h(demo_tok), timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["type"] == "group"
        assert BUDI_ID in (data.get("participants") or [])
        assert len(data.get("humans") or []) == 2
        pids = data.get("persona_ids") or []
        assert RIO in pids and NADIA in pids
        assert (data.get("title") or "").startswith("Grup:")

        # System message appended
        m = requests.get(f"{BASE}/api/conversations/{cid}/messages", headers=_h(demo_tok), timeout=20)
        assert m.status_code == 200
        msgs = m.json()
        joined = " ".join([x.get("content", "") for x in (msgs if isinstance(msgs, list) else msgs.get("messages", []))])
        assert "mengundang" in joined and "Budi" in joined

    def test_budi_can_access_after_invite(self, demo_tok, budi_tok):
        conv = _mk_private(demo_tok, NOVA)
        cid = conv["id"]
        r = requests.post(f"{BASE}/api/conversations/{cid}/members",
                          json={"friend_ids": [BUDI_ID]}, headers=_h(demo_tok), timeout=20)
        assert r.status_code == 200, r.text
        # Budi can GET messages
        m = requests.get(f"{BASE}/api/conversations/{cid}/messages", headers=_h(budi_tok), timeout=20)
        assert m.status_code == 200, m.text
        # Appears in Budi's conv list
        lst = requests.get(f"{BASE}/api/conversations", headers=_h(budi_tok), timeout=20).json()
        items = lst if isinstance(lst, list) else lst.get("items", lst.get("conversations", []))
        assert any(c.get("id") == cid for c in items)


class TestAddMembersAuth:
    def test_non_host_participant_gets_403(self, demo_tok, budi_tok):
        conv = _mk_private(demo_tok, NADIA)
        cid = conv["id"]
        # Add budi first
        requests.post(f"{BASE}/api/conversations/{cid}/members",
                      json={"friend_ids": [BUDI_ID]}, headers=_h(demo_tok), timeout=20)
        # Budi now tries to invite someone
        r = requests.post(f"{BASE}/api/conversations/{cid}/members",
                          json={"persona_ids": [RIO]}, headers=_h(budi_tok), timeout=20)
        assert r.status_code == 403, r.text
        assert "host" in (r.json().get("detail") or "").lower()

    def test_non_participant_gets_404(self, demo_tok, budi_tok):
        conv = _mk_private(demo_tok, NOVA)
        cid = conv["id"]
        # Budi is NOT part of this conv
        r = requests.post(f"{BASE}/api/conversations/{cid}/members",
                          json={"persona_ids": [RIO]}, headers=_h(budi_tok), timeout=20)
        assert r.status_code == 404, r.text

    def test_only_existing_ids_returns_400(self, demo_tok):
        conv = _mk_private(demo_tok, NADIA)
        cid = conv["id"]
        # Nadia is already in conv
        r = requests.post(f"{BASE}/api/conversations/{cid}/members",
                          json={"persona_ids": [NADIA]}, headers=_h(demo_tok), timeout=20)
        assert r.status_code == 400, r.text
        assert "Tidak ada" in (r.json().get("detail") or "")

    def test_unknown_ids_returns_400(self, demo_tok):
        conv = _mk_private(demo_tok, NADIA)
        cid = conv["id"]
        r = requests.post(f"{BASE}/api/conversations/{cid}/members",
                          json={"persona_ids": ["nonexistent-id-xyz"],
                                "friend_ids": ["nonexistent-user-id"]},
                          headers=_h(demo_tok), timeout=20)
        assert r.status_code == 400, r.text


class TestAddMembersGroupConv:
    def test_add_persona_to_existing_group_and_moderator_patch(self, demo_tok):
        conv = _mk_private(demo_tok, NADIA)
        cid = conv["id"]
        # Convert to group with Rio
        r1 = requests.post(f"{BASE}/api/conversations/{cid}/members",
                           json={"persona_ids": [RIO]}, headers=_h(demo_tok), timeout=20)
        assert r1.status_code == 200
        assert r1.json()["type"] == "group"
        # Add Nova
        r2 = requests.post(f"{BASE}/api/conversations/{cid}/members",
                           json={"persona_ids": [NOVA]}, headers=_h(demo_tok), timeout=20)
        assert r2.status_code == 200, r2.text
        d = r2.json()
        pids = set(d.get("persona_ids") or [])
        assert {NADIA, RIO, NOVA}.issubset(pids)
        # Moderator PATCH on the newly added persona
        rm = requests.patch(f"{BASE}/api/conversations/{cid}/moderator",
                            json={"persona_id": NOVA}, headers=_h(demo_tok), timeout=20)
        assert rm.status_code in (200, 204), rm.text
