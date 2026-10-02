import React, { useState } from "react";
import { AlertTriangle, Loader2, Archive, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Markdown } from "./Markdown";

// Checks required notulen fields before a meeting is closed; resolves true = proceed to end, false = keep discussing.
export function useNotulenGate(cid) {
  const [state, setState] = useState(null);
  const gate = () => new Promise((resolve) => {
    api.post(`/conversations/${cid}/notulen-check`).then((r) => {
      if (!r.data.missing?.length) resolve(true); else setState({ ...r.data, resolve });
    }).catch(() => resolve(true));
  });
  const done = (v) => { state?.resolve(v); setState(null); };
  const dialog = state ? (
    <div className="fixed inset-0 z-[130] flex items-center justify-center bg-black/60 p-4" data-testid="notulen-check-dialog">
      <div className="w-full max-w-md rounded-2xl bg-white p-5 text-slate-800 shadow-2xl">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-600"><AlertTriangle size={20} /></span>
          <div><p className="text-base font-bold">Notulen belum lengkap</p><p className="mt-0.5 text-sm text-slate-500">Asisten belum menemukan data untuk kolom wajib berikut:</p></div>
        </div>
        <ul className="mt-3 space-y-1.5">
          {state.missing.map((f) => <li key={f} className="rounded-lg bg-amber-50 px-3 py-2 text-sm" data-testid="notulen-missing-field"><span className="font-semibold">{f}</span>{state.notes?.[f] && <span className="text-slate-500"> — {state.notes[f]}</span>}</li>)}
        </ul>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={() => done(true)} data-testid="notulen-end" className="rounded-xl px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-100">Tetap akhiri</button>
          <button onClick={() => done(false)} data-testid="notulen-continue" className="btn-primary py-2">Lanjutkan pembahasan</button>
        </div>
      </div>
    </div>
  ) : null;
  return { gate, dialog };
}

// Shown when the thread is long: summarize + archive, or snooze.
export function SummaryPrompt({ cid, onDone, onLater, dark = false }) {
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try { const r = await api.post(`/conversations/${cid}/compact`); toast.success(`${r.data.archived} pesan lama diarsipkan`); await onDone?.(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal merangkum"); } finally { setBusy(false); }
  };
  const later = async () => { try { await api.post(`/conversations/${cid}/summary-later`); } catch (e) {} onLater?.(); };
  return (
    <div data-testid="summary-prompt" className={`mx-auto flex max-w-2xl flex-wrap items-center gap-3 rounded-2xl border px-4 py-3 text-sm ${dark ? "border-amber-300/30 bg-amber-300/10 text-amber-50" : "border-amber-300 bg-amber-50 text-amber-900"}`}>
      <Archive size={16} className="shrink-0" />
      <span className="flex-1">Pembicaraan sudah cukup panjang. Mau saya rangkum dulu dan arsipkan pesan lama agar asisten tetap fokus?</span>
      <button onClick={run} disabled={busy} data-testid="summary-run" className="flex items-center gap-1 rounded-lg bg-[#2F6BFF] px-3 py-1.5 text-xs font-bold text-white disabled:opacity-60">{busy && <Loader2 size={12} className="animate-spin" />} Rangkum & arsipkan</button>
      <button onClick={later} disabled={busy} data-testid="summary-later" className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${dark ? "bg-white/10" : "bg-white"}`}>Nanti</button>
    </div>
  );
}

// Read-only archive viewer (raw messages that were summarized away).
export function ArchiveModal({ cid, onClose }) {
  const [items, setItems] = useState(null);
  React.useEffect(() => { api.get(`/conversations/${cid}/messages?archived=1&limit=200`).then((r) => setItems(r.data.messages)).catch(() => setItems([])); }, [cid]);
  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4" data-testid="archive-modal">
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center gap-2 border-b border-[#E7ECF3] px-5 py-3"><Archive size={16} className="text-slate-500" /><p className="font-bold text-slate-900">Arsip percakapan</p><span className="text-xs text-slate-400">{items?.length ?? "…"} pesan</span><button onClick={onClose} data-testid="archive-close" className="ml-auto rounded-lg p-1.5 text-slate-500 hover:bg-slate-100"><X size={16} /></button></div>
        <div className="flex-1 space-y-3 overflow-y-auto p-5 text-sm">
          {items === null ? <Loader2 className="mx-auto animate-spin text-slate-400" /> : items.length === 0 ? <p className="text-center text-slate-500">Arsip kosong.</p> : items.map((m) => (
            <div key={m.id} className={`rounded-xl px-3 py-2 ${m.role === "user" ? "bg-[#EEF3FF]" : "bg-slate-50"}`}><p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{m.role === "user" ? (m.sender_name || "Anda") : (m.persona_name || "Asisten")}</p><Markdown content={m.content} /></div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function LoadMore({ onClick, loading, testid = "load-more" }) {
  return (
    <div className="flex justify-center py-3">
      <button onClick={onClick} disabled={loading} data-testid={testid} className="flex items-center gap-2 rounded-full border border-[#E7ECF3] bg-white px-4 py-1.5 text-xs font-semibold text-[#2F6BFF] hover:bg-[#EEF3FF] disabled:opacity-60">{loading && <Loader2 size={12} className="animate-spin" />} Muat lebih banyak</button>
    </div>
  );
}
