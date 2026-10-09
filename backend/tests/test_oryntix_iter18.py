"""Iter 18 — Backend tests: pagination, compact/summary-later, notulen fields, voices, pricing/usage, iter17 regression."""
import os
import json
import time
import requests
import pytest
import sys as _sys; _sys.path.insert(0, '/app/backend/tests')  # noqa: E702
from creds import DEMO_PASSWORD, ADMIN_PASSWORD, BUDI_PASSWORD  # noqa: E402,F401

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://ai-companion-test-5.preview.emergentagent.com").rstrip("/")
MEETING_CID = "bcf72bc8-1c0d-4c5f-bb3c-e7d15dbee9f6"
ADMIN_EMAIL = "admin@aivora.ai"
ADMIN_PASS = ADMIN_PASSWORD


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def demo_h():
    return {"Authorization": f"Bearer {_login('demo@aivora.ai', DEMO_PASSWORD)}"}


@pytest.fixture(scope="module")
def admin_h():
    return {"Authorization": f"Bearer {_login(ADMIN_EMAIL, ADMIN_PASS)}"}


def _parse_sse(text):
    final = None
    statuses = []
    extras = []
    for line in text.split("\n"):
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except Exception:
            continue
        extras.append(obj)
        if obj.get("status"):
            statuses.append(obj["status"])
        if obj.get("final"):
            final = obj
    return final, statuses, extras


def _get_persona_ids(h, n=2):
    r = requests.get(f"{BASE_URL}/api/personas", headers=h, timeout=15)
    assert r.status_code == 200, r.text
    ps = r.json()
    assert len(ps) >= n, "Not enough personas"
    return [p["id"] for p in ps[:n]]


