import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { Share2, FileText, Download, Loader2, Sparkles, Route, ImageIcon, Clapperboard, HardDrive, ExternalLink, Coins, X, UserRound, ShieldCheck, Volume2, VolumeX, Save, AlarmClock, ChevronDown } from "lucide-react";
import { SocialPreview } from "./SocialPreview";
import { toast } from "sonner";
import { api, API_BASE, getToken } from "../lib/api";

export const fileUrl = (path, download = false) => `${API_BASE}/files/${path}?auth=${getToken()}${download ? "&download=1" : ""}`;
export const downloadUrl = (path) => fileUrl(path, true);
export const driveMediaUrl = (driveId) => `${API_BASE}/integrations/google/media/${driveId}?auth=${getToken()}`;
export const mediaSrc = (x) => x.url || (x.drive_id ? driveMediaUrl(x.drive_id) : fileUrl(x.path));
export const openPublish = (media, context = "") => window.dispatchEvent(new CustomEvent("oryntix:publish", { detail: { media, context } }));
const FMT = { docx: "Word", pdf: "PDF", md: "Markdown" };

// Images / downloadable files produced by the assistant (media[]) + bare media URLs found in the text.
// Full-size image viewer (portal so message-bubble transforms can't clip it); Esc or backdrop closes.
export function Lightbox({ media, onClose }) {
  useEffect(() => { const k = (e) => e.key === "Escape" && onClose(); window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [onClose]);
  if (!media) return null;
  const src = media.url || fileUrl(media.path);
  return createPortal(
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/90 p-4 sm:p-8 fade-up" onClick={(e) => { e.stopPropagation(); onClose(); }} data-testid="image-lightbox">
      <button type="button" onClick={onClose} aria-label="Tutup" data-testid="lightbox-close" className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white hover:bg-white/20"><X size={20} /></button>
      <img src={src} alt={media.name || ""} onClick={(e) => e.stopPropagation()} className="max-h-[85vh] max-w-full rounded-xl object-contain shadow-2xl" data-testid="lightbox-image" />
      <div className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-full bg-black/60 px-3 py-1.5 text-xs text-white" onClick={(e) => e.stopPropagation()}>
        {media.request || media.prompt ? <span className="max-w-[40vw] truncate opacity-80">{media.request || media.prompt}</span> : null}
        {media.path && <a href={downloadUrl(media.path)} download={media.name || "gambar.jpg"} className="flex items-center gap-1 rounded-full bg-white/10 px-2.5 py-1 font-semibold hover:bg-white/20" data-testid="lightbox-download"><Download size={12} /> Unduh</a>}
        {media.path && <button type="button" onClick={() => { onClose(); openPublish(media, media.request || media.prompt || ""); }} className="flex items-center gap-1 rounded-full bg-white/10 px-2.5 py-1 font-semibold hover:bg-white/20" data-testid="lightbox-publish"><Share2 size={12} /> Publikasikan</button>}
      </div>
    </div>, document.body);
}

export function MediaList({ media = [], dark = false }) {
  const [zoom, setZoom] = useState(null);
  if (!media.length) return null;
  const chip = dark ? "bg-white/10 text-white/90 hover:bg-white/15" : "bg-[#EEF3FF] text-slate-700 hover:bg-[#E0E9FF]";
  return (
    <div className="mt-2 space-y-2" data-testid="media-list">
      {zoom && <Lightbox media={zoom} onClose={() => setZoom(null)} />}
      {media.filter((x) => x.type === "image").map((x, i) => (
        <div key={`i${i}`} className="group relative">
          <button type="button" onClick={() => setZoom(x)} data-testid="media-image" className={`block w-full min-h-[80px] cursor-zoom-in overflow-hidden rounded-xl text-left ${dark ? "bg-black/20" : "bg-slate-100"}`}>
            <img src={x.url || fileUrl(x.path)} alt={x.name || ""} className="max-h-72 w-full object-cover transition group-hover:scale-[1.01]" />
          </button>
          {x.quality && <span className={`mt-1 block text-[11px] ${dark ? "text-white/50" : "text-slate-400"}`} data-testid="media-image-meta">{x.model}{x.preset ? ` · ${x.preset}` : ""} · {ASPECT_LABEL[x.aspect_ratio] || x.aspect_ratio} · kualitas {x.quality}</span>}
          {x.path && <button type="button" onClick={() => openPublish(x)} data-testid="media-publish-btn" className="absolute right-2 top-2 flex items-center gap-1 rounded-full bg-black/60 px-2.5 py-1 text-[11px] font-semibold text-white opacity-0 transition group-hover:opacity-100 hover:bg-black/80"><Share2 size={11} /> Publikasikan</button>}
        </div>
      ))}
      {media.filter((x) => x.type === "video").map((x, i) => (
        <div key={`v${i}`} className="group relative">
          <video src={mediaSrc(x)} controls preload="metadata" className="max-h-56 w-full rounded-xl bg-black" data-testid="media-video" />
          {(x.path || x.drive_id) && <button type="button" onClick={() => openPublish(x, x.request || x.prompt || "")} data-testid="media-publish-btn" className="absolute right-2 top-2 flex items-center gap-1 rounded-full bg-black/60 px-2.5 py-1 text-[11px] font-semibold text-white opacity-0 transition group-hover:opacity-100 hover:bg-black/80"><Share2 size={11} /> Publikasikan</button>}
          {x.link && <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px]">
            <a href={x.link} target="_blank" rel="noreferrer" data-testid="media-drive-link" className={`flex items-center gap-1 rounded-lg px-2.5 py-1 font-semibold transition ${chip}`}><HardDrive size={12} /> Buka di Google Drive <ExternalLink size={10} className="opacity-60" /></a>
            {x.tier && <span className={dark ? "text-white/50" : "text-slate-400"} data-testid="media-video-meta">Seedance {x.tier} · {x.duration}s{x.resolution ? ` · ${x.resolution}` : ""}{x.aspect_ratio ? ` · ${ASPECT_LABEL[x.aspect_ratio] || x.aspect_ratio}` : ""}{x.real_person ? " · real person" : ""}{x.audio ? " · dengan suara" : ""}</span>}
          </div>}
        </div>
      ))}
      {media.some((x) => x.type === "file") && (
        <div className="flex flex-wrap gap-1.5">
          {media.filter((x) => x.type === "file").map((x, i) => (
            <a key={`f${i}`} href={x.url || downloadUrl(x.path)} target="_blank" rel="noreferrer" download={x.name} data-testid={`media-file-${x.format || "file"}`} className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition ${chip}`}>
              <FileText size={13} /> {FMT[x.format] || x.name} <Download size={12} className="opacity-60" />
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

// "Buat gambar? ±25 kredit" confirmation for expensive tools.
const RENDER_LABEL = { image: "Merender gambar…", video: "Merender video… (±2–5 menit)" };

const BOX_ASPECT = { "9:16": "aspect-[9/16] max-w-[240px]", "3:4": "aspect-[3/4] max-w-[320px]", "1:1": "aspect-square max-w-[320px]", "4:3": "aspect-[4/3] max-w-[420px]", "21:9": "aspect-[21/9] max-w-[480px]" };
export const ASPECT_LABEL = { "16:9": "16:9 Lanskap", "9:16": "9:16 Potret", "1:1": "1:1 Persegi", "4:3": "4:3", "3:4": "3:4", "21:9": "21:9 Ultra-lebar" };

export function RenderingBox({ kind = "image", dark = false, aspect = "" }) {
  const Icon = kind === "video" ? Clapperboard : ImageIcon;
  const shape = kind === "video" ? (BOX_ASPECT[aspect] || "aspect-video max-w-[420px]") : (BOX_ASPECT[aspect] || "aspect-[4/3] max-w-[420px]");
  return (
    <div data-testid={`rendering-box-${kind}`} className={`relative mt-2 w-full overflow-hidden rounded-xl border ${shape} ${dark ? "border-white/10 bg-white/5" : "border-slate-200 bg-slate-100"}`}>
      <div className="render-shimmer absolute inset-0" />
      <div className={`relative flex h-full flex-col items-center justify-center gap-2 ${dark ? "text-white/70" : "text-slate-500"}`}>
        <span className={`flex h-11 w-11 items-center justify-center rounded-full ${dark ? "bg-white/10" : "bg-white shadow-sm"}`}><Icon size={20} className="animate-pulse text-[#2F6BFF]" /></span>
        <span className="flex items-center gap-1.5 text-xs font-semibold"><Loader2 size={12} className="animate-spin" /> {RENDER_LABEL[kind] || RENDER_LABEL.image}</span>
      </div>
    </div>
  );
}

const TOOL_LABEL = (pt) => pt.kind === "social" ? `${pt.schedule_at ? "Jadwalkan posting" : "Posting"} ke ${(pt.providers || []).join(", ")}`
  : pt.kind === "video" ? `Render video ±5 detik · ±${pt.credits} kredit`
  : pt.kind === "image_edit" ? `Edit gambar terakhir · ±${pt.credits} kredit`
  : pt.count > 1 ? `Buat ${pt.count} gambar (tugas Ruang Kerja) · ±${pt.credits} kredit` : `Buat gambar · ±${pt.credits} kredit`;

const fmtCredits = (n) => Number(n || 0).toLocaleString("id-ID", { maximumFractionDigits: n >= 100 ? 0 : 2 });

// Call-to-action attached by the assistant (e.g. connect Google Drive before rendering a video).
export function MessageCta({ m, dark = false }) {
  if (!m.cta?.href) return null;
  return <Link to={m.cta.href} data-testid="msg-cta" className={`mt-2 inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition ${dark ? "bg-white text-slate-900 hover:bg-white/90" : "bg-[#2F6BFF] text-white hover:bg-[#2558d6]"}`}>{m.cta.label} <ExternalLink size={11} /></Link>;
}

const SEL_CLS = (dark) => `w-full appearance-none rounded-lg border py-1.5 pl-2.5 pr-7 text-[11px] font-semibold outline-none transition focus:ring-2 focus:ring-[#2F6BFF]/40 ${dark ? "border-white/15 bg-white/10 text-white [&>option]:text-slate-900" : "border-amber-200 bg-white text-slate-800"}`;
function Combo({ label, value, onChange, items, testid, dark }) {
  return (
    <label className="flex min-w-[140px] flex-1 flex-col gap-1 sm:max-w-[240px]" data-testid={`${testid}-picker`}>
      <span className={dark ? "text-white/60" : "text-amber-700"}>{label}</span>
      <span className="relative block">
        <select value={value} onChange={(e) => onChange(e.target.value)} className={SEL_CLS(dark)} data-testid={testid}>
          {items.map(([v, l, hint]) => <option key={v} value={v}>{l}{hint ? ` — ${hint}` : ""}</option>)}
        </select>
        <ChevronDown size={13} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 opacity-60" />
      </span>
    </label>
  );
}
// Seedance 2.0 vs 2.5 picker with resolution + real-person options: per-second platform price, clip total and whether the balance covers it.
const RES_OPTS = [["480p", "480p", "Hemat"], ["720p", "720p", "Standar"], ["1080p", "1080p", "Tajam"]];
const VIDEO_ASPECTS = [["16:9", "Lanskap 16:9", "YouTube"], ["9:16", "Potret 9:16", "Reels / Shorts / TikTok"], ["1:1", "Persegi 1:1", "feed Instagram"], ["4:3", "4:3"], ["3:4", "3:4"], ["21:9", "Sinematik 21:9"]];
function VideoChoiceCard({ m, cid, onDone, dark }) {
  const pt = m.pending_tool;
  const [busy, setBusy] = useState(pt?.running ? "run" : "");
  const [res, setRes] = useState(pt.resolution || "720p");
  const [vAspect, setVAspect] = useState(pt.aspect_ratio || "16:9");
  const [real, setReal] = useState(!!pt.real_person);
  const [audio, setAudio] = useState(!!pt.with_audio);
  const [consent, setConsent] = useState(false);
  const mult = pt.multipliers || { res: { "480p": 0.6, "720p": 1, "1080p": 1.6 }, real_person: 1.45, audio: 1 };
  const canReal = !!pt.reference_path && (pt.options || []).some((o) => o.real_person);
  const canAudio = (pt.options || []).some((o) => o.audio);
  const price = (o) => Math.max(1, Math.ceil(o.per_sec * pt.duration * (mult.res[res] ?? 1) * (real ? mult.real_person : 1) * (audio ? (mult.audio ?? 1) : 1)));
  const supported = (o) => pt.duration <= o.max_dur && (o.resolutions || ["720p"]).includes(res) && (!real || o.real_person) && (!audio || o.audio);
  const pick = async (tier) => {
    setBusy(tier);
    try { await api.post(`/conversations/${cid}/messages/${m.id}/run-tool`, null, { params: { choice: tier, resolution: res, aspect: vAspect, real_person: real, with_audio: audio, app_url: window.location.origin } }); await onDone?.(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal memulai render video"); setBusy(""); }
  };
  const cancel = async () => { setBusy("cancel"); try { await api.post(`/conversations/${cid}/messages/${m.id}/cancel-tool`); await onDone?.(); } catch { setBusy(""); } };
  if (busy && busy !== "cancel") return <RenderingBox kind="video" dark={dark} aspect={vAspect} />;
  const seg = (on) => `rounded-lg px-2.5 py-1 text-[11px] font-semibold transition ${on ? (dark ? "bg-white text-slate-900" : "bg-[#2F6BFF] text-white") : (dark ? "bg-white/10 hover:bg-white/15" : "bg-white hover:bg-slate-100")}`;
  return (
    <div data-testid="video-choice-card" className={`mt-2 rounded-xl border p-3 text-xs ${dark ? "border-amber-300/30 bg-amber-300/10 text-amber-50" : "border-amber-300 bg-amber-50 text-amber-900"}`}>
      <p className="mb-2 flex items-center gap-1.5 font-semibold"><Clapperboard size={14} /> Video {pt.duration} detik{vAspect !== "16:9" ? ` · ${ASPECT_LABEL[vAspect] || vAspect}` : ""} <span className={`ml-auto flex items-center gap-1 font-normal ${dark ? "text-white/60" : "text-amber-700"}`}><Coins size={11} /> saldo {fmtCredits(pt.balance)}</span></p>
      <div className="mb-2 flex flex-wrap gap-2">
        <Combo label="Rasio" value={vAspect} onChange={setVAspect} items={VIDEO_ASPECTS} testid="video-aspect" dark={dark} />
      </div>
      <div className="mb-2 flex flex-wrap items-center gap-1.5" data-testid="video-res-picker">
        <span className={`mr-1 ${dark ? "text-white/60" : "text-amber-700"}`}>Resolusi</span>
        {RES_OPTS.map(([v, l, hint]) => <button key={v} type="button" onClick={() => setRes(v)} className={seg(res === v)} data-testid={`video-res-${v}`} title={`×${mult.res[v] ?? 1}`}>{l} <span className="font-normal opacity-70">{hint}</span></button>)}
      </div>
      {canReal && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5" data-testid="video-mode-picker">
          <span className={`mr-1 ${dark ? "text-white/60" : "text-amber-700"}`}>Mode</span>
          <button type="button" onClick={() => setReal(false)} className={seg(!real)} data-testid="video-mode-normal">Normal</button>
          <button type="button" onClick={() => setReal(true)} className={`${seg(real)} flex items-center gap-1`} data-testid="video-mode-real"><UserRound size={11} /> Real person <span className="font-normal opacity-70">×{mult.real_person}</span></button>
        </div>
      )}
      {canAudio && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5" data-testid="video-audio-picker">
          <span className={`mr-1 ${dark ? "text-white/60" : "text-amber-700"}`}>Suara</span>
          <button type="button" onClick={() => setAudio(false)} className={`${seg(!audio)} flex items-center gap-1`} data-testid="video-audio-off"><VolumeX size={11} /> Tanpa suara</button>
          <button type="button" onClick={() => setAudio(true)} className={`${seg(audio)} flex items-center gap-1`} data-testid="video-audio-on"><Volume2 size={11} /> Dengan suara & ambience {mult.audio && mult.audio !== 1 ? <span className="font-normal opacity-70">×{mult.audio}</span> : null}</button>
        </div>
      )}
      {real && (
        <label className={`mb-2 flex cursor-pointer items-start gap-2 rounded-lg px-2.5 py-2 ${dark ? "bg-white/10" : "bg-white"}`} data-testid="video-consent">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5" data-testid="video-consent-check" />
          <span className="flex items-start gap-1.5"><ShieldCheck size={13} className="mt-0.5 shrink-0" /> Saya memiliki hak dan izin atas orang yang ada di gambar ini (wajib untuk mode real person).</span>
        </label>
      )}
      <div className="grid gap-2 sm:grid-cols-2">
        {(pt.options || []).map((o) => {
          const sup = supported(o); const cr = price(o); const ok = sup && cr <= pt.balance && (!real || consent);
          return (
            <button key={o.tier} type="button" disabled={!ok || !!busy} onClick={() => pick(o.tier)} data-testid={`video-choice-${o.tier}`}
              className={`flex flex-col items-start rounded-lg border px-3 py-2 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${dark ? "border-white/15 bg-white/10 hover:bg-white/15" : "border-[#2F6BFF]/30 bg-white hover:border-[#2F6BFF] hover:shadow-sm"}`}>
              <span className="flex w-full items-center gap-1 font-bold">{o.label}<span className={`ml-auto font-black ${dark ? "text-white" : "text-[#2F6BFF]"}`}>±{fmtCredits(cr)} kredit</span></span>
              <span className={`mt-0.5 ${dark ? "text-white/60" : "text-slate-500"}`}>{fmtCredits(cr / pt.duration)} kredit/detik · {res}{real ? " · real person" : ""}{audio ? " · suara" : ""}
                {!sup ? (pt.duration > o.max_dur ? ` · maks ${o.max_dur} dtk` : real && !o.real_person ? " · tidak ada mode real person" : audio && !o.audio ? " · tidak ada opsi suara" : ` · tidak ada ${res}`) : cr > pt.balance ? " · saldo tidak cukup" : real && !consent ? " · centang izin dulu" : ""}</span>
            </button>
          );
        })}
      </div>
      <button type="button" onClick={cancel} disabled={!!busy} data-testid="tool-cancel-btn" className={`mt-2 rounded-lg px-3 py-1.5 font-semibold disabled:opacity-60 ${dark ? "bg-white/10" : "bg-white"}`}>Batal</button>
    </div>
  );
}

// Image confirmation with model choice (Nano Banana vs GPT Image) + aspect ratio & quality — picking a model runs the tool.
const IMG_ASPECTS = [["1:1", "Persegi"], ["16:9", "Lanskap"], ["9:16", "Potret"], ["4:3", "4:3"], ["3:4", "3:4"], ["21:9", "Ultra-lebar"]];
const IMG_QUALITIES = [["hemat", "Hemat", "1K · draf"], ["standar", "Standar", "2K"], ["tinggi", "Tinggi", "4K · detail"]];
function ImageChoiceCard({ m, cid, onDone, dark = false }) {
  const [busy, setBusy] = useState(m.pending_tool?.running ? "run" : "");
  const pt = m.pending_tool;
  const [aspect, setAspect] = useState(pt.aspect_ratio || "1:1");
  const [quality, setQuality] = useState(pt.quality || "standar");
  const [preset, setPreset] = useState(pt.preset || "");
  const presets = pt.presets || [];
  const choosePreset = (id) => { setPreset(id); const p = presets.find((x) => x.id === id); if (p) setAspect(p.aspect); };
  const chooseAspect = (v) => { setAspect(v); if (preset && presets.find((x) => x.id === preset)?.aspect !== v) setPreset(""); };
  if (busy === "run") return <RenderingBox kind={pt.kind} dark={dark} aspect={aspect} />;
  const pick = async (id) => {
    setBusy("run");
    try { await api.post(`/conversations/${cid}/messages/${m.id}/run-tool`, null, { params: { choice: id, aspect, quality, preset: preset || undefined, app_url: window.location.origin } }); await onDone?.(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat gambar"); setBusy(""); }
  };
  const cancel = async () => { setBusy("cancel"); try { await api.post(`/conversations/${cid}/messages/${m.id}/cancel-tool`); await onDone?.(); } catch (e) { setBusy(""); } };
  const price = (o) => o.prices?.[quality]?.[aspect] ?? o.credits;
  const lbl = dark ? "text-white/60" : "text-amber-700";
  return (
    <div data-testid="tool-request-card" className={`mt-2 rounded-xl border p-3 text-xs ${dark ? "border-amber-300/30 bg-amber-300/10 text-amber-100" : "border-amber-300 bg-amber-50 text-amber-900"}`}>
      <p className="mb-2 flex items-center gap-1.5 font-semibold"><ImageIcon size={14} /> {pt.kind === "image_edit" ? "Edit gambar terakhir" : "Buat gambar"}</p>
      <div className="mb-3 flex flex-wrap gap-2">
        {presets.length > 0 && <Combo label="Preset sosial" value={preset} onChange={choosePreset} items={[["", "Kustom"], ...presets.map((p) => [p.id, p.label, p.aspect])]} testid="image-preset" dark={dark} />}
        <Combo label="Rasio" value={aspect} onChange={chooseAspect} items={IMG_ASPECTS.map(([v, l]) => [v, `${l} ${v}`])} testid="image-aspect" dark={dark} />
        <Combo label="Kualitas" value={quality} onChange={setQuality} items={IMG_QUALITIES} testid="image-quality" dark={dark} />
      </div>
      <p className={`mb-1.5 ${lbl}`}>Pilih model:</p>
      <div className="grid gap-2 sm:grid-cols-2">
        {pt.options.map((o) => (
          <button key={o.id} type="button" disabled={!o.available || !!busy} onClick={() => pick(o.id)} data-testid={`image-choice-${o.id}`}
            className={`rounded-xl border p-2.5 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${dark ? "border-white/15 bg-white/5 hover:bg-white/10" : "border-amber-200 bg-white hover:border-[#2F6BFF]"}`}>
            <span className="flex items-center justify-between gap-2"><span className="font-bold">{o.label}</span><span className="inline-flex items-center gap-1 font-semibold text-[#2F6BFF]" data-testid={`image-price-${o.id}`}><Coins size={11} /> {price(o)} kredit</span></span>
            <span className={`block text-[11px] ${dark ? "text-white/60" : "text-slate-500"}`}>{o.desc}{o.id === "gpt-image" && ["4:3", "3:4"].includes(aspect) ? " · dirender 3:2 (ukuran terdekat)" : ""}{!o.available ? " · kunci provider belum diatur" : ""}</span>
          </button>
        ))}
      </div>
      <div className="mt-2 flex justify-end"><button onClick={cancel} disabled={!!busy} data-testid="tool-cancel-btn" className={`rounded-lg px-3 py-1.5 font-semibold disabled:opacity-60 ${dark ? "bg-white/10" : "bg-white"}`}>Batal</button></div>
    </div>
  );
}

export function ToolRequestCard({ m, cid, onDone, dark = false }) {
  const [busy, setBusy] = useState(m.pending_tool?.running ? "run" : "");
  const [draft, setDraft] = useState({});
  if (!m.pending_tool) return null;
  if (m.pending_tool.kind === "video" && m.pending_tool.options) return <VideoChoiceCard m={m} cid={cid} onDone={onDone} dark={dark} />;
  if (["image", "image_edit"].includes(m.pending_tool.kind) && m.pending_tool.options?.length) return <ImageChoiceCard m={m} cid={cid} onDone={onDone} dark={dark} />;
  if (busy === "run" && ["image", "image_edit", "video"].includes(m.pending_tool.kind)) return <RenderingBox kind={m.pending_tool.kind} dark={dark} />;
  const act = async (kind) => {
    setBusy(kind);
    const edits = kind === "run" && m.pending_tool.kind === "social" ? { caption: draft.caption, title: draft.title } : {};
    try { await api.post(`/conversations/${cid}/messages/${m.id}/${kind === "run" ? "run-tool" : "cancel-tool"}`, null, { params: kind === "run" ? { app_url: window.location.origin, ...edits } : {} }); await onDone?.(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menjalankan alat"); setBusy(""); }
  };
  const social = m.pending_tool.kind === "social";
  return (
    <div data-testid="tool-request-card" className={`mt-2 flex flex-wrap items-center gap-2 rounded-xl border px-3 py-2 text-xs ${dark ? "border-amber-300/30 bg-amber-300/10 text-amber-100" : "border-amber-300 bg-amber-50 text-amber-900"}`}>
      {m.pending_tool.kind === "video" ? <Clapperboard size={14} /> : social ? <Share2 size={14} /> : <ImageIcon size={14} />}<span className="flex-1 font-semibold">{TOOL_LABEL(m.pending_tool)}</span>
      {social && <SocialPreview pt={m.pending_tool} dark={dark} draft={draft} onDraft={setDraft} />}
      <button onClick={() => act("run")} disabled={!!busy} data-testid="tool-run-btn" className="flex items-center gap-1 rounded-lg bg-[#2F6BFF] px-3 py-1.5 font-bold text-white disabled:opacity-60">{busy === "run" ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />} Lanjutkan</button>
      <button onClick={() => act("cancel")} disabled={!!busy} data-testid="tool-cancel-btn" className={`rounded-lg px-3 py-1.5 font-semibold disabled:opacity-60 ${dark ? "bg-white/10" : "bg-white"}`}>Batal</button>
    </div>
  );
}

const REASON = { it: "topik IT/coding", research: "riset & analisis panjang" };

// Chat-mode reminder message → "Ingatkan lagi 10 menit" (snooze) button.
export function ReminderCard({ m, dark = false }) {
  const [done, setDone] = useState(false);
  if (m.tool !== "reminder" || !m.reminder?.id) return null;
  const snooze = async () => {
    try { await api.post(`/reminders/${m.reminder.id}/snooze`, { minutes: 10 }); setDone(true); toast.success("Oke, akan diingatkan lagi 10 menit lagi"); }
    catch (e) { toast.error(e?.response?.status === 404 ? "Pengingat ini sudah tidak aktif" : "Gagal menunda"); }
  };
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2" data-testid="reminder-card">
      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${dark ? "bg-white/10 text-white/70" : "bg-amber-50 text-amber-700"}`}><AlarmClock size={10} /> Pengingat{m.reminder.snoozed ? " ulang" : ""}: {m.reminder.title}</span>
      {!done && <button type="button" onClick={snooze} data-testid="reminder-snooze-btn" className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-bold transition ${dark ? "bg-white text-slate-900 hover:bg-white/90" : "bg-[#0B132B] text-white hover:bg-[#1c2749]"}`}><AlarmClock size={11} /> Ingatkan lagi 10 menit</button>}
      {done && <span className={`text-[11px] ${dark ? "text-white/60" : "text-slate-500"}`} data-testid="reminder-snoozed">Ditunda 10 menit ✓</span>}
    </div>
  );
}

export const pendingUrl = (id) => `${API_BASE}/pending-files/${id}?auth=${getToken()}`;
const fmtSize = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

// Files produced by a provider tool (chart PNG / CSV / GPT image) that are only HELD until the user confirms where to save them.
export function PendingFiles({ m, cid, onDone, dark = false }) {
  const [busy, setBusy] = useState("");
  const [drive, setDrive] = useState(null);
  const files = m.pending_files || [];
  useEffect(() => { if (files.length && drive === null) api.get("/integrations/google/status").then((r) => setDrive(!!r.data?.connected)).catch(() => setDrive(false)); }, [files.length, drive]);
  if (!files.length) return null;
  const act = async (f, target) => {
    setBusy(`${f.id}:${target}`);
    try {
      if (target === "discard") await api.delete(`/pending-files/${f.id}`, { params: { message_id: m.id } });
      else await api.post(`/pending-files/${f.id}/save`, { message_id: m.id, target });
      toast.success(target === "discard" ? "Berkas dibuang" : target === "drive" ? `Tersimpan di Google Drive: ${f.name}` : `Tersimpan: ${f.name}`);
      await onDone?.();
    } catch (e) {
      const st = e?.response?.status; const detail = e?.response?.data?.detail || "Gagal menyimpan";
      toast.error(detail, st === 413 || st === 400 ? { action: { label: "Buka Integrasi", onClick: () => { window.location.href = "/integrations"; } }, duration: 9000 } : undefined);
    } finally { setBusy(""); }
  };
  const btn = dark ? "bg-white/10 text-white hover:bg-white/15" : "bg-white text-slate-700 hover:bg-slate-100";
  return (
    <div className="mt-2 space-y-2" data-testid="pending-files">
      {files.map((f) => (
        <div key={f.id} data-testid={`pending-file-${f.kind}`} className={`rounded-xl border p-2 text-xs ${dark ? "border-amber-300/30 bg-amber-300/10 text-amber-50" : "border-amber-300 bg-amber-50 text-amber-900"}`}>
          {f.kind === "image" ? <img src={pendingUrl(f.id)} alt={f.name} className="mb-2 max-h-72 w-full rounded-lg object-contain bg-black/5" data-testid="pending-file-preview" />
            : <a href={pendingUrl(f.id)} target="_blank" rel="noreferrer" className="mb-2 flex items-center gap-1.5 font-semibold underline-offset-2 hover:underline"><FileText size={13} /> {f.name} <span className="font-normal opacity-70">· {fmtSize(f.size)}</span></a>}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-auto flex items-center gap-1 font-semibold"><Save size={12} /> Simpan {f.kind === "image" ? "gambar" : "berkas"} ini? <span className="font-normal opacity-70">(sementara, 2 jam)</span></span>
            <button type="button" disabled={!!busy} onClick={() => act(f, "storage")} data-testid="pending-save-btn" className="flex items-center gap-1 rounded-lg bg-[#2F6BFF] px-2.5 py-1.5 font-bold text-white disabled:opacity-60">{busy === `${f.id}:storage` ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} Simpan</button>
            {drive && <button type="button" disabled={!!busy} onClick={() => act(f, "drive")} data-testid="pending-save-drive-btn" className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 font-semibold disabled:opacity-60 ${btn}`}>{busy === `${f.id}:drive` ? <Loader2 size={12} className="animate-spin" /> : <HardDrive size={12} />} Ke Drive</button>}
            <button type="button" disabled={!!busy} onClick={() => act(f, "discard")} data-testid="pending-discard-btn" className={`rounded-lg px-2.5 py-1.5 font-semibold disabled:opacity-60 ${btn}`}>Buang</button>
          </div>
        </div>
      ))}
    </div>
  );
}

// Provider built-in tools the assistant used for this reply (+ credits) and the sources it cited.
export function ToolUsage({ m, dark = false }) {
  const used = (m.tools_used || []).filter((t) => t.count > 0);
  const cites = m.citations || [];
  if (!used.length && !cites.length) return null;
  const pill = dark ? "bg-white/10 text-white/70" : "bg-[#EEF3FF] text-[#2F6BFF]";
  return (
    <div className="mt-1 space-y-1" data-testid="tool-usage">
      {used.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {used.map((t) => <span key={t.id} data-testid={`tool-used-${t.id.replace(":", "-")}`} className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${pill}`}><Sparkles size={10} /> {t.label}{t.count > 1 ? ` ×${t.count}` : ""}{t.credits ? ` · ${t.credits} kredit` : ""}</span>)}
        </div>
      )}
      {cites.length > 0 && (
        <details className={`text-[11px] ${dark ? "text-white/60" : "text-slate-500"}`} data-testid="tool-citations">
          <summary className="cursor-pointer select-none font-semibold">Sumber ({cites.length})</summary>
          <ol className="mt-1 list-decimal space-y-0.5 pl-4">
            {cites.map((c, i) => <li key={i}><a href={c.url} target="_blank" rel="noreferrer" className="underline-offset-2 hover:underline">{c.title || c.url}</a></li>)}
          </ol>
        </details>
      )}
    </div>
  );
}

export function ModelBadge({ m, dark = false }) {
  if (!m.routed || !m.model_label) return null;
  return (
    <span data-testid="model-badge" title={`Dialihkan otomatis karena ${REASON[m.routed] || m.routed}`} className={`mt-1 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${dark ? "bg-white/10 text-white/60" : "bg-slate-100 text-slate-500"}`}>
      <Route size={10} /> via {m.model_label}
    </span>
  );
}
