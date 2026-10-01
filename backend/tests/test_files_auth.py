"""Test /api/files auth matrix for Aivora."""
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ai-companion-test-5.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "demo@aivora.ai"
DEMO_PASSWORD = os.environ.get("TEST_DEMO_PASSWORD", os.environ.get("TEST_ADMIN_PASSWORD", "demo123456"))
DEMO_USER_ID = "fb1a64ce-ff1c-4376-b090-e90b286a5024"
DEMO_PATH = f"aivora/videos/{DEMO_USER_ID}/demo.mp4"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"], r.json()["user"]["id"]


def test_files_requires_auth():
    r = requests.get(f"{API}/files/{DEMO_PATH}", timeout=30)
    assert r.status_code == 401, r.text


def test_files_valid_token_200():
    token, uid = _login(DEMO_EMAIL, DEMO_PASSWORD)
    assert uid == DEMO_USER_ID
    r = requests.get(f"{API}/files/{DEMO_PATH}?auth={token}", timeout=30)
    assert r.status_code == 200, r.text
    assert len(r.content) > 0


def test_files_wrong_user_403():
    # register fresh user, use their token to access DEMO path -> 403
    import uuid
    email = f"TEST_filesuser_{uuid.uuid4().hex[:8]}@aivora.ai"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Testpass123!", "name": "F"}, timeout=30)
    assert r.status_code == 200
    tok = r.json()["access_token"]
    r = requests.get(f"{API}/files/{DEMO_PATH}?auth={tok}", timeout=30)
    assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text}"


def test_files_bearer_header_also_works():
    token, _ = _login(DEMO_EMAIL, DEMO_PASSWORD)
    r = requests.get(f"{API}/files/{DEMO_PATH}", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    assert r.status_code == 200
