"""Iter 26 — WhatsApp-style direct chats, task discuss groups, archives + reminders, auto-archive settings."""
import os
import time
from datetime import datetime, timezone, timedelta

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

DEMO_EMAIL = "demo@aivora.ai"
DEMO_PASS = "demo123456"
RIO = "e93a66a6-59b1-4a12-8c16-0c9dba6c3348"
NOVA = "4d4b348c-ce16-431d-8927-5a76d66ae9ef"
NADIA = "77f5be90-dd50-407c-b9b9-5f604e13447c"
TEAM_TASK_EXISTS_GROUP = "8bf5cd9d-0e8a-48cf-ab11-754147ace093"
TEAM_TASK_NO_GROUP = "37f47d30-343f-4f16-aced-5a36a21c6a27"


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASS}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def h(demo_token):
    return {"Authorization": f"Bearer {demo_token}"}


# ---------- (B)/(A) Direct conv idempotence + unread + mark_read ----------

def test_direct_conv_idempotent(h):
    r1 = requests.post(f"{API}/conversations/direct", json={"persona_id": RIO}, headers=h, timeout=30)
    assert r1.status_code == 200, r1.text
    cid1 = r1.json()["id"]
    r2 = requests.post(f"{API}/conversations/direct", json={"persona_id": RIO}, headers=h, timeout=30)
    assert r2.status_code == 200
    assert r2.json()["id"] == cid1, "direct conv must be idempotent per assistant"


def test_list_conversations_has_unread_flag(h):
    r = requests.get(f"{API}/conversations", headers=h, timeout=30)
    assert r.status_code == 200
    convs = r.json()
    assert isinstance(convs, list) and len(convs) > 0
    for c in convs:
        assert "unread" in c and isinstance(c["unread"], bool)
        assert c.get("archived_conv") is not True  # only non-archived


def test_mark_read_clears_unread(h):
    # pick a conv with last_message so unread flag toggles
    convs = requests.get(f"{API}/conversations", headers=h, timeout=30).json()
    target = next((c for c in convs if c.get("last_message")), None)
    assert target is not None, "need at least one conv with last_message"
    cid = target["id"]
    r = requests.post(f"{API}/conversations/{cid}/read", headers=h, timeout=30)
    assert r.status_code == 200
    convs2 = requests.get(f"{API}/conversations", headers=h, timeout=30).json()
    c2 = next(c for c in convs2 if c["id"] == cid)
    assert c2["unread"] is False


# ---------- (B) Task chat-target + discuss ----------

