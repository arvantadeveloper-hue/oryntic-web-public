"""
Comprehensive workspace / multi-user feature tests.

Covers:
  - Admin role & migration (demo@aivora.ai)
  - Admin creates workspace users (POST /api/admin/users)
  - Regular-user restrictions (personas/wallet 403)
  - Shared wallet decrement (admin wallet drops when regular user chats)
  - Multi-human meeting access + invite semantics
  - Realtime WebSocket (connect, receive, auth rejections)
"""
import asyncio
import json
import os
import time
import uuid

import pytest
import requests
import websockets

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ai-companion-test-5.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
WS_BASE = BASE_URL.replace("https://", "wss://").replace("http://", "ws://") + "/api/ws/"

ADMIN_EMAIL = "demo@aivora.ai"
ADMIN_PW = os.environ.get("TEST_ADMIN_PASSWORD", "demo123456")
BUDI_EMAIL = "budi@aivora.ai"
BUDI_PW = os.environ.get("TEST_BUDI_PASSWORD", "budi123456")


# ---------------- helpers ----------------
def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return r.json()


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def admin_tok(admin):
    return admin["access_token"]


@pytest.fixture(scope="module")
def admin_user(admin):
    return admin["user"]


@pytest.fixture(scope="module")
def budi():
    return _login(BUDI_EMAIL, BUDI_PW)


@pytest.fixture(scope="module")
def budi_tok(budi):
    return budi["access_token"]


@pytest.fixture(scope="module")
def budi_user(budi):
    return budi["user"]


@pytest.fixture(scope="module")
def fresh_user(admin_tok):
    """Create a fresh test user via admin."""
    email = f"qa_user_{uuid.uuid4().hex[:8]}@aivora.ai"
    r = requests.post(f"{API}/admin/users",
                      headers=_hdr(admin_tok),
                      json={"email": email, "password": "qauser123", "name": "QA User"},
                      timeout=20)
    assert r.status_code == 200, r.text
    created = r.json()
    tok = _login(email, "qauser123")["access_token"]
    yield {"user": created, "token": tok, "email": email, "password": "qauser123"}
    # cleanup
    try:
        requests.delete(f"{API}/admin/users/{created['id']}", headers=_hdr(admin_tok), timeout=10)
    except Exception:
        pass


# =================================================================
# 1. Roles & migration
# =================================================================
class TestRoles:
    def test_admin_role_and_owner(self, admin_user):
        assert admin_user["role"] == "admin"
        assert admin_user["is_admin"]
        assert admin_user["owner_id"] == admin_user["id"]
        assert admin_user["email"] == ADMIN_EMAIL

    def test_me_reflects_admin(self, admin_tok, admin_user):
        r = requests.get(f"{API}/auth/me", headers=_hdr(admin_tok), timeout=15)
        assert r.status_code == 200
        me = r.json()
        assert me["role"] == "admin"
        assert me["owner_id"] == admin_user["id"]


# =================================================================
# 2. Admin creates users
# =================================================================
class TestAdminCreateUsers:
    def test_create_user_basics(self, fresh_user, admin_user):
        u = fresh_user["user"]
        assert u["role"] == "user"
        assert u["owner_id"] == admin_user["id"]
        assert not (u["is_admin"])

    def test_duplicate_email_409(self, admin_tok, fresh_user):
        r = requests.post(f"{API}/admin/users",
                          headers=_hdr(admin_tok),
                          json={"email": fresh_user["email"], "password": "another123", "name": "Dup"},
                          timeout=15)
        assert r.status_code == 409, r.text

    def test_workspace_users_list_contains(self, admin_tok, admin_user, fresh_user):
        r = requests.get(f"{API}/admin/workspace-users", headers=_hdr(admin_tok), timeout=15)
        assert r.status_code == 200
        ids = [x["id"] for x in r.json()]
        assert admin_user["id"] in ids
        assert fresh_user["user"]["id"] in ids

    def test_non_admin_create_user_403(self, budi_tok):
        r = requests.post(f"{API}/admin/users",
                          headers=_hdr(budi_tok),
                          json={"email": f"nope_{uuid.uuid4().hex[:6]}@a.ai", "password": "x123456"},
                          timeout=15)
        assert r.status_code == 403, r.text


