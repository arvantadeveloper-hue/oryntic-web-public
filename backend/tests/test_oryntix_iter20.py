"""Iter 20 - Workspace overhaul: exports, revisions, discuss, add persona, chat-doc, member access.

Credentials:
  demo@aivora.ai / $TEST_DEMO_PASSWORD  (workspace owner, see backend/.env)
  budi@aivora.ai / budi123456  (member of demo workspace)
"""
import os
import json
import pytest
import requests
import sys as _sys; _sys.path.insert(0, '/app/backend/tests')  # noqa: E702
from creds import DEMO_PASSWORD, ADMIN_PASSWORD, BUDI_PASSWORD  # noqa: E402,F401

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ai-companion-test-5.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
TIMEOUT = 90


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def demo_token():
    return _login("demo@aivora.ai", DEMO_PASSWORD)


@pytest.fixture(scope="module")
def budi_token():
    return _login("budi@aivora.ai", BUDI_PASSWORD)


def H(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def completed_task(demo_token):
    """Pick any already-completed task from demo's workspace, or create one via chat."""
    r = requests.get(f"{API}/tasks?limit=50", headers=H(demo_token), timeout=30)
    assert r.status_code == 200
    tasks = r.json()
    completed = [t for t in tasks if t.get("status") == "completed" and (t.get("final_output") or "").strip()]
    if completed:
        return completed[0]
    pytest.skip("no completed task available for export tests")


# ---------- GET /tasks list & detail ----------
class TestTaskListDetail:
    def test_list_tasks_has_workspace_id(self, demo_token):
        r = requests.get(f"{API}/tasks?limit=20", headers=H(demo_token), timeout=30)
        assert r.status_code == 200
        tasks = r.json()
        assert isinstance(tasks, list) and len(tasks) > 0
        assert all("workspace_id" in t for t in tasks[:5]), "tasks missing workspace_id"

    def test_task_detail_shape(self, demo_token, completed_task):
        r = requests.get(f"{API}/tasks/{completed_task['id']}", headers=H(demo_token), timeout=30)
        assert r.status_code == 200
        t = r.json()
        assert isinstance(t.get("has_tables"), bool)
        assert isinstance(t.get("version"), int) and t["version"] >= 1
        assert isinstance(t.get("versions"), list)
        for v in t["versions"]:
            assert "content" not in v, "versions[] must not include content"


# ---------- Exports ----------
class TestExports:
    def test_export_docx(self, demo_token, completed_task):
        r = requests.get(f"{API}/tasks/{completed_task['id']}/export/docx", headers=H(demo_token), timeout=60)
        assert r.status_code == 200
        assert "wordprocessingml" in r.headers.get("content-type", "")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd and ".docx" in cd
        assert len(r.content) > 100

    def test_export_pdf(self, demo_token, completed_task):
        r = requests.get(f"{API}/tasks/{completed_task['id']}/export/pdf", headers=H(demo_token), timeout=60)
        assert r.status_code == 200
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content[:4] == b"%PDF"

    def test_export_md(self, demo_token, completed_task):
        r = requests.get(f"{API}/tasks/{completed_task['id']}/export/md", headers=H(demo_token), timeout=30)
        assert r.status_code == 200
        assert "markdown" in r.headers.get("content-type", "")
        assert len(r.content) > 0

    def test_export_xlsx_no_tables(self, demo_token, completed_task):
        # task likely has no tables; expect 400
        detail = requests.get(f"{API}/tasks/{completed_task['id']}", headers=H(demo_token), timeout=30).json()
        if detail.get("has_tables"):
            pytest.skip("completed task already has tables")
        r = requests.get(f"{API}/tasks/{completed_task['id']}/export/xlsx", headers=H(demo_token), timeout=30)
        assert r.status_code == 400

    def test_export_bogus_format(self, demo_token, completed_task):
        r = requests.get(f"{API}/tasks/{completed_task['id']}/export/bogus", headers=H(demo_token), timeout=30)
        assert r.status_code == 400


# ---------- Revise via workspace endpoint ----------
class TestRevise:
    @pytest.fixture(scope="class")
    def revised(self, demo_token, completed_task):
        before = requests.get(f"{API}/tasks/{completed_task['id']}", headers=H(demo_token), timeout=30).json()
        v0 = int(before["version"])
        r = requests.post(f"{API}/tasks/{completed_task['id']}/revise",
                          headers=H(demo_token),
                          json={"instruction": "Tambahkan tabel anggaran dengan kolom Item, Biaya, dan Keterangan. Isi 3 baris contoh."},
                          timeout=TIMEOUT)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        body = r.json()
        assert body["version"] == v0 + 1
        return {"task_id": completed_task["id"], "v0": v0, "v_new": body["version"]}

    def test_version_incremented(self, demo_token, revised):
        r = requests.get(f"{API}/tasks/{revised['task_id']}", headers=H(demo_token), timeout=30)
        assert r.status_code == 200
        t = r.json()
        assert t["version"] == revised["v_new"]
        # versions[] contains the previous one with a note
        olds = [v for v in t["versions"] if int(v["version"]) == revised["v0"]]
        assert len(olds) == 1
        assert "note" in olds[0]

    def test_get_old_version(self, demo_token, revised):
        r = requests.get(f"{API}/tasks/{revised['task_id']}/versions/{revised['v0']}", headers=H(demo_token), timeout=30)
        assert r.status_code == 200
        assert r.json().get("content") is not None

    def test_get_bad_version(self, demo_token, revised):
        r = requests.get(f"{API}/tasks/{revised['task_id']}/versions/99", headers=H(demo_token), timeout=30)
        assert r.status_code == 404

    def test_xlsx_now_works_if_tables(self, demo_token, revised):
        detail = requests.get(f"{API}/tasks/{revised['task_id']}", headers=H(demo_token), timeout=30).json()
        if not detail.get("has_tables"):
            pytest.skip("LLM did not include a markdown table in the revision")
        r = requests.get(f"{API}/tasks/{revised['task_id']}/export/xlsx", headers=H(demo_token), timeout=60)
        assert r.status_code == 200
        assert "spreadsheetml" in r.headers.get("content-type", "")
        assert r.content[:2] == b"PK"  # xlsx is a zip


# ---------- Discuss (chat/call/meeting) ----------
class TestDiscuss:
    def test_chat_reuse(self, demo_token, completed_task):
        tid = completed_task["id"]
        r1 = requests.post(f"{API}/tasks/{tid}/discuss", headers=H(demo_token), json={"mode": "chat"}, timeout=30)
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["open_call"] is False
        cid = d1["conversation_id"]

        r2 = requests.post(f"{API}/tasks/{tid}/discuss", headers=H(demo_token), json={"mode": "chat"}, timeout=30)
        assert r2.json()["conversation_id"] == cid, "chat mode should reuse the same private conv"

        # inspect conversation
        rm = requests.get(f"{API}/conversations/{cid}/messages?limit=5", headers=H(demo_token), timeout=30)
        assert rm.status_code == 200
        conv = rm.json()["conversation"]
        assert conv.get("task_id") == tid
        assert conv["type"] == "private"
        assert len(conv.get("members") or []) == 1

    def test_call_mode_same_private(self, demo_token, completed_task):
        tid = completed_task["id"]
        r_chat = requests.post(f"{API}/tasks/{tid}/discuss", headers=H(demo_token), json={"mode": "chat"}, timeout=30)
        chat_cid = r_chat.json()["conversation_id"]
        r = requests.post(f"{API}/tasks/{tid}/discuss", headers=H(demo_token), json={"mode": "call"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["open_call"] is True
        assert r.json()["conversation_id"] == chat_cid

    def test_meeting_is_separate(self, demo_token, completed_task):
        tid = completed_task["id"]
        r_chat = requests.post(f"{API}/tasks/{tid}/discuss", headers=H(demo_token), json={"mode": "chat"}, timeout=30)
        chat_cid = r_chat.json()["conversation_id"]
        r = requests.post(f"{API}/tasks/{tid}/discuss", headers=H(demo_token), json={"mode": "meeting"}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body["open_call"] is True
        assert body["conversation_id"] != chat_cid
        rm = requests.get(f"{API}/conversations/{body['conversation_id']}/messages?limit=1", headers=H(demo_token), timeout=30)
        conv = rm.json()["conversation"]
        assert conv["type"] == "meeting"
        assert conv.get("task_id") == tid


# ---------- Revision via chat (SSE) ----------
def _read_sse(resp):
    """Yield parsed JSON data events from an SSE text/event-stream."""
    buf = b""
    for chunk in resp.iter_content(chunk_size=None):
        if not chunk:
            continue
        buf += chunk
        while b"\n\n" in buf:
            raw, buf = buf.split(b"\n\n", 1)
            for line in raw.decode("utf-8", "ignore").splitlines():
                if line.startswith("data:"):
                    try:
                        yield json.loads(line[5:].strip())
                    except Exception:
                        pass


class TestChatRevision:
    @pytest.fixture(scope="class")
    def chat_cid(self, demo_token, completed_task):
        r = requests.post(f"{API}/tasks/{completed_task['id']}/discuss", headers=H(demo_token), json={"mode": "chat"}, timeout=30)
        return r.json()["conversation_id"]

    def test_revise_via_chat_increments_version(self, demo_token, completed_task, chat_cid):
        tid = completed_task["id"]
        before = requests.get(f"{API}/tasks/{tid}", headers=H(demo_token), timeout=30).json()
        v0 = before["version"]
        with requests.post(f"{API}/conversations/{chat_cid}/send",
                           headers={"Authorization": f"Bearer {demo_token}", "Content-Type": "application/json", "Accept": "text/event-stream"},
                           json={"content": "Tolong ubah judul bagian pertama menjadi Ringkasan Eksekutif"},
                           stream=True, timeout=TIMEOUT) as resp:
            assert resp.status_code == 200
            final_text = ""
            for ev in _read_sse(resp):
                if ev.get("final") and ev.get("content"):
                    final_text = ev["content"]
                if ev.get("done"):
                    break
        assert "Revisi" in final_text and "tersimpan di Ruang Kerja" in final_text, f"final content: {final_text[:400]}"
        after = requests.get(f"{API}/tasks/{tid}", headers=H(demo_token), timeout=30).json()
        assert after["version"] == v0 + 1

    def test_non_revision_question_no_version_change(self, demo_token, completed_task, chat_cid):
        tid = completed_task["id"]
        before = requests.get(f"{API}/tasks/{tid}", headers=H(demo_token), timeout=30).json()
        v0 = before["version"]
        got_final = False
        with requests.post(f"{API}/conversations/{chat_cid}/send",
                           headers={"Authorization": f"Bearer {demo_token}", "Content-Type": "application/json", "Accept": "text/event-stream"},
                           json={"content": "Apa poin utama dokumen ini?"},
                           stream=True, timeout=TIMEOUT) as resp:
            assert resp.status_code == 200
            for ev in _read_sse(resp):
                if ev.get("final"):
                    got_final = True
                if ev.get("done"):
                    break
        assert got_final
        after = requests.get(f"{API}/tasks/{tid}", headers=H(demo_token), timeout=30).json()
        assert after["version"] == v0, "non-revision question must not bump version"


# ---------- Add persona to conversation ----------
class TestAddPersona:
    def test_add_persona_private_to_group(self, demo_token, completed_task):
        tid = completed_task["id"]
        r_chat = requests.post(f"{API}/tasks/{tid}/discuss", headers=H(demo_token), json={"mode": "chat"}, timeout=30)
        cid = r_chat.json()["conversation_id"]
        conv_before = requests.get(f"{API}/conversations/{cid}/messages?limit=1", headers=H(demo_token), timeout=30).json()["conversation"]
        in_ids = set(conv_before.get("persona_ids") or [])
        personas = requests.get(f"{API}/personas", headers=H(demo_token), timeout=30).json()
        others = [p for p in personas if p["id"] not in in_ids]
        if not others:
            pytest.skip("no other persona to add")
        pid = others[0]["id"]
        r = requests.post(f"{API}/conversations/{cid}/personas", headers=H(demo_token), json={"persona_id": pid}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["type"] == "group"
        assert len(body["members"]) == 2
        assert pid in body["persona_ids"] and list(in_ids)[0] in body["persona_ids"]

        # same persona again -> 409
        r2 = requests.post(f"{API}/conversations/{cid}/personas", headers=H(demo_token), json={"persona_id": pid}, timeout=30)
        assert r2.status_code == 409

        # unknown persona -> 404
        r3 = requests.post(f"{API}/conversations/{cid}/personas", headers=H(demo_token), json={"persona_id": "nope-does-not-exist"}, timeout=30)
        assert r3.status_code == 404

        # system message "bergabung ke percakapan" present
        msgs = requests.get(f"{API}/conversations/{cid}/messages?limit=20", headers=H(demo_token), timeout=30).json()["messages"]
        assert any("bergabung ke percakapan" in (m.get("content") or "") for m in msgs)


# ---------- Chat → document creates workspace task ----------
class TestChatDocumentCreatesTask:
    def test_document_chat_creates_task(self, demo_token):
        # Create a fresh private conversation (not task-linked) with first persona
        personas = requests.get(f"{API}/personas", headers=H(demo_token), timeout=30).json()
        assert personas, "need at least one persona"
        pid = personas[0]["id"]
        r_new = requests.post(f"{API}/conversations", headers=H(demo_token), json={"persona_ids": [pid], "type": "private"}, timeout=30)
        assert r_new.status_code == 200, r_new.text
        cid = r_new.json()["id"]
        task_id = None
        has_media = False
        final_event = {}
        with requests.post(f"{API}/conversations/{cid}/send",
                           headers={"Authorization": f"Bearer {demo_token}", "Content-Type": "application/json", "Accept": "text/event-stream"},
                           json={"content": "Buatkan dokumen proposal singkat program magang 3 paragraf, judul: Proposal Magang"},
                           stream=True, timeout=TIMEOUT) as resp:
            assert resp.status_code == 200
            for ev in _read_sse(resp):
                if ev.get("final"):
                    final_event = ev
                    task_id = ev.get("task_id")
                    if ev.get("media"):
                        has_media = True
                if ev.get("done"):
                    break
        assert has_media, "final event must include media files"
        # BUG: backend _emit_final() in chat.py drops task_id from the SSE payload (only forwards media/pending_tool).
        # Task IS created correctly, but frontend can't learn task_id from the SSE stream.
        assert task_id, f"final event must include task_id (BUG: _emit_final strips it). Final keys: {list(final_event.keys())}"
        assert task_id, "final event must include task_id"
        assert has_media, "final event must include media files"
        t = requests.get(f"{API}/tasks/{task_id}", headers=H(demo_token), timeout=30).json()
        assert t.get("type") == "document"
        assert t.get("status") == "completed"
        assert t.get("source") == "chat"
        assert (t.get("final_output") or "").strip() != ""


# ---------- Budi (member) regression ----------
class TestMemberAccess:
    def test_member_sees_demo_tasks(self, budi_token, completed_task):
        r = requests.get(f"{API}/tasks?limit=50", headers=H(budi_token), timeout=30)
        assert r.status_code == 200
        tids = [t["id"] for t in r.json()]
        assert completed_task["id"] in tids, "member should see demo-workspace tasks"

    def test_member_get_task(self, budi_token, completed_task):
        r = requests.get(f"{API}/tasks/{completed_task['id']}", headers=H(budi_token), timeout=30)
        assert r.status_code == 200
        assert r.json()["id"] == completed_task["id"]

    def test_member_export_docx(self, budi_token, completed_task):
        r = requests.get(f"{API}/tasks/{completed_task['id']}/export/docx", headers=H(budi_token), timeout=60)
        assert r.status_code == 200
        assert "wordprocessingml" in r.headers.get("content-type", "")
