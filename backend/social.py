"""Social Media (phase 1): users connect THEIR OWN LinkedIn / Meta (Facebook Page + Instagram) / YouTube accounts via OAuth
(Oryntix only provides the developer app from .env). Publish text/image/video, log every post for the Social Media menu."""
import asyncio
import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx
import jwt
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query, Form, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from pydantic import BaseModel, Field
from db import db, now_iso, new_id
from auth import current_user, JWT_SECRET
from storage import get_object

router = APIRouter(prefix="/api/social", tags=["social"])
_fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(("social:" + JWT_SECRET).encode()).digest()))
PROVIDERS = {
    "linkedin": {"label": "LinkedIn", "env": ("LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"), "kinds": ["text", "image"],
                 "auth": "https://www.linkedin.com/oauth/v2/authorization", "token": "https://www.linkedin.com/oauth/v2/accessToken", "scope": "openid profile w_member_social"},
    "meta": {"label": "Facebook Page & Instagram", "env": ("META_APP_ID", "META_APP_SECRET"), "kinds": ["text", "image", "video"],
             "auth": "https://www.facebook.com/v21.0/dialog/oauth", "token": "https://graph.facebook.com/v21.0/oauth/access_token",
             "scope": "pages_show_list,pages_manage_posts,pages_read_engagement,instagram_basic,instagram_content_publish"},
    "youtube": {"label": "YouTube", "env": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"), "kinds": ["video"],
                "auth": "https://accounts.google.com/o/oauth2/v2/auth", "token": "https://oauth2.googleapis.com/token", "scope": "https://www.googleapis.com/auth/youtube.upload openid email"},
}


def configured(p: str) -> bool:
    return all(os.environ.get(k, "").strip() for k in PROVIDERS[p]["env"])


def _creds(p: str) -> tuple:
    return tuple(os.environ[k] for k in PROVIDERS[p]["env"])


def _enc(s: str) -> str:
    return _fernet.encrypt(s.encode()).decode()


def _dec(s: str) -> str:
    return _fernet.decrypt(s.encode()).decode()


def file_sig(path: str, ttl: int = 3600) -> str:
    return jwt.encode({"purpose": "file", "path": path, "exp": int(time.time()) + ttl}, JWT_SECRET, algorithm="HS256")


def verify_file_sig(path: str, sig: str) -> bool:
    try:
        d = jwt.decode(sig, JWT_SECRET, algorithms=["HS256"])
        return d.get("purpose") == "file" and d.get("path") == path
    except Exception:
        return False


def public_media_url(base: str, path: str) -> str:
    return f"{base}/api/files/{path}?sig={file_sig(path)}"


def drive_sig(uid: str, file_id: str, ttl: int = 3600) -> str:
    return jwt.encode({"purpose": "drive", "uid": uid, "file_id": file_id, "exp": int(time.time()) + ttl}, JWT_SECRET, algorithm="HS256")


def verify_drive_sig(file_id: str, sig: str) -> Optional[str]:
    """Returns the owning user id when the signed Drive link is valid."""
    try:
        d = jwt.decode(sig, JWT_SECRET, algorithms=["HS256"])
        return d.get("uid") if d.get("purpose") == "drive" and d.get("file_id") == file_id else None
    except Exception:
        return None


def public_drive_url(base: str, uid: str, file_id: str) -> str:
    return f"{base}/api/integrations/google/public/{file_id}?sig={drive_sig(uid, file_id)}"


async def media_bytes(uid: str, x) -> tuple:
    """(bytes, content_type) of the media to publish — platform storage path or the user's Google Drive file."""
    if getattr(x, "drive_id", None):
        from integrations import drive_bytes
        return await drive_bytes(uid, x.drive_id)
    return await asyncio.to_thread(get_object, x.media_path)


# ---------- accounts ----------
async def accounts(uid: str) -> list:
    rows = {r["provider"]: r async for r in db.social_accounts.find({"user_id": uid}, {"_id": 0, "access_token": 0, "refresh_token": 0})}
    return [{"id": p, "label": v["label"], "kinds": v["kinds"], "configured": configured(p), "connected": p in rows, **{k: rows[p].get(k) for k in ("account_name", "account_picture", "pages", "connected_at") if p in rows}} for p, v in PROVIDERS.items()]


