import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { Bot, MessageSquare, Clapperboard, Phone, Plug, X, ChevronRight, ChevronLeft, Sparkles } from "lucide-react";

const KEY = "oryntix_tour_done";
export const tourDone = () => localStorage.getItem(KEY) === "1";
export const openTour = () => window.dispatchEvent(new Event("oryntix:tour"));

// 5-step welcome tour distilled from the User Manual; shown once per browser, replayable from the Help (?) button.
const STEPS = [
  { icon: Bot, title: "Buat asisten pertamamu", body: "Beri nama, kepribadian, suara, dan pilih model AI. Klik Buat Potret untuk foto asisten, lalu tambahkan Pengetahuan agar jawabannya sesuai konteksmu.", cta: "Buka AI Agents", href: "/personas" },
  { icon: MessageSquare, title: "Ngobrol & minta gambar", body: "Ketik apa adanya: \"buatkan logo kedai kopi\" atau \"render foto realistis kucing\". Gambar muncul langsung di chat; bilang \"ubah jadi kartun\" untuk mengeditnya. Klik gambar untuk tampilan besar.", cta: "Buka Chat", href: "/chat" },
  { icon: Clapperboard, title: "Video & dokumen", body: "Hubungkan Google Drive, lalu minta \"video 8 detik versi portrait untuk Reels\". Pilih Seedance 2.0/2.5, resolusi, dan suara — harga kredit tampil di tombol. Dokumen Word/Excel/PPT juga bisa diminta.", cta: "Hubungkan Drive", href: "/integrations" },
  { icon: Phone, title: "Panggilan suara realtime", body: "Tekan ikon telepon di chat untuk bicara langsung dengan asisten (boleh menyela). Buat grup untuk rapat bersama beberapa asisten & teman, lengkap dengan notulen.", cta: "Coba di Chat", href: "/chat" },
  { icon: Plug, title: "Ruang Kerja, pengingat & kredit", body: "Katakan \"tugaskan ke Rio: susun laporan Q3\" untuk tugas multi-langkah. Atur pengingat yang menelepon kamu. Pantau saldo kredit di kanan atas — titik hijau berarti realtime terhubung.", cta: "Lihat Ruang Kerja", href: "/workspace" },
];

export function WelcomeTour({ user }) {
  const [open, setOpen] = useState(false);
  const [i, setI] = useState(0);
  const nav = useNavigate();
  useEffect(() => { if (user && !tourDone()) { const t = setTimeout(() => setOpen(true), 900); return () => clearTimeout(t); } return undefined; }, [user]);
  useEffect(() => { const on = () => { setI(0); setOpen(true); }; window.addEventListener("oryntix:tour", on); return () => window.removeEventListener("oryntix:tour", on); }, []);
  if (!open) return null;
  const close = () => { localStorage.setItem(KEY, "1"); setOpen(false); };
  const s = STEPS[i]; const Icon = s.icon; const last = i === STEPS.length - 1;
  return createPortal(
    <div className="fixed inset-0 z-[110] flex items-end justify-center p-4 sm:items-center" data-testid="welcome-tour">
      <div className="absolute inset-0 bg-slate-900/50 backdrop-blur-[2px]" onClick={close} />
      <div className="relative w-full max-w-lg overflow-hidden rounded-3xl border border-[#E7ECF3] bg-white shadow-2xl fade-up">
        <div className="flex items-center justify-between bg-[#2F6BFF] px-6 py-4 text-white">
          <span className="flex items-center gap-2 text-sm font-bold"><Sparkles size={16} /> Tur singkat Oryntix</span>
          <span className="text-xs opacity-80" data-testid="tour-step-counter">Langkah {i + 1} dari {STEPS.length}</span>
          <button onClick={close} aria-label="Tutup tur" data-testid="tour-close" className="rounded-full p-1 hover:bg-white/15"><X size={18} /></button>
        </div>
        <div className="px-6 py-6">
          <div className="flex items-start gap-4">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#EEF3FF] text-[#2F6BFF]"><Icon size={24} /></span>
            <div>
              <h3 className="text-lg font-bold text-slate-900" data-testid="tour-step-title">{s.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{s.body}</p>
              <button onClick={() => { close(); nav(s.href); }} data-testid="tour-step-cta" className="mt-3 text-sm font-semibold text-[#2F6BFF] hover:underline">{s.cta} →</button>
            </div>
          </div>
          <div className="mt-6 flex items-center justify-between">
            <div className="flex gap-1.5" data-testid="tour-dots">{STEPS.map((_, k) => <button key={k} onClick={() => setI(k)} aria-label={`Langkah ${k + 1}`} className={`h-2 rounded-full transition-all ${k === i ? "w-6 bg-[#2F6BFF]" : "w-2 bg-slate-200 hover:bg-slate-300"}`} />)}</div>
            <div className="flex items-center gap-2">
              {i > 0 && <button onClick={() => setI(i - 1)} data-testid="tour-prev" className="flex items-center gap-1 rounded-full px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-100"><ChevronLeft size={16} /> Kembali</button>}
              {!last && <button onClick={close} data-testid="tour-skip" className="rounded-full px-3 py-2 text-sm font-semibold text-slate-500 hover:bg-slate-100">Lewati</button>}
              <button onClick={() => (last ? close() : setI(i + 1))} data-testid="tour-next" className="flex items-center gap-1 rounded-full bg-[#2F6BFF] px-4 py-2 text-sm font-bold text-white hover:bg-[#2558d6]">{last ? "Mulai pakai Oryntix" : "Selanjutnya"} {!last && <ChevronRight size={16} />}</button>
            </div>
          </div>
        </div>
      </div>
    </div>, document.body);
}
