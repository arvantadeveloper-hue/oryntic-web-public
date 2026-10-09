"""Iteration 43 — pricing catalog as single source of provider prices, read-only realtime admin,
language rule (uses conversation_language / fallback app_language), and GitHub/GitLab direct commit."""
import copy
import json
import os
import re
import time

import pytest
import requests
from pymongo import MongoClient

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL must be set"

ADMIN_EMAIL = "admin@aivora.ai"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or "Aivora!Admin2026"
DEMO_EMAIL = "demo@aivora.ai"
DEMO_PASSWORD = "demo123456"

MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "test_database"

LEGACY_PRICING_KEYS = (
    "text_usd_per_1k_chars", "image_usd", "stt_usd", "tts_usd",
    "provider_usd_per_min", "model_prices", "tool_prices", "realtime_models",
    "rt_audio_in_usd_1m", "video_usd_per_sec",
)


def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    r.raise_for_status()
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def demo_token():
    return _login(DEMO_EMAIL, DEMO_PASSWORD)


@pytest.fixture(scope="module")
def mongo():
    cli = MongoClient(MONGO_URL)
    yield cli[DB_NAME]
    cli.close()


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# =========================================================================
# 1) /api/admin/pricing — legacy keys gone; rates match catalog
# =========================================================================
class TestAdminPricing:
    def test_pricing_shape_and_rates(self, admin_token):
        r = requests.get(f"{BASE}/api/admin/pricing", headers=H(admin_token), timeout=15)
        assert r.status_code == 200
        body = r.json()
        p = body["pricing"]
        for k in LEGACY_PRICING_KEYS:
            assert k not in p, f"legacy key still present: {k}"
        for k in ("margin_pct", "tax_pct", "usd_per_credit", "usd_to_idr", "chars_per_token", "video_res_480_mult", "packages"):
            assert k in p, f"missing expected key: {k}"
        rates = body["rates"]
        assert rates["image"] == 57, rates
        assert rates["realtime_per_min"] == 73, rates
        assert rates["text_per_1k"] == 9.74, rates
        rm = body.get("realtime_models") or []
        assert len(rm) == 1 and rm[0]["id"] == "gpt-live-1", rm
        assert abs(float(rm[0]["per_min_usd"]) - 0.05) < 1e-9
        assert int(rm[0]["credits_per_min"]) == 73
        tools = {t["id"]: t for t in body.get("tools") or []}
        assert abs(float(tools["openai:image_generation"]["usd"]) - 0.032) < 1e-9
        assert int(tools["openai:image_generation"]["credits"]) == 47
        assert abs(float(tools["openai:web_search"]["usd"]) - 0.01) < 1e-9
        assert int(tools["openai:web_search"]["credits"]) == 15
        features = {f["feature"]: f for f in body.get("features") or []}
        img = features["image"]
        assert img["source"] == "gemini-nano-banana/image_out"
        assert abs(float(img["provider_usd"]) - 0.039) < 1e-9
        assert int(img["credits"]) == 57
        txt = features["text"]
        assert txt["source"] == "text-default/per_1k_chars"
        assert abs(float(txt["provider_usd"]) - 0.00675) < 1e-9

    def test_put_pricing_margin_change_affects_image_rate(self, admin_token):
        g = requests.get(f"{BASE}/api/admin/pricing", headers=H(admin_token), timeout=15).json()
        orig = copy.deepcopy(g["pricing"])

        body = copy.deepcopy(orig)
        body["margin_pct"] = 40
        r = requests.put(f"{BASE}/api/admin/pricing", headers=H(admin_token), json=body, timeout=15)
        assert r.status_code == 200
        rr = r.json()
        assert rr["rates"]["image"] == 61, rr["rates"]

        body["margin_pct"] = 30
        r = requests.put(f"{BASE}/api/admin/pricing", headers=H(admin_token), json=body, timeout=15)
        assert r.status_code == 200
        assert r.json()["rates"]["image"] == 57

    def test_put_ignores_legacy_keys(self, admin_token):
        g = requests.get(f"{BASE}/api/admin/pricing", headers=H(admin_token), timeout=15).json()
        body = copy.deepcopy(g["pricing"])
        body["image_usd"] = 5
        body["text_usd_per_1k_chars"] = 99
        body["model_prices"] = {"foo": 1}
        r = requests.put(f"{BASE}/api/admin/pricing", headers=H(admin_token), json=body, timeout=15)
        assert r.status_code == 200
        p = r.json()["pricing"]
        for k in LEGACY_PRICING_KEYS:
            assert k not in p, f"legacy key leaked back: {k}"


