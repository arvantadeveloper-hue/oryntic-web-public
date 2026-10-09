"""Backend tests for iteration 8: reminder-call voice response, daily quota enforce+display, invite link."""
import os
import uuid
import pytest
import requests
import sys as _sys; _sys.path.insert(0, '/app/backend/tests')  # noqa: E702
from creds import DEMO_PASSWORD, ADMIN_PASSWORD, BUDI_PASSWORD  # noqa: E402,F401

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

ADMIN = {"email": "demo@aivora.ai", "password": os.environ.get("TEST_ADMIN_PASSWORD", DEMO_PASSWORD)}
BUDI = {"email": "budi@aivora.ai", "password": os.environ.get("TEST_BUDI_PASSWORD", BUDI_PASSWORD)}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_tok():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def budi_tok():
    return _login(BUDI)


@pytest.fixture(scope="module")
def budi_id(admin_tok):
    r = requests.get(f"{API}/admin/workspace-users", headers=_h(admin_tok))
    assert r.status_code == 200, r.text
    for u in r.json():
        if u["email"] == BUDI["email"]:
            return u["id"]
    pytest.skip("budi not in workspace")


@pytest.fixture(scope="module")
def shared_persona(admin_tok):
    r = requests.get(f"{API}/personas", headers=_h(admin_tok))
    assert r.status_code == 200
    personas = [p for p in r.json() if p.get("name")]
    assert personas, "need at least 1 persona"
    return personas[0]


# ---------------- Reminder-call voice response ----------------

class TestReminderRespond:
    def test_accept_with_persona_returns_message_conversation(self, budi_tok, shared_persona):
        # create reminder: start_at ~5min in future, remind_minutes 30 => remind_at in past
        from datetime import datetime, timezone, timedelta
        start = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        payload = {"title": "TEST_rapat_pagi", "description": "Diskusi roadmap",
                   "start_at": start, "remind_minutes": 30, "persona_id": shared_persona["id"]}
        r = requests.post(f"{API}/reminders", json=payload, headers=_h(budi_tok))
        assert r.status_code == 200, r.text
        rid = r.json()["id"]

        r2 = requests.post(f"{API}/reminders/{rid}/respond",
                           json={"action": "accept"}, headers=_h(budi_tok))
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert data["status"] == "answered"
        assert data["message"] and isinstance(data["message"], str) and len(data["message"]) > 5
        assert "persona" in data
        assert data["persona"]["id"] == shared_persona["id"]
        assert data["persona"]["name"]
        assert "voice" in data["persona"]
        assert "conversation" in data
        conv = data["conversation"]
        assert "id" in conv and "members" in conv
        assert conv["type"] == "private"
        # cleanup
        requests.delete(f"{API}/reminders/{rid}", headers=_h(budi_tok))

    def test_accept_without_persona_returns_message_only(self, budi_tok):
        from datetime import datetime, timezone, timedelta
        start = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        payload = {"title": "TEST_notes", "description": "", "start_at": start, "remind_minutes": 30}
        r = requests.post(f"{API}/reminders", json=payload, headers=_h(budi_tok))
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        r2 = requests.post(f"{API}/reminders/{rid}/respond", json={"action": "accept"}, headers=_h(budi_tok))
        assert r2.status_code == 200, r2.text
        d = r2.json()
        assert d["message"]
        assert "conversation" not in d
        assert "persona" not in d
        requests.delete(f"{API}/reminders/{rid}", headers=_h(budi_tok))

    def test_decline(self, budi_tok):
        from datetime import datetime, timezone, timedelta
        start = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        r = requests.post(f"{API}/reminders",
                          json={"title": "TEST_decline", "start_at": start, "remind_minutes": 30},
                          headers=_h(budi_tok))
        rid = r.json()["id"]
        r2 = requests.post(f"{API}/reminders/{rid}/respond",
                           json={"action": "decline"}, headers=_h(budi_tok))
        assert r2.status_code == 200
        assert r2.json() == {"status": "declined"}
        requests.delete(f"{API}/reminders/{rid}", headers=_h(budi_tok))


# ---------------- Daily credit quota ----------------

