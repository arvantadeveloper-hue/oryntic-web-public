"""seedance2video.io public API client: async text-to-video with polling. Videos are never kept on the platform — callers upload to the user's Drive."""
import asyncio
import math
import os
import httpx
from typing import Optional
from db import new_id
from pricing import RATES

BASE = "https://api.seedance2video.io/v1"
TIERS = {
    "2.0": {"model": "seedance-2.0-pro", "label": "Seedance 2.0", "rate_key": "video20_per_sec", "max_dur": 15, "resolutions": ["480p", "720p", "1080p"], "real_person": True, "audio": True},
    "2.5": {"model": "seedance-2.5", "label": "Seedance 2.5", "rate_key": "video_per_sec", "max_dur": 30, "resolutions": ["480p", "720p", "1080p"], "real_person": False, "audio": True},
}
RESOLUTIONS = {"480p": "480p Hemat", "720p": "720p Standar", "1080p": "1080p Tajam"}
MIN_DUR, DEFAULT_DUR = 4, 5
ASPECTS = {"16:9": "Landscape 16:9 (YouTube)", "9:16": "Portrait 9:16 (Reels/Shorts/TikTok)", "1:1": "Persegi 1:1 (feed Instagram)", "4:3": "4:3", "3:4": "3:4", "21:9": "Sinematik 21:9"}


def configured() -> bool:
    return bool(os.environ.get("SEEDANCE_API_KEY"))


def _headers(extra=None) -> dict:
    h = {"Authorization": f"Bearer {os.environ['SEEDANCE_API_KEY']}", "Content-Type": "application/json"}
    h.update(extra or {})
    return h


def per_sec(tier: str) -> float:
    return float(RATES.get(TIERS[tier]["rate_key"]) or 0)


def multipliers() -> dict:
    return {"res": dict(RATES.get("video_res_mult") or {"480p": 0.6, "720p": 1.0, "1080p": 1.6}), "real_person": float(RATES.get("video_real_person_mult") or 1.45), "audio": float(RATES.get("video_audio_mult") or 1.0)}


def quote(tier: str, duration: int, resolution: str = "720p", real_person: bool = False, audio: bool = False) -> int:
    m = multipliers()
    return max(1, math.ceil(per_sec(tier) * duration * m["res"].get(resolution, 1.0) * (m["real_person"] if real_person else 1.0) * (m["audio"] if audio else 1.0)))


def supports(tier: str, duration: int, resolution: str = "720p", real_person: bool = False, audio: bool = False) -> bool:
    c = TIERS[tier]
    return duration <= c["max_dur"] and resolution in c["resolutions"] and (not real_person or c["real_person"]) and (not audio or c.get("audio", False))


def clamp_duration(d) -> int:
    try:
        d = int(d)
    except (TypeError, ValueError):
        return DEFAULT_DUR
    return max(MIN_DUR, min(30, d))


def options(duration: int, resolution: str = "720p", real_person: bool = False, audio: bool = False) -> list:
    """Both tiers with platform credits/sec (720p normal) and the total for this clip at the chosen options; unsupported combos are flagged."""
    return [{"tier": t, "model": c["model"], "label": c["label"], "per_sec": round(per_sec(t), 2), "credits": quote(t, duration, resolution, real_person, audio),
             "max_dur": c["max_dur"], "resolutions": c["resolutions"], "real_person": c["real_person"], "audio": c.get("audio", False),
             "available": supports(t, duration, resolution, real_person, audio)} for t, c in TIERS.items()]


async def generate(prompt: str, tier: str, duration: int, aspect_ratio: str = "16:9", resolution: str = "720p", timeout: int = 900, image_url: Optional[str] = None, real_person: bool = False, consent_ref: str = "", generate_audio: bool = False) -> dict:
    """Submit and poll until done. image_url (public HTTPS on a Key-approved host) switches to image-to-video. Returns {video_url, provider_credits, generation_id}."""
    cfg = TIERS[tier]
    body = {"model": cfg["model"], "mode": "image-to-video" if image_url else "text-to-video", "prompt": prompt[:7000],
            "parameters": {"aspect_ratio": aspect_ratio, "resolution": resolution, "duration_seconds": int(duration)}}
    if generate_audio:
        body["parameters"]["generate_audio"] = True
    if image_url:
        body["inputs"] = [{"type": "image", "url": image_url}]
    if real_person and image_url:
        body["parameters"]["real_person_mode"] = True
        body["compliance"] = {"rights_confirmed": True, "consent_reference": consent_ref or new_id()}
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
