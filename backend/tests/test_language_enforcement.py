"""
Tests for Indonesian (Bahasa Indonesia) language enforcement across:
- Private persona reply
- Group persona replies
- Meeting Moderator per-turn summary
- Meeting Moderator live interjection (moderator_kind: interject)
- End-of-meeting /summary endpoint
"""
import os
import re
import json
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

EMAIL = "demo@aivora.ai"
PASSWORD = os.environ.get("TEST_PASSWORD", os.environ.get("TEST_ADMIN_PASSWORD", "demo123456"))
PRIVATE_CID = "ca8b4741-ebde-49f2-8ccc-eea69af65869"
GROUP_CID = "04d5c2c9-9b26-4d80-bc7e-2f1a15da7d1d"

INDO_PROMPT = "Halo, tolong jelaskan secara singkat apa manfaat olahraga pagi untuk kesehatan tubuh dan pikiran?"

# Common Indonesian stopwords/function words - presence indicates Bahasa Indonesia
ID_MARKERS = {
    "yang", "dan", "untuk", "dengan", "tidak", "adalah", "ini", "itu", "saya",
    "kita", "kamu", "anda", "kami", "akan", "dari", "pada", "atau", "juga",
    "bisa", "dapat", "sudah", "harus", "lebih", "sangat", "karena", "agar",
    "tentang", "sebagai", "serta", "oleh", "jika", "maka", "seperti", "banyak",
    "melakukan", "membantu", "menjaga", "terima", "kasih", "halo", "selamat",
    "sehat", "tubuh", "pikiran", "manfaat", "olahraga", "pagi",
}
# Common English words - presence indicates English leak
EN_MARKERS = {
    "the", "and", "for", "with", "this", "that", "you", "are", "have", "will",
    "your", "from", "they", "their", "which", "there", "about", "would", "could",
    "should", "because", "when", "what", "benefits", "morning", "exercise",
    "health", "body", "mind", "hello", "please", "between",
}


def _tokens(text: str):
    return [t.lower() for t in re.findall(r"[A-Za-zÀ-ÿ]+", text or "")]


def detect_lang(text: str):
    toks = _tokens(text)
    if not toks:
        return "empty", 0, 0
    id_hits = sum(1 for t in toks if t in ID_MARKERS)
    en_hits = sum(1 for t in toks if t in EN_MARKERS)
    return ("id" if id_hits >= en_hits else "en"), id_hits, en_hits


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in {r.json()}"
    return tok


@pytest.fixture(scope="session")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _ensure_id_setting(headers):
    # Make sure conversation_language is 'id'
    try:
        requests.patch(f"{BASE_URL}/api/me/settings", headers=headers,
                       json={"conversation_language": "id"}, timeout=15)
    except Exception:
        pass


def _stream_send(cid, content, headers, moderator=True, timeout=120):
    """POST /send and parse SSE events; return list of 'final' events (one per persona + optional moderator)."""
    r = requests.post(
        f"{BASE_URL}/api/conversations/{cid}/send",
        headers=headers,
        data=json.dumps({"content": content, "moderator": moderator}),
        stream=True,
        timeout=timeout,
    )
    assert r.status_code == 200, f"send failed {r.status_code}: {r.text[:400]}"
    finals = []
    buf = ""
    for raw in r.iter_lines(decode_unicode=True):
        if not raw:
            continue
        if raw.startswith("data: "):
            payload = raw[6:]
            try:
                evt = json.loads(payload)
            except Exception:
                continue
            if evt.get("final"):
                finals.append(evt)
    return finals


def test_private_persona_language(headers):
    _ensure_id_setting(headers)
    finals = _stream_send(PRIVATE_CID, INDO_PROMPT, headers, moderator=True)
    assert finals, "no final events received"
    for f in finals:
        content = f.get("content", "")
        lang, idh, enh = detect_lang(content)
        print(f"[private] persona={f.get('persona_name')} lang={lang} id_hits={idh} en_hits={enh} len={len(content)}")
        print(f"    preview: {content[:200]}")
        assert lang == "id", f"Private persona reply not in Indonesian. id={idh} en={enh}. Content: {content[:300]}"


