import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useI18n } from "../i18n";

const STATUSES = ["all", "running", "queued", "completed", "failed"];
const statusColor = { completed: "#10B981", running: "#8B5CF6", queued: "#F59E0B", failed: "#EF4444", cancelled: "#94A3B8" };

export default function Workspace() {
  const nav = useNavigate();
  const { t } = useI18n();
  const [goal, setGoal] = useState("");
  const [tasks, setTasks] = useState([]);
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => {
    const params = [];
    if (filter !== "all") params.push(`status=${filter}`);
    if (q) params.push(`q=${encodeURIComponent(q)}`);
    api.get(`/tasks${params.length ? `?${params.join("&")}` : ""}`).then((r) => setTasks(r.data)).catch(() => {});
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filter, q]);
  useEffect(() => {
    const iv = setInterval(() => { if (tasks.some((x) => ["queued", "running"].includes(x.status))) load(); }, 4000);
    return () => clearInterval(iv); /* eslint-disable-next-line */
  }, [tasks, filter, q]);

  const delegate = async () => {
    if (!goal.trim()) return;
    setBusy(true);
    try { const r = await api.post("/tasks", { goal }); setGoal(""); toast.success("Aivora mulai mengerjakan..."); nav(`/workspace/${r.data.id}`); }
    catch (e) { toast.error("Gagal"); } finally { setBusy(false); }
  };
  const del = async (id, e) => { e.stopPropagation(); await api.delete(`/tasks/${id}`); load(); };

  return (
    <div className="mx-auto max-w-5xl p-5 sm:p-8 lg:p-10 fade-up" data-testid="workspace-page">
      <h1 className="text-3xl font-extrabold text-slate-900">{t("nav.workspace")}</h1>
      <p className="text-sm text-slate-500">Beri Aivora sebuah tujuan — tim agent akan mengerjakannya.</p>

      <div className="mt-6 aivora-card p-5" style={{ background: "linear-gradient(135deg, rgba(0,209,255,.08), rgba(124,58,237,.1))" }}>
        <textarea className="input-dark min-h-[90px]" placeholder={t("work.delegate")} value={goal} onChange={(e) => setGoal(e.target.value)} data-testid="goal-input" />
        <button onClick={delegate} disabled={busy} className="btn-grad mt-3 flex items-center gap-2 rounded-xl px-6 py-3 text-sm" data-testid="delegate-btn">
          <Sparkles size={16} /> {busy ? "..." : "Delegasikan ke Aivora"}
        </button>
      </div>

      <div className="mt-8 flex flex-wrap items-center gap-2">
        {STATUSES.map((s) => (
          <button key={s} onClick={() => setFilter(s)} data-testid={`filter-${s}`}
            className={`rounded-full px-4 py-1.5 text-xs font-medium capitalize ${filter === s ? "btn-grad" : "border border-slate-200 text-slate-500"}`}>{s}</button>
        ))}
        <div className="relative ml-auto">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input className="input-dark w-48 py-2 pl-9" placeholder={t("common.search")} value={q} onChange={(e) => setQ(e.target.value)} data-testid="task-search" />
        </div>
      </div>

      <div className="mt-5 space-y-3">
        {tasks.length === 0 ? <p className="py-10 text-center text-slate-500">Belum ada tugas.</p> : tasks.map((tk) => (
          <div key={tk.id} onClick={() => nav(`/workspace/${tk.id}`)} data-testid={`task-${tk.id}`}
            className="aivora-card aivora-card-hover group flex cursor-pointer items-center justify-between p-5">
            <div className="min-w-0">
              <p className="truncate font-semibold text-slate-900">{tk.goal}</p>
              <p className="mt-1 text-xs text-slate-500">{(tk.steps || []).length} subtugas · {tk.credits_used || 0} kredit</p>
            </div>
            <div className="ml-4 flex items-center gap-3">
              <span className="rounded-full px-3 py-1 text-xs font-semibold capitalize" style={{ background: `${statusColor[tk.status]}22`, color: statusColor[tk.status] }}>{tk.status}</span>
              <button onClick={(e) => del(tk.id, e)} className="text-slate-500 opacity-0 transition group-hover:opacity-100 hover:text-[#EF4444]"><Trash2 size={15} /></button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
