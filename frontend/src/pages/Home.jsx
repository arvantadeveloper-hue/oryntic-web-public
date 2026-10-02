import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MessageSquare, FileText, Bot, Users, Sparkles, Plus, ArrowRight, CheckCircle2, Clock, FolderKanban, Mic, Video, Bell, Search, MoreHorizontal, Zap } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { BRAND_HERO } from "../components/Logo";
import { TrialBanner } from "../components/TrialBanner";

const statusColor = { completed: "#10B981", running: "#7C3AED", queued: "#F59E0B", failed: "#EF4444", cancelled: "#94A3B8" };
const ago = (iso) => {
  const d = (Date.now() - new Date(iso).getTime()) / 60000;
  if (d < 1) return "baru saja";
  if (d < 60) return `${Math.round(d)} mnt lalu`;
  if (d < 1440) return `${Math.round(d / 60)} jam lalu`;
  return `${Math.round(d / 1440)} hari lalu`;
};

function Stat({ icon: Icon, label, value, tint, testId }) {
  return (
    <div className="aivora-card flex items-center gap-3 p-4" data-testid={testId}>
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl" style={{ background: `${tint}14`, color: tint }}><Icon size={20} /></span>
      <div className="min-w-0">
        <p className="truncate text-xs font-medium text-slate-500">{label}</p>
        <p className="text-2xl font-bold leading-tight text-slate-900">{value}</p>
      </div>
      <span className="ml-auto flex items-end gap-0.5">{[5, 8, 6, 10, 7, 12].map((h, i) => <span key={i} className="w-1 rounded-sm" style={{ height: h + 4, background: `${tint}${i === 5 ? "" : "66"}` }} />)}</span>
    </div>
  );
}

function SectionHead({ title, action, onAction, extra }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="text-base font-bold text-slate-900 md:text-lg">{title}</h2>
      <div className="flex items-center gap-2">
        {action && <button onClick={onAction} className="text-xs font-semibold text-[#2F6BFF] hover:underline">{action}</button>}
        {extra}
      </div>
    </div>
  );
}

