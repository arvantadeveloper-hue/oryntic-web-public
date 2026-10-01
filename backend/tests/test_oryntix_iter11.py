"""Oryntix iteration-11 — Realtime voice backend tests."""
import os
import time
import math
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ai-companion-test-5.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = ("demo@aivora.ai", "demo123456")
USER = ("budi@aivora.ai", "budi123456")


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_tok():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def user_tok():
    return _login(*USER)


# --- /realtime/status ---------------------------------------------------
class TestStatus:
    def test_status_requires_auth(self):
        assert requests.get(f"{API}/realtime/status", timeout=15).status_code in (401, 403)

    def test_status_authed(self, admin_tok):
        r = requests.get(f"{API}/realtime/status", headers=_hdr(admin_tok), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["enabled"] is True
        assert d["model"] == "gpt-realtime"
        assert isinstance(d["credits_per_min"], int) and d["credits_per_min"] > 0


# --- Admin realtime pricing ---------------------------------------------
class TestPricing:
    DEFAULTS = {"provider_usd_per_min": 0.25, "margin_pct": 30, "tax_pct": 11,
                "usd_to_idr": 16500, "idr_per_credit": 80}

    def test_user_forbidden_get(self, user_tok):
        r = requests.get(f"{API}/admin/realtime-pricing", headers=_hdr(user_tok), timeout=15)
        assert r.status_code == 403

    def test_user_forbidden_put(self, user_tok):
        r = requests.put(f"{API}/admin/realtime-pricing", headers=_hdr(user_tok), json=self.DEFAULTS, timeout=15)
        assert r.status_code == 403

    def test_defaults_and_cpm_math(self, admin_tok):
        # Ensure defaults first
        r = requests.put(f"{API}/admin/realtime-pricing", headers=_hdr(admin_tok), json=self.DEFAULTS, timeout=15)
        assert r.status_code == 200
        g = requests.get(f"{API}/admin/realtime-pricing", headers=_hdr(admin_tok), timeout=15).json()
        assert g["provider_usd_per_min"] == 0.25
        assert g["margin_pct"] == 30
        assert g["tax_pct"] == 11
        assert g["usd_to_idr"] == 16500
        assert g["idr_per_credit"] == 80
        assert g["credits_per_min"] == 75

    def test_put_custom_and_restore(self, admin_tok):
        payload = {"provider_usd_per_min": 0.2, "margin_pct": 30, "tax_pct": 11,
                   "usd_to_idr": 16000, "idr_per_credit": 80}
        r = requests.put(f"{API}/admin/realtime-pricing", headers=_hdr(admin_tok), json=payload, timeout=15)
        assert r.status_code == 200
        d = r.json()
        expected = math.ceil(0.2 * 1.3 * 1.11 * 16000 / 80)
        assert expected == 58
        assert d["credits_per_min"] == 58
        # restore
        r = requests.put(f"{API}/admin/realtime-pricing", headers=_hdr(admin_tok), json=self.DEFAULTS, timeout=15)
        assert r.status_code == 200 and r.json()["credits_per_min"] == 75


# --- helpers ------------------------------------------------------------
def _create_private_conv(tok):
    # pick an existing persona
    personas = requests.get(f"{API}/personas", headers=_hdr(tok), timeout=15).json()
    assert personas, "no personas in workspace"
    pid = personas[0]["id"]
    r = requests.post(f"{API}/conversations", headers=_hdr(tok),
                      json={"type": "private", "persona_ids": [pid], "title": f"TEST_rt_{uuid.uuid4().hex[:6]}"},
                      timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["id"], pid


# --- /realtime/calls creation -------------------------------------------
class TestCreateCall:
    def test_create_ok(self, admin_tok):
        cid, pid = _create_private_conv(admin_tok)
        r = requests.post(f"{API}/realtime/calls", headers=_hdr(admin_tok),
                          json={"conversation_id": cid}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("call_id", "voice", "model", "credits_per_min", "language", "persona"):
            assert k in d
        assert d["persona"]["id"] == pid
        assert d["persona"]["name"]
        assert d["model"] == "gpt-realtime"

    def test_inaccessible_conversation_404(self, admin_tok, user_tok):
        # Create a convo as user that admin cannot access? Admin owns workspace, so instead,
        # use a bogus id
        r = requests.post(f"{API}/realtime/calls", headers=_hdr(admin_tok),
                          json={"conversation_id": "nonexistent-" + uuid.uuid4().hex}, timeout=15)
        assert r.status_code == 404

    def test_group_without_persona_400(self, admin_tok):
        # Create a meeting with no personas (or group) -> persona_id missing on conv
        # Create a group conversation (type meeting) with another participant but no persona
        # We'll craft a conversation lacking persona_id
        users = requests.get(f"{API}/admin/workspace-users", headers=_hdr(admin_tok), timeout=15).json()
        others = [u for u in users if u.get("email") != ADMIN[0]]
        if not others:
            pytest.skip("no second user available")
        r = requests.post(f"{API}/conversations", headers=_hdr(admin_tok),
                          json={"type": "meeting", "participant_ids": [others[0]["id"]],
                                "persona_ids": [], "title": "TEST_rt_meet"}, timeout=15)
        if r.status_code != 200:
            pytest.skip(f"cannot create meeting w/o persona: {r.status_code} {r.text}")
        cid = r.json()["id"]
        rr = requests.post(f"{API}/realtime/calls", headers=_hdr(admin_tok),
                           json={"conversation_id": cid}, timeout=15)
        assert rr.status_code == 400


# --- negotiate (bad SDP -> 502) ----------------------------------------
class TestNegotiate:
    def test_bad_sdp_502(self, admin_tok):
        cid, _ = _create_private_conv(admin_tok)
        c = requests.post(f"{API}/realtime/calls", headers=_hdr(admin_tok),
                          json={"conversation_id": cid}, timeout=20).json()
        call_id = c["call_id"]
        # NOTE: public (Cloudflare) edge rewrites upstream 502 into an HTML error page.
        # Hit backend directly on localhost so we can validate the actual JSON detail.
        r = requests.post(f"http://localhost:8001/api/realtime/calls/{call_id}/negotiate",
                          headers={**_hdr(admin_tok), "Content-Type": "application/sdp"},
                          data="invalid sdp", timeout=60)
        assert r.status_code == 502, r.text
        detail = r.json().get("detail", "")
        assert detail == "Negosiasi Realtime gagal, coba lagi", f"got detail={detail!r}"


# --- transcript ---------------------------------------------------------
class TestTranscript:
    def test_assistant_user_and_bad_role(self, admin_tok):
        cid, _ = _create_private_conv(admin_tok)
        c = requests.post(f"{API}/realtime/calls", headers=_hdr(admin_tok),
                          json={"conversation_id": cid}, timeout=20).json()
        call_id = c["call_id"]
        # assistant
        r = requests.post(f"{API}/realtime/calls/{call_id}/transcript", headers=_hdr(admin_tok),
                          json={"role": "assistant", "content": "Halo tes"}, timeout=15)
        assert r.status_code == 200
        # user
        r2 = requests.post(f"{API}/realtime/calls/{call_id}/transcript", headers=_hdr(admin_tok),
                           json={"role": "user", "content": "balasan user"}, timeout=15)
        assert r2.status_code == 200
        # bogus role
        rb = requests.post(f"{API}/realtime/calls/{call_id}/transcript", headers=_hdr(admin_tok),
                           json={"role": "bogus", "content": "x"}, timeout=15)
        assert rb.status_code == 422
        # Appears in messages
        msgs = requests.get(f"{API}/conversations/{cid}/messages", headers=_hdr(admin_tok), timeout=15).json()
        texts = [m.get("content") for m in msgs.get("messages", msgs if isinstance(msgs, list) else [])]
        # some servers return list directly
        if isinstance(msgs, dict) and "messages" in msgs:
            arr = msgs["messages"]
        elif isinstance(msgs, list):
            arr = msgs
        else:
            arr = []
        assert any(m.get("content") == "Halo tes" and m.get("via") == "realtime"
                   and m.get("role") == "assistant" and m.get("persona_name") for m in arr), f"missing assistant tx in {arr}"


# --- billing (tick + end) ----------------------------------------------
class TestBilling:
    def test_tick_end_flow(self, admin_tok):
        cid, _ = _create_private_conv(admin_tok)
        c = requests.post(f"{API}/realtime/calls", headers=_hdr(admin_tok),
                          json={"conversation_id": cid}, timeout=20).json()
        call_id = c["call_id"]
        cpm = c["credits_per_min"]

        me0 = requests.get(f"{API}/auth/me", headers=_hdr(admin_tok), timeout=15).json()
        credits0 = me0.get("credits", 0)

        r = requests.post(f"{API}/realtime/calls/{call_id}/tick", headers=_hdr(admin_tok),
                          json={"elapsed_seconds": 70}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["billed_minutes"] == 2
        assert d["charged_now"] == 2 * cpm

        me1 = requests.get(f"{API}/auth/me", headers=_hdr(admin_tok), timeout=15).json()
        assert me1["credits"] == credits0 - 2 * cpm, f"{credits0} -> {me1['credits']}"

        # second tick no additional charge
        r2 = requests.post(f"{API}/realtime/calls/{call_id}/tick", headers=_hdr(admin_tok),
                           json={"elapsed_seconds": 90}, timeout=15).json()
        assert r2["billed_minutes"] == 2
        assert r2["charged_now"] == 0

        # end with 130s -> 3 minutes, charge 1 extra
        e = requests.post(f"{API}/realtime/calls/{call_id}/end", headers=_hdr(admin_tok),
                          json={"elapsed_seconds": 130}, timeout=15)
        assert e.status_code == 200, e.text
        ed = e.json()
        assert ed["billed_minutes"] == 3
        assert ed["charged_now"] == cpm

        # subsequent tick 400
        r3 = requests.post(f"{API}/realtime/calls/{call_id}/tick", headers=_hdr(admin_tok),
                           json={"elapsed_seconds": 200}, timeout=15)
        assert r3.status_code == 400

    def test_other_users_call_404(self, admin_tok, user_tok):
        cid, _ = _create_private_conv(admin_tok)
        c = requests.post(f"{API}/realtime/calls", headers=_hdr(admin_tok),
                          json={"conversation_id": cid}, timeout=20).json()
        call_id = c["call_id"]
        r = requests.post(f"{API}/realtime/calls/{call_id}/tick", headers=_hdr(user_tok),
                         json={"elapsed_seconds": 10}, timeout=15)
        assert r.status_code == 404
        # cleanup
        requests.post(f"{API}/realtime/calls/{call_id}/end", headers=_hdr(admin_tok),
                      json={"elapsed_seconds": 1}, timeout=15)


# --- reminders fallback & respond --------------------------------------
class TestReminders:
    def _create(self, tok, minutes_ahead=1):
        start = (datetime.now(timezone.utc) + timedelta(minutes=minutes_ahead)).isoformat()
        r = requests.post(f"{API}/reminders", headers=_hdr(tok),
                          json={"title": "TEST_rt_rem", "description": "bahas Q1",
                                "start_at": start, "remind_minutes": 1},
                          timeout=15)
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def test_incoming_has_persona_fallback(self, admin_tok):
        rid = self._create(admin_tok)
        # wait up to 40s for scheduler
        found = None
        for _ in range(40):
            time.sleep(2)
            lst = requests.get(f"{API}/reminders/incoming", headers=_hdr(admin_tok), timeout=15).json()
            for it in lst:
                if it["id"] == rid and it.get("status") == "ringing":
                    found = it
                    break
            if found:
                break
        assert found is not None, "reminder did not ring"
        assert found.get("persona") and found["persona"].get("name"), "persona fallback missing"

        # respond realtime:true
        r = requests.post(f"{API}/reminders/{rid}/respond", headers=_hdr(admin_tok),
                          json={"action": "accept", "realtime": True}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "answered"
        assert d["message"] is None
        assert isinstance(d["opening"], str) and "TEST_rt_rem" in d["opening"]
        assert d["persona"]["voice"]
        assert d["conversation"]["id"] and d["conversation"]["type"] == "private"

    def test_respond_realtime_false_message(self, admin_tok):
        rid = self._create(admin_tok)
        for _ in range(40):
            time.sleep(2)
            lst = requests.get(f"{API}/reminders/incoming", headers=_hdr(admin_tok), timeout=15).json()
            if any(it["id"] == rid and it.get("status") == "ringing" for it in lst):
                break
        r = requests.post(f"{API}/reminders/{rid}/respond", headers=_hdr(admin_tok),
                          json={"action": "accept", "realtime": False}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("message"), str) and len(d["message"]) > 10