@router.get("/accounts")
async def list_accounts(u: dict = Depends(current_user)):
    return {"items": await accounts(u["id"])}


@router.get("/{provider}/start")
async def start(provider: str, redirect_uri: str = Query(min_length=10), app_url: str = Query(min_length=8), u: dict = Depends(current_user)):
    if provider not in PROVIDERS or not configured(provider):
        raise HTTPException(400, "Integrasi ini belum dikonfigurasi oleh platform.")
    cid, _ = _creds(provider)
    state = jwt.encode({"purpose": "social", "p": provider, "uid": u["id"], "redirect_uri": redirect_uri, "app_url": app_url, "exp": int(time.time()) + 600}, JWT_SECRET, algorithm="HS256")
    q = {"client_id": cid, "redirect_uri": redirect_uri, "response_type": "code", "scope": PROVIDERS[provider]["scope"], "state": state}
    if provider == "youtube":
        q.update({"access_type": "offline", "prompt": "consent"})
    return {"url": f"{PROVIDERS[provider]['auth']}?{httpx.QueryParams(q)}"}


async def _exchange(provider: str, code: str, redirect_uri: str) -> dict:
    cid, sec = _creds(provider)
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(PROVIDERS[provider]["token"], data={"code": code, "client_id": cid, "client_secret": sec, "redirect_uri": redirect_uri, "grant_type": "authorization_code"})
    if r.status_code != 200:
        raise HTTPException(400, f"Pertukaran token gagal: {r.text[:200]}")
    return r.json()


async def _profile(provider: str, tok: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as c:
        if provider == "linkedin":
            me = (await c.get("https://api.linkedin.com/v2/userinfo", headers={"Authorization": f"Bearer {tok}"})).json()
            return {"account_id": me.get("sub"), "account_name": me.get("name"), "account_picture": me.get("picture")}
        if provider == "meta":
            me = (await c.get("https://graph.facebook.com/v21.0/me", params={"access_token": tok, "fields": "id,name,picture"})).json()
            pages = (await c.get("https://graph.facebook.com/v21.0/me/accounts", params={"access_token": tok, "fields": "id,name,access_token,instagram_business_account{id,username}"})).json().get("data", [])
            return {"account_id": me.get("id"), "account_name": me.get("name"), "account_picture": ((me.get("picture") or {}).get("data") or {}).get("url"),
                    "pages": [{"id": p["id"], "name": p["name"], "token": _enc(p["access_token"]), "ig_id": (p.get("instagram_business_account") or {}).get("id"), "ig_username": (p.get("instagram_business_account") or {}).get("username")} for p in pages]}
        me = (await c.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "snippet", "mine": "true"}, headers={"Authorization": f"Bearer {tok}"})).json()
        ch = (me.get("items") or [{}])[0]
        return {"account_id": ch.get("id"), "account_name": (ch.get("snippet") or {}).get("title"), "account_picture": (((ch.get("snippet") or {}).get("thumbnails") or {}).get("default") or {}).get("url")}


@router.get("/callback")
async def callback(code: str = Query(...), state: str = Query(...)):
    try:
        st = jwt.decode(state, JWT_SECRET, algorithms=["HS256"])
        assert st.get("purpose") == "social"
    except Exception as e:
        raise HTTPException(400, "State tidak valid") from e
    provider, uid = st["p"], st["uid"]
    tok = await _exchange(provider, code, st["redirect_uri"])
    prof = await _profile(provider, tok["access_token"])
    await db.social_accounts.update_one({"user_id": uid, "provider": provider}, {"$set": {"user_id": uid, "provider": provider, "access_token": _enc(tok["access_token"]),
                                         "refresh_token": _enc(tok["refresh_token"]) if tok.get("refresh_token") else None, "expires_at": time.time() + int(tok.get("expires_in") or 3600) - 60,
                                         **prof, "connected_at": now_iso()}}, upsert=True)
    return RedirectResponse(f"{st['app_url']}/social?connected={provider}")


