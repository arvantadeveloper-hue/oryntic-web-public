"""Regression tests for the chat_media/startup/docbuild refactor (iteration_44)."""
import json
import os
import time
import uuid
from datetime import datetime, timezone

import pytest
import requests

from tests.creds import ADMIN_EMAIL, ADMIN_PASSWORD, DEMO_EMAIL, DEMO_PASSWORD

from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"


# ---------- shared sessions (reuse tokens; login is rate-limited) ----------
@pytest.fixture(scope="session")
def demo():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json()["access_token"]
    s.headers.update({"Authorization": f"Bearer {tok}"})
    me = s.get(f"{API}/auth/me", timeout=15).json()
    uid = me.get("id") or me.get("user", {}).get("id") or me.get("_id") or ""
    return {"session": s, "token": tok, "user_id": uid}


@pytest.fixture(scope="session")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
    return {"session": s, "token": r.json()["access_token"]}


# ---------- SSE helper ----------
def sse_send(session, cid: str, content: str, timeout: int = 90):
    """POST /send, collect SSE events, return (final_event, all_events)."""
    url = f"{API}/conversations/{cid}/send"
    final = None
    events = []
    with session.post(url, json={"content": content}, stream=True, timeout=timeout) as r:
        assert r.status_code == 200, f"send failed {r.status_code}: {r.text[:300]}"
        buf = ""
        for raw in r.iter_lines(decode_unicode=True):
            if raw is None:
                continue
            if raw == "":
                if buf:
                    data = buf.strip()
                    buf = ""
                    if data == "[DONE]":
                        break
                    try:
                        ev = json.loads(data)
                        events.append(ev)
                        if ev.get("final"):
                            final = ev
                    except Exception:
                        pass
                continue
            if raw.startswith("data:"):
                buf += raw[5:].lstrip()
    return final, events


# ---------- smoke ----------
class TestSmoke:
    def test_root_ok(self):
        r = requests.get(f"{API}/", timeout=15)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_startup_log(self):
        with open("/var/log/supervisor/backend.err.log", "r", errors="ignore") as f:
            data = f.read()[-20000:]
        assert "Oryntix API started" in data
        # make sure no uncaught traceback since last start
        last_start = data.rfind("Oryntix API started")
        tail = data[last_start:]
        assert "Traceback" not in tail, tail[:2000]


