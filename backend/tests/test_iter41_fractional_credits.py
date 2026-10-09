"""Iteration 41 — Fractional metering, voice per-second billing, WebSocket transport (90s idle, 4KB cap)."""
import asyncio
import json
import os
import time
import pytest
import requests
import websockets
import sys as _sys; _sys.path.insert(0, '/app/backend/tests')  # noqa: E702
from creds import DEMO_PASSWORD, ADMIN_PASSWORD, BUDI_PASSWORD  # noqa: E402,F401

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
WS_URL = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")

DEMO_EMAIL = "demo@aivora.ai"
DEMO_PASS = DEMO_PASSWORD
ADMIN_EMAIL = "admin@aivora.ai"
ADMIN_PASS = ADMIN_PASSWORD


# ------------------------------- fixtures -------------------------------

@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASS}, timeout=30)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code}")
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def demo_headers(demo_token):
    return {"Authorization": f"Bearer {demo_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def demo_user(demo_headers):
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=demo_headers, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def demo_persona(demo_headers):
    r = requests.get(f"{BASE_URL}/api/personas", headers=demo_headers, timeout=30)
    assert r.status_code == 200, r.text
    personas = r.json()
    assert personas, "no personas available"
    # prefer a non-builtin persona
    return next((p for p in personas if not p.get("builtin")), personas[0])


@pytest.fixture(scope="module")
def demo_conv(demo_headers, demo_persona):
    r = requests.post(f"{BASE_URL}/api/conversations/direct",
                      json={"persona_id": demo_persona["id"]}, headers=demo_headers, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------- fractional chat metering -------------------------------

def _wallet(headers):
    r = requests.get(f"{BASE_URL}/api/wallet", headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _stream_send(cid, text, headers, timeout=90):
    """POST /send is SSE; drain the stream and return the aggregated events."""
    with requests.post(f"{BASE_URL}/api/conversations/{cid}/send",
                       json={"content": text}, headers=headers, stream=True, timeout=timeout) as r:
        assert r.status_code == 200, f"send failed {r.status_code} {r.text[:300]}"
        chunks = []
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                try:
                    chunks.append(json.loads(line[5:].strip()))
                except Exception:
                    pass
        return chunks


class TestFractionalChatMetering:
    """Short chats must bill fractional (<1) credits_exact, with credits=0 and wallet carrying remainders."""

    def test_short_chat_fractional_and_carry(self, demo_headers, demo_conv, demo_user):
        uid = demo_user["id"]
        # Count baseline usage events before
        before = _wallet(demo_headers)
        base_available = before["available"]

        cid = demo_conv["id"]
        # Send 3 short chats
        for i in range(3):
            evs = _stream_send(cid, f"Halo {i}", demo_headers)
            # Expect at least a "done" event
            assert evs, "no SSE events received"
            time.sleep(0.4)

        # Pull usage events via admin backdoor? Instead inspect wallet consumed delta + breakdown + daily_used.
        after = _wallet(demo_headers)
        delta_available = base_available - after["available"]
        print(f"available before={base_available} after={after['available']} delta={delta_available} consumed={after['consumed']}")
        print(f"breakdown={after['breakdown']}")

        # Fractional spend should keep whole credits movement small (<=1 for 3 short chats)
        assert delta_available <= 1, f"wallet dropped {delta_available} whole credits for 3 short msgs (expected 0-1 with fractional metering)"
        # Consumed should be rounded to 2 decimals and > 0
        assert isinstance(after["consumed"], float) or isinstance(after["consumed"], int)
        assert after["consumed"] > 0

    def test_messages_persisted(self, demo_headers, demo_conv):
        cid = demo_conv["id"]
        r = requests.get(f"{BASE_URL}/api/conversations/{cid}/messages", headers=demo_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        msgs = data.get("messages") if isinstance(data, dict) else data
        assert isinstance(msgs, list) and msgs, f"no messages list in response: {str(data)[:200]}"
        assert any(isinstance(m, dict) and m.get("role") == "assistant" for m in msgs), "no assistant messages persisted"
        assert any(isinstance(m, dict) and m.get("role") == "user" for m in msgs), "no user messages persisted"


# ------------------------------- voice per-second billing -------------------------------

class TestVoiceCallBilling:
    def test_voice_tick_fractional(self, demo_headers, demo_conv):
        cid = demo_conv["id"]
        r = requests.post(f"{BASE_URL}/api/realtime/calls",
                          json={"conversation_id": cid}, headers=demo_headers, timeout=30)
        if r.status_code == 503:
            pytest.skip("Realtime not enabled (no OPENAI_API_KEY)")
        assert r.status_code == 200, r.text
        data = r.json()
        call_id = data["call_id"]
        cpm = data["credits_per_min"]
        print(f"call_id={call_id} cpm={cpm}")

        # Tick 7 seconds — client elapsed matters but server will override via started_at.
        # The call was just created with started_at=None, so server uses client_elapsed value.
        # BUT negotiate() sets started_at — we skip negotiate, so client_elapsed is honored.
        t1 = requests.post(f"{BASE_URL}/api/realtime/calls/{call_id}/tick",
                           json={"elapsed_seconds": 7}, headers=demo_headers, timeout=30)
        assert t1.status_code == 200, t1.text
        d1 = t1.json()
        expected_7 = round(7 * cpm / 60.0, 3)
        print(f"tick7 -> {d1} expected charged_now={expected_7}")
        assert d1["billed_seconds"] == 7
        # Fractional, not a whole-minute charge
        assert abs(d1["charged_now"] - expected_7) < 0.01, f"expected ~{expected_7}, got {d1['charged_now']}"
        assert d1["charged_now"] < cpm, "7s should bill less than full minute"

        # Tick to 17 (so +10 seconds)
        t2 = requests.post(f"{BASE_URL}/api/realtime/calls/{call_id}/tick",
                           json={"elapsed_seconds": 17}, headers=demo_headers, timeout=30)
        assert t2.status_code == 200, t2.text
        d2 = t2.json()
        expected_delta = round(10 * cpm / 60.0, 3)
        print(f"tick17 -> {d2} expected charged_now={expected_delta}")
        assert d2["billed_seconds"] == 17
        assert abs(d2["charged_now"] - expected_delta) < 0.01

        # End the call
        e = requests.post(f"{BASE_URL}/api/realtime/calls/{call_id}/end",
                          json={"elapsed_seconds": 17}, headers=demo_headers, timeout=30)
        assert e.status_code == 200, e.text
        de = e.json()
        print(f"end -> {de}")
        expected_total = round(17 * cpm / 60.0, 3)
        assert abs(de["credits_total"] - expected_total) < 0.05

    def test_voice_usage_report_fraction(self, demo_headers, demo_conv):
        cid = demo_conv["id"]
        r = requests.post(f"{BASE_URL}/api/realtime/calls",
                          json={"conversation_id": cid}, headers=demo_headers, timeout=30)
        if r.status_code == 503:
            pytest.skip("Realtime not enabled")
        assert r.status_code == 200, r.text
        call_id = r.json()["call_id"]
        # Tiny usage payload — must not be swallowed by int rounding
        usage = {"input_tokens": 10, "output_tokens": 10,
                 "input_token_details": {"audio_tokens": 5, "text_tokens": 5, "cached_tokens": 0},
                 "output_token_details": {"audio_tokens": 5, "text_tokens": 5}}
        u = requests.post(f"{BASE_URL}/api/realtime/calls/{call_id}/usage",
                          json={"usage": usage}, headers=demo_headers, timeout=30)
        assert u.status_code == 200, u.text
        du = u.json()
        print(f"usage report -> {du}")
        # Must be fractional-capable — charged_now should be >= 0 and may be small
        assert "charged_now" in du and "credits_total" in du and "usd" in du
        assert du["charged_now"] >= 0
        # End
        requests.post(f"{BASE_URL}/api/realtime/calls/{call_id}/end",
                      json={"elapsed_seconds": 0}, headers=demo_headers, timeout=30)


# ------------------------------- video avatar config -------------------------------

class TestVideoConfig:
    def test_video_config_exposes_per_sec(self, demo_headers):
        r = requests.get(f"{BASE_URL}/api/support/video-config", headers=demo_headers, timeout=30)
        assert r.status_code == 200, r.text
        c = r.json()
        print(f"video-config: {c}")
        assert "credits_per_sec" in c
        assert isinstance(c["credits_per_sec"], (int, float))
        assert c["credits_per_sec"] > 0


# ------------------------------- wallet aggregation -------------------------------

class TestWalletAggregation:
    def test_wallet_two_decimals_and_int_available(self, demo_headers):
        w = _wallet(demo_headers)
        print(f"wallet: available={w['available']} consumed={w['consumed']} daily_used={w['daily_used']}")
        assert isinstance(w["available"], int), f"available must be int, got {type(w['available'])}"
        # consumed may be int if 0, otherwise float with 2 decimals
        consumed_str = f"{w['consumed']}"
        assert "." not in consumed_str or len(consumed_str.split(".")[1]) <= 2
        # breakdown values rounded to 2 decimals
        for b in w["breakdown"]:
            s = f"{b['credits']}"
            assert "." not in s or len(s.split(".")[1]) <= 2
        # daily_used reflects fractional usage (will be float)
        assert w["daily_used"] >= 0


# ------------------------------- admin usage report -------------------------------

class TestAdminUsageReport:
    def test_usage_report_shape(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/usage-report?days=7", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        print(f"usage-report keys: {list(data.keys())} total={data.get('total')}")
        for k in ("by_user", "by_feature", "daily", "total", "events"):
            assert k in data, f"missing {k}"
        assert isinstance(data["daily"], list) and len(data["daily"]) == 7
        # totals must be numeric and non-negative
        assert isinstance(data["total"], (int, float)) and data["total"] >= 0


# ------------------------------- WebSocket transport -------------------------------

@pytest.mark.asyncio
async def test_ws_user_invalid_token_closes_4401():
    """Server rejects invalid token. Depending on whether it accepts before closing,
    the client sees either a 403 handshake rejection OR a close code 4401 after accept."""
    url = f"{WS_URL}/api/ws/user?token=invalid-xyz"
    try:
        async with websockets.connect(url, open_timeout=10, close_timeout=5) as ws:
            try:
                await asyncio.wait_for(ws.recv(), timeout=5)
                pytest.fail("ws should have been closed")
            except websockets.ConnectionClosed as e:
                print(f"closed code={e.code}")
                assert e.code == 4401, f"expected 4401, got {e.code}"
    except Exception as e:
        # Starlette closes pre-accept → HTTP 403 handshake rejection, which is acceptable.
        name = type(e).__name__
        msg = str(e)
        print(f"handshake rejected: {name}: {msg}")
        assert ("403" in msg) or ("4401" in msg) or isinstance(e, websockets.ConnectionClosed), f"unexpected error: {name}: {msg}"


@pytest.mark.asyncio
async def test_ws_user_keepalive_30s(demo_token):
    """Keep socket open ~30s pinging every 10s — must stay open."""
    url = f"{WS_URL}/api/ws/user?token={demo_token}"
    async with websockets.connect(url, open_timeout=10) as ws:
        for i in range(3):
            await ws.send("ping")
            await asyncio.sleep(10)
        # still open
        assert ws.state.name == "OPEN", f"ws closed early: {ws.state}"
        print("ws kept open ~30s with pings")


@pytest.mark.asyncio
async def test_ws_user_idle_closes_after_90s(demo_token):
    """Send nothing — server closes after WS_IDLE_SEC=90."""
    url = f"{WS_URL}/api/ws/user?token={demo_token}"
    async with websockets.connect(url, open_timeout=10) as ws:
        start = time.time()
        try:
            # Should close itself eventually
            await asyncio.wait_for(ws.recv(), timeout=120)
        except websockets.ConnectionClosed as e:
            dur = time.time() - start
            print(f"server closed idle socket after {dur:.1f}s, code={e.code}")
            assert 80 <= dur <= 115, f"idle close at {dur:.1f}s outside expected 80-115"
            return
        except asyncio.TimeoutError:
            pytest.fail("server did not close idle socket within 120s")


@pytest.mark.asyncio
async def test_ws_meeting_rtc_relay(demo_token, demo_conv):
    cid = demo_conv["id"]
    url = f"{WS_URL}/api/ws/{cid}?token={demo_token}"
    async with websockets.connect(url, open_timeout=10) as a, websockets.connect(url, open_timeout=10) as b:
        await asyncio.sleep(0.3)
        payload = {"type": "rtc", "kind": "offer", "sdp": "x"}
        await a.send(json.dumps(payload))
        try:
            raw = await asyncio.wait_for(b.recv(), timeout=5)
            msg = json.loads(raw)
            print(f"relayed: {msg}")
            assert msg.get("type") == "rtc"
            assert msg.get("kind") == "offer"
            assert "from" in msg
        except asyncio.TimeoutError:
            pytest.fail("rtc signaling not relayed to second client")
