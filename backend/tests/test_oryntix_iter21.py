"""Iter 21 - Task delegation offer/accept, scheduled tasks, direct assign, calendar aggregation.

Credentials:
  demo@aivora.ai / $TEST_DEMO_PASSWORD  (workspace owner, see backend/.env)
  budi@aivora.ai / budi123456  (member of demo workspace)
"""
import os
import json
import time
from datetime import datetime, timedelta, timezone

import pytest
import requests
import sys as _sys; _sys.path.insert(0, '/app/backend/tests')  # noqa: E702
from creds import DEMO_PASSWORD, ADMIN_PASSWORD, BUDI_PASSWORD  # noqa: E402,F401

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://ai-companion-test-5.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def demo_token():
    return _login("demo@aivora.ai", DEMO_PASSWORD)


@pytest.fixture(scope="module")
def budi_token():
    return _login("budi@aivora.ai", BUDI_PASSWORD)


@pytest.fixture(scope="module")
def persona_id(demo_token):
    r = requests.get(f"{API}/personas", headers=H(demo_token), timeout=30)
    assert r.status_code == 200
    personas = r.json()
    assert personas, "no personas available"
    return personas[0]["id"]


def _new_conv(tok, pid, title="Iter21 test"):
    r = requests.post(
        f"{API}/conversations",
        headers=H(tok),
        json={"type": "private", "persona_ids": [pid], "title": title},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _send_sse(tok, cid, text, timeout=120):
    """POST /conversations/{cid}/send, read SSE lines, return the final event dict."""
    final = None
    with requests.post(
        f"{API}/conversations/{cid}/send",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        json={"content": text},
        stream=True,
        timeout=timeout,
    ) as r:
        assert r.status_code == 200, f"/send {r.status_code} {r.text[:400]}"
        for raw in r.iter_lines():
            if not raw:
                continue
            try:
                line = raw.decode("utf-8")
            except Exception:
                continue
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except Exception:
                continue
            if ev.get("final"):
                final = ev
    assert final is not None, "no final SSE event"
    return final


# ---------- A) Offer trigger via long delegation ----------
class TestTaskOfferTurn:
    def test_long_delegation_produces_offer(self, demo_token, persona_id):
        cid = _new_conv(demo_token, persona_id)
        tasks_before = requests.get(f"{API}/tasks?limit=5", headers=H(demo_token), timeout=20).json()
        ids_before = {t["id"] for t in tasks_before}

        text = ("Tolong susunkan proposal lengkap program pelatihan karyawan 2027: "
                "latar belakang, tujuan, kurikulum 6 modul, jadwal, dan anggaran rinci.")
        final = _send_sse(demo_token, cid, text)
        assert final.get("tool") == "task_offer", f"expected tool=task_offer, got {final}"
        pending = final.get("pending_task") or {}
        assert isinstance(pending.get("title"), str) and pending["title"].strip(), "pending_task.title missing"
        content = (final.get("content") or "") + " " + (final.get("text") or "")
        assert "bahas satu per satu" in content.lower(), "offer missing 'bahas satu per satu'"
        assert "terima beres" in content.lower(), "offer missing 'terima beres'"

        # No new task created yet
        tasks_after = requests.get(f"{API}/tasks?limit=20", headers=H(demo_token), timeout=20).json()
        new_ids = {t["id"] for t in tasks_after} - ids_before
        assert not new_ids, f"unexpected new tasks created on offer: {new_ids}"

        # Conv should have pending_task persisted
        pytest.offer_cid = cid

    def test_short_question_no_offer(self, demo_token, persona_id):
        cid = _new_conv(demo_token, persona_id, title="short-q")
        final = _send_sse(demo_token, cid, "Apa ibu kota Australia?")
        assert final.get("tool") != "task_offer", f"short q unexpectedly triggered offer: {final.get('tool')}"


# ---------- B) Accept delegate -> queued task runs to completion ----------
class TestAcceptDelegate:
    def test_accept_delegate_flow(self, demo_token, persona_id):
        cid = getattr(pytest, "offer_cid", None)
        if not cid:
            cid = _new_conv(demo_token, persona_id)
            _send_sse(demo_token, cid, "Tolong susunkan proposal lengkap program pelatihan karyawan 2027: latar belakang, tujuan, kurikulum 6 modul, jadwal, dan anggaran rinci.")

        r = requests.post(f"{API}/conversations/{cid}/tasks/accept",
                          headers=H(demo_token), json={"mode": "delegate"}, timeout=30)
        assert r.status_code == 200, r.text
        msg = r.json()
        assert msg.get("tool") == "task_assigned", f"missing tool=task_assigned: {msg}"
        task_id = msg.get("task_id")
        assert task_id, "task_id missing in assistant message"

        # GET task detail
        r = requests.get(f"{API}/tasks/{task_id}", headers=H(demo_token), timeout=30)
        assert r.status_code == 200, r.text
        t = r.json()
        assert t.get("type") == "assigned"
        assert t.get("source") == "chat"
        assert t.get("persona_name"), "persona_name missing on task"

        # Poll until completed (up to ~120s)
        deadline = time.time() + 150
        last_status = None
        while time.time() < deadline:
            r = requests.get(f"{API}/tasks/{task_id}", headers=H(demo_token), timeout=30)
            t = r.json()
            last_status = t.get("status")
            if last_status == "completed":
                break
            if last_status == "failed":
                pytest.fail(f"task failed: {t.get('error')}")
            time.sleep(3)
        assert last_status == "completed", f"task did not complete in time (last status={last_status})"
        assert (t.get("final_output") or "").strip(), "final_output empty"
        assert t.get("credits_used", 0) > 0, "credits_used not > 0"

        # Conversation last message has tool=task_done
        r = requests.get(f"{API}/conversations/{cid}/messages", headers=H(demo_token), timeout=30)
        assert r.status_code == 200
        msgs = r.json().get("messages") or []
        last_ai = next((m for m in reversed(msgs) if m.get("role") == "assistant"), None)
        assert last_ai is not None
        assert last_ai.get("tool") == "task_done", f"last AI msg not task_done: {last_ai}"
        assert last_ai.get("task_id") == task_id

        # /task-notifications lists this task
        r = requests.get(f"{API}/task-notifications", headers=H(demo_token), timeout=30)
        assert r.status_code == 200
        notifs = r.json()
        assert any(n.get("id") == task_id for n in notifs), f"task not in /task-notifications: {notifs}"

        # Ack and verify empty for this task
        r = requests.post(f"{API}/task-notifications/ack", headers=H(demo_token), timeout=30)
        assert r.status_code == 200
        r = requests.get(f"{API}/task-notifications", headers=H(demo_token), timeout=30)
        assert r.status_code == 200
        assert not any(n.get("id") == task_id for n in r.json()), "task still in notifications after ack"

        # Accept again -> 400 (no pending offer)
        r = requests.post(f"{API}/conversations/{cid}/tasks/accept",
                          headers=H(demo_token), json={"mode": "delegate"}, timeout=30)
        assert r.status_code == 400, f"expected 400 after task consumed, got {r.status_code} {r.text}"

        pytest.completed_task_id = task_id


# ---------- C) Scheduled task via "terima beres saja" text + Discuss mode ----------
class TestScheduledAndDiscuss:
    def test_scheduled_via_text_accept(self, demo_token, persona_id):
        cid = _new_conv(demo_token, persona_id, title="scheduled")
        # Server clock is 2026-10-02 UTC per context; "lusa jam 10 pagi" should resolve future
        delegation = ("Tolong susunkan proposal lengkap program magang mahasiswa 2027: "
                      "latar belakang, tujuan, kurikulum, jadwal, dan anggaran. Kerjakan lusa jam 10 pagi.")
        final = _send_sse(demo_token, cid, delegation)
        assert final.get("tool") == "task_offer", f"no offer: {final}"

        # Now text-only accept
        final2 = _send_sse(demo_token, cid, "terima beres saja")
        assert final2.get("tool") == "task_assigned", f"expected task_assigned, got {final2.get('tool')} :: {final2}"
        task_id = final2.get("task_id")
        assert task_id, "task_id missing"

        r = requests.get(f"{API}/tasks/{task_id}", headers=H(demo_token), timeout=30)
        assert r.status_code == 200
        t = r.json()
        assert t.get("status") == "scheduled", f"expected scheduled, got {t.get('status')} - scheduled_at={t.get('scheduled_at')}"
        sched = t.get("scheduled_at")
        assert sched, "scheduled_at missing"
        # future (UTC)
        try:
            d = datetime.fromisoformat(sched.replace("Z", "+00:00"))
        except Exception:
            pytest.fail(f"scheduled_at not ISO: {sched}")
        assert d > datetime.now(timezone.utc), f"scheduled_at not in future: {sched}"
        pytest.scheduled_task_id = task_id

    def test_discuss_mode_no_task_created(self, demo_token, persona_id):
        cid = _new_conv(demo_token, persona_id, title="discuss")
        final = _send_sse(demo_token, cid,
            "Tolong susun strategi pemasaran digital lengkap untuk brand kopi lokal "
            "mencakup target audiens, kanal, kampanye bulanan, KPI dan anggaran.")
        assert final.get("tool") == "task_offer"

        tasks_before = requests.get(f"{API}/tasks?limit=50", headers=H(demo_token), timeout=20).json()
        ids_before = {t["id"] for t in tasks_before}

        r = requests.post(f"{API}/conversations/{cid}/tasks/accept",
                          headers=H(demo_token), json={"mode": "discuss"}, timeout=60)
        assert r.status_code == 200, r.text
        msg = r.json()
        # discuss mode returns a plain assistant message (no tool=task_assigned)
        assert msg.get("tool") not in ("task_assigned",), f"discuss should not assign: {msg.get('tool')}"
        assert (msg.get("content") or "").strip(), "discuss message content empty"

        tasks_after = requests.get(f"{API}/tasks?limit=50", headers=H(demo_token), timeout=20).json()
        new_ids = {t["id"] for t in tasks_after} - ids_before
        assert not new_ids, f"discuss should not create tasks, got {new_ids}"


# ---------- D) Direct assign endpoint ----------
class TestDirectAssign:
    def test_direct_assign_creates_and_executes(self, demo_token, persona_id):
        cid = _new_conv(demo_token, persona_id, title="direct-assign")
        r = requests.post(
            f"{API}/conversations/{cid}/tasks",
            headers=H(demo_token),
            json={"title": "Ringkasan riset pasar EV",
                  "brief": "Buat ringkasan 1 halaman", "scheduled_at": None},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("task_id", "status", "when", "assistant"):
            assert k in body, f"missing {k} in response: {body}"
        task_id = body["task_id"]

        deadline = time.time() + 150
        last = None
        while time.time() < deadline:
            r = requests.get(f"{API}/tasks/{task_id}", headers=H(demo_token), timeout=30)
            t = r.json()
            last = t.get("status")
            if last == "completed":
                break
            if last == "failed":
                pytest.fail(f"direct task failed: {t.get('error')}")
            time.sleep(3)
        assert last == "completed", f"direct task not completed, last={last}"

    def test_invalid_cid_returns_404(self, demo_token):
        r = requests.post(
            f"{API}/conversations/does-not-exist/tasks",
            headers=H(demo_token),
            json={"title": "x" * 5, "brief": "y"},
            timeout=20,
        )
        assert r.status_code == 404, f"expected 404, got {r.status_code} {r.text}"


# ---------- E) Calendar ----------
class TestCalendar:
    def test_event_crud_and_calendar_aggregation(self, demo_token):
        # pick a month window around today (server clock 2026-10)
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1)

        start_at = (now + timedelta(days=1)).replace(microsecond=0).isoformat()
        r = requests.post(f"{API}/events", headers=H(demo_token),
                          json={"title": "TEST_Iter21 Event", "start_at": start_at,
                                "notes": "iter21 note"}, timeout=20)
        assert r.status_code == 200, r.text
        ev = r.json()
        assert ev.get("id")
        # UTC normalized
        assert ev["start_at"].endswith("+00:00") or ev["start_at"].endswith("Z"), f"not UTC: {ev['start_at']}"
        ev_id = ev["id"]

        r = requests.get(f"{API}/calendar",
                         params={"start": month_start.isoformat(), "end": month_end.isoformat()},
                         headers=H(demo_token), timeout=30)
        assert r.status_code == 200, r.text
        items = r.json()
        assert isinstance(items, list)
        kinds = {i["kind"] for i in items}
        assert "event" in kinds, f"no event kind: {kinds}"
        # sort check
        ats = [i.get("at") or "" for i in items]
        assert ats == sorted(ats), "calendar items not sorted by at"
        assert any(i["kind"] == "event" and i.get("id") == ev_id for i in items)
        # task kind (we created scheduled + completed tasks earlier in session)
        assert "task" in kinds, f"no task kind in calendar: {kinds}"

        # bad dates -> 400
        r = requests.get(f"{API}/calendar", params={"start": "not-a-date", "end": "nope"},
                         headers=H(demo_token), timeout=20)
        assert r.status_code == 400, f"bad dates expected 400 got {r.status_code}"

        # delete event
        r = requests.delete(f"{API}/events/{ev_id}", headers=H(demo_token), timeout=20)
        assert r.status_code == 200, r.text
        r = requests.delete(f"{API}/events/{ev_id}", headers=H(demo_token), timeout=20)
        assert r.status_code == 404, f"second delete expected 404 got {r.status_code}"
        pytest.shared_event_start = start_at

    def test_member_sees_event_but_cannot_delete(self, demo_token, budi_token):
        # Create a fresh event as demo
        now = datetime.now(timezone.utc)
        start_at = (now + timedelta(days=2)).replace(microsecond=0).isoformat()
        r = requests.post(f"{API}/events", headers=H(demo_token),
                          json={"title": "TEST_Iter21 SharedEvent", "start_at": start_at}, timeout=20)
        assert r.status_code == 200, r.text
        ev_id = r.json()["id"]

        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        month_end = (now.replace(day=1) + timedelta(days=40)).isoformat()

        r = requests.get(f"{API}/calendar", params={"start": month_start, "end": month_end},
                         headers=H(budi_token), timeout=30)
        assert r.status_code == 200, r.text
        items = r.json()
        target = next((i for i in items if i.get("id") == ev_id and i["kind"] == "event"), None)
        assert target is not None, f"budi did not see demo's event {ev_id}"
        assert target.get("mine") is False, f"expected mine=False for budi, got {target}"

        # Budi cannot delete
        r = requests.delete(f"{API}/events/{ev_id}", headers=H(budi_token), timeout=20)
        assert r.status_code == 404, f"budi delete should 404, got {r.status_code}"

        # Cleanup as demo
        requests.delete(f"{API}/events/{ev_id}", headers=H(demo_token), timeout=20)