# ---------- (1) Pagination ----------
class TestPagination:
    def test_conversations_pagination(self, demo_h):
        r1 = requests.get(f"{BASE_URL}/api/conversations?limit=20&offset=0", headers=demo_h, timeout=15)
        assert r1.status_code == 200, r1.text
        page1 = r1.json()
        assert isinstance(page1, list)
        assert len(page1) <= 20
        if len(page1) == 20:
            r2 = requests.get(f"{BASE_URL}/api/conversations?limit=20&offset=20", headers=demo_h, timeout=15)
            assert r2.status_code == 200
            page2 = r2.json()
            ids1 = {c["id"] for c in page1}
            ids2 = {c["id"] for c in page2}
            assert ids1.isdisjoint(ids2), "pages overlap"

    def test_messages_pagination(self, demo_h):
        r = requests.get(f"{BASE_URL}/api/conversations/{MEETING_CID}/messages?limit=5", headers=demo_h, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "has_more" in j and "archived_count" in j and "long_chat" in j
        msgs = j["messages"]
        assert len(msgs) <= 5
        # ascending order
        for a, b in zip(msgs, msgs[1:]):
            assert a["created_at"] <= b["created_at"]
        assert isinstance(j["has_more"], bool)
        assert j["archived_count"] >= 56  # already compacted once per context

        if msgs:
            cursor = msgs[0]["created_at"]
            r2 = requests.get(f"{BASE_URL}/api/conversations/{MEETING_CID}/messages?limit=5&before={cursor}", headers=demo_h, timeout=20)
            assert r2.status_code == 200
            j2 = r2.json()
            # archived_count/long_chat omitted when `before` is used
            assert "archived_count" not in j2
            for m in j2["messages"]:
                assert m["created_at"] < cursor, f"{m['created_at']} not < {cursor}"

    def test_messages_archived(self, demo_h):
        r = requests.get(f"{BASE_URL}/api/conversations/{MEETING_CID}/messages?limit=10&archived=1", headers=demo_h, timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert all(m.get("archived") is True for m in j["messages"])


# ---------- (2) Compact / summary-later ----------
class TestCompactFlow:
    @pytest.fixture(scope="class")
    def fresh_cid(self, demo_h):
        pids = _get_persona_ids(demo_h, 2)
        r = requests.post(f"{BASE_URL}/api/conversations", headers=demo_h,
                          json={"persona_ids": pids, "type": "group", "title": "TEST_iter18_compact"}, timeout=20)
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        # send 3 short messages
        for q in ("Halo", "Siapa kamu?", "Terima kasih"):
            s = requests.post(f"{BASE_URL}/api/conversations/{cid}/send", headers=demo_h,
                              json={"content": q}, timeout=120)
            assert s.status_code == 200, s.text
        yield cid
        requests.delete(f"{BASE_URL}/api/conversations/{cid}", headers=demo_h, timeout=15)

    def test_compact_then_followup(self, demo_h, fresh_cid):
        cid = fresh_cid
        # count live msgs before
        before = requests.get(f"{BASE_URL}/api/conversations/{cid}/messages?limit=200", headers=demo_h, timeout=15).json()
        live_before = len(before["messages"])
        assert live_before >= 3

        r = requests.post(f"{BASE_URL}/api/conversations/{cid}/compact", headers=demo_h, timeout=120)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("summary"), "no summary"
        assert j.get("archived", 0) >= 3
        assert j.get("credits_used", 0) > 0

        after = requests.get(f"{BASE_URL}/api/conversations/{cid}/messages?limit=200", headers=demo_h, timeout=15).json()
        # Only the Rangkuman note should be visible now
        assert len(after["messages"]) == 1, f"Expected only 1 live msg (rangkuman), got {len(after['messages'])}"
        note = after["messages"][0]
        assert note.get("is_summary") is True
        assert after["archived_count"] >= 3
        assert after["conversation"].get("memory_summary"), "memory_summary not persisted"

        # archived=1 shows them
        arch = requests.get(f"{BASE_URL}/api/conversations/{cid}/messages?limit=200&archived=1", headers=demo_h, timeout=15).json()
        assert len(arch["messages"]) >= 3

        # Follow-up send still works
        s = requests.post(f"{BASE_URL}/api/conversations/{cid}/send", headers=demo_h,
                          json={"content": "Lanjutkan dengan 1 kalimat singkat."}, timeout=120)
        assert s.status_code == 200, s.text
        final, _, _ = _parse_sse(s.text)
        assert final is not None, "no final event after compact"
        assert final.get("content"), "empty reply after compact"

    def test_summary_later_ok(self, demo_h, fresh_cid):
        r = requests.post(f"{BASE_URL}/api/conversations/{fresh_cid}/summary-later", headers=demo_h, timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_compact_without_live_msgs_400(self, demo_h):
        # create empty conv then immediately compact
        pids = _get_persona_ids(demo_h, 1)
        r = requests.post(f"{BASE_URL}/api/conversations", headers=demo_h,
                          json={"persona_ids": pids, "type": "private", "title": "TEST_iter18_empty"}, timeout=15)
        cid = r.json()["id"]
        try:
            c = requests.post(f"{BASE_URL}/api/conversations/{cid}/compact", headers=demo_h, timeout=30)
            assert c.status_code == 400, c.text
        finally:
            requests.delete(f"{BASE_URL}/api/conversations/{cid}", headers=demo_h, timeout=15)


# ---------- (3) Notulen fields ----------
class TestNotulen:
    def test_set_three_and_check(self, demo_h):
        new_fields = [
            {"name": "  Agenda  ", "required": True},
            {"name": "Keputusan", "required": True},
            {"name": "Catatan", "required": False},
        ]
        r = requests.put(f"{BASE_URL}/api/auth/settings", headers=demo_h, json={"notulen_fields": new_fields}, timeout=15)
        assert r.status_code == 200, r.text
        # verify trimmed names via /me
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=demo_h, timeout=15).json()
        saved = (me.get("settings") or {}).get("notulen_fields") or []
        names = [f["name"] for f in saved]
        assert names == ["Agenda", "Keputusan", "Catatan"], names

        # notulen-check on meeting conv
        chk = requests.post(f"{BASE_URL}/api/conversations/{MEETING_CID}/notulen-check", headers=demo_h, timeout=120)
        assert chk.status_code == 200, chk.text
        j = chk.json()
        assert len(j["fields"]) == 3
        req_names = {"Agenda", "Keputusan"}
        assert set(j["missing"]).issubset(req_names), j["missing"]
        assert "notes" in j

    def test_summary_uses_configured_headings(self, demo_h):
        # Create a fresh meeting with some content so /summary has history
        pids = _get_persona_ids(demo_h, 2)
        r = requests.post(f"{BASE_URL}/api/conversations", headers=demo_h,
                          json={"persona_ids": pids, "type": "meeting", "title": "TEST_iter18_notulen"}, timeout=15)
        cid = r.json()["id"]
        try:
            for q in ("Agenda rapat: review Q1.", "Keputusan: lanjutkan proyek A.", "Catatan: tim butuh 2 anggota baru."):
                s = requests.post(f"{BASE_URL}/api/conversations/{cid}/send", headers=demo_h, json={"content": q}, timeout=120)
                assert s.status_code == 200
            sm = requests.post(f"{BASE_URL}/api/conversations/{cid}/summary", headers=demo_h, timeout=180)
            assert sm.status_code == 200, sm.text
            md = sm.json()["summary"]
            for h in ("Agenda", "Keputusan", "Catatan"):
                assert h in md, f"heading '{h}' missing in summary:\n{md[:400]}"
        finally:
            requests.delete(f"{BASE_URL}/api/conversations/{cid}", headers=demo_h, timeout=15)

    def test_restore_defaults(self, demo_h):
        default = [
            {"name": "Agenda", "required": True},
            {"name": "Pembahasan", "required": True},
            {"name": "Keputusan", "required": True},
            {"name": "Tindak lanjut (PIC & tenggat)", "required": True},
            {"name": "Isu terbuka", "required": False},
        ]
        r = requests.put(f"{BASE_URL}/api/auth/settings", headers=demo_h, json={"notulen_fields": default}, timeout=15)
        assert r.status_code == 200
        me = requests.get(f"{BASE_URL}/api/auth/me", headers=demo_h, timeout=15).json()
        saved = (me.get("settings") or {}).get("notulen_fields") or []
        assert [f["name"] for f in saved] == [f["name"] for f in default]


# ---------- (4) Voices ----------
class TestVoices:
    def test_voices_list(self, demo_h):
        r = requests.get(f"{BASE_URL}/api/voice/voices", headers=demo_h, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert len(j["voices"]) == 13
        assert j["voices"][:2] == ["marin", "cedar"]
        assert len(j["realtime"]) == 10
        assert isinstance(j["info"], dict) and len(j["info"]) >= 13

    def test_tts_marin_fallback(self, demo_h):
        r = requests.post(f"{BASE_URL}/api/voice/tts", headers=demo_h,
                          json={"text": "Halo, ini contoh suara", "voice": "marin"}, timeout=60)
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("audio/mpeg")
        assert len(r.content) > 100


# ---------- (5) Pricing & usage ----------
class TestPricingUsage:
    def test_admin_pricing_includes_fields(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/admin/pricing", headers=admin_h, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        p = j["pricing"]
        assert abs(p["usd_per_credit"] - 0.001) < 1e-9
        rates = j["rates"]
        assert abs(rates["image"] - 122) <= 1, rates
        assert abs(rates["text_per_1k"] - 9.74) < 0.05, rates
        assert "video_per_sec" in rates
        assert abs(rates["realtime_per_min"] - 29) <= 1

    def test_realtime_usage_billing(self, demo_h):
        # Create a call
        c = requests.post(f"{BASE_URL}/api/realtime/calls", headers=demo_h,
                          json={"conversation_id": MEETING_CID}, timeout=30)
        if c.status_code == 503:
            pytest.skip("Realtime disabled")
        assert c.status_code == 200, c.text
        call_id = c.json()["call_id"]

        usage = {
            "input_token_details": {"audio_tokens": 1200, "text_tokens": 300},
            "output_token_details": {"audio_tokens": 900, "text_tokens": 120},
        }
        u1 = requests.post(f"{BASE_URL}/api/realtime/calls/{call_id}/usage", headers=demo_h,
                           json={"usage": usage}, timeout=30)
        assert u1.status_code == 200, u1.text
        j1 = u1.json()
        assert abs(j1["usd"] - 0.0991) < 0.001, j1
        assert abs(j1["charged_now"] - 143) <= 1, j1

        u2 = requests.post(f"{BASE_URL}/api/realtime/calls/{call_id}/usage", headers=demo_h,
                           json={"usage": usage}, timeout=30)
        assert u2.status_code == 200
        j2 = u2.json()
        assert abs(j2["charged_now"] - 143) <= 1, j2
        assert j2["credits_total"] >= j1["credits_total"] + 140

        # End with 30s elapsed → 1 minute connection fee ≈ 29
        e = requests.post(f"{BASE_URL}/api/realtime/calls/{call_id}/end", headers=demo_h,
                          json={"elapsed_seconds": 30}, timeout=30)
        assert e.status_code == 200, e.text
        je = e.json()
        assert je.get("billed_minutes") == 1
        assert abs(je.get("charged_now", 0) - 29) <= 2, f"connection fee off: {je}"


# ---------- (6) Regression: iter17 send + routing badge ----------
class TestRegression:
    def test_meeting_chat_channel_send(self, demo_h):
        # ensure smart_routing ON
        requests.put(f"{BASE_URL}/api/auth/settings", headers=demo_h, json={"smart_routing": True}, timeout=15)
        time.sleep(2)
        r = requests.post(f"{BASE_URL}/api/conversations/{MEETING_CID}/send", headers=demo_h,
                          json={"content": "Jelaskan singkat apa itu regex di python, 1 kalimat.",
                                "channel": "meeting_chat"}, timeout=120)
        assert r.status_code == 200, r.text
        final, _, _ = _parse_sse(r.text)
        assert final is not None
        assert final.get("routed") == "it", f"expected routed=it: {final}"
        assert final.get("model_label") == "Claude Sonnet"
