"""Iter 23 — Workspace keyword search + Team delegation flow.

Credentials: demo@aivora.ai / demo123456
"""
import os
import json
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = ln.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def tok():
    return _login("demo@aivora.ai", "demo123456")


@pytest.fixture(scope="module")
def persona_id(tok):
    r = requests.get(f"{API}/personas", headers=H(tok), timeout=30)
    assert r.status_code == 200
    personas = r.json()
    assert personas
    return personas[0]["id"]


@pytest.fixture(scope="module")
def persona_count(tok):
    r = requests.get(f"{API}/personas", headers=H(tok), timeout=30)
    return len(r.json())


def _new_conv(tok, pid, title="Iter23"):
    r = requests.post(f"{API}/conversations", headers=H(tok),
                      json={"type": "private", "persona_ids": [pid], "title": title}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _send_sse(tok, cid, text, timeout=180):
    final = None
    with requests.post(f"{API}/conversations/{cid}/send", headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
                       json={"content": text}, stream=True, timeout=timeout) as r:
        assert r.status_code == 200, f"/send {r.status_code} {r.text[:400]}"
        for raw in r.iter_lines():
            if not raw:
                continue
            try:
                line = raw.decode("utf-8")
            except Exception:
                continue
            if not line.startswith("data:"):
                continue
            try:
                ev = json.loads(line[5:].strip())
            except Exception:
                continue
            if ev.get("final"):
                final = ev
    assert final is not None, "no final SSE event"
    return final


# ========== Workspace search ==========
class TestWorkspaceSearch:
    def test_get_search_returns_results(self, tok):
        r = requests.get(f"{API}/workspace/search", headers=H(tok), params={"q": "kedai kopi"}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0, "expected non-empty results for 'kedai kopi'"
        first = data[0]
        for k in ("id", "title", "link", "version", "snippet"):
            assert k in first, f"missing key {k} in {first}"
        assert first["link"].startswith("/workspace/")
        assert first["link"].endswith(first["id"])

    def test_get_search_empty_for_gibberish(self, tok):
        r = requests.get(f"{API}/workspace/search", headers=H(tok), params={"q": "zzzqqq"}, timeout=30)
        assert r.status_code == 200
        assert r.json() == []

    def test_search_turn_via_send(self, tok, persona_id):
        cid = _new_conv(tok, persona_id, "Iter23 search")
        final = _send_sse(tok, cid, "Carikan dokumen tentang kedai kopi di ruang kerja")
        assert final.get("tool") == "workspace_search", f"tool wrong: {final.get('tool')}"
        results = final.get("results") or []
        assert len(results) > 0, "no results in final SSE"
        content = final.get("content") or ""
        assert "/workspace/" in content, "expected markdown link to /workspace/ in content"

        # follow-up: question referencing the found doc; must NOT be workspace_search tool again
        final2 = _send_sse(tok, cid, "Apa isi utama dokumen pertama itu?")
        assert final2.get("tool") in (None, "", "text"), f"expected normal reply, got tool={final2.get('tool')}"
        c2 = final2.get("content") or ""
        assert len(c2) > 20, "expected substantive reply referencing the document"

    def test_conv_workspace_search_endpoint(self, tok, persona_id):
        cid = _new_conv(tok, persona_id, "Iter23 conv-search")
        r = requests.post(f"{API}/conversations/{cid}/workspace-search", headers=H(tok),
                          json={"query": "kedai kopi"}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("count", 0) > 0
        assert isinstance(j.get("results"), list) and len(j["results"]) > 0
        # last assistant message should carry tool='workspace_search'
        time.sleep(0.5)
        m = requests.get(f"{API}/conversations/{cid}/messages", headers=H(tok), timeout=20)
        assert m.status_code == 200
        data = m.json()
        msgs = data.get("messages") if isinstance(data, dict) else data
        last_ast = [x for x in msgs if x.get("role") == "assistant"]
        assert last_ast, "no assistant messages after conv-search"
        assert last_ast[-1].get("tool") == "workspace_search"


# ========== Team delegation ==========
LONG_DELEGATION = ("Tolong susunkan rencana peluncuran produk aplikasi kasir UMKM: "
                   "riset kompetitor, positioning, rencana konten 3 bulan, anggaran, dan KPI.")


class TestTeamDelegation:
    def test_offer_includes_team_possible(self, tok, persona_id, persona_count):
        if persona_count < 2:
            pytest.skip("need >=2 personas to offer team")
        cid = _new_conv(tok, persona_id, "Iter23 team-offer")
        final = _send_sse(tok, cid, LONG_DELEGATION)
        assert final.get("tool") == "task_offer", f"wrong tool: {final.get('tool')}"
        pt = final.get("pending_task") or {}
        assert pt.get("team_possible") is True, f"team_possible should be True; pending_task={pt}"
        # keep for next test
        TestTeamDelegation._cid = cid

    def test_accept_team_and_poll(self, tok, persona_id, persona_count):
        if persona_count < 2:
            pytest.skip("need >=2 personas")
        cid = getattr(TestTeamDelegation, "_cid", None) or _new_conv(tok, persona_id, "Iter23 team-accept-fresh")
        if not getattr(TestTeamDelegation, "_cid", None):
            # need pending offer
            _send_sse(tok, cid, LONG_DELEGATION)

        r = requests.post(f"{API}/conversations/{cid}/tasks/accept", headers=H(tok),
                          json={"mode": "team"}, timeout=60)
        assert r.status_code == 200, r.text
        msg = r.json()
        assert msg.get("tool") == "task_assigned", f"expected tool task_assigned, got {msg}"
        parent_id = msg.get("task_id")
        assert parent_id

        # fetch parent task
        pr = requests.get(f"{API}/tasks/{parent_id}", headers=H(tok), timeout=20)
        assert pr.status_code == 200, pr.text
        parent = pr.json()
        assert parent.get("team") is True
        assert parent.get("status") in ("running", "scheduled", "assembling", "completed")
        subs = parent.get("subtasks") or []
        assert 2 <= len(subs) <= 5, f"unexpected subtasks len {len(subs)}: {subs}"
        personas_in_subs = {s.get("persona_name") for s in subs}
        assert len(personas_in_subs) >= 2, f"expected distinct personas, got {personas_in_subs}"

        # each child task reachable; parent_id matches
        for s in subs:
            cr = requests.get(f"{API}/tasks/{s['id']}", headers=H(tok), timeout=20)
            assert cr.status_code == 200, f"child {s['id']} not fetchable"
            child = cr.json()
            assert child.get("parent_id") == parent_id

        # Poll parent up to ~4 minutes
        deadline = time.time() + 240
        status = parent.get("status")
        final_output = parent.get("final_output") or ""
        while time.time() < deadline and status != "completed":
            time.sleep(10)
            pr = requests.get(f"{API}/tasks/{parent_id}", headers=H(tok), timeout=20)
            if pr.status_code != 200:
                continue
            parent = pr.json()
            status = parent.get("status")
            final_output = parent.get("final_output") or ""
            if status == "failed":
                pytest.fail(f"parent task failed: {parent.get('error')}")

        assert status == "completed", f"parent not completed after 4min; status={status}"
        assert len(final_output) > 100, f"final_output too short: {len(final_output)}"
        assert (parent.get("credits_used") or 0) > 0

        # Last conversation message should be task_done containing 'Tugas tim'
        m = requests.get(f"{API}/conversations/{cid}/messages", headers=H(tok), timeout=20)
        data = m.json()
        msgs = data.get("messages") if isinstance(data, dict) else data
        done = [x for x in msgs if x.get("role") == "assistant" and x.get("tool") == "task_done"]
        assert done, "no task_done message posted"
        assert "Tugas tim" in (done[-1].get("content") or "")

    def test_direct_assign_team_true(self, tok, persona_id, persona_count):
        if persona_count < 2:
            pytest.skip("need >=2 personas")
        cid = _new_conv(tok, persona_id, "Iter23 direct-team")
        r = requests.post(f"{API}/conversations/{cid}/tasks", headers=H(tok),
                          json={"title": "Ringkasan tren AI 2026",
                                "brief": "3 bagian: teknologi, bisnis, regulasi",
                                "team": True}, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        tid = j.get("task_id")
        assert tid, j
        assert isinstance(j.get("subtasks"), list)
        # parent task should be team=true
        pr = requests.get(f"{API}/tasks/{tid}", headers=H(tok), timeout=20)
        assert pr.status_code == 200
        parent = pr.json()
        assert parent.get("team") is True
        assert len(parent.get("subtasks") or []) >= 2
        # cleanup is NOT performed (keep for later inspection), but mark title as TEST_
