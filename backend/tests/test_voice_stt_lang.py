"""Voice STT language forcing (BUG regression).

Round-trip: TTS Indonesian text -> STT -> transcript must stay Indonesian.
Also verifies voices list and TTS validation.
"""
import os
import base64
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "demo@aivora.ai"
DEMO_PASSWORD = os.environ.get("TEST_DEMO_PASSWORD", os.environ.get("TEST_ADMIN_PASSWORD", "demo123456"))

ID_TEXT = "Halo, apa kabar hari ini? Aku ingin bercerita tentang pekerjaanku."
ID_KEYWORDS = ["halo", "apa", "kabar", "hari", "aku", "ingin", "tentang"]


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, timeout=20)
    if r.status_code != 200:
        # try register
        rr = requests.post(f"{API}/auth/register", json={
            "email": DEMO_EMAIL, "password": DEMO_PASSWORD, "name": "Demo"
        }, timeout=20)
        if rr.status_code not in (200, 201):
            pytest.skip(f"cannot auth demo user: login={r.status_code} register={rr.status_code}")
        tok = rr.json().get("token") or rr.json().get("access_token")
    else:
        tok = r.json().get("token") or r.json().get("access_token")
    assert tok, "no token"
    return tok


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_voices_list(headers) -> None:
    r = requests.get(f"{API}/voice/voices", headers=headers, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "voices" in data
    assert len(data["voices"]) == 9
    for v in ["alloy", "nova", "shimmer", "echo", "fable", "onyx", "coral", "sage", "ash"]:
        assert v in data["voices"]


def test_tts_empty_text_400(headers) -> None:
    r = requests.post(f"{API}/voice/tts", headers=headers, json={"text": "", "voice": "nova"}, timeout=15)
    assert r.status_code == 400


def test_tts_returns_audio(headers) -> None:
    r = requests.post(f"{API}/voice/tts", headers=headers,
                      json={"text": "Halo apa kabar", "voice": "nova"}, timeout=60)
    assert r.status_code == 200, r.text[:200]
    assert r.headers.get("content-type", "").startswith("audio/")
    assert len(r.content) > 1000


@pytest.fixture(scope="module")
def id_audio_b64(headers):
    r = requests.post(f"{API}/voice/tts", headers=headers,
                      json={"text": ID_TEXT, "voice": "nova"}, timeout=60)
    assert r.status_code == 200, r.text[:200]
    return base64.b64encode(r.content).decode()


def _assert_indonesian(text: str):
    low = text.lower()
    hits = [w for w in ID_KEYWORDS if w in low]
    assert len(hits) >= 3, f"transcript not Indonesian (hits={hits}): {text!r}"


def test_stt_defaults_to_indonesian_from_user_setting(headers, id_audio_b64) -> None:
    # No language in body -> should fallback to user.settings.conversation_language or 'id'
    r = requests.post(f"{API}/voice/transcribe", headers=headers,
                      json={"audio_b64": id_audio_b64, "filename": "audio.mp3"}, timeout=90)
    assert r.status_code == 200, r.text[:300]
    text = (r.json().get("text") or "").strip()
    assert text, "empty transcript"
    print(f"[default-lang] transcript: {text!r}")
    _assert_indonesian(text)


def test_stt_explicit_language_id(headers, id_audio_b64) -> None:
    r = requests.post(f"{API}/voice/transcribe", headers=headers,
                      json={"audio_b64": id_audio_b64, "filename": "audio.mp3", "language": "id"},
                      timeout=90)
    assert r.status_code == 200, r.text[:300]
    text = (r.json().get("text") or "").strip()
    assert text
    print(f"[lang=id] transcript: {text!r}")
    _assert_indonesian(text)


def test_stt_deducts_credits(headers, id_audio_b64) -> None:
    me1 = requests.get(f"{API}/auth/me", headers=headers, timeout=15).json()
    bal_before = int(me1.get("credits", 0))
    r = requests.post(f"{API}/voice/transcribe", headers=headers,
                      json={"audio_b64": id_audio_b64, "filename": "audio.mp3", "language": "id"},
                      timeout=90)
    assert r.status_code == 200
    me2 = requests.get(f"{API}/auth/me", headers=headers, timeout=15).json()
    bal_after = int(me2.get("credits", 0))
    assert bal_after <= bal_before - 1, f"credits not deducted: {bal_before} -> {bal_after}"
