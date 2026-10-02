import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Download, Copy, CheckCircle2, Loader2, Clock, XCircle, MessageSquare, Phone, Video, History, FileText, FileSpreadsheet, FileType, Bot, PencilLine } from "lucide-react";
import { toast } from "sonner";
import { api, API_BASE, getToken } from "../lib/api";
import { Markdown } from "../components/Markdown";
import { MediaList } from "../components/MessageExtras";
import { Mark } from "../components/Logo";

const roleColor = { Research: "#00D1FF", Planning: "#F59E0B", Writing: "#7C3AED", Analyst: "#06B6D4", Coding: "#10B981", Reviewer: "#EF4444" };
const FORMATS = [
  { fmt: "docx", label: "Word", Icon: FileText },
  { fmt: "pdf", label: "PDF", Icon: FileType },
  { fmt: "xlsx", label: "Excel", Icon: FileSpreadsheet, needsTables: true },
  { fmt: "md", label: "Markdown", Icon: Download },
];

// On-demand conversion: nothing is pre-generated, files are built when the button is clicked.
function ExportBar({ task }) {
  const [busy, setBusy] = useState("");
  const download = async (fmt) => {
    setBusy(fmt);
    try {
      const res = await fetch(`${API_BASE}/tasks/${task.id}/export/${fmt}`, { headers: { Authorization: `Bearer ${getToken()}` } });
      if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || "Gagal mengonversi"); }
      const blob = await res.blob(); const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `${(task.goal || "hasil").slice(0, 40).replace(/[^\w\- ]+/g, "")}.${fmt}`; a.click();
      URL.revokeObjectURL(url); toast.success(`File ${fmt.toUpperCase()} siap`);
    } catch (e) { toast.error(e.message); } finally { setBusy(""); }
  };
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="export-bar">
      <span className="text-xs text-slate-500">Konversi ke:</span>
      {FORMATS.map(({ fmt, label, Icon, needsTables }) => {
        const off = needsTables && !task.has_tables;
        return (
          <button key={fmt} onClick={() => download(fmt)} disabled={off || !!busy} title={off ? "Hasil tidak memiliki tabel" : `Unduh sebagai ${label}`} data-testid={`export-${fmt}`}
            className="flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40">
            {busy === fmt ? <Loader2 size={13} className="animate-spin" /> : <Icon size={13} />} {label}
          </button>
        );
      })}
    </div>
  );
}

function DiscussBar({ task, nav }) {
  const [busy, setBusy] = useState("");
  const go = async (mode) => {
    setBusy(mode);
    try {
      const r = await api.post(`/tasks/${task.id}/discuss`, { mode });
      nav(`/chat/${r.data.conversation_id}`, { state: r.data.open_call ? { openMeeting: true } : {} });
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuka diskusi"); } finally { setBusy(""); }
  };
  const B = ({ mode, Icon, label, cls }) => (
    <button onClick={() => go(mode)} disabled={!!busy} data-testid={`discuss-${mode}`} className={`flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-bold text-white transition hover:brightness-105 disabled:opacity-60 ${cls}`}>
      {busy === mode ? <Loader2 size={14} className="animate-spin" /> : <Icon size={14} />} {label}
    </button>
  );
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="discuss-bar">
      <span className="flex items-center gap-1 text-xs text-slate-500"><Bot size={13} /> {task.persona_name ? `Asisten: ${task.persona_name}` : "Hubungi asisten"}</span>
      <B mode="chat" Icon={MessageSquare} label="Chat" cls="bg-[#0B132B]" />
      <B mode="call" Icon={Phone} label="Telepon" cls="bg-[#10B981]" />
      <B mode="meeting" Icon={Video} label="Buat Panggilan" cls="bg-[#2F6BFF]" />
    </div>
  );
}

function RevisePanel({ task, onDone }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!text.trim()) return;
    setBusy(true);
    try { const r = await api.post(`/tasks/${task.id}/revise`, { instruction: text }); toast.success(`Revisi v${r.data.version} tersimpan`); setText(""); setOpen(false); onDone(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal merevisi"); } finally { setBusy(false); }
  };
  if (!open) return <button onClick={() => setOpen(true)} className="flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600" data-testid="revise-open"><PencilLine size={13} /> Revisi cepat</button>;
  return (
    <div className="mt-3 w-full rounded-xl border border-[#2F6BFF]/30 bg-[#EEF3FF] p-3" data-testid="revise-panel">
      <textarea className="input-dark min-h-[70px] text-sm" placeholder="Apa yang perlu diubah? (mis. tambahkan tabel anggaran, persingkat bagian 2)" value={text} onChange={(e) => setText(e.target.value)} data-testid="revise-input" />
      <div className="mt-2 flex gap-2"><button onClick={submit} disabled={busy} className="btn-grad rounded-lg px-4 py-1.5 text-xs" data-testid="revise-submit">{busy ? "Merevisi..." : "Terapkan revisi"}</button><button onClick={() => setOpen(false)} className="rounded-lg px-3 py-1.5 text-xs text-slate-500">Batal</button></div>
    </div>
  );
}

