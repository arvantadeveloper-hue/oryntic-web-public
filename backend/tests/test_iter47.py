"""Iter47 — Agenda confirm/cancel chat flow + voice endpoints + regression.

Requires network to the preview URL, Mongo access for verification, and LLM
responses (planner latency 2–6 s)."""
import json
import os
import time
from datetime import datetime, timedelta, timezone

import pymongo
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or [l.split("=", 1)[1].strip() for l in open("/app/frontend/.env") if l.startswith("REACT_APP_BACKEND_URL")][0]
BASE_URL = BASE_URL.rstrip("/")
MONGO_URL = [l.split("=", 1)[1].strip().strip('"') for l in open("/app/backend/.env") if l.startswith("MONGO_URL")][0]
DB_NAME = [l.split("=", 1)[1].strip().strip('"') for l in open("/app/backend/.env") if l.startswith("DB_NAME")][0]


# ---------- shared fixtures ----------
@pytest.fixture(scope="module")
def mongo():
    cli = pymongo.MongoClient(MONGO_URL)
    yield cli[DB_NAME]
    cli.close()


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "demo@aivora.ai", "password": "demo123456"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def demo_user_id(demo_token, mongo):
    r = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {demo_token}"}, timeout=30)
    assert r.status_code == 200
    return r.json()["id"]


@pytest.fixture(scope="module")
def h(demo_token):
    return {"Authorization": f"Bearer {demo_token}"}


@pytest.fixture(scope="module")
def cid(h):
    r = requests.get(f"{BASE_URL}/api/conversations", headers=h, timeout=30)
    assert r.status_code == 200
    data = r.json()
    items = data.get("items", data) if isinstance(data, dict) else data
    for c in items:
        pids = c.get("persona_ids") or ([c.get("persona_id")] if c.get("persona_id") else [])
        if c.get("type") in ("private",) and len(pids) == 1 and "oryntix-support" not in pids:
            return c["id"]
    pytest.skip("No 1:1 non-support conversation available for demo user")


# ---------- cleanup fixture ----------
@pytest.fixture(scope="module", autouse=True)
def cleanup(mongo, demo_user_id):
    yield
    titles = ["Rapat tim", "Meeting klien", "bayar listrik", "Uji agenda suara"]
    for t in titles:
        mongo.events.delete_many({"user_id": demo_user_id, "title": {"$regex": t, "$options": "i"}})
        mongo.reminders.delete_many({"user_id": demo_user_id, "title": {"$regex": t, "$options": "i"}})
    # clear any lingering pending state
    mongo.conversations.update_many({"user_id": demo_user_id}, {"$unset": {"pending_calendar": "", "pending_cancel": ""}})


def _send(cid, h, text, timeout=120):
    """Send a message, return the final SSE event. Honours 2s rate-limit per message."""
    time.sleep(2.2)
    r = requests.post(f"{BASE_URL}/api/conversations/{cid}/send", json={"content": text}, headers=h, stream=True, timeout=timeout)
    if r.status_code != 200:
        return {"_status": r.status_code, "_body": r.text[:400]}
    final = {}
    for line in r.iter_lines():
        if line and line.startswith(b"data:"):
            try:
                ev = json.loads(line[5:])
            except Exception:
                continue
            if ev.get("final"):
                final = ev
    return final


# ============================================================
# CHAT FLOW — record (ask → confirm → create)
# ============================================================
class TestChatRecord:
    def test_01_ask(self, cid, h, mongo, demo_user_id):
        # Clear any lingering agenda state before starting
        mongo.conversations.update_one({"id": cid}, {"$unset": {"pending_calendar": "", "pending_cancel": ""}})
        mongo.events.delete_many({"user_id": demo_user_id, "title": {"$regex": "Rapat tim", "$options": "i"}})
        mongo.reminders.delete_many({"user_id": demo_user_id, "title": {"$regex": "Rapat tim", "$options": "i"}})

        f = _send(cid, h, "Ingatkan saya rapat tim besok")
        assert f.get("tool") == "calendar_question", f
        content = (f.get("content") or "").lower()
        # Must ask for time + mode
        assert ("jam" in content or "tanggal" in content), content
        assert ("panggilan" in content or "telepon" in content) and "chat" in content, content

    def test_02_confirm_stage(self, cid, h):
        f = _send(cid, h, "jam 10 pagi, via telepon aja")
        assert f.get("tool") == "calendar_confirm", f
        content = f.get("content") or ""
        assert "10:00" in content, content
        assert "panggilan telepon" in content.lower(), content

    def test_03_create(self, cid, h, mongo, demo_user_id):
        f = _send(cid, h, "ya")
        assert f.get("tool") == "calendar_event", f
        content = f.get("content") or ""
        assert content.startswith("📅 **Tercatat di kalender"), content[:200]
        assert "menelepon Anda otomatis" in content, content
        # SSE final whitelists only a subset of extras; `event` isn't streamed — look it up in mongo.
        doc = mongo.events.find_one({"user_id": demo_user_id, "title": {"$regex": "Rapat tim", "$options": "i"}}, sort=[("created_at", -1)])
        assert doc, "event not persisted"
        ev = {"id": doc["id"]}
        assert "rapat tim" in doc["title"].lower()
        assert (doc.get("remind") or {}).get("mode") == "call"
        assert doc.get("reminder_id")
        rem = mongo.reminders.find_one({"id": doc["reminder_id"], "user_id": demo_user_id})
        assert rem, "linked reminder missing"
        assert rem.get("event_id") == ev["id"]
        assert rem.get("mode") == "call"
        assert rem.get("status") == "scheduled"
        # GET /api/events/upcoming returns it
        up = requests.get(f"{BASE_URL}/api/events/upcoming", headers=h, timeout=30).json()
        assert any(i["id"] == ev["id"] and i["kind"] == "event" for i in up["items"]), up