class TestDailyQuota:
    def test_patch_quota_and_workspace_users_shows_it(self, admin_tok, budi_id):
        r = requests.patch(f"{API}/admin/users/{budi_id}", json={"daily_credit_limit": 1},
                           headers=_h(admin_tok))
        assert r.status_code == 200, r.text
        assert r.json()["daily_credit_limit"] == 1
        # workspace-users reflects
        wu = requests.get(f"{API}/admin/workspace-users", headers=_h(admin_tok)).json()
        row = next(u for u in wu if u["id"] == budi_id)
        assert row["daily_credit_limit"] == 1
        assert isinstance(row["today_usage"], int) or isinstance(row["today_usage"], float)

    def test_quota_blocks_regular_user_with_402(self, admin_tok, budi_tok, shared_persona):
        # ensure quota=1 (likely already exceeded by prior usage)
        # create a private conv
        r = requests.post(f"{API}/conversations",
                          json={"persona_ids": [shared_persona["id"]], "type": "private"},
                          headers=_h(budi_tok))
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        # send message; expect 402 Indonesian "Kuota kredit harian"
        r2 = requests.post(f"{API}/conversations/{cid}/send",
                           json={"content": "halo"}, headers=_h(budi_tok), stream=False)
        assert r2.status_code == 402, f"expected 402, got {r2.status_code}: {r2.text}"
        assert "Kuota kredit harian" in r2.text

    def test_reset_quota_unlocks_and_admin_unlimited(self, admin_tok, budi_tok, budi_id, shared_persona):
        r = requests.patch(f"{API}/admin/users/{budi_id}", json={"daily_credit_limit": 0},
                           headers=_h(admin_tok))
        assert r.status_code == 200
        assert r.json()["daily_credit_limit"] == 0
        # budi sends again
        r = requests.post(f"{API}/conversations",
                          json={"persona_ids": [shared_persona["id"]], "type": "private"},
                          headers=_h(budi_tok))
        cid = r.json()["id"]
        # SSE stream — just check status 200 on initial response
        with requests.post(f"{API}/conversations/{cid}/send",
                           json={"content": "ping"}, headers=_h(budi_tok), stream=True, timeout=60) as resp:
            assert resp.status_code == 200, resp.text
            # drain a bit
            got = b""
            for chunk in resp.iter_content(1024):
                got += chunk
                if b"[DONE]" in got or len(got) > 2000:
                    break
        # admin never blocked — even if we set admin's own quota very low
        # (admins are role=admin; quota_exceeded short-circuits)
        rconv = requests.post(f"{API}/conversations",
                              json={"persona_ids": [shared_persona["id"]], "type": "private"},
                              headers=_h(admin_tok))
        acid = rconv.json()["id"]
        resp2 = requests.post(f"{API}/conversations/{acid}/send",
                              json={"content": "cek admin"}, headers=_h(admin_tok), stream=True, timeout=60)
        assert resp2.status_code == 200
        resp2.close()


# ---------------- Invite link ----------------

class TestInviteLink:
    @pytest.fixture(scope="class")
    def meeting(self, admin_tok, shared_persona):
        # need 2 personas for meeting
        pr = [p for p in requests.get(f"{API}/personas", headers=_h(admin_tok)).json() if p.get("name")]
        pids = [p["id"] for p in pr[:2]]
        if len(pids) < 2:
            pids = pids * 2  # fallback; backend still may make private
        r = requests.post(f"{API}/conversations",
                          json={"persona_ids": pids, "type": "meeting",
                                "title": "TEST_invite_meeting"},
                          headers=_h(admin_tok))
        assert r.status_code == 200, r.text
        return r.json()

    def test_create_invite_link_idempotent(self, admin_tok, meeting):
        cid = meeting["id"]
        r = requests.post(f"{API}/conversations/{cid}/invite-link", headers=_h(admin_tok))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["token"] and data["path"] == f"/join/{data['token']}"
        # repeat -> same token
        r2 = requests.post(f"{API}/conversations/{cid}/invite-link", headers=_h(admin_tok))
        assert r2.json()["token"] == data["token"]

    def test_invite_link_private_400(self, admin_tok, shared_persona):
        r = requests.post(f"{API}/conversations",
                          json={"persona_ids": [shared_persona["id"]], "type": "private"},
                          headers=_h(admin_tok))
        cid = r.json()["id"]
        r2 = requests.post(f"{API}/conversations/{cid}/invite-link", headers=_h(admin_tok))
        assert r2.status_code == 400, r2.text

    def test_invite_info_public_no_auth(self, admin_tok, meeting):
        cid = meeting["id"]
        tok = requests.post(f"{API}/conversations/{cid}/invite-link", headers=_h(admin_tok)).json()["token"]
        r = requests.get(f"{API}/invites/{tok}")  # NO auth
        assert r.status_code == 200, r.text
        d = r.json()
        assert "title" in d and "type" in d and "members" in d and "workspace" in d
        # bad token
        rb = requests.get(f"{API}/invites/not_a_real_token_xyz")
        assert rb.status_code == 404

    def test_invite_register_new_user_and_join(self, admin_tok, meeting):
        cid = meeting["id"]
        tok = requests.post(f"{API}/conversations/{cid}/invite-link", headers=_h(admin_tok)).json()["token"]
        email = f"TEST_invite_{uuid.uuid4().hex[:8]}@aivora.ai"
        payload = {"name": "Invite Guy", "email": email, "password": "secret123"}
        r = requests.post(f"{API}/invites/{tok}/register", json=payload)  # NO auth
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["access_token"]
        assert d["user"]["email"] == email.lower()
        assert d["user"]["role"] == "user"
        assert d["conversation_id"] == cid
        new_tok = d["access_token"]
        # that user's /api/conversations includes the meeting
        lst = requests.get(f"{API}/conversations", headers=_h(new_tok)).json()
        assert any(c["id"] == cid for c in lst)
        # duplicate email => 409
        r2 = requests.post(f"{API}/invites/{tok}/register", json=payload)
        assert r2.status_code == 409
        # cleanup: delete user
        wu = requests.get(f"{API}/admin/workspace-users", headers=_h(admin_tok)).json()
        for u in wu:
            if u["email"] == email:
                requests.delete(f"{API}/admin/users/{u['id']}", headers=_h(admin_tok))

    def test_invite_existing_user_join(self, admin_tok, budi_tok, meeting):
        cid = meeting["id"]
        tok = requests.post(f"{API}/conversations/{cid}/invite-link", headers=_h(admin_tok)).json()["token"]
        r = requests.post(f"{API}/invites/{tok}/join", headers=_h(budi_tok))
        assert r.status_code == 200, r.text
        assert r.json()["conversation_id"] == cid

    def test_bad_token_404(self):
        r = requests.post(f"{API}/invites/bad_token_zzz/join",
                          headers={"Authorization": f"Bearer {_login(BUDI)}"})
        assert r.status_code == 404