@router.delete("/{provider}")
async def disconnect(provider: str, u: dict = Depends(current_user)):
    await db.social_accounts.delete_one({"user_id": u["id"], "provider": provider})
    return {"ok": True}


async def _token(uid: str, provider: str) -> dict:
    acc = await db.social_accounts.find_one({"user_id": uid, "provider": provider}, {"_id": 0})
    if not acc:
        raise HTTPException(400, f"{PROVIDERS[provider]['label']} belum terhubung.")
    if provider == "youtube" and acc.get("refresh_token") and time.time() > float(acc.get("expires_at") or 0):
        cid, sec = _creds(provider)
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(PROVIDERS[provider]["token"], data={"refresh_token": _dec(acc["refresh_token"]), "client_id": cid, "client_secret": sec, "grant_type": "refresh_token"})
        if r.status_code == 200:
            acc["access_token"] = _enc(r.json()["access_token"])
            await db.social_accounts.update_one({"user_id": uid, "provider": provider}, {"$set": {"access_token": acc["access_token"], "expires_at": time.time() + int(r.json().get("expires_in") or 3600) - 60}})
    acc["token"] = _dec(acc["access_token"])
    return acc


# ---------- publishing ----------
class PublishIn(BaseModel):
    providers: list[str] = Field(min_length=1, max_length=3)
    kind: str = Field(pattern="^(text|image|video)$")
    text: str = Field(default="", max_length=3000)
    title: str = Field(default="", max_length=100)
    media_path: Optional[str] = Field(default=None, max_length=500)
    drive_id: Optional[str] = Field(default=None, max_length=200)
    page_id: Optional[str] = None
    to_instagram: bool = True
    app_url: str = Field(min_length=8, max_length=300)
    source: Optional[dict] = None


