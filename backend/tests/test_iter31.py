"""Iter31 — Oryntix: FX 18000, pricing engine, call cost report, URL knowledge, snapshot billing."""
import os
import copy
import time
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
DEMO = {"email": "demo@aivora.ai", "password": "demo123456"}
PADM = {"email": "admin@aivora.ai", "password": "Aivora!Admin2026"}


def _login(creds):
    r = requests.post(f"{BASE}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def demo_tok():
    return _login(DEMO)


@pytest.fixture(scope="module")
def padm_tok():
    return _login(PADM)


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------- packages (public) ----------
def test_packages_public_fx18k():
    r = requests.get(f"{BASE}/api/wallet/packages", timeout=20)
    assert r.status_code == 200
    pkgs = r.json()
    assert len(pkgs) == 5
    exp_price = {"starter": 69000, "basic": 115000, "plus": 220000, "pro": 524000, "ultimate": 999000}
    exp_cred = {"starter": 3000, "basic": 5000, "plus": 10000, "pro": 25000, "ultimate": 50000}
    for p in pkgs:
        assert p["price_idr"] == exp_price[p["id"]], f"{p['id']} price {p['price_idr']} != {exp_price[p['id']]}"
        assert p["credits"] == exp_cred[p["id"]], f"{p['id']} credits {p['credits']} != {exp_cred[p['id']]}"


# ---------- admin pricing GET ----------
def test_admin_pricing_get(padm_tok):
    r = requests.get(f"{BASE}/api/admin/pricing", headers=H(padm_tok), timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    p = body["pricing"]
    assert p["usd_to_idr"] == 18000.0
    assert (p.get("margin_overrides") or {}).get("call_bandwidth") == 50.0
    assert p["bandwidth_usd_per_gb"] == 0.5
    assert p["vision_usd"] == 0.006
    assert len(p["packages"]) == 5
    feats = body["features"]
    assert len(feats) == 9
    for f in feats:
        assert set(f.keys()) >= {"feature", "label", "provider_usd", "margin_pct", "credits"}
    rates = body["rates"]
    assert "vision" in rates and "bandwidth_per_mb" in rates
    assert rates["vision"] == 9


def test_admin_pricing_forbidden_for_workspace_admin(demo_tok):
    r = requests.get(f"{BASE}/api/admin/pricing", headers=H(demo_tok), timeout=20)
    assert r.status_code == 403


# ---------- preview (no save) ----------
def test_admin_pricing_preview(padm_tok):
    g = requests.get(f"{BASE}/api/admin/pricing", headers=H(padm_tok), timeout=20).json()
    body = dict(g["pricing"])
    # whitelist writable fields in PlatformPricingIn
    allowed = {"margin_pct", "tax_pct", "usd_to_idr", "idr_per_credit", "text_usd_per_1k_chars", "image_usd",
               "profile_usd", "stt_usd", "tts_usd", "provider_usd_per_min", "usd_per_credit",
               "rt_audio_in_usd_1m", "rt_audio_out_usd_1m", "rt_text_in_usd_1m", "rt_text_out_usd_1m",
               "rt_cached_in_usd_1m", "video_usd_per_sec", "vision_usd", "bandwidth_usd_per_gb",
               "margin_overrides", "package_margin_pct", "package_round_idr", "packages"}
    body = {k: v for k, v in body.items() if k in allowed}
    body["margin_overrides"] = {"text": 10}
    body["packages"] = copy.deepcopy(body["packages"])
    body["packages"][0]["usd"] = 4
    r = requests.post(f"{BASE}/api/admin/pricing/preview", json=body, headers=H(padm_tok), timeout=20)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["packages"][0]["usd"] == 4
    # text feature margin should be 10 in features table
    tf = next(f for f in out["features"] if f["feature"] == "text")
    assert tf["margin_pct"] == 10

    # Verify nothing saved
    g2 = requests.get(f"{BASE}/api/admin/pricing", headers=H(padm_tok), timeout=20).json()
    assert g2["pricing"]["packages"][0]["usd"] == g["pricing"]["packages"][0]["usd"]
    assert (g2["pricing"].get("margin_overrides") or {}) == (g["pricing"].get("margin_overrides") or {})


def test_admin_pricing_preview_invalid_override(padm_tok):
    g = requests.get(f"{BASE}/api/admin/pricing", headers=H(padm_tok), timeout=20).json()
    body = {k: v for k, v in g["pricing"].items() if k not in ("updated_at",)}
    body["margin_overrides"] = {"foo": 5}
    r = requests.post(f"{BASE}/api/admin/pricing/preview", json=body, headers=H(padm_tok), timeout=20)
    assert r.status_code == 422, r.text


def test_admin_pricing_preview_duplicate_pkg_ids(padm_tok):
    g = requests.get(f"{BASE}/api/admin/pricing", headers=H(padm_tok), timeout=20).json()
    body = {k: v for k, v in g["pricing"].items() if k not in ("updated_at",)}
    body["packages"] = copy.deepcopy(body["packages"])
    body["packages"][1]["id"] = body["packages"][0]["id"]  # dupe
    r = requests.post(f"{BASE}/api/admin/pricing/preview", json=body, headers=H(padm_tok), timeout=20)
    assert r.status_code == 422


# ---------- PUT roundtrip ----------
def test_admin_pricing_put_roundtrip(padm_tok):
    g = requests.get(f"{BASE}/api/admin/pricing", headers=H(padm_tok), timeout=20).json()
    allowed = {"margin_pct", "tax_pct", "usd_to_idr", "idr_per_credit", "text_usd_per_1k_chars", "image_usd",
               "profile_usd", "stt_usd", "tts_usd", "provider_usd_per_min", "usd_per_credit",
               "rt_audio_in_usd_1m", "rt_audio_out_usd_1m", "rt_text_in_usd_1m", "rt_text_out_usd_1m",
               "rt_cached_in_usd_1m", "video_usd_per_sec", "vision_usd", "bandwidth_usd_per_gb",
               "margin_overrides", "package_margin_pct", "package_round_idr", "packages"}
    body = {k: v for k, v in g["pricing"].items() if k in allowed}
    r = requests.put(f"{BASE}/api/admin/pricing", json=body, headers=H(padm_tok), timeout=20)
    assert r.status_code == 200, r.text
    g2 = requests.get(f"{BASE}/api/admin/pricing", headers=H(padm_tok), timeout=20).json()
    for k in allowed:
        if k == "packages":
            assert len(g2["pricing"][k]) == len(body[k])
            continue
        assert g2["pricing"].get(k) == body.get(k), f"mismatch on {k}"


# ---------- wallet /calls ----------
def test_wallet_calls_list(demo_tok):
    r = requests.get(f"{BASE}/api/wallet/calls?limit=5", headers=H(demo_tok), timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body and "has_more" in body and "next_before" in body
    for it in body["items"]:
        for k in ("id", "started_at", "seconds", "assistant_credits", "data_credits", "data_mb", "snapshot_count", "snapshot_credits"):
            assert k in it, f"missing {k}"
        assert "total" in it
        assert it["total"] == it["assistant_credits"] + it["data_credits"] + it["snapshot_credits"]
        # non-zero rule
        assert (it["assistant_credits"] or it["data_credits"] or it["snapshot_credits"] or it["seconds"])
    if body["has_more"] and body["next_before"]:
        r2 = requests.get(f"{BASE}/api/wallet/calls?limit=5&before={body['next_before']}", headers=H(demo_tok), timeout=20)
        assert r2.status_code == 200


# ---------- realtime vision rate ----------
def test_vision_rate(demo_tok):
    r = requests.get(f"{BASE}/api/realtime/vision-rate", headers=H(demo_tok), timeout=20)
    assert r.status_code == 200
    assert r.json().get("credits") == 9


# ---------- knowledge from URL ----------
@pytest.fixture(scope="module")
def demo_persona(demo_tok):
    r = requests.get(f"{BASE}/api/personas", headers=H(demo_tok), timeout=20)
    assert r.status_code == 200
    items = r.json()
    assert items, "no personas for demo"
    return items[0]["id"]


def test_knowledge_from_url_full_flow(demo_tok, demo_persona):
    url = "https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API"
    r = requests.post(f"{BASE}/api/personas/{demo_persona}/knowledge",
                      json={"url": url}, headers=H(demo_tok), timeout=60)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["source"] == "url"
    assert doc["url"] == url
    assert doc["title"], "title should be set from page"
    assert doc["chunk_count"] > 0
    kid = doc["id"]

    # refresh
    r2 = requests.post(f"{BASE}/api/personas/{demo_persona}/knowledge/{kid}/refresh",
                       headers=H(demo_tok), timeout=60)
    assert r2.status_code == 200, r2.text
    doc2 = r2.json()
    assert doc2["chunk_count"] > 0

    # cleanup
    rd = requests.delete(f"{BASE}/api/personas/{demo_persona}/knowledge/{kid}", headers=H(demo_tok), timeout=20)
    assert rd.status_code == 200


def test_knowledge_invalid_url(demo_tok, demo_persona):
    r = requests.post(f"{BASE}/api/personas/{demo_persona}/knowledge",
                      json={"url": "ftp://x"}, headers=H(demo_tok), timeout=20)
    assert r.status_code == 400


# ---------- realtime call + snapshot ----------
GROUP_CID = "90435108-e7d4-429c-9daa-f488d70035b7"


def test_realtime_snapshot_billing(demo_tok):
    # Get wallet before
    w0 = requests.get(f"{BASE}/api/wallet", headers=H(demo_tok), timeout=20).json()
    cons0 = w0["consumed"]

    # presence
    pr = requests.post(f"{BASE}/api/conversations/{GROUP_CID}/call/presence",
                      json={"bytes_delta": 0}, headers=H(demo_tok), timeout=20)
    if pr.status_code == 404:
        pytest.skip(f"demo doesn't have access to group {GROUP_CID}")
    assert pr.status_code == 200, pr.text
    presence = pr.json()
    assert "call_session_id" in presence
    assert "is_host" in presence
    csid = presence["call_session_id"]

    # start realtime call
    rc = requests.post(f"{BASE}/api/realtime/calls",
                       json={"conversation_id": GROUP_CID, "call_session_id": csid},
                       headers=H(demo_tok), timeout=30)
    if rc.status_code == 503:
        pytest.skip("OPENAI_API_KEY not configured on backend (503)")
    assert rc.status_code == 200, rc.text
    call = rc.json()
    call_id = call.get("call_id") or call.get("id")
    assert call_id, f"no call_id in {call}"

    try:
        # snapshot
        sn = requests.post(f"{BASE}/api/realtime/calls/{call_id}/snapshot",
                           headers=H(demo_tok), timeout=20)
        assert sn.status_code == 200, sn.text
        snj = sn.json()
        assert snj.get("credits") == 9
        assert snj.get("snapshots") == 1

        # wallet after
        time.sleep(0.5)
        w1 = requests.get(f"{BASE}/api/wallet", headers=H(demo_tok), timeout=20).json()
        assert w1["consumed"] >= cons0 + 9
        feats = {b["feature"] for b in w1.get("breakdown") or []}
        assert "screen_snapshot" in feats, f"screen_snapshot not in breakdown: {feats}"

        # calls report shows this session
        cr = requests.get(f"{BASE}/api/wallet/calls?limit=20", headers=H(demo_tok), timeout=20).json()
        row = next((r for r in cr["items"] if r["id"] == csid), None)
        assert row is not None, f"session {csid} not in call report"
        assert row["snapshot_count"] >= 1
        assert row["snapshot_credits"] >= 9
    finally:
        # end & leave
        requests.post(f"{BASE}/api/realtime/calls/{call_id}/end",
                      json={"elapsed_seconds": 0}, headers=H(demo_tok), timeout=20)
        requests.post(f"{BASE}/api/conversations/{GROUP_CID}/call/leave",
                      headers=H(demo_tok), timeout=20)
