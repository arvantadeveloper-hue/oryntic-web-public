import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Share2, Link2, Unplug, Loader2, CheckCircle2, ExternalLink, Image as ImageIcon, Video, Type, XCircle, Plus, CalendarClock, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { fileUrl, openPublish } from "../components/MessageExtras";

const ICON = { linkedin: "in", meta: "f", youtube: "▶" };
const TABS = [["image", "Gambar", ImageIcon], ["video", "Video", Video], ["text", "Teks", Type]];

const SCHED_STATUS = { scheduled: ["Terjadwal", "bg-[#EEF3FF] text-[#2F6BFF]"], running: ["Sedang diposting", "bg-amber-50 text-amber-700"], sent: ["Terkirim", "bg-emerald-50 text-emerald-600"], partial: ["Sebagian terkirim", "bg-amber-50 text-amber-700"], failed: ["Gagal", "bg-rose-50 text-rose-600"], cancelled: ["Dibatalkan", "bg-slate-100 text-slate-500"] };

function ScheduledList({ items, onCancel }) {
  const pending = items.filter((j) => j.status === "scheduled");
  const done = items.filter((j) => j.status !== "scheduled").slice(-6).reverse();
  return (
    <div className="mt-8 aivora-card p-5" data-testid="social-scheduled">
      <div className="flex items-center gap-2"><CalendarClock size={16} className="text-[#2F6BFF]" /><p className="text-sm font-bold text-slate-900">Posting terjadwal</p><span className="rounded-full bg-slate-100 px-2 text-[10px] font-bold text-slate-500" data-testid="social-scheduled-count">{pending.length}</span></div>
      <p className="mt-1 text-xs text-slate-500">Minta lewat chat: "posting gambar ini ke LinkedIn besok jam 9" — asisten akan mengunggahnya tepat waktu dan mengabari Anda di chat.</p>
      {pending.length === 0 && done.length === 0 && <p className="mt-3 text-xs text-slate-400" data-testid="social-scheduled-empty">Belum ada jadwal.</p>}
      <div className="mt-3 space-y-2">
        {[...pending, ...done].map((j) => {
          const [label, cls] = SCHED_STATUS[j.status] || [j.status, "bg-slate-100 text-slate-500"];
          return (
            <div key={j.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-[#EEF1F6] px-3 py-2 text-xs" data-testid={`social-sched-${j.id}`}>
              <span className={`rounded-full px-2 py-0.5 font-bold ${cls}`}>{label}</span>
              <span className="font-semibold text-slate-800">{(j.providers || []).map((p) => p.toUpperCase()).join(", ")}</span>
              <span className="text-slate-500">{j.kind === "text" ? "teks" : j.kind} · {j.scheduled_label || new Date(j.scheduled_at).toLocaleString("id-ID")}</span>
              <span className="min-w-0 flex-1 truncate text-slate-600">{j.text}</span>
              {j.error && <span className="text-rose-600">{j.error}</span>}
              {j.status === "scheduled" && <button onClick={() => onCancel(j.id)} className="flex items-center gap-1 font-semibold text-rose-600 hover:underline" data-testid={`social-sched-cancel-${j.id}`}><Trash2 size={11} /> Batalkan</button>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function SocialMedia() {
  const [accounts, setAccounts] = useState(null);
  const [posts, setPosts] = useState([]);
  const [sched, setSched] = useState([]);
  const [tab, setTab] = useState("image");
  const [params, setParams] = useSearchParams();
  const load = () => {
    api.get("/social/accounts").then((r) => setAccounts(r.data.items)).catch(() => setAccounts([]));
    api.get("/social/posts").then((r) => setPosts(r.data.items)).catch(() => {});
    api.get("/social/scheduled").then((r) => setSched(r.data.items)).catch(() => {});
  };
  const cancelSched = async (id) => {
    if (!window.confirm("Batalkan posting terjadwal ini?")) return;
    try { await api.delete(`/social/scheduled/${id}`); toast.success("Jadwal dibatalkan"); load(); } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membatalkan"); }
  };
  useEffect(() => { load(); const c = params.get("connected"); if (c) { toast.success(`${c} terhubung`); setParams({}); } /* eslint-disable-next-line */ }, []);
  const connect = async (p) => {
    try { const r = await api.get(`/social/${p}/start`, { params: { redirect_uri: `${window.location.origin.replace(/\/$/, "")}/api/social/callback`, app_url: window.location.origin } }); window.location.href = r.data.url; }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal memulai koneksi"); }
  };
  const disconnect = async (p) => { if (!window.confirm("Putuskan akun ini?")) return; await api.delete(`/social/${p}`); load(); };
  const shown = posts.filter((p) => p.kind === tab);
  return (
    <div className="mx-auto max-w-6xl p-5 sm:p-8 lg:p-10 fade-up" data-testid="social-page">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-3xl font-extrabold text-slate-900">Social Media</h1><p className="text-sm text-slate-500">Hubungkan akun Anda sendiri — Oryntix hanya memfasilitasi. Semua konten yang dipublikasikan lewat asisten tercatat di sini.</p></div>
        <button onClick={() => openPublish(null, "")} className="btn-grad flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-bold" data-testid="social-new-text-post"><Plus size={14} /> Posting teks</button>
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-3" data-testid="social-accounts">
        {(accounts || []).map((a) => (
          <div key={a.id} className="aivora-card p-4" data-testid={`social-acc-${a.id}`}>
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#0B132B] text-sm font-black text-white">{ICON[a.id]}</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-bold text-slate-900">{a.label}</p>
                {a.connected ? <p className="flex items-center gap-1 text-xs text-emerald-700" data-testid={`social-status-${a.id}`}><CheckCircle2 size={12} /> {a.account_name || "Terhubung"}{a.pages?.length ? ` · ${a.pages.length} halaman` : ""}</p>
                  : <p className="text-xs text-slate-500" data-testid={`social-status-${a.id}`}>{a.configured ? "Belum terhubung" : "Belum dikonfigurasi platform"}</p>}
                <p className="mt-1 text-[11px] text-slate-400">Mendukung: {a.kinds.join(", ")}</p>
              </div>
            </div>
            <div className="mt-3">
              {a.connected ? <button onClick={() => disconnect(a.id)} className="flex items-center gap-1 rounded-lg border border-rose-200 px-3 py-1.5 text-xs font-bold text-rose-600" data-testid={`social-disconnect-${a.id}`}><Unplug size={12} /> Putuskan</button>
                : <button onClick={() => connect(a.id)} disabled={!a.configured} className="btn-grad flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-bold disabled:opacity-40" data-testid={`social-connect-${a.id}`}><Link2 size={12} /> Hubungkan</button>}
            </div>
          </div>
        ))}
        {accounts === null && <p className="flex items-center gap-2 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p>}
      </div>
      <ScheduledList items={sched} onCancel={cancelSched} />
      <div className="mt-8 flex gap-2 border-b border-[#E7ECF3]" data-testid="social-tabs">
        {TABS.map(([k, l, I]) => <button key={k} onClick={() => setTab(k)} data-testid={`social-tab-${k}`} className={`flex items-center gap-1.5 border-b-2 px-4 py-2.5 text-sm font-semibold transition ${tab === k ? "border-[#2F6BFF] text-[#2F6BFF]" : "border-transparent text-slate-500 hover:text-slate-800"}`}><I size={14} /> {l} <span className="rounded-full bg-slate-100 px-1.5 text-[10px] text-slate-500">{posts.filter((p) => p.kind === k).length}</span></button>)}
      </div>
      {shown.length === 0 ? <p className="py-12 text-center text-sm text-slate-400" data-testid="social-empty">Belum ada {TABS.find((t) => t[0] === tab)[1].toLowerCase()} yang dipublikasikan. Klik "Publikasikan" pada hasil asisten di chat atau Ruang Kerja, atau minta lewat chat: "posting gambar ini ke LinkedIn".</p> : (
        <div className={`mt-4 grid gap-4 ${tab === "text" ? "" : "sm:grid-cols-2 lg:grid-cols-3"}`} data-testid="social-posts">
          {shown.map((p) => (
            <div key={p.id} className="aivora-card overflow-hidden" data-testid={`social-post-${p.id}`}>
              {p.kind === "image" && p.media_path && <img src={fileUrl(p.media_path)} alt="" className="h-44 w-full object-cover" />}
              {p.kind === "video" && p.media_path && <video src={fileUrl(p.media_path)} className="h-44 w-full bg-black" controls preload="metadata" />}
              <div className="p-4">
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="font-bold uppercase text-slate-500">{p.provider}{p.account_name ? ` · ${p.account_name}` : ""}</span>
                  <span className={`flex items-center gap-1 font-semibold ${p.status === "sent" ? "text-emerald-600" : "text-rose-600"}`}>{p.status === "sent" ? <CheckCircle2 size={12} /> : <XCircle size={12} />}{p.status === "sent" ? "Terkirim" : "Gagal"}</span>
                </div>
                <p className="mt-2 line-clamp-4 text-sm text-slate-800">{p.text || p.title}</p>
                {p.error && <p className="mt-1 text-xs text-rose-600">{p.error}</p>}
                <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-slate-400">
                  <span>{new Date(p.created_at).toLocaleString("id-ID")}</span>
                  {p.post_url && <a href={p.post_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 font-semibold text-[#2F6BFF]">Lihat post <ExternalLink size={10} /></a>}
                  {p.instagram_url && <a href={p.instagram_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 font-semibold text-[#2F6BFF]">Instagram <ExternalLink size={10} /></a>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      <p className="mt-6 flex items-center gap-1 text-[11px] text-slate-400"><Share2 size={11} /> Perintah suara/chat: "posting gambar terakhir ke LinkedIn dengan caption …", "unggah video ini ke YouTube".</p>
    </div>
  );
}
