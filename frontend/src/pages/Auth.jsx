import React, { useState } from "react";
import { toast } from "sonner";
import { Mail, Lock, Eye, EyeOff, ArrowRight, Globe, BarChart3, FileText, Users, Sparkles, MessageSquare, Video } from "lucide-react";
import { Logo, BRAND_HERO, TAGLINE } from "../components/Logo";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n";
import { useNavigate } from "react-router-dom";

const CHIPS = [
  { icon: BarChart3, label: "Analisis data" },
  { icon: FileText, label: "Buat dokumen" },
  { icon: Users, label: "Meeting & notulen" },
  { icon: Sparkles, label: "Riset & insight" },
];
const CARDS = [
  { icon: MessageSquare, title: "Multi-Agen AI", desc: "Diskusi dengan berbagai agen AI sesuai kebutuhan Anda.", c: "#2F6BFF" },
  { icon: FileText, title: "Dokumen & Analisis", desc: "Buat, analisis, dan ringkas dokumen dengan AI.", c: "#7C3AED" },
  { icon: Video, title: "Meeting Assistant", desc: "Pengingat, ringkasan, dan tindak lanjut otomatis.", c: "#22B8FF" },
];

export default function Auth() {
  const { login, register } = useAuth();
  const { t, lang, setLang } = useI18n();
  const nav = useNavigate();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const u = mode === "login" ? await login(email, password) : await register(email, password, name);
      toast.success(mode === "login" ? "Selamat datang kembali" : "Akun berhasil dibuat");
      nav(u.onboarded ? "/home" : "/onboarding");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Terjadi kesalahan");
    } finally { setBusy(false); }
  };

  return (
    <div className="flex min-h-screen bg-white">
      {/* left hero */}
      <div className="relative hidden flex-1 overflow-hidden lg:block sidebar-dark">
        <img src={BRAND_HERO} alt="" className="hero-float pointer-events-none absolute -right-24 top-1/2 w-[520px] -translate-y-1/2 opacity-90 drop-shadow-2xl xl:w-[600px]" />
        <div className="absolute inset-0" style={{ background: "linear-gradient(100deg, rgba(10,17,40,.96) 0%, rgba(10,17,40,.75) 45%, rgba(10,17,40,.15) 100%)" }} />
        <div className="relative z-10 flex h-full flex-col justify-between p-10 xl:p-14">
          <div className="flex items-center justify-between">
            <Logo size={36} light />
            <span className="hidden text-sm font-medium tracking-wide text-white/60 xl:block">{TAGLINE}</span>
          </div>

          <div className="max-w-xl">
            <h1 className="text-4xl font-bold leading-tight tracking-tight text-white xl:text-5xl">
              Intelligence, <span className="grad-text">Orchestrated.</span>
            </h1>
            <p className="mt-4 max-w-md text-base text-white/75">
              Oryntix membantu Anda berdiskusi, menganalisis, membuat dokumen, hingga menyelesaikan pekerjaan bersama tim agen AI — lewat chat maupun meeting suara.
            </p>
            <div className="mt-6 flex items-center gap-3">
              <div className="flex flex-wrap gap-2">
                {CHIPS.map((c) => (
                  <span key={c.label} className="flex items-center gap-1.5 rounded-full border border-white/20 bg-white/10 px-3 py-1.5 text-xs font-medium text-white/90 backdrop-blur">
                    <c.icon size={13} /> {c.label}
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            {CARDS.map((c) => (
              <div key={c.title} className="rounded-2xl border border-white/15 bg-white/10 p-4 backdrop-blur">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg text-white" style={{ background: c.c }}><c.icon size={18} /></span>
                <p className="mt-3 text-sm font-bold text-white">{c.title}</p>
                <p className="mt-1 text-xs leading-relaxed text-white/70">{c.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* right login panel */}
      <div className="flex w-full items-center justify-center p-6 sm:p-10 lg:w-[480px] xl:w-[540px]">
        <div className="w-full max-w-sm fade-up">
          <div className="mb-8 flex items-center justify-between">
            <Logo size={40} />
            <button onClick={() => setLang(lang === "id" ? "en" : "id")} data-testid="auth-lang-toggle"
              className="flex items-center gap-1.5 rounded-full border border-[#E7ECF3] bg-white px-3 py-1.5 text-xs font-semibold text-slate-600">
              <Globe size={14} /> {lang.toUpperCase()}
            </button>
          </div>

          <h2 className="text-3xl font-bold tracking-tight text-slate-900">Selamat Datang</h2>
          <p className="mt-1.5 text-sm text-slate-500">Masuk ke workspace Oryntix Anda · {TAGLINE}</p>

          <form onSubmit={submit} className="mt-7 space-y-4">
            {mode === "register" && (
              <div className="relative">
                <Users size={17} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                <input className="input-dark pl-11" placeholder={t("auth.name")} value={name} onChange={(e) => setName(e.target.value)} data-testid="auth-name-input" />
              </div>
            )}
            <div className="relative">
              <Mail size={17} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
              <input className="input-dark pl-11" type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required data-testid="auth-email-input" />
            </div>
            <div className="relative">
              <Lock size={17} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
              <input className="input-dark px-11" type={show ? "text" : "password"} placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} data-testid="auth-password-input" />
              <button type="button" onClick={() => setShow(!show)} className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400">{show ? <EyeOff size={17} /> : <Eye size={17} />}</button>
            </div>

            <div className="flex items-center justify-between text-sm">
              <label className="flex items-center gap-2 text-slate-500"><input type="checkbox" className="h-4 w-4 rounded accent-[#2F6BFF]" defaultChecked /> Ingat saya</label>
              <span className="font-semibold text-[#2F6BFF]">Lupa password?</span>
            </div>

            <button className="btn-grad flex w-full items-center justify-center gap-2 rounded-xl py-3.5 text-sm" disabled={busy} data-testid="auth-submit-btn">
              {busy ? "..." : (mode === "login" ? "Masuk" : "Daftar")} <ArrowRight size={17} />
            </button>
          </form>

          <div className="my-6 flex items-center gap-3 text-xs text-slate-400">
            <div className="h-px flex-1 bg-[#E7ECF3]" /> atau masuk dengan <div className="h-px flex-1 bg-[#E7ECF3]" />
          </div>
          <button onClick={() => toast.message("Login Google sedang disiapkan — menunggu Client ID/Secret Google OAuth")} data-testid="social-google"
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-[#E7ECF3] bg-white py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50">
            <span className="text-base font-bold text-[#4285F4]">G</span> Masuk dengan Google
          </button>

          <p className="mt-7 text-center text-sm text-slate-500">
            {mode === "login" ? "Belum punya akun?" : "Sudah punya akun?"}{" "}
            <button className="font-semibold text-[#2F6BFF]" data-testid="auth-toggle-btn" onClick={() => setMode(mode === "login" ? "register" : "login")}>
              {mode === "login" ? "Daftar sekarang" : "Masuk"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
