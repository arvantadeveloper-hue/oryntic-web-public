import { LoadMore } from "../components/ConversationTools";
import { onUserEvent, isWsConnected } from "../lib/userEvents";
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
  const [shown, setShown] = useState(20);
  const [goal, setGoal] = useState("");
  const [tasks, setTasks] = useState([]);
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [models, setModels] = useState([]);
  const [reco, setReco] = useState(null);
  const [chosen, setChosen] = useState("");

  useEffect(() => { api.get("/models").then((r) => setModels(r.data.models)).catch(() => {}); }, []);

  const load = () => {
    const params = [];
    if (filter !== "all") params.push(`status=${filter}`);
    if (q) params.push(`q=${encodeURIComponent(q)}`);
    api.get(`/tasks${params.length ? `?${params.join("&")}` : ""}`).then((r) => setTasks(r.data)).catch(() => {});
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filter, q]);
  useEffect(() => {
    const iv = setInterval(() => { if (!isWsConnected() && tasks.some((x) => ["queued", "running"].includes(x.status))) load(); }, 20000);
    const off = onUserEvent(["task_update", "ws_state"], load);
    return () => { clearInterval(iv); off(); }; /* eslint-disable-next-line */
  }, [tasks, filter, q]);

  const delegate = async () => {
    if (!goal.trim()) return;
    setBusy(true);
    try {
      const rc = await api.post("/tasks/recommend", { goal });
      if (rc.data.needs_choice && rc.data.recommendation) {
        setReco(rc.data);
        setChosen(rc.data.recommendation.executable ? rc.data.recommendation.id : rc.data.default);
        setBusy(false);
        return;
      }
      await runTask(null);
    } catch (e) { await runTask(null); }
  };
  const runTask = async (model) => {
    setBusy(true);
    try { const r = await api.post("/tasks", { goal, model }); setGoal(""); setReco(null); toast.success("Tim agen mulai mengerjakan..."); nav(`/workspace/${r.data.id}`); }
    catch (e) { toast.error("Gagal"); } finally { setBusy(false); }
  };
  const del = async (id, e) => { e.stopPropagation(); await api.delete(`/tasks/${id}`); load(); };

  return (
    <div className="mx-auto max-w-5xl p-5 sm:p-8 lg:p-10 fade-up" data-testid="workspace-page">
      <h1 className="text-3xl font-extrabold text-slate-900">{t("nav.workspace")}</h1>
      <p className="text-sm text-slate-500">Beri Oryntix sebuah tujuan — tim agent akan mengerjakannya.</p>

      <div className="mt-6 aivora-card p-5" style={{ background: "linear-gradient(135deg, rgba(0,209,255,.08), rgba(124,58,237,.1))" }}>
        <textarea className="input-dark min-h-[90px]" placeholder={t("work.delegate")} value={goal} onChange={(e) => setGoal(e.target.value)} data-testid="goal-input" />
        <button onClick={delegate} disabled={busy} className="btn-grad mt-3 flex items-center gap-2 rounded-xl px-6 py-3 text-sm" data-testid="delegate-btn">
          <Sparkles size={16} /> {busy ? "..." : "Delegasikan ke Tim"}
        </button>
        {reco && (
          <div className="mt-4 rounded-2xl border border-[#2F6BFF]/30 bg-[#EEF3FF] p-4" data-testid="reco-panel">
            <p className="text-sm font-semibold text-slate-900">💡 Rekomendasi model untuk tugas ini</p>
            <p className="mt-1 text-xs text-slate-600"><b>{reco.recommendation.label}</b> — {reco.recommendation.reason}.{!reco.recommendation.executable && " (Model khusus ini belum dapat dieksekusi di sini; tugas akan dijalankan dengan model teks terbaik yang tersedia.)"}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <select className="input-dark w-56 py-2" value={chosen} onChange={(e) => setChosen(e.target.value)} data-testid="reco-model-select">
                {models.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
              </select>
              <button onClick={() => runTask(chosen)} disabled={busy} className="btn-grad rounded-xl px-5 py-2 text-sm" data-testid="reco-run-btn">Jalankan</button>
              <button onClick={() => runTask(null)} disabled={busy} className="rounded-xl border border-slate-200 px-4 py-2 text-sm text-slate-600">Pakai default</button>
            </div>
          </div>
        )}
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
        {tasks.length === 0 ? <p className="py-10 text-center text-slate-500">Belum ada tugas.</p> : tasks.slice(0, shown).map((tk) => (
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
        {tasks.length > shown && <LoadMore onClick={() => setShown((n) => n + 20)} testid="tasks-load-more" />}
      </div>
    </div>
  );
}
