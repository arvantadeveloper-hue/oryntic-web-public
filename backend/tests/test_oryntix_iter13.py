"""Iteration 13 tests: Moderator interjection endpoint + Admin usage report."""
import os
import time
import json
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ai-companion-test-5.preview.emergentagent.com").rstrip("/")
API = BASE_URL + "/api"

ADMIN = {"email": "demo@aivora.ai", "password": "demo123456"}
BUDI = {"email": "budi@aivora.ai", "password": "budi123456"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def budi_token():
    return _login(BUDI)


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def two_personas(admin_token):
    r = requests.get(f"{API}/personas", headers=_h(admin_token), timeout=30)
    assert r.status_code == 200
    personas = r.json()
    assert len(personas) >= 2, "Need at least 2 personas"
    return [p["id"] for p in personas[:2]]


@pytest.fixture(scope="module")
def meeting_conv(admin_token, two_personas):
    r = requests.post(f"{API}/conversations", headers=_h(admin_token),
                      json={"type": "meeting", "persona_ids": two_personas, "title": "TEST_mod_meeting"}, timeout=30)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    yield cid
    requests.delete(f"{API}/conversations/{cid}", headers=_h(admin_token), timeout=30)


@pytest.fixture(scope="module")
def private_conv_admin(admin_token, two_personas):
    r = requests.post(f"{API}/conversations", headers=_h(admin_token),
                      json={"type": "private", "persona_ids": [two_personas[0]], "title": "TEST_priv"}, timeout=30)
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    yield cid
    requests.delete(f"{API}/conversations/{cid}", headers=_h(admin_token), timeout=30)


# -------- Moderator endpoint tests --------
class TestModerate:
    def test_moderate_meeting_no_messages_returns_null(self, admin_token, meeting_conv):
        r = requests.post(f"{API}/conversations/{meeting_conv}/moderate",
                          headers=_h(admin_token), json={"reason": "silence"}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["content"] is None
        assert data["voice"] == "onyx"

    def test_moderate_bogus_reason_422(self, admin_token, meeting_conv):
        r = requests.post(f"{API}/conversations/{meeting_conv}/moderate",
                          headers=_h(admin_token), json={"reason": "bogus"}, timeout=30)
        assert r.status_code == 422, r.text

    def test_moderate_on_private_400(self, admin_token, private_conv_admin):
        r = requests.post(f"{API}/conversations/{private_conv_admin}/moderate",
                          headers=_h(admin_token), json={"reason": "silence"}, timeout=30)
        assert r.status_code == 400, r.text
        assert "moderator" in r.text.lower() or "meeting" in r.text.lower()

    def test_moderate_foreign_conversation_404(self, admin_token):
        r = requests.post(f"{API}/conversations/nonexistent-cid-xyz/moderate",
                          headers=_h(admin_token), json={"reason": "silence"}, timeout=30)
        assert r.status_code == 404

    def test_moderate_silence_after_user_message(self, admin_token, meeting_conv):
        # send one user message (consume SSE)
        r = requests.post(f"{API}/conversations/{meeting_conv}/send",
                          headers=_h(admin_token), json={"content": "Halo semua, bagaimana rencana peluncuran minggu ini?"},
                          timeout=120, stream=True)
        assert r.status_code == 200
        for _ in r.iter_lines():
            pass
        time.sleep(1)

        # admin credits before
        me1 = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=30).json()
        credits_before = me1.get("credits", 0)

        r2 = requests.post(f"{API}/conversations/{meeting_conv}/moderate",
                           headers=_h(admin_token), json={"reason": "silence"}, timeout=60)
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert isinstance(data.get("content"), str) and len(data["content"]) > 0, f"expected non-empty content, got {data}"
        assert data["voice"] == "onyx"

        # moderator message must appear in GET /messages
        time.sleep(1)
        msgs = requests.get(f"{API}/conversations/{meeting_conv}/messages", headers=_h(admin_token), timeout=30).json()["messages"]
        mod_msgs = [m for m in msgs if m.get("persona_id") == "__moderator__"]
        assert len(mod_msgs) >= 1, "moderator message not persisted"
        assert mod_msgs[-1].get("is_moderator") is True

        # admin credits should drop (meeting_moderation recorded)
        me2 = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=30).json()
        assert me2.get("credits", 0) <= credits_before, "credits should decrease (or equal)"

    def test_moderate_stuck_with_insufficient_turns(self, admin_token, two_personas):
        # fresh meeting w/ only 1 user turn
        r = requests.post(f"{API}/conversations", headers=_h(admin_token),
                          json={"type": "meeting", "persona_ids": two_personas, "title": "TEST_stuck1"}, timeout=30)
        cid = r.json()["id"]
        try:
            # send one message
            r0 = requests.post(f"{API}/conversations/{cid}/send", headers=_h(admin_token),
                               json={"content": "Pembuka diskusi."}, timeout=120, stream=True)
            for _ in r0.iter_lines():
                pass
            time.sleep(1)
            r2 = requests.post(f"{API}/conversations/{cid}/moderate",
                               headers=_h(admin_token), json={"reason": "stuck"}, timeout=30)
            assert r2.status_code == 200
            assert r2.json()["content"] is None
        finally:
            requests.delete(f"{API}/conversations/{cid}", headers=_h(admin_token), timeout=30)


