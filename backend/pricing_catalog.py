"""Hierarchical price catalog: provider → service/model → price component → unit. THE single source of provider prices.

ONE formula for every component (easy to change in one place):
    base_usd = usd * qty / qty_basis
    sell_usd = base_usd × (1 + margin%) × (1 + tax%)      # steps listed in PIPELINE
    credits  = sell_usd / usd_per_credit
Per-image prices are flat: unit "image", qty_basis 1, usd = price of one image.

margin/tax resolution order: component → service → provider → platform feature override → platform global.
Stored in Mongo as config/pricing_catalog; DEFAULT_CATALOG below is the seed taken from the providers' docs.
"""
import math
import re
import time
from typing import Optional

import httpx

from db import db, now_iso

PIPELINE = ["margin", "tax"]  # order of multipliers applied on top of the provider cost
UNITS = {
    "token": "token", "character": "karakter", "minute": "menit", "second": "detik", "image": "gambar",
    "request": "permintaan", "call": "panggilan API", "search": "pencarian", "session": "sesi",
    "container_hour": "jam kontainer", "GB": "GB", "GB_day": "GB per hari", "profile": "profil",
    "snapshot": "cuplikan", "page": "halaman", "k_chars": "1.000 karakter", "song": "lagu", "video_second": "detik video",
}
M1 = 1_000_000


def comp(cid, label, unit, qty_basis, usd, **kw) -> dict:
    return {"id": cid, "label": label, "unit": unit, "qty_basis": qty_basis, "usd": usd,
            "modality": kw.get("modality", "text"), "direction": kw.get("direction", "flat"),
            "margin_pct": kw.get("margin_pct"), "tax_pct": kw.get("tax_pct"), "enabled": kw.get("enabled", True),
            "doc_col": kw.get("doc_col"), "note": kw.get("note", "")}


def _text_model(sid, label, doc_model, usd_in, usd_out, cached=None, note="") -> dict:
    cs = [comp("text_in", "Input", "token", M1, usd_in, direction="input", doc_col=0),
          comp("text_out", "Output", "token", M1, usd_out, direction="output", doc_col=-1)]
    if cached is not None:
        cs.insert(1, comp("cached_in", "Input (cache hit)", "token", M1, cached, direction="input", doc_col=1))
    return {"id": sid, "label": label, "kind": "text", "doc_model": doc_model, "margin_pct": None, "tax_pct": None, "note": note, "components": cs}