async def _publish_linkedin(acc: dict, x: PublishIn, uid: str) -> dict:
    h = {"Authorization": f"Bearer {acc['token']}", "X-Restli-Protocol-Version": "2.0.0", "LinkedIn-Version": "202409", "Content-Type": "application/json"}
    author = f"urn:li:person:{acc['account_id']}"
    body = {"author": author, "commentary": x.text or x.title, "visibility": "PUBLIC", "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []}, "lifecycleState": "PUBLISHED"}
    async with httpx.AsyncClient(timeout=60) as c:
        if x.kind == "image" and x.media_path:
            init = await c.post("https://api.linkedin.com/rest/images?action=initializeUpload", headers=h, json={"initializeUploadRequest": {"owner": author}})
            v = init.json().get("value") or {}
            data, ctype = await media_bytes(uid, x)
            await c.put(v["uploadUrl"], content=data, headers={"Content-Type": ctype})
            body["content"] = {"media": {"id": v["image"], "altText": x.title or "image"}}
        r = await c.post("https://api.linkedin.com/rest/posts", headers=h, json=body)
    if r.status_code not in (200, 201):
        raise HTTPException(502, f"LinkedIn menolak: {r.text[:200]}")
    pid = r.headers.get("x-restli-id") or r.headers.get("x-linkedin-id") or ""
    return {"post_id": pid, "post_url": f"https://www.linkedin.com/feed/update/{pid}" if pid else "https://www.linkedin.com/feed/"}


async def _publish_meta(acc: dict, x: PublishIn, base: str, uid: str) -> dict:
    pages = acc.get("pages") or []
    page = next((p for p in pages if p["id"] == x.page_id), pages[0] if pages else None)
    if not page:
        raise HTTPException(400, "Tidak ada Halaman Facebook pada akun ini (Instagram memerlukan akun Business yang terhubung ke Halaman).")
    ptok = _dec(page["token"])
    url = public_drive_url(base, uid, x.drive_id) if x.drive_id else public_media_url(base, x.media_path) if x.media_path else None
    out = {}
    async with httpx.AsyncClient(timeout=120) as c:
        if x.kind == "text":
            r = await c.post(f"https://graph.facebook.com/v21.0/{page['id']}/feed", data={"message": x.text, "access_token": ptok})
        elif x.kind == "image":
            r = await c.post(f"https://graph.facebook.com/v21.0/{page['id']}/photos", data={"url": url, "caption": x.text, "access_token": ptok})
        else:
            r = await c.post(f"https://graph.facebook.com/v21.0/{page['id']}/videos", data={"file_url": url, "description": x.text, "title": x.title, "access_token": ptok})
        if r.status_code != 200:
            raise HTTPException(502, f"Facebook menolak: {r.text[:200]}")
        fid = r.json().get("post_id") or r.json().get("id")
        out.update({"post_id": fid, "post_url": f"https://www.facebook.com/{fid}"})
        if x.to_instagram and page.get("ig_id") and x.kind in ("image", "video") and url:
            params = {"caption": x.text, "access_token": ptok, **({"image_url": url} if x.kind == "image" else {"video_url": url, "media_type": "REELS"})}
            cr = await c.post(f"https://graph.facebook.com/v21.0/{page['ig_id']}/media", data=params)
            if cr.status_code == 200:
                for _ in range(20 if x.kind == "video" else 1):  # videos need processing before publish
                    pr = await c.post(f"https://graph.facebook.com/v21.0/{page['ig_id']}/media_publish", data={"creation_id": cr.json()["id"], "access_token": ptok})
                    if pr.status_code == 200:
                        out["instagram_post_id"] = pr.json().get("id")
                        out["instagram_url"] = f"https://www.instagram.com/{page.get('ig_username') or ''}"
                        break
                    await asyncio.sleep(5)
            else:
                out["instagram_error"] = cr.text[:200]
    return out


async def _publish_youtube(acc: dict, x: PublishIn, uid: str) -> dict:
    if not (x.media_path or x.drive_id):
        raise HTTPException(400, "YouTube memerlukan file video.")
    data, ctype = await media_bytes(uid, x)
    if not (ctype or "").startswith("video/"):
        ctype = "video/mp4"
    meta = {"snippet": {"title": (x.title or x.text or "Video Oryntix")[:100], "description": x.text[:5000]}, "status": {"privacyStatus": "public"}}
    async with httpx.AsyncClient(timeout=300) as c:
        init = await c.post("https://www.googleapis.com/upload/youtube/v3/videos", params={"uploadType": "resumable", "part": "snippet,status"},
                            headers={"Authorization": f"Bearer {acc['token']}", "Content-Type": "application/json", "X-Upload-Content-Type": ctype, "X-Upload-Content-Length": str(len(data))}, json=meta)
        if init.status_code != 200:
            raise HTTPException(502, f"YouTube menolak: {init.text[:200]}")
        r = await c.put(init.headers["Location"], content=data, headers={"Content-Type": ctype})
    if r.status_code not in (200, 201):
        raise HTTPException(502, f"Unggah YouTube gagal: {r.text[:200]}")
    vid = r.json().get("id")
    return {"post_id": vid, "post_url": f"https://youtu.be/{vid}"}


async def publish(uid: str, x: PublishIn) -> list:
    """Publish to each provider; always log the attempt (status sent|failed) for the Social Media menu."""
    results = []
    for p in x.providers:
        if p not in PROVIDERS:
            continue
        rec = {"id": new_id(), "user_id": uid, "provider": p, "kind": x.kind, "text": x.text, "title": x.title, "media_path": x.media_path, "drive_id": x.drive_id, "status": "sent", "source": x.source, "created_at": now_iso()}
        try:
            if x.kind not in PROVIDERS[p]["kinds"]:
                raise HTTPException(400, f"{PROVIDERS[p]['label']} tidak mendukung konten {x.kind}.")
            acc = await _token(uid, p)
            rec["account_name"] = acc.get("account_name")
            res = await (_publish_linkedin(acc, x, uid) if p == "linkedin" else _publish_meta(acc, x, x.app_url, uid) if p == "meta" else _publish_youtube(acc, x, uid))
            rec.update(res)
        except HTTPException as e:
            rec.update(status="failed", error=str(e.detail))
        except Exception as e:  # network / provider surprises
            rec.update(status="failed", error=str(e)[:200])
        await db.social_posts.insert_one(dict(rec))
        results.append({k: v for k, v in rec.items() if k != "_id"})
    return results


@router.post("/publish")
async def publish_endpoint(x: PublishIn, u: dict = Depends(current_user)):
    return {"results": await publish(u["id"], x)}


# ---------- scheduled posts (chat: "posting besok jam 9 ke LinkedIn") ----------
LABEL = {p: v["label"] for p, v in PROVIDERS.items()}


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "_id"}


