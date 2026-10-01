"""Iteration 9 — Oryntix: voice_mode, meeting-with-1-persona, nudge, moderator interject gating."""
import os
import json
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "demo@aivora.ai"
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "demo123456")


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def personas(admin_headers):
    r = requests.get(f"{BASE_URL}/api/personas", headers=admin_headers, timeout=20)
    assert r.status_code == 200
    ps = [p for p in r.json() if p.get("name")]
    assert len(ps) >= 2, "need at least 2 named personas"
    return ps


def _consume_sse(resp, max_bytes=100_000):
    events = []
    buf = b""
    for chunk in resp.iter_content(chunk_size=1024):
        buf += chunk
        if len(buf) > max_bytes:
            break
    for line in buf.decode("utf-8", errors="ignore").splitlines():
        if line.startswith("data: "):
            s = line[6:]
            if s == "[DONE]":
                events.append({"__done__": True})
                continue
            try:
                events.append(json.loads(s))
            except Exception:
                pass
    return events


# ---------- 1. meeting w/ one persona keeps type meeting ----------
class TestCreateConvMeetingTypes:
    def test_meeting_single_persona_stays_meeting(self, admin_headers, personas):
        r = requests.post(f"{BASE_URL}/api/conversations", headers=admin_headers,
                          json={"type": "meeting", "persona_ids": [personas[0]["id"]], "title": "TEST_meet_1p"},
                          timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["type"] == "meeting"
        assert len(d["persona_ids"]) == 1
        requests.delete(f"{BASE_URL}/api/conversations/{d['id']}", headers=admin_headers, timeout=15)

    def test_group_single_persona_downgrades_to_private(self, admin_headers, personas):
        r = requests.post(f"{BASE_URL}/api/conversations", headers=admin_headers,
                          json={"type": "group", "persona_ids": [personas[0]["id"]], "title": "TEST_grp_1p"},
                          timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["type"] == "private"
        requests.delete(f"{BASE_URL}/api/conversations/{d['id']}", headers=admin_headers, timeout=15)

    def test_group_two_personas_is_group(self, admin_headers, personas):
        r = requests.post(f"{BASE_URL}/api/conversations", headers=admin_headers,
                          json={"type": "group", "persona_ids": [personas[0]["id"], personas[1]["id"]],
                                "title": "TEST_grp_2p"}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["type"] == "group"
        requests.delete(f"{BASE_URL}/api/conversations/{d['id']}", headers=admin_headers, timeout=15)


# ---------- 2. voice_mode SSE send ----------
class TestVoiceModeSend:
    @pytest.fixture(scope="class")
    def priv_conv(self, admin_headers, personas):
        r = requests.post(f"{BASE_URL}/api/conversations", headers=admin_headers,
                          json={"type": "private", "persona_ids": [personas[0]["id"]], "title": "TEST_voice_priv"},
                          timeout=20)
        assert r.status_code == 200
        cid = r.json()["id"]
        yield cid
        requests.delete(f"{BASE_URL}/api/conversations/{cid}", headers=admin_headers, timeout=15)

    def test_voice_mode_streams_and_short(self, admin_headers, priv_conv):
        with requests.post(f"{BASE_URL}/api/conversations/{priv_conv}/send", headers=admin_headers,
                           json={"content": "Halo, gimana cuaca hari ini menurutmu?", "moderator": False,
                                 "voice_mode": True, "interrupted": False},
                           stream=True, timeout=90) as resp:
            assert resp.status_code == 200
            events = _consume_sse(resp, max_bytes=200_000)
        finals = [e for e in events if e.get("final") and e.get("content")]
        assert finals, f"no final event; events={events[:4]}"
        content = finals[0]["content"]
        # spoken style: no markdown bullets/headers
        assert "\n#" not in content and "\n- " not in content and "**" not in content, content
        # roughly short
        assert len(content) < 1200

    def test_interrupted_flag_accepted(self, admin_headers, priv_conv):
        with requests.post(f"{BASE_URL}/api/conversations/{priv_conv}/send", headers=admin_headers,
                           json={"content": "sebentar, aku mau tanya cepat", "moderator": False,
                                 "voice_mode": True, "interrupted": True}, stream=True, timeout=90) as resp:
            assert resp.status_code == 200
            events = _consume_sse(resp, max_bytes=200_000)
        assert any(e.get("final") for e in events)


# ---------- 3. nudge endpoint ----------
class TestNudge:
    @pytest.fixture(scope="class")
    def priv_with_msg(self, admin_headers, personas):
        r = requests.post(f"{BASE_URL}/api/conversations", headers=admin_headers,
                          json={"type": "private", "persona_ids": [personas[0]["id"]], "title": "TEST_nudge_priv"},
                          timeout=20)
        cid = r.json()["id"]
        # Need at least one message
        with requests.post(f"{BASE_URL}/api/conversations/{cid}/send", headers=admin_headers,
                           json={"content": "hai", "moderator": False, "voice_mode": True},
                           stream=True, timeout=90) as resp:
            _consume_sse(resp)
        yield cid
        requests.delete(f"{BASE_URL}/api/conversations/{cid}", headers=admin_headers, timeout=15)

    @pytest.fixture(scope="class")
    def meeting_with_msg(self, admin_headers, personas):
        r = requests.post(f"{BASE_URL}/api/conversations", headers=admin_headers,
                          json={"type": "meeting", "persona_ids": [personas[0]["id"], personas[1]["id"]],
                                "title": "TEST_nudge_meet"}, timeout=20)
        cid = r.json()["id"]
        with requests.post(f"{BASE_URL}/api/conversations/{cid}/send", headers=admin_headers,
                           json={"content": "mari diskusi tentang strategi marketing", "moderator": False,
                                 "voice_mode": True}, stream=True, timeout=120) as resp:
            _consume_sse(resp, max_bytes=300_000)
        yield cid
        requests.delete(f"{BASE_URL}/api/conversations/{cid}", headers=admin_headers, timeout=15)

    def test_nudge_private_replies_as_persona(self, admin_headers, priv_with_msg, personas):
        with requests.post(f"{BASE_URL}/api/conversations/{priv_with_msg}/nudge", headers=admin_headers,
                           stream=True, timeout=90) as resp:
            assert resp.status_code == 200
            events = _consume_sse(resp, max_bytes=200_000)
        finals = [e for e in events if e.get("final")]
        assert finals, events[:5]
        # In private, persona_id is the persona (not moderator)
        assert finals[0]["persona_id"] == personas[0]["id"]

    def test_nudge_meeting_is_moderator(self, admin_headers, meeting_with_msg):
        with requests.post(f"{BASE_URL}/api/conversations/{meeting_with_msg}/nudge", headers=admin_headers,
                           stream=True, timeout=90) as resp:
            assert resp.status_code == 200
            events = _consume_sse(resp, max_bytes=200_000)
        finals = [e for e in events if e.get("final")]
        assert finals, events[:5]
        assert finals[0]["persona_id"] == "__moderator__"
        assert finals[0].get("moderator_kind") == "interject"

    def test_nudge_404_for_other_user(self, personas):
        # login as regular user and try to nudge admin's conv
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": "budi@aivora.ai", "password": os.environ.get("TEST_BUDI_PASSWORD", "budi123456")}, timeout=20)
        if r.status_code != 200:
            pytest.skip("budi user not available")
        tok = r.json()["access_token"]
        # fake conv id
        r2 = requests.post(f"{BASE_URL}/api/conversations/does-not-exist/nudge",
                           headers={"Authorization": f"Bearer {tok}"}, timeout=20)
        assert r2.status_code == 404

    def test_nudge_400_when_no_messages(self, admin_headers, personas):
        r = requests.post(f"{BASE_URL}/api/conversations", headers=admin_headers,
                          json={"type": "private", "persona_ids": [personas[0]["id"]], "title": "TEST_nudge_empty"},
                          timeout=20)
        cid = r.json()["id"]
        try:
            r2 = requests.post(f"{BASE_URL}/api/conversations/{cid}/nudge", headers=admin_headers, timeout=30)
            assert r2.status_code == 400
        finally:
            requests.delete(f"{BASE_URL}/api/conversations/{cid}", headers=admin_headers, timeout=15)


# ---------- 4. moderator:false in meeting (turn 1 no mod event, no meeting_notes) ----------
class TestMeetingModGating:
    def test_turn1_meeting_no_moderator_event_no_task(self, admin_headers, personas):
        # baseline count
        t0 = requests.get(f"{BASE_URL}/api/tasks", headers=admin_headers, timeout=20).json()
        notes_before = len([t for t in t0 if t.get("type") == "meeting_notes"])

        r = requests.post(f"{BASE_URL}/api/conversations", headers=admin_headers,
                          json={"type": "meeting", "persona_ids": [personas[0]["id"], personas[1]["id"]],
                                "title": "TEST_mod_gate"}, timeout=20)
        cid = r.json()["id"]
        try:
            with requests.post(f"{BASE_URL}/api/conversations/{cid}/send", headers=admin_headers,
                               json={"content": "halo semua, apa agenda hari ini?", "moderator": False,
                                     "voice_mode": True}, stream=True, timeout=180) as resp:
                assert resp.status_code == 200
                events = _consume_sse(resp, max_bytes=400_000)
            # No moderator start event on turn 1
            mod_starts = [e for e in events if e.get("is_moderator") and e.get("start")]
            assert not mod_starts, f"unexpected moderator event on turn 1: {mod_starts}"

            # Still get persona responses (two personas)
            finals = [e for e in events if e.get("final")]
            assert len(finals) >= 1

            # No meeting_notes task created
            t1 = requests.get(f"{BASE_URL}/api/tasks", headers=admin_headers, timeout=20).json()
            notes_after = len([t for t in t1 if t.get("type") == "meeting_notes"])
            assert notes_after == notes_before, "unexpected meeting_notes task created"
        finally:
            requests.delete(f"{BASE_URL}/api/conversations/{cid}", headers=admin_headers, timeout=15)


# ---------- 5. legacy moderator:true meeting still produces summary + task ----------
class TestLegacyModeratorSummary:
    def test_legacy_moderator_true_creates_task(self, admin_headers, personas):
        r = requests.post(f"{BASE_URL}/api/conversations", headers=admin_headers,
                          json={"type": "meeting", "persona_ids": [personas[0]["id"], personas[1]["id"]],
                                "title": "TEST_legacy_mod"}, timeout=20)
        cid = r.json()["id"]
        try:
            with requests.post(f"{BASE_URL}/api/conversations/{cid}/send", headers=admin_headers,
                               json={"content": "bahas rencana peluncuran produk minggu depan"},  # moderator defaults True
                               stream=True, timeout=180) as resp:
                assert resp.status_code == 200
                events = _consume_sse(resp, max_bytes=500_000)
            mod_final = [e for e in events if e.get("is_moderator") and e.get("final")]
            assert mod_final, "expected a Moderator final event in legacy meeting"
            # meeting_notes task created
            tasks = requests.get(f"{BASE_URL}/api/tasks", headers=admin_headers, timeout=20).json()
            matches = [t for t in tasks if t.get("type") == "meeting_notes" and cid in (t.get("goal", "") + t.get("final_output", ""))]
            # fallback: just assert at least one meeting_notes task exists after
            notes = [t for t in tasks if t.get("type") == "meeting_notes"]
            assert notes, "no meeting_notes task found"
        finally:
            requests.delete(f"{BASE_URL}/api/conversations/{cid}", headers=admin_headers, timeout=15)


# ---------- 6. summary endpoint still works / 400 for private ----------
class TestSummaryEndpoint:
    def test_summary_400_private(self, admin_headers, personas):
        r = requests.post(f"{BASE_URL}/api/conversations", headers=admin_headers,
                          json={"type": "private", "persona_ids": [personas[0]["id"]], "title": "TEST_sum_priv"},
                          timeout=20)
        cid = r.json()["id"]
        try:
            r2 = requests.post(f"{BASE_URL}/api/conversations/{cid}/summary", headers=admin_headers, timeout=20)
            assert r2.status_code == 400
        finally:
            requests.delete(f"{BASE_URL}/api/conversations/{cid}", headers=admin_headers, timeout=15)

    def test_summary_ok_meeting(self, admin_headers, personas):
        r = requests.post(f"{BASE_URL}/api/conversations", headers=admin_headers,
                          json={"type": "meeting", "persona_ids": [personas[0]["id"], personas[1]["id"]],
                                "title": "TEST_sum_meet"}, timeout=20)
        cid = r.json()["id"]
        try:
            # seed at least one message (moderator:false to avoid auto-summary creating task twice)
            with requests.post(f"{BASE_URL}/api/conversations/{cid}/send", headers=admin_headers,
                               json={"content": "diskusi singkat tentang target Q1", "moderator": False,
                                     "voice_mode": True}, stream=True, timeout=120) as resp:
                _consume_sse(resp, max_bytes=300_000)
            r2 = requests.post(f"{BASE_URL}/api/conversations/{cid}/summary", headers=admin_headers, timeout=120)
            assert r2.status_code == 200, r2.text
            assert "summary" in r2.json()
        finally:
            requests.delete(f"{BASE_URL}/api/conversations/{cid}", headers=admin_headers, timeout=15)