export default function TaskDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [task, setTask] = useState(null);
  const [viewVer, setViewVer] = useState(null); // {version, content}

  const load = () => api.get(`/tasks/${id}`).then((r) => { setTask(r.data); setViewVer(null); }).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);
  useEffect(() => {
    if (!task) return;
    if (["queued", "running"].includes(task.status)) { const iv = setInterval(load, 3000); return () => clearInterval(iv); }
    /* eslint-disable-next-line */
  }, [task]);

  if (!task) return <div className="p-10 text-slate-500">Memuat...</div>;

  const showVersion = async (v) => {
    if (v === task.version) { setViewVer(null); return; }
    try { const r = await api.get(`/tasks/${id}/versions/${v}`); setViewVer(r.data); } catch (e) { toast.error("Versi tidak ditemukan"); }
  };
  const stepIcon = (s) => {
    if (s.status === "completed") return <CheckCircle2 size={16} className="text-[#10B981]" />;
    if (s.status === "running") return <Loader2 size={16} className="animate-spin text-[#8B5CF6]" />;
    return <Clock size={16} className="text-[#F59E0B]" />;
  };
  const content = viewVer ? viewVer.content : task.final_output;
  const allVersions = [...(task.versions || []).map((v) => v.version), task.version];

  return (
    <div className="mx-auto max-w-4xl p-5 sm:p-8 lg:p-10 fade-up" data-testid="task-detail-page">
      <button onClick={() => nav("/workspace")} className="mb-4 flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"><ArrowLeft size={16} /> Ruang Kerja</button>

      <div className="aivora-card p-6">
        <div className="flex items-start gap-3">
          <Mark size={40} />
          <div className="flex-1">
            <h1 className="text-xl font-bold text-slate-900" data-testid="task-goal">{task.goal}</h1>
            {task.summary && <p className="mt-1 text-sm text-slate-500">{task.summary}</p>}
          </div>
          <StatusBadge status={task.status} />
        </div>
        <div className="mt-4 border-t border-[#E7ECF3] pt-4"><DiscussBar task={task} nav={nav} /></div>
      </div>

      {(task.steps || []).length > 0 || ["queued", "running"].includes(task.status) ? (<>
        <h2 className="mt-8 mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">Agent & Subtugas</h2>
        <div className="space-y-3">
          {(task.steps || []).length === 0 && <div className="aivora-card flex items-center gap-3 p-5 text-sm text-slate-500"><Loader2 size={16} className="animate-spin text-[#8B5CF6]" /> Oryntix sedang menyusun rencana...</div>}
          {(task.steps || []).map((s, i) => (
            <div key={s.id || i} className="aivora-card p-5" data-testid={`step-${i}`}>
              <div className="flex items-center gap-3">
                {stepIcon(s)}
                <span className="rounded-md px-2 py-0.5 text-xs font-semibold" style={{ background: `${roleColor[s.role] || "#94A3B8"}22`, color: roleColor[s.role] || "#94A3B8" }}>{s.role}</span>
                <span className="text-sm font-semibold text-slate-900">{s.title}</span>
              </div>
              {s.output && <div className="mt-3 border-t border-slate-200 pt-3 text-sm text-slate-600"><Markdown content={s.output} /></div>}
            </div>
          ))}
        </div>
      </>) : null}

      {task.status === "completed" && (
        <div className="mt-8">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-slate-500">Hasil {viewVer ? <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-bold normal-case text-amber-700">Melihat v{viewVer.version} (lama)</span> : <span className="rounded-full bg-[#EEF3FF] px-2 py-0.5 text-[11px] font-bold normal-case text-[#2F6BFF]" data-testid="task-version">v{task.version}</span>}</h2>
            <div className="flex flex-wrap items-center gap-2">
              {allVersions.length > 1 && (
                <label className="flex items-center gap-1 rounded-lg border border-slate-200 px-2 py-1.5 text-xs text-slate-600"><History size={13} />
                  <select value={viewVer ? viewVer.version : task.version} onChange={(e) => showVersion(parseInt(e.target.value, 10))} className="bg-transparent outline-none" data-testid="version-select">
                    {allVersions.map((v) => <option key={v} value={v}>v{v}{v === task.version ? " (terbaru)" : ""}</option>)}
                  </select>
                </label>
              )}
              <button onClick={() => { navigator.clipboard.writeText(content || ""); toast.success("Disalin"); }} className="flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600" data-testid="copy-output"><Copy size={13} /> Salin</button>
              <RevisePanel task={task} onDone={load} />
            </div>
          </div>
          {task.revision_note && !viewVer && <p className="mb-3 text-xs text-slate-500">Revisi terakhir: {task.revision_note.replace(/\*\*/g, "")}</p>}
          <div className="mb-3"><ExportBar task={task} /></div>
          {(task.video_path || task.video_url) && (
            <video src={task.video_path ? `${API_BASE}/files/${task.video_path}?auth=${getToken()}` : task.video_url} controls className="mb-3 w-full rounded-2xl border border-[#E7ECF3]" data-testid="task-video" />
          )}
          {(task.media || []).length > 0 && <div className="mb-3 aivora-card p-4" data-testid="task-media"><MediaList media={task.media} /></div>}
          <div className="aivora-card p-6" data-testid="final-output"><Markdown content={content} /></div>
          <p className="mt-3 text-right text-xs text-slate-500">Total: {task.credits_used} kredit</p>
        </div>
      )}
      {task.status === "failed" && (
        <div className="mt-8 flex items-center gap-2 rounded-xl border border-[#EF4444]/40 bg-[#EF4444]/10 p-4 text-sm text-[#EF4444]"><XCircle size={16} /> Tugas gagal. {task.error}</div>
      )}
    </div>
  );
}

function StatusBadge({ status }) {
  const map = { completed: ["#10B981", "Selesai"], running: ["#8B5CF6", "Berjalan"], queued: ["#F59E0B", "Antre"], failed: ["#EF4444", "Gagal"], cancelled: ["#94A3B8", "Batal"], scheduled: ["#2F6BFF", "Terjadwal"] };
  const [c, l] = map[status] || ["#94A3B8", status];
  return <span className="shrink-0 rounded-full px-3 py-1 text-xs font-semibold" style={{ background: `${c}22`, color: c }} data-testid="task-status">{l}</span>;
}