DEFAULT_CATALOG = {
    "version": 3,
    "providers": [
        {"id": "openai", "label": "OpenAI", "docs_url": "https://developers.openai.com/api/docs/pricing", "margin_pct": None, "tax_pct": None,
         "doc_cols": {"text_in": 0, "cached_in": 1, "text_out": 3}, "services": [
            _text_model("gpt-astra", "GPT Astra", "gpt-6-astra", 10.0, 50.0, 1.0),
            _text_model("gpt-luna", "GPT Luna", "gpt-6-luna", 0.10, 0.50, 0.01),
            _text_model("gpt-terra", "GPT Terra", "gpt-5.6-terra", 1.0, 5.0, 0.10, note="Tidak tercantum di halaman harga publik — nilai manual."),
            _text_model("gpt-5-5", "GPT 5.5", "gpt-5.5", 1.25, 10.0, 0.125, note="Model generasi sebelumnya — nilai manual."),
            {"id": "gpt-live", "label": "GPT-Live (sesi suara)", "kind": "realtime", "doc_model": "gpt-live-1", "margin_pct": None, "tax_pct": None, "components": [
                comp("per_minute", "Harga per menit sesi", "minute", 1, 0.05, modality="audio", doc_col=0,
                     note="Ditagih per detik oleh OpenAI; model & tool di dalam sesi ditagih terpisah.")]},
            {"id": "gpt-realtime-2.1", "label": "GPT Realtime 2.1", "kind": "realtime", "doc_model": "gpt-realtime-2.1", "margin_pct": None, "tax_pct": None, "components": [
                comp("audio_in", "Audio input", "token", M1, 32.0, modality="audio", direction="input"),
                comp("audio_out", "Audio output", "token", M1, 64.0, modality="audio", direction="output"),
                comp("text_in", "Teks input", "token", M1, 4.0, direction="input"),
                comp("text_out", "Teks output", "token", M1, 24.0, direction="output"),
                comp("cached_in", "Input (cache hit)", "token", M1, 0.40, direction="input"),
                comp("image_in", "Gambar input", "token", M1, 5.0, modality="image", direction="input")]},
            {"id": "gpt-realtime-2.1-mini", "label": "GPT Realtime 2.1 Mini", "kind": "realtime", "doc_model": "gpt-realtime-2.1-mini", "margin_pct": None, "tax_pct": None, "components": [
                comp("audio_in", "Audio input", "token", M1, 10.0, modality="audio", direction="input"),
                comp("audio_out", "Audio output", "token", M1, 20.0, modality="audio", direction="output"),
                comp("text_in", "Teks input", "token", M1, 0.60, direction="input"),
                comp("text_out", "Teks output", "token", M1, 2.40, direction="output"),
                comp("cached_in", "Input (cache hit)", "token", M1, 0.30, direction="input"),
                comp("image_in", "Gambar input", "token", M1, 0.80, modality="image", direction="input")]},
            {"id": "gpt-realtime-2.0", "label": "GPT Realtime 2.0", "kind": "realtime", "doc_model": "gpt-realtime-2.0", "margin_pct": None, "tax_pct": None, "components": [
                comp("audio_in", "Audio input", "token", M1, 32.0, modality="audio", direction="input"),
                comp("audio_out", "Audio output", "token", M1, 64.0, modality="audio", direction="output"),
                comp("text_in", "Teks input", "token", M1, 4.0, direction="input"),
                comp("text_out", "Teks output", "token", M1, 24.0, direction="output"),
                comp("cached_in", "Input (cache hit)", "token", M1, 0.40, direction="input")]},
            {"id": "gpt-image", "label": "GPT Image 2.5", "kind": "image", "doc_model": "gpt-image-2.5-sunburst", "margin_pct": None, "tax_pct": None, "components": [
                comp("image_in", "Gambar input (per gambar)", "image", 1, 0.0084, modality="image", direction="input",
                     note="Flat per gambar referensi ≤1024² (≈1.056 token × $8/1M)."),
                comp("image_out", "Gambar output (per gambar, 1024² medium)", "image", 1, 0.032, modality="image", direction="output",
                     note="Flat per gambar: low ≈ $0,008 · medium ≈ $0,032 · high ≈ $0,125 (kalkulator OpenAI)."),
                comp("text_in", "Teks prompt", "token", M1, 5.0, direction="input")]},
            {"id": "openai-whisper", "label": "Transkripsi suara (Whisper)", "kind": "stt", "doc_model": "gpt-transcribe", "margin_pct": None, "tax_pct": None, "components": [
                comp("per_request", "Per permintaan transkripsi", "request", 1, 0.0165, modality="audio", direction="input")]},
            {"id": "openai-tts", "label": "Suara TTS", "kind": "tts", "doc_model": "", "margin_pct": None, "tax_pct": None, "components": [
                comp("per_request", "Per permintaan ucapan", "request", 1, 0.013, modality="audio", direction="output")]},
            {"id": "openai-vision", "label": "Cuplikan layar ke asisten", "kind": "vision", "doc_model": "", "margin_pct": None, "tax_pct": None, "components": [
                comp("per_snapshot", "Per cuplikan", "snapshot", 1, 0.006, modality="image", direction="input")]},
            {"id": "openai:web_search", "label": "Tool: Pencarian web", "kind": "tool", "doc_model": "Web search", "margin_pct": None, "tax_pct": None, "components": [
                comp("per_call", "Per 1.000 panggilan", "call", 1000, 10.0, note="Token hasil pencarian ditagih di tarif model.")]},
            {"id": "openai:code_interpreter", "label": "Tool: Code Interpreter", "kind": "tool", "doc_model": "Containers", "margin_pct": None, "tax_pct": None, "components": [
                comp("per_session", "Per sesi kontainer 20 menit (1 GB)", "session", 1, 0.03)]},
            {"id": "openai:image_generation", "label": "Tool: Pembuatan gambar", "kind": "tool", "doc_model": "", "margin_pct": None, "tax_pct": None, "components": [
                comp("per_image", "Per gambar (1024², medium)", "image", 1, 0.032, modality="image", direction="output")]},
            {"id": "openai:file_search", "label": "Tool: File search", "kind": "tool", "doc_model": "File search", "margin_pct": None, "tax_pct": None, "components": [
                comp("per_call", "Per 1.000 panggilan tool", "call", 1000, 2.50),
                comp("storage", "Penyimpanan per GB per hari", "GB_day", 1, 0.10, note="1 GB pertama gratis.")]},
        ]},
        {"id": "gemini", "label": "Google Gemini", "docs_url": "https://ai.google.dev/gemini-api/docs/pricing", "margin_pct": None, "tax_pct": None,
         "doc_cols": {}, "services": [
            _text_model("gemini-pro", "Gemini 3.1 Pro", "gemini-3.1-pro-preview", 2.0, 12.0, 0.20, note="Halaman Gemini memuat harga promo bertanggal — impor otomatis dimatikan, perbarui manual."),
            _text_model("gemini-3-8-flash", "Gemini 3.8 Flash", "gemini-3.8-flash", 0.75, 3.75, 0.075),
            _text_model("gemini-3-7-flash", "Gemini 3.7 Flash", "gemini-3.7-flash", 0.75, 3.75, 0.075),
            _text_model("gemini-3-6-flash", "Gemini 3.6 Flash", "gemini-3.6-flash", 0.75, 3.75, 0.075),
            _text_model("gemini-3-5-flash", "Gemini 3.5 Flash", "gemini-3.5-flash", 1.50, 9.0, 0.15),
            _text_model("gemini-3-flash", "Gemini 3 Flash", "gemini-3-flash-preview", 0.50, 3.0, 0.05),
            {"id": "gemini-nano-banana", "label": "Gemini 2.5 Flash Image (Nano Banana)", "kind": "image", "doc_model": "gemini-2.5-flash-image", "margin_pct": None, "tax_pct": None, "components": [
                comp("image_out", "Gambar output (per gambar)", "image", 1, 0.039, modality="image", direction="output",
                     note="Flat per gambar ≤1024² (1.290 token × $30/1M)."),
                comp("text_in", "Teks/gambar input", "token", M1, 0.30, direction="input")]},
            {"id": "gemini:google_search", "label": "Tool: Google Search grounding", "kind": "tool", "doc_model": "Google Search", "margin_pct": None, "tax_pct": None, "components": [
                comp("per_request", "Per 1.000 permintaan (Gemini 3+)", "request", 1000, 14.0, note="5.000 permintaan pertama per bulan gratis.")]},
            {"id": "gemini:code_execution", "label": "Tool: Eksekusi kode", "kind": "tool", "doc_model": "Code execution", "margin_pct": None, "tax_pct": None, "components": [
                comp("per_request", "Per permintaan", "request", 1, 0.0, note="Hanya ditagih sebagai token model.")]},
        ]},
        {"id": "anthropic", "label": "Anthropic Claude", "docs_url": "https://platform.claude.com/docs/en/about-claude/pricing", "margin_pct": None, "tax_pct": None,
         "doc_cols": {"text_in": 0, "text_out": 1, "cached_in": 4}, "services": [
            _text_model("claude-opus-5-5", "Claude Opus 5.5", "Claude Opus 5.5", 4.0, 20.0, 0.20),
            _text_model("claude-sonnet", "Claude Sonnet 5.5", "Claude Sonnet 5.5", 2.0, 10.0, 0.10),
            _text_model("claude-opus-5", "Claude Opus 5", "Claude Opus 5", 5.0, 25.0, 0.50),
            _text_model("claude-sonnet-5", "Claude Sonnet 5", "Claude Sonnet 5", 2.0, 10.0, 0.20),
            _text_model("claude-opus-4-8", "Claude Opus 4.8", "Claude Opus 4.8", 5.0, 25.0, 0.50),
            _text_model("claude-haiku", "Claude Haiku 4.5", "Claude Haiku 4.5", 1.0, 5.0, 0.10),
            _text_model("claude-fable", "Claude Fable 5.1", "Claude Fable 5.1", 10.0, 50.0, 0.25),
            {"id": "anthropic:web_search", "label": "Tool: Pencarian web", "kind": "tool", "doc_model": "Web search", "margin_pct": None, "tax_pct": None, "components": [
                comp("per_search", "Per 1.000 pencarian", "search", 1000, 10.0)]},
            {"id": "anthropic:code_execution", "label": "Tool: Eksekusi kode", "kind": "tool", "doc_model": "Code execution", "margin_pct": None, "tax_pct": None, "components": [
                comp("per_hour", "Per jam kontainer", "container_hour", 1, 0.05, note="1.550 jam pertama per bulan gratis.")]},
        ]},
        {"id": "seedance", "label": "Seedance (video)", "docs_url": "https://seedance2video.io/pricing", "margin_pct": None, "tax_pct": None, "services": [
            {"id": "seedance-2-5", "label": "Seedance 2.5 (720p)", "kind": "video", "doc_model": "", "margin_pct": None, "tax_pct": None, "components": [
                comp("per_second", "Per detik video keluaran", "video_second", 1, 0.80, modality="video", direction="output")]},
            {"id": "seedance-2-0", "label": "Seedance 2.0 Pro (720p)", "kind": "video", "doc_model": "", "margin_pct": None, "tax_pct": None, "components": [
                comp("per_second", "Per detik video keluaran", "video_second", 1, 0.60, modality="video", direction="output")]},
        ]},
        {"id": "oryntix", "label": "Infrastruktur Oryntix", "docs_url": "", "margin_pct": None, "tax_pct": None, "services": [
            {"id": "turn-relay", "label": "Data panggilan teman (TURN metered.ca)", "kind": "infra", "doc_model": "", "margin_pct": None, "tax_pct": None, "components": [
                comp("per_gb", "Per GB relay (ingress + egress)", "GB", 1, 0.50, margin_pct=50.0,
                     note="Tarif overage metered.ca: $0,40/GB (Growth), $0,20/GB (Business), $0,10/GB (Enterprise).")]},
            {"id": "persona-profile", "label": "Pembuatan profil persona", "kind": "infra", "doc_model": "", "margin_pct": None, "tax_pct": None, "components": [
                comp("per_profile", "Per profil", "profile", 1, 0.026)]},
            {"id": "text-default", "label": "Teks default (model tanpa harga di katalog)", "kind": "text", "doc_model": "", "margin_pct": None, "tax_pct": None, "components": [
                comp("per_1k_chars", "Per 1.000 karakter (input + output)", "k_chars", 1, 0.00675, note="Dipakai hanya bila model otak tidak ada di katalog.")]},
        ]},
    ],
}
# platform feature key → (service id, component id) used by the billing engine
FEATURE_COMPONENT = {
    "text": ("text-default", "per_1k_chars"),
    "image": ("gemini-nano-banana", "image_out"),
    "profile": ("persona-profile", "per_profile"),
    "stt": ("openai-whisper", "per_request"),
    "tts": ("openai-tts", "per_request"),
    "vision": ("openai-vision", "per_snapshot"),
    "realtime_call": ("gpt-live", "per_minute"),
    "call_bandwidth": ("turn-relay", "per_gb"),
    "video": ("seedance-2-5", "per_second"),
    "video20": ("seedance-2-0", "per_second"),
}
_cache = {"at": 0.0, "cat": None}


