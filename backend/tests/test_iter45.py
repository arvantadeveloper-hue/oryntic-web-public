"""Iteration 45 — video resume, repeating social posts, wallet video-sessions."""
import asyncio
import os
import time
from datetime import datetime, timezone, timedelta

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "demo@aivora.ai", "password": "demo123456"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def me(token):
    r = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}"}


def _db():
    return AsyncIOMotorClient(MONGO_URL)[DB_NAME]


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------- 1) GET /wallet/video-sessions ----------
class TestVideoSessionsEndpoint:
    def test_shape_and_pagination(self, H, me):
        r = requests.get(f"{BASE_URL}/api/wallet/video-sessions", headers=H)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("items", "has_more", "next_before"):
            assert k in data
        for it in data["items"]:
            for k in ("id", "title", "started_at", "seconds", "credits", "sessions"):
                assert k in it, f"missing {k} in call item"
            for s in it["sessions"]:
                for k in ("id", "started_at", "ended_at", "seconds", "credits", "max_seconds",
                          "status", "end_reason", "end_label", "resumed", "sandbox"):
                    assert k in s, f"missing {k} in session"

        # paginated: limit=1
        r1 = requests.get(f"{BASE_URL}/api/wallet/video-sessions?limit=1", headers=H)
        assert r1.status_code == 200
        d1 = r1.json()
        assert len(d1["items"]) <= 1
        if d1["has_more"] and d1["next_before"]:
            r2 = requests.get(f"{BASE_URL}/api/wallet/video-sessions?limit=1&before={d1['next_before']}", headers=H)
            assert r2.status_code == 200


# ---------- 2) Error responses ----------
class TestVideoErrorPaths:
    def test_stop_bogus_call_404(self, H):
        r = requests.post(f"{BASE_URL}/api/realtime/calls/bogus-xyz/video/stop",
                          json={"elapsed_seconds": 5, "reason": "DISCONNECTED"}, headers=H)
        assert r.status_code == 404, r.text
        assert "Tidak ada sesi video aktif" in r.text

    def test_stop_invalid_reason_422(self, H):
        r = requests.post(f"{BASE_URL}/api/realtime/calls/bogus-xyz/video/stop",
                          json={"elapsed_seconds": 5, "reason": "FOO"}, headers=H)
        assert r.status_code == 422, r.text

    def test_start_resume_bogus_call_404(self, H):
        r = requests.post(f"{BASE_URL}/api/realtime/calls/bogus-xyz/video/start",
                          json={"resume": True}, headers=H)
        assert r.status_code == 404, r.text
        assert "Panggilan dukungan tidak ditemukan" in r.text


# ---------- 3) DB-seeded resume ----------
class TestResumeFlow:
    def test_resume_leftover_then_exhausted(self, H, me):
        uid = me["id"]
        async def seed():
            db = _db()
            await db.realtime_calls.insert_one({
                "id": "t-call-1", "user_id": uid, "persona_id": "oryntix-support",
                "conversation_id": None, "created_at": _now_iso()
            })
            await db.video_sessions.insert_one({
                "id": "t-vs-1", "call_id": "t-call-1", "user_id": uid,
                "status": "ended", "end_reason": "DISCONNECTED",
                "max_seconds": 1200, "billed_seconds": 500, "credits": 1000, "prior_credits": 0,
                "credits_per_sec": 2, "sandbox": True,
                "created_at": _now_iso(), "ended_at": _now_iso(), "updated_at": _now_iso(),
                "la_session_id": "fake", "session_token": "fake",
            })

        async def cleanup():
            db = _db()
            await db.realtime_calls.delete_many({"id": "t-call-1"})
            await db.video_sessions.delete_many({"call_id": "t-call-1"})

        try:
            asyncio.run(seed())

            # Verify the seeded call appears in wallet/video-sessions
            r_v = requests.get(f"{BASE_URL}/api/wallet/video-sessions", headers=H)
            assert r_v.status_code == 200
            ids = [c["id"] for c in r_v.json()["items"]]
            assert "t-call-1" in ids, "seeded call must appear in video-sessions"

            # Attempt resume
            r = requests.post(f"{BASE_URL}/api/realtime/calls/t-call-1/video/start",
                              json={"resume": True}, headers=H)
            # Must NOT be 400 "Tidak ada sesi video yang bisa dilanjutkan"
            if r.status_code == 400:
                assert "Tidak ada sesi video yang bisa dilanjutkan" not in (r.text or ""), r.text
            assert r.status_code in (200, 402, 503), f"unexpected {r.status_code}: {r.text}"
            if r.status_code == 200:
                data = r.json()
                assert data.get("resumed") is True
                assert data.get("max_seconds", 999) <= 700
                assert data.get("prior_credits") == 1000

            # Make leftover < 20s → should be 400 "Sisa waktu video sudah habis"
            async def exhaust():
                db = _db()
                # clear any new active session created above (don't allow _close_stale_video 409)
                await db.video_sessions.update_many(
                    {"call_id": "t-call-1", "status": "active"},
                    {"$set": {"status": "ended", "end_reason": "USER_CLOSED", "ended_at": _now_iso()}}
                )
                await db.video_sessions.update_one(
                    {"id": "t-vs-1"},
                    {"$set": {"billed_seconds": 1190}}
                )

            asyncio.run(exhaust())
            r2 = requests.post(f"{BASE_URL}/api/realtime/calls/t-call-1/video/start",
                               json={"resume": True}, headers=H)
            assert r2.status_code == 400, r2.text
            assert "Sisa waktu video sudah habis" in r2.text
        finally:
            asyncio.run(cleanup())


