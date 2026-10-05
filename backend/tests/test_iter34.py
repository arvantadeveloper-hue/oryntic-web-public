"""Iter34 — verify fixes:
(1) Duplicate-push on task completion: _save_ai_msg must skip _fanout when extra.tool is set.
(2) Google login CSRF: /start sets cookie oryntix_gl; /exchange rejects when cookie missing/mismatched; rate limited.
(3) Drive OAuth callback with glogin-purpose state (or garbage) → 307 to /integrations?error=state (not 500).
(4) Per-user WS: /api/ws/user?token=bad → 4401 (or 403 handshake); valid token → stays open and gets reminder_due.
"""
import os
import re
import json
import time
import asyncio
import pytest
import requests
import websockets
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone, timedelta

def _load_frontend_env():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return os.environ.get("REACT_APP_BACKEND_URL", "")


BASE = (_load_frontend_env() or os.environ.get("REACT_APP_BACKEND_URL", "")).rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL not set"
WS_BASE = re.sub(r"^http", "ws", BASE)
FRONT_REDIRECT = BASE + "/auth/google"


# ---------- helpers ----------
@pytest.fixture(scope="module")
def demo_token():
    # Try login first; fall back to minting a JWT directly (shared rate limit with /google/start).
    r = requests.post(f"{BASE}/api/auth/login", json={"email": "demo@aivora.ai", "password": "demo123456"}, timeout=20)
    if r.status_code == 200:
        return r.json()["access_token"]
    # Fallback: mint via backend auth module
    import sys
    sys.path.insert(0, "/app/backend")
    from auth import make_token  # type: ignore
    from motor.motor_asyncio import AsyncIOMotorClient
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"])
    dbh = cli[os.environ["DB_NAME"]]
    u = asyncio.get_event_loop().run_until_complete(dbh.users.find_one({"email": "demo@aivora.ai"}, {"_id": 0, "id": 1, "role": 1}))
    cli.close()
    assert u, "demo user not found"
    return make_token(u["id"], u.get("role", "admin"))


@pytest.fixture(scope="module")
def demo_headers(demo_token):
    return {"Authorization": f"Bearer {demo_token}"}


# ---------- (2) Google login CSRF ----------
class TestGoogleLoginCSRF:
    def test_start_sets_cookie_and_state(self):
        s = requests.Session()
        r = s.post(f"{BASE}/api/auth/google/start", json={"redirect_uri": FRONT_REDIRECT}, timeout=20)
        if r.status_code == 503:
            pytest.skip("Google login not configured")
        assert r.status_code == 200, r.text
        j = r.json()
        assert "authorization_url" in j
        q = parse_qs(urlparse(j["authorization_url"]).query)
        assert "state" in q and len(q["state"][0]) > 10
        # cookie
        assert "oryntix_gl" in s.cookies, f"cookies={dict(s.cookies)}"
        return s, q["state"][0]

    def test_exchange_without_cookie_rejected(self):
        s = requests.Session()
        r0 = s.post(f"{BASE}/api/auth/google/start", json={"redirect_uri": FRONT_REDIRECT}, timeout=20)
        if r0.status_code == 503:
            pytest.skip("Google login not configured")
        state = parse_qs(urlparse(r0.json()["authorization_url"]).query)["state"][0]
        # Second clean session (no cookie)
        clean = requests.Session()
        r = clean.post(f"{BASE}/api/auth/google/exchange",
                       json={"code": "abcd1234", "state": state, "redirect_uri": FRONT_REDIRECT}, timeout=20)
        assert r.status_code == 400, r.text
        detail = (r.json().get("detail") or "").lower()
        assert "sesi login google tidak valid" in detail, detail

    def test_exchange_with_cookie_passes_csrf_fails_at_google(self):
        s = requests.Session()
        r0 = s.post(f"{BASE}/api/auth/google/start", json={"redirect_uri": FRONT_REDIRECT}, timeout=20)
        if r0.status_code == 503:
            pytest.skip("Google login not configured")
        state = parse_qs(urlparse(r0.json()["authorization_url"]).query)["state"][0]
        r = s.post(f"{BASE}/api/auth/google/exchange",
                   json={"code": "abcd1234-fake", "state": state, "redirect_uri": FRONT_REDIRECT}, timeout=20)
        assert r.status_code == 400, r.text
        detail = (r.json().get("detail") or "").lower()
        # Proves state+cookie check passed and we hit Google (fake code rejected).
        assert "kode google tidak valid" in detail, detail

    def test_exchange_tampered_state(self):
        s = requests.Session()
        r0 = s.post(f"{BASE}/api/auth/google/start", json={"redirect_uri": FRONT_REDIRECT}, timeout=20)
        if r0.status_code == 503:
            pytest.skip("Google login not configured")
        state = parse_qs(urlparse(r0.json()["authorization_url"]).query)["state"][0]
        tampered = state[:-4] + "AAAA"
        r = s.post(f"{BASE}/api/auth/google/exchange",
                   json={"code": "abcd1234", "state": tampered, "redirect_uri": FRONT_REDIRECT}, timeout=20)
        assert r.status_code == 400
        assert "sesi login google tidak valid" in (r.json().get("detail") or "").lower()

    def test_rate_limit_start(self):
        got_429 = False
        for i in range(25):
            r = requests.post(f"{BASE}/api/auth/google/start", json={"redirect_uri": FRONT_REDIRECT}, timeout=20)
            if r.status_code == 503:
                pytest.skip("Google login not configured")
            if r.status_code == 429:
                got_429 = True
                break
        assert got_429, "no 429 after 25 /start attempts"