def _merge(stored: dict | None) -> dict:
    """Defaults + admin edits: match by id so new seed entries appear and custom entries survive."""
    out = {"version": DEFAULT_CATALOG["version"], "providers": [], "updated_at": (stored or {}).get("updated_at")}
    legacy = int((stored or {}).get("version") or 0) < 3  # v2 stored flat-token image rows → superseded by the per-image seed
    sp = {p["id"]: p for p in (stored or {}).get("providers") or []}
    for dp in DEFAULT_CATALOG["providers"]:
        p = {**dp, **{k: v for k, v in sp.get(dp["id"], {}).items() if k != "services"}}
        ss = {s["id"]: s for s in (sp.get(dp["id"], {}).get("services") or [])}
        services = []
        for dsv in dp["services"]:
            sv = {**dsv, **{k: v for k, v in ss.get(dsv["id"], {}).items() if k != "components"}}
            sc = {c["id"]: {k: v for k, v in c.items() if k != "flat_qty"} for c in (ss.get(dsv["id"], {}).get("components") or [])
                  if not (legacy and c.get("flat_qty"))}
            sv["components"] = [{**dc, **sc.get(dc["id"], {})} for dc in dsv["components"]] + \
                               [c for cid, c in sc.items() if cid not in {d["id"] for d in dsv["components"]}]
            services.append(sv)
        services += [s for sid, s in ss.items() if sid not in {d["id"] for d in dp["services"]}]
        p["services"] = services
        out["providers"].append(p)
    out["providers"] += [p for pid, p in sp.items() if pid not in {d["id"] for d in DEFAULT_CATALOG["providers"]}]
    return out


