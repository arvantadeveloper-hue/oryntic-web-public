"""Iter 25 backend tests: team removal, gallery, change-password, files download, demo+budi login."""
import os
import pytest
import requests
import sys as _sys; _sys.path.insert(0, '/app/backend/tests')  # noqa: E702
from creds import DEMO_PASSWORD, ADMIN_PASSWORD, BUDI_PASSWORD  # noqa: E402,F401

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    return ln.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")

BASE = _load_backend_url()
API = f"{BASE}/api"

DEMO = {"email": "demo@aivora.ai", "password": DEMO_PASSWORD}
BUDI = {"email": "budi@aivora.ai", "password": BUDI_PASSWORD}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login {creds['email']} -> {r.status_code} {r.text}"
    tok = r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def demo_token():
    return _login(DEMO)


@pytest.fixture(scope="module")
def budi_token():
    return _login(BUDI)


def H(t):
    return {"Authorization": f"Bearer {t}"}


# ---- Team / workspace invite removal ----
def test_team_invites_removed(demo_token) -> None:
    r = requests.get(f"{API}/team/invites", headers=H(demo_token), timeout=20)
    assert r.status_code == 404, f"expected 404 got {r.status_code}"


def test_auth_workspaces_removed(demo_token) -> None:
    r = requests.get(f"{API}/auth/workspaces", headers=H(demo_token), timeout=20)
    assert r.status_code == 404


def test_admin_create_user_removed(demo_token) -> None:
    r = requests.post(f"{API}/admin/users", json={"email": "x@x.com", "password": "pw1234567", "name": "x"},
                      headers=H(demo_token), timeout=20)
    assert r.status_code in (404, 405), f"expected 404/405 got {r.status_code}"


# ---- Gallery ----
def test_gallery_default(demo_token) -> None:
    r = requests.get(f"{API}/gallery?limit=5", headers=H(demo_token), timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert "items" in j and "has_more" in j and "next_before" in j
    assert len(j["items"]) <= 5


def test_gallery_pagination(demo_token) -> None:
    r1 = requests.get(f"{API}/gallery?limit=5", headers=H(demo_token), timeout=30).json()
    if not r1.get("has_more"):
        pytest.skip("not enough items for pagination test")
    nb = r1["next_before"]
    assert nb
    r2 = requests.get(f"{API}/gallery?limit=5&before={nb}", headers=H(demo_token), timeout=30).json()
    ids1 = {i["id"] for i in r1["items"]}
    ids2 = {i["id"] for i in r2["items"]}
    assert ids1.isdisjoint(ids2), "page2 should not overlap page1"


def test_gallery_filter_image(demo_token) -> None:
    r = requests.get(f"{API}/gallery?type=image&limit=20", headers=H(demo_token), timeout=30)
    assert r.status_code == 200
    for it in r.json()["items"]:
        assert it["kind"] == "image", f"non-image in image filter: {it}"


def test_gallery_filter_document(demo_token) -> None:
    r = requests.get(f"{API}/gallery?type=document&limit=20", headers=H(demo_token), timeout=30)
    assert r.status_code == 200
    for it in r.json()["items"]:
        assert it["kind"] == "document"


# ---- Files download with ?auth=&download=1 ----
def test_file_download_header(demo_token) -> None:
    # find an image item that has a path
    r = requests.get(f"{API}/gallery?type=image&limit=10", headers=H(demo_token), timeout=30).json()
    paths = [i["path"] for i in r.get("items", []) if i.get("path")]
    if not paths:
        pytest.skip("no image file to test download header")
    p = paths[0]
    url = f"{API}/files/{p}?auth={demo_token}&download=1"
    rr = requests.get(url, timeout=30, stream=True)
    assert rr.status_code == 200, f"GET {url} -> {rr.status_code}"
    cd = rr.headers.get("content-disposition", "")
    assert "attachment" in cd.lower(), f"Content-Disposition missing attachment: {cd!r}"


def test_task_export_docx_header(demo_token) -> None:
    r = requests.get(f"{API}/gallery?type=document&limit=5", headers=H(demo_token), timeout=30).json()
    tasks = [i["task_id"] for i in r.get("items", []) if i.get("task_id")]
    if not tasks:
        pytest.skip("no document task available")
    tid = tasks[0]
    url = f"{API}/tasks/{tid}/export/docx?auth={demo_token}"
    rr = requests.get(url, timeout=30, stream=True)
    assert rr.status_code == 200
    cd = rr.headers.get("content-disposition", "")
    assert "attachment" in cd.lower()


# ---- Change password ----
def test_change_password_wrong_old(demo_token) -> None:
    r = requests.post(f"{API}/auth/change-password",
                      json={"current_password": "WRONG_PASSWORD_xxxx", "new_password": "NewPass!2026"},
                      headers=H(demo_token), timeout=20)
    assert r.status_code == 400, f"expected 400 got {r.status_code} {r.text}"


def test_change_password_roundtrip() -> None:
    """Change demo password then restore it."""
    tok = _login(DEMO)
    new_pw = "Demo!2026x"
    r = requests.post(f"{API}/auth/change-password",
                      json={"current_password": DEMO["password"], "new_password": new_pw},
                      headers=H(tok), timeout=20)
    assert r.status_code == 200, f"change -> {r.status_code} {r.text}"
    # login with new
    r2 = requests.post(f"{API}/auth/login", json={"email": DEMO["email"], "password": new_pw}, timeout=20)
    assert r2.status_code == 200, f"login new -> {r2.status_code}"
    tok2 = r2.json()["access_token"]
    # restore
    r3 = requests.post(f"{API}/auth/change-password",
                       json={"current_password": new_pw, "new_password": DEMO["password"]},
                       headers=H(tok2), timeout=20)
    assert r3.status_code == 200, f"restore -> {r3.status_code} {r3.text}"
    # verify restored
    r4 = requests.post(f"{API}/auth/login", json=DEMO, timeout=20)
    assert r4.status_code == 200, "demo password NOT restored!"


def test_budi_login_ok() -> None:
    r = requests.post(f"{API}/auth/login", json=BUDI, timeout=20)
    assert r.status_code == 200
