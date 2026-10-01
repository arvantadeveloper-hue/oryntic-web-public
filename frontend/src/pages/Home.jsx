import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { MessageSquare, FileText, BarChart3, Calendar, Lightbulb, Settings2, Send, ArrowRight, FileCheck2, Clock, Bot, Users, Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { AIVORA_HERO } from "../components/Logo";

const QUICK = [
  { icon: MessageSquare, title: "Chat dengan Aivora", desc: "Tanyakan apa saja, dapatkan jawaban instan", to: "/chat", c: "#2F6BFF" },
  { icon: FileText, title: "Buat Dokumen", desc: "Buat proposal, laporan, atau dokumen", to: "/workspace", c: "#7C3AED" },
  { icon: BarChart3, title: "Analisis Data", desc: "Minta insight dari data Anda", to: "/workspace", c: "#22B8FF" },
  { icon: Calendar, title: "Jadwalkan Meeting", desc: "Atur pengingat & notulen otomatis", to: "/reminders", c: "#F59E0B" },
  { icon: Lightbulb, title: "Riset & Insight", desc: "Cari informasi & analisis mendalam", to: "/workspace", c: "#10B981" },
  { icon: Settings2, title: "Otomatisasi Tugas", desc: "Delegasikan tugas ke agen AI", to: "/workspace", c: "#EC4899" },
];
const CAPS = ["Diskusi dengan berbagai agen AI", "Buat, analisis & ringkas dokumen", "Pengingat & jadwal otomatis", "Riset dan insight", "Otomatisasi tugas"];
const statusColor = { completed: "#10B981", running: "#7C3AED", queued: "#F59E0B", failed: "#EF4444", cancelled: "#94A3B8" };

function progress(tk) {
  if (tk.status === "completed") return 100;
  if (tk.status === "failed" || tk.status === "cancelled") return 100;
  const steps = tk.steps || [];
  if (!steps.length) return 8;
  return Math.max(12, Math.round((steps.filter((s) => s.status === "completed").length / steps.length) * 90));
}

export default function Home() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [tasks, setTasks] = useState([]);
  const [reminders, setReminders] = useState([]);
  const [ask, setAsk] = useState("");

  useEffect(() => {
    api.get("/tasks").then((r) => setTasks(r.data)).catch(() => {});
    api.get("/reminders").then((r) => setReminders(r.data)).catch(() => {});
  }, []);

  const projects = tasks.slice(0, 4);
  const docs = tasks.filter((t) => t.status === "completed").slice(0, 4);
  const upcoming = reminders.filter((r) => ["scheduled", "ringing"].includes(r.status)).slice(0, 5);

  const submitAsk = async () => {
    const r = await api.post("/conversations", { title: ask.slice(0, 40) || "New conversation" });
    nav(`/chat/${r.data.id}`);
  };

  const now = new Date();
  const dateStr = now.toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  return (
    <div className="grid grid-cols-1 gap-6 p-5 sm:p-7 xl:grid-cols-[1fr_340px] fade-up" data-testid="home-page">
      <div className="min-w-0 space-y-7">
        {/* hero banner */}
        <section className="relative overflow-hidden rounded-3xl p-7 sm:p-9" style={{ background: "linear-gradient(120deg,#EEF3FF 0%,#F3EEFF 60%,#EAF6FF 100%)" }}>
          <div className="grid gap-6 md:grid-cols-[1fr_auto]">
            <div className="max-w-md">
              <h1 className="text-3xl font-extrabold text-slate-900 sm:text-4xl">Halo, {user?.name}! 👋</h1>
              <p className="mt-2 text-slate-500">Ada yang bisa saya bantu hari ini?</p>
              <div className="mt-5 flex items-center gap-2 rounded-2xl border border-white bg-white/90 p-2 shadow-sm backdrop-blur">
                <Sparkles size={18} className="ml-2 text-[#2F6BFF]" />
                <input value={ask} onChange={(e) => setAsk(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submitAsk()}
                  placeholder="Tanyakan apa saja atau berikan tugas..." className="flex-1 bg-transparent px-1 text-sm outline-none" data-testid="home-ask" />
                <button onClick={submitAsk} data-testid="home-ask-send" className="btn-grad flex h-9 w-9 items-center justify-center rounded-xl"><Send size={16} /></button>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {[["Buat dokumen", FileText, "/workspace"], ["Analisis data", BarChart3, "/workspace"], ["Jadwalkan meeting", Calendar, "/reminders"]].map(([l, Ic, to]) => (
                  <button key={l} onClick={() => nav(to)} className="flex items-center gap-1.5 rounded-full border border-[#E7ECF3] bg-white px-3.5 py-2 text-xs font-semibold text-slate-600 transition hover:border-[#2F6BFF] hover:text-[#2F6BFF]">
                    <Ic size={13} /> {l}
                  </button>
                ))}
              </div>
            </div>
            <div className="hidden items-end gap-4 md:flex">
              <div className="w-44 self-stretch overflow-hidden rounded-2xl">
                <img src={AIVORA_HERO} alt="Aivora" className="h-full w-full object-cover" />
              </div>
              <div className="w-52 self-center rounded-2xl border border-white bg-white/80 p-4 backdrop-blur">
                <p className="text-xs font-bold text-slate-900">Saya Aivora, siap membantu Anda & tim hari ini.</p>
                <div className="mt-3 space-y-2">
                  {CAPS.map((c) => (
                    <div key={c} className="flex items-start gap-2 text-[11px] text-slate-500"><span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-[#2F6BFF]" /> {c}</div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* quick actions */}
        <section>
          <h2 className="mb-4 text-lg font-bold text-slate-900">Mulai dengan cepat</h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            {QUICK.map((q) => (
              <button key={q.title} onClick={() => nav(q.to)} data-testid={`qa-${q.title}`}
                className="aivora-card aivora-card-hover flex flex-col items-center gap-3 p-4 text-center">
                <span className="flex h-12 w-12 items-center justify-center rounded-2xl" style={{ background: `${q.c}15`, color: q.c }}><q.icon size={22} /></span>
                <span className="text-xs font-bold text-slate-900">{q.title}</span>
                <span className="text-[11px] leading-tight text-slate-400">{q.desc}</span>
              </button>
            ))}
          </div>
        </section>

        {/* recent projects */}
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-bold text-slate-900">Proyek Terbaru</h2>
            <button onClick={() => nav("/workspace")} className="flex items-center gap-1 text-sm font-semibold text-[#2F6BFF]">Lihat Semua <ArrowRight size={14} /></button>
          </div>
          {projects.length === 0 ? (
            <button onClick={() => nav("/workspace")} data-testid="home-empty-task" className="aivora-card flex w-full flex-col items-center gap-2 p-8 text-center text-sm text-slate-400 hover:border-[#2F6BFF]">
              <Bot size={28} className="text-[#2F6BFF]" /> Belum ada proyek. Beri Aivora sebuah tujuan untuk dikerjakan.
            </button>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {projects.map((tk) => (
                <button key={tk.id} onClick={() => nav(`/workspace/${tk.id}`)} data-testid={`home-task-${tk.id}`}
                  className="aivora-card aivora-card-hover p-5 text-left">
                  <div className="flex items-start justify-between gap-3">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#EEF3FF] text-[#2F6BFF]"><Bot size={20} /></span>
                    <span className="rounded-full px-2.5 py-0.5 text-[11px] font-semibold capitalize" style={{ background: `${statusColor[tk.status]}18`, color: statusColor[tk.status] }}>{tk.status}</span>
                  </div>
                  <p className="mt-3 line-clamp-2 text-sm font-bold text-slate-900">{tk.goal}</p>
                  <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full" style={{ width: `${progress(tk)}%`, background: "linear-gradient(90deg,#2F6BFF,#7C3AED)" }} />
                  </div>
                  <p className="mt-1.5 text-right text-xs font-semibold text-slate-400">{progress(tk)}%</p>
                </button>
              ))}
            </div>
          )}
        </section>

        {/* recent documents */}
        {docs.length > 0 && (
          <section>
            <h2 className="mb-4 text-lg font-bold text-slate-900">Dokumen Terbaru</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {docs.map((tk) => (
                <button key={tk.id} onClick={() => nav(`/workspace/${tk.id}`)} className="aivora-card aivora-card-hover flex items-center gap-3 p-4 text-left">
                  <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#10B981]/12 text-[#10B981]"><FileCheck2 size={18} /></span>
                  <span className="min-w-0"><span className="block truncate text-sm font-semibold text-slate-900">{tk.goal}</span>
                    <span className="block text-xs text-slate-400">{new Date(tk.created_at).toLocaleDateString("id-ID")}</span></span>
                </button>
              ))}
            </div>
          </section>
        )}
      </div>

      {/* right rail */}
      <aside className="space-y-6">
        <div className="aivora-card p-5">
          <p className="text-sm font-bold text-slate-900">{dateStr}</p>
          <div className="mt-3 flex justify-between">
            {["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"].map((d, i) => {
              const day = new Date(now); day.setDate(now.getDate() - ((now.getDay() + 6) % 7) + i);
              const active = day.toDateString() === now.toDateString();
              return (
                <div key={d} className={`flex h-14 w-9 flex-col items-center justify-center rounded-xl text-xs ${active ? "btn-grad" : "text-slate-500"}`}>
                  <span className={active ? "text-white/80" : "text-slate-400"}>{d}</span>
                  <span className={`text-sm font-bold ${active ? "text-white" : "text-slate-700"}`}>{day.getDate()}</span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="aivora-card p-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-900">Jadwal Saya</h3>
            <button onClick={() => nav("/reminders")} className="text-xs font-semibold text-[#2F6BFF]">Lihat Semua</button>
          </div>
          {upcoming.length === 0 ? <p className="py-3 text-sm text-slate-400">Belum ada jadwal.</p> : upcoming.map((r) => (
            <div key={r.id} className="mb-2 flex items-start gap-3 rounded-xl bg-slate-50 p-3" data-testid={`home-rem-${r.id}`}>
              <Clock size={15} className="mt-0.5 text-[#F59E0B]" />
              <div className="min-w-0"><p className="truncate text-sm font-semibold text-slate-800">{r.title}</p>
                <p className="text-xs text-slate-400">{new Date(r.start_at).toLocaleString("id-ID", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</p></div>
            </div>
          ))}
        </div>

        <div className="aivora-card overflow-hidden p-5" style={{ background: "linear-gradient(135deg,#EEF3FF,#F3EEFF)" }}>
          <p className="flex items-center gap-2 text-sm font-bold text-slate-900"><Sparkles size={16} className="text-[#2F6BFF]" /> Ringkasan Kredit</p>
          <p className="mt-2 text-3xl font-extrabold grad-text">{user?.credits ?? 0}</p>
          <p className="text-xs text-slate-500">kredit tersedia</p>
          <button onClick={() => nav("/wallet")} data-testid="home-topup-btn" className="btn-grad mt-3 w-full rounded-xl py-2.5 text-sm">Isi Ulang</button>
        </div>
      </aside>
    </div>
  );
}