# ============================================================
# CHAT FLOW — cancel
# ============================================================
class TestChatCancel:
    def test_04_cancel_confirm(self, cid, h):
        f = _send(cid, h, "rapat tim besok batal")
        assert f.get("tool") == "calendar_cancel_confirm", f
        c = f.get("content") or ""
        assert "Rapat tim" in c or "rapat tim" in c.lower(), c
        assert "hapus" in c.lower(), c

    def test_05_cancel_yes(self, cid, h, mongo, demo_user_id):
        f = _send(cid, h, "ya")
        assert f.get("tool") == "calendar_cancelled", f
        # verify event + reminder gone
        docs = list(mongo.events.find({"user_id": demo_user_id, "title": {"$regex": "Rapat tim", "$options": "i"}}))
        assert docs == [], f"events still present: {docs}"
        rems = list(mongo.reminders.find({"user_id": demo_user_id, "title": {"$regex": "Rapat tim", "$options": "i"}}))
        assert rems == [], f"reminders still present: {rems}"


# ============================================================
# CHAT FLOW — edge cases
# ============================================================
class TestChatEdge:
    def test_06a_confirm_then_change_then_decline(self, cid, h, mongo, demo_user_id):
        mongo.conversations.update_one({"id": cid}, {"$unset": {"pending_calendar": "", "pending_cancel": ""}})
        f = _send(cid, h, "Catat jadwal meeting klien Kamis jam 14.00, ingatkan lewat chat")
        assert f.get("tool") == "calendar_confirm", f
        c = (f.get("content") or "").lower()
        assert "pesan chat" in c, c
        assert "14:00" in c, c

        f = _send(cid, h, "ubah jadi jam 15.00")
        assert f.get("tool") == "calendar_confirm", f
        assert "15:00" in (f.get("content") or ""), f

        f = _send(cid, h, "tidak usah")
        assert f.get("tool") == "calendar_question", f
        assert "tidak jadi" in (f.get("content") or "").lower(), f
        # no event created
        n = mongo.events.count_documents({"user_id": demo_user_id, "title": {"$regex": "meeting klien", "$options": "i"}})
        assert n == 0, "unexpected event created after decline"

    def test_06b_no_reminder_flow(self, cid, h, mongo, demo_user_id):
        mongo.conversations.update_one({"id": cid}, {"$unset": {"pending_calendar": "", "pending_cancel": ""}})
        f = _send(cid, h, "Ingatkan saya bayar listrik tanggal 20 jam 9 pagi, tanpa pengingat")
        assert f.get("tool") == "calendar_confirm", f
        assert "Tanpa pengingat" in (f.get("content") or ""), f

        f = _send(cid, h, "ya")
        assert f.get("tool") == "calendar_event", f
        # pull id from DB (SSE final doesn't stream the full event object)
        doc = mongo.events.find_one({"user_id": demo_user_id, "title": {"$regex": "bayar listrik", "$options": "i"}}, sort=[("created_at", -1)])
        assert doc, "event not persisted"
        assert doc.get("remind") in (None, {}), doc.get("remind")
        # DELETE the event afterwards
        r = requests.delete(f"{BASE_URL}/api/events/{doc['id']}", headers=h, timeout=30)
        assert r.status_code == 200
        assert mongo.events.count_documents({"id": doc["id"]}) == 0

    def test_06c_cancel_no_match(self, cid, h, mongo, demo_user_id):
        # Make sure no stale pending state remains
        mongo.conversations.update_one({"id": cid}, {"$unset": {"pending_calendar": "", "pending_cancel": ""}})
        f = _send(cid, h, "janji dokter gigi Jumat gak jadi")
        tool = f.get("tool")
        # LLM-based planner may occasionally reply with a plain message (is_cancel=false). Retry once.
        if tool not in ("calendar_cancel_none", "calendar_cancel_question"):
            f = _send(cid, h, "appointment dokter gigi Jumat batal")
            tool = f.get("tool")
        assert tool in ("calendar_cancel_none", "calendar_cancel_question"), f
        if tool == "calendar_cancel_question":
            f = _send(cid, h, "tidak pernah")
            assert f.get("tool") == "calendar_cancel_none", f

    def test_06d_unrelated(self, cid, h):
        f = _send(cid, h, "apa kabar?")
        # Must NOT trigger any calendar tool; a normal reply streams
        tool = f.get("tool")
        assert tool in (None, "", "chat"), f"unexpected tool for unrelated msg: {tool} / {f}"
        assert (f.get("content") or "").strip(), "empty reply"


