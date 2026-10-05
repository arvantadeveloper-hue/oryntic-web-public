import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X, Download, Share2, Copy, Loader2, ExternalLink, Clock, Ban, HardDrive } from "lucide-react";
import { toast } from "sonner";
import { api, API_BASE, getToken } from "../lib/api";
import { fileUrl, downloadUrl } from "./MessageExtras";
import { Markdown } from "./Markdown";

const HOURS = [[1, "1 jam"], [24, "24 jam"], [168, "7 hari"], [720, "30 hari"]];
const exportUrl = (taskId, fmt) => `${API_BASE}/tasks/${taskId}/export/${fmt}?auth=${getToken()}`;

export function ShareModal({ item, onClose }) {
  const [hours, setHours] = useState(24);
  const [link, setLink] = useState(null);
  const [busy, setBusy] = useState(false);
  const [mine, setMine] = useState([]);
  const load = () => api.get("/shares").then((r) => setMine(r.data.filter((s) => s.active && (s.task_id ? s.task_id === item.task_id : s.path === item.path)))).catch(() => {});
  useEffect(() => { load(); }, []); // eslint-disable-line
  const create = async () => {
    setBusy(true);
    try {
      const r = await api.post("/shares", { kind: item.kind === "file" ? "file" : item.kind, name: item.name, path: item.path, task_id: item.kind === "document" ? item.task_id : undefined, hours });
      setLink(`${window.location.origin}/s/${r.data.code}`); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat tautan"); } finally { setBusy(false); }
  };
  const copy = (u) => { navigator.clipboard?.writeText(u); toast.success("Tautan disalin"); };
  const revoke = async (code) => { await api.delete(`/shares/${code}`); toast.success("Tautan dicabut"); load(); if (link?.endsWith(code)) setLink(null); };
  return createPortal(
    <div className="fixed inset-0 z-[95] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-3xl border border-[#E7ECF3] bg-white p-6 shadow-2xl fade-up" data-testid="share-modal">
        <button onClick={onClose} className="absolute right-4 top-4 text-slate-400" data-testid="share-close"><X size={18} /></button>
        <h3 className="flex items-center gap-2 text-lg font-bold text-slate-900"><Share2 size={18} className="text-[#2F6BFF]" /> Bagikan berkas</h3>
        <p className="mt-1 truncate text-xs text-slate-500">{item.name}</p>
        <p className="mt-4 text-xs font-semibold text-slate-600">Masa berlaku tautan</p>
        <div className="mt-2 flex flex-wrap gap-2">{HOURS.map(([h, l]) => <button key={h} onClick={() => setHours(h)} data-testid={`share-hours-${h}`} className={`rounded-full px-3.5 py-1.5 text-xs font-semibold ${hours === h ? "btn-grad" : "border border-[#E7ECF3] text-slate-600"}`}>{l}</button>)}</div>
        <button onClick={create} disabled={busy} className="btn-grad mt-4 flex w-full items-center justify-center gap-2 rounded-xl py-2.5 text-sm" data-testid="share-create">{busy ? <Loader2 size={15} className="animate-spin" /> : <Share2 size={15} />} Buat tautan publik</button>
        {link && (
          <div className="mt-3 flex items-center gap-2 rounded-xl bg-[#EEF3FF] p-3" data-testid="share-link-box">
            <span className="min-w-0 flex-1 truncate text-xs font-semibold text-[#2F6BFF]" data-testid="share-link">{link}</span>
            <button onClick={() => copy(link)} className="text-[#2F6BFF]" data-testid="share-copy"><Copy size={15} /></button>
            <a href={link} target="_blank" rel="noreferrer" className="text-[#2F6BFF]"><ExternalLink size={15} /></a>
          </div>
        )}
        {mine.length > 0 && (
          <div className="mt-4">
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Tautan aktif</p>
            <div className="mt-1 space-y-1">{mine.map((s) => (
              <div key={s.code} className="flex items-center gap-2 text-xs" data-testid={`share-row-${s.code}`}>
                <Clock size={12} className="text-slate-400" /><span className="flex-1 truncate text-slate-600">/s/{s.code} · sampai {new Date(s.expires_at).toLocaleString("id-ID", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })} · {s.views}x dilihat</span>
                <button onClick={() => copy(`${window.location.origin}/s/${s.code}`)} className="text-[#2F6BFF]"><Copy size={13} /></button>
                <button onClick={() => revoke(s.code)} className="text-[#EF4444]" data-testid={`share-revoke-${s.code}`} title="Cabut"><Ban size={13} /></button>
              </div>
            ))}</div>
          </div>
        )}
      </div>
    </div>, document.body
  );
}