REPEATS = ("none", "daily", "weekly")
HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]


def user_tz(user: dict):
    from zoneinfo import ZoneInfo
    tz = (user.get("settings") or {}).get("timezone") or "Asia/Jakarta"
    try:
        return ZoneInfo(tz)
    except Exception:
        return ZoneInfo("Asia/Jakarta")


def when_label(dt) -> str:
    """Local datetime → 'Senin, 3 Juni 2026 08:00 (Asia/Jakarta)'."""
    return f"{HARI[dt.weekday()]}, {dt.day} {BULAN[dt.month - 1]} {dt.year} {dt:%H:%M} ({dt.tzinfo})"


def repeat_label(repeat: str, dt) -> str:
    if repeat == "daily":
        return f"setiap hari {dt:%H:%M}"
    if repeat == "weekly":
        return f"setiap {HARI[dt.weekday()]} {dt:%H:%M}"
    return ""


async def schedule_post(uid: str, x: PublishIn, when_utc: str, label: str, meta: Optional[dict] = None, repeat: str = "none", tz: str = "Asia/Jakarta") -> dict:
    repeat = repeat if repeat in REPEATS else "none"
    job = {"id": new_id(), "user_id": uid, "status": "scheduled", "scheduled_at": when_utc, "scheduled_label": label, "payload": x.model_dump(),
           "providers": x.providers, "kind": x.kind, "text": x.text, "media_path": x.media_path, "repeat": repeat, "tz": tz, **(meta or {}), "created_at": now_iso()}
    if repeat != "none":
        job["series_id"] = job.get("series_id") or job["id"]
        job["repeat_label"] = repeat_label(repeat, datetime.fromisoformat(when_utc).astimezone(user_tz({"settings": {"timezone": tz}})))
    await db.social_schedules.insert_one(dict(job))
    return job


async def _schedule_next(job: dict):
    """Repeating series: the next occurrence is created right after this one ran (same wall-clock time in the user's timezone)."""
    if job.get("repeat") not in ("daily", "weekly"):
        return
    z = user_tz({"settings": {"timezone": job.get("tz") or "Asia/Jakarta"}})
    nxt = datetime.fromisoformat(job["scheduled_at"]).astimezone(z)
    step = timedelta(days=1 if job["repeat"] == "daily" else 7)
    while nxt <= datetime.now(timezone.utc):
        nxt = (nxt + step).replace(tzinfo=z)
    meta = {k: job[k] for k in ("conversation_id", "persona_id", "persona_name", "portrait", "series_id") if job.get(k)}
    await schedule_post(job["user_id"], PublishIn(**job["payload"]), nxt.astimezone(timezone.utc).isoformat(), when_label(nxt), meta, job["repeat"], str(z))


def results_text(res: list) -> str:
    lines = []
    for r in res:
        lab = LABEL.get(r["provider"], r["provider"])
        if r["status"] == "sent":
            lines.append(f"- **{lab}**: terkirim — [lihat post]({r.get('post_url')})" + (f" · [Instagram]({r['instagram_url']})" if r.get("instagram_url") else ""))
        else:
            lines.append(f"- **{lab}**: gagal — {r.get('error') or 'tidak diketahui'}")
    return "\n".join(lines)


