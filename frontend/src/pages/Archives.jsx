import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Archive, Search, Loader2, RotateCcw, Bell, ChevronDown, ChevronUp, Users, User, CheckCircle2, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Sentinel } from "../components/Gallery";
import { Markdown } from "../components/Markdown";

const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" }) : "-");
export const periodText = (a) => (fmtDate(a.period_start) === fmtDate(a.period_end) ? fmtDate(a.period_start) : `${fmtDate(a.period_start)} – ${fmtDate(a.period_end)}`);

export function RemindModal({ archive, onClose }) {
  const [when, setWhen] = useState(() => { const d = new Date(Date.now() + 86400000); d.setMinutes(0, 0, 0); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16); });
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try { await api.post(`/archives/${archive.id}/remind`, { start_at: new Date(when).toISOString() }); toast.success("Pengingat dibuat dari arsip"); onClose(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat pengingat"); } finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-[94] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} />
      <div className="relative w-full max-w-sm rounded-3xl border border-[#E7ECF3] bg-white p-6 shadow-2xl fade-up" data-testid="archive-remind-modal">
        <button onClick={onClose} className="absolute right-4 top-4 text-slate-400"><X size={18} /></button>
        <h3 className="text-lg font-bold text-slate-900">Jadikan pengingat</h3>
        <p className="mt-1 text-sm text-slate-500">Asisten akan menelepon Anda untuk melanjutkan «{archive.title}» pada waktu berikut.</p>
        <input type="datetime-local" className="input-dark mt-4" value={when} onChange={(e) => setWhen(e.target.value)} data-testid="archive-remind-when" />
        <button onClick={save} disabled={busy} className="btn-grad mt-4 w-full rounded-xl py-2.5 text-sm" data-testid="archive-remind-save">{busy ? "..." : "Buat Pengingat"}</button>
      </div>
    </div>
  );
}

