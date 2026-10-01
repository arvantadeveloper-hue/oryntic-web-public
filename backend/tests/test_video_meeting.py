"""Backend tests for Video Room meeting endpoints:
- POST /api/conversations/{cid}/summary
- POST /api/conversations/{cid}/send with moderator flag (meeting type)
"""
import os
import json
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
MEETING_CID = "dba6c41f-ca3b-4cf6-b7e9-bfab1f47e40d"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": "demo@aivora.ai", "password": "demo123456"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"] if "access_token" in r.json() else r.json().get("token")


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}"}


# --- meeting summary endpoint ---
def test_summary_empty_conversation_returns_400(h):
    # create a fresh meeting with 2 personas but no messages -> 400
    personas = requests.get(f"{API}/personas", headers=h).json()
    assert len(personas) >= 2
    pids = [personas[0]["id"], personas[1]["id"]]
    r = requests.post(f"{API}/conversations", headers=h, json={"persona_ids": pids, "type": "meeting", "title": "TEST_empty_meeting"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    s = requests.post(f"{API}/conversations/{cid}/summary", headers=h)
    assert s.status_code == 400, s.text
    requests.delete(f"{API}/conversations/{cid}", headers=h)


def test_summary_creates_meeting_notes_task(h):
    # ensure the existing meeting has some history by sending a short user message with moderator:false
    msg = f"TEST ringkas: apa agenda rapat singkat kita? {uuid.uuid4().hex[:6]}"
    with requests.post(f"{API}/conversations/{MEETING_CID}/send", headers=h,
                       json={"content": msg, "moderator": False}, stream=True, timeout=120) as resp:
        assert resp.status_code == 200
        # drain
        for _ in resp.iter_lines():
            pass

    before = requests.get(f"{API}/tasks", headers=h).json()
    before_ids = {t["id"] for t in before if t.get("type") == "meeting_notes"}

    r = requests.post(f"{API}/conversations/{MEETING_CID}/summary", headers=h, timeout=120)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "summary" in data and isinstance(data["summary"], str) and len(data["summary"]) > 10

    after = requests.get(f"{API}/tasks", headers=h).json()
    new_notes = [t for t in after if t.get("type") == "meeting_notes" and t["id"] not in before_ids]
    assert len(new_notes) >= 1
    t = new_notes[0]
    assert t["goal"].startswith("Notulen rapat:")
    assert t["status"] == "completed"
    assert t.get("final_output")


# --- moderator flag on send stream ---
def _collect_events(cid, h, body):
    events = []
    with requests.post(f"{API}/conversations/{cid}/send", headers=h, json=body, stream=True, timeout=180) as resp:
        assert resp.status_code == 200
        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode() if isinstance(raw, bytes) else raw
            if line.startswith("data: "):
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    events.append(json.loads(payload))
                except Exception:
                    pass
    return events


def test_send_moderator_false_skips_moderator_block(h):
    evs = _collect_events(MEETING_CID, h, {"content": f"TEST singkat tanpa mod {uuid.uuid4().hex[:5]}", "moderator": False})
    assert any(e.get("done") for e in evs)
    assert not any(e.get("is_moderator") for e in evs), "moderator block should NOT appear when moderator=false"


def test_send_moderator_true_emits_moderator_block(h):
    evs = _collect_events(MEETING_CID, h, {"content": f"TEST dengan mod {uuid.uuid4().hex[:5]}", "moderator": True})
    assert any(e.get("is_moderator") and e.get("final") for e in evs), "moderator final block expected when moderator=true"
