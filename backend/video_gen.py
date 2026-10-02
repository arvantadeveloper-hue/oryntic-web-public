import os
import time
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
# Fal Universal Key: queue inference through the Emergent proxy only, NOT Fal Platform APIs.
INTEGRATION_PROXY_BASE = os.environ.get("INTEGRATION_PROXY_URL", "https://integrations.emergentagent.com").rstrip("/")
CONTROL_BASE = f"{INTEGRATION_PROXY_BASE}/api/v1/fal"
QUEUE_ORIGIN = "https://queue.fal.run"
SEEDANCE_ENDPOINT = os.environ.get("SEEDANCE_ENDPOINT", "fal-ai/bytedance/seedance/v1/pro/text-to-video")


def _headers(extra=None):
    h = {"Authorization": f"Bearer {EMERGENT_LLM_KEY}", "Content-Type": "application/json"}
    if os.environ.get("job_id"):
        h["X-App-ID"] = os.environ["job_id"]
        h["X-Job-ID"] = os.environ["job_id"]
    if os.environ.get("run_id"):
        h["X-Environment-ID"] = os.environ["run_id"]
    if extra:
        h.update(extra)
    return h


def _run_media(endpoint_id: str, payload: dict, timeout_seconds: int = 420) -> dict:
    sub = requests.post(f"{CONTROL_BASE}/proxy",
                        headers=_headers({"X-Fal-Target-Url": f"{QUEUE_ORIGIN}/{endpoint_id}"}),
                        json=payload, timeout=60)
    if sub.status_code == 402:
        raise RuntimeError("Insufficient Universal Key credits")
    sub.raise_for_status()
    s = sub.json()
    status_url, response_url = s["status_url"], s["response_url"]
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        st = requests.get(status_url, headers=_headers(), timeout=30)
        st.raise_for_status()
        status = (st.json().get("status") or "").upper()
        if status in {"COMPLETED", "OK"}:
            res = requests.get(response_url, headers=_headers(), timeout=60)
            res.raise_for_status()
            return res.json()
        if status in {"FAILED", "CANCELLED", "CANCELED", "ERROR"}:
            raise RuntimeError(f"Video generation failed: {status}")
        time.sleep(3)
    raise RuntimeError("Timed out waiting for video generation")


def generate_seedance_video(prompt: str) -> str | None:
    """Blocking. Returns a temporary video URL or None. Call via asyncio.to_thread."""
    result = _run_media(SEEDANCE_ENDPOINT, {"prompt": prompt[:1500]})
    # Normalize common Fal output shapes
    if isinstance(result, dict):
        if result.get("video") and isinstance(result["video"], dict):
            return result["video"].get("url")
        if result.get("videos") and result["videos"]:
            return result["videos"][0].get("url")
        if result.get("url"):
            return result["url"]
    return None