async def refresh(force: bool = False) -> dict:
    if force or _cache["cat"] is None or time.time() - _cache["at"] > 30:
        doc = await db.config.find_one({"id": "pricing_catalog"}, {"_id": 0, "id": 0})
        _cache["cat"] = _merge(doc)
        _cache["at"] = time.time()
    return _cache["cat"]


async def get_catalog() -> dict:
    return await refresh()


async def set_catalog(cat: dict) -> dict:
    await db.config.update_one({"id": "pricing_catalog"}, {"$set": {**cat, "updated_at": now_iso()}}, upsert=True)
    return await refresh(force=True)


def catalog() -> dict:
    """Cached catalog for synchronous billing paths (populated by refresh())."""
    return _cache["cat"] or _merge(None)


def find(service_id: str, component_id: str, cat: dict | None = None) -> Optional[tuple]:
    for p in (cat or catalog())["providers"]:
        for s in p["services"]:
            if s["id"] == service_id:
                for c in s["components"]:
                    if c["id"] == component_id:
                        return p, s, c
    return None


def _pct(field: str, c: dict, s: dict, p: dict, pricing: dict, feature: str | None) -> float:
    for src in (c, s, p):
        if src.get(field) is not None:
            return float(src[field])
    if field == "margin_pct":
        ov = (pricing.get("margin_overrides") or {}).get(feature) if feature else None
        return float(ov if ov is not None else pricing.get("margin_pct", 30.0))
    return float(pricing.get("tax_pct", 11.0))