# =========================================================================
# 2) /api/admin/pricing-catalog — v3, no flat_qty, correct components & quote
# =========================================================================
class TestPricingCatalog:
    def test_catalog_shape(self, admin_token):
        r = requests.get(f"{BASE}/api/admin/pricing-catalog", headers=H(admin_token), timeout=15)
        assert r.status_code == 200
        cat = r.json()["catalog"]
        assert cat["version"] == 3
        # recursively assert no flat_qty keys
        for p in cat["providers"]:
            for s in p["services"]:
                for c in s["components"]:
                    assert "flat_qty" not in c, f"flat_qty in {p['id']}/{s['id']}/{c['id']}"

        def find(sid, cid):
            for p in cat["providers"]:
                for s in p["services"]:
                    if s["id"] == sid:
                        for c in s["components"]:
                            if c["id"] == cid:
                                return c
            return None

        c = find("gpt-image", "image_out")
        assert c and c["unit"] == "image" and c["qty_basis"] == 1 and abs(float(c["usd"]) - 0.032) < 1e-9
        c = find("gpt-image", "image_in")
        assert c and c["unit"] == "image" and abs(float(c["usd"]) - 0.0084) < 1e-9
        c = find("gemini-nano-banana", "image_out")
        assert c and c["unit"] == "image" and abs(float(c["usd"]) - 0.039) < 1e-9
        c = find("openai:image_generation", "per_image")
        assert c and c["unit"] == "image" and abs(float(c["usd"]) - 0.032) < 1e-9
        c = find("text-default", "per_1k_chars")
        assert c and c["unit"] == "k_chars" and c["qty_basis"] == 1 and abs(float(c["usd"]) - 0.00675) < 1e-9
        c = find("gpt-live", "per_minute")
        assert c and abs(float(c["usd"]) - 0.05) < 1e-9

    def test_quote(self, admin_token):
        r = requests.post(f"{BASE}/api/admin/pricing-catalog/quote", headers=H(admin_token),
                          json={"service_id": "gpt-image", "component_id": "image_out", "qty": 1}, timeout=15)
        assert r.status_code == 200
        q = r.json()
        assert abs(float(q["base_usd"]) - 0.032) < 1e-9
        assert int(q["credits"]) == 47

        r = requests.post(f"{BASE}/api/admin/pricing-catalog/quote", headers=H(admin_token),
                          json={"service_id": "gpt-image", "component_id": "image_out", "qty": None}, timeout=15)
        assert r.status_code == 200
        q = r.json()
        assert float(q["qty"]) == 1.0
        assert abs(float(q["base_usd"]) - 0.032) < 1e-9

        r = requests.post(f"{BASE}/api/admin/pricing-catalog/quote", headers=H(admin_token),
                          json={"service_id": "gemini-nano-banana", "component_id": "image_out", "qty": 3}, timeout=15)
        assert r.status_code == 200
        assert abs(float(r.json()["base_usd"]) - 0.117) < 1e-6

    def test_catalog_edit_propagates_to_billing(self, admin_token):
        g = requests.get(f"{BASE}/api/admin/pricing-catalog", headers=H(admin_token), timeout=15).json()
        cat = copy.deepcopy(g["catalog"])
        # mutate gemini-nano-banana/image_out usd to 0.05
        for p in cat["providers"]:
            for s in p["services"]:
                if s["id"] == "gemini-nano-banana":
                    for c in s["components"]:
                        if c["id"] == "image_out":
                            c["usd"] = 0.05
        try:
            r = requests.put(f"{BASE}/api/admin/pricing-catalog", headers=H(admin_token), json=cat, timeout=15)
            assert r.status_code == 200
            # Verify billing engine updated
            rates = requests.get(f"{BASE}/api/admin/pricing", headers=H(admin_token), timeout=15).json()["rates"]
            assert rates["image"] == 73, rates
        finally:
            # Restore
            for p in cat["providers"]:
                for s in p["services"]:
                    if s["id"] == "gemini-nano-banana":
                        for c in s["components"]:
                            if c["id"] == "image_out":
                                c["usd"] = 0.039
            r = requests.put(f"{BASE}/api/admin/pricing-catalog", headers=H(admin_token), json=cat, timeout=15)
            assert r.status_code == 200
            rates = requests.get(f"{BASE}/api/admin/pricing", headers=H(admin_token), timeout=15).json()["rates"]
            assert rates["image"] == 57