export function PreviewDrawer({ item, onClose }) {
  const [doc, setDoc] = useState(null);
  const [share, setShare] = useState(false);
  useEffect(() => { if (item?.kind === "document") api.get(`/tasks/${item.task_id}`).then((r) => setDoc(r.data)).catch(() => setDoc({ final_output: "_Gagal memuat dokumen._" })); }, [item]);
  if (!item) return null;
  const btn = "flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-bold";
  return createPortal(
    <div className="fixed inset-0 z-[90] flex justify-end">
      <div className="absolute inset-0 bg-slate-900/30" onClick={onClose} />
      <div className="relative flex h-full w-full max-w-2xl flex-col bg-white shadow-2xl" data-testid="gallery-preview">
        <div className="flex items-start justify-between gap-3 border-b border-[#E7ECF3] p-5">
          <div className="min-w-0"><h3 className="truncate text-base font-bold text-slate-900" data-testid="preview-title">{item.name}</h3><p className="text-xs text-slate-400">{item.persona_name || "Asisten"} · {new Date(item.created_at).toLocaleDateString("id-ID", { day: "numeric", month: "long", year: "numeric" })}</p></div>
          <button onClick={onClose} className="text-slate-400" data-testid="preview-close"><X size={20} /></button>
        </div>
        <div className="flex flex-wrap gap-2 border-b border-[#E7ECF3] px-5 py-3">
          {item.kind === "document" ? (<>
            <a href={exportUrl(item.task_id, "docx")} download className={`${btn} bg-slate-100 text-slate-700`} data-testid="preview-dl-docx"><Download size={13} /> Word</a>
            <a href={exportUrl(item.task_id, "pdf")} download className={`${btn} bg-slate-100 text-slate-700`} data-testid="preview-dl-pdf"><Download size={13} /> PDF</a>
            <a href={`${window.location.origin}/workspace/${item.task_id}`} target="_blank" rel="noreferrer" className={`${btn} bg-[#EEF3FF] text-[#2F6BFF]`}><ExternalLink size={13} /> Ruang Kerja</a>
          </>) : item.kind === "drive" ? (
            <a href={item.link} target="_blank" rel="noreferrer" className={`${btn} bg-[#EEF3FF] text-[#2F6BFF]`} data-testid="preview-open-drive"><HardDrive size={13} /> Buka di Google Drive <ExternalLink size={12} /></a>
          ) : <a href={downloadUrl(item.path)} download={item.name} className={`${btn} bg-slate-100 text-slate-700`} data-testid="preview-dl-file"><Download size={13} /> Unduh</a>}
          {item.kind !== "drive" && <button onClick={() => setShare(true)} className={`${btn} bg-[#0B132B] text-white`} data-testid="preview-share"><Share2 size={13} /> Bagikan</button>}
        </div>
        <div className="flex-1 overflow-y-auto p-5" data-testid="preview-body">
          {item.kind === "drive" && (
            <div className="aivora-card p-5 text-sm text-slate-600" data-testid="preview-drive-info">
              <p className="flex items-center gap-2 font-semibold text-slate-900"><HardDrive size={16} className="text-[#2F6BFF]" /> Tersimpan di Google Drive Anda</p>
              <p className="mt-2">Berkas ini disimpan langsung ke Drive, bukan di penyimpanan Oryntix — jadi tidak memakai kuota 50 MB. Buka, bagikan, atau unduh lewat Google Drive.</p>
              {item.mime && <p className="mt-2 text-xs text-slate-400">{item.mime}</p>}
            </div>
          )}
          {item.kind === "image" && <img src={fileUrl(item.path)} alt={item.name} className="mx-auto max-h-full rounded-2xl" />}
          {item.kind === "video" && <video src={fileUrl(item.path)} controls className="w-full rounded-2xl" />}
          {item.kind === "document" && (doc ? <div className="aivora-card p-5"><Markdown content={doc.final_output || "_Dokumen kosong._"} /></div> : <p className="flex items-center gap-2 text-sm text-slate-400"><Loader2 size={15} className="animate-spin" /> Memuat dokumen…</p>)}
        </div>
      </div>
      {share && <ShareModal item={item} onClose={() => setShare(false)} />}
    </div>, document.body
  );
}
