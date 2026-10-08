"""Iteration 38 — reminders & calendar events with mode + offsets, scheduler, chat intercept.

Adapted from /app/backend/tests/manual_reminders_calendar.py and manual_calendar_followup.py.
Uses minted JWT (login throttle avoidance). LLM-driven chat intercepts are gated behind
TEST_RUN_LLM=1 to avoid burning credits during repeated runs.
"""
import json
import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta

import pytest
import requests

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    BASE_URL = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
API = BASE_URL.rstrip("/") + "/api"
NADIA_ID = "77f5be90-dd50-407c-b9b9-5f604e13447c"


# ---- fixtures ----
@pytest.fixture(scope="module")
def auth_headers():
    from auth import make_token  # noqa: E402
    async def _u():
        from db import db
        return await db.users.find_one({"email": "demo@aivora.ai"})
    u = asyncio.get_event_loop().run_until_complete(_u())
    assert u, "demo user missing"
    tok = make_token(u["id"], "admin")
    return {"Authorization": f"Bearer {tok}"}, u


@pytest.fixture
def future_iso():
    return (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()


# ---- Reminders CRUD + mode/offsets ----
class TestReminderCRUD:
    def test_create_with_offsets_and_chat_mode(self, auth_headers, future_iso):
        H, _ = auth_headers
        r = requests.post(f"{API}/reminders", headers=H, json={
            "title": "TEST_rem1", "start_at": future_iso,
            "offsets": [30, 60], "mode": "chat"
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["mode"] == "chat"
        assert body["offsets"] == [30, 60]
        assert body["status"] == "scheduled"
        assert len(body["alerts"]) == 2
        for a in body["alerts"]:
            assert a["status"] == "scheduled"
        assert body["remind_minutes"] == 30
        start_dt = datetime.fromisoformat(body["start_at"].replace("Z", "+00:00"))
        remind_dt = datetime.fromisoformat(body["remind_at"].replace("Z", "+00:00"))
        delta = (start_dt - remind_dt).total_seconds() / 60
        assert 29 <= delta <= 31, f"remind_at should be 30 min before start, got {delta}"
        requests.delete(f"{API}/reminders/{body['id']}", headers=H)

    def test_legacy_remind_minutes_only(self, auth_headers, future_iso):
        H, _ = auth_headers
        r = requests.post(f"{API}/reminders", headers=H, json={
            "title": "TEST_rem_legacy", "start_at": future_iso,
            "remind_minutes": 15
        }).json()
        assert r["offsets"] == [15]
        assert r["mode"] in ("call", "chat")
        requests.delete(f"{API}/reminders/{r['id']}", headers=H)

    def test_invalid_mode_falls_back_to_call(self, auth_headers, future_iso):
        H, _ = auth_headers
        r = requests.post(f"{API}/reminders", headers=H, json={
            "title": "TEST_rem_bad_mode", "start_at": future_iso,
            "offsets": [30], "mode": "banana"
        }).json()
        assert r["mode"] == "call"
        requests.delete(f"{API}/reminders/{r['id']}", headers=H)

    def test_update_recomputes_alerts(self, auth_headers, future_iso):
        H, _ = auth_headers
        r = requests.post(f"{API}/reminders", headers=H, json={
            "title": "TEST_upd", "start_at": future_iso, "offsets": [30], "mode": "chat"
        }).json()
        rid = r["id"]
        upd = requests.put(f"{API}/reminders/{rid}", headers=H, json={
            "offsets": [60], "mode": "call"
        })
        assert upd.status_code == 200, upd.text
        u = upd.json()
        assert u["mode"] == "call"
        assert u["offsets"] == [60]
        assert u["status"] == "scheduled"
        assert u["remind_minutes"] == 60
        assert len(u["alerts"]) == 1 and u["alerts"][0]["minutes"] == 60
        # GET lists
        lst = requests.get(f"{API}/reminders", headers=H).json()
        assert any(x["id"] == rid for x in lst)
        # DELETE
        d = requests.delete(f"{API}/reminders/{rid}", headers=H)
        assert d.status_code in (200, 204)
        lst2 = requests.get(f"{API}/reminders", headers=H).json()
        assert not any(x["id"] == rid for x in lst2)


# ---- Events ↔ linked reminder ----
class TestEventLinkedReminder:
    def test_event_with_reminder_creates_link(self, auth_headers, future_iso):
        H, u = auth_headers
        ev = requests.post(f"{API}/events", headers=H, json={
            "title": "TEST_ev_linked", "start_at": future_iso, "notes": "Ruang A",
            "remind_mode": "call", "remind_offsets": [30, 60]
        })
        assert ev.status_code == 200, ev.text
        body = ev.json()
        assert body["remind"]["mode"] == "call"
        assert body["remind"]["offsets"] == [30, 60]
        assert body.get("reminder_id")
        rid = body["reminder_id"]
        eid = body["id"]
        # linked reminder present in /reminders
        rems = requests.get(f"{API}/reminders", headers=H).json()
        linked = [x for x in rems if x.get("event_id") == eid]
        assert len(linked) == 1
        assert linked[0]["title"] == "TEST_ev_linked"
        # calendar listing: EVENT present, no duplicate 'reminder' kind for linked
        s = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        e = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        cal = requests.get(f"{API}/calendar", headers=H, params={"start": s, "end": e}).json()
        ev_entries = [c for c in cal if c["kind"] == "event" and c["title"] == "TEST_ev_linked"]
        rem_dups = [c for c in cal if c["kind"] == "reminder" and c.get("id") == rid]
        assert len(ev_entries) == 1
        assert ev_entries[0]["remind"]["mode"] == "call"
        assert ev_entries[0]["remind"]["offsets"] == [30, 60]
        assert not rem_dups, "linked reminder should be hidden from calendar"
        # DELETE event removes reminder
        requests.delete(f"{API}/events/{eid}", headers=H)
        rems2 = requests.get(f"{API}/reminders", headers=H).json()
        assert not any(x.get("event_id") == eid for x in rems2)

    def test_delete_linked_reminder_also_removes_event(self, auth_headers, future_iso):
        H, _ = auth_headers
        ev = requests.post(f"{API}/events", headers=H, json={
            "title": "TEST_ev_del_via_rem", "start_at": future_iso,
            "remind_mode": "chat", "remind_offsets": [30]
        }).json()
        rid = ev["reminder_id"]
        eid = ev["id"]
        d = requests.delete(f"{API}/reminders/{rid}", headers=H)
        assert d.status_code in (200, 204)
        s = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        e = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        cal = requests.get(f"{API}/calendar", headers=H, params={"start": s, "end": e}).json()
        assert not any(c["kind"] == "event" and c.get("id") == eid for c in cal)

    def test_plain_reminder_in_calendar_has_remind(self, auth_headers, future_iso):
        H, _ = auth_headers
        r = requests.post(f"{API}/reminders", headers=H, json={
            "title": "TEST_plain_rem", "start_at": future_iso,
            "offsets": [10, 30], "mode": "chat"
        }).json()
        s = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        e = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        cal = requests.get(f"{API}/calendar", headers=H, params={"start": s, "end": e}).json()
        mine = [c for c in cal if c["kind"] == "reminder" and c.get("id") == r["id"]]
        assert len(mine) == 1
        assert mine[0]["remind"]["mode"] == "chat"
        assert mine[0]["remind"]["offsets"] == [10, 30]
        requests.delete(f"{API}/reminders/{r['id']}", headers=H)

    def test_event_without_remind_no_reminder(self, auth_headers, future_iso):
        H, _ = auth_headers
        ev = requests.post(f"{API}/events", headers=H, json={
            "title": "TEST_ev_noremind", "start_at": future_iso
        }).json()
        assert ev.get("remind") in (None, {}) or ev.get("remind") is None
        assert not ev.get("reminder_id")
        rems = requests.get(f"{API}/reminders", headers=H).json()
        assert not any(x.get("event_id") == ev["id"] for x in rems)
        requests.delete(f"{API}/events/{ev['id']}", headers=H)


# ---- Scheduler ----
class TestScheduler:
    def test_chat_mode_fires_message(self, auth_headers, future_iso):
        H, u = auth_headers
        import reminders as rem_mod
        from db import db

        async def run():
            r = requests.post(f"{API}/reminders", headers=H, json={
                "title": "TEST_sched_chat", "start_at": future_iso,
                "offsets": [30, 60], "mode": "chat"
            }).json()
            past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            await db.reminders.update_one({"id": r["id"]}, {"$set": {"alerts.0.remind_at": past}})
            await rem_mod.scheduler_tick()
            after = await db.reminders.find_one({"id": r["id"]}, {"_id": 0})
            assert after["status"] == "sent", f"expected sent, got {after['status']}"
            statuses = {a["minutes"]: a["status"] for a in after["alerts"]}
            assert statuses[30] == "fired"
            assert statuses[60] == "scheduled"
            msg = await db.messages.find_one({"tool": "reminder", "reminder.id": r["id"]}, {"_id": 0})
            assert msg, "chat reminder message not posted"
            assert msg.get("cta") and msg["cta"].get("href") == "/reminders"
            # second tick should not re-fire first alert
            before2 = [(a["minutes"], a["status"]) for a in after["alerts"]]
            await rem_mod.scheduler_tick()
            after2 = await db.reminders.find_one({"id": r["id"]}, {"_id": 0})
            after2_pairs = [(a["minutes"], a["status"]) for a in after2["alerts"]]
            assert after2_pairs == before2
            requests.delete(f"{API}/reminders/{r['id']}", headers=H)

        asyncio.get_event_loop().run_until_complete(run())

    def test_call_mode_rings_and_incoming(self, auth_headers, future_iso):
        H, _ = auth_headers
        import reminders as rem_mod
        from db import db

        async def run():
            r = requests.post(f"{API}/reminders", headers=H, json={
                "title": "TEST_sched_call", "start_at": future_iso,
                "offsets": [30], "mode": "call"
            }).json()
            past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            await db.reminders.update_one({"id": r["id"]}, {"$set": {"alerts.0.remind_at": past}})
            await rem_mod.scheduler_tick()
            after = await db.reminders.find_one({"id": r["id"]}, {"_id": 0})
            assert after["status"] == "ringing"
            inc = requests.get(f"{API}/reminders/incoming", headers=H).json()
            assert any(i["id"] == r["id"] for i in inc)
            requests.delete(f"{API}/reminders/{r['id']}", headers=H)

        asyncio.get_event_loop().run_until_complete(run())

    def test_legacy_reminder_without_alerts_fires(self, auth_headers, future_iso):
        H, u = auth_headers
        import reminders as rem_mod
        from db import db

        async def run():
            past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            await db.reminders.insert_one({
                "id": "TEST_legacy_sched", "user_id": u["id"], "title": "TEST_Legacy",
                "start_at": future_iso, "remind_minutes": 30, "remind_at": past,
                "status": "scheduled", "created_at": past
            })
            await rem_mod.scheduler_tick()
            r = await db.reminders.find_one({"id": "TEST_legacy_sched"}, {"_id": 0})
            assert r["status"] == "ringing"
            await db.reminders.delete_one({"id": "TEST_legacy_sched"})

        asyncio.get_event_loop().run_until_complete(run())

    def test_very_late_reminder_marked_missed(self, auth_headers):
        H, u = auth_headers
        import reminders as rem_mod
        from db import db

        async def run():
            far_past_start = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
            far_past_remind = (datetime.now(timezone.utc) - timedelta(hours=7, minutes=30)).isoformat()
            await db.reminders.insert_one({
                "id": "TEST_missed", "user_id": u["id"], "title": "TEST_Missed",
                "start_at": far_past_start, "remind_minutes": 30, "remind_at": far_past_remind,
                "status": "scheduled", "mode": "call",
                "alerts": [{"minutes": 30, "remind_at": far_past_remind, "status": "scheduled"}],
                "created_at": far_past_remind
            })
            await rem_mod.scheduler_tick()
            r = await db.reminders.find_one({"id": "TEST_missed"}, {"_id": 0})
            assert r["status"] == "missed", f"expected missed, got {r['status']}"
            await db.reminders.delete_one({"id": "TEST_missed"})

        asyncio.get_event_loop().run_until_complete(run())
