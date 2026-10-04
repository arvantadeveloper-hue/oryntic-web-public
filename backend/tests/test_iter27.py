"""Iter 27 — shares (public gallery links), friends (invite/accept/dm), memory pin, mixed-group AI silence, two-tier compact summary."""
import os
import time
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

DEMO = ("demo@aivora.ai", "demo123456")
BUDI = ("budi@aivora.ai", "budi123456")
RIO = "e93a66a6-59b1-4a12-8c16-0c9dba6c3348"
MIXED_GROUP = "90435108-e7d4-429c-9daa-f488d70035b7"
RIO_DIRECT_CID = "4e36eefc-3ae9-4f48-98b5-e1a0fc7828e9"


def _login(email, pw):
    time.sleep(1)
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def demo_h():
    return {"Authorization": f"Bearer {_login(*DEMO)}"}


@pytest.fixture(scope="module")
def budi_h():
    return {"Authorization": f"Bearer {_login(*BUDI)}"}


# ---------- Shares (documents + images) ----------
@pytest.fixture(scope="module")
def doc_task_id(demo_h):
    r = requests.get(f"{API}/gallery?type=document&limit=20", headers=demo_h, timeout=30)
    assert r.status_code == 200
    items = r.json().get("items") or []
    done = [i for i in items if i.get("task_id")]
    assert done, "need a completed document task"
    return done[0]["task_id"]


@pytest.fixture(scope="module")
def image_item(demo_h):
    r = requests.get(f"{API}/gallery?type=image&limit=20", headers=demo_h, timeout=30)
    assert r.status_code == 200
    items = r.json().get("items") or []
    with_path = [i for i in items if i.get("path")]
    if not with_path:
        pytest.skip("no image in gallery")
    return with_path[0]


def test_share_document_full_flow(demo_h, doc_task_id) -> None:
    # invalid hours
    bad = requests.post(f"{API}/shares", json={"kind": "document", "name": "QA Doc", "task_id": doc_task_id, "hours": 5}, headers=demo_h, timeout=30)
    assert bad.status_code == 400

    r = requests.post(f"{API}/shares", json={"kind": "document", "name": "QA Doc", "task_id": doc_task_id, "hours": 24}, headers=demo_h, timeout=30)
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    assert code

    # Public GET (no auth)
    pub = requests.get(f"{API}/public/share/{code}", timeout=30)
    assert pub.status_code == 200
    body = pub.json()
    assert body["kind"] == "document"
    assert "title" in body and "content" in body

    # export pdf
    exp = requests.get(f"{API}/public/share/{code}/export/pdf", timeout=60)
    assert exp.status_code == 200
    assert "attachment" in exp.headers.get("Content-Disposition", "").lower()
    assert exp.headers.get("content-type", "").startswith("application/pdf")

    # revoke
    d = requests.delete(f"{API}/shares/{code}", headers=demo_h, timeout=30)
    assert d.status_code == 200
    # public now 404
    g = requests.get(f"{API}/public/share/{code}", timeout=30)
    assert g.status_code == 404


def test_share_image_file(demo_h, image_item) -> None:
    r = requests.post(f"{API}/shares", json={"kind": "image", "name": image_item.get("name") or "image.png", "path": image_item["path"], "hours": 24}, headers=demo_h, timeout=30)
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    f = requests.get(f"{API}/public/share/{code}/file", timeout=30)
    assert f.status_code == 200
    assert f.headers.get("content-type", "").startswith("image/")


# ---------- Friends ----------
def test_friends_demo_already_friends_with_budi(demo_h) -> None:
    r = requests.post(f"{API}/friends/invite", json={"email": "budi@aivora.ai"}, headers=demo_h, timeout=30)
    assert r.status_code == 400
    assert "berteman" in r.text.lower()


