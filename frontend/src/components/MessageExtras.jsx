import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { Share2, FileText, Download, Loader2, Sparkles, Route, ImageIcon, Clapperboard, HardDrive, ExternalLink, Coins, X, UserRound, ShieldCheck, Volume2, VolumeX } from "lucide-react";
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
export const ASPECT_LABEL = { "16:9": "16:9", "9:16": "9:16 Portrait", "1:1": "1:1 Persegi", "4:3": "4:3", "3:4": "3:4", "21:9": "21:9 Sinematik" };

export function RenderingBox({ kind = "image", dark = false, aspect = "" }) {
  const Icon = kind === "video" ? Clapperboard : ImageIcon;
  const shape = kind === "video" ? (BOX_ASPECT[aspect] || "aspect-video max-w-[420px]") : "aspect-[4/3] max-w-[420px]";
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

const TOOL_LABEL = (pt) => pt.kind === "social" ? `Posting ke ${(pt.providers || []).join(", ")}`
  : pt.kind === "video" ? `Render video ±5 detik · ±${pt.credits} kredit`
  : pt.kind === "image_edit" ? `Edit gambar terakhir · ±${pt.credits} kredit`
  : pt.count > 1 ? `Buat ${pt.count} gambar (tugas Ruang Kerja) · ±${pt.credits} kredit` : `Buat gambar · ±${pt.credits} kredit`;

const fmtCredits = (n) => Number(n || 0).toLocaleString("id-ID", { maximumFractionDigits: n >= 100 ? 0 : 2 });

// Call-to-action attached by the assistant (e.g. connect Google Drive before rendering a video).
export function MessageCta({ m, dark = false }) {
  if (!m.cta?.href) return null;
  return <Link to={m.cta.href} data-testid="msg-cta" className={`mt-2 inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold transition ${dark ? "bg-white text-slate-900 hover:bg-white/90" : "bg-[#2F6BFF] text-white hover:bg-[#2558d6]"}`}>{m.cta.label} <ExternalLink size={11} /></Link>;
}

// Seedance 2.0 vs 2.5 picker with resolution + real-person options: per-second platform price, clip total and whether the balance covers it.
const RES_OPTS = [["480p", "480p", "Hemat"], ["720p", "720p", "Standar"], ["1080p", "1080p", "Tajam"]];
function VideoChoiceCard({ m, cid, onDone, dark }) {
  const pt = m.pending_tool;
  const [busy, setBusy] = useState(pt?.running ? "run" : "");
  const [res, setRes] = useState(pt.resolution || "720p");
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
    try { await api.post(`/conversations/${cid}/messages/${m.id}/run-tool`, null, { params: { choice: tier, resolution: res, real_person: real, with_audio: audio, app_url: window.location.origin } }); await onDone?.(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal memulai render video"); setBusy(""); }
  };
  const cancel = async () => { setBusy("cancel"); try { await api.post(`/conversations/${cid}/messages/${m.id}/cancel-tool`); await onDone?.(); } catch { setBusy(""); } };
  if (busy && busy !== "cancel") return <RenderingBox kind="video" dark={dark} aspect={pt.aspect_ratio} />;
  const seg = (on) => `rounded-lg px-2.5 py-1 text-[11px] font-semibold transition ${on ? (dark ? "bg-white text-slate-900" : "bg-[#2F6BFF] text-white") : (dark ? "bg-white/10 hover:bg-white/15" : "bg-white hover:bg-slate-100")}`;
  return (
    <div data-testid="video-choice-card" className={`mt-2 rounded-xl border p-3 text-xs ${dark ? "border-amber-300/30 bg-amber-300/10 text-amber-50" : "border-amber-300 bg-amber-50 text-amber-900"}`}>
      <p className="mb-2 flex items-center gap-1.5 font-semibold"><Clapperboard size={14} /> Video {pt.duration} detik{pt.aspect_ratio && pt.aspect_ratio !== "16:9" ? ` · ${ASPECT_LABEL[pt.aspect_ratio] || pt.aspect_ratio}` : ""} <span className={`ml-auto flex items-center gap-1 font-normal ${dark ? "text-white/60" : "text-amber-700"}`}><Coins size={11} /> saldo {fmtCredits(pt.balance)}</span></p>
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

export function ToolRequestCard({ m, cid, onDone, dark = false }) {
  const [busy, setBusy] = useState(m.pending_tool?.running ? "run" : "");
  if (!m.pending_tool) return null;
  if (m.pending_tool.kind === "video" && m.pending_tool.options) return <VideoChoiceCard m={m} cid={cid} onDone={onDone} dark={dark} />;
  if (busy === "run" && ["image", "image_edit", "video"].includes(m.pending_tool.kind)) return <RenderingBox kind={m.pending_tool.kind} dark={dark} />;
  const act = async (kind) => {
    setBusy(kind);
    try { await api.post(`/conversations/${cid}/messages/${m.id}/${kind === "run" ? "run-tool" : "cancel-tool"}`, null, { params: kind === "run" ? { app_url: window.location.origin } : {} }); await onDone?.(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menjalankan alat"); setBusy(""); }
  };
  return (
    <div data-testid="tool-request-card" className={`mt-2 flex flex-wrap items-center gap-2 rounded-xl border px-3 py-2 text-xs ${dark ? "border-amber-300/30 bg-amber-300/10 text-amber-100" : "border-amber-300 bg-amber-50 text-amber-900"}`}>
      {m.pending_tool.kind === "video" ? <Clapperboard size={14} /> : <ImageIcon size={14} />}<span className="flex-1 font-semibold">{TOOL_LABEL(m.pending_tool)}</span>
      <button onClick={() => act("run")} disabled={!!busy} data-testid="tool-run-btn" className="flex items-center gap-1 rounded-lg bg-[#2F6BFF] px-3 py-1.5 font-bold text-white disabled:opacity-60">{busy === "run" ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />} Lanjutkan</button>
      <button onClick={() => act("cancel")} disabled={!!busy} data-testid="tool-cancel-btn" className={`rounded-lg px-3 py-1.5 font-semibold disabled:opacity-60 ${dark ? "bg-white/10" : "bg-white"}`}>Batal</button>
    </div>
  );
}

const REASON = { it: "topik IT/coding", research: "riset & analisis panjang" };

export function ModelBadge({ m, dark = false }) {
  if (!m.routed || !m.model_label) return null;
  return (
    <span data-testid="model-badge" title={`Dialihkan otomatis karena ${REASON[m.routed] || m.routed}`} className={`mt-1 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${dark ? "bg-white/10 text-white/60" : "bg-slate-100 text-slate-500"}`}>
      <Route size={10} /> via {m.model_label}
    </span>
  );
}
