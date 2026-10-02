"""Iter19: email verification + team invites + multi-workspace backend tests."""
import os
import re
import time
import requests
import pytest

def _load_frontend_env():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.strip().split("=", 1)[1]
    except Exception:
        pass
    return None

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env() or "").rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL not set"
API = f"{BASE}/api"
TS = int(time.time())


def _tok_from_link(link: str, key: str) -> str:
    m = re.search(rf"[?&]{key}=([^&]+)", link) or re.search(rf"/{key.rstrip('=')}/([^/?#]+)", link)
    return m.group(1) if m else link.rsplit("/", 1)[-1].split("?")[0]


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{API}/auth/login", json={"email": "demo@aivora.ai", "password": "demo123456"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ---------- register / verify / login ----------
class TestEmailVerification:
    email = f"qa.verify.{TS}@example.com"
    token = None
    verify_link = None

    def test_01_register_returns_pending(self):
        r = requests.post(f"{API}/auth/register", json={
            "email": self.email, "password": "secret123", "name": "QA Verify",
            "app_url": BASE,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("pending_verification") is True
        assert "access_token" not in d
        assert d.get("email") == self.email
        assert "debug_link" in d and d["debug_link"]
        TestEmailVerification.verify_link = d["debug_link"]
        TestEmailVerification.token = _tok_from_link(d["debug_link"], "token")

    def test_02_login_before_verify_403(self):
        r = requests.post(f"{API}/auth/login", json={"email": self.email, "password": "secret123"})
        assert r.status_code == 403, r.text
        detail = r.json().get("detail")
        if isinstance(detail, dict):
            assert detail.get("code") == "unverified"
        else:
            assert "unverified" in str(detail).lower()

    def test_03_register_again_resends(self):
        r = requests.post(f"{API}/auth/register", json={
            "email": self.email, "password": "secret123", "name": "QA",
            "app_url": BASE,
        })
        assert r.status_code == 200
        assert r.json().get("pending_verification") is True
        if r.json().get("debug_link"):
            TestEmailVerification.token = _tok_from_link(r.json()["debug_link"], "token")

    def test_04_resend_verification(self):
        r = requests.post(f"{API}/auth/resend-verification", json={"email": self.email, "app_url": BASE})
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        # token may be rotated — capture latest
        if d.get("debug_link"):
            TestEmailVerification.token = _tok_from_link(d["debug_link"], "token")

    def test_05_resend_unknown_ok(self):
        r = requests.post(f"{API}/auth/resend-verification", json={"email": f"nobody.{TS}@example.com"})
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_06_verify_token(self):
        r = requests.get(f"{API}/auth/verify-email", params={"token": self.token})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "access_token" in d
        assert d["user"]["verified"] is True

    def test_07_verify_second_time_400(self):
        r = requests.get(f"{API}/auth/verify-email", params={"token": self.token})
        assert r.status_code == 400

    def test_08_login_after_verify(self):
        r = requests.post(f"{API}/auth/login", json={"email": self.email, "password": "secret123"})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_09_register_verified_email_409(self):
        r = requests.post(f"{API}/auth/register", json={
            "email": self.email, "password": "secret123", "name": "x", "app_url": BASE,
        })
        assert r.status_code == 409


# ---------- team invite (new user) ----------
class TestInviteNewUser:
    email = f"qa.invite.new.{TS}@example.com"
    invite_id = None
    token = None

    def test_01_invite_new(self, demo_token):
        r = requests.post(f"{API}/team/invites",
            headers={"Authorization": f"Bearer {demo_token}"},
            json={"email": self.email, "app_url": BASE})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "pending"
        assert d["existing_user"] is False
        assert "/invite/" in d["debug_link"]
        TestInviteNewUser.invite_id = d["id"]
        TestInviteNewUser.token = d["debug_link"].rsplit("/", 1)[-1]

    def test_02_by_token_public(self):
        r = requests.get(f"{API}/team/invites/by-token/{self.token}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["workspace_name"] == "Demo"
        assert d.get("inviter_name")
        assert d["existing_user"] is False

    def test_03_accept_requires_password(self):
        r = requests.post(f"{API}/team/invites/by-token/{self.token}/accept", json={})
        assert r.status_code == 400

    def test_04_accept_ok(self):
        r = requests.post(f"{API}/team/invites/by-token/{self.token}/accept",
                          json={"name": "QA Invite", "password": "newpass123"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "access_token" in d
        assert d["user"]["role"] == "user"
        assert d["user"].get("is_home_workspace") is False

    def test_05_invite_status_joined(self, demo_token):
        r = requests.get(f"{API}/team/invites", headers={"Authorization": f"Bearer {demo_token}"})
        assert r.status_code == 200
        rows = r.json() if isinstance(r.json(), list) else r.json().get("invites", [])
        row = next((x for x in rows if x.get("email") == self.email), None)
        assert row and row["status"] == "joined"

    def test_06_in_workspace_users(self, demo_token):
        r = requests.get(f"{API}/admin/workspace-users", headers={"Authorization": f"Bearer {demo_token}"})
        assert r.status_code == 200
        users = r.json() if isinstance(r.json(), list) else r.json().get("users", [])
        assert any(u.get("email") == self.email for u in users)

    def test_07_invite_same_409(self, demo_token):
        r = requests.post(f"{API}/team/invites",
            headers={"Authorization": f"Bearer {demo_token}"},
            json={"email": self.email, "app_url": BASE})
        assert r.status_code == 409


# ---------- existing-user invite + workspace switch ----------
class TestInviteExistingUser:
    email = f"qa.existing.{TS}@example.com"
    user_token = None
    user_id = None
    invite_id = None

    def test_01_register_and_verify(self):
        r = requests.post(f"{API}/auth/register", json={
            "email": self.email, "password": "secret123", "name": "QA Ex", "app_url": BASE,
        })
        assert r.status_code == 200
        tok = _tok_from_link(r.json()["debug_link"], "token")
        r2 = requests.get(f"{API}/auth/verify-email", params={"token": tok})
        assert r2.status_code == 200
        TestInviteExistingUser.user_token = r2.json()["access_token"]
        TestInviteExistingUser.user_id = r2.json()["user"]["id"]

    def test_02_invite_existing(self, demo_token):
        r = requests.post(f"{API}/team/invites",
            headers={"Authorization": f"Bearer {demo_token}"},
            json={"email": self.email, "app_url": BASE})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["existing_user"] is True
        TestInviteExistingUser.invite_id = d["id"]

    def test_03_my_invites_lists(self):
        r = requests.get(f"{API}/team/my-invites", headers={"Authorization": f"Bearer {self.user_token}"})
        assert r.status_code == 200
        rows = r.json() if isinstance(r.json(), list) else r.json().get("invites", [])
        assert any(x["id"] == self.invite_id for x in rows)

    def test_04_accept(self):
        r = requests.post(f"{API}/team/my-invites/{self.invite_id}/accept",
                          headers={"Authorization": f"Bearer {self.user_token}"},
                          json={})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "access_token" in d
        TestInviteExistingUser.user_token = d["access_token"]

    def test_05_workspaces_two(self):
        r = requests.get(f"{API}/auth/workspaces", headers={"Authorization": f"Bearer {self.user_token}"})
        assert r.status_code == 200
        rows = r.json() if isinstance(r.json(), list) else r.json().get("workspaces", [])
        assert len(rows) >= 2
        homes = [x for x in rows if x.get("is_home")]
        actives = [x for x in rows if x.get("active")]
        assert len(homes) == 1
        assert len(actives) == 1

    def test_06_switch_home(self):
        r = requests.get(f"{API}/auth/workspaces", headers={"Authorization": f"Bearer {self.user_token}"})
        home = next(x for x in r.json() if x.get("is_home"))
        r2 = requests.post(f"{API}/auth/switch-workspace",
                           headers={"Authorization": f"Bearer {self.user_token}"},
                           json={"workspace_id": home["id"]})
        assert r2.status_code == 200
        d = r2.json()
        assert d["user"]["role"] == "admin"
        assert d["user"].get("is_home_workspace") is True

    def test_07_switch_bad_403(self):
        r = requests.post(f"{API}/auth/switch-workspace",
                          headers={"Authorization": f"Bearer {self.user_token}"},
                          json={"workspace_id": "nope-does-not-exist"})
        assert r.status_code == 403


# ---------- reject + resend + cancel + remove ----------
class TestInviteRejectResendCancelRemove:
    email = f"qa.reject.{TS}@example.com"

    def test_full_flow(self, demo_token):
        H = {"Authorization": f"Bearer {demo_token}"}
        # new invite
        r = requests.post(f"{API}/team/invites", headers=H, json={"email": self.email, "app_url": BASE})
        assert r.status_code == 200
        inv_id = r.json()["id"]
        tok = r.json()["debug_link"].rsplit("/", 1)[-1]
        # reject by token
        r = requests.post(f"{API}/team/invites/by-token/{tok}/reject")
        assert r.status_code == 200
        rows = requests.get(f"{API}/team/invites", headers=H).json()
        rows = rows if isinstance(rows, list) else rows.get("invites", [])
        row = next(x for x in rows if x["id"] == inv_id)
        assert row["status"] == "rejected"
        # resend brings back pending
        r = requests.post(f"{API}/team/invites/{inv_id}/resend", headers=H)
        assert r.status_code == 200
        assert r.json().get("debug_link")
        rows = requests.get(f"{API}/team/invites", headers=H).json()
        rows = rows if isinstance(rows, list) else rows.get("invites", [])
        row = next(x for x in rows if x["id"] == inv_id)
        assert row["status"] == "pending"
        # cancel/delete
        r = requests.delete(f"{API}/team/invites/{inv_id}", headers=H)
        assert r.status_code in (200, 204)
        rows = requests.get(f"{API}/team/invites", headers=H).json()
        rows = rows if isinstance(rows, list) else rows.get("invites", [])
        assert not any(x["id"] == inv_id for x in rows)

    def test_remove_member(self, demo_token):
        H = {"Authorization": f"Bearer {demo_token}"}
        email = f"qa.member.{TS}@example.com"
        r = requests.post(f"{API}/team/invites", headers=H, json={"email": email, "app_url": BASE})
        tok = r.json()["debug_link"].rsplit("/", 1)[-1]
        r = requests.post(f"{API}/team/invites/by-token/{tok}/accept",
                          json={"name": "member", "password": "memberpass1"})
        assert r.status_code == 200
        member_token = r.json()["access_token"]
        member_id = r.json()["user"]["id"]
        # verify in workspace-users
        users = requests.get(f"{API}/admin/workspace-users", headers=H).json()
        users = users if isinstance(users, list) else users.get("users", [])
        assert any(u["id"] == member_id for u in users)
        # remove via /team/members
        r = requests.delete(f"{API}/team/members/{member_id}", headers=H)
        assert r.status_code in (200, 204)
        users = requests.get(f"{API}/admin/workspace-users", headers=H).json()
        users = users if isinstance(users, list) else users.get("users", [])
        assert not any(u["id"] == member_id for u in users)
        # member's workspaces now shows only home
        ws = requests.get(f"{API}/auth/workspaces", headers={"Authorization": f"Bearer {member_token}"}).json()
        ws = ws if isinstance(ws, list) else ws.get("workspaces", [])
        assert len(ws) == 1 and ws[0].get("is_home") is True


# ---------- legacy regression ----------
class TestLegacyBudi:
    def test_login_and_workspaces(self):
        r = requests.post(f"{API}/auth/login", json={"email": "budi@aivora.ai", "password": "budi123456"})
        assert r.status_code == 200, r.text
        tok = r.json()["access_token"]
        ws = requests.get(f"{API}/auth/workspaces", headers={"Authorization": f"Bearer {tok}"}).json()
        ws = ws if isinstance(ws, list) else ws.get("workspaces", [])
        assert any(x.get("name") == "Demo" for x in ws)

    def test_budi_listed_in_demo(self, demo_token):
        users = requests.get(f"{API}/admin/workspace-users",
                             headers={"Authorization": f"Bearer {demo_token}"}).json()
        users = users if isinstance(users, list) else users.get("users", [])
        assert any(u.get("email") == "budi@aivora.ai" for u in users)
