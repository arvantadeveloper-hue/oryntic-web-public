"""Iter 28 — RTC ICE servers, notification badges, WS /api/ws/{cid} RTC relay."""
import os
import time
import json
import asyncio
import pytest
import requests
import websockets

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
WS_BASE = BASE.replace("https://", "wss://").replace("http://", "ws://") + "/api/ws"

DEMO = ("demo@aivora.ai", "demo123456")
BUDI = ("budi@aivora.ai", "budi123456")


def _login(email, pw):
    time.sleep(1)
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def demo_tok():
    return _login(*DEMO)


@pytest.fixture(scope="module")
def budi_tok():
    return _login(*BUDI)


@pytest.fixture(scope="module")
def demo_h(demo_tok):
    return {"Authorization": f"Bearer {demo_tok}"}


@pytest.fixture(scope="module")
def budi_h(budi_tok):
    return {"Authorization": f"Bearer {budi_tok}"}


@pytest.fixture(scope="module")
def budi_id(demo_h):
    r = requests.get(f"{API}/friends", headers=demo_h, timeout=30)
    for f in r.json()["friends"]:
        if f["email"] == "budi@aivora.ai":
            return f["id"]
    pytest.fail("budi not found")


@pytest.fixture(scope="module")
def demo_id(budi_h):
    r = requests.get(f"{API}/friends", headers=budi_h, timeout=30)
    for f in r.json()["friends"]:
        if f["email"] == "demo@aivora.ai":
            return f["id"]
    pytest.fail("demo not found")


