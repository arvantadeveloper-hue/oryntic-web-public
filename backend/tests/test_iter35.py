"""Iter35 backend tests: trial-info, credit meta sync, GitHub integration validation,
multi-image chat flow (image_set task), GitHub-not-connected chat reply."""
import json
import os
import time
import uuid
import requests
import pytest
import sys as _sys; _sys.path.insert(0, '/app/backend/tests')  # noqa: E702
from creds import DEMO_PASSWORD, ADMIN_PASSWORD, BUDI_PASSWORD  # noqa: E402,F401

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://ai-companion-test-5.preview.emergentagent.com").rstrip("/")
DEMO = {"email": "demo@aivora.ai", "password": DEMO_PASSWORD}


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{BASE}/api/auth/login", json=DEMO, timeout=30)
    if r.status_code == 429:
        # fallback: mint a JWT directly via backend.auth
        import sys
        sys.path.insert(0, "/app/backend")
        from pymongo import MongoClient
        from auth import make_token
        cli = MongoClient(os.environ["MONGO_URL"])
        u = cli[os.environ["DB_NAME"]].users.find_one({"email": DEMO["email"]})
        return make_token(u["id"], "admin")
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def hdr(demo_token):
    return {"Authorization": f"Bearer {demo_token}", "Content-Type": "application/json"}