async def social_tick():
    """Scheduler: publish due jobs once (claim → run → record), then tell the user in the originating chat + notification."""
    now_s = datetime.now(timezone.utc).isoformat()
    async for job in db.social_schedules.find({"status": "scheduled", "scheduled_at": {"$lte": now_s}}, {"_id": 0}):
        claimed = await db.social_schedules.update_one({"id": job["id"], "status": "scheduled"}, {"$set": {"status": "running"}})
        if not claimed.modified_count:
            continue
        err = ""
        try:
            res = await publish(job["user_id"], PublishIn(**job["payload"]))
            status = "sent" if res and all(r["status"] == "sent" for r in res) else ("failed" if not res or all(r["status"] != "sent" for r in res) else "partial")
        except Exception as e:
            res, status, err = [], "failed", str(getattr(e, "detail", e))[:200]
        await db.social_schedules.update_one({"id": job["id"]}, {"$set": {"status": status, "results": res, "error": err, "ran_at": now_iso()}})
        try:
            await _schedule_next(job)
        except Exception as e:
            err = (err + f" (jadwal berikutnya gagal dibuat: {e})")[:300]
        rep = f"\n\n🔁 Jadwal berulang **{job['repeat_label']}** — posting berikutnya sudah disiapkan." if job.get("repeat") in ("daily", "weekly") else ""
        text = (f"Posting terjadwal ({job.get('scheduled_label') or job['scheduled_at']}) sudah dijalankan:\n" + (results_text(res) if res else f"- gagal — {err}")
                + rep + "\n\nRiwayat lengkap ada di menu [Social Media](/social).")
        if job.get("conversation_id"):
            await db.messages.insert_one({"id": new_id(), "conversation_id": job["conversation_id"], "role": "assistant", "content": text, "persona_id": job.get("persona_id"),
                                          "persona_name": job.get("persona_name"), "portrait": job.get("portrait"), "credits": 0, "tool": "social_publish", "created_at": now_iso()})
            await db.conversations.update_one({"id": job["conversation_id"]}, {"$set": {"updated_at": now_iso(), "last_message": text[:120]}})
            from realtime import notify_user
            await notify_user(job["user_id"], {"type": "message_new", "conversation_id": job["conversation_id"]})
        from push import send_push
        await send_push(job["user_id"], "Posting terjadwal " + ("terkirim" if status == "sent" else "gagal" if status == "failed" else "sebagian terkirim"),
                        ", ".join(LABEL.get(p, p) for p in job.get("providers") or []), {"link": "/social", "tag": f"social-{job['id']}"}, kind="messages")


@router.get("/scheduled")
async def list_scheduled(u: dict = Depends(current_user)):
    rows = await db.social_schedules.find({"user_id": u["id"]}, {"_id": 0, "payload": 0}).sort("scheduled_at", 1).to_list(200)
    return {"items": rows}


@router.delete("/scheduled/{jid}")
async def cancel_scheduled(jid: str, u: dict = Depends(current_user)):
    r = await db.social_schedules.update_one({"id": jid, "user_id": u["id"], "status": "scheduled"}, {"$set": {"status": "cancelled", "cancelled_at": now_iso()}})
    if not r.modified_count:
        raise HTTPException(404, "Jadwal tidak ditemukan atau sudah dijalankan")
    return {"ok": True}


@router.post("/scheduled/{jid}/stop-repeat")
async def stop_repeat(jid: str, u: dict = Depends(current_user)):
    """The pending post still runs once; no further occurrences are created."""
    r = await db.social_schedules.update_one({"id": jid, "user_id": u["id"], "status": "scheduled", "repeat": {"$in": ["daily", "weekly"]}}, {"$set": {"repeat": "none", "repeat_stopped_at": now_iso()}})
    if not r.modified_count:
        raise HTTPException(404, "Jadwal berulang tidak ditemukan")
    return {"ok": True}


