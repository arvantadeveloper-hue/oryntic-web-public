"""seedance2video.io public API client: async text-to-video with polling. Videos are never kept on the platform — callers upload to the user's Drive."""
import asyncio
import math
import os
import httpx
from db import new_id
from pricing import RATES

BASE = "https://api.seedance2video.io/v1"
TIERS = {
    "2.0": {"model": "seedance-2.0-pro", "label": "Seedance 2.0", "rate_key": "video20_per_sec", "max_dur": 15},
    "2.5": {"model": "seedance-2.5", "label": "Seedance 2.5", "rate_key": "video_per_sec", "max_dur": 30},
}
MIN_DUR, DEFAULT_DUR = 4, 5


def configured() -> bool:
    return bool(os.environ.get("SEEDANCE_API_KEY"))


def _headers(extra=None) -> dict:
    h = {"Authorization": f"Bearer {os.environ['SEEDANCE_API_KEY']}", "Content-Type": "application/json"}
    h.update(extra or {})
    return h


def per_sec(tier: str) -> float:
    return float(RATES.get(TIERS[tier]["rate_key"]) or 0)


def quote(tier: str, duration: int) -> int:
    return max(1, math.ceil(per_sec(tier) * duration))


def clamp_duration(d) -> int:
    try:
        d = int(d)
    except (TypeError, ValueError):
        return DEFAULT_DUR
    return max(MIN_DUR, min(30, d))


def options(duration: int) -> list:
    """Both tiers with platform credits/sec and the total for this clip; a tier that cannot render this duration is flagged."""
    return [{"tier": t, "model": c["model"], "label": c["label"], "per_sec": round(per_sec(t), 2), "credits": quote(t, duration),
             "max_dur": c["max_dur"], "available": duration <= c["max_dur"]} for t, c in TIERS.items()]


async def generate(prompt: str, tier: str, duration: int, aspect_ratio: str = "16:9", resolution: str = "720p", timeout: int = 900) -> dict:
    """Submit and poll until done. Returns {video_url, provider_credits, generation_id}."""
    cfg = TIERS[tier]
    body = {"model": cfg["model"], "mode": "text-to-video", "prompt": prompt[:7000],
            "parameters": {"aspect_ratio": aspect_ratio, "resolution": resolution, "duration_seconds": int(duration)}}
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(f"{BASE}/videos", json=body, headers=_headers({"Idempotency-Key": new_id()}))
        if r.status_code >= 400:
            raise RuntimeError(f"Seedance {r.status_code}: {(r.json().get('detail') if 'json' in r.headers.get('content-type', '') else r.text)[:300]}")
        gen = r.json()
        status_url = gen.get("status_url") or f"{BASE}/generations/{gen['id']}"
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            st = (gen.get("status") or "").lower()
            if st == "completed":
                out = gen.get("output") or {}
                url = out.get("video_url") or ((out.get("urls") or [None])[0])
                if not url:
                    raise RuntimeError("Seedance completed without a video URL")
                return {"video_url": url, "provider_credits": int((gen.get("billing") or {}).get("cost_credits") or 0), "generation_id": gen.get("id")}
            if st in ("failed", "canceled"):
                raise RuntimeError(f"Seedance generation {st}")
            await asyncio.sleep(min(15, max(4, int(gen.get("retry_after_seconds") or 6))))
            s = await c.get(status_url, headers=_headers())
            if s.status_code >= 400:
                raise RuntimeError(f"Seedance poll {s.status_code}")
            gen = s.json()
    raise RuntimeError("Seedance generation timed out")


async def download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.content
