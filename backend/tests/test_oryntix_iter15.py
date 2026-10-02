"""Iter15: cross-tenant persona isolation, trial-expiry inheritance, login throttle, admin regression."""
import os
import uuid
import asyncio
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

DEMO = ("demo@aivora.ai", "demo123456")
BUDI = ("budi@aivora.ai", "budi123456")
PLATFORM = ("admin@aivora.ai", "Aivora!Admin2026")

S = requests.Session()
S.headers["Content-Type"] = "application/json"


def _login(email, pw):
    r = S.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _reg(email, pw, name):
    r = S.post(f"{API}/auth/register", json={"email": email, "password": pw, "name": name})
    assert r.status_code in (200, 201), f"register {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


MIN_PROFILE = {
    "identity": {"name": "TEST15_Persona", "age_range": "25-30", "gender_presentation": "female",
                 "background": "test", "occupation": "tester", "summary": "iter15 isolation persona"},
    "personality": {"primary_traits": ["calm"], "communication_style": "concise", "humor": "dry",
                    "formality": "neutral", "attitude": "friendly", "boundaries": "pro only"},
    "appearance": {"face": "oval", "hair": "black", "eyes": "brown", "skin": "medium",
                   "build": "average", "clothing": "casual", "distinctive": "none", "visual_style": "modern"},
    "voice": {"character": "warm", "language": "id", "accent": "neutral", "pace": "medium"},
    "language": {"primary": "id", "additional": ["en"]},
    "system_instructions": "You are a test persona."
}


@pytest.fixture(scope="module")
def mongo():
    cli = AsyncIOMotorClient(MONGO_URL)
    db = cli[DB_NAME]
    yield db
    cli.close()


@pytest.fixture(scope="module")
def two_fresh_admins():
    a_email = f"iter15a_{uuid.uuid4().hex[:8]}@aivora.ai"
    b_email = f"iter15b_{uuid.uuid4().hex[:8]}@aivora.ai"
    a_tok = _reg(a_email, "pwd12345", "Iter15 A")
    b_tok = _reg(b_email, "pwd12345", "Iter15 B")
    yield {"a_email": a_email, "a_tok": a_tok, "b_email": b_email, "b_tok": b_tok}
    # cleanup via mongo
    async def _clean():
        cli = AsyncIOMotorClient(MONGO_URL)
        db = cli[DB_NAME]
        for em in (a_email, b_email):
            u = await db.users.find_one({"email": em})
            if u:
                await db.personas.delete_many({"user_id": u["id"]})
                await db.users.delete_one({"id": u["id"]})
        cli.close()
    asyncio.run(_clean())


# =========== 1. CROSS-TENANT PERSONA ISOLATION ===========

class TestPersonaIsolation:
    def test_a_creates_persona(self, two_fresh_admins):
        tok = two_fresh_admins["a_tok"]
        r = S.post(f"{API}/personas", headers=_hdr(tok),
                   json={"profile": MIN_PROFILE, "model": "gpt-5.4", "voice": "alloy"})
        assert r.status_code == 200, r.text
        pid = r.json()["id"]
        two_fresh_admins["a_persona_id"] = pid
        assert pid

    def test_b_admin_personas_excludes_a(self, two_fresh_admins):
        tok_b = two_fresh_admins["b_tok"]
        r = S.get(f"{API}/admin/personas", headers=_hdr(tok_b))
        assert r.status_code == 200, r.text
        ids = {p["id"] for p in r.json()}
        assert two_fresh_admins["a_persona_id"] not in ids
        # Fresh B has no personas
        assert ids == set() or two_fresh_admins["a_persona_id"] not in ids

    def test_a_admin_personas_contains_only_own(self, two_fresh_admins):
        tok_a = two_fresh_admins["a_tok"]
        r = S.get(f"{API}/admin/personas", headers=_hdr(tok_a))
        assert r.status_code == 200
        ids = {p["id"] for p in r.json()}
        assert two_fresh_admins["a_persona_id"] in ids
        # Must be subset of GET /personas
        r2 = S.get(f"{API}/personas", headers=_hdr(tok_a))
        assert r2.status_code == 200
        own_ids = {p["id"] for p in r2.json()}
        assert ids.issubset(own_ids), f"admin/personas {ids} not subset of personas {own_ids}"

    def test_demo_admin_personas_subset_own(self):
        tok = _login(*DEMO)
        r = S.get(f"{API}/admin/personas", headers=_hdr(tok))
        assert r.status_code == 200
        admin_ids = {p["id"] for p in r.json()}
        r2 = S.get(f"{API}/personas", headers=_hdr(tok))
        own_ids = {p["id"] for p in r2.json()}
        assert admin_ids.issubset(own_ids)
        assert len(admin_ids) > 0  # demo has Rio/Nova/Nadia

    def test_budi_member_forbidden(self):
        tok = _login(*BUDI)
        r = S.get(f"{API}/admin/personas", headers=_hdr(tok))
        assert r.status_code == 403


# =========== 2. ADMIN REGRESSION ===========

class TestAdminRegression:
    def test_workspace_users_demo(self):
        tok = _login(*DEMO)
        r = S.get(f"{API}/admin/workspace-users", headers=_hdr(tok))
        assert r.status_code == 200

    def test_usage_report_demo(self):
        tok = _login(*DEMO)
        r = S.get(f"{API}/admin/usage-report?days=7", headers=_hdr(tok))
        assert r.status_code == 200

    def test_pricing_demo_forbidden(self):
        tok = _login(*DEMO)
        r = S.get(f"{API}/admin/pricing", headers=_hdr(tok))
        assert r.status_code == 403

    def test_pricing_platform_ok(self):
        tok = _login(*PLATFORM)
        r = S.get(f"{API}/admin/pricing", headers=_hdr(tok))
        assert r.status_code == 200


