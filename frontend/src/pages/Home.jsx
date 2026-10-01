import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, Users, Briefcase, MessageSquare, Bell, ArrowRight, Loader2, CheckCircle2, Clock } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n";
import { AIVORA_MARK } from "../components/Logo";

const statusColor = {
  completed: "#10B981", running: "#8B5CF6", queued: "#F59E0B", failed: "#EF4444", cancelled: "#94A3B8",
};

export default function Home() {
  const { user } = useAuth();
  const { t } = useI18n();
  const nav = useNavigate();
  const [personas, setPersonas] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [wallet, setWallet] = useState(null);

  useEffect(() => {
    api.get("/personas").then((r) => setPersonas(r.data)).catch(() => {});
    api.get("/tasks").then((r) => setTasks(r.data)).catch(() => {});
    api.get("/wallet").then((r) => setWallet(r.data)).catch(() => {});
  }, []);

  const running = tasks.filter((x) => ["queued", "running"].includes(x.status));
  const done = tasks.filter((x) => x.status === "completed");

  const quick = [
    { icon: Users, label: t("home.newPersona"), to: "/personas/new", color: "#00D1FF", test: "qa-persona" },
    { icon: Briefcase, label: t("home.delegate"), to: "/workspace", color: "#7C3AED", test: "qa-delegate" },
    { icon: MessageSquare, label: t("home.startChat"), to: "/chat", color: "#06B6D4", test: "qa-chat" },
    { icon: Bell, label: t("nav.reminders"), to: "/reminders", color: "#F59E0B", test: "qa-reminders" },
  ];

  return (
    <div className="p-5 sm:p-8 lg:p-10 fade-up" data-testid="home-page">
      <div className="flex items-center gap-4">
        <img src={AIVORA_MARK} alt="" className="h-12 w-12" />
        <div>
          <h1 className="text-3xl font-extrabold text-white sm:text-4xl">
            {t("home.greeting")}, <span className="grad-text">{user?.name}</span>
          </h1>
          <p className="text-sm text-slate-400">Apa yang ingin Anda kerjakan hari ini?</p>
        </div>
      </div>

      {/* quick actions */}
      <div className="mt-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {quick.map((q) => (
          <button key={q.test} data-testid={q.test} onClick={() => nav(q.to)}
            className="aivora-card aivora-card-hover group flex flex-col items-start gap-4 p-5 text-left">
            <span className="flex h-11 w-11 items-center justify-center rounded-xl" style={{ background: `${q.color}22`, color: q.color }}>
              <q.icon size={22} />
            </span>
            <span className="flex items-center gap-1 text-sm font-semibold text-white">{q.label}
              <ArrowRight size={14} className="opacity-0 transition group-hover:translate-x-1 group-hover:opacity-100" /></span>
          </button>
        ))}
      </div>

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* running + recent */}
        <div className="space-y-6 lg:col-span-2">
          <section className="aivora-card p-6">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-white"><Loader2 size={18} className="text-[#8B5CF6]" /> {t("home.running")}</h2>
            {running.length === 0 ? (
              <p className="text-sm text-slate-500">Tidak ada tugas berjalan.</p>
            ) : running.map((tk) => (
              <button key={tk.id} onClick={() => nav(`/workspace/${tk.id}`)} data-testid={`home-task-${tk.id}`}
                className="mb-2 flex w-full items-center justify-between rounded-xl bg-[#0e1830] px-4 py-3 text-left hover:bg-[#1C2D5A]">
                <span className="truncate text-sm text-slate-200">{tk.goal}</span>
                <span className="ml-3 flex items-center gap-1.5 text-xs" style={{ color: statusColor[tk.status] }}>
                  <Clock size={13} /> {tk.status}</span>
              </button>
            ))}
          </section>

          <section className="aivora-card p-6">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-white"><CheckCircle2 size={18} className="text-[#10B981]" /> {t("home.recent")}</h2>
            {done.length === 0 ? (
              <p className="text-sm text-slate-500">{t("home.empty")}</p>
            ) : done.slice(0, 5).map((tk) => (
              <button key={tk.id} onClick={() => nav(`/workspace/${tk.id}`)} data-testid={`home-done-${tk.id}`}
                className="mb-2 flex w-full items-center justify-between rounded-xl bg-[#0e1830] px-4 py-3 text-left hover:bg-[#1C2D5A]">
                <span className="truncate text-sm text-slate-200">{tk.goal}</span>
                <ArrowRight size={14} className="ml-3 shrink-0 text-slate-500" />
              </button>
            ))}
          </section>
        </div>

        {/* sidebar: wallet + personas */}
        <div className="space-y-6">
          <section className="aivora-card overflow-hidden p-6" style={{ background: "linear-gradient(135deg, rgba(0,209,255,.12), rgba(124,58,237,.14))" }}>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-300"><Sparkles size={16} className="text-[#00D1FF]" /> {t("home.wallet")}</h2>
            <p className="mt-3 text-4xl font-extrabold text-white" data-testid="home-credits">{user?.credits ?? 0}</p>
            <p className="text-sm text-slate-400">{t("common.credits")} tersedia</p>
            <button onClick={() => nav("/wallet")} data-testid="home-topup-btn" className="btn-grad mt-4 w-full rounded-xl py-2.5 text-sm">{t("wallet.topup")}</button>
          </section>

          <section className="aivora-card p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-bold text-white">{t("nav.personas")}</h2>
              <button onClick={() => nav("/personas")} className="text-xs text-[#00D1FF]">Lihat semua</button>
            </div>
            {personas.length === 0 ? (
              <button onClick={() => nav("/personas/new")} data-testid="home-create-persona" className="w-full rounded-xl border border-dashed border-slate-600 py-6 text-sm text-slate-400 hover:border-[#00D1FF]">
                + Buat persona pertama Anda
              </button>
            ) : personas.slice(0, 4).map((p) => (
              <button key={p.id} onClick={() => nav(`/personas/${p.id}`)} data-testid={`home-persona-${p.id}`}
                className="mb-2 flex w-full items-center gap-3 rounded-xl bg-[#0e1830] px-3 py-2.5 text-left hover:bg-[#1C2D5A]">
                <div className="h-9 w-9 shrink-0 overflow-hidden rounded-full bg-[#1C2D5A]">
                  {p.portrait ? <img src={p.portrait} alt="" className="h-full w-full object-cover" /> : <div className="flex h-full w-full items-center justify-center text-xs text-slate-400">{p.name[0]}</div>}
                </div>
                <span className="truncate text-sm text-slate-200">{p.name}</span>
              </button>
            ))}
          </section>
        </div>
      </div>
    </div>
  );
}