# ---------- 4) Recurring social schedule ----------
class TestRecurringSchedule:
    def test_tick_creates_next_weekly(self, H, me):
        uid = me["id"]
        from zoneinfo import ZoneInfo
        tz_name = "Asia/Jakarta"
        tz = ZoneInfo(tz_name)

        orig_id = "t-sched-orig-1"
        past_iso = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        job = {
            "id": orig_id, "user_id": uid, "status": "scheduled",
            "scheduled_at": past_iso, "scheduled_label": "x",
            "payload": {
                "providers": ["linkedin"], "kind": "text", "text": "tes berulang",
                "title": "", "media_path": None, "drive_id": None,
                "app_url": "https://oryntix.app", "source": {},
            },
            "providers": ["linkedin"], "kind": "text", "text": "tes berulang",
            "repeat": "weekly", "tz": tz_name, "series_id": orig_id,
            "repeat_label": "setiap Senin 08:00", "created_at": _now_iso(),
        }

        async def seed():
            db = _db()
            await db.social_schedules.insert_one(dict(job))

        async def tick():
            import sys
            sys.path.insert(0, "/app/backend")
            import social as social_mod
            await social_mod.social_tick()

        async def cleanup():
            db = _db()
            await db.social_schedules.delete_many({"series_id": orig_id})
            await db.social_schedules.delete_many({"id": orig_id})

        try:
            asyncio.run(seed())
            asyncio.run(tick())

            # Original must be done
            async def fetch():
                db = _db()
                orig = await db.social_schedules.find_one({"id": orig_id}, {"_id": 0})
                nxt = await db.social_schedules.find_one(
                    {"series_id": orig_id, "id": {"$ne": orig_id}, "status": "scheduled"},
                    {"_id": 0}
                )
                return orig, nxt

            orig, nxt = asyncio.run(fetch())
            assert orig and orig["status"] in ("failed", "sent", "partial"), f"orig status: {orig and orig.get('status')}"
            assert nxt, "Next occurrence must be scheduled"
            assert nxt["repeat"] == "weekly"
            assert nxt["series_id"] == orig_id

            # Check +7 days
            orig_dt = datetime.fromisoformat(past_iso)
            nxt_dt = datetime.fromisoformat(nxt["scheduled_at"])
            delta = nxt_dt - orig_dt
            # Should be at least 7 days
            assert delta >= timedelta(days=6, hours=23), f"delta {delta}"
            assert nxt.get("repeat_label", "").startswith("setiap ")

            # Stop repeat
            jid = nxt["id"]
            r = requests.post(f"{BASE_URL}/api/social/scheduled/{jid}/stop-repeat", headers=H)
            assert r.status_code == 200, r.text

            async def verify():
                db = _db()
                return await db.social_schedules.find_one({"id": jid}, {"_id": 0})

            doc = asyncio.run(verify())
            assert doc["repeat"] == "none"

            # Second call → 404
            r2 = requests.post(f"{BASE_URL}/api/social/scheduled/{jid}/stop-repeat", headers=H)
            assert r2.status_code == 404

            # GET scheduled lists both
            rl = requests.get(f"{BASE_URL}/api/social/scheduled", headers=H)
            assert rl.status_code == 200
            ids = {x["id"] for x in rl.json()["items"]}
            assert jid in ids
        finally:
            asyncio.run(cleanup())


# ---------- 5) chat._schedule_utc unit ----------
class TestScheduleUtcUnit:
    def test_weekly_rolls_and_none_past(self):
        import sys
        sys.path.insert(0, "/app/backend")
        import chat
        res = chat._schedule_utc("2026-01-05T08:00", {}, "weekly")
        assert isinstance(res, tuple) and len(res) == 4, res
        utc_iso, label, repeat, rlabel = res
        assert repeat == "weekly"
        assert rlabel.startswith("setiap ") and "08:00" in rlabel
        # Must be future
        assert datetime.fromisoformat(utc_iso) > datetime.now(timezone.utc)

        res2 = chat._schedule_utc("2026-01-05T08:00", {}, "none")
        assert res2 is None