# =========== 3. TRIAL-EXPIRY INHERITANCE ===========

class TestTrialExpiry:
    def test_trial_expiry_blocks_member(self):
        asyncio.run(self._run())

    async def _run(self):
        cli = AsyncIOMotorClient(MONGO_URL)
        mongo = cli[DB_NAME]
        # Snapshot demo user
        demo_doc = await mongo.users.find_one({"email": DEMO[0]})
        assert demo_doc, "demo user missing"
        original_plan = demo_doc.get("plan")
        original_trial = demo_doc.get("trial_ends_at")
        try:
            # Set trial expired
            await mongo.users.update_one(
                {"id": demo_doc["id"]},
                {"$set": {"plan": "trial", "trial_ends_at": "2020-01-01T00:00:00+00:00"}}
            )

            # Find or create a private conversation for Budi with persona Rio
            budi_tok = _login(*BUDI)
            # Find Rio persona id
            personas = S.get(f"{API}/personas", headers=_hdr(budi_tok)).json()
            rio = next((p for p in personas if p["name"].lower() == "rio"), None)
            assert rio, "Rio persona not found in demo workspace"
            # Try to find existing conv or create
            convs = S.get(f"{API}/conversations", headers=_hdr(budi_tok)).json()
            cid = None
            for c in convs:
                if c.get("type") == "private" and rio["id"] in (c.get("persona_ids") or []):
                    cid = c["id"]
                    break
            if not cid:
                rc = S.post(f"{API}/conversations", headers=_hdr(budi_tok),
                            json={"type": "private", "persona_ids": [rio["id"]]})
                assert rc.status_code == 200, rc.text
                cid = rc.json()["id"]

            # Member send -> 402
            r = S.post(f"{API}/conversations/{cid}/send",
                       headers=_hdr(budi_tok), json={"content": "halo iter15 trial"})
            assert r.status_code == 402, f"budi expected 402 got {r.status_code}: {r.text}"
            assert "Masa percobaan" in r.text

            # Demo admin also -> 402
            demo_tok = _login(*DEMO)
            dconvs = S.get(f"{API}/conversations", headers=_hdr(demo_tok)).json()
            dcid = None
            for c in dconvs:
                if c.get("type") == "private" and rio["id"] in (c.get("persona_ids") or []):
                    dcid = c["id"]
                    break
            if not dcid:
                rc = S.post(f"{API}/conversations", headers=_hdr(demo_tok),
                            json={"type": "private", "persona_ids": [rio["id"]]})
                dcid = rc.json()["id"]
            r2 = S.post(f"{API}/conversations/{dcid}/send",
                        headers=_hdr(demo_tok), json={"content": "halo demo trial"})
            assert r2.status_code == 402, f"demo expected 402 got {r2.status_code}: {r2.text}"
            assert "Masa percobaan" in r2.text
        finally:
            # Restore
            unset = {}
            setd = {"plan": original_plan or "paid"}
            if original_trial is None:
                unset["trial_ends_at"] = ""
            else:
                setd["trial_ends_at"] = original_trial
            update = {"$set": setd}
            if unset:
                update["$unset"] = unset
            await mongo.users.update_one({"id": demo_doc["id"]}, update)

        # After restore - budi send ok
        budi_tok = _login(*BUDI)
        convs = S.get(f"{API}/conversations", headers=_hdr(budi_tok)).json()
        personas = S.get(f"{API}/personas", headers=_hdr(budi_tok)).json()
        rio = next((p for p in personas if p["name"].lower() == "rio"), None)
        cid = None
        for c in convs:
            if c.get("type") == "private" and rio["id"] in (c.get("persona_ids") or []):
                cid = c["id"]
                break
        r3 = S.post(f"{API}/conversations/{cid}/send",
                    headers=_hdr(budi_tok), json={"content": "halo iter15 restored"}, stream=True, timeout=30)
        assert r3.status_code == 200, f"after restore expected 200 got {r3.status_code}: {r3.text[:300] if hasattr(r3,'text') else ''}"
        r3.close()


# =========== 4. LOGIN THROTTLE (RUN LAST) ===========

class TestZZLoginThrottle:
    def test_login_bruteforce_lockout(self):
        # Use a fresh email so per-account counter starts at 0.
        # Per-IP counter may already have entries from other tests in this run
        # (login_allowed counts every login attempt per IP within 5min window),
        # so we only assert that: (a) wrong password returns 401 OR 429, and
        # (b) within 11 attempts we observe at least one 429 with the Indonesian message.
        email = f"bruteforce_{uuid.uuid4().hex[:6]}@x.ai"
        got_429 = False
        msg = ""
        for i in range(11):
            r = S.post(f"{API}/auth/login", json={"email": email, "password": "wrong"})
            assert r.status_code in (401, 429), f"attempt {i+1}: unexpected {r.status_code} {r.text}"
            if r.status_code == 429:
                got_429 = True
                msg = r.text
                break
        assert got_429, "expected 429 lockout within 11 attempts"
        assert "Terlalu banyak percobaan login" in msg
