"""Chat media turns: image, image-edit, video (Seedance), document and Google Drive — extracted from chat.py.
Each turn is an async generator yielding SSE events; the shared primitives (emit_final, latest_media) come from chat_core."""
import logging
from typing import Optional

from fastapi import HTTPException

from auth import workspace_id
from chat_core import emit_final, latest_media
from db import db, now_iso, new_id
from llm import record_usage
from pricing import rate as tool_rate, refresh as pricing_refresh
from realtime import notify
from tools import run_image_tool, run_document_tool
import seedance

log = logging.getLogger("chat")

IMAGE_DONE_TEXT = "Ini gambarnya! ✨ Kalau mau diubah gayanya, bilang saja."
IMAGE_EDIT_DONE_TEXT = "Ini versi barunya! ✨ Mau diubah lagi? Tinggal bilang."


def _image_request(ctx, plan: dict, ref: Optional[dict]) -> tuple:
    """→ (plan, prompts, n): an edit always targets the latest image with a single prompt."""
    if ref:
        plan = {**plan, "image_prompts": [plan.get("edit_prompt") or ctx.user_text]}
    prompts = plan.get("image_prompts") or [(plan.get("image_prompt") or "").strip() or "illustration"]
    return plan, prompts, 1 if ref else len(prompts)


async def _image_confirm_card(ctx, plan: dict, prompts: list, n: int, credits: int, ref: Optional[dict]) -> tuple:
    """Confirmation text + pending_tool for the model/quality picker (single image) or the cost confirmation (image set)."""
    text = ("Siap, aku ubah gambar terakhirnya sesuai permintaanmu! 🎨 Mau pakai model yang mana?" if ref
            else f"Siap, aku bisa buatkan {n} gambarnya! 🎨 Perkiraan biaya ±{credits * n} kredit. Lanjutkan?" if n > 1
            else "Siap, aku bisa buatkan gambarnya! 🎨 Mau pakai model yang mana?")
    pt = {"kind": "image_edit" if ref else "image_set" if n > 1 else "image", "prompt": prompts[0], "prompts": prompts, "credits": credits * n, "count": n, "request": ctx.user_text[:300],
          "aspect_ratio": plan.get("aspect_ratio") or "1:1", "quality": plan.get("quality") or "standar", "preset": plan.get("preset")}
    if n == 1:
        from tools import image_model_options, image_presets
        pt["options"] = await image_model_options()
        pt["presets"] = image_presets()
    if ref:
        pt["reference_path"] = ref["path"]
    return text, pt


async def _render_single_image(ctx, prompt: str, plan: dict, ref: Optional[dict]) -> Optional[dict]:
    try:
        return await run_image_tool(ctx.user["id"], prompt, ref["path"] if ref else None, "gemini-image", plan.get("aspect_ratio") or "1:1", plan.get("quality") or "standar", plan.get("preset"))
    except Exception as exc:
        log.warning("image turn failed: %s", exc)
        return None


async def _image_turn(ctx, plan: dict, confirm_threshold: int):
    from chat import _start_image_set, _image_set_text
    credits = tool_rate("image")
    ref = await latest_media(ctx.cid, "image") if plan.get("tool") == "image_edit" else None
    plan, prompts, n = _image_request(ctx, plan, ref)
    yield ctx.sse(start=True)
    if credits * n >= confirm_threshold:
        text, pt = await _image_confirm_card(ctx, plan, prompts, n, credits, ref)
        yield ctx.sse(delta=text)
        async for ev in emit_final(ctx, text, 0, {"pending_tool": pt}):
            yield ev
        return
    if n > 1:
        task = await _start_image_set(ctx.user, ctx.persona, ctx.cid, prompts, (plan.get("title") or f"{n} gambar: {ctx.user_text[:60]}").strip())
        async for ev in emit_final(ctx, _image_set_text(task, n), 0, {"tool": "image_set", "task_id": task["id"]}):
            yield ev
        return
    yield ctx.sse(status="Mengedit gambar..." if ref else "Merender gambar...", rendering="image")
    out = await _render_single_image(ctx, prompts[0], plan, ref)
    if not out:
        async for ev in emit_final(ctx, "Maaf, gambarnya belum berhasil dibuat. Coba ulangi dengan deskripsi lain ya.", 0, {}):
            yield ev
        return
    await record_usage(ctx.user["id"], "image_generation", out["credits"], {"conversation_id": ctx.cid, "persona_id": ctx.persona["id"]})
    out["media"][0]["request"] = ctx.user_text[:300]
    async for ev in emit_final(ctx, IMAGE_EDIT_DONE_TEXT if ref else IMAGE_DONE_TEXT, out["credits"], {"media": out["media"], "tool": "image_edit" if ref else "image"}):
        yield ev


