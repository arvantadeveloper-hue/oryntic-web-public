"""Aivora backend regression tests.
Covers: auth, personas (profile + 1 portrait), chat SSE, multi-agent tasks,
reminders, wallet, admin RBAC.
"""
import os
import time
import json
import uuid
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get(
    "REACT_APP_BACKEND_URL"
) else None
# fall back to frontend .env if not exported
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@aivora.ai"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Aivora!Admin2026")

# unique test user per run
RUN_ID = uuid.uuid4().hex[:8]
TEST_EMAIL = f"TEST_user_{RUN_ID}@aivora.ai"
TEST_PASSWORD = os.environ.get("TEST_TEST_PASSWORD", "Testpass123!")


# ---------- shared state ----------
state = {}


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- Health ----------
class TestHealth:
    def test_root(self, s):
        r = s.get(f"{API}/")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"


# ---------- Auth ----------
class TestAuth:
    def test_register(self, s):
        r = s.post(f"{API}/auth/register", json={
            "email": TEST_EMAIL, "password": TEST_PASSWORD, "name": "TestUser"
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert "access_token" in data
        assert data["user"]["email"] == TEST_EMAIL.lower()
        assert data["user"]["credits"] == 500
        assert not (data["user"]["onboarded"])
        state["token"] = data["access_token"]
        state["user_id"] = data["user"]["id"]

    def test_duplicate_register(self, s):
        r = s.post(f"{API}/auth/register", json={
            "email": TEST_EMAIL, "password": TEST_PASSWORD
        })
        assert r.status_code == 409

    def test_login(self, s):
        r = s.post(f"{API}/auth/login", json={
            "email": TEST_EMAIL, "password": TEST_PASSWORD
        })
        assert r.status_code == 200
        state["token"] = r.json()["access_token"]

    def test_login_bad(self, s):
        r = s.post(f"{API}/auth/login", json={
            "email": TEST_EMAIL, "password": "wrong!!!"
        })
        assert r.status_code == 401

    def test_me(self, s):
        r = s.get(f"{API}/auth/me", headers=auth_headers(state["token"]))
        assert r.status_code == 200
        assert r.json()["email"] == TEST_EMAIL.lower()

    def test_me_unauthorized(self, s):
        r = s.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_onboard(self, s):
        r = s.post(f"{API}/auth/onboard", json={
            "name": "TestUser", "app_language": "en",
            "conversation_language": "en", "timezone": "Asia/Jakarta",
            "interests": "ai, testing"
        }, headers=auth_headers(state["token"]))
        assert r.status_code == 200
        assert r.json()["onboarded"]
        assert r.json()["settings"]["app_language"] == "en"

    def test_admin_login(self, s):
        r = s.post(f"{API}/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        assert r.status_code == 200, r.text
        assert r.json()["user"]["role"] == "admin"
        state["admin_token"] = r.json()["access_token"]


# ---------- Personas ----------
class TestPersonas:
    def test_generate_profile(self, s):
        r = s.post(f"{API}/personas/generate-profile", json={
            "description": "A calm 28-year-old Indonesian female UX researcher who loves cats, "
                           "speaks softly, warm humor, formal yet friendly.",
            "method": "describe"
        }, headers=auth_headers(state["token"]), timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "profile" in data
        prof = data["profile"]
        for key in ("identity", "personality", "appearance", "voice", "language", "system_instructions"):
            assert key in prof, f"missing {key}"
        state["profile"] = prof

    def test_create_persona(self, s):
        r = s.post(f"{API}/personas", json={"profile": state["profile"]},
                   headers=auth_headers(state["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert "id" in data
        state["persona_id"] = data["id"]

    def test_list_personas(self, s):
        r = s.get(f"{API}/personas", headers=auth_headers(state["token"]))
        assert r.status_code == 200
        ids = [p["id"] for p in r.json()]
        assert state["persona_id"] in ids

    def test_get_persona(self, s):
        r = s.get(f"{API}/personas/{state['persona_id']}",
                  headers=auth_headers(state["token"]))
        assert r.status_code == 200
        assert r.json()["id"] == state["persona_id"]

    def test_generate_portrait_once(self, s):
        """One portrait call to avoid spam; verify data URL + credit deduction."""
        before = s.get(f"{API}/auth/me", headers=auth_headers(state["token"])).json()["credits"]
        r = s.post(f"{API}/personas/{state['persona_id']}/portrait",
                   json={"style": "cinematic realistic", "use_reference": False},
                   headers=auth_headers(state["token"]), timeout=180)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["portrait"].startswith("data:image/")
        assert data["credits_used"] == 25
        after = data["credits"]
        assert before - after == 25

    def test_duplicate_persona(self, s):
        r = s.post(f"{API}/personas/{state['persona_id']}/duplicate",
                   headers=auth_headers(state["token"]))
        assert r.status_code == 200
        assert r.json()["name"].endswith("(Copy)")
        state["dup_persona_id"] = r.json()["id"]

    def test_soft_delete(self, s):
        r = s.delete(f"{API}/personas/{state['dup_persona_id']}",
                     headers=auth_headers(state["token"]))
        assert r.status_code == 200
        r2 = s.get(f"{API}/personas", headers=auth_headers(state["token"]))
        ids = [p["id"] for p in r2.json()]
        assert state["dup_persona_id"] not in ids


# ---------- Chat (SSE) ----------
class TestChat:
    def test_create_conversation(self, s):
        r = s.post(f"{API}/conversations",
                   json={"persona_id": state["persona_id"]},
                   headers=auth_headers(state["token"]))
        assert r.status_code == 200
        state["cid"] = r.json()["id"]

    def test_stream_message(self, s):
        url = f"{API}/conversations/{state['cid']}/send"
        with requests.post(
            url, json={"content": "Say hello in one short sentence."},
            headers=auth_headers(state["token"]), stream=True, timeout=120
        ) as r:
            assert r.status_code == 200
            ct = r.headers.get("content-type", "")
            assert "text/event-stream" in ct
            received = []
            done = False
            for raw in r.iter_lines():
                if not raw:
                    continue
                line = raw.decode() if isinstance(raw, bytes) else raw
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        done = True
                        break
                    try:
                        obj = json.loads(payload)
                    except Exception:
                        continue
                    if "delta" in obj:
                        received.append(obj["delta"])
                    if obj.get("done"):
                        done = True
            assert done, "stream didn't finish"
            assert len(received) > 0, "no delta chunks received"

    def test_messages_persisted(self, s):
        r = s.get(f"{API}/conversations/{state['cid']}/messages",
                  headers=auth_headers(state["token"]))
        assert r.status_code == 200
        msgs = r.json()["messages"]
        roles = [m["role"] for m in msgs]
        assert "user" in roles and "assistant" in roles

    def test_memory_crud(self, s):
        h = auth_headers(state["token"])
        r = s.post(f"{API}/memory",
                   json={"persona_id": state["persona_id"], "content": "User likes coffee"},
                   headers=h)
        assert r.status_code == 200
        mid = r.json()["id"]
        r = s.get(f"{API}/memory", headers=h)
        assert r.status_code == 200
        assert any(m["id"] == mid for m in r.json())
        r = s.put(f"{API}/memory/{mid}", json={"content": "User loves espresso"}, headers=h)
        assert r.status_code == 200
        r = s.delete(f"{API}/memory/{mid}", headers=h)
        assert r.status_code == 200

    def test_delete_conversation(self, s):
        r = s.delete(f"{API}/conversations/{state['cid']}",
                     headers=auth_headers(state["token"]))
        assert r.status_code == 200


# ---------- Multi-agent Tasks ----------
class TestTasks:
    def test_create_task_and_poll(self, s):
        h = auth_headers(state["token"])
        r = s.post(f"{API}/tasks",
                   json={"goal": "Write a 3-bullet weekend plan for a solo traveler in Bali."},
                   headers=h)
        assert r.status_code == 200, r.text
        tid = r.json()["id"]
        assert r.json()["status"] == "queued"
        state["tid"] = tid

        # poll up to 90s
        final = None
        for _ in range(45):
            time.sleep(2)
            r = s.get(f"{API}/tasks/{tid}", headers=h)
            assert r.status_code == 200
            t = r.json()
            if t["status"] in ("completed", "failed"):
                final = t
                break
        assert final is not None, "task did not finish within 90s"
        assert final["status"] == "completed", f"status={final['status']} err={final.get('error')}"
        assert len(final.get("steps", [])) >= 1
        assert final.get("final_output"), "no final_output"
        assert final.get("credits_used", 0) > 0

    def test_list_tasks(self, s):
        r = s.get(f"{API}/tasks", headers=auth_headers(state["token"]))
        assert r.status_code == 200
        assert any(t["id"] == state["tid"] for t in r.json())

    def test_filter_search_tasks(self, s):
        h = auth_headers(state["token"])
        r = s.get(f"{API}/tasks?status=completed", headers=h)
        assert r.status_code == 200
        r = s.get(f"{API}/tasks?q=Bali", headers=h)
        assert r.status_code == 200

    def test_delete_task(self, s):
        r = s.delete(f"{API}/tasks/{state['tid']}",
                     headers=auth_headers(state["token"]))
        assert r.status_code == 200


# ---------- Reminders ----------
class TestReminders:
    def test_create_reminder(self, s):
        from datetime import datetime, timezone, timedelta
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        r = s.post(f"{API}/reminders", json={
            "title": "TEST_Reminder", "description": "Call Mom",
            "start_at": future, "remind_minutes": 30,
            "persona_id": state["persona_id"],
        }, headers=auth_headers(state["token"]))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "scheduled"
        assert "remind_at" in data
        state["rid"] = data["id"]

    def test_list_reminders(self, s):
        r = s.get(f"{API}/reminders", headers=auth_headers(state["token"]))
        assert r.status_code == 200
        assert any(x["id"] == state["rid"] for x in r.json())

    def test_incoming_empty(self, s):
        r = s.get(f"{API}/reminders/incoming",
                  headers=auth_headers(state["token"]))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_decline(self, s):
        r = s.post(f"{API}/reminders/{state['rid']}/respond",
                   json={"action": "decline"},
                   headers=auth_headers(state["token"]))
        assert r.status_code == 200
        assert r.json()["status"] == "declined"

    def test_delete(self, s):
        r = s.delete(f"{API}/reminders/{state['rid']}",
                     headers=auth_headers(state["token"]))
        assert r.status_code == 200


# ---------- Wallet ----------
class TestWallet:
    def test_wallet_get(self, s):
        r = s.get(f"{API}/wallet", headers=auth_headers(state["token"]))
        assert r.status_code == 200
        d = r.json()
        for k in ("available", "consumed", "breakdown", "transactions"):
            assert k in d

    def test_packages(self, s):
        r = s.get(f"{API}/wallet/packages",
                  headers=auth_headers(state["token"]))
        assert r.status_code == 200
        pkgs = r.json()
        assert len(pkgs) == 5
        assert {"starter", "basic", "plus", "pro", "ultimate"}.issubset({p["id"] for p in pkgs})

    def test_topup(self, s):
        before = s.get(f"{API}/wallet", headers=auth_headers(state["token"])).json()["available"]
        r = s.post(f"{API}/wallet/topup", json={"package_id": "starter"},
                   headers=auth_headers(state["token"]))
        assert r.status_code == 200
        assert r.json()["added"] == 500
        assert r.json()["simulated"]
        after = s.get(f"{API}/wallet", headers=auth_headers(state["token"])).json()["available"]
        assert after - before == 500

    def test_topup_bad_pkg(self, s):
        r = s.post(f"{API}/wallet/topup", json={"package_id": "nope"},
                   headers=auth_headers(state["token"]))
        assert r.status_code == 404


# ---------- Admin ----------
class TestAdmin:
    def test_overview(self, s):
        r = s.get(f"{API}/admin/overview",
                  headers=auth_headers(state["admin_token"]))
        assert r.status_code == 200
        for k in ("users", "personas", "tasks", "conversations", "reminders"):
            assert k in r.json()

    def test_users(self, s):
        r = s.get(f"{API}/admin/users",
                  headers=auth_headers(state["admin_token"]))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_tasks(self, s):
        r = s.get(f"{API}/admin/tasks",
                  headers=auth_headers(state["admin_token"]))
        assert r.status_code == 200

    def test_pricing(self, s):
        r = s.get(f"{API}/admin/pricing",
                  headers=auth_headers(state["admin_token"]))
        assert r.status_code == 200
        assert "packages" in r.json()
        assert "providers" in r.json()

    def test_non_admin_blocked(self, s):
        r = s.get(f"{API}/admin/overview",
                  headers=auth_headers(state["token"]))
        assert r.status_code == 403


# ---------- Cleanup ----------
def test_zz_cleanup_persona(s) -> None:
    s.delete(f"{API}/personas/{state.get('persona_id','')}",
             headers=auth_headers(state["token"]))
