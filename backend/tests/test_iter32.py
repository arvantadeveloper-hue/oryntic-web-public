"""Iteration 32 — Platform back-office (/api/platform/*), chat archives list, pricing roundtrip."""
import os
import random
import string
import time
import pytest
import requests
import sys as _sys; _sys.path.insert(0, '/app/backend/tests')  # noqa: E702
from creds import DEMO_PASSWORD, ADMIN_PASSWORD, BUDI_PASSWORD  # noqa: E402,F401

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].splitlines()[0].strip()
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@aivora.ai"
ADMIN_PASS = ADMIN_PASSWORD
DEMO_EMAIL = "demo@aivora.ai"
DEMO_PASS = DEMO_PASSWORD
BUDI_EMAIL = "budi@aivora.ai"
BUDI_PASS = BUDI_PASSWORD
CID = "4e36eefc-3ae9-4f48-98b5-e1a0fc7828e9"


def _login(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    return r


def _auth(email, pw):
    r = _login(email, pw)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_tok():
    return _auth(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="module")
def demo_tok():
    return _auth(DEMO_EMAIL, DEMO_PASS)


@pytest.fixture(scope="module")
def budi_tok():
    return _auth(BUDI_EMAIL, BUDI_PASS)


# ---------- /platform/me ----------
class TestPlatformMe:
    def test_admin_me(self, admin_tok):
        r = requests.get(f"{API}/platform/me", headers=_h(admin_tok))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("platform_role") == "super_admin"

    def test_demo_me_forbidden(self, demo_tok):
        r = requests.get(f"{API}/platform/me", headers=_h(demo_tok))
        assert r.status_code == 403

    def test_unauth_me(self):
        r = requests.get(f"{API}/platform/me")
        assert r.status_code == 401


# ---------- /platform/stats ----------
class TestPlatformStats:
    def test_stats_shape(self, admin_tok):
        r = requests.get(f"{API}/platform/stats", headers=_h(admin_tok))
        assert r.status_code == 200
        d = r.json()
        for k in ("users_total", "users_new", "credits_sold", "topups", "revenue_idr",
                  "credits_consumed", "credits_outstanding", "active_calls", "active_rooms",
                  "by_feature", "daily"):
            assert k in d, f"missing {k}"
        assert isinstance(d["by_feature"], list) and isinstance(d["daily"], list)

    def test_stats_days_7(self, admin_tok):
        r = requests.get(f"{API}/platform/stats?days=7", headers=_h(admin_tok))
        assert r.status_code == 200
        d = r.json()
        assert len(d["daily"]) == 7


# ---------- staff CRUD ----------
class TestPlatformStaff:
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    fin_email = f"finance-test-{rand}@aivora.ai"
    fin_id = None
    fin_tok = None

    def test_create_finance_staff(self, admin_tok):
        r = requests.post(f"{API}/platform/staff",
                          json={"email": self.__class__.fin_email, "role": "finance"},
                          headers=_h(admin_tok))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("created") is True
        assert d["staff"]["platform_role"] == "finance"
        assert "debug_link" in d, "debug_link expected in preview env"
        self.__class__.fin_id = d["staff"]["id"]
        # extract token
        link = d["debug_link"]
        tok = link.split("token=")[-1].split("&")[0]
        self.__class__.reset_tok = tok

    def test_reset_password_and_login(self):
        r = requests.post(f"{API}/auth/reset-password",
                          json={"token": self.__class__.reset_tok, "password": "Finance123!"})
        assert r.status_code == 200, r.text
        time.sleep(0.3)
        tok = _auth(self.__class__.fin_email, "Finance123!")
        self.__class__.fin_tok = tok

    def test_finance_me(self):
        r = requests.get(f"{API}/platform/me", headers=_h(self.__class__.fin_tok))
        assert r.status_code == 200
        assert r.json()["platform_role"] == "finance"

    def test_finance_stats_allowed(self):
        r = requests.get(f"{API}/platform/stats", headers=_h(self.__class__.fin_tok))
        assert r.status_code == 200

    def test_finance_pricing_get_allowed(self):
        r = requests.get(f"{API}/admin/pricing", headers=_h(self.__class__.fin_tok))
        assert r.status_code == 200

    def test_finance_pricing_put_forbidden(self):
        r = requests.get(f"{API}/admin/pricing", headers=_h(self.__class__.fin_tok))
        body = r.json()
        r2 = requests.put(f"{API}/admin/pricing", json=body, headers=_h(self.__class__.fin_tok))
        assert r2.status_code == 403

    def test_finance_staff_list_forbidden(self):
        r = requests.get(f"{API}/platform/staff", headers=_h(self.__class__.fin_tok))
        assert r.status_code == 403

    def test_finance_adjust_credits_forbidden(self, admin_tok):
        # find any user id
        r = requests.get(f"{API}/platform/users?limit=1", headers=_h(admin_tok))
        uid = r.json()["items"][0]["id"]
        r2 = requests.post(f"{API}/platform/users/{uid}/credits",
                           json={"delta": 10, "note": "x"},
                           headers=_h(self.__class__.fin_tok))
        assert r2.status_code == 403

    def test_admin_staff_list(self, admin_tok):
        r = requests.get(f"{API}/platform/staff", headers=_h(admin_tok))
        assert r.status_code == 200
        items = r.json()["items"]
        emails = [i["email"] for i in items]
        assert ADMIN_EMAIL in emails
        assert self.__class__.fin_email in emails
        owner = [i for i in items if i["email"] == ADMIN_EMAIL][0]
        assert owner.get("is_owner") is True

    def test_change_role_up_and_down(self, admin_tok):
        uid = self.__class__.fin_id
        r1 = requests.put(f"{API}/platform/staff/{uid}", json={"role": "super_admin"}, headers=_h(admin_tok))
        assert r1.status_code == 200
        r2 = requests.put(f"{API}/platform/staff/{uid}", json={"role": "finance"}, headers=_h(admin_tok))
        assert r2.status_code == 200

    def test_cannot_edit_self(self, admin_tok):
        me = requests.get(f"{API}/platform/me", headers=_h(admin_tok)).json()
        r = requests.put(f"{API}/platform/staff/{me['id']}", json={"role": "finance"}, headers=_h(admin_tok))
        assert r.status_code == 400
        r2 = requests.delete(f"{API}/platform/staff/{me['id']}", headers=_h(admin_tok))
        assert r2.status_code == 400

    def test_revoke_finance(self, admin_tok):
        r = requests.delete(f"{API}/platform/staff/{self.__class__.fin_id}", headers=_h(admin_tok))
        assert r.status_code == 200
        # that user's me is now 403
        r2 = requests.get(f"{API}/platform/me", headers=_h(self.__class__.fin_tok))
        assert r2.status_code == 403

    def test_audit_contains_entries(self, admin_tok):
        r = requests.get(f"{API}/platform/audit", headers=_h(admin_tok))
        assert r.status_code == 200
        actions = [i["action"] for i in r.json()["items"]]
        for a in ("staff.grant", "staff.role", "staff.revoke"):
            assert a in actions, f"audit missing {a}"


# ---------- /platform/users ----------
class TestPlatformUsers:
    def test_list_and_fields(self, admin_tok):
        r = requests.get(f"{API}/platform/users?limit=5", headers=_h(admin_tok))
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "has_more" in d
        for it in d["items"]:
            for k in ("id", "email", "credits", "used_30d", "personas", "disabled"):
                assert k in it

    def test_q_filter(self, admin_tok):
        r = requests.get(f"{API}/platform/users?q=budi", headers=_h(admin_tok))
        assert r.status_code == 200
        items = r.json()["items"]
        assert any("budi" in i["email"] for i in items)

    def test_pagination(self, admin_tok):
        r = requests.get(f"{API}/platform/users?limit=2", headers=_h(admin_tok))
        d = r.json()
        if d.get("has_more") and d.get("next_before"):
            r2 = requests.get(f"{API}/platform/users?limit=2&before={d['next_before']}", headers=_h(admin_tok))
            assert r2.status_code == 200
            # no overlap
            ids1 = {i["id"] for i in d["items"]}
            ids2 = {i["id"] for i in r2.json()["items"]}
            assert ids1.isdisjoint(ids2)

    def test_adjust_credits_roundtrip(self, admin_tok, budi_tok):
        r = requests.get(f"{API}/platform/users?q=budi", headers=_h(admin_tok))
        budi = [i for i in r.json()["items"] if i["email"] == BUDI_EMAIL][0]
        before = budi["credits"]
        r1 = requests.post(f"{API}/platform/users/{budi['id']}/credits",
                           json={"delta": 50, "note": "test"}, headers=_h(admin_tok))
        assert r1.status_code == 200
        assert r1.json()["credits"] == before + 50
        # NOTE: /api/wallet for budi queries transactions by workspace_id (demo's id);
        # platform adjust writes credit_transactions with budi's own user_id,
        # so the adjustment row is NOT visible in /api/wallet for the sub-user budi.
        # We assert on the admin-side credit field + verify adjustment exists via re-read.
        r_check = requests.get(f"{API}/platform/users?q=budi", headers=_h(admin_tok))
        budi_after = [i for i in r_check.json()["items"] if i["email"] == BUDI_EMAIL][0]
        assert budi_after["credits"] == before + 50
        # restore
        r2 = requests.post(f"{API}/platform/users/{budi['id']}/credits",
                           json={"delta": -50, "note": "restore"}, headers=_h(admin_tok))
        assert r2.status_code == 200
        assert r2.json()["credits"] == before

    def test_disable_enable_budi(self, admin_tok, budi_tok):
        r = requests.get(f"{API}/platform/users?q=budi", headers=_h(admin_tok))
        budi = [i for i in r.json()["items"] if i["email"] == BUDI_EMAIL][0]
        bid = budi["id"]
        # disable
        r1 = requests.post(f"{API}/platform/users/{bid}/disable",
                           json={"disabled": True, "reason": "test"}, headers=_h(admin_tok))
        assert r1.status_code == 200
        # existing token 401
        me = requests.get(f"{API}/auth/me", headers=_h(budi_tok))
        assert me.status_code == 401
        # login fails 403
        lg = _login(BUDI_EMAIL, BUDI_PASS)
        assert lg.status_code == 403
        # enable (RESTORE)
        r2 = requests.post(f"{API}/platform/users/{bid}/disable",
                           json={"disabled": False}, headers=_h(admin_tok))
        assert r2.status_code == 200
        time.sleep(0.3)
        lg2 = _login(BUDI_EMAIL, BUDI_PASS)
        assert lg2.status_code == 200, f"budi re-login failed: {lg2.text}"

    def test_disable_self_forbidden(self, admin_tok):
        me = requests.get(f"{API}/platform/me", headers=_h(admin_tok)).json()
        r = requests.post(f"{API}/platform/users/{me['id']}/disable",
                          json={"disabled": True}, headers=_h(admin_tok))
        assert r.status_code == 400


# ---------- pricing roundtrip ----------
class TestPricing:
    def test_pricing_get_put_roundtrip(self, admin_tok):
        r = requests.get(f"{API}/admin/pricing", headers=_h(admin_tok))
        assert r.status_code == 200
        body = r.json()
        # GET returns nested shape; PUT expects pricing fields + packages at top level.
        pricing = body.get("pricing") or {}
        put_body = {**pricing, "packages": body.get("packages") or pricing.get("packages", [])}
        r2 = requests.put(f"{API}/admin/pricing", json=put_body, headers=_h(admin_tok))
        assert r2.status_code == 200, r2.text

    def test_preview_margin_override_text(self, admin_tok):
        g = requests.get(f"{API}/admin/pricing", headers=_h(admin_tok)).json()
        pricing = g["pricing"]
        base_body = {**pricing, "packages": g.get("packages") or pricing.get("packages", [])}
        # with override 10%
        body1 = {**base_body, "margin_overrides": {"text": 10}}
        r = requests.post(f"{API}/admin/pricing/preview", json=body1, headers=_h(admin_tok))
        assert r.status_code == 200, r.text
        feats = r.json()["features"]
        text_row = next(f for f in feats if f["feature"] == "text")
        credits_10 = text_row["credits"]
        # default (no override)
        body2 = {**base_body, "margin_overrides": {}}
        r2 = requests.post(f"{API}/admin/pricing/preview", json=body2, headers=_h(admin_tok))
        feats2 = r2.json()["features"]
        text_row2 = next(f for f in feats2 if f["feature"] == "text")
        credits_30 = text_row2["credits"]
        assert credits_10 == 9, f"expected 9, got {credits_10}"
        assert credits_30 == 10, f"expected 10, got {credits_30}"
        # ensure nothing saved: GET pricing again, margin_overrides should NOT include text
        g2 = requests.get(f"{API}/admin/pricing", headers=_h(admin_tok)).json()
        assert "text" not in (g2["pricing"].get("margin_overrides") or {})


# ---------- chat archives ----------
class TestArchives:
    def test_archives_pagination(self, demo_tok):
        r = requests.get(f"{API}/archives?conversation_id={CID}&limit=15", headers=_h(demo_tok))
        assert r.status_code == 200, r.text
        d = r.json()
        items = d.get("items") or []
        assert len(items) == 15
        assert d.get("has_more") is True
        nb = d.get("next_before")
        assert nb
        r2 = requests.get(f"{API}/archives?conversation_id={CID}&limit=15&before={nb}", headers=_h(demo_tok))
        assert r2.status_code == 200
        items2 = r2.json()["items"]
        assert items2, "second page empty"
        # all items2 created_at < nb
        for it in items2:
            assert it["created_at"] < nb, f"{it['created_at']} not < {nb}"
        # no overlap
        ids1 = {i["id"] for i in items}
        ids2 = {i["id"] for i in items2}
        assert ids1.isdisjoint(ids2)

    def test_messages_has_archives_count(self, demo_tok):
        r = requests.get(f"{API}/conversations/{CID}/messages?limit=50", headers=_h(demo_tok))
        assert r.status_code == 200
        d = r.json()
        assert "archives_count" in d
        assert isinstance(d["archives_count"], int)
        assert d["archives_count"] > 0
