"""Iter 16 — Backend tests for meeting_chat side-channel, mic settings, realtime negotiate ?sensitivity."""
import os
import json
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ai-companion-test-5.preview.emergentagent.com").rstrip("/")
MEETING_CID = "bcf72bc8-1c0d-4c5f-bb3c-e7d15dbee9f6"  # 'Meeting: Rio, Nova' (demo workspace)


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "demo@aivora.ai", "password": "demo123456"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(demo_token):
    return {"Authorization": f"Bearer {demo_token}"}


# ---------- (1) Settings endpoint ----------
class TestSettings:
    def test_settings_invalid_mic_sensitivity_422(self, auth_headers):
        r = requests.put(f"{BASE_URL}/api/auth/settings",
                         headers=auth_headers, json={"mic_sensitivity": "ultra"}, timeout=15)
        assert r.status_code == 422, r.text

    def test_settings_full_update_high_false(self, auth_headers):
        r = requests.put(f"{BASE_URL}/api/auth/settings",
                         headers=auth_headers,
                         json={"mic_sensitivity": "high", "noise_suppression": False}, timeout=15)
        assert r.status_code == 200, r.text
        s = r.json().get("settings", {})
        assert s.get("mic_sensitivity") == "high"
        assert s.get("noise_suppression") is False

        # verify via GET /me
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=15).json()
        assert me["settings"]["mic_sensitivity"] == "high"
        assert me["settings"]["noise_suppression"] is False

    def test_settings_partial_update_keeps_other(self, auth_headers):
        # Only change noise_suppression -> mic_sensitivity must remain 'high'
        r = requests.put(f"{BASE_URL}/api/auth/settings",
                         headers=auth_headers, json={"noise_suppression": True}, timeout=15)
        assert r.status_code == 200, r.text
        s = r.json()["settings"]
        assert s.get("mic_sensitivity") == "high"
        assert s.get("noise_suppression") is True

    def test_restore_defaults(self, auth_headers):
        r = requests.put(f"{BASE_URL}/api/auth/settings",
                         headers=auth_headers,
                         json={"mic_sensitivity": "medium", "noise_suppression": True}, timeout=15)
        assert r.status_code == 200


# ---------- (2) Meeting chat channel ----------
def _parse_sse(text):
    personas = {}
    final_contents = []
    for line in text.split("\n"):
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except Exception:
            continue
        pid = obj.get("persona_id")
        if pid:
            personas.setdefault(pid, obj.get("persona_name"))
        if obj.get("final") and obj.get("content"):
            final_contents.append((pid, obj.get("persona_name"), obj.get("content")))
    return personas, final_contents


class TestMeetingChat:
    def test_meeting_exists(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/conversations/{MEETING_CID}/messages",
                         headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        conv = r.json()["conversation"]
        assert conv["type"] == "meeting"
        assert len(conv.get("persona_ids", [])) >= 2

    def test_channel_bogus_422(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/conversations/{MEETING_CID}/send",
                          headers=auth_headers,
                          json={"content": "halo", "channel": "bogus"}, timeout=15)
        assert r.status_code == 422, r.text

    def test_meeting_chat_single_responder_no_moderator(self, auth_headers):
        prompt = "Buatkan tabel 3 paket harga singkat."
        r = requests.post(f"{BASE_URL}/api/conversations/{MEETING_CID}/send",
                          headers=auth_headers,
                          json={"content": prompt, "attachments": [], "channel": "meeting_chat"},
                          timeout=120, stream=False)
        assert r.status_code == 200, r.text
        personas, finals = _parse_sse(r.text)
        # exclude moderator from personas: it should NOT appear
        assert "__moderator__" not in personas, f"Moderator should not fire for meeting_chat. personas={personas}"
        assert len(finals) == 1, f"Expected exactly 1 persona final, got {len(finals)}: {finals}"

        # messages persisted with via='meeting_chat'
        msgs = requests.get(f"{BASE_URL}/api/conversations/{MEETING_CID}/messages",
                            headers=auth_headers, timeout=15).json()["messages"]
        # find last user/assistant mc pair
        mc = [m for m in msgs if m.get("via") == "meeting_chat"]
        assert len(mc) >= 2
        # Last two should be user then assistant for our prompt
        last_user = [m for m in mc if m["role"] == "user"][-1]
        last_asst = [m for m in mc if m["role"] == "assistant"][-1]
        assert last_user["content"] == prompt
        assert last_user["via"] == "meeting_chat"
        assert last_asst["via"] == "meeting_chat"

    def test_meeting_chat_mention_routes_to_named(self, auth_headers):
        prompt = "@Nova sebutkan 1 ide singkat"
        r = requests.post(f"{BASE_URL}/api/conversations/{MEETING_CID}/send",
                          headers=auth_headers,
                          json={"content": prompt, "channel": "meeting_chat"},
                          timeout=120)
        assert r.status_code == 200
        personas, finals = _parse_sse(r.text)
        assert len(finals) == 1, finals
        assert finals[0][1].lower() == "nova", f"Expected Nova, got {finals}"

    def test_regular_send_without_channel_has_no_via(self, auth_headers):
        # Use a private conv to avoid moderator; find or create one with Rio
        convs = requests.get(f"{BASE_URL}/api/conversations", headers=auth_headers, timeout=15).json()
        private = next((c for c in convs if c.get("type") == "private"), None)
        if not private:
            pytest.skip("No private conversation available")
        cid = private["id"]
        r = requests.post(f"{BASE_URL}/api/conversations/{cid}/send",
                          headers=auth_headers,
                          json={"content": "Halo singkat"}, timeout=60)
        assert r.status_code == 200
        msgs = requests.get(f"{BASE_URL}/api/conversations/{cid}/messages",
                            headers=auth_headers, timeout=15).json()["messages"]
        # Last two messages must have no 'via' field (or not meeting_chat)
        last_two = msgs[-2:]
        for m in last_two:
            assert m.get("via") != "meeting_chat"


# ---------- (3) Realtime ----------
class TestRealtime:
    def test_realtime_status(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/realtime/status", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert r.json().get("enabled") is True

    def test_negotiate_accepts_sensitivity_query(self, auth_headers):
        # Create a call
        r = requests.post(f"{BASE_URL}/api/realtime/calls",
                          headers=auth_headers, json={"conversation_id": MEETING_CID}, timeout=30)
        assert r.status_code == 200, r.text
        call_id = r.json()["call_id"]
        # Negotiate with dummy SDP + ?sensitivity=low
        headers = {**auth_headers, "Content-Type": "application/sdp"}
        r2 = requests.post(f"{BASE_URL}/api/realtime/calls/{call_id}/negotiate?sensitivity=low",
                           headers=headers, data="v=0\n", timeout=30)
        # Must NOT be 500; expect 502 (bad SDP forwarded to OpenAI) or 200
        assert r2.status_code != 500, f"500 from negotiate: {r2.text}"
        assert r2.status_code in (200, 502), f"Unexpected status {r2.status_code}: {r2.text}"
        # Cleanup — end call
        requests.post(f"{BASE_URL}/api/realtime/calls/{call_id}/end",
                      headers=auth_headers, json={"elapsed_seconds": 0}, timeout=15)