VIDEO_WAIT_TEXT = "Oke, aku render videonya sekarang. 🎬 Proses ini biasanya 2–5 menit — hasilnya akan muncul otomatis di sini begitu selesai, dan filenya tersimpan di Google Drive kamu."
VIDEO_DONE_TEXT = "Ini videonya! 🎬 Filenya sudah tersimpan di Google Drive kamu (folder Oryntix). Kalau mau adegan atau gayanya diubah, bilang saja."
VIDEO_FAIL_TEXT = "Maaf, videonya belum berhasil dirender. Kredit kamu tidak dipotong. Coba ulangi dengan deskripsi adegan yang lain ya."


async def _owner_balance(user: dict) -> int:
    owner_id = user.get("owner_id") or user["id"]
    owner = await db.users.find_one({"id": owner_id}, {"_id": 0, "credits": 1}) or {}
    return int(owner.get("credits") or 0)


def _fmt_credits(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".") if n >= 100 else f"{n:g}"


async def video_pricing_text() -> str:
    """One line with both Seedance tiers in platform credits/sec — reused by the system prompt and the chat offer."""
    await pricing_refresh()
    return " · ".join(f"{o['label']} ±{_fmt_credits(o['per_sec'])} kredit/detik" for o in seedance.options(seedance.DEFAULT_DUR))


def _video_fail_text(err: str, app_base: str) -> str:
    e = err.lower()
    if "hostname approved" in e or "approved for this api" in e:
        host = app_base.split("//")[-1].split("/")[0] or "domain aplikasi ini"
        return (f"Videonya belum bisa dirender dari gambar: host gambar referensi **{host}** belum disetujui di akun seedance2video.io. "
                "Admin perlu mendaftarkan host itu di *Settings → API Keys* (atau hubungi support@seedance2video.io). Kredit kamu tidak dipotong.")
    if "paid" in e and "account" in e:
        return "Videonya belum bisa dirender: akun seedance2video.io yang dipakai platform belum berlangganan paket berbayar (API hanya untuk akun berbayar). Admin platform perlu mengaktifkan paketnya dulu. Kredit kamu tidak dipotong."
    if "insufficient" in e or " 402" in e or ("credit" in e and "seedance" in e):
        return "Videonya belum bisa dirender: saldo kredit akun seedance2video.io (provider) habis — admin platform perlu menambah kredit di sana. Kredit kamu tidak dipotong."
    return VIDEO_FAIL_TEXT


