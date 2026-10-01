import os
import logging
import requests

logger = logging.getLogger("aivora.storage")

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "aivora"

storage_key = None


def init_storage(force: bool = False):
    """Call once at startup. Returns a session-scoped reusable storage_key."""
    global storage_key
    if storage_key and not force:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=180,
    )
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data, timeout=180,
        )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str):
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=120)
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=120)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


def store_remote_video(url: str, user_id: str, task_id: str) -> str | None:
    """Download a temporary remote video and persist it to object storage.
    Returns the permanent storage path, or None on failure."""
    try:
        r = requests.get(url, timeout=180, headers={"User-Agent": "Mozilla/5.0 (Oryntix)"})
        r.raise_for_status()
        ext = "mp4"
        ct = r.headers.get("Content-Type", "video/mp4")
        if "webm" in ct:
            ext = "webm"
        path = f"{APP_NAME}/videos/{user_id}/{task_id}.{ext}"
        result = put_object(path, r.content, "video/mp4" if ext == "mp4" else ct)
        return result["path"]
    except Exception as e:
        logger.error(f"store_remote_video failed: {e}")
        return None