# -------- Admin usage-report tests --------
class TestUsageReport:
    def test_usage_report_shape_and_totals(self, admin_token):
        r = requests.get(f"{API}/admin/usage-report?days=7", headers=_h(admin_token), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("days", "total", "events", "by_user", "by_feature", "daily"):
            assert k in d, f"missing key {k}"
        assert d["days"] == 7
        assert len(d["daily"]) == 7
        # desc sorted by_user
        for i in range(len(d["by_user"]) - 1):
            assert d["by_user"][i]["credits"] >= d["by_user"][i + 1]["credits"]
        # totals consistency
        sum_user = sum(x["credits"] for x in d["by_user"])
        sum_feat = sum(x["credits"] for x in d["by_feature"])
        sum_daily = sum(x["credits"] for x in d["daily"])
        assert d["total"] == sum_user == sum_feat == sum_daily, f"inconsistent {d['total']}/{sum_user}/{sum_feat}/{sum_daily}"
        # Indonesian labels
        feat_map = {x["feature"]: x["label"] for x in d["by_feature"]}
        if "chat" in feat_map:
            assert feat_map["chat"] == "Chat"
        if "realtime_call" in feat_map:
            assert feat_map["realtime_call"] == "Panggilan Realtime"

    def test_usage_report_clamps(self, admin_token):
        r = requests.get(f"{API}/admin/usage-report?days=400", headers=_h(admin_token), timeout=30).json()
        assert r["days"] == 365
        r = requests.get(f"{API}/admin/usage-report?days=0", headers=_h(admin_token), timeout=30).json()
        assert r["days"] == 1

    def test_usage_report_forbidden_for_user(self, budi_token):
        r = requests.get(f"{API}/admin/usage-report?days=7", headers=_h(budi_token), timeout=30)
        assert r.status_code == 403

    def test_budi_attribution(self, admin_token, budi_token):
        # Find or create budi's private conv
        convs = requests.get(f"{API}/conversations", headers=_h(budi_token), timeout=30).json()
        private_budi = next((c for c in convs if c.get("type") == "private" and c.get("user_id")), None)
        if not private_budi:
            # need a persona id
            personas = requests.get(f"{API}/personas", headers=_h(budi_token), timeout=30).json()
            assert personas
            r = requests.post(f"{API}/conversations", headers=_h(budi_token),
                              json={"type": "private", "persona_ids": [personas[0]["id"]], "title": "TEST_budi_priv"}, timeout=30)
            assert r.status_code == 200, r.text
            cid = r.json()["id"]
        else:
            cid = private_budi["id"]

        r0 = requests.post(f"{API}/conversations/{cid}/send", headers=_h(budi_token),
                           json={"content": "Halo apa kabar hari ini?"}, timeout=120, stream=True)
        assert r0.status_code == 200
        for _ in r0.iter_lines():
            pass
        time.sleep(2)

        r2 = requests.get(f"{API}/admin/usage-report?days=1", headers=_h(admin_token), timeout=30).json()
        budi_entries = [u for u in r2["by_user"] if (u.get("email") or "").lower() == "budi@aivora.ai"]
        assert budi_entries, f"Budi not in by_user: {r2['by_user']}"
        assert budi_entries[0]["credits"] > 0
