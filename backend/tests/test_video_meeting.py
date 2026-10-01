"""Backend tests for Video Room meeting endpoints:
- POST /api/conversations/{cid}/summary
- POST /api/conversations/{cid}/send with moderator flag (meeting type)
- New: 'Moderator Aktif' interjection on every even user turn when moderator=false
"""
import os
import json
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
LEGACY_MEETING_CID = "dba6c41f-ca3b-4cf6-b7e9-bfab1f47e40d"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": "demo@aivora.ai", "password": os.environ.get("TEST_ADMIN_PASSWORD", "demo123456")})
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("access_token") or j.get("token")


@pytest.fixture(scope="module")
def h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def persona_ids(h):
    personas = requests.get(f"{API}/personas", headers=h).json()
    assert len(personas) >= 2
    return [personas[0]["id"], personas[1]["id"]]


def _collect_events(cid, h, body):
    events = []
    with requests.post(f"{API}/conversations/{cid}/send", headers=h, json=body, stream=True, timeout=180) as resp:
        assert resp.status_code == 200, resp.text
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


def _task_count(h):
    return len(requests.get(f"{API}/tasks", headers=h).json())


# --- summary endpoint ---
def test_summary_empty_conversation_returns_400(h, persona_ids):
    r = requests.post(f"{API}/conversations", headers=h,
                      json={"persona_ids": persona_ids, "type": "meeting", "title": "TEST_empty"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    s = requests.post(f"{API}/conversations/{cid}/summary", headers=h)
    assert s.status_code == 400, s.text
    requests.delete(f"{API}/conversations/{cid}", headers=h)


def test_summary_private_conversation_returns_400(h, persona_ids):
    r = requests.post(f"{API}/conversations", headers=h,
                      json={"persona_ids": [persona_ids[0]], "type": "private", "title": "TEST_priv"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    s = requests.post(f"{API}/conversations/{cid}/summary", headers=h)
    assert s.status_code == 400, s.text
    requests.delete(f"{API}/conversations/{cid}", headers=h)


def test_summary_creates_meeting_notes_task(h):
    msg = f"TEST ringkas: apa agenda rapat singkat kita? {uuid.uuid4().hex[:6]}"
    with requests.post(f"{API}/conversations/{LEGACY_MEETING_CID}/send", headers=h,
                       json={"content": msg, "moderator": False}, stream=True, timeout=180) as resp:
        assert resp.status_code == 200
        for _ in resp.iter_lines():
            pass

    before = requests.get(f"{API}/tasks", headers=h).json()
    before_ids = {t["id"] for t in before if t.get("type") == "meeting_notes"}

    r = requests.post(f"{API}/conversations/{LEGACY_MEETING_CID}/summary", headers=h, timeout=180)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data.get("summary"), str) and len(data["summary"]) > 10

    after = requests.get(f"{API}/tasks", headers=h).json()
    new_notes = [t for t in after if t.get("type") == "meeting_notes" and t["id"] not in before_ids]
    assert len(new_notes) == 1
    t = new_notes[0]
    assert t["goal"].startswith("Notulen")
    assert t["status"] == "completed"


# --- Moderator Aktif: interjection on even turns, no task ---
def test_moderator_interject_even_turns_no_task(h, persona_ids):
    r = requests.post(f"{API}/conversations", headers=h,
                      json={"persona_ids": persona_ids, "type": "meeting", "title": "TEST_interject"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]

    tasks_before = _task_count(h)

    # Turn 1 (odd) -> NO moderator event
    evs1 = _collect_events(cid, h, {"content": "TEST t1: mulai rapat singkat.", "moderator": False})
    assert any(e.get("done") for e in evs1)
    mod_evs_1 = [e for e in evs1 if e.get("is_moderator")]
    assert mod_evs_1 == [], f"Turn 1 should emit NO moderator events, got {mod_evs_1}"

    tasks_mid = _task_count(h)
    assert tasks_mid == tasks_before, f"No task should be created on turn 1 ({tasks_before} -> {tasks_mid})"

    # Turn 2 (even) -> Moderator interject event, SHORT content, NO task
    evs2 = _collect_events(cid, h, {"content": "TEST t2: lanjut diskusi.", "moderator": False})
    mod_finals = [e for e in evs2 if e.get("is_moderator") and e.get("final")]
    assert len(mod_finals) == 1, f"Expected 1 moderator final event on turn 2, got {len(mod_finals)}"
    mf = mod_finals[0]
    assert mf.get("moderator_kind") == "interject", f"moderator_kind must be 'interject', got {mf.get('moderator_kind')}"
    content = mf.get("content", "")
    assert content, "interject content must not be empty"
    # SHORT: 1-2 sentences, hard upper bound ~400 chars
    assert len(content) <= 400, f"Interject should be short, got {len(content)} chars: {content!r}"

    tasks_after = _task_count(h)
    assert tasks_after == tasks_before, (
        f"Interjection must NOT create a task ({tasks_before} -> {tasks_after})"
    )

    # Also verify moderator start event exists
    assert any(e.get("is_moderator") and e.get("start") for e in evs2)

    requests.delete(f"{API}/conversations/{cid}", headers=h)


# --- Legacy: moderator:true still emits full summary + creates meeting_notes task ---
def test_moderator_true_emits_summary_and_creates_task(h, persona_ids):
    r = requests.post(f"{API}/conversations", headers=h,
                      json={"persona_ids": persona_ids, "type": "meeting", "title": "TEST_modtrue"})
    assert r.status_code == 200
    cid = r.json()["id"]

    tasks_before = _task_count(h)
    evs = _collect_events(cid, h, {"content": "TEST moderator true path.", "moderator": True})
    mod_finals = [e for e in evs if e.get("is_moderator") and e.get("final")]
    assert len(mod_finals) >= 1, "Expected moderator final block on moderator=true"
    # Legacy branch does NOT set moderator_kind='interject'
    assert mod_finals[0].get("moderator_kind") != "interject"

    tasks_after = _task_count(h)
    assert tasks_after == tasks_before + 1, (
        f"moderator=true legacy should create one meeting_notes task ({tasks_before} -> {tasks_after})"
    )
    tasks = requests.get(f"{API}/tasks", headers=h).json()
    newest = sorted([t for t in tasks if t.get("type") == "meeting_notes"],
                    key=lambda t: t.get("created_at", ""))[-1]
    assert newest["type"] == "meeting_notes"

    requests.delete(f"{API}/conversations/{cid}", headers=h)