async def _run_video_bg(mid: str, cid: str, uid: str, persona_id: Optional[str], pt: dict, app_base: str = ""):
    """Background: render at seedance2video.io, upload the file to the user's Google Drive (never platform storage), then swap the placeholder message."""
    from integrations import drive_save
    from social import public_media_url
    tier, duration, prompt, request = pt["tier"], int(pt["duration"]), pt["prompt"], pt.get("request") or ""
    try:
        image_url = public_media_url(app_base, pt["reference_path"]) if pt.get("reference_path") and app_base else None
        aspect = pt.get("aspect_ratio") if pt.get("aspect_ratio") in seedance.ASPECTS else "16:9"
        res = pt.get("resolution") if pt.get("resolution") in seedance.RESOLUTIONS else "720p"
        rp = bool(pt.get("real_person")) and bool(image_url)
        au = bool(pt.get("with_audio"))
        gen = await seedance.generate(prompt, tier, duration, aspect_ratio=aspect, resolution=res, image_url=image_url, real_person=rp, consent_ref=f"oryntix-{uid[:8]}-{mid[:8]}", generate_audio=au)
        data = await seedance.download(gen["video_url"])
        title = f"Oryntix video - {(request or prompt)[:50].strip()} ({seedance.TIERS[tier]['label']}, {duration}s, {pt.get('aspect_ratio') or '16:9'}, {pt.get('resolution') or '720p'}).mp4"
        f = await drive_save(uid, title, kind="file", data=data, mime="video/mp4", source={"kind": "video", "conversation_id": cid, "message_id": mid, "tier": tier})
        credits = seedance.quote(tier, duration, res, rp, au)
        await record_usage(uid, "video_generation", credits, {"conversation_id": cid, "persona_id": persona_id, "tier": tier, "duration": duration, "resolution": res, "real_person": rp, "audio": au, "provider_credits": gen.get("provider_credits")})
        media = {"type": "video", "name": f["name"], "drive_id": f["drive_id"], "link": f.get("link"), "prompt": prompt[:400], "request": request[:300], "tier": tier, "duration": duration, "aspect_ratio": aspect, "resolution": res, "real_person": rp, "audio": au}
        if pt.get("reference_path"):
            media["animated_from"] = pt["reference_path"]
        upd = {"content": VIDEO_DONE_TEXT, "media": [media], "tool": "video", "credits": credits, "rendering": None}
    except Exception as exc:
        log.warning("video render failed: %s", exc)
        upd = {"content": _video_fail_text(str(exc), app_base), "tool": "video", "error": True, "rendering": None}
    await db.messages.update_one({"id": mid}, {"$set": upd})
    msg = await db.messages.find_one({"id": mid}, {"_id": 0})
    if msg:
        await notify(cid, {"type": "message", "role": "assistant", "persona_id": persona_id, "message": msg})


def _video_params(plan: dict, user_text: str, ref: Optional[dict]) -> dict:
    """Normalised render parameters from the planner output (invalid values fall back to the defaults)."""
    return {"duration": seedance.clamp_duration(plan.get("duration")), "prompt": (plan.get("video_prompt") or user_text).strip(),
            "aspect": plan.get("aspect_ratio") if plan.get("aspect_ratio") in seedance.ASPECTS else "16:9",
            "resolution": plan.get("resolution") if plan.get("resolution") in seedance.RESOLUTIONS else "720p",
            "real_person": bool(plan.get("real_person")) and bool(ref), "with_audio": bool(plan.get("with_audio"))}


def _video_blocker(opts: list, balance: int, drive_ok: bool, duration: int) -> Optional[tuple]:
    """(text, extra) when the render cannot be offered yet: Drive not connected or balance below the cheapest tier."""
    avail = [o for o in opts if o["available"]]
    if not drive_ok:
        est = " atau ".join(f"{o['label']} ±{_fmt_credits(o['credits'])} kredit" for o in avail)
        return (f"Siap bikin videonya ({duration} detik)! 🎬 Tapi video hasil render akan kusimpan langsung ke **Google Drive kamu**, bukan di server — "
                f"jadi hubungkan Google Drive dulu ya, lalu minta lagi.\n\nPerkiraan biaya: {est}.", {"tool": "video", "cta": {"label": "Hubungkan Google Drive", "href": "/integrations"}})
    if balance < min(o["credits"] for o in avail):
        return (f"Untuk video {duration} detik butuh " + " atau ".join(f"±{_fmt_credits(o['credits'])} kredit ({o['label']})" for o in avail)
                + f", sedangkan saldo kredit kamu {_fmt_credits(balance)}. Tambah kredit dulu ya, nanti aku langsung render. 🙏",
                {"tool": "video", "error": True, "cta": {"label": "Tambah Kredit", "href": "/wallet"}})
    return None


