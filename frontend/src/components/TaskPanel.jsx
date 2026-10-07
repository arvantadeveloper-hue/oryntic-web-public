import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { X, ExternalLink, Loader2, CheckCircle2, Clock, XCircle, ClipboardList, Images, FileText } from "lucide-react";
import { api } from "../lib/api";
import { onUserEvent, coalesce } from "../lib/userEvents";
import { Markdown } from "./Markdown";
import { MediaList } from "./MessageExtras";

const STATUS = { completed: ["#10B981", "Selesai"], running: ["#8B5CF6", "Berjalan"], queued: ["#F59E0B", "Antre"], failed: ["#EF4444", "Gagal"], scheduled: ["#2F6BFF", "Terjadwal"], cancelled: ["#94A3B8", "Batal"] };
const Badge = ({ status }) => { const [c, l] = STATUS[status] || ["#94A3B8", status]; return <span className="shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold" style={{ background: `${c}22`, color: c }} data-testid="task-panel-status">{l}</span>; };

function useTask(taskId) {
  const [task, setTask] = useState(null);
  useEffect(() => {
    if (!taskId) return undefined;
    let alive = true;
    const load = () => api.get(`/tasks/${taskId}`).then((r) => alive && setTask(r.data)).catch(() => {});
    load();
    const off = onUserEvent(["task_update", "ws_state"], (e) => { if (e.type === "ws_state" ? e.connected : (!e.task_id || e.task_id === taskId)) coalesce(`task-${taskId}`, load); }); // trigger → GET
    return () => { alive = false; off(); };
  }, [taskId]);
  return task;
}

// Compact clickable card under an assistant message that produced a Workspace task (document / image set).
export function TaskCard({ m, onOpen }) {
  const task = useTask(m.task_id);
  if (!m.task_id) return null;
  const done = (task?.steps || []).filter((s) => s.status === "completed").length;
  const total = (task?.steps || []).length;
  const isImg = (m.tool || task?.type) === "image_set" || task?.type === "image_set";
  return (
    <button onClick={() => onOpen(m.task_id)} data-testid="task-card" className="mt-2 flex w-full items-center gap-3 rounded-xl border border-[#2F6BFF]/25 bg-[#EEF3FF] p-3 text-left transition hover:border-[#2F6BFF]/60 hover:bg-[#E0E9FF]">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#2F6BFF] text-white">{isImg ? <Images size={16} /> : <FileText size={16} />}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-xs font-bold text-slate-900" data-testid="task-card-title">{task?.goal || "Tugas Ruang Kerja"}</span>
        <span className="block text-[11px] text-slate-500">{task ? (total ? `${done}/${total} selesai · ` : "") + (task.status === "running" ? "sedang dikerjakan…" : task.status === "completed" ? "klik untuk lihat hasil" : STATUS[task.status]?.[1] || task.status) : "memuat…"}</span>
      </span>
      {task ? <Badge status={task.status} /> : <Loader2 size={14} className="animate-spin text-slate-400" />}
    </button>
  );
}

// Right-hand slide-in with the task detail (progress, media, result) — opened from TaskCard / /workspace links in chat.
export function TaskSidePanel({ taskId, onClose }) {
  const task = useTask(taskId);
  const nav = useNavigate();
  useEffect(() => { const k = (e) => e.key === "Escape" && onClose(); window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [onClose]);
  if (!taskId) return null;
  const icon = (s) => s.status === "completed" ? <CheckCircle2 size={14} className="text-[#10B981]" /> : s.status === "running" ? <Loader2 size={14} className="animate-spin text-[#8B5CF6]" /> : s.status === "failed" ? <XCircle size={14} className="text-[#EF4444]" /> : <Clock size={14} className="text-[#F59E0B]" />;
  return (
    <>
      <div className="fixed inset-0 z-[70] bg-slate-900/30 md:hidden" onClick={onClose} />
      <aside className="fixed right-0 top-0 z-[71] flex h-full w-full max-w-md flex-col border-l border-[#E7ECF3] bg-white shadow-2xl md:absolute md:w-[420px]" data-testid="task-side-panel" style={{ animation: "fadeUp .25s ease both" }}>
        <div className="flex items-start gap-3 border-b border-[#E7ECF3] p-4">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#2F6BFF] text-white"><ClipboardList size={17} /></span>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-bold uppercase tracking-wider text-[#2F6BFF]">Tugas Ruang Kerja{task ? ` · v${task.version}` : ""}</p>
            <p className="truncate text-sm font-bold text-slate-900" data-testid="task-panel-title">{task?.goal || "Memuat…"}</p>
            {task?.summary && <p className="mt-0.5 text-xs text-slate-500">{task.summary}</p>}
          </div>
          {task && <Badge status={task.status} />}
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700" data-testid="task-panel-close"><X size={18} /></button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {!task && <p className="flex items-center gap-2 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat tugas…</p>}
          {(task?.steps || []).length > 0 && (
            <div data-testid="task-panel-steps">
              <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">Progres</p>
              <div className="space-y-1.5">{task.steps.map((s, i) => <div key={s.id || i} className="flex items-start gap-2 rounded-lg border border-[#E7ECF3] px-3 py-2 text-xs text-slate-700" data-testid={`task-panel-step-${i}`}>{icon(s)}<span className="min-w-0 flex-1 truncate">{s.title}</span></div>)}</div>
            </div>
          )}
          {(task?.media || []).length > 0 && <div data-testid="task-panel-media"><p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">Hasil ({task.media.length})</p><MediaList media={task.media} /></div>}
          {task?.status === "completed" && task.final_output && <div className="rounded-xl border border-[#E7ECF3] p-3 text-sm text-slate-700" data-testid="task-panel-output"><Markdown content={task.final_output} /></div>}
          {task?.status === "failed" && <p className="rounded-xl border border-[#EF4444]/40 bg-[#EF4444]/10 p-3 text-xs text-[#EF4444]">Tugas gagal. {task.error}</p>}
        </div>
        <div className="flex items-center justify-between border-t border-[#E7ECF3] p-3 text-xs">
          <span className="text-slate-500">{task ? `${task.credits_used || 0} kredit` : ""}</span>
          <button onClick={() => nav(`/workspace/${taskId}`)} className="flex items-center gap-1 font-semibold text-[#2F6BFF]" data-testid="task-panel-open-full"><ExternalLink size={12} /> Buka halaman penuh</button>
        </div>
      </aside>
    </>
  );
}