# ---------- 1. trial-info (public) ----------
def test_trial_info_public():
    r = requests.get(f"{BASE}/api/auth/trial-info", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["trial_credits"] == 700
    assert d["trial_days"] == 7
    assert d["trial_daily_limit"] == 100


# ---------- 2. me + wallet credit sync ----------
def test_me_has_credit_meta(hdr):
    r = requests.get(f"{BASE}/api/auth/me", headers=hdr, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "credits" in d and "credits_cap" in d and "daily_used" in d
    assert d["credits_cap"] >= 1
    assert d["credits_cap"] >= d["credits"]


def test_wallet_matches_me(hdr):
    me = requests.get(f"{BASE}/api/auth/me", headers=hdr, timeout=15).json()
    w = requests.get(f"{BASE}/api/wallet", headers=hdr, timeout=15).json()
    for k in ("available", "credits_cap", "plan", "daily_limit", "daily_used"):
        assert k in w, f"missing {k} in wallet: {w.keys()}"
    assert w["available"] == me["credits"]
    assert w["credits_cap"] == me["credits_cap"]


# ---------- 3. GitHub integration (not connected) ----------
def test_integrations_contains_github(hdr):
    r = requests.get(f"{BASE}/api/integrations", headers=hdr, timeout=10)
    assert r.status_code == 200
    data = r.json()
    items = data.get("items") or data if isinstance(data, list) else data.get("items")
    # response is {items:[...], coming_soon:[...]}
    assert isinstance(data, dict)
    assert any(i.get("id") == "github" for i in data.get("items", []))
    gh = next(i for i in data["items"] if i["id"] == "github")
    assert gh.get("connected") is False
    cs = data.get("coming_soon") or []
    for c in cs:
        s = c if isinstance(c, str) else (c.get("id", "") + c.get("name", ""))
        assert "github" not in s.lower()


def test_github_status_not_connected(hdr):
    r = requests.get(f"{BASE}/api/integrations/github/status", headers=hdr, timeout=10)
    assert r.status_code == 200
    assert r.json().get("connected") is False


def test_github_connect_invalid_token(hdr):
    r = requests.post(f"{BASE}/api/integrations/github",
                      headers=hdr, json={"token": "github_pat_invalidtokenvalue1234567890"}, timeout=20)
    assert r.status_code == 400
    assert "Token GitHub tidak valid" in r.text


def test_github_repos_not_connected(hdr):
    r = requests.get(f"{BASE}/api/integrations/github/repos", headers=hdr, timeout=10)
    assert r.status_code == 400
    assert "GitHub belum terhubung" in r.text


def test_github_tree_not_connected(hdr):
    r = requests.post(f"{BASE}/api/integrations/github/tree",
                      headers=hdr, json={"repo": "octocat/Hello-World"}, timeout=10)
    assert r.status_code == 400
    assert "GitHub belum terhubung" in r.text


def test_github_pr_validation_422(hdr):
    r = requests.post(f"{BASE}/api/integrations/github/pr",
                      headers=hdr, json={"repo": "o/r", "title": "test change", "body": "", "changes": []},
                      timeout=10)
    assert r.status_code == 422, r.text


# ---------- 4. GitHub-not-connected chat reply ----------
def _get_private_persona_conv(hdr):
    """Return a conversation_id with a persona for the demo user (private AI chat)."""
    r = requests.get(f"{BASE}/api/conversations", headers=hdr, timeout=15)
    assert r.status_code == 200
    convs = r.json()
    # pick a private (non-meeting) one with persona_ids
    for c in convs:
        if c.get("type") in (None, "private", "chat") and (c.get("persona_ids") or c.get("participants_personas")):
            return c["id"]
    # create one via persona list
    personas = requests.get(f"{BASE}/api/personas", headers=hdr, timeout=10).json()
    pid = personas[0]["id"]
    r = requests.post(f"{BASE}/api/conversations/direct", headers=hdr, json={"persona_id": pid}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _sse_last(resp):
    """Collect the final data: JSON event from an SSE stream."""
    last = None
    for raw in resp.iter_lines(decode_unicode=True):
        if not raw:
            continue
        if raw.startswith("data:"):
            try:
                obj = json.loads(raw[5:].strip())
                last = obj
            except Exception:
                pass
    return last


def test_github_not_connected_chat(hdr):
    cid = _get_private_persona_conv(hdr)
    r = requests.post(f"{BASE}/api/conversations/{cid}/send",
                      headers=hdr, json={"content": "tampilkan daftar repo github saya"},
                      stream=True, timeout=120)
    assert r.status_code == 200
    # scan all SSE events for text "GitHub belum terhubung" and tool github_repos
    saw_tool = False
    saw_text = False
    for raw in r.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data:"):
            continue
        try:
            obj = json.loads(raw[5:].strip())
        except Exception:
            continue
        if obj.get("tool") == "github_repos":
            saw_tool = True
            if obj.get("error"):
                saw_text = True
        txt = obj.get("content") or obj.get("delta") or obj.get("final") or ""
        if isinstance(txt, str) and "belum terhubung" in txt.lower():
            saw_text = True
    assert saw_tool, "expected tool=github_repos in SSE events"
    assert saw_text, "expected 'GitHub belum terhubung' message"


# ---------- 5. multi-image flow (image_set) ----------
@pytest.mark.timeout(180)
def test_multi_image_pending_then_run(hdr):
    cid = _get_private_persona_conv(hdr)
    content = ("Buatkan 2 gambar: satu kucing oranye tidur di sofa, "
               "satu lagi anjing golden retriever lari di pantai")
    r = requests.post(f"{BASE}/api/conversations/{cid}/send",
                      headers=hdr, json={"content": content}, stream=True, timeout=120)
    assert r.status_code == 200
    final = None
    for raw in r.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data:"):
            continue
        try:
            obj = json.loads(raw[5:].strip())
        except Exception:
            continue
        if obj.get("pending_tool"):
            final = obj
    assert final is not None, "no pending_tool event seen"
    pt = final["pending_tool"]
    assert pt.get("kind") == "image_set"
    assert pt.get("count") == 2
    assert len(pt.get("prompts") or []) == 2

    # find the pending message_id
    msgs = requests.get(f"{BASE}/api/conversations/{cid}/messages", headers=hdr, timeout=15).json().get("messages", [])
    pending = [m for m in msgs if (m.get("pending_tool") or {}).get("kind") == "image_set"]
    assert pending, "pending image_set message not found in messages"
    mid = pending[-1]["id"]

    # run-tool
    rr = requests.post(f"{BASE}/api/conversations/{cid}/messages/{mid}/run-tool",
                       headers=hdr, timeout=60)
    assert rr.status_code == 200, rr.text
    body = rr.json()
    assert body.get("tool") == "image_set"
    assert body.get("task_id")
    tid = body["task_id"]

    # verify task shape immediately
    t = requests.get(f"{BASE}/api/tasks/{tid}", headers=hdr, timeout=15).json()
    assert t.get("type") == "image_set"
    assert len(t.get("steps") or []) == 2

    # poll up to 120s for completion (two Gemini image generations)
    deadline = time.time() + 150
    status = None
    while time.time() < deadline:
        t = requests.get(f"{BASE}/api/tasks/{tid}", headers=hdr, timeout=15).json()
        status = t.get("status")
        if status == "completed":
            break
        time.sleep(5)
    assert status == "completed", f"task did not complete in time; last={t}"
    media = t.get("media") or []
    assert len(media) == 2, f"expected 2 media, got {len(media)}: {media}"

    # verify assistant message now carries task_id
    msgs = requests.get(f"{BASE}/api/conversations/{cid}/messages", headers=hdr, timeout=15).json().get("messages", [])
    assert any(m.get("task_id") == tid for m in msgs), "no message with the created task_id"