# =========================================================================
# 3) /api/admin/realtime-pricing read-only + /api/realtime/status
# =========================================================================
class TestRealtimePricing:
    def test_realtime_pricing_get(self, admin_token):
        r = requests.get(f"{BASE}/api/admin/realtime-pricing", headers=H(admin_token), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["model"] == "gpt-live-1"
        assert abs(float(d["provider_usd_per_min"]) - 0.05) < 1e-9
        assert float(d["margin_pct"]) == 30.0
        assert float(d["tax_pct"]) == 11.0
        assert int(d["credits_per_min"]) == 73
        assert d["catalog_path"] == "openai/gpt-live/per_minute"

    def test_realtime_pricing_put_removed(self, admin_token):
        r = requests.put(f"{BASE}/api/admin/realtime-pricing", headers=H(admin_token), json={"provider_usd_per_min": 0.1}, timeout=15)
        assert r.status_code == 405, r.status_code

    def test_realtime_status_demo(self, demo_token):
        r = requests.get(f"{BASE}/api/realtime/status", headers=H(demo_token), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["model"] == "gpt-live-1"
        assert int(d["credits_per_min"]) == 73


# =========================================================================
# 4) Language rule — assistant must answer in user settings language
# =========================================================================
def _sse_final(resp):
    """Collect the final SSE event's content from a streamed POST response."""
    final_content = None
    buf = b""
    for chunk in resp.iter_content(chunk_size=1024):
        if not chunk:
            continue
        buf += chunk
        while b"\n\n" in buf:
            evt, buf = buf.split(b"\n\n", 1)
            for line in evt.decode("utf-8", errors="ignore").splitlines():
                if line.startswith("data: "):
                    data = line[6:].strip()
                    if data == "[DONE]":
                        return final_content
                    try:
                        obj = json.loads(data)
                    except Exception:
                        continue
                    if obj.get("final"):
                        final_content = obj.get("content") or final_content
                    elif obj.get("content") and not obj.get("delta"):
                        final_content = obj.get("content") or final_content
    return final_content


class TestLanguageRule:
    @pytest.fixture(scope="class")
    def support_cid(self, demo_token):
        r = requests.post(f"{BASE}/api/conversations/direct", headers=H(demo_token),
                          json={"persona_id": "oryntix-support"}, timeout=15)
        assert r.status_code in (200, 201), (r.status_code, r.text)
        return r.json()["id"]

    def _send(self, demo_token, cid, text):
        with requests.post(f"{BASE}/api/conversations/{cid}/send", headers=H(demo_token),
                           json={"content": text}, stream=True, timeout=90) as resp:
            assert resp.status_code == 200, (resp.status_code, resp.text[:300])
            return _sse_final(resp)

    def test_english_output_when_conv_lang_en(self, mongo, demo_token, support_cid):
        mongo.users.update_one({"email": DEMO_EMAIL}, {"$set": {"settings.conversation_language": "en", "settings.app_language": "id"}})
        time.sleep(35)  # pricing cache + language cache
        out = self._send(demo_token, support_cid, "Halo, bagaimana cara membeli kredit di Oryntix? Jawab singkat.")
        assert out, "no final content"
        low = out.lower()
        # expect English (has 'credit' not 'kredit')
        assert "kredit" not in low, f"should be English, got: {out[:400]}"
        assert any(w in low for w in ("credit", "package", "go to", "buy", "purchase")), f"no English markers: {out[:400]}"

    def test_indonesian_output_when_conv_lang_id(self, mongo, demo_token, support_cid):
        mongo.users.update_one({"email": DEMO_EMAIL}, {"$set": {"settings.conversation_language": "id"}})
        time.sleep(35)
        out = self._send(demo_token, support_cid, "How do I buy credits? Short answer.")
        assert out
        low = out.lower()
        assert "kredit" in low or "paket" in low or "anda" in low, f"should be Indonesian, got: {out[:400]}"

    def test_app_language_fallback(self, mongo, demo_token, support_cid):
        mongo.users.update_one({"email": DEMO_EMAIL}, {"$unset": {"settings.conversation_language": ""}, "$set": {"settings.app_language": "en"}})
        time.sleep(35)
        out = self._send(demo_token, support_cid, "Halo, bagaimana cara membeli kredit? Jawab singkat.")
        assert out
        low = out.lower()
        assert "kredit" not in low, f"app_language en should give English, got: {out[:400]}"
        # restore
        mongo.users.update_one({"email": DEMO_EMAIL}, {"$set": {"settings.conversation_language": "id", "settings.app_language": "id"}})


# =========================================================================
# 5) GitHub/GitLab direct commit endpoints
# =========================================================================
class TestCommitEndpoints:
    def test_github_commit_not_connected(self, demo_token):
        r = requests.post(f"{BASE}/api/integrations/github/commit", headers=H(demo_token),
                          json={"repo": "a/b", "title": "test commit", "changes": [{"path": "x", "content": "y"}], "branch": "dev"},
                          timeout=15)
        assert r.status_code == 400, (r.status_code, r.text)
        assert "GitHub" in r.text and ("belum terhubung" in r.text.lower() or "belum terhubung" in r.text)

    def test_gitlab_commit_not_connected(self, demo_token):
        r = requests.post(f"{BASE}/api/integrations/gitlab/commit", headers=H(demo_token),
                          json={"repo": "a/b", "title": "test commit", "changes": [{"path": "x", "content": "y"}], "branch": "dev"},
                          timeout=15)
        assert r.status_code == 400, (r.status_code, r.text)
        assert "GitLab" in r.text and "belum terhubung" in r.text.lower()

    def test_github_commit_missing_branch_422(self, demo_token):
        r = requests.post(f"{BASE}/api/integrations/github/commit", headers=H(demo_token),
                          json={"repo": "a/b", "title": "test commit", "changes": [{"path": "x", "content": "y"}]},
                          timeout=15)
        assert r.status_code == 422, (r.status_code, r.text)


# =========================================================================
# 6) Planner recognises direct commit vs PR
# =========================================================================
class TestPlanner:
    def test_plan_tool_commit_vs_pr(self):
        import subprocess
        script = (
            "import asyncio, json, sys\n"
            "sys.path.insert(0, '/app/backend')\n"
            "from tools import plan_tool\n"
            "a = asyncio.run(plan_tool('Perbaiki typo di README.md repo budi/app lalu commit langsung ke branch dev, jangan bikin PR', ''))\n"
            "b = asyncio.run(plan_tool('Ubah fungsi login di repo budi/app dan buat pull request', ''))\n"
            "print(json.dumps({'a': a, 'b': b}))\n"
        )
        out = subprocess.run(["python", "-c", script], capture_output=True, text=True, timeout=120, cwd="/app/backend")
        assert out.returncode == 0, (out.stdout, out.stderr)
        last = out.stdout.strip().splitlines()[-1]
        data = json.loads(last)
        a, b = data["a"], data["b"]
        assert a.get("tool") == "github_commit", a
        assert (a.get("branch") or "").lower() == "dev"
        assert "budi/app" in (a.get("repo") or "")
        assert b.get("tool") == "github_pr", b
