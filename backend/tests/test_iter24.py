"""Iter 24: forgot/reset password + delegation (named assistants) regression."""
import os
from tests.creds import DEMO_EMAIL, DEMO_PASSWORD, BUDI_EMAIL, BUDI_PASSWORD
import requests
import pytest

_env = os.environ.get("REACT_APP_BACKEND_URL")
if not _env:
    # Read from frontend/.env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                _env = line.split("=", 1)[1].strip()
                break
BASE = _env.rstrip("/")
API = f"{BASE}/api"


@pytest.fixture(scope="session")
def demo_token():
    r = requests.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_login_demo_ok() -> None:
    r = requests.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert r.status_code == 200
    assert r.json().get("access_token")


def test_forgot_unknown_email_no_leak() -> None:
    r = requests.post(f"{API}/auth/forgot-password", json={"email": "nobody-xyz-12345@example.com"})
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True
    # Should NOT leak debug_link for unknown emails
    assert "debug_link" not in d or d.get("debug_link") in (None, "")


def test_reset_password_bad_token() -> None:
    r = requests.post(f"{API}/auth/reset-password", json={"token": "totallybogus", "password": "whatever123"})
    assert r.status_code == 400


def test_forgot_budi_returns_debug_link() -> None:
    r = requests.post(f"{API}/auth/forgot-password", json={"email": BUDI_EMAIL})
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True
    # EMAIL_DEBUG_LINKS=true in preview
    assert d.get("debug_link"), f"expected debug_link in {d}"
    assert "token=" in d["debug_link"]


def test_full_reset_flow_and_restore() -> None:
    # 1) forgot
    r = requests.post(f"{API}/auth/forgot-password", json={"email": BUDI_EMAIL})
    assert r.status_code == 200
    link = r.json()["debug_link"]
    token = link.split("token=")[-1].split("&")[0]
    # 2) reset to new password
    r2 = requests.post(f"{API}/auth/reset-password", json={"token": token, "password": BUDI_PASSWORD})
    assert r2.status_code == 200, r2.text
    assert r2.json().get("access_token")
    # 3) login with (restored) password
    r3 = requests.post(f"{API}/auth/login", json={"email": BUDI_EMAIL, "password": BUDI_PASSWORD})
    assert r3.status_code == 200


def test_delegation_named_assistants(demo_token) -> None:
    H = {"Authorization": f"Bearer {demo_token}"}
    # Rio persona id provided
    cid_resp = requests.post(
        f"{API}/conversations",
        headers=H,
        json={"type": "private", "persona_ids": ["e93a66a6-59b1-4a12-8c16-0c9dba6c3348"]},
    )
    assert cid_resp.status_code == 200, cid_resp.text
    cid = cid_resp.json()["id"]

    task_payload = {
        "title": "Proposal ekspansi cabang Bandung",
        "brief": "Proposal lengkap: studi kelayakan, anggaran, rencana IT, timeline.",
        "assignments": [
            {"assistant": "Nova", "part": "anggaran dan keuangan"},
            {"assistant": "Dimas", "part": "rencana IT"},
        ],
    }
    r = requests.post(f"{API}/conversations/{cid}/tasks", headers=H, json=task_payload, timeout=180)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "subtasks" in data, data
    subs = data["subtasks"]
    assert isinstance(subs, list) and len(subs) >= 1
    # subtasks response is list of strings "{persona_name}: {title}"
    nova_strs = [s for s in subs if isinstance(s, str) and s.lower().startswith("nova:")]
    assert nova_strs, f"No Nova subtask: {subs}"
    assert any(("anggaran" in s.lower() or "keuangan" in s.lower() or "finance" in s.lower()) for s in nova_strs), f"Nova not on finance: {nova_strs}"

    # unmatched_assistants should contain Dimas
    unmatched = data.get("unmatched_assistants") or []
    assert any(str(x).lower() == "dimas" for x in unmatched), f"unmatched_assistants missing Dimas: {unmatched}"

    # pinned flag
    task_id = data.get("task_id") or data.get("id")
    assert task_id
    r2 = requests.get(f"{API}/tasks/{task_id}", headers=H)
    assert r2.status_code == 200, r2.text
    td = r2.json()
    subs2 = td.get("subtasks", [])
    pinned = [s for s in subs2 if s.get("pinned")]
    assert len(pinned) >= 1
    for s in pinned:
        nm = (s.get("assignee_name") or s.get("persona_name") or "").lower()
        assert nm == "nova", f"pinned subtask not Nova: {s}"
    # Save task_id to a file for optional frontend check
    with open("/tmp/iter24_task_id.txt", "w") as f:
        f.write(task_id)