export default function Home() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [tasks, setTasks] = useState([]);
  const [reminders, setReminders] = useState([]);
  const [personas, setPersonas] = useState([]);
  const [convs, setConvs] = useState([]);
  const isAdmin = user?.role === "admin";

  useEffect(() => {
    api.get("/tasks").then((r) => setTasks(r.data)).catch(() => {});
    api.get("/reminders").then((r) => setReminders(r.data)).catch(() => {});
    api.get("/personas").then((r) => setPersonas(r.data)).catch(() => {});
    api.get("/conversations").then((r) => setConvs(r.data)).catch(() => {});
  }, []);

  const completed = tasks.filter((t) => t.status === "completed");
  const upcoming = reminders.filter((r) => ["scheduled", "ringing"].includes(r.status)).slice(0, 4);
  const activity = [
    ...tasks.map((t) => ({ id: "t" + t.id, icon: FolderKanban, tint: "#7C3AED", text: `Tugas "${t.goal}" ${t.status === "completed" ? "selesai" : t.status === "running" ? "sedang dikerjakan" : t.status}`, at: t.updated_at || t.created_at, to: `/workspace/${t.id}` })),
    ...convs.map((c) => ({ id: "c" + c.id, icon: c.type === "meeting" ? Video : MessageSquare, tint: c.type === "meeting" ? "#10B981" : "#2F6BFF", text: c.type === "meeting" ? `Panggilan "${c.title}"` : `Percakapan "${c.title}"`, at: c.updated_at || c.created_at, to: `/chat/${c.id}` })),
  ].sort((a, b) => new Date(b.at) - new Date(a.at)).slice(0, 5);

  const now = new Date();
  const dateStr = now.toLocaleDateString("id-ID", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
  const first = (user?.name || "").split(" ")[0];
  const QUICK = [
    { icon: Bot, title: "Agen Baru", desc: "Buat & atur agen AI", to: isAdmin ? "/personas/new" : "/chat", tint: "#2F6BFF" },
    { icon: Video, title: "Panggilan", desc: "Rapat suara dengan agen", to: "/chat", tint: "#10B981" },
    { icon: FolderKanban, title: "Tugas Baru", desc: "Delegasikan pekerjaan", to: "/workspace", tint: "#7C3AED" },
    { icon: Bell, title: "Pengingat", desc: "Jadwal & panggilan", to: "/reminders", tint: "#F59E0B" },
    { icon: Users, title: "Tim", desc: "Kelola anggota", to: isAdmin ? "/team" : "/profile", tint: "#EC4899" },
  ];
  const TOOLS = [
    { icon: MessageSquare, label: "Chat", to: "/chat", tint: "#2F6BFF" }, { icon: FileText, label: "Dokumen", to: "/workspace", tint: "#10B981" },
    { icon: Video, label: "Panggilan", to: "/chat", tint: "#7C3AED" }, { icon: Search, label: "Riset", to: "/workspace", tint: "#F59E0B" },
    { icon: Mic, label: "Suara", to: "/chat", tint: "#22B8FF" }, { icon: Zap, label: "Otomasi", to: "/workspace", tint: "#EC4899" },
    { icon: Bell, label: "Pengingat", to: "/reminders", tint: "#F97316" }, { icon: MoreHorizontal, label: "Lainnya", to: "/profile", tint: "#64748B" },
  ];

  return (
    <div className="grid grid-cols-1 gap-5 p-4 sm:p-6 xl:grid-cols-[1fr_320px] fade-up" data-testid="home-page">
      <div className="min-w-0 space-y-5">
        <TrialBanner />
        {/* hero banner */}
        <section className="relative overflow-hidden rounded-3xl p-6 sm:p-8" style={{ background: "linear-gradient(110deg,#EAF0FF 0%,#F2F5FF 55%,#E6F4FF 100%)" }} data-testid="home-hero">
          <div className="relative z-10 max-w-lg">
            <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">Welcome back, {first}</p>
            <h1 className="mt-2 text-3xl font-bold leading-[1.1] tracking-tight text-[#0A1128] sm:text-4xl lg:text-[40px]">Turn your ideas into real results with AI.</h1>
            <p className="mt-3 max-w-md text-sm text-slate-600 md:text-base">Orkestrasikan agen AI, otomatiskan alur kerja, dan percepat bisnis Anda bersama Oryntix.</p>
            <div className="mt-5 flex flex-wrap gap-2.5">
              <button onClick={() => nav(isAdmin ? "/personas/new" : "/chat")} data-testid="home-create-persona" className="btn-primary"><Plus size={16} /> {isAdmin ? "Create New Agent" : "Mulai Chat"}</button>
              <button onClick={() => nav("/chat")} data-testid="home-team-chat" className="btn-soft">Mulai Panggilan</button>
            </div>
          </div>
          <img src={BRAND_HERO} alt="" className="hero-float pointer-events-none absolute -right-6 top-1/2 hidden w-72 -translate-y-1/2 drop-shadow-2xl md:block lg:w-80" />
        </section>

        {/* stats */}
        <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat icon={Bot} label="Active Agents" value={personas.length} tint="#2F6BFF" testId="stat-agents" />
          <Stat icon={FolderKanban} label="Projects" value={tasks.length} tint="#7C3AED" testId="stat-projects" />
          <Stat icon={CheckCircle2} label="Tasks Completed" value={completed.length} tint="#10B981" testId="stat-completed" />
          <Stat icon={Clock} label="Panggilan" value={convs.filter((c) => c.type === "meeting").length} tint="#F59E0B" testId="stat-meetings" />
        </section>

        <div className="grid gap-5 lg:grid-cols-2">
          {/* recent activity */}
          <section className="aivora-card p-5" data-testid="home-activity">
            <SectionHead title="Recent Activity" action="View All" onAction={() => nav("/workspace")} />
            {activity.length === 0 ? (
              <p className="py-6 text-center text-sm text-slate-400">Belum ada aktivitas. Mulai chat atau beri tugas pada agen Anda.</p>
            ) : activity.map((a) => (
              <button key={a.id} onClick={() => nav(a.to)} className="flex w-full items-center gap-3 rounded-xl px-2 py-2.5 text-left transition hover:bg-slate-50">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg" style={{ background: `${a.tint}14`, color: a.tint }}><a.icon size={16} /></span>
                <span className="min-w-0 flex-1 truncate text-sm text-slate-700">{a.text}</span>
                <span className="shrink-0 text-xs text-slate-400">{ago(a.at)}</span>
              </button>
            ))}
          </section>

          {/* your AI agents */}
          <section className="aivora-card p-5" data-testid="home-agents">
            <SectionHead title="Your AI Agents" action="View All" onAction={() => nav(isAdmin ? "/personas" : "/chat")}
              extra={isAdmin && <button onClick={() => nav("/personas/new")} className="flex h-6 w-6 items-center justify-center rounded-md bg-[#2F6BFF] text-white" data-testid="home-add-agent"><Plus size={14} /></button>} />
            {personas.length === 0 ? (
              <div className="py-5 text-center">
                <p className="text-sm text-slate-400">Belum ada agen AI.</p>
                {isAdmin && <button onClick={() => nav("/personas/new")} className="btn-primary mt-3">+ Buat Agen</button>}
              </div>
            ) : personas.slice(0, 5).map((p) => (
              <button key={p.id} onClick={() => nav(isAdmin ? `/personas/${p.id}` : "/chat")} className="flex w-full items-center gap-3 rounded-xl px-2 py-2.5 text-left transition hover:bg-slate-50" data-testid={`home-persona-${p.id}`}>
                {p.portrait ? <img src={p.portrait} alt="" className="h-9 w-9 rounded-lg object-cover" /> : <span className="flex h-9 w-9 items-center justify-center rounded-lg text-sm font-bold text-white" style={{ background: "linear-gradient(135deg,#2F6BFF,#7C3AED)" }}>{p.name[0]}</span>}
                <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold text-slate-900">{p.name}</span><span className="block truncate text-xs text-slate-400">{p.summary || p.model || "Agen AI"}</span></span>
                <span className="flex items-center gap-1.5 text-xs text-slate-500"><span className="h-2 w-2 rounded-full bg-[#10B981]" /> Online</span>
              </button>
            ))}
          </section>
        </div>

        {/* quick actions */}
        <section>
          <SectionHead title="Quick Actions" />
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {QUICK.map((q) => (
              <button key={q.title} onClick={() => nav(q.to)} data-testid={`qa-${q.title}`} className="aivora-card aivora-card-hover flex items-center gap-3 p-3.5 text-left">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl" style={{ background: `${q.tint}14`, color: q.tint }}><q.icon size={18} /></span>
                <span className="min-w-0"><span className="block truncate text-sm font-semibold text-slate-900">{q.title}</span><span className="block truncate text-[11px] text-slate-400">{q.desc}</span></span>
              </button>
            ))}
          </div>
        </section>
      </div>

      {/* right rail */}
      <aside className="space-y-5">
        <div className="aivora-card p-4">
          <div className="flex items-center justify-between"><p className="text-sm font-bold text-slate-900">{dateStr}</p><span className="text-xs text-slate-400">Today</span></div>
          <div className="mt-3 grid grid-cols-7 gap-1">
            {["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"].map((d, i) => {
              const day = new Date(now); day.setDate(now.getDate() - now.getDay() + i);
              const active = day.toDateString() === now.toDateString();
              return (
                <div key={d} className="flex flex-col items-center gap-1">
                  <span className="text-[10px] text-slate-400">{d}</span>
                  <span className={`flex h-8 w-8 items-center justify-center rounded-lg text-sm font-semibold ${active ? "bg-[#2F6BFF] text-white" : "text-slate-700"}`}>{day.getDate()}</span>
                </div>
              );
            })}
          </div>
          <div className="mt-4 flex items-center justify-between"><p className="text-sm font-bold text-slate-900">Upcoming</p><button onClick={() => nav("/reminders")} className="text-xs font-semibold text-[#2F6BFF]">View All</button></div>
          {upcoming.length === 0 ? <p className="py-3 text-xs text-slate-400">Belum ada jadwal.</p> : upcoming.map((r) => (
            <div key={r.id} className="mt-2 flex items-start gap-3" data-testid={`home-rem-${r.id}`}>
              <span className="w-10 shrink-0 text-xs text-slate-400">{new Date(r.start_at).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })}</span>
              <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-[#2F6BFF]" />
              <div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-800">{r.title}</p><p className="text-xs text-slate-400">{new Date(r.start_at).toLocaleDateString("id-ID", { day: "numeric", month: "short" })}</p></div>
            </div>
          ))}
        </div>

        <div className="rounded-2xl p-5 text-white" style={{ background: "linear-gradient(135deg,#2F6BFF 0%,#5B3DF5 100%)" }} data-testid="home-promo">
          <Sparkles size={22} />
          <p className="mt-2 text-sm font-bold">Boost your productivity with AI meetings</p>
          <p className="mt-1 text-xs text-white/80">Ajak beberapa agen ke satu ruang panggilan, bicara bebas, dan dapatkan notulen otomatis.</p>
          <button onClick={() => nav("/chat")} className="mt-3 flex items-center gap-1.5 rounded-lg bg-white px-3.5 py-2 text-xs font-bold text-[#2F6BFF]">Mulai Panggilan <ArrowRight size={13} /></button>
        </div>

        <div className="aivora-card p-4">
          <div className="flex items-center justify-between"><p className="text-sm font-bold text-slate-900">Popular Tools</p></div>
          <div className="mt-3 grid grid-cols-4 gap-2">
            {TOOLS.map((tl) => (
              <button key={tl.label} onClick={() => nav(tl.to)} className="flex flex-col items-center gap-1.5 rounded-xl p-2 transition hover:bg-slate-50">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl" style={{ background: `${tl.tint}14`, color: tl.tint }}><tl.icon size={18} /></span>
                <span className="text-[11px] font-medium text-slate-600">{tl.label}</span>
              </button>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}