def _video_offer_text(v: dict, opts: list, mult: dict, balance: int, ref: Optional[dict]) -> str:
    avail, skipped = [o for o in opts if o["available"]], [o for o in opts if not o["available"]]
    res, rp, au, dur = v["resolution"], v["real_person"], v["with_audio"], v["duration"]
    lines = [f"**{o['label']}** ±{_fmt_credits(o['per_sec'] * mult['res'].get(res, 1) * (mult['real_person'] if rp else 1) * (mult['audio'] if au else 1))} kredit/detik → ±{_fmt_credits(o['credits'])} kredit untuk {dur} detik"
             + ("" if o["credits"] <= balance else " *(saldo tidak cukup)*") for o in avail]
    fmt = (f" format {seedance.ASPECTS[v['aspect']]}" if v["aspect"] != "16:9" else "") + (f", {seedance.RESOLUTIONS[res]}" if res != "720p" else "") + (", mode real person" if rp else "") + (", dengan suara/ambience" if au else "")
    intro = f"Siap, aku animasikan gambar terakhir jadi video {dur} detik{fmt}. 🎬 Mau pakai model yang mana?" if ref else f"Siap, videonya {dur} detik{fmt}. 🎬 Mau pakai model yang mana?"
    why = {True: lambda o: f"maksimal {o['max_dur']} detik", False: lambda o: "tidak mendukung mode real person" if rp and not o["real_person"] else f"tidak mendukung {res}"}
    return (f"{intro}\n\n" + "\n".join(f"- {l}" for l in lines)
            + "".join(f"\n\n*{o['label']} tidak tersedia: {why[dur > o['max_dur']](o)}.*" for o in skipped)
            + f"\n\nSaldo kredit kamu: {_fmt_credits(balance)}. Pilih resolusi dan model di bawah ya.")


async def video_offer(user: dict, cid: str, plan: dict, user_text: str) -> tuple:
    """Shared by typed chat and voice calls: returns (text, extra) — the Seedance 2.0/2.5 offer, or a Drive/credits/config notice."""
    from integrations import drive_connected
    if not seedance.configured():
        return "Fitur render video belum diaktifkan oleh admin platform (API key Seedance belum diatur). Coba lagi nanti ya.", {"tool": "video", "error": True}
    ref = await latest_media(cid, "image") if plan.get("from_image") else None
    v = _video_params(plan, user_text, ref)
    await pricing_refresh()
    opts = seedance.options(v["duration"], v["resolution"], v["real_person"], v["with_audio"])
    balance = await _owner_balance(user)
    blocked = _video_blocker(opts, balance, await drive_connected(user["id"]), v["duration"])
    if blocked:
        return blocked
    mult = seedance.multipliers()
    pt = {"kind": "video", "prompt": v["prompt"], "duration": v["duration"], "aspect_ratio": v["aspect"], "resolution": v["resolution"], "real_person": v["real_person"],
          "with_audio": v["with_audio"], "multipliers": mult, "options": opts, "balance": balance, "request": user_text[:300]}
    if ref:
        pt["reference_path"] = ref["path"]
    return _video_offer_text(v, opts, mult, balance, ref), {"pending_tool": pt}


async def _video_turn(ctx, plan: dict, confirm_threshold: int):
    yield ctx.sse(start=True)
    text, extra = await video_offer(ctx.user, ctx.cid, plan, ctx.user_text)
    if "pending_tool" in extra:
        yield ctx.sse(delta=text)
    async for ev in emit_final(ctx, text, 0, extra):
        yield ev


