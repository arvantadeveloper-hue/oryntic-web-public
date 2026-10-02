"""Iter 17 — Backend tests for model routing, image/document tools, attachment memory."""
import os
import json
import time
import requests
import pytest

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "https://ai-companion-test-5.preview.emergentagent.com").rstrip("/")
MEETING_CID = "bcf72bc8-1c0d-4c5f-bb3c-e7d15dbee9f6"
ADMIN_EMAIL = "admin@aivora.ai"
ADMIN_PASS = "Aivora!Admin2026"


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def demo_token():
    return _login("demo@aivora.ai", "demo123456")


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="module")
def demo_h(demo_token):
    return {"Authorization": f"Bearer {demo_token}"}


@pytest.fixture(scope="module")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- SSE helpers ----------
def _parse_sse(text):
    final = None
    statuses = []
    for line in text.split("\n"):
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
        except Exception:
            continue
        if obj.get("status"):
            statuses.append(obj["status"])
        if obj.get("final"):
            final = obj
    return final, statuses


# ---------- (1) Admin model routing ----------
class TestAdminRouting:
    def test_demo_cannot_access(self, demo_h):
        r = requests.get(f"{BASE_URL}/api/admin/model-routing", headers=demo_h, timeout=15)
        assert r.status_code == 403, r.text

    def test_admin_get_defaults(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/admin/model-routing", headers=admin_h, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("enabled", "it_model", "research_model", "confirm_threshold", "models"):
            assert k in j
        assert isinstance(j["models"], list) and len(j["models"]) > 0

    def test_admin_put_valid(self, admin_h):
        r = requests.put(f"{BASE_URL}/api/admin/model-routing", headers=admin_h,
                         json={"enabled": True, "it_model": "gemini-pro",
                               "research_model": "gemini-pro", "confirm_threshold": 20}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["it_model"] == "gemini-pro"
        # verify GET reflects
        g = requests.get(f"{BASE_URL}/api/admin/model-routing", headers=admin_h, timeout=15).json()
        assert g["it_model"] == "gemini-pro"
        assert g["confirm_threshold"] == 20

    def test_admin_put_invalid_model(self, admin_h):
        r = requests.put(f"{BASE_URL}/api/admin/model-routing", headers=admin_h,
                         json={"enabled": True, "it_model": "nope",
                               "research_model": "gemini-pro", "confirm_threshold": 20}, timeout=15)
        assert r.status_code == 400, r.text

    def test_restore_defaults(self, admin_h):
        r = requests.put(f"{BASE_URL}/api/admin/model-routing", headers=admin_h,
                         json={"enabled": True, "it_model": "claude-sonnet",
                               "research_model": "gemini-pro", "confirm_threshold": 20}, timeout=15)
        assert r.status_code == 200
        # allow cache to refresh
        time.sleep(1)


# ---------- (2) Smart routing in /send ----------
class TestRoutingInSend:
    def test_it_message_routed_to_claude(self, demo_h):
        # Ensure routing enabled & smart_routing on
        requests.put(f"{BASE_URL}/api/auth/settings", headers=demo_h,
                     json={"smart_routing": True}, timeout=15)
        time.sleep(2)  # cache
        r = requests.post(f"{BASE_URL}/api/conversations/{MEETING_CID}/send",
                          headers=demo_h,
                          json={"content": "Jelaskan singkat apa itu regex di python, 1 kalimat",
                                "attachments": [], "channel": "meeting_chat"},
                          timeout=120)
        assert r.status_code == 200, r.text
        final, _ = _parse_sse(r.text)
        assert final is not None, "No final event"
        assert final.get("routed") == "it", f"Expected routed=it, got {final}"
        assert final.get("model_label") == "Claude Sonnet", f"Got {final.get('model_label')}"

        # verify persisted
        msgs = requests.get(f"{BASE_URL}/api/conversations/{MEETING_CID}/messages",
                            headers=demo_h, timeout=15).json()["messages"]
        last_asst = [m for m in msgs if m["role"] == "assistant"][-1]
        assert last_asst.get("routed") == "it"
        assert last_asst.get("model_key") == "claude-sonnet"

    def test_non_it_message_no_routed(self, demo_h):
        r = requests.post(f"{BASE_URL}/api/conversations/{MEETING_CID}/send",
                          headers=demo_h,
                          json={"content": "Apa kabar hari ini?", "channel": "meeting_chat"},
                          timeout=120)
        assert r.status_code == 200
        final, _ = _parse_sse(r.text)
        assert final is not None
        assert "routed" not in final or not final.get("routed"), f"Should NOT be routed: {final}"

    def test_smart_routing_off_disables(self, demo_h):
        r = requests.put(f"{BASE_URL}/api/auth/settings", headers=demo_h,
                        json={"smart_routing": False}, timeout=15)
        assert r.status_code == 200
        time.sleep(1)
        r = requests.post(f"{BASE_URL}/api/conversations/{MEETING_CID}/send",
                          headers=demo_h,
                          json={"content": "Jelaskan singkat apa itu regex di python, 1 kalimat",
                                "channel": "meeting_chat"}, timeout=120)
        assert r.status_code == 200
        final, _ = _parse_sse(r.text)
        assert final is not None
        assert not final.get("routed"), f"Smart routing OFF but got routed: {final}"
        # restore
        requests.put(f"{BASE_URL}/api/auth/settings", headers=demo_h,
                     json={"smart_routing": True}, timeout=15)


# ---------- (3) Image tool with confirmation ----------
class TestImageTool:
    def _get_private_cid(self, demo_h):
        convs = requests.get(f"{BASE_URL}/api/conversations", headers=demo_h, timeout=15).json()
        p = next((c for c in convs if c.get("type") == "private"), None)
        assert p, "No private conversation"
        return p["id"]

    def test_image_pending_then_cancel(self, demo_h):
        cid = self._get_private_cid(demo_h)
        r = requests.post(f"{BASE_URL}/api/conversations/{cid}/send", headers=demo_h,
                          json={"content": "Buatkan gambar poster promosi kopi susu gaya minimalis"},
                          timeout=120)
        assert r.status_code == 200, r.text
        final, _ = _parse_sse(r.text)
        assert final is not None
        pt = final.get("pending_tool")
        assert pt and pt.get("kind") == "image", f"No pending_tool: {final}"
        assert pt.get("credits") == 25
        mid = final["message_id"]

        c = requests.post(f"{BASE_URL}/api/conversations/{cid}/messages/{mid}/cancel-tool",
                          headers=demo_h, timeout=30)
        assert c.status_code == 200, c.text
        body = c.json()
        assert body.get("tool_cancelled") is True
        assert not body.get("pending_tool")

    def test_image_pending_then_run(self, demo_h):
        cid = self._get_private_cid(demo_h)
        r = requests.post(f"{BASE_URL}/api/conversations/{cid}/send", headers=demo_h,
                          json={"content": "Buatkan gambar ilustrasi kucing kecil lucu gaya kartun"},
                          timeout=120)
        assert r.status_code == 200
        final, _ = _parse_sse(r.text)
        assert final.get("pending_tool"), f"No pending_tool: {final}"
        mid = final["message_id"]

        run = requests.post(f"{BASE_URL}/api/conversations/{cid}/messages/{mid}/run-tool",
                            headers=demo_h, timeout=180)
        assert run.status_code == 200, run.text
        body = run.json()
        assert body.get("media"), "No media after run"
        assert body["media"][0]["type"] == "image"
        assert body.get("credits") == 25
        path = body["media"][0]["path"]

        f = requests.get(f"{BASE_URL}/api/files/{path}?auth={demo_h['Authorization'].split()[1]}",
                         timeout=30)
        assert f.status_code == 200, f.text
        assert f.headers.get("content-type", "").startswith("image/"), f.headers

    def test_run_tool_without_pending_404(self, demo_h):
        cid = self._get_private_cid(demo_h)
        # pick any assistant message id without pending_tool
        msgs = requests.get(f"{BASE_URL}/api/conversations/{cid}/messages",
                            headers=demo_h, timeout=15).json()["messages"]
        candidate = next((m for m in msgs if m["role"] == "assistant" and not m.get("pending_tool")), None)
        assert candidate, "No assistant msg found"
        r = requests.post(f"{BASE_URL}/api/conversations/{cid}/messages/{candidate['id']}/run-tool",
                          headers=demo_h, timeout=30)
        assert r.status_code == 404, r.text


# ---------- (4) Document tool ----------
class TestDocumentTool:
    def test_document_three_files(self, demo_h):
        convs = requests.get(f"{BASE_URL}/api/conversations", headers=demo_h, timeout=15).json()
        cid = next(c for c in convs if c.get("type") == "private")["id"]
        r = requests.post(f"{BASE_URL}/api/conversations/{cid}/send", headers=demo_h,
                          json={"content": "Buatkan dokumen surat penawaran kerja sama 1 halaman untuk kafe"},
                          timeout=180)
        assert r.status_code == 200, r.text
        final, statuses = _parse_sse(r.text)
        assert final is not None
        assert any("dokumen" in s.lower() or "menyusun" in s.lower() for s in statuses), f"statuses={statuses}"
        media = final.get("media") or []
        assert len(media) == 3, f"Expected 3 files, got {media}"
        formats = {m.get("format") or m["name"].split(".")[-1] for m in media}
        assert formats == {"docx", "pdf", "md"}, f"formats={formats}"

        token = demo_h["Authorization"].split()[1]
        for m in media:
            path = m["path"]
            fr = requests.get(f"{BASE_URL}/api/files/{path}?auth={token}", timeout=60)
            assert fr.status_code == 200, f"{path}: {fr.text}"
            ext = path.rsplit(".", 1)[-1]
            ct = fr.headers.get("content-type", "")
            if ext == "pdf":
                assert "application/pdf" in ct
                assert fr.content[:4] == b"%PDF"
            elif ext == "docx":
                assert "wordprocessingml" in ct or "officedocument" in ct

        # verify tool='document' stored
        msgs = requests.get(f"{BASE_URL}/api/conversations/{cid}/messages",
                            headers=demo_h, timeout=15).json()["messages"]
        last_asst = [m for m in msgs if m["role"] == "assistant"][-1]
        assert last_asst.get("tool") == "document"


# ---------- (5) Attachment memory ----------
class TestAttachmentMemory:
    def test_attachment_text_persisted_and_remembered(self, demo_h):
        convs = requests.get(f"{BASE_URL}/api/conversations", headers=demo_h, timeout=15).json()
        cid = next(c for c in convs if c.get("type") == "private")["id"]
        r = requests.post(f"{BASE_URL}/api/conversations/{cid}/send", headers=demo_h,
                          json={"content": "Simpan catatan ini ya",
                                "attachments": [{"type": "text", "name": "catatan.txt",
                                                 "data": "Harga kopi susu Rp25.000, es kopi gula aren Rp28.000"}]},
                          timeout=120)
        assert r.status_code == 200
        _parse_sse(r.text)

        # check user msg has attachment_text
        msgs = requests.get(f"{BASE_URL}/api/conversations/{cid}/messages",
                            headers=demo_h, timeout=15).json()["messages"]
        last_user = [m for m in msgs if m["role"] == "user"][-1]
        assert last_user.get("attachment_text"), f"no attachment_text in {last_user}"
        assert "28.000" in last_user["attachment_text"] or "28000" in last_user["attachment_text"]

        # follow-up
        r2 = requests.post(f"{BASE_URL}/api/conversations/{cid}/send", headers=demo_h,
                           json={"content": "Berapa harga es kopi gula aren menurut lampiran tadi?"},
                           timeout=120)
        assert r2.status_code == 200
        final, _ = _parse_sse(r2.text)
        content = (final or {}).get("content", "")
        assert "28" in content, f"reply does not mention 28k: {content}"
