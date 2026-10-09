"""Iteration 14: Trial plan, platform-admin separation, pricing/trial admin endpoints, quota trial expiry."""
import os
import uuid
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import sys as _sys; _sys.path.insert(0, '/app/backend/tests')  # noqa: E702
from creds import DEMO_PASSWORD, ADMIN_PASSWORD, BUDI_PASSWORD  # noqa: E402,F401

def _read_base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        for line in open("/app/frontend/.env"):
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

BASE = _read_base()
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "test_database"

DEMO = ("demo@aivora.ai", DEMO_PASSWORD)
ADMIN = ("admin@aivora.ai", ADMIN_PASSWORD)


def _login(email, pw):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, (email, r.status_code, r.text)
    return r.json()["access_token"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def demo_tok():
    return _login(*DEMO)


@pytest.fixture(scope="module")
def admin_tok():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def trial_user():
    """Register a fresh trial user; return (email, pw, token, user_dict)."""
    email = f"trial_{uuid.uuid4().hex[:10]}@aivora.ai"
    pw = "TrialPass123!"
    r = requests.post(f"{BASE}/api/auth/register", json={"email": email, "password": pw, "name": "Trial Tester"}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    return {"email": email, "pw": pw, "token": body["access_token"], "user": body["user"]}


# ------------ Register & /auth/me ------------
class TestRegister:
    def test_register_trial_defaults(self, trial_user):
        u = trial_user["user"]
        assert u["role"] == "admin"
        assert u["plan"] == "trial"
        assert u["credits"] == 700
        assert u["daily_credit_limit"] == 100
        assert u.get("trial_ends_at")
        assert not (u.get("is_platform_admin"))

    def test_me_matches(self, trial_user):
        r = requests.get(f"{BASE}/api/auth/me", headers=_hdr(trial_user["token"]), timeout=20)
        assert r.status_code == 200
        u = r.json()
        assert u["plan"] == "trial"
        assert u["credits"] == 700
        assert u["daily_credit_limit"] == 100
        assert u["role"] == "admin"
        assert not (u["is_platform_admin"])
        assert u["trial_ends_at"]


# ------------ Platform admin guards ------------
PLATFORM_ONLY_GETS = ["/api/admin/overview", "/api/admin/users", "/api/admin/tasks",
                     "/api/admin/pricing", "/api/admin/rate-limits", "/api/admin/realtime-pricing"]


class TestPlatformGuards:
    def test_demo_blocked_on_platform_endpoints(self, demo_tok):
        for ep in PLATFORM_ONLY_GETS:
            r = requests.get(f"{BASE}{ep}", headers=_hdr(demo_tok), timeout=20)
            assert r.status_code == 403, f"{ep} returned {r.status_code}, expected 403"

    def test_demo_blocked_on_put_trial(self, demo_tok):
        r = requests.put(f"{BASE}/api/admin/trial", headers=_hdr(demo_tok),
                         json={"trial_days": 7, "trial_daily_limit": 100, "trial_credits": 700}, timeout=20)
        assert r.status_code == 403

    def test_demo_allowed_on_workspace_endpoints(self, demo_tok):
        r = requests.get(f"{BASE}/api/admin/workspace-users", headers=_hdr(demo_tok), timeout=20)
        assert r.status_code == 200
        r = requests.get(f"{BASE}/api/admin/usage-report", headers=_hdr(demo_tok), timeout=30)
        assert r.status_code == 200

    def test_platform_admin_allowed(self, admin_tok):
        for ep in PLATFORM_ONLY_GETS:
            r = requests.get(f"{BASE}{ep}", headers=_hdr(admin_tok), timeout=30)
            assert r.status_code == 200, f"{ep} returned {r.status_code}"


# ------------ Pricing & Trial admin endpoints ------------
class TestPricingAndTrial:
    def test_pricing_get_shape(self, admin_tok):
        r = requests.get(f"{BASE}/api/admin/pricing", headers=_hdr(admin_tok), timeout=20)
        assert r.status_code == 200
        d = r.json()
        for k in ("packages", "pricing", "rates", "trial", "providers", "tariff"):
            assert k in d
        p = d["pricing"]
        for f in ("margin_pct", "tax_pct", "usd_to_idr", "idr_per_credit",
                  "text_usd_per_1k_chars", "image_usd", "profile_usd", "stt_usd", "tts_usd", "provider_usd_per_min"):
            assert f in p
        rates = d["rates"]
        assert abs(rates["text_per_1k"] - 2.01) < 0.05
        assert rates["image"] == 25
        assert rates["profile"] == 8
        assert rates["stt"] == 5
        assert rates["tts"] == 4
        assert rates["realtime_per_min"] == 75
        t = d["trial"]
        assert t == {"trial_days": 7, "trial_daily_limit": 100, "trial_credits": 700}

    def test_pricing_put_margin_recomputes(self, admin_tok, demo_tok):
        # bump margin to 50
        base = requests.get(f"{BASE}/api/admin/pricing", headers=_hdr(admin_tok), timeout=20).json()["pricing"]
        new = {**base, "margin_pct": 50.0}
        r = requests.put(f"{BASE}/api/admin/pricing", headers=_hdr(admin_tok), json=new, timeout=20)
        assert r.status_code == 200, r.text
        rates = r.json()["rates"]
        # expected image: ceil(0.084*1.5*1.11*16500/80) = ceil(28.85) = 29
        assert rates["image"] == 29
        # realtime: ceil(0.25*1.5*1.11*16500/80) = ceil(85.84) = 86
        assert rates["realtime_per_min"] in (86, 87)  # accept rounding variants

        # realtime/status reflects it
        rs = requests.get(f"{BASE}/api/realtime/status", headers=_hdr(demo_tok), timeout=20)
        assert rs.status_code == 200
        assert rs.json().get("credits_per_min") == rates["realtime_per_min"]

        # restore
        r = requests.put(f"{BASE}/api/admin/pricing", headers=_hdr(admin_tok), json={**base, "margin_pct": 30.0}, timeout=20)
        assert r.status_code == 200
        rates2 = r.json()["rates"]
        assert rates2["image"] == 25
        assert rates2["realtime_per_min"] == 75

    def test_trial_put_affects_new_registrations(self, admin_tok):
        # change trial config
        r = requests.put(f"{BASE}/api/admin/trial", headers=_hdr(admin_tok),
                         json={"trial_days": 14, "trial_daily_limit": 150, "trial_credits": 1000}, timeout=20)
        assert r.status_code == 200
        assert r.json()["trial"]["trial_credits"] == 1000

        try:
            # register a new user
            email = f"trial_{uuid.uuid4().hex[:10]}@aivora.ai"
            rr = requests.post(f"{BASE}/api/auth/register",
                               json={"email": email, "password": "Pass12345!", "name": "T2"}, timeout=30)
            assert rr.status_code == 200
            u = rr.json()["user"]
            assert u["credits"] == 1000
            assert u["daily_credit_limit"] == 150
        finally:
            # restore
            rb = requests.put(f"{BASE}/api/admin/trial", headers=_hdr(admin_tok),
                              json={"trial_days": 7, "trial_daily_limit": 100, "trial_credits": 700}, timeout=20)
            assert rb.status_code == 200


# ------------ Trial quota expiry → 402 ------------
async def _set_trial_expired(user_id):
    client = AsyncIOMotorClient(MONGO_URL)
    try:
        await client[DB_NAME].users.update_one({"id": user_id}, {"$set": {"trial_ends_at": "2020-01-01T00:00:00+00:00"}})
    finally:
        client.close()


class TestTrialQuotaAndTopup:
    def test_trial_expired_blocks_send_and_topup_resumes(self, trial_user):
        tok = trial_user["token"]
        uid = trial_user["user"]["id"]
        h = _hdr(tok)

        # Create a minimal persona
        rp = requests.post(f"{BASE}/api/personas", headers=h,
                           json={"profile": {"identity": {"name": "QuotaTestP", "summary": "trial test"}}}, timeout=30)
        assert rp.status_code == 200, rp.text
        pid = rp.json()["id"]

        # Create a private conversation
        rc = requests.post(f"{BASE}/api/conversations", headers=h,
                           json={"persona_ids": [pid], "type": "private"}, timeout=20)
        assert rc.status_code == 200, rc.text
        cid = rc.json()["id"]

        # Expire trial via Mongo
        asyncio.get_event_loop().run_until_complete(_set_trial_expired(uid))

        # /send should return 402 with "Masa percobaan"
        rs = requests.post(f"{BASE}/api/conversations/{cid}/send", headers=h,
                           json={"content": "halo"}, timeout=30)
        assert rs.status_code == 402, (rs.status_code, rs.text)
        assert "Masa percobaan" in rs.text

        # Topup: pick first package
        pkgs = requests.get(f"{BASE}/api/wallet/packages", headers=h, timeout=20).json()
        pkg_id = pkgs[0]["id"]
        rt = requests.post(f"{BASE}/api/wallet/topup", headers=h, json={"package_id": pkg_id}, timeout=20)
        assert rt.status_code == 200, rt.text

        # /auth/me now shows plan=paid, daily_credit_limit=0
        me = requests.get(f"{BASE}/api/auth/me", headers=h, timeout=20).json()
        assert me["plan"] == "paid"
        assert me["daily_credit_limit"] == 0


# ------------ Cleanup fixture: drop test users to avoid DB bloat ------------
@pytest.fixture(scope="session", autouse=True)
def _cleanup():
    yield
    try:
        client = AsyncIOMotorClient(MONGO_URL)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(client[DB_NAME].users.delete_many({"email": {"$regex": "^trial_.*@aivora.ai$"}}))
        client.close()
    except Exception:
        pass
