import React, { useState } from "react";
import { Share2, FileText, Download, Loader2, Sparkles, Route, ImageIcon, Clapperboard } from "lucide-react";
import { toast } from "sonner";
import { api, API_BASE, getToken } from "../lib/api";

export const fileUrl = (path, download = false) => `${API_BASE}/files/${path}?auth=${getToken()}${download ? "&download=1" : ""}`;
export const downloadUrl = (path) => fileUrl(path, true);
export const openPublish = (media, context = "") => window.dispatchEvent(new CustomEvent("oryntix:publish", { detail: { media, context } }));
const FMT = { docx: "Word", pdf: "PDF", md: "Markdown" };

// Images / downloadable files produced by the assistant (media[]) + bare media URLs found in the text.
export function MediaList({ media = [], dark = false }) {
  if (!media.length) return null;
  const chip = dark ? "bg-white/10 text-white/90 hover:bg-white/15" : "bg-[#EEF3FF] text-slate-700 hover:bg-[#E0E9FF]";
  return (
    <div className="mt-2 space-y-2" data-testid="media-list">
      {media.filter((x) => x.type === "image").map((x, i) => (
        <div key={`i${i}`} className="group relative">
          <a href={x.url || fileUrl(x.path)} target="_blank" rel="noreferrer" data-testid="media-image" className={`block min-h-[80px] overflow-hidden rounded-xl ${dark ? "bg-black/20" : "bg-slate-100"}`}>
            <img src={x.url || fileUrl(x.path)} alt={x.name || ""} className="max-h-72 w-full object-cover" />
          </a>
          {x.path && <button type="button" onClick={() => openPublish(x)} data-testid="media-publish-btn" className="absolute right-2 top-2 flex items-center gap-1 rounded-full bg-black/60 px-2.5 py-1 text-[11px] font-semibold text-white opacity-0 transition group-hover:opacity-100 hover:bg-black/80"><Share2 size={11} /> Publikasikan</button>}
        </div>
      ))}
      {media.filter((x) => x.type === "video").map((x, i) => (
        <div key={`v${i}`} className="group relative">
          <video src={x.url || fileUrl(x.path)} controls preload="metadata" className="max-h-56 w-full rounded-xl bg-black" data-testid="media-video" />
          {x.path && <button type="button" onClick={() => openPublish(x)} data-testid="media-publish-btn" className="absolute right-2 top-2 flex items-center gap-1 rounded-full bg-black/60 px-2.5 py-1 text-[11px] font-semibold text-white opacity-0 transition group-hover:opacity-100 hover:bg-black/80"><Share2 size={11} /> Publikasikan</button>}
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

export function RenderingBox({ kind = "image", dark = false }) {
  const Icon = kind === "video" ? Clapperboard : ImageIcon;
  return (
    <div data-testid={`rendering-box-${kind}`} className={`relative mt-2 w-full max-w-[420px] overflow-hidden rounded-xl border ${kind === "video" ? "aspect-video" : "aspect-[4/3]"} ${dark ? "border-white/10 bg-white/5" : "border-slate-200 bg-slate-100"}`}>
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
  : pt.count > 1 ? `Buat ${pt.count} gambar (tugas Ruang Kerja) · ±${pt.credits} kredit` : `Buat gambar · ±${pt.credits} kredit`;

export function ToolRequestCard({ m, cid, onDone, dark = false }) {
  const [busy, setBusy] = useState(m.pending_tool?.running ? "run" : "");
  if (!m.pending_tool) return null;
  if (busy === "run" && (m.pending_tool.kind === "image" || m.pending_tool.kind === "video")) return <RenderingBox kind={m.pending_tool.kind} dark={dark} />;
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
