"""Iter33 tests:
(A) POST /api/realtime/calls/{call_id}/transcript - accepts optional `via` (default 'realtime' | 'meeting_chat'), 'bogus' -> 422.
(B) Verify messages are persisted in /api/conversations/{cid}/messages with correct `via`.
(C) Gallery drive_items shape (kind='drive' with link, no path).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ai-companion-test-5.preview.emergentagent.com").rstrip("/")
DEMO_EMAIL = "demo@aivora.ai"
DEMO_PASSWORD = "demo123456"
GOOGLE_USER_ID = "3c4bd726-168e-4e36-9515-a6a7d22fd8ef"


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text}"
    return r.json()["access_token"]


def _mint_google_token():
    import sys
    sys.path.insert(0, "/app/backend")
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from auth import make_token
    return make_token(GOOGLE_USER_ID, "admin")


@pytest.fixture(scope="module")
def demo_headers():
    return {"Authorization": f"Bearer {_login(DEMO_EMAIL, DEMO_PASSWORD)}"}


@pytest.fixture(scope="module")
def google_headers():
    return {"Authorization": f"Bearer {_mint_google_token()}"}


@pytest.fixture(scope="module")
def demo_conv(demo_headers):
    """Create a private (single persona) conversation using an existing persona."""
    # Find a persona of the demo user
    r = requests.get(f"{BASE_URL}/api/personas", headers=demo_headers, timeout=30)
    assert r.status_code == 200, r.text
    personas = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    assert personas, "demo user needs at least one persona"
    pid = personas[0]["id"]
    r = requests.post(f"{BASE_URL}/api/conversations",
                      headers=demo_headers,
                      json={"persona_ids": [pid], "title": "TEST_iter33_voice"},
                      timeout=30)
    assert r.status_code in (200, 201), r.text
    return r.json()


@pytest.fixture(scope="module")
def demo_call(demo_headers, demo_conv):
    r = requests.post(f"{BASE_URL}/api/realtime/calls",
                      headers=demo_headers,
                      json={"conversation_id": demo_conv["id"]},
                      timeout=30)
    if r.status_code == 402:
        pytest.skip("Credits insufficient for creating realtime call")
    assert r.status_code == 200, r.text
    return r.json()


class TestTranscriptEndpoint:
    def test_transcript_default_via_realtime(self, demo_headers, demo_call):
        call_id = demo_call["call_id"]
        r = requests.post(f"{BASE_URL}/api/realtime/calls/{call_id}/transcript",
                          headers=demo_headers,
                          json={"role": "user", "content": "halo iter33 realtime"},
                          timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        assert "message_id" in r.json()

    def test_transcript_via_meeting_chat(self, demo_headers, demo_call):
        call_id = demo_call["call_id"]
        r = requests.post(f"{BASE_URL}/api/realtime/calls/{call_id}/transcript",
                          headers=demo_headers,
                          json={"role": "assistant", "content": "[Tautan Drive: Uji](https://docs.google.com/document/d/XYZ)", "via": "meeting_chat"},
                          timeout=30)
        assert r.status_code == 200, r.text

    def test_transcript_via_bogus_422(self, demo_headers, demo_call):
        call_id = demo_call["call_id"]
        r = requests.post(f"{BASE_URL}/api/realtime/calls/{call_id}/transcript",
                          headers=demo_headers,
                          json={"role": "user", "content": "x", "via": "bogus"},
                          timeout=30)
        assert r.status_code == 422, f"expected 422, got {r.status_code} {r.text}"

    def test_messages_contain_correct_via(self, demo_headers, demo_conv, demo_call):
        cid = demo_conv["id"]
        r = requests.get(f"{BASE_URL}/api/conversations/{cid}/messages?limit=50",
                         headers=demo_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        items = data.get("items") or data.get("messages") or (data if isinstance(data, list) else [])
        vias = {m.get("via") for m in items if m.get("via")}
        assert "realtime" in vias, f"expected realtime in {vias}"
        assert "meeting_chat" in vias, f"expected meeting_chat in {vias}"
        # Also validate the meeting_chat assistant message has the markdown link content
        found = [m for m in items if m.get("via") == "meeting_chat" and m.get("role") == "assistant"]
        assert any("docs.google.com" in (m.get("content") or "") for m in found)

    def test_end_call(self, demo_headers, demo_call):
        call_id = demo_call["call_id"]
        r = requests.post(f"{BASE_URL}/api/realtime/calls/{call_id}/end",
                          headers=demo_headers,
                          json={"elapsed_seconds": 0},
                          timeout=30)
        assert r.status_code == 200, r.text


class TestGalleryDriveItems:
    def test_drive_items_shape(self, google_headers):
        r = requests.get(f"{BASE_URL}/api/gallery?type=all&limit=60", headers=google_headers, timeout=30)
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        drives = [i for i in items if i.get("kind") == "drive"]
        if not drives:
            pytest.skip("No drive items for google user")
        for d in drives:
            assert d.get("link"), f"drive item missing link: {d}"
            assert "docs.google.com" in d["link"] or "drive.google.com" in d["link"]
            # path should be absent or empty
            assert not d.get("path"), f"drive item should not have path: {d}"