def quote(service_id: str, component_id: str, qty: float | None, pricing: dict, feature: str | None = None,
          cat: dict | None = None) -> Optional[dict]:
    """The ONE calculation. Returns the full breakdown, or None when the component does not exist/is disabled."""
    hit = find(service_id, component_id, cat)
    if not hit:
        return None
    p, s, c = hit
    if not c.get("enabled", True):
        return None
    if qty is None:
        qty = 1.0
    margin = _pct("margin_pct", c, s, p, pricing, feature)
    tax = _pct("tax_pct", c, s, p, pricing, feature)
    base = float(c["usd"]) * float(qty) / max(float(c.get("qty_basis") or 1), 1e-9)
    sell = base
    for step in PIPELINE:
        sell *= 1 + (margin if step == "margin" else tax) / 100
    upc = max(float(pricing.get("usd_per_credit") or 0.001), 1e-9)
    return {"path": f"{p['id']}/{s['id']}/{c['id']}", "provider": p["label"], "service": s["label"], "component": c["label"],
            "unit": c["unit"], "qty": float(qty), "qty_basis": c.get("qty_basis"), "unit_usd": float(c["usd"]),
            "base_usd": base, "margin_pct": margin, "tax_pct": tax,
            "margin_usd": base * margin / 100, "tax_usd": base * (1 + margin / 100) * tax / 100,
            "total_usd": sell, "credits_exact": sell / upc, "credits": max(1, math.ceil(sell / upc))}


