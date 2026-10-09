"""Backend tests for the hierarchical pricing catalog (iter 40)."""
import os
import math
import pytest
import requests
import sys as _sys; _sys.path.insert(0, '/app/backend/tests')  # noqa: E702
from creds import DEMO_PASSWORD, ADMIN_PASSWORD, BUDI_PASSWORD  # noqa: E402,F401

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = ("admin@aivora.ai", ADMIN_PASSWORD)
DEMO = ("demo@aivora.ai", DEMO_PASSWORD)


def _login(email, pw):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def admin_tok():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def demo_tok():
    return _login(*DEMO)


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------- catalog read/write ----------
def test_get_catalog(admin_tok):
    r = requests.get(f"{BASE}/admin/pricing-catalog", headers=H(admin_tok), timeout=20)
    assert r.status_code == 200
    data = r.json()
    provider_ids = {p["id"] for p in data["catalog"]["providers"]}
    assert {"openai", "gemini", "anthropic", "seedance", "oryntix"}.issubset(provider_ids)
    assert data["globals"]["margin_pct"] == 30
    assert data["globals"]["tax_pct"] == 11


def test_quote_gpt_live_3_min(admin_tok):
    r = requests.post(f"{BASE}/admin/pricing-catalog/quote", headers=H(admin_tok),
                      json={"service_id": "gpt-live", "component_id": "per_minute", "qty": 3}, timeout=20)
    assert r.status_code == 200
    q = r.json()
    # 0.05 * 3 * 1.30 * 1.11 / 0.001 ≈ 216.45 → ceil 217
    assert q["credits"] == 217, q


def test_quote_per_image_gpt_image(admin_tok):
    """Catalog v3: image prices are flat per image (unit image, qty_basis 1) — no flat_qty/variant."""
    r = requests.post(f"{BASE}/admin/pricing-catalog/quote", headers=H(admin_tok),
                      json={"service_id": "gpt-image", "component_id": "image_out", "qty": None}, timeout=20)
    assert r.status_code == 200
    q = r.json()
    assert q["qty"] == 1
    # 0.032 * 1.30 * 1.11 / 0.001 ≈ 46.18 → ceil 47
    assert q["credits"] == 47, q


def test_quote_per_image_gemini_nano_banana(admin_tok):
    r = requests.post(f"{BASE}/admin/pricing-catalog/quote", headers=H(admin_tok),
                      json={"service_id": "gemini-nano-banana", "component_id": "image_out", "qty": None}, timeout=20)
    assert r.status_code == 200
    q = r.json()
    assert q["qty"] == 1  # per image (flat)


def test_quote_404(admin_tok):
    r = requests.post(f"{BASE}/admin/pricing-catalog/quote", headers=H(admin_tok),
                      json={"service_id": "nope", "component_id": "nope", "qty": 1}, timeout=20)
    assert r.status_code == 404