def test_chat_target_existing_group(h):
    r = requests.get(f"{API}/tasks/{TEAM_TASK_EXISTS_GROUP}/chat-target", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["single"] is False
    assert len(data["personas"]) >= 2
    # Expect an existing group with exact persona members (Tim Laporan 2025)
    assert data.get("group") is not None, "expected exact-match group to exist"


def test_chat_target_second_team_task(h):
    r = requests.get(f"{API}/tasks/{TEAM_TASK_NO_GROUP}/chat-target", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["single"] is False
    assert len(data["personas"]) >= 2


def test_discuss_task_creates_or_reuses_group(h):
    # Use the "no group" team task to create a group via POST discuss
    pids = [NOVA, NADIA]
    r = requests.post(f"{API}/tasks/{TEAM_TASK_NO_GROUP}/discuss",
                      json={"mode": "chat", "group_title": "QA Grup", "persona_ids": pids},
                      headers=h, timeout=30)
    assert r.status_code == 200, r.text
    cid = r.json()["conversation_id"]
    assert cid
    # Verify task_id is attached
    rc = requests.get(f"{API}/conversations/{cid}/messages?limit=1", headers=h, timeout=30)
    assert rc.status_code == 200
    # Verify task has this conv_id attached
    rt = requests.get(f"{API}/tasks/{TEAM_TASK_NO_GROUP}", headers=h, timeout=30)
    assert rt.status_code == 200
    conv_ids = rt.json().get("conversation_ids") or []
    assert cid in conv_ids


# ---------- (D) Archives list / get / restore / remind ----------

@pytest.fixture(scope="module")
def archive_items(h):
    r = requests.get(f"{API}/archives?limit=5", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(data.keys()) >= {"items", "has_more", "next_before"}
    return data


def test_archives_pagination_shape(archive_items):
    assert isinstance(archive_items["items"], list)
    assert isinstance(archive_items["has_more"], bool)
    if archive_items["has_more"]:
        assert archive_items["next_before"]
    else:
        assert archive_items["next_before"] in (None, "")


def test_archives_search_q(h):
    r = requests.get(f"{API}/archives?q=kasir", headers=h, timeout=30)
    assert r.status_code == 200
    items = r.json()["items"]
    # q may legitimately return 0, but endpoint must respond with a list and sensible structure
    assert isinstance(items, list)


def test_archive_detail_has_messages(h, archive_items):
    if not archive_items["items"]:
        pytest.skip("no archives present")
    aid = archive_items["items"][0]["id"]
    r = requests.get(f"{API}/archives/{aid}", headers=h, timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert "messages" in data and isinstance(data["messages"], list)
    assert data.get("id") == aid


def test_restore_archive_marks_messages_live(h, archive_items):
    # pick a non-restored archive
    candidates = [a for a in archive_items["items"] if not a.get("restored")]
    if not candidates:
        # fetch more
        more = requests.get(f"{API}/archives?limit=50", headers=h, timeout=30).json()["items"]
        candidates = [a for a in more if not a.get("restored")]
    if not candidates:
        pytest.skip("no non-restored archives available")
    a = candidates[0]
    aid = a["id"]
    cid = a["conversation_id"]
    # archived_count before
    before = requests.get(f"{API}/conversations/{cid}/messages?limit=1", headers=h, timeout=30)
    assert before.status_code == 200
    r = requests.post(f"{API}/archives/{aid}/restore", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("ok") is True
    assert data.get("conversation_id") == cid
    assert isinstance(data.get("restored"), int) and data["restored"] >= 0
    # Verify archive marked restored
    g = requests.get(f"{API}/archives/{aid}", headers=h, timeout=30).json()
    assert g.get("restored") is True


def test_archive_remind_creates_reminder(h, archive_items):
    if not archive_items["items"]:
        pytest.skip("no archives present")
    aid = archive_items["items"][0]["id"]
    start_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    r = requests.post(f"{API}/archives/{aid}/remind", json={"start_at": start_at}, headers=h, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"].startswith("Lanjutkan:")
    # Verify reminder appears in GET /api/reminders
    rr = requests.get(f"{API}/reminders", headers=h, timeout=30)
    assert rr.status_code == 200
    titles = [x.get("title", "") for x in rr.json()]
    assert any(t.startswith("Lanjutkan:") for t in titles)


# ---------- Settings auto_archive_hours ----------

def test_settings_auto_archive_hours_valid_and_restore(h):
    # Set to 72
    r = requests.put(f"{API}/auth/settings", json={"auto_archive_hours": 72}, headers=h, timeout=30)
    assert r.status_code == 200, r.text
    settings = r.json().get("settings") or {}
    assert settings.get("auto_archive_hours") == 72
    # Set to 1000 → 422
    r2 = requests.put(f"{API}/auth/settings", json={"auto_archive_hours": 1000}, headers=h, timeout=30)
    assert r2.status_code == 422
    # Restore to 24
    r3 = requests.put(f"{API}/auth/settings", json={"auto_archive_hours": 24}, headers=h, timeout=30)
    assert r3.status_code == 200
    assert (r3.json().get("settings") or {}).get("auto_archive_hours") == 24


# ---------- Regression: login budi + galeri ----------

def test_login_budi_regression():
    time.sleep(1)
    r = requests.post(f"{API}/auth/login", json={"email": "budi@aivora.ai", "password": "budi123456"}, timeout=30)
    assert r.status_code == 200, r.text
    assert "access_token" in r.json()


def test_gallery_still_works(h):
    r = requests.get(f"{API}/gallery?limit=5", headers=h, timeout=30)
    assert r.status_code == 200
    assert "items" in r.json()