def test_group_persona_language(headers):
    _ensure_id_setting(headers)
    finals = _stream_send(GROUP_CID, INDO_PROMPT, headers, moderator=True)
    assert len(finals) >= 2, f"expected >=2 persona finals in group, got {len(finals)}"
    for f in finals:
        if f.get("is_moderator"):
            continue
        content = f.get("content", "")
        lang, idh, enh = detect_lang(content)
        print(f"[group] persona={f.get('persona_name')} lang={lang} id={idh} en={enh}")
        print(f"    preview: {content[:200]}")
        assert lang == "id", f"Group persona {f.get('persona_name')} not Indonesian. id={idh} en={enh}: {content[:300]}"


@pytest.fixture(scope="session")
def fresh_meeting_cid(headers):
    # Need 2 persona ids - fetch user personas
    r = requests.get(f"{BASE_URL}/api/personas", headers=headers, timeout=20)
    assert r.status_code == 200, r.text
    personas = r.json()
    assert len(personas) >= 2, "need at least 2 personas"
    pids = [personas[0]["id"], personas[1]["id"]]
    r = requests.post(f"{BASE_URL}/api/conversations", headers=headers,
                      json={"persona_ids": pids, "type": "meeting", "title": "TEST_meeting_lang"}, timeout=20)
    assert r.status_code in (200, 201), r.text
    cid = r.json().get("id") or r.json().get("conversation", {}).get("id")
    assert cid, f"no cid in {r.json()}"
    return cid


def test_meeting_moderator_per_turn_summary_language(headers, fresh_meeting_cid):
    _ensure_id_setting(headers)
    finals = _stream_send(fresh_meeting_cid, INDO_PROMPT, headers, moderator=True)
    mod = [f for f in finals if f.get("is_moderator")]
    assert mod, f"no moderator final event received; got {[f.get('persona_name') for f in finals]}"
    content = mod[0].get("content", "")
    lang, idh, enh = detect_lang(content)
    print(f"[meeting-moderator-summary] lang={lang} id={idh} en={enh}")
    print(f"    preview: {content[:300]}")
    assert lang == "id", f"Meeting moderator summary not Indonesian. id={idh} en={enh}: {content[:300]}"


def test_meeting_moderator_interjection_language(headers, fresh_meeting_cid):
    _ensure_id_setting(headers)
    # Need even user-message count for interject to fire. The per-turn-summary test above already sent 1 user msg.
    # Send 1st moderator:false (user count=2 -> even -> interject)
    finals1 = _stream_send(fresh_meeting_cid, "Lanjutkan diskusi mengenai topik ini.", headers, moderator=False)
    interject1 = [f for f in finals1 if f.get("is_moderator") and f.get("moderator_kind") == "interject"]
    # Try one more if first didn't produce (depends on counter parity)
    if not interject1:
        finals2 = _stream_send(fresh_meeting_cid, "Beri pendapat tambahan.", headers, moderator=False)
        interject1 = [f for f in finals2 if f.get("is_moderator") and f.get("moderator_kind") == "interject"]
    assert interject1, "no moderator interjection event emitted after two moderator:false turns"
    content = interject1[0].get("content", "")
    lang, idh, enh = detect_lang(content)
    print(f"[meeting-moderator-interject] lang={lang} id={idh} en={enh}")
    print(f"    preview: {content[:300]}")
    assert lang == "id", f"Moderator interjection not Indonesian. id={idh} en={enh}: {content[:300]}"


def test_meeting_summary_endpoint_language(headers, fresh_meeting_cid):
    _ensure_id_setting(headers)
    r = requests.post(f"{BASE_URL}/api/conversations/{fresh_meeting_cid}/summary", headers=headers, timeout=60)
    assert r.status_code == 200, f"summary failed {r.status_code}: {r.text[:400]}"
    data = r.json()
    summary = data.get("summary") or data.get("content") or ""
    lang, idh, enh = detect_lang(summary)
    print(f"[meeting-summary-endpoint] lang={lang} id={idh} en={enh}")
    print(f"    preview: {summary[:300]}")
    assert summary, "empty summary"
    assert lang == "id", f"Summary endpoint reply not Indonesian. id={idh} en={enh}: {summary[:300]}"

    # Regression: a meeting_notes task should be created
    rt = requests.get(f"{BASE_URL}/api/tasks", headers=headers, timeout=20)
    if rt.status_code == 200:
        tasks = rt.json()
        has_mn = any(t.get("type") == "meeting_notes" for t in tasks)
        print(f"[meeting-summary-endpoint] meeting_notes task present: {has_mn} (total tasks={len(tasks)})")
        assert has_mn, "no meeting_notes task created after /summary"
