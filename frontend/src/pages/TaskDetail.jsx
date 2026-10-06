import React, { useEffect, useState } from "react";
import { onUserEvent, isWsConnected } from "../lib/userEvents";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Download, Copy, CheckCircle2, Loader2, Clock, XCircle, MessageSquare, Phone, X, History, GitCompareArrows, FileText, FileSpreadsheet, FileType, Bot, PencilLine } from "lucide-react";
import { toast } from "sonner";
import { api, API_BASE, getToken } from "../lib/api";
import { Markdown } from "../components/Markdown";
import { MediaList } from "../components/MessageExtras";
import { Mark } from "../components/Logo";
import { VersionDiff } from "../components/VersionDiff";

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

function GroupModal({ target, mode, onClose, onCreate }) {
  const [title, setTitle] = useState(target.default_title || "");
  const [ids, setIds] = useState(target.personas.map((p) => p.id));
  const [busy, setBusy] = useState(false);
  const toggle = (pid) => setIds((x) => (x.includes(pid) ? x.filter((i) => i !== pid) : [...x, pid]));
  return (
    <div className="fixed inset-0 z-[92] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-3xl border border-[#E7ECF3] bg-white p-6 shadow-2xl fade-up" data-testid="create-group-modal">
        <button onClick={onClose} className="absolute right-4 top-4 text-slate-400"><X size={18} /></button>
        <h3 className="text-lg font-bold text-slate-900">Buat Grup Percakapan</h3>
        <p className="mt-1 text-sm text-slate-500">Belum ada grup untuk semua asisten yang terlibat di tugas ini. Buat grup agar {mode === "call" ? "panggilan" : "diskusi"} melibatkan mereka sekaligus.</p>
        <input className="input-dark mt-4 py-2.5" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Nama grup" data-testid="group-modal-title" />
        <div className="mt-3 max-h-56 space-y-2 overflow-y-auto">
          {target.personas.map((p) => { const on = ids.includes(p.id); return (
            <button key={p.id} onClick={() => toggle(p.id)} data-testid={`group-member-${p.id}`} className={`flex w-full items-center gap-3 rounded-xl border p-2.5 text-left ${on ? "border-[#2F6BFF] bg-[#EEF3FF]" : "border-[#E7ECF3]"}`}>
              {p.portrait ? <img src={p.portrait} alt="" className="h-8 w-8 rounded-full object-cover" /> : <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#7C3AED] text-xs font-bold text-white">{p.name[0]}</span>}
              <span className="flex-1 text-sm font-semibold text-slate-900">{p.name}</span>
              <span className={`flex h-5 w-5 items-center justify-center rounded-md border ${on ? "btn-grad border-transparent" : "border-slate-300"}`}>{on && <CheckCircle2 size={13} />}</span>
            </button>
          ); })}
        </div>
        {(target.other_groups || []).length > 0 && (
          <div className="mt-3">
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Atau pakai grup yang ada</p>
            <div className="mt-1 max-h-28 space-y-1 overflow-y-auto">{target.other_groups.map((g) => <button key={g.id} onClick={() => onCreate({ conversation_id: g.id })} className="block w-full truncate rounded-lg px-2 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-50" data-testid={`use-group-${g.id}`}>{g.title}</button>)}</div>
          </div>
        )}
        <button disabled={busy || ids.length < 1} onClick={async () => { setBusy(true); await onCreate({ group_title: title, persona_ids: ids }); setBusy(false); }} className="btn-grad mt-4 flex w-full items-center justify-center gap-2 rounded-xl py-2.5 text-sm disabled:opacity-50" data-testid="group-modal-create">
          {busy ? <Loader2 size={15} className="animate-spin" /> : <MessageSquare size={15} />} Buat Grup & {mode === "call" ? "Mulai Panggilan" : "Buka Chat"}
        </button>
      </div>
    </div>
  );
}

function DiscussBar({ task, nav }) {
  const [busy, setBusy] = useState("");
  const [modal, setModal] = useState(null); // {target, mode}
  const open = async (mode, body = {}) => {
    const r = await api.post(`/tasks/${task.id}/discuss`, { mode, ...body });
    nav(`/chat/${r.data.conversation_id}`, { state: r.data.open_call ? { openMeeting: true } : {} });
  };
  const go = async (mode) => {
    setBusy(mode);
    try {
      const t = (await api.get(`/tasks/${task.id}/chat-target`)).data;
      if (t.single) return await open(mode);
      if (t.group) return await open(mode, { conversation_id: t.group.id });
      setModal({ target: t, mode });
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
      <B mode="call" Icon={Phone} label="Panggilan" cls="bg-[#10B981]" />
      {modal && <GroupModal target={modal.target} mode={modal.mode} onClose={() => setModal(null)} onCreate={async (body) => { try { await open(modal.mode, body); } catch (e) { toast.error("Gagal membuat grup"); } }} />}
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
  const [compare, setCompare] = useState(null); // {version, content} base version shown as a diff against the one being viewed

  const load = () => api.get(`/tasks/${id}`).then((r) => { setTask(r.data); setViewVer(null); setCompare(null); }).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);
  useEffect(() => {
    if (!task) return;
    const off = onUserEvent(["task_update"], (e) => { if (!e.task_id || e.task_id === id) load(); });
    if (["queued", "running"].includes(task.status)) { const iv = setInterval(() => { if (!isWsConnected()) load(); }, 15000); return () => { clearInterval(iv); off(); }; }
    return off;
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
  const curVer = viewVer ? viewVer.version : task.version;
  const fetchVer = async (v) => (v === task.version ? { version: v, content: task.final_output } : (await api.get(`/tasks/${id}/versions/${v}`)).data);
  const toggleCompare = async () => {
    if (compare) { setCompare(null); return; }
    const base = [...allVersions].filter((v) => v < curVer).pop() ?? allVersions.find((v) => v !== curVer);
    if (base === undefined) return;
    try { setCompare(await fetchVer(base)); } catch (e) { toast.error("Versi tidak ditemukan"); }
  };
  const setBase = async (v) => { try { setCompare(await fetchVer(v)); } catch (e) { toast.error("Versi tidak ditemukan"); } };

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

      {task.parent_id && <button onClick={() => nav(`/workspace/${task.parent_id}`)} className="mt-4 text-xs font-semibold text-[#2F6BFF]" data-testid="task-parent-link">← Bagian dari tugas tim</button>}
      {(task.subtasks || []).length > 0 && (
        <div className="mt-8" data-testid="subtasks">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">Pembagian ke tim · {task.subtasks.length} sub-tugas</h2>
          <div className="space-y-2">
            {task.subtasks.map((s) => (
              <button key={s.id} onClick={() => nav(`/workspace/${s.id}`)} className="aivora-card flex w-full items-center gap-3 p-4 text-left hover:border-[#2F6BFF]/40" data-testid={`subtask-${s.id}`}>
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#7C3AED] text-xs font-bold text-white">{(s.persona_name || "A")[0]}</span>
                <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold text-slate-900">{s.title}</span><span className="block text-xs text-slate-500">{s.persona_name}{s.pinned && <span className="ml-1.5 rounded-full bg-[#EEF3FF] px-1.5 py-0.5 text-[10px] font-semibold text-[#2F6BFF]" data-testid="subtask-pinned">ditunjuk Anda</span>}</span></span>
                <StatusBadge status={s.status} />
              </button>
            ))}
          </div>
        </div>
      )}
      {(task.steps || []).length > 0 || (["queued", "running"].includes(task.status) && !(task.subtasks || []).length) ? (<>
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
              {allVersions.length > 1 && (
                <button onClick={toggleCompare} className={`flex items-center gap-1 rounded-lg border px-3 py-1.5 text-xs ${compare ? "border-[#2F6BFF] bg-[#EEF3FF] font-semibold text-[#2F6BFF]" : "border-slate-200 text-slate-600"}`} data-testid="compare-toggle" title="Tampilkan perbedaan dengan versi lain"><GitCompareArrows size={13} /> {compare ? "Tutup perbandingan" : "Bandingkan"}</button>
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
          {compare && (
            <div className="mb-3" data-testid="compare-panel">
              <label className="mb-2 flex items-center gap-2 text-xs text-slate-600">Bandingkan v{curVer} dengan
                <select value={compare.version} onChange={(e) => setBase(parseInt(e.target.value, 10))} className="rounded-lg border border-slate-200 bg-white px-2 py-1 outline-none" data-testid="compare-base-select">
                  {allVersions.filter((v) => v !== curVer).map((v) => <option key={v} value={v}>v{v}</option>)}
                </select>
                <span className="text-slate-400">· hijau = ditambahkan, merah = dihapus</span>
              </label>
              <VersionDiff oldText={compare.content} newText={content} oldLabel={`v${compare.version}`} newLabel={`v${curVer}`} />
            </div>
          )}
          {!compare && <div className="aivora-card p-6" data-testid="final-output"><Markdown content={content} /></div>}
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