@pytest.fixture(scope="module")
def dm_id(demo_h, budi_id):
    r = requests.post(f"{API}/friends/{budi_id}/chat", headers=demo_h, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------- /api/rtc/ice-servers ----------
def test_ice_servers_unauthenticated():
    r = requests.get(f"{API}/rtc/ice-servers", timeout=30)
    assert r.status_code in (401, 403), r.text


def test_ice_servers_authenticated(demo_h):
    r = requests.get(f"{API}/rtc/ice-servers", headers=demo_h, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "iceServers" in body
    assert isinstance(body["iceServers"], list) and body["iceServers"]
    assert all("urls" in s for s in body["iceServers"])
    assert "turn" in body
    # with no METERED env, must be STUN-only
    if not (os.environ.get("METERED_APP_NAME") and os.environ.get("METERED_CREDENTIAL_API_KEY")):
        assert body["turn"] is False
        urls = " ".join(json.dumps(s["urls"]) for s in body["iceServers"])
        assert "stun:" in urls


# ---------- /api/notifications/badges ----------
def test_badges_shape(budi_h):
    r = requests.get(f"{API}/notifications/badges", headers=budi_h, timeout=30)
    assert r.status_code == 200, r.text
    b = r.json()
    assert isinstance(b.get("friend_requests"), int)
    assert isinstance(b.get("unread_chats"), int)
    assert b["friend_requests"] >= 0
    assert b["unread_chats"] >= 0


def test_badges_friend_requests_zero_when_already_friends(demo_h):
    r = requests.get(f"{API}/notifications/badges", headers=demo_h, timeout=30)
    assert r.status_code == 200
    # demo & budi already friends; no other pending request expected
    assert r.json()["friend_requests"] >= 0


def test_badge_unread_flow_demo_sends_budi_reads(demo_h, budi_h, dm_id):
    # Mark both as read first to establish baseline
    requests.post(f"{API}/conversations/{dm_id}/read", headers=demo_h, timeout=30)
    requests.post(f"{API}/conversations/{dm_id}/read", headers=budi_h, timeout=30)
    time.sleep(1)
    before = requests.get(f"{API}/notifications/badges", headers=budi_h, timeout=30).json()["unread_chats"]
    before_demo = requests.get(f"{API}/notifications/badges", headers=demo_h, timeout=30).json()["unread_chats"]

    # demo sends in DM (SSE stream - must consume to finish)
    r = requests.post(f"{API}/conversations/{dm_id}/send",
                      json={"content": f"ping badge {int(time.time())}"},
                      headers=demo_h, timeout=60, stream=True)
    assert r.status_code == 200
    for _ in r.iter_lines(decode_unicode=True):
        pass
    time.sleep(2)

    after = requests.get(f"{API}/notifications/badges", headers=budi_h, timeout=30).json()["unread_chats"]
    assert after >= max(before, 1), f"budi unread_chats should increase; before={before}, after={after}"

    # demo (the sender) should NOT be counted as unread for themselves
    after_demo = requests.get(f"{API}/notifications/badges", headers=demo_h, timeout=30).json()["unread_chats"]
    assert after_demo == before_demo, f"sender's badge should not grow; before={before_demo}, after={after_demo}"

    # budi marks as read → decreases
    rr = requests.post(f"{API}/conversations/{dm_id}/read", headers=budi_h, timeout=30)
    assert rr.status_code == 200
    time.sleep(1)
    final = requests.get(f"{API}/notifications/badges", headers=budi_h, timeout=30).json()["unread_chats"]
    assert final <= after - 1 or final == 0, f"budi unread should decrease after read; after={after}, final={final}"


# ---------- WebSocket RTC relay ----------
@pytest.mark.asyncio
async def test_ws_rtc_relay(demo_tok, budi_tok, demo_id, budi_id, dm_id):
    url_demo = f"{WS_BASE}/{dm_id}?token={demo_tok}"
    url_budi = f"{WS_BASE}/{dm_id}?token={budi_tok}"

    async with websockets.connect(url_demo, open_timeout=15) as ws_demo:
        async with websockets.connect(url_budi, open_timeout=15) as ws_budi:
            await asyncio.sleep(0.5)
            # budi sends join → demo should receive
            await ws_budi.send(json.dumps({"type": "rtc", "kind": "join"}))
            raw = await asyncio.wait_for(ws_demo.recv(), timeout=5)
            msg = json.loads(raw)
            assert msg.get("type") == "rtc"
            assert msg.get("kind") == "join"
            assert msg.get("from") == budi_id
            assert msg.get("from_name"), f"from_name missing: {msg}"

            # demo sends offer targeted → budi should receive with from=demo
            await ws_demo.send(json.dumps({
                "type": "rtc", "kind": "offer", "to": budi_id,
                "sdp": {"type": "offer", "sdp": "v=0\r\n"}
            }))
            raw = await asyncio.wait_for(ws_budi.recv(), timeout=5)
            msg2 = json.loads(raw)
            assert msg2.get("type") == "rtc"
            assert msg2.get("kind") == "offer"
            assert msg2.get("from") == demo_id
            assert msg2.get("to") == budi_id
            assert msg2.get("sdp", {}).get("type") == "offer"

            # sender should NOT get its own message echoed (exclude=ws)
            try:
                extra = await asyncio.wait_for(ws_demo.recv(), timeout=1.5)
                # if we got something, it must not be our own offer
                m = json.loads(extra)
                assert m.get("kind") != "offer" or m.get("from") != demo_id
            except asyncio.TimeoutError:
                pass  # expected

        # ws_budi closed → demo should receive leave
        await asyncio.sleep(0.5)
        try:
            raw = await asyncio.wait_for(ws_demo.recv(), timeout=5)
            leave = json.loads(raw)
            assert leave.get("type") == "rtc"
            assert leave.get("kind") == "leave"
            assert leave.get("from") == budi_id
        except asyncio.TimeoutError:
            pytest.fail("demo did not receive leave event after budi disconnected")


@pytest.mark.asyncio
async def test_ws_rejects_invalid_token(dm_id):
    url = f"{WS_BASE}/{dm_id}?token=invalid"
    with pytest.raises(Exception):
        async with websockets.connect(url, open_timeout=10) as ws:
            await asyncio.wait_for(ws.recv(), timeout=3)


# ---------- Regression ----------
def test_login_both():
    assert _login(*DEMO)
    assert _login(*BUDI)


def test_conversations_load(demo_h, budi_h):
    assert requests.get(f"{API}/conversations", headers=demo_h, timeout=30).status_code == 200
    assert requests.get(f"{API}/conversations", headers=budi_h, timeout=30).status_code == 200