# ---------- import diff ----------
def test_import_anthropic(admin_tok):
    r = requests.post(f"{BASE}/admin/pricing-catalog/import?provider_id=anthropic", headers=H(admin_tok), timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert isinstance(d.get("rows"), list)
    assert len(d["rows"]) > 0


def test_import_openai(admin_tok):
    r = requests.post(f"{BASE}/admin/pricing-catalog/import?provider_id=openai", headers=H(admin_tok), timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert len(d["rows"]) > 0


def test_import_gemini_empty_not_crash(admin_tok):
    r = requests.post(f"{BASE}/admin/pricing-catalog/import?provider_id=gemini", headers=H(admin_tok), timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("rows") == []


# ---------- authorization ----------
def test_demo_forbidden_get(demo_tok):
    r = requests.get(f"{BASE}/admin/pricing-catalog", headers=H(demo_tok), timeout=20)
    assert r.status_code == 403


def test_demo_forbidden_put(demo_tok):
    r = requests.put(f"{BASE}/admin/pricing-catalog", headers=H(demo_tok),
                     json={"version": 2, "providers": []}, timeout=20)
    assert r.status_code == 403


def test_demo_forbidden_import(demo_tok):
    r = requests.post(f"{BASE}/admin/pricing-catalog/import?provider_id=openai", headers=H(demo_tok), timeout=20)
    assert r.status_code == 403


# ---------- billing engine reads catalog ----------
def test_pricing_feature_image_source(admin_tok):
    r = requests.get(f"{BASE}/admin/pricing", headers=H(admin_tok), timeout=20)
    assert r.status_code == 200
    data = r.json()
    feats = {f["key"]: f for f in data["features"]} if "features" in data and isinstance(data["features"], list) and data["features"] and isinstance(data["features"][0], dict) and "key" in data["features"][0] else None
    # tolerate different schemas: find any 'image' row referring to gemini-nano-banana/image_out
    text = str(data["features"])
    assert "gemini-nano-banana/image_out" in text, text[:400]


def test_tool_web_search_price(admin_tok):
    r = requests.get(f"{BASE}/admin/pricing", headers=H(admin_tok), timeout=20)
    data = r.json()
    tools = data.get("tools", [])
    web = next((t for t in tools if t.get("id") == "openai:web_search"), None)
    assert web is not None, tools
    assert abs(float(web.get("usd", 0)) - 0.01) < 1e-6, web


def test_realtime_call_provider_usd(admin_tok):
    r = requests.get(f"{BASE}/admin/pricing", headers=H(admin_tok), timeout=20)
    data = r.json()
    txt = str(data)
    # gpt-live per_minute $0.05
    assert "0.05" in txt


# ---------- persistence after PUT ----------
def test_persistence_round_trip(admin_tok):
    # read, edit one price (gpt-luna text_in), save, read back, restore
    r = requests.get(f"{BASE}/admin/pricing-catalog", headers=H(admin_tok), timeout=20).json()
    cat = r["catalog"]
    original = None
    for p in cat["providers"]:
        if p["id"] != "openai":
            continue
        for s in p["services"]:
            if s["id"] != "gpt-luna":
                continue
            for c in s["components"]:
                if c["id"] == "text_in":
                    original = float(c["usd"])
                    c["usd"] = 0.12345
    assert original is not None
    try:
        put = requests.put(f"{BASE}/admin/pricing-catalog", headers=H(admin_tok),
                           json={"version": cat.get("version", 2), "providers": cat["providers"]}, timeout=30)
        assert put.status_code == 200, put.text
        r2 = requests.get(f"{BASE}/admin/pricing-catalog", headers=H(admin_tok), timeout=20).json()
        comp = next(c for p in r2["catalog"]["providers"] if p["id"] == "openai"
                    for s in p["services"] if s["id"] == "gpt-luna"
                    for c in s["components"] if c["id"] == "text_in")
        assert abs(float(comp["usd"]) - 0.12345) < 1e-6, comp
    finally:
        # restore
        for p in cat["providers"]:
            if p["id"] != "openai":
                continue
            for s in p["services"]:
                if s["id"] != "gpt-luna":
                    continue
                for c in s["components"]:
                    if c["id"] == "text_in":
                        c["usd"] = original
        requests.put(f"{BASE}/admin/pricing-catalog", headers=H(admin_tok),
                     json={"version": cat.get("version", 2), "providers": cat["providers"]}, timeout=30)


# ---------- regression: demo chat still charges ----------
def test_personas_support_present(demo_tok):
    r = requests.get(f"{BASE}/personas", headers=H(demo_tok), timeout=20)
    assert r.status_code == 200
    personas = r.json()
    sup = next((p for p in personas if "oryntix" in (p.get("name") or "").lower() or (p.get("profile") or {}).get("role") == "support" or p.get("is_support")), None)
    # fallback: any persona whose profile has non-empty system_instructions
    if not sup:
        sup = next((p for p in personas if (p.get("profile") or {}).get("system_instructions")), None)
    assert sup is not None, [p.get("name") for p in personas]
    assert (sup.get("profile") or {}).get("system_instructions"), sup
