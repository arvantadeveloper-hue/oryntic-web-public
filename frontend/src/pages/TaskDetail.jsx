import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Download, Copy, CheckCircle2, Loader2, Clock, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Markdown } from "../components/Markdown";
import { Mark } from "../components/Logo";

const roleColor = { Research: "#00D1FF", Planning: "#F59E0B", Writing: "#7C3AED", Analyst: "#06B6D4", Coding: "#10B981", Reviewer: "#EF4444" };

export default function TaskDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [task, setTask] = useState(null);

  const load = () => api.get(`/tasks/${id}`).then((r) => setTask(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);
  useEffect(() => {
    if (!task) return;
    if (["queued", "running"].includes(task.status)) { const iv = setInterval(load, 3000); return () => clearInterval(iv); }
    /* eslint-disable-next-line */
  }, [task]);

  if (!task) return <div className="p-10 text-slate-500">Memuat...</div>;

  const exportMd = () => {
    const blob = new Blob([task.final_output || ""], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `aivora-task-${id.slice(0, 8)}.md`; a.click();
    URL.revokeObjectURL(url);
  };

  const stepIcon = (s) => {
    if (s.status === "completed") return <CheckCircle2 size={16} className="text-[#10B981]" />;
    if (s.status === "running") return <Loader2 size={16} className="animate-spin text-[#8B5CF6]" />;
    return <Clock size={16} className="text-[#F59E0B]" />;
  };

  return (
    <div className="mx-auto max-w-4xl p-5 sm:p-8 lg:p-10 fade-up" data-testid="task-detail-page">
      <button onClick={() => nav("/workspace")} className="mb-4 flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"><ArrowLeft size={16} /> {t_back()}</button>

      <div className="aivora-card p-6">
        <div className="flex items-start gap-3">
          <Mark size={40} />
          <div className="flex-1">
            <h1 className="text-xl font-bold text-slate-900" data-testid="task-goal">{task.goal}</h1>
            {task.summary && <p className="mt-1 text-sm text-slate-500">{task.summary}</p>}
          </div>
          <StatusBadge status={task.status} />
        </div>
      </div>

      {/* subtasks */}
      <h2 className="mt-8 mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">Agent & Subtugas</h2>
      <div className="space-y-3">
        {(task.steps || []).length === 0 && ["queued", "running"].includes(task.status) && (
          <div className="aivora-card flex items-center gap-3 p-5 text-sm text-slate-500"><Loader2 size={16} className="animate-spin text-[#8B5CF6]" /> Aivora sedang menyusun rencana...</div>
        )}
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

      {/* final output */}
      {task.status === "completed" && (
        <div className="mt-8">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">Hasil Akhir</h2>
            <div className="flex gap-2">
              <button onClick={() => { navigator.clipboard.writeText(task.final_output); toast.success("Disalin"); }} className="flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600" data-testid="copy-output"><Copy size={13} /> Salin</button>
              <button onClick={exportMd} className="flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600" data-testid="export-output"><Download size={13} /> Ekspor .md</button>
            </div>
          </div>
          <div className="aivora-card p-6" data-testid="final-output"><Markdown content={task.final_output} /></div>
          <p className="mt-3 text-right text-xs text-slate-500">Total: {task.credits_used} kredit</p>
        </div>
      )}
      {task.status === "failed" && (
        <div className="mt-8 flex items-center gap-2 rounded-xl border border-[#EF4444]/40 bg-[#EF4444]/10 p-4 text-sm text-[#EF4444]"><XCircle size={16} /> Tugas gagal. {task.error}</div>
      )}
    </div>
  );
}

function t_back() { return "Ruang Kerja"; }

function StatusBadge({ status }) {
  const map = { completed: ["#10B981", "Selesai"], running: ["#8B5CF6", "Berjalan"], queued: ["#F59E0B", "Antre"], failed: ["#EF4444", "Gagal"], cancelled: ["#94A3B8", "Batal"] };
  const [c, l] = map[status] || ["#94A3B8", status];
  return <span className="shrink-0 rounded-full px-3 py-1 text-xs font-semibold" style={{ background: `${c}22`, color: c }} data-testid="task-status">{l}</span>;
}