# ---------- scheduler proof (startup.py _scheduler_loop) ----------
class TestScheduler:
    def test_due_job_marked_failed(self, demo):
        from pymongo import MongoClient
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "test_database")
        cli = MongoClient(mongo_url)
        db = cli[db_name]
        job_id = str(uuid.uuid4())
        payload = {
            "providers": ["linkedin"], "kind": "text", "text": "tick test",
            "title": "", "media_path": None, "drive_id": None,
            "app_url": "https://oryntix.app", "source": {},
        }
        doc = {
            "id": job_id,
            "user_id": demo["user_id"],
            "status": "scheduled",
            "scheduled_at": "2020-01-01T00:00:00+00:00",
            "providers": ["linkedin"],
            "kind": "text",
            "text": "tick test",
            "conversation_id": None,
            "payload": payload,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        db.social_schedules.insert_one(doc)
        try:
            end = time.time() + 60
            final_doc = None
            while time.time() < end:
                time.sleep(3)
                final_doc = db.social_schedules.find_one({"id": job_id})
                if final_doc and final_doc.get("status") in ("failed", "sent", "partial"):
                    break
            assert final_doc is not None
            assert final_doc.get("status") == "failed", f"status={final_doc.get('status')}"
            results = final_doc.get("results") or []
            assert results and "LinkedIn" in (results[0].get("error") or "")
        finally:
            db.social_schedules.delete_one({"id": job_id})
            cli.close()


# ---------- helpers to pick persona + create conv ----------
def _non_builtin_persona(session) -> str:
    r = session.get(f"{API}/personas", timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    arr = data if isinstance(data, list) else data.get("items") or data.get("personas") or []
    for p in arr:
        pid = p.get("id") or p.get("_id")
        is_builtin = p.get("builtin") or p.get("is_builtin") or (p.get("source") == "builtin")
        if pid and not is_builtin and pid != "oryntix-support":
            return pid
    # fall-back: just use any non-support persona
    for p in arr:
        pid = p.get("id") or p.get("_id")
        if pid and pid != "oryntix-support":
            return pid
    pytest.skip("No persona available")


def _create_direct(session, persona_id: str) -> str:
    r = session.post(f"{API}/conversations/direct", json={"persona_id": persona_id}, timeout=20)
    assert r.status_code in (200, 201), r.text
    j = r.json()
    return j.get("id") or j.get("conversation_id") or j["conversation"]["id"]


def _cancel_tool(session, cid, mid):
    r = session.post(f"{API}/conversations/{cid}/messages/{mid}/cancel-tool", timeout=20)
    return r.status_code


# ---------- image_turn ----------
class TestImageTurn:
    def test_image_offer_and_cancel(self, demo):
        s = demo["session"]
        pid = _non_builtin_persona(s)
        cid = _create_direct(s, pid)
        final, _ = sse_send(s, cid, "Buatkan gambar kucing oranye memakai topi astronot")
        assert final is not None, "no final event"
        pt = final.get("pending_tool") or {}
        assert pt.get("kind") == "image", f"got pt={pt} content={final.get('content','')[:200]}"
        assert pt.get("options") and len(pt["options"]) > 0
        assert pt.get("presets")
        assert pt.get("prompt")
        assert (pt.get("credits") or 0) > 0
        code = _cancel_tool(s, cid, final["message_id"])
        assert code == 200


# ---------- image_edit on existing conv with image ----------
class TestImageEdit:
    def test_image_edit_offer_and_cancel(self, demo):
        s = demo["session"]
        cid = "bcf72bc8-1c0d-4c5f-bb3c-e7d15dbee9f6"
        # verify conv accessible
        r = s.get(f"{API}/conversations/{cid}/messages", timeout=20)
        if r.status_code != 200:
            pytest.skip(f"seed conv not accessible: {r.status_code}")
        final, events = sse_send(s, cid, "Ubah gambar terakhir jadi gaya kartun", timeout=120)
        # In a group conv there can be two finals; pick any with image_edit
        edit_final = next((e for e in events if (e.get("pending_tool") or {}).get("kind") == "image_edit"), None)
        assert edit_final is not None, f"no image_edit final; finals={[e.get('pending_tool') for e in events if e.get('final')]}"
        pt = edit_final["pending_tool"]
        ref = pt.get("reference_path") or pt.get("ref_path") or pt.get("reference") or ""
        assert "aivora/images/" in ref, f"ref={ref}"
        _cancel_tool(s, cid, edit_final["message_id"])


# ---------- video offer ----------
class TestVideoOffer:
    def test_video_offer_any_valid_outcome(self, demo):
        s = demo["session"]
        pid = _non_builtin_persona(s)
        cid = _create_direct(s, pid)
        final, _ = sse_send(s, cid, "Buatkan video 5 detik pantai saat matahari terbenam", timeout=90)
        assert final is not None
        content = (final.get("content") or "").lower()
        pt = final.get("pending_tool") or {}
        tool = final.get("tool")
        tool_dict = tool if isinstance(tool, dict) else {}
        tool_name = (tool if isinstance(tool, str) else tool_dict.get("kind") or tool_dict.get("name") or "")

        case_a = pt.get("kind") == "video" and pt.get("options")
        case_b = (tool_name == "video" or pt.get("kind") == "video") and (
            "/integrations" in json.dumps(final) or "drive" in content or "belum terhubung" in content
        )
        case_c = "belum diaktifkan" in content and (tool_dict.get("error") or tool_name == "video")
        assert case_a or case_b or case_c, f"unexpected video outcome; pt={pt}, tool={tool}, content={content[:300]}"
        if case_a:
            _cancel_tool(s, cid, final["message_id"])


# ---------- drive save turn ----------
class TestDriveTurn:
    def test_drive_save(self, demo):
        s = demo["session"]
        pid = _non_builtin_persona(s)
        cid = _create_direct(s, pid)
        final, _ = sse_send(
            s, cid,
            "Simpan catatan ini ke Google Drive sebagai dokumen: Rapat tim Senin membahas roadmap Q4 dan alokasi anggaran.",
            timeout=90,
        )
        assert final is not None
        pt = final.get("pending_tool") or {}
        tool = final.get("tool")
        tool_name = tool if isinstance(tool, str) else (tool or {}).get("kind") or (tool or {}).get("name")
        kind = tool_name or pt.get("kind")
        assert kind == "drive_save", f"got kind={kind}, tool={tool}, pt={pt}"


# ---------- docbuild ----------
class TestDocBuild:
    def test_build_docx_and_pdf(self):
        from docbuild import build_docx, build_pdf
        d = build_docx("Judul", "# H1\n\nParagraf **tebal**\n\n- item 1\n- item 2\n\n| a | b |\n|---|---|\n| 1 | 2 |")
        p = build_pdf("Judul", "# H1\n\nteks")
        assert len(d) > 2000
        assert p[:4] == b"%PDF"

    def test_tools_reexport(self):
        from tools import build_docx, build_pdf
        assert callable(build_docx) and callable(build_pdf)

    def test_module_imports(self):
        import chat, chat_core, chat_media, server, startup  # noqa: F401
        assert chat.video_offer is chat_media.video_offer


# ---------- unrelated regression ----------
class TestUnrelated:
    def test_login(self, demo):
        assert demo["token"]

    def test_realtime_status(self, demo):
        r = demo["session"].get(f"{API}/realtime/status", timeout=15)
        assert r.status_code == 200
        assert r.json().get("model") == "gpt-live-1"

    def test_admin_pricing(self, admin):
        r = admin["session"].get(f"{API}/admin/pricing", timeout=20)
        assert r.status_code == 200
        rates = r.json().get("rates") or {}
        assert rates.get("image") == 57, f"image rate={rates.get('image')}"

    def test_support_chat(self, demo):
        s = demo["session"]
        cid = "403c8205-7477-48af-af44-0b6bf83258e5"
        r = s.get(f"{API}/conversations/{cid}/messages", timeout=20)
        if r.status_code != 200:
            pytest.skip("support conv not available")
        final, events = sse_send(s, cid, "Halo, apa kabar?", timeout=90)
        assert final is not None
        assert final.get("content"), "no assistant text"
        done = next((e for e in events if e.get("done") or e.get("type") == "done"), None)
        # credits_used present on done or final
        src = done or final
        assert "credits_used" in src or "credits" in src, f"no credits info: {src.keys()}"

    def test_ws_user(self, demo):
        import asyncio
        import websockets
        wss = BASE.replace("https://", "wss://").replace("http://", "ws://")
        url = f"{wss}/api/ws/user?token={demo['token']}"

        async def _run():
            async with websockets.connect(url, open_timeout=15) as ws:
                assert ws.state.name in ("OPEN", "CONNECTED")
        asyncio.get_event_loop().run_until_complete(_run())