# =================================================================
# 3. Regular-user restrictions
# =================================================================
class TestRegularUserRestrictions:
    def test_personas_create_403(self, budi_tok):
        r = requests.post(f"{API}/personas",
                          headers=_hdr(budi_tok),
                          json={"name": "X", "role": "friend"},
                          timeout=15)
        assert r.status_code == 403

    def test_personas_generate_profile_403(self, budi_tok):
        r = requests.post(f"{API}/personas/generate-profile",
                          headers=_hdr(budi_tok),
                          json={"hint": "x"},
                          timeout=15)
        assert r.status_code == 403

    def test_wallet_topup_403(self, budi_tok):
        r = requests.post(f"{API}/wallet/topup",
                          headers=_hdr(budi_tok),
                          json={"package_id": "starter"},
                          timeout=15)
        assert r.status_code == 403

    def test_shared_personas_visible(self, admin_tok, budi_tok):
        a = requests.get(f"{API}/personas", headers=_hdr(admin_tok), timeout=15).json()
        b = requests.get(f"{API}/personas", headers=_hdr(budi_tok), timeout=15).json()
        a_ids = sorted(p["id"] for p in a)
        b_ids = sorted(p["id"] for p in b)
        assert a_ids == b_ids, f"regular user should see same shared personas, admin={a_ids} budi={b_ids}"
        assert len(a_ids) > 0, "no shared personas available"

    def test_persona_update_delete_403(self, admin_tok, budi_tok):
        personas = requests.get(f"{API}/personas", headers=_hdr(admin_tok), timeout=15).json()
        pid = personas[0]["id"]
        r = requests.put(f"{API}/personas/{pid}", headers=_hdr(budi_tok),
                         json={"name": "Hack"}, timeout=15)
        assert r.status_code == 403, r.text
        r = requests.delete(f"{API}/personas/{pid}", headers=_hdr(budi_tok), timeout=15)
        assert r.status_code == 403, r.text

    def test_regular_can_get_shared_persona(self, admin_tok, budi_tok):
        personas = requests.get(f"{API}/personas", headers=_hdr(admin_tok), timeout=15).json()
        pid = personas[0]["id"]
        r = requests.get(f"{API}/personas/{pid}", headers=_hdr(budi_tok), timeout=15)
        assert r.status_code == 200


# =================================================================
# 4. Shared wallet
# =================================================================
class TestSharedWallet:
    def test_regular_user_decrements_admin_wallet(self, admin_tok, budi_tok):
        w0 = requests.get(f"{API}/wallet", headers=_hdr(admin_tok), timeout=15).json()
        before_available = float(w0.get("available", 0))
        before_consumed = float(w0.get("consumed", 0))

        personas = requests.get(f"{API}/personas", headers=_hdr(budi_tok), timeout=15).json()
        assert personas, "need shared personas"
        pid = personas[0]["id"]

        cv = requests.post(f"{API}/conversations",
                           headers=_hdr(budi_tok),
                           json={"persona_ids": [pid], "type": "private", "title": "TEST_wallet"},
                           timeout=20)
        assert cv.status_code == 200, cv.text
        cid = cv.json()["id"]

        # Send a short message (SSE); drain stream
        send = requests.post(f"{API}/conversations/{cid}/send",
                             headers=_hdr(budi_tok),
                             json={"content": "Halo singkat.", "attachments": [], "moderator": False},
                             stream=True, timeout=90)
        assert send.status_code == 200, send.text
        for _ in send.iter_lines():
            pass
        send.close()

        # small settle delay for record_usage
        time.sleep(2)
        w1 = requests.get(f"{API}/wallet", headers=_hdr(admin_tok), timeout=15).json()
        after_available = float(w1.get("available", 0))
        after_consumed = float(w1.get("consumed", 0))
        # Shared-wallet contract: regular user's AI usage must register against the admin's workspace wallet.
        # If admin has balance, 'available' must decrease; otherwise 'consumed' must increase.
        delta_consumed = after_consumed - before_consumed
        delta_available = before_available - after_available
        assert delta_consumed > 0 or delta_available > 0, (
            f"admin wallet did not register regular user's usage; "
            f"available {before_available}->{after_available}, consumed {before_consumed}->{after_consumed}"
        )