# ---------- (3) Drive OAuth callback with wrong state ----------
class TestDriveCallbackState:
    def _start_glogin_state(self):
        r = requests.post(f"{BASE}/api/auth/google/start", json={"redirect_uri": FRONT_REDIRECT}, timeout=20)
        if r.status_code == 503:
            pytest.skip("Google login not configured")
        if r.status_code == 429:
            pytest.skip("rate-limited from previous test; cannot mint glogin state")
        return parse_qs(urlparse(r.json()["authorization_url"]).query)["state"][0]

    def test_callback_glogin_state_redirects_error_state(self):
        glogin_state = self._start_glogin_state()
        r = requests.get(f"{BASE}/api/integrations/google/callback",
                         params={"code": "x", "state": glogin_state},
                         allow_redirects=False, timeout=20)
        assert r.status_code == 307, (r.status_code, r.text[:200])
        assert "/integrations?error=state" in r.headers.get("location", "")

    def test_callback_garbage_state_redirects_error_state(self):
        r = requests.get(f"{BASE}/api/integrations/google/callback",
                         params={"code": "x", "state": "garbage"},
                         allow_redirects=False, timeout=20)
        assert r.status_code == 307
        assert "/integrations?error=state" in r.headers.get("location", "")


# ---------- (1) chat._save_ai_msg source check + behavioural message_new ----------
class TestFanoutGuard:
    def test_source_guard_present(self):
        with open("/app/backend/chat.py") as f:
            src = f.read()
        # Guard: tool-set messages must NOT fanout
        assert re.search(r'_save_ai_msg[\s\S]{0,2000}if via != "realtime" and not \(extra or \{\}\)\.get\("tool"\)', src), \
            "fanout guard not found in _save_ai_msg"

    def test_assignments_task_done_passes_tool_marker(self):
        with open("/app/backend/assignments.py") as f:
            src = f.read()
        assert '"tool": "task_done"' in src, "task_done marker missing in assignments.py"

    @pytest.mark.asyncio
    async def test_message_new_pushed_for_regular_assistant_reply(self, demo_token, demo_headers):
        # Pick an existing assistant conversation
        convs = requests.get(f"{BASE}/api/conversations", headers=demo_headers, timeout=20).json()
        priv = next((c for c in convs if c.get("type") == "private" and c.get("persona_id")), None)
        if not priv:
            # create one
            personas = requests.get(f"{BASE}/api/personas", headers=demo_headers, timeout=20).json()
            if not personas:
                pytest.skip("no personas for demo")
            cr = requests.post(f"{BASE}/api/conversations", headers=demo_headers,
                               json={"persona_ids": [personas[0]["id"]], "type": "private"}, timeout=20)
            priv = cr.json()
        cid = priv["id"]

        url = f"{WS_BASE}/api/ws/user?token={demo_token}"
        async with websockets.connect(url, open_timeout=15) as ws:
            await asyncio.sleep(0.3)
            # Fire SSE send in a thread, consuming it fully
            def _send():
                with requests.post(f"{BASE}/api/conversations/{cid}/send", headers=demo_headers,
                                   json={"content": "Halo singkat tes 34", "voice_mode": False},
                                   timeout=120, stream=True) as resp:
                    for _ in resp.iter_lines(decode_unicode=True):
                        pass
            loop = asyncio.get_event_loop()
            fut = loop.run_in_executor(None, _send)

            got_message_new = False
            raw_events = []
            try:
                deadline = time.time() + 90
                while time.time() < deadline:
                    msg = await asyncio.wait_for(ws.recv(), timeout=max(1, deadline - time.time()))
                    try:
                        data = json.loads(msg)
                    except Exception:
                        continue
                    raw_events.append(data)
                    if data.get("type") == "message_new" and data.get("conversation_id") == cid:
                        if data.get("sender_name") and data.get("sender_name") != "User" and "demo" not in (data.get("sender_name") or "").lower():
                            got_message_new = True
                            break
            except asyncio.TimeoutError:
                pass
            print(f"WS events observed: {raw_events[:10]}")
            assert got_message_new, f"no assistant message_new event received within 90s; events={raw_events[:20]}"