async def _document_turn(ctx, plan: dict):
    title = (plan.get("title") or "Dokumen").strip()[:120]
    yield ctx.sse(start=True)
    yield ctx.sse(status=f"Sedang menyusun dokumen “{title}”...")
    out = None
    try:
        out = await run_document_tool(ctx.user["id"], ctx.system, title, plan.get("instructions") or title, ctx.prompt, ctx.model_key)
    except Exception:
        out = None
    if not out:
        async for ev in emit_final(ctx, "Maaf, dokumennya belum berhasil dibuat. Coba lagi sebentar ya.", 0, {}):
            yield ev
        return
    await record_usage(ctx.user["id"], "document_generation", out["credits"], {"conversation_id": ctx.cid, "persona_id": ctx.persona["id"]})
    task = {"id": new_id(), "user_id": ctx.user["id"], "workspace_id": workspace_id(ctx.user), "goal": title, "type": "document", "status": "completed",
            "steps": [], "summary": "Dokumen dibuat dari chat", "model": ctx.model_key, "final_output": out["markdown"], "media": [m for m in out["media"] if m.get("type") != "file"],
            "credits_used": out["credits"], "persona_id": ctx.persona["id"], "persona_name": ctx.persona["name"], "source": "chat", "conversation_ids": [ctx.cid],
            "version": 1, "created_at": now_iso(), "updated_at": now_iso()}
    await db.tasks.insert_one(dict(task))
    extra = {"media": out["media"], "tool": "document", "model_key": ctx.model_key, "model_label": out["model_label"], "doc_markdown": out["markdown"][:20000], "task_id": task["id"]}
    async for ev in emit_final(ctx, f"Dokumen **{title}** sudah jadi! 📄 Tersedia dalam Word, PDF, dan Markdown di bawah ini.\n\nDokumen ini juga tersimpan di Ruang Kerja untuk dibahas atau direvisi nanti — [buka di Ruang Kerja](/workspace/{task['id']}).", out["credits"], extra):
        yield ev


async def _drive_save_action(ctx, plan: dict) -> tuple:
    from integrations import drive_save
    md = (plan.get("text") or "").strip()
    if ctx.task and len(md) < 40:
        md = ctx.task.get("final_output") or md
    if len(md) < 2:
        raise HTTPException(400, "Belum ada isi yang bisa disimpan — sebutkan dokumen atau isinya.")
    title = (plan.get("title") or (ctx.task or {}).get("goal") or "Dokumen Oryntix")[:200]
    item = await drive_save(ctx.user["id"], title, md, plan.get("kind") or "doc", source={"task_id": (ctx.task or {}).get("id"), "conversation_id": ctx.cid})
    return (f"Tersimpan di Google Drive sebagai **{item['name']}** — [buka di Drive]({item['link']}). Di Galeri hanya tautannya yang disimpan, jadi tidak memakai penyimpanan platform.",
            {"tool": "drive_save", "drive": item})


async def _drive_update_action(ctx, plan: dict) -> tuple:
    from integrations import drive_update
    f = await drive_update(ctx.user["id"], plan.get("file") or plan.get("title") or "", plan.get("text") or "", plan.get("mode") or "append")
    return f"Dokumen **{f['name']}** sudah diperbarui — [buka di Drive]({f.get('webViewLink')}).", {"tool": "drive_update", "drive": f}


async def _drive_link_action(ctx, plan: dict) -> tuple:
    from integrations import drive_link
    f = await drive_link(ctx.user["id"], plan.get("file") or plan.get("title") or "")
    return f"Ini tautannya: [{f['name']}]({f.get('webViewLink')})", {"tool": "drive_link", "drive": f}


DRIVE_ACTIONS = {"drive_save": _drive_save_action, "drive_update": _drive_update_action, "drive_link": _drive_link_action}


async def _drive_turn(ctx, plan: dict):
    """Google Drive tools from chat: save (doc/sheet), update a Doc, or fetch a link. Needs the user's Drive connection."""
    tool = plan["tool"]
    yield ctx.sse(start=True)
    yield ctx.sse(status="Menghubungi Google Drive...")
    try:
        text, extra = await DRIVE_ACTIONS.get(tool, _drive_link_action)(ctx, plan)
    except HTTPException as e:
        text, extra = f"{e.detail}", {"tool": tool, "error": True}
    async for ev in emit_final(ctx, text, 0, extra):
        yield ev
