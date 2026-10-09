"""
Iteration 10 regression tests after security/code-review fixes:
(a) Moderator in meetings no longer per-turn: /send does NOT create meeting_notes
(b) /summary endpoint creates exactly one meeting_notes task
(c) /summary allows any participant / workspace admin
(d) Invite links expire in 7 days; invalid/expired → 404 'Undangan tidak valid...';
    invite-registered users have daily_credit_limit=200
(e) GET /api/conversations and /messages do not include invite_token
(f) POST /api/conversations rejects persona_ids not in caller workspace (400)
(g) GET /api/files - path traversal / wrong prefix → 403
(h) voice/tts sanity
"""
import os
import time
import uuid
import json
import pytest
import requests
import sys as _sys; _sys.path.insert(0, '/app/backend/tests')  # noqa: E702
from creds import DEMO_PASSWORD, ADMIN_PASSWORD, BUDI_PASSWORD  # noqa: E402,F401

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ai-companion-test-5.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "demo@aivora.ai"
ADMIN_PASS = os.environ.get("TEST_ADMIN_PASSWORD", DEMO_PASSWORD)
BUDI_EMAIL = "budi@aivora.ai"
BUDI_PASS = os.environ.get("TEST_BUDI_PASSWORD", BUDI_PASSWORD)


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def budi_token():
    r = requests.post(f"{API}/auth/login", json={"email": BUDI_EMAIL, "password": BUDI_PASS}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def budi_headers(budi_token):
    return {"Authorization": f"Bearer {budi_token}"}


@pytest.fixture(scope="module")
def two_personas(admin_headers):
    r = requests.get(f"{API}/personas", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    items = [p for p in r.json() if (p.get("name") or "").strip()]
    assert len(items) >= 2, "Need at least 2 named personas in workspace"
    return items[:2]


@pytest.fixture(scope="module")
def meeting_cid(admin_headers, two_personas):
    pids = [p["id"] for p in two_personas]
    r = requests.post(f"{API}/conversations", headers=admin_headers,
                      json={"persona_ids": pids, "type": "meeting", "title": "TEST_iter10_meet"}, timeout=30)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    yield cid
    requests.delete(f"{API}/conversations/{cid}", headers=admin_headers, timeout=15)


def _consume_sse(resp):
    events = []
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line.startswith("data: "):
            payload = line[6:]
            if payload == "[DONE]":
                break
            try:
                events.append(json.loads(payload))
            except Exception:
                pass
    return events


# ---------- (a) /send no longer creates meeting_notes ----------
def test_send_does_not_create_meeting_notes_task(admin_headers, meeting_cid) -> None:
    # baseline
    before = requests.get(f"{API}/tasks", headers=admin_headers, timeout=15).json()
    before_notes = [t for t in before if t.get("type") == "meeting_notes"]

    r = requests.post(f"{API}/conversations/{meeting_cid}/send", headers=admin_headers,
                      json={"content": "Halo tim, mari bahas strategi marketing Q1."}, stream=True, timeout=120)
    assert r.status_code == 200, r.text
    events = _consume_sse(r)

    finals = [e for e in events if e.get("final") and not e.get("is_moderator")]
    mod_events = [e for e in events if e.get("is_moderator")]
    assert len(finals) >= 2, f"Expected 2 persona finals, got {len(finals)}"
    assert len(mod_events) == 0, "Turn 1: moderator must NOT interject"

    after = requests.get(f"{API}/tasks", headers=admin_headers, timeout=15).json()
    after_notes = [t for t in after if t.get("type") == "meeting_notes"]
    assert len(after_notes) == len(before_notes), "No meeting_notes task should be created by /send"


def test_send_turn2_no_meeting_notes_task(admin_headers, meeting_cid) -> None:
    before = requests.get(f"{API}/tasks", headers=admin_headers, timeout=15).json()
    before_notes = sum(1 for t in before if t.get("type") == "meeting_notes")

    r = requests.post(f"{API}/conversations/{meeting_cid}/send", headers=admin_headers,
                      json={"content": "Bagaimana pendapat kalian soal budget iklan?"}, stream=True, timeout=120)
    assert r.status_code == 200
    _consume_sse(r)  # may or may not include moderator

    after = requests.get(f"{API}/tasks", headers=admin_headers, timeout=15).json()
    after_notes = sum(1 for t in after if t.get("type") == "meeting_notes")
    assert after_notes == before_notes, "/send turn 2 must not create meeting_notes"


# ---------- (b,c) /summary ----------
def test_summary_creates_one_meeting_notes_task(admin_headers, meeting_cid) -> None:
    before = requests.get(f"{API}/tasks", headers=admin_headers, timeout=15).json()
    before_notes = sum(1 for t in before if t.get("type") == "meeting_notes")

    r = requests.post(f"{API}/conversations/{meeting_cid}/summary", headers=admin_headers, timeout=90)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "summary" in body and len(body["summary"]) > 0

    after = requests.get(f"{API}/tasks", headers=admin_headers, timeout=15).json()
    after_notes = sum(1 for t in after if t.get("type") == "meeting_notes")
    assert after_notes == before_notes + 1, "Exactly one meeting_notes task should be created"


def test_summary_private_returns_400(admin_headers, two_personas) -> None:
    pid = two_personas[0]["id"]
    r = requests.post(f"{API}/conversations", headers=admin_headers,
                      json={"persona_ids": [pid], "type": "private", "title": "TEST_iter10_priv"}, timeout=15)
    assert r.status_code == 200
    cid = r.json()["id"]
    try:
        # need a message
        requests.post(f"{API}/conversations/{cid}/send", headers=admin_headers,
                      json={"content": "hi"}, stream=True, timeout=60).close()
        r = requests.post(f"{API}/conversations/{cid}/summary", headers=admin_headers, timeout=30)
        assert r.status_code == 400
    finally:
        requests.delete(f"{API}/conversations/{cid}", headers=admin_headers, timeout=15)


def test_summary_allowed_for_participant(admin_headers, budi_headers, budi_token, two_personas) -> None:
    """Budi is invited as participant; he should be able to call /summary (not 404)."""
    pids = [p["id"] for p in two_personas]
    # get budi id
    me = requests.get(f"{API}/auth/me", headers=budi_headers, timeout=15).json()
    budi_id = me["id"]
    r = requests.post(f"{API}/conversations", headers=admin_headers,
                      json={"persona_ids": pids, "type": "meeting", "title": "TEST_iter10_part"}, timeout=15)
    cid = r.json()["id"]
    try:
        inv = requests.post(f"{API}/conversations/{cid}/participants", headers=admin_headers,
                            json={"user_ids": [budi_id]}, timeout=15)
        assert inv.status_code == 200, inv.text
        # need some content
        requests.post(f"{API}/conversations/{cid}/send", headers=admin_headers,
                      json={"content": "Diskusi singkat untuk uji notulen."}, stream=True, timeout=120).close()
        time.sleep(1)
        r2 = requests.post(f"{API}/conversations/{cid}/summary", headers=budi_headers, timeout=90)
        assert r2.status_code == 200, f"Participant should be allowed: {r2.status_code} {r2.text}"
    finally:
        requests.delete(f"{API}/conversations/{cid}", headers=admin_headers, timeout=15)


# ---------- (d) invite links ----------
def test_invite_link_structure_and_expiry(admin_headers, meeting_cid) -> None:
    r = requests.post(f"{API}/conversations/{meeting_cid}/invite-link", headers=admin_headers, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "token" in body and len(body["token"]) >= 32, f"token too short: {body.get('token')}"
    assert "path" in body and body["path"].startswith("/join/")
    assert "expires_at" in body
    # parse iso
    from datetime import datetime, timezone, timedelta
    exp = datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    delta = exp - now
    assert timedelta(days=6) < delta < timedelta(days=8), f"expiry not ~7 days: {delta}"

    # GET /invites/{token}
    r2 = requests.get(f"{API}/invites/{body['token']}", timeout=15)
    assert r2.status_code == 200

    # bogus
    r3 = requests.get(f"{API}/invites/bogus_token_xyz_404", timeout=15)
    assert r3.status_code == 404
    assert "kedaluwarsa" in r3.json().get("detail", "")


def test_invite_register_sets_daily_limit_200(admin_headers, meeting_cid) -> None:
    r = requests.post(f"{API}/conversations/{meeting_cid}/invite-link", headers=admin_headers, timeout=15)
    assert r.status_code == 200
    token = r.json()["token"]
    rand = uuid.uuid4().hex[:8]
    email = f"test_invite_{rand}@aivora.ai"  # lowercased, backend lowercases on save
    reg = requests.post(f"{API}/invites/{token}/register",
                        json={"name": f"Test {rand}", "email": email, "password": "pw123456"}, timeout=30)
    assert reg.status_code == 200, reg.text
    assert "access_token" in reg.json()

    # admin lists workspace users
    users = requests.get(f"{API}/admin/workspace-users", headers=admin_headers, timeout=15).json()
    hit = next((u for u in users if u.get("email") == email), None)
    assert hit is not None, f"new user {email} not in workspace list"
    assert hit.get("daily_credit_limit") == 200, f"expected 200, got {hit.get('daily_credit_limit')}"
    # cleanup
    try:
        requests.delete(f"{API}/admin/users/{hit['id']}", headers=admin_headers, timeout=15)
    except Exception:
        pass


# ---------- (e) invite_token not leaked ----------
def test_conversations_list_no_invite_token(admin_headers, meeting_cid) -> None:
    # ensure an invite_token exists for the conv
    requests.post(f"{API}/conversations/{meeting_cid}/invite-link", headers=admin_headers, timeout=15)
    convs = requests.get(f"{API}/conversations", headers=admin_headers, timeout=15).json()
    for c in convs:
        assert "invite_token" not in c, f"invite_token leaked in list for conv {c.get('id')}"

    msgs = requests.get(f"{API}/conversations/{meeting_cid}/messages", headers=admin_headers, timeout=15).json()
    assert "invite_token" not in msgs.get("conversation", {}), "invite_token leaked in messages.conversation"


# ---------- (f) persona_ids workspace isolation ----------
def test_create_conv_rejects_foreign_persona(admin_headers) -> None:
    r = requests.post(f"{API}/conversations", headers=admin_headers,
                      json={"persona_ids": ["00000000-0000-0000-0000-000000000000"], "type": "private"}, timeout=15)
    assert r.status_code == 400
    assert "persona" in r.json().get("detail", "").lower()


# ---------- (g) files path checks ----------
def test_files_path_traversal_forbidden(admin_token) -> None:
    me = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {admin_token}"}, timeout=15).json()
    uid = me["id"]
    # path traversal
    r = requests.get(f"{API}/files/aivora/videos/{uid}/../other/x.mp4?auth={admin_token}", timeout=15)
    assert r.status_code == 403, f"expected 403 for traversal, got {r.status_code}"

    r2 = requests.get(f"{API}/files/other/videos/{uid}/x.mp4?auth={admin_token}", timeout=15)
    assert r2.status_code == 403, f"expected 403 for wrong prefix, got {r2.status_code}"


# ---------- (h) voice/tts sanity ----------
def test_voice_tts_sanity(admin_headers) -> None:
    r = requests.post(f"{API}/voice/tts", headers=admin_headers,
                      json={"text": "halo", "voice": "nova"}, timeout=60)
    assert r.status_code == 200, r.text
    ct = r.headers.get("content-type", "")
    assert "audio" in ct, f"expected audio content-type, got {ct}"
    assert len(r.content) > 100