# ---------- Meta (Facebook) platform callbacks: Deauthorize + Data Deletion Request ----------
def _parse_signed_request(signed_request: str) -> dict:
    """Verify Facebook's signed_request (HMAC-SHA256 with the app secret) and return its payload."""
    import hmac
    def pad(s: str) -> str:
        return s + "=" * (-len(s) % 4)
    try:
        sig_b64, payload_b64 = signed_request.split(".", 1)
        sig = base64.urlsafe_b64decode(pad(sig_b64))
        payload = json.loads(base64.urlsafe_b64decode(pad(payload_b64)))
    except Exception:
        raise HTTPException(400, "signed_request tidak valid")
    expected = hmac.new(os.environ["META_APP_SECRET"].encode(), payload_b64.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(400, "Tanda tangan signed_request tidak cocok")
    return payload


async def _remove_meta_user(fb_user_id: str, wipe_posts: bool) -> int:
    accs = await db.social_accounts.find({"provider": "meta", "account_id": fb_user_id}, {"_id": 0, "user_id": 1}).to_list(50)
    await db.social_accounts.delete_many({"provider": "meta", "account_id": fb_user_id})
    if wipe_posts and accs:
        await db.social_posts.delete_many({"provider": "meta", "user_id": {"$in": [a["user_id"] for a in accs]}})
    return len(accs)


@router.post("/meta/deauthorize")
async def meta_deauthorize(signed_request: str = Form(...)):
    """Facebook 'Deauthorize callback URL': the user removed Oryntix from their Facebook apps → drop stored tokens."""
    if not configured("meta"):
        raise HTTPException(503, "Integrasi Meta belum dikonfigurasi.")
    payload = _parse_signed_request(signed_request)
    removed = await _remove_meta_user(str(payload.get("user_id") or ""), wipe_posts=False)
    return {"ok": True, "removed": removed}


@router.post("/meta/data-deletion")
async def meta_data_deletion(request: Request, signed_request: str = Form(...)):
    """Facebook 'Data Deletion Request URL': delete everything we hold for that Facebook user and return a status URL + confirmation code."""
    if not configured("meta"):
        raise HTTPException(503, "Integrasi Meta belum dikonfigurasi.")
    payload = _parse_signed_request(signed_request)
    fb_uid = str(payload.get("user_id") or "")
    removed = await _remove_meta_user(fb_uid, wipe_posts=True)
    code = new_id().split("-")[0]
    await db.data_deletion_requests.insert_one({"id": new_id(), "code": code, "provider": "meta", "subject_id": fb_uid, "removed_accounts": removed, "status": "done", "created_at": now_iso()})
    base = f"{request.headers.get('x-forwarded-proto') or request.url.scheme}://{request.headers.get('x-forwarded-host') or request.headers.get('host')}"
    return {"url": f"{base}/api/social/meta/data-deletion/{code}", "confirmation_code": code}


@router.get("/meta/data-deletion/{code}", response_class=HTMLResponse)
async def meta_data_deletion_status(code: str):
    req = await db.data_deletion_requests.find_one({"code": code}, {"_id": 0})
    if not req:
        return HTMLResponse("<h2>Permintaan tidak ditemukan</h2>", status_code=404)
    return HTMLResponse(f"<!doctype html><html lang='id'><body style='font-family:sans-serif;max-width:560px;margin:48px auto;padding:0 16px'>"
                        f"<h2>Oryntix — Penghapusan Data</h2><p>Kode konfirmasi: <b>{code}</b></p><p>Status: <b>Selesai</b> ({req['created_at'][:10]}).</p>"
                        f"<p>Semua token akses, koneksi akun Facebook/Instagram, dan riwayat unggahan yang terkait akun Facebook Anda telah dihapus dari Oryntix.</p></body></html>")


@router.get("/posts")
async def list_posts(kind: Optional[str] = None, u: dict = Depends(current_user)):
    q = {"user_id": u["id"], **({"kind": kind} if kind in ("text", "image", "video") else {})}
    return {"items": await db.social_posts.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)}


class CaptionIn(BaseModel):
    context: str = Field(default="", max_length=6000)
    providers: list[str] = Field(default_factory=list)
    kind: str = Field(default="image")
    media_path: Optional[str] = Field(default=None, max_length=500)


@router.post("/caption")
async def caption(x: CaptionIn, u: dict = Depends(current_user)):
    from llm import llm_text, describe_image
    from auth import _lang_name
    ctx = x.context
    if x.media_path and x.kind == "image":  # look at the actual picture so the caption matches it
        try:
            data, _ = await asyncio.to_thread(get_object, x.media_path)
            ctx = (await describe_image(base64.b64encode(data).decode())) + ("\n\n" + x.context if x.context else "")
        except Exception:
            pass
    text = await llm_text(f"Write ONE social-media caption in {_lang_name(u)} for {', '.join(x.providers) or 'social media'} about the content described. Natural, engaging, 1-3 short sentences + up to 4 relevant hashtags. No quotes, no preamble, never ask questions.", (ctx or "Konten dari asisten Oryntix")[:6000], "gpt-terra")
    return {"caption": text.strip()}