# =================================================================
# 5. Meeting + participants + invite
# =================================================================
@pytest.fixture(scope="module")
def meeting(admin_tok, budi_user):
    personas = requests.get(f"{API}/personas", headers=_hdr(admin_tok), timeout=15).json()
    pids = [p["id"] for p in personas[:2]]
    assert len(pids) >= 2, "need at least 2 shared personas for a meeting"
    r = requests.post(f"{API}/conversations",
                      headers=_hdr(admin_tok),
                      json={"persona_ids": pids, "type": "meeting",
                            "title": "TEST_meeting_ws",
                            "participant_ids": [budi_user["id"]]},
                      timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


class TestMeetingAccess:
    def test_meeting_in_regular_user_list(self, meeting, budi_tok):
        r = requests.get(f"{API}/conversations", headers=_hdr(budi_tok), timeout=15)
        assert r.status_code == 200
        ids = [c["id"] for c in r.json()]
        assert meeting["id"] in ids

    def test_both_can_send(self, meeting, admin_tok, budi_tok):
        for tok, who in [(admin_tok, "admin"), (budi_tok, "budi")]:
            r = requests.post(f"{API}/conversations/{meeting['id']}/send",
                              headers=_hdr(tok),
                              json={"content": f"ping dari {who}", "attachments": [], "moderator": False},
                              stream=True, timeout=90)
            assert r.status_code == 200, f"{who} send failed: {r.status_code} {r.text}"
            for _ in r.iter_lines():
                pass
            r.close()

    def test_outsider_cannot_access(self, meeting, fresh_user):
        """Fresh user is in the same workspace though — we need an outsider.
        We use the seeded super-admin (ADMIN_EMAIL from .env) who owns a DIFFERENT workspace.
        If not available, we skip."""
        env_email = os.environ.get("ADMIN_EMAIL")
        env_pw = os.environ.get("ADMIN_PASSWORD")
        if not (env_email and env_pw) or env_email.lower() == ADMIN_EMAIL:
            pytest.skip("No seeded super-admin available in a different workspace")
        try:
            super_tok = _login(env_email, env_pw)["access_token"]
        except AssertionError:
            pytest.skip("Could not login seeded super-admin")
        r = requests.get(f"{API}/conversations/{meeting['id']}/messages",
                         headers=_hdr(super_tok), timeout=15)
        assert r.status_code == 404, f"outsider should 404, got {r.status_code}"

    def test_invite_endpoint(self, meeting, admin_tok, budi_tok, fresh_user):
        # admin invite works
        r = requests.post(f"{API}/conversations/{meeting['id']}/participants",
                          headers=_hdr(admin_tok),
                          json={"user_ids": [fresh_user["user"]["id"]]}, timeout=15)
        assert r.status_code == 200, r.text

        # non-owner, non-admin participant invite -> 403
        r = requests.post(f"{API}/conversations/{meeting['id']}/participants",
                          headers=_hdr(budi_tok),
                          json={"user_ids": [fresh_user["user"]["id"]]}, timeout=15)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"

    def test_invite_on_private_400(self, admin_tok, budi_user):
        personas = requests.get(f"{API}/personas", headers=_hdr(admin_tok), timeout=15).json()
        pid = personas[0]["id"]
        r = requests.post(f"{API}/conversations",
                          headers=_hdr(admin_tok),
                          json={"persona_ids": [pid], "type": "private", "title": "TEST_priv"},
                          timeout=15)
        assert r.status_code == 200
        cid = r.json()["id"]
        r = requests.post(f"{API}/conversations/{cid}/participants",
                          headers=_hdr(admin_tok),
                          json={"user_ids": [budi_user["id"]]}, timeout=15)
        assert r.status_code == 400, r.text


# =================================================================
# 6. WebSocket realtime
# =================================================================
class TestWebSocket:
    def test_ws_connects_and_receives(self, meeting, admin_tok, budi_tok):
        cid = meeting["id"]

        async def run():
            url = f"{WS_BASE}{cid}?token={budi_tok}"
            async with websockets.connect(url, open_timeout=15) as ws:
                task = asyncio.create_task(asyncio.to_thread(
                    lambda: requests.post(
                        f"{API}/conversations/{cid}/send",
                        headers=_hdr(admin_tok),
                        json={"content": "WS test ping", "attachments": [], "moderator": False},
                        timeout=90, stream=True).close()))
                got = []
                try:
                    while len(got) < 1:
                        msg = await asyncio.wait_for(ws.recv(), timeout=45)
                        try:
                            got.append(json.loads(msg))
                        except Exception:
                            got.append({"raw": msg})
                except asyncio.TimeoutError:
                    pass
                await task
                return got

        got = asyncio.run(run())
        assert len(got) >= 1, "No WS frames received"
        assert any("type" in g for g in got), f"frames missing 'type': {got}"

    def test_ws_invalid_token_rejected(self, meeting):
        async def run():
            url = f"{WS_BASE}{meeting['id']}?token=not-a-valid-jwt"
            try:
                async with websockets.connect(url, open_timeout=10) as ws:
                    await asyncio.wait_for(ws.recv(), timeout=5)
                return "connected"
            except Exception as e:
                return f"rejected:{type(e).__name__}"

        res = asyncio.run(run())
        assert res.startswith("rejected"), f"WS with invalid token should be rejected, got {res}"

    def test_ws_forbidden_conversation(self, admin_tok, budi_tok):
        personas = requests.get(f"{API}/personas", headers=_hdr(admin_tok), timeout=15).json()
        pid = personas[0]["id"]
        r = requests.post(f"{API}/conversations",
                          headers=_hdr(admin_tok),
                          json={"persona_ids": [pid], "type": "private", "title": "TEST_priv_ws"},
                          timeout=15)
        assert r.status_code == 200
        cid = r.json()["id"]

        async def run():
            url = f"{WS_BASE}{cid}?token={budi_tok}"
            try:
                async with websockets.connect(url, open_timeout=10) as ws:
                    await asyncio.wait_for(ws.recv(), timeout=5)
                return "connected"
            except Exception as e:
                return f"rejected:{type(e).__name__}"

        res = asyncio.run(run())
        assert res.startswith("rejected"), f"WS to forbidden conv should be rejected, got {res}"