export function ArchiveCard({ a, onRestored, compact = false }) {
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [remind, setRemind] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const toggle = async () => {
    if (!open && !detail) { try { setDetail((await api.get(`/archives/${a.id}`)).data); } catch (e) {} }
    setOpen(!open);
  };
  const restore = async () => {
    setBusy(true);
    try { const r = await api.post(`/archives/${a.id}/restore`); toast.success(`${r.data.restored} pesan dipulihkan`); setConfirm(false); onRestored && onRestored(a, r.data); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal memulihkan"); } finally { setBusy(false); }
  };
  return (
    <div className="aivora-card overflow-hidden" data-testid={`archive-card-${a.id}`}>
      <div className="flex items-start gap-3 p-4">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#0B132B] text-white">{a.conversation_type === "private" ? <User size={17} /> : <Users size={17} />}</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-bold text-slate-900" data-testid="archive-title">{a.title}</p>
            {a.restored && <span className="flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-700" data-testid="archive-restored-badge"><CheckCircle2 size={11} /> Dipulihkan</span>}
            {a.reason === "auto" && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">otomatis</span>}
          </div>
          <p className="text-[11px] text-slate-400">{periodText(a)} · {a.message_count} pesan · {(a.persona_names || []).join(", ")}</p>
          {!compact && <p className="mt-1.5 line-clamp-3 text-xs text-slate-600">{(a.summary || "").replace(/[#*_`]/g, "")}</p>}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-[#E7ECF3] px-4 py-2.5">
        <button onClick={toggle} className="flex items-center gap-1 text-xs font-semibold text-slate-600" data-testid="archive-toggle">{open ? <ChevronUp size={13} /> : <ChevronDown size={13} />} {open ? "Tutup" : "Lihat isi"}</button>
        <span className="flex-1" />
        {!a.restored && (confirm ? (
          <span className="flex items-center gap-2 text-xs" data-testid="archive-confirm">
            <span className="text-slate-600">Pulihkan ke chat?</span>
            <button onClick={restore} disabled={busy} className="rounded-lg bg-[#10B981] px-2.5 py-1 font-bold text-white" data-testid="archive-confirm-yes">{busy ? "..." : "Ya"}</button>
            <button onClick={() => setConfirm(false)} className="rounded-lg border border-[#E7ECF3] px-2.5 py-1 font-semibold text-slate-600" data-testid="archive-confirm-no">Batal</button>
          </span>
        ) : <button onClick={() => setConfirm(true)} className="flex items-center gap-1 rounded-lg bg-[#EEF3FF] px-2.5 py-1.5 text-xs font-bold text-[#2F6BFF]" data-testid="archive-restore"><RotateCcw size={13} /> Pulihkan</button>)}
        <button onClick={() => setRemind(true)} className="flex items-center gap-1 rounded-lg border border-[#E7ECF3] px-2.5 py-1.5 text-xs font-semibold text-slate-700" data-testid="archive-remind"><Bell size={13} /> Jadikan pengingat</button>
        <button onClick={() => nav(`/chat/${a.conversation_id}`)} className="rounded-lg border border-[#E7ECF3] px-2.5 py-1.5 text-xs font-semibold text-slate-700" data-testid="archive-open-chat">Buka chat</button>
      </div>
      {open && (
        <div className="max-h-80 space-y-2 overflow-y-auto border-t border-[#E7ECF3] bg-[#F8FAFC] p-4" data-testid="archive-messages">
          <div className="rounded-xl bg-white p-3 text-xs text-slate-700"><Markdown content={a.summary || ""} /></div>
          {!detail && <p className="flex items-center gap-2 text-xs text-slate-400"><Loader2 size={13} className="animate-spin" /> Memuat pesan…</p>}
          {(detail?.messages || []).map((m) => (
            <div key={m.id} className={`text-xs ${m.role === "user" ? "text-right" : ""}`}><span className="font-semibold text-slate-500">{m.role === "user" ? m.sender_name || "Anda" : m.persona_name}: </span><span className="text-slate-700">{(m.content || "").slice(0, 400)}</span></div>
          ))}
        </div>
      )}
      {remind && <RemindModal archive={a} onClose={() => setRemind(false)} />}
    </div>
  );
}

export default function Archives() {
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [hasMore, setHasMore] = useState(false);
  const cursor = useRef(null);
  const timer = useRef(null);

  const load = useCallback(async (reset, query) => {
    setLoading(true);
    try {
      const r = await api.get(`/archives?limit=20${query ? `&q=${encodeURIComponent(query)}` : ""}${!reset && cursor.current ? `&before=${encodeURIComponent(cursor.current)}` : ""}`);
      setItems((p) => (reset ? r.data.items : [...p, ...r.data.items])); setHasMore(!!r.data.has_more); cursor.current = r.data.next_before;
    } catch (e) {} finally { setLoading(false); }
  }, []);
  useEffect(() => { load(true, ""); }, [load]);
  const onSearch = (v) => { setQ(v); clearTimeout(timer.current); timer.current = setTimeout(() => { cursor.current = null; load(true, v); }, 350); };
  const onRestored = (a) => setItems((p) => p.map((x) => (x.id === a.id ? { ...x, restored: true } : x)));

  return (
    <div className="mx-auto max-w-4xl p-5 sm:p-8" data-testid="archives-page">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-slate-900 sm:text-3xl"><Archive size={26} className="text-[#2F6BFF]" /> Arsip Percakapan</h1>
      <p className="mt-1 text-sm text-slate-500">Percakapan yang tidak aktif dirangkum dan diarsipkan otomatis (atur jedanya di Settings). Cari, lihat isinya, pulihkan ke chat, atau jadikan pengingat.</p>
      <div className="relative mt-5"><Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
        <input className="input-dark pl-10" placeholder="Cari judul, isi pesan, atau nama asisten…" value={q} onChange={(e) => onSearch(e.target.value)} data-testid="archive-search" /></div>
      <div className="mt-5 space-y-3">
        {items.map((a) => <ArchiveCard key={a.id} a={a} onRestored={onRestored} />)}
        {loading && <p className="flex items-center justify-center gap-2 py-6 text-sm text-slate-400" data-testid="archive-loading"><Loader2 size={16} className="animate-spin" /> Memuat arsip…</p>}
        {!loading && items.length === 0 && <p className="py-12 text-center text-sm text-slate-400" data-testid="archive-empty">Belum ada arsip{q ? " yang cocok" : ""}.</p>}
        {!loading && hasMore && <Sentinel onVisible={() => load(false, q)} />}
      </div>
    </div>
  );
}