def credits(service_id: str, component_id: str, qty: float | None, pricing: dict, feature: str | None = None) -> Optional[float]:
    q = quote(service_id, component_id, qty, pricing, feature)
    return q["credits_exact"] if q else None


def unit_usd(service_id: str, component_id: str) -> Optional[float]:
    hit = find(service_id, component_id)
    if not hit:
        return None
    _, _, c = hit
    return float(c["usd"]) / max(float(c.get("qty_basis") or 1), 1e-9)


def feature_usd(feature: str, pricing: dict) -> Optional[float]:
    """Provider cost of ONE unit of a platform feature (one image, one minute, one request, 1k chars …)."""
    path = FEATURE_COMPONENT.get(feature)
    if not path:
        return None
    q = quote(path[0], path[1], 1, pricing, feature)
    return q["base_usd"] if q else None


def table(pricing: dict) -> list:
    """Admin view: whole tree with computed columns per component."""
    out = []
    for p in catalog()["providers"]:
        services = []
        for s in p["services"]:
            rows = []
            for c in s["components"]:
                q = quote(s["id"], c["id"], 1.0, pricing, None) or {}
                rows.append({**c, "unit_label": UNITS.get(c["unit"], c["unit"]), "calc": q})
            services.append({**s, "components": rows})
        out.append({**p, "services": services})
    return out


# ---------- import from the providers' public docs (admin reviews the diff before applying) ----------
async def scrape(url: str) -> str:
    async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 OryntixPricingBot"}) as c:
        r = await c.get(url)
        r.raise_for_status()
    html = re.sub(r"(?is)<(script|style|svg)[^>]*>.*?</\1>", " ", r.text)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html))


def _row_prices(text: str, anchor: str, window: int = 500) -> list:
    """Prices found right after the anchor; scans every occurrence and takes the first with at least 2 numbers."""
    best = []
    start = 0
    while True:
        i = text.find(anchor, start)
        if i < 0:
            return best
        start = i + len(anchor)
        vals = [float(x.replace(",", "")) for x in re.findall(r"\$([0-9]+(?:\.[0-9]+)?)", text[start: start + window])]
        if len(vals) >= 2:
            return vals
        best = best or vals


async def import_diff(provider_id: str, pricing: dict) -> dict:
    cat = await refresh()
    prov = next((p for p in cat["providers"] if p["id"] == provider_id), None)
    if not prov or not prov.get("docs_url"):
        return {"provider": provider_id, "rows": [], "error": "Provider tidak punya docs_url"}
    text = await scrape(prov["docs_url"])
    cols = prov.get("doc_cols")
    rows, unmatched = [], []
    for s in prov["services"]:
        anchor = s.get("doc_model") or ""
        found = _row_prices(text, anchor) if anchor else []
        if not found:
            unmatched.append(s["id"])
            continue
        matched = False
        for c in s["components"]:
            col = cols.get(c["id"]) if cols is not None else c.get("doc_col")
            if col is None:
                continue
            try:
                doc_usd = found[col]
            except IndexError:
                continue
            matched = True
            cur = float(c["usd"])
            rows.append({"path": f"{prov['id']}/{s['id']}/{c['id']}", "service": s["label"], "component": c["label"],
                         "current_usd": cur, "doc_usd": doc_usd, "changed": abs(cur - doc_usd) > 1e-9})
        if not matched:
            unmatched.append(s["id"])
    return {"provider": provider_id, "docs_url": prov["docs_url"], "rows": rows,
            "unmatched": unmatched, "scraped_at": now_iso()}


async def apply_import(provider_id: str, rows: list) -> dict:
    cat = await refresh(force=True)
    by_path = {r["path"]: float(r["doc_usd"]) for r in rows if r.get("doc_usd") is not None}
    for p in cat["providers"]:
        for s in p["services"]:
            for c in s["components"]:
                key = f"{p['id']}/{s['id']}/{c['id']}"
                if key in by_path:
                    c["usd"] = by_path[key]
    return await set_catalog({k: v for k, v in cat.items() if k != "updated_at"})