# ---------- (4) Per-user WS token checks + reminder_due ----------
class TestUserWS:
    @pytest.mark.asyncio
    async def test_ws_bad_token_rejected(self):
        url = f"{WS_BASE}/api/ws/user?token=bad"
        try:
            async with websockets.connect(url, open_timeout=10) as ws:
                # If it opens, it must close with 4401 very quickly
                try:
                    await asyncio.wait_for(ws.recv(), timeout=5)
                except websockets.ConnectionClosed as e:
                    assert e.code == 4401, f"got close code {e.code}"
                    return
                except asyncio.TimeoutError:
                    pytest.fail("bad token WS stayed open")
        except websockets.InvalidStatusCode as e:
            assert e.status_code in (401, 403), e.status_code
        except websockets.exceptions.InvalidStatus as e:
            assert e.response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_ws_valid_token_stays_open_and_gets_reminder(self, demo_token, demo_headers):
        url = f"{WS_BASE}/api/ws/user?token={demo_token}"
        async with websockets.connect(url, open_timeout=15) as ws:
            # Create a reminder due in ~60s
            start_at = (datetime.now(timezone.utc) + timedelta(seconds=55)).isoformat()
            r = requests.post(f"{BASE}/api/reminders", headers=demo_headers,
                              json={"title": "TEST_iter34 reminder", "description": "",
                                    "start_at": start_at, "remind_minutes": 5},
                              timeout=20)
            assert r.status_code in (200, 201), r.text
            rid = r.json().get("id") or r.json().get("reminder", {}).get("id")

            got = False
            deadline = time.time() + 180  # scheduler tick ≤ 60s + buffer
            try:
                while time.time() < deadline:
                    msg = await asyncio.wait_for(ws.recv(), timeout=max(1, deadline - time.time()))
                    try:
                        data = json.loads(msg)
                    except Exception:
                        continue
                    if data.get("type") == "reminder_due":
                        got = True
                        break
            except asyncio.TimeoutError:
                pass
            # cleanup
            if rid:
                requests.delete(f"{BASE}/api/reminders/{rid}", headers=demo_headers, timeout=20)
            assert got, "no reminder_due event within 180s"