def test_friends_list_shape_demo_sees_budi(demo_h) -> None:
    r = requests.get(f"{API}/friends", headers=demo_h, timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert "friends" in data
    names = [f.get("email") for f in data["friends"]]
    assert "budi@aivora.ai" in names
    return data


def test_friend_chat_idempotent(demo_h) -> None:
    budi_id = next(f["id"] for f in requests.get(f"{API}/friends", headers=demo_h, timeout=30).json()["friends"] if f["email"] == "budi@aivora.ai")
    r1 = requests.post(f"{API}/friends/{budi_id}/chat", headers=demo_h, timeout=30)
    assert r1.status_code == 200, r1.text
    cid1 = r1.json()["id"]
    r2 = requests.post(f"{API}/friends/{budi_id}/chat", headers=demo_h, timeout=30)
    assert r2.status_code == 200
    assert r2.json()["id"] == cid1


def test_friend_dm_title_per_user(demo_h, budi_h) -> None:
    convs_d = requests.get(f"{API}/conversations", headers=demo_h, timeout=30).json()
    dms_d = [c for c in convs_d if c.get("type") == "dm"]
    assert dms_d, "demo should have at least one dm"
    assert any("budi" in (c.get("title") or "").lower() for c in dms_d)

    convs_b = requests.get(f"{API}/conversations", headers=budi_h, timeout=30).json()
    dms_b = [c for c in convs_b if c.get("type") == "dm"]
    assert dms_b
    assert any("demo" in (c.get("title") or "").lower() for c in dms_b)


def test_friend_email_invite_unregistered(demo_h) -> None:
    email = f"qa-teman-{int(time.time())}@example.com"
    r = requests.post(f"{API}/friends/invite", json={"email": email}, headers=demo_h, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("status") == "emailed"
    # appears in email_invites pending
    data = requests.get(f"{API}/friends", headers=demo_h, timeout=30).json()
    emails = [e.get("email") for e in data.get("email_invites") or []]
    assert email in emails


# ---------- Memory pin ----------
def test_memory_pin_toggle(demo_h) -> None:
    # create a memory for Rio
    r = requests.post(f"{API}/memory", json={"persona_id": RIO, "content": f"QA pin test {int(time.time())}", "enabled": True}, headers=demo_h, timeout=30)
    assert r.status_code in (200, 201), r.text
    mid = r.json()["id"]
    u = requests.put(f"{API}/memory/{mid}", json={"pinned": True}, headers=demo_h, timeout=30)
    assert u.status_code == 200, u.text
    assert u.json().get("pinned") is True
    # cleanup
    requests.delete(f"{API}/memory/{mid}", headers=demo_h, timeout=30)


# ---------- Mixed group behavior ----------
def _sse_events(resp):
    out = []
    for line in resp.iter_lines(decode_unicode=True):
        if line and line.startswith("data: "):
            out.append(line[6:])
    return out


def test_mixed_group_no_ai_on_casual_message(budi_h) -> None:
    import json as _json
    r = requests.post(f"{API}/conversations/{MIXED_GROUP}/send", json={"content": "oke siap"}, headers=budi_h, timeout=120, stream=True)
    assert r.status_code == 200, r.text
    evs = _sse_events(r)
    had_persona = False
    for e in evs:
        try:
            d = _json.loads(e)
        except Exception:
            continue
        if d.get("persona_name") and d.get("persona_name") != "Moderator":
            had_persona = True
            break
    assert not had_persona, f"expected no AI reply, got events: {evs[:5]}"


def test_mixed_group_ai_replies_when_addressed(budi_h) -> None:
    import json as _json
    r = requests.post(f"{API}/conversations/{MIXED_GROUP}/send", json={"content": "Rio, tolong sebutkan 2 manfaat menabung"}, headers=budi_h, timeout=180, stream=True)
    assert r.status_code == 200, r.text
    evs = _sse_events(r)
    found = False
    for e in evs:
        try:
            d = _json.loads(e)
        except Exception:
            continue
        if (d.get("persona_name") or "").lower() == "rio":
            found = True
            break
    assert found, f"expected Rio to reply; events: {evs[:10]}"


# ---------- Two-tier compact summary ----------
def test_compact_two_tier_summary(demo_h, budi_h) -> None:
    cid = MIXED_GROUP  # has multiple live messages from mixed-group tests above
    msgs = requests.get(f"{API}/conversations/{cid}/messages?limit=200", headers=demo_h, timeout=30).json()
    live_count = sum(1 for m in msgs.get("messages", []) if not m.get("archived"))
    if live_count < 2:
        # top up with 1 cheap human message
        requests.post(f"{API}/conversations/{cid}/send", json={"content": "ok"}, headers=budi_h, timeout=60, stream=True).close()
        time.sleep(2)

    r = requests.post(f"{API}/conversations/{cid}/compact", headers=demo_h, timeout=240)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("summary") and body.get("archive_id") and "archived" in body
    aid = body["archive_id"]
    g = requests.get(f"{API}/archives/{aid}", headers=demo_h, timeout=30)
    assert g.status_code == 200
    ad = g.json()
    assert ad.get("summary"), "archive should have detailed summary"
    msgs2 = requests.get(f"{API}/conversations/{cid}/messages?limit=5", headers=demo_h, timeout=30).json()
    core = (msgs2.get("conversation") or {}).get("memory_summary") or ""
    assert len(core) <= 1500, f"core memory_summary too long: {len(core)}"


# ---------- Regression ----------
def test_login_both() -> None:
    assert _login(*DEMO)
    assert _login(*BUDI)


def test_archives_and_workspace_load(demo_h) -> None:
    a = requests.get(f"{API}/archives?limit=5", headers=demo_h, timeout=30)
    assert a.status_code == 200
    w = requests.get(f"{API}/tasks?limit=5", headers=demo_h, timeout=30)
    assert w.status_code == 200


def test_gallery_search(demo_h) -> None:
    r = requests.get(f"{API}/gallery?q=Bandung&limit=10", headers=demo_h, timeout=30)
    assert r.status_code == 200
    assert "items" in r.json()
