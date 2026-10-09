"""Iter 22 — Daily digest (Ringkasan Harian) + Meeting→Panggilan wording."""
import os
import time
import requests
import pytest
import sys as _sys; _sys.path.insert(0, '/app/backend/tests')  # noqa: E702
from creds import DEMO_PASSWORD, ADMIN_PASSWORD, BUDI_PASSWORD  # noqa: E402,F401

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    # fallback to frontend/.env
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                BASE = ln.split("=", 1)[1].strip().rstrip("/")
API = BASE + "/api"
EMAIL, PWD = "demo@aivora.ai", DEMO_PASSWORD


@pytest.fixture(scope="module")
def tok():
    r = requests.post(f"{API}/auth/login", json={"email": EMAIL, "password": PWD}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def persona_id(h):
    r = requests.get(f"{API}/personas", headers=h, timeout=10)
    assert r.status_code == 200
    personas = r.json()
    assert personas
    return personas[0]["id"]


# ---------- Settings validation ----------
def test_settings_daily_digest_echo(h, persona_id) -> None:
    r = requests.put(f"{API}/auth/settings",
                     json={"daily_digest": {"enabled": True, "channel": "both", "time": "07:00", "persona_id": persona_id}},
                     headers=h, timeout=15)
    assert r.status_code == 200, r.text
    dd = (r.json().get("settings") or {}).get("daily_digest") or {}
    assert dd.get("enabled") is True
    assert dd.get("channel") == "both"
    assert dd.get("time") == "07:00"
    assert dd.get("persona_id") == persona_id


def test_settings_invalid_time(h, persona_id) -> None:
    r = requests.put(f"{API}/auth/settings",
                     json={"daily_digest": {"enabled": True, "channel": "chat", "time": "7am", "persona_id": persona_id}},
                     headers=h, timeout=15)
    assert r.status_code == 400
    assert "HH:MM" in (r.json().get("detail") or "")


def test_settings_channel_coerced(h, persona_id) -> None:
    r = requests.put(f"{API}/auth/settings",
                     json={"daily_digest": {"enabled": True, "channel": "sms", "time": "07:00", "persona_id": persona_id}},
                     headers=h, timeout=15)
    assert r.status_code == 200
    assert r.json()["settings"]["daily_digest"]["channel"] == "chat"


# ---------- send-now ----------
def _decline_rem(h, rid):
    requests.post(f"{API}/reminders/{rid}/respond", json={"action": "decline"}, headers=h, timeout=10)


def test_send_now_both(h, persona_id) -> None:
    # ensure enabled + both
    requests.put(f"{API}/auth/settings",
                 json={"daily_digest": {"enabled": True, "channel": "both", "time": "07:00", "persona_id": persona_id}},
                 headers=h, timeout=15)
    r = requests.post(f"{API}/digest/send-now", headers=h, timeout=90)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("sent") is True
    assert j.get("channel") == "both"
    assert j.get("credits_used", 0) > 0
    assert j.get("conversation_id")
    assert j.get("reminder_id")

    # verify assistant message content
    time.sleep(1)
    m = requests.get(f"{API}/conversations/{j['conversation_id']}/messages?limit=3", headers=h, timeout=15)
    assert m.status_code == 200
    data = m.json()
    msgs = data.get("messages") if isinstance(data, dict) else data
    assert msgs
    last_ast = [x for x in msgs if x.get("role") == "assistant"]
    assert last_ast, "no assistant message"
    text = last_ast[-1].get("content") or ""
    assert "Demo" in text, f"name not in digest: {text[:200]}"

    # verify incoming reminder
    inc = requests.get(f"{API}/reminders/incoming", headers=h, timeout=10)
    assert inc.status_code == 200
    found = [x for x in inc.json() if x.get("id") == j["reminder_id"]]
    assert found, "digest reminder not in incoming"
    assert found[0].get("title") == "Ringkasan harian"
    assert found[0].get("status") == "ringing"
    assert (found[0].get("description") or "").strip()

    _decline_rem(h, j["reminder_id"])


def test_send_now_chat_only(h, persona_id) -> None:
    requests.put(f"{API}/auth/settings",
                 json={"daily_digest": {"enabled": True, "channel": "chat", "time": "07:00", "persona_id": persona_id}},
                 headers=h, timeout=15)
    r = requests.post(f"{API}/digest/send-now", headers=h, timeout=90)
    assert r.status_code == 200
    j = r.json()
    assert j.get("sent") is True
    assert j.get("channel") == "chat"
    assert j.get("conversation_id")
    assert "reminder_id" not in j or not j.get("reminder_id")


def test_send_now_disabled_force(h, persona_id) -> None:
    requests.put(f"{API}/auth/settings",
                 json={"daily_digest": {"enabled": False, "channel": "chat", "time": "07:00", "persona_id": persona_id}},
                 headers=h, timeout=15)
    r = requests.post(f"{API}/digest/send-now", headers=h, timeout=90)
    assert r.status_code == 200
    j = r.json()
    assert j.get("sent") is True


# ---------- Meeting → Panggilan wording ----------
def test_conversations_no_meeting_prefix(h) -> None:
    r = requests.get(f"{API}/conversations", headers=h, timeout=15)
    assert r.status_code == 200
    titles = [c.get("title", "") for c in r.json()]
    bad = [t for t in titles if t.startswith("Meeting:")]
    assert not bad, f"found legacy titles: {bad}"


def test_create_meeting_title_is_panggilan(h) -> None:
    pr = requests.get(f"{API}/personas", headers=h, timeout=10).json()
    assert len(pr) >= 2
    pids = [pr[0]["id"], pr[1]["id"]]
    r = requests.post(f"{API}/conversations", json={"persona_ids": pids, "type": "meeting"}, headers=h, timeout=15)
    assert r.status_code in (200, 201), r.text
    j = r.json()
    cid = j.get("id")
    title = j.get("title", "")
    assert title.startswith("Panggilan:"), f"unexpected title: {title}"
    # cleanup
    requests.delete(f"{API}/conversations/{cid}", headers=h, timeout=10)


def test_task_discuss_meeting_mode_title(h) -> None:
    # create a task
    tr = requests.post(f"{API}/tasks",
                       json={"title": "TEST_iter22 panggilan wording", "goal": "verifikasi judul panggilan", "deadline": None, "context": ""},
                       headers=h, timeout=15)
    assert tr.status_code in (200, 201), tr.text
    tid = tr.json().get("id") or tr.json().get("task_id")
    assert tid
    d = requests.post(f"{API}/tasks/{tid}/discuss", json={"mode": "meeting"}, headers=h, timeout=20)
    assert d.status_code in (200, 201), d.text
    jd = d.json()
    conv_id = jd.get("conversation_id") or jd.get("id")
    assert conv_id
    # fetch to confirm title
    cv = requests.get(f"{API}/conversations/{conv_id}", headers=h, timeout=10)
    if cv.status_code == 200:
        assert (cv.json().get("title") or "").startswith("Panggilan:")
    else:
        # fallback: list
        allc = requests.get(f"{API}/conversations", headers=h, timeout=10).json()
        c = next((x for x in allc if x.get("id") == conv_id), None)
        assert c and (c.get("title") or "").startswith("Panggilan:")
    # cleanup
    requests.delete(f"{API}/conversations/{conv_id}", headers=h, timeout=10)
    requests.delete(f"{API}/tasks/{tid}", headers=h, timeout=10)