# ============================================================
# VOICE ENDPOINTS
# ============================================================
class TestVoiceEndpoints:
    @pytest.fixture(scope="class")
    def voice_event(self, h, mongo, demo_user_id, cid):
        # tomorrow 09:00 +07:00
        tz = timezone(timedelta(hours=7))
        tomorrow = (datetime.now(tz) + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        payload = {"title": "Uji agenda suara", "start_at": tomorrow.isoformat(), "remind_mode": "chat", "remind_offsets": [15]}
        r = requests.post(f"{BASE_URL}/api/events", headers=h, json=payload, timeout=30)
        assert r.status_code == 200, r.text
        ev = r.json()
        yield ev
        # best-effort cleanup
        requests.delete(f"{BASE_URL}/api/events/{ev['id']}", headers=h, timeout=30)
        mongo.events.delete_many({"user_id": demo_user_id, "title": "Uji agenda suara"})
        mongo.reminders.delete_many({"user_id": demo_user_id, "title": "Uji agenda suara"})

    def test_upcoming_q_match(self, h, voice_event):
        r = requests.get(f"{BASE_URL}/api/events/upcoming", params={"q": "agenda suara"}, headers=h, timeout=30)
        assert r.status_code == 200
        items = r.json()["items"]
        hit = next((i for i in items if i["id"] == voice_event["id"]), None)
        assert hit, items
        for k in ("id", "kind", "title", "start_at", "when", "remind_mode", "repeat"):
            assert k in hit, (k, hit)
        assert hit["kind"] == "event"
        assert hit["remind_mode"] == "chat"
        assert hit["repeat"] == "none"
        # Indonesian weekday label
        assert any(d in hit["when"] for d in ("Senin","Selasa","Rabu","Kamis","Jumat","Sabtu","Minggu")), hit["when"]

    def test_upcoming_fallback(self, h, voice_event):
        r = requests.get(f"{BASE_URL}/api/events/upcoming", params={"q": "zzzz"}, headers=h, timeout=30)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1, "expected fallback to all items"

    def test_cancel_ok_and_404(self, h, voice_event, cid, mongo, demo_user_id):
        r = requests.post(f"{BASE_URL}/api/events/cancel", headers=h, json={"id": voice_event["id"], "kind": "event", "conversation_id": cid}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True and body["item"]["id"] == voice_event["id"]
        # assistant message with tool calendar_cancelled appended
        time.sleep(0.5)
        msgs = requests.get(f"{BASE_URL}/api/conversations/{cid}/messages", headers=h, timeout=30).json()["messages"]
        assert any((m.get("meta") or {}).get("tool") == "calendar_cancelled" for m in msgs[-10:]) or \
               any("calendar_cancelled" in json.dumps(m, default=str) for m in msgs[-10:]), "calendar_cancelled msg not posted"
        # second cancel → 404
        r2 = requests.post(f"{BASE_URL}/api/events/cancel", headers=h, json={"id": voice_event["id"], "kind": "event"}, timeout=30)
        assert r2.status_code == 404, r2.text

    def test_cancel_bad_kind_422(self, h, voice_event):
        r = requests.post(f"{BASE_URL}/api/events/cancel", headers=h, json={"id": voice_event["id"], "kind": "foo"}, timeout=30)
        assert r.status_code == 422, r.text


# ============================================================
# REGRESSION — reminders + /events + /calendar
# ============================================================
class TestRegression:
    def test_reminders_crud(self, h, mongo, demo_user_id):
        tz = timezone(timedelta(hours=7))
        when = (datetime.now(tz) + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
        payload = {"title": "TEST_regress_reminder", "description": "", "start_at": when.isoformat(), "remind_minutes": 30, "mode": "chat", "repeat": "none"}
        r = requests.post(f"{BASE_URL}/api/reminders", headers=h, json=payload, timeout=30)
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        r = requests.get(f"{BASE_URL}/api/reminders", headers=h, timeout=30)
        assert r.status_code == 200
        items = r.json()
        if isinstance(items, dict):
            items = items.get("items", [])
        assert any(i["id"] == rid for i in items), "created reminder not in list"
        r = requests.delete(f"{BASE_URL}/api/reminders/{rid}", headers=h, timeout=30)
        assert r.status_code in (200, 204)

    def test_calendar_range(self, h):
        tz = timezone(timedelta(hours=7))
        start = (datetime.now(tz) - timedelta(days=1)).isoformat()
        end = (datetime.now(tz) + timedelta(days=14)).isoformat()
        r = requests.get(f"{BASE_URL}/api/calendar", headers=h, params={"start": start, "end": end}, timeout=30)
        assert r.status_code == 200, r.text
