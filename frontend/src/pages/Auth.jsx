import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Mail, Lock, Eye, EyeOff, ArrowRight, Globe, BarChart3, FileText, Users, Sparkles, MessageSquare, Video, MailCheck, KeyRound, Loader2, Gift } from "lucide-react";
import { Logo, BRAND_HERO, TAGLINE } from "../components/Logo";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import { useI18n } from "../i18n";
import { useNavigate } from "react-router-dom";
import { startGoogleLogin } from "./GoogleCallback";

const CHIPS = [
  { icon: BarChart3, label: "Analisis data" },
  { icon: FileText, label: "Buat dokumen" },
  { icon: Users, label: "Panggilan & notulen" },
  { icon: Sparkles, label: "Riset & insight" },
];
const CARDS = [
  { icon: MessageSquare, title: "Multi-Agen AI", desc: "Diskusi dengan berbagai agen AI sesuai kebutuhan Anda.", c: "#2F6BFF" },
  { icon: FileText, title: "Dokumen & Analisis", desc: "Buat, analisis, dan ringkas dokumen dengan AI.", c: "#7C3AED" },
  { icon: Video, title: "Panggilan Assistant", desc: "Pengingat, ringkasan, dan tindak lanjut otomatis.", c: "#22B8FF" },
];
const TITLES = { login: "Selamat Datang", register: "Buat Akun", forgot: "Lupa Password" };
const SUBTITLES = { login: `Masuk ke workspace Oryntix Anda · ${TAGLINE}`, register: "Daftar dan mulai bekerja bersama tim agen AI Anda.", forgot: "Masukkan email akun Anda — kami kirim tautan untuk membuat password baru." };

function PendingScreen({ pending, onResend, onBack }) {
  const reset = pending.kind === "reset";
  return (
    <div className="flex min-h-screen items-center justify-center bg-white p-6">
      <div className="w-full max-w-md text-center fade-up" data-testid={reset ? "reset-pending" : "verify-pending"}>
        <Logo size={40} />
        <span className="mx-auto mt-8 flex h-16 w-16 items-center justify-center rounded-full bg-[#EEF3FF] text-[#2F6BFF]"><MailCheck size={30} /></span>
        <h2 className="mt-6 text-2xl font-bold text-slate-900">Cek email Anda</h2>
        <p className="mt-2 text-sm text-slate-500">
          {reset ? <>Jika <b className="text-slate-800">{pending.email}</b> terdaftar, kami sudah mengirim tautan untuk mengatur ulang password. Tautan berlaku 1 jam.</>
            : <>Kami mengirim tautan verifikasi ke <b className="text-slate-800">{pending.email}</b>. Klik tautan tersebut untuk mengaktifkan akun dan masuk.</>}
        </p>
        {pending.mail_sent === false && <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-700" data-testid="verify-mail-warning">Email belum terkirim (server email bermasalah). Coba kirim ulang atau hubungi admin.</p>}
        <button onClick={onResend} className="mt-6 rounded-xl border border-[#E7ECF3] px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50" data-testid="verify-resend-btn">Kirim ulang tautan</button>
        <p className="mt-6 text-sm text-slate-500">{reset ? "Sudah ingat password?" : "Sudah verifikasi?"} <button className="font-semibold text-[#2F6BFF]" onClick={onBack} data-testid="verify-back-login">Masuk</button></p>
      </div>
    </div>
  );
}

export default function Auth() {
  const { login, register } = useAuth();
  const { t, lang, setLang } = useI18n();
  const nav = useNavigate();
  const [mode, setMode] = useState("login"); // login | register | forgot
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [name, setName] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [googleOn, setGoogleOn] = useState(false);
  const [gBusy, setGBusy] = useState(false);
  useEffect(() => { api.get("/auth/google/status").then((r) => setGoogleOn(!!r.data.enabled)).catch(() => setGoogleOn(false)); api.get("/auth/trial-info").then((r) => setTrial(r.data)).catch(() => {}); }, []);
  const [trial, setTrial] = useState(null);
  const googleLogin = async () => { setGBusy(true); try { await startGoogleLogin(); } catch (e) { toast.error(e?.response?.data?.detail || "Login Google gagal dimulai"); } finally { if (window.self !== window.top) setGBusy(false); } };
  const [pending, setPending] = useState(null); // {email, mail_sent, kind: verify|reset}
  const [unverified, setUnverified] = useState(false);
  const mismatch = mode === "register" && confirm.length > 0 && confirm !== password;

  const switchMode = (m) => { setMode(m); setConfirm(""); setUnverified(false); };

  const forgot = async (addr) => {
    const r = await api.post("/auth/forgot-password", { email: addr, app_url: window.location.origin });
    setPending({ email: addr, mail_sent: r.data.mail_sent !== false, kind: "reset" });
  };

  const resend = async () => {
    const addr = pending?.email || email;
    try {
      if (pending?.kind === "reset") { await forgot(addr); toast.success("Tautan reset dikirim ulang"); return; }
      const r = await api.post("/auth/resend-verification", { email: addr, app_url: window.location.origin });
      setPending({ email: addr, mail_sent: r.data.mail_sent !== false, kind: "verify" }); toast.success("Tautan verifikasi dikirim ulang");
    } catch (err) { toast.error(err?.response?.data?.detail || "Gagal mengirim ulang"); }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (mode === "register" && password !== confirm) { toast.error("Ulangi password tidak sama"); return; }
    setBusy(true); setUnverified(false);
    try {
      if (mode === "forgot") { await forgot(email); return; }
      if (mode === "register") {
        const r = await register(email, password, name);
        if (r.pending_verification) { setPending({ email: r.email, mail_sent: r.mail_sent, kind: "verify" }); return; }
        toast.success("Akun berhasil dibuat"); nav(r.user?.onboarded ? "/home" : "/onboarding"); return;
      }
      const u = await login(email, password);
      toast.success("Selamat datang kembali");
      const after = sessionStorage.getItem("after_login"); sessionStorage.removeItem("after_login");
      nav(after || (u.onboarded ? "/home" : "/onboarding"));
    } catch (err) {
      const d = err?.response?.data?.detail;
      if (d?.code === "unverified") { setUnverified(true); toast.error(d.message); return; }
      toast.error((typeof d === "string" && d) || d?.message || "Terjadi kesalahan");
    } finally { setBusy(false); }
  };

  if (pending) return <PendingScreen pending={pending} onResend={resend} onBack={() => { setPending(null); switchMode("login"); }} />;

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
              Oryntix membantu Anda berdiskusi, menganalisis, membuat dokumen, hingga menyelesaikan pekerjaan bersama tim agen AI — lewat chat maupun panggilan suara.
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

      {/* right panel */}
      <div className="flex w-full items-center justify-center p-6 sm:p-10 lg:w-[480px] xl:w-[540px]">
        <div className="w-full max-w-sm fade-up">
          <div className="mb-8 flex items-center justify-between">
            <Logo size={40} />
            <button onClick={() => setLang(lang === "id" ? "en" : "id")} data-testid="auth-lang-toggle"
              className="flex items-center gap-1.5 rounded-full border border-[#E7ECF3] bg-white px-3 py-1.5 text-xs font-semibold text-slate-600">
              <Globe size={14} /> {lang.toUpperCase()}
            </button>
          </div>

          <h2 className="text-3xl font-bold tracking-tight text-slate-900" data-testid="auth-title">{TITLES[mode]}</h2>
          <p className="mt-1.5 text-sm text-slate-500">{SUBTITLES[mode]}</p>
          {mode === "register" && trial && <p className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-[#EEF3FF] px-3 py-1.5 text-xs font-semibold text-[#2F6BFF]" data-testid="auth-trial-info"><Gift size={13} /> Gratis {trial.trial_credits} kredit · {trial.trial_days} hari percobaan · {trial.trial_daily_limit} kredit/hari</p>}

          {mode !== "forgot" && googleOn && (<>
            <button type="button" onClick={googleLogin} disabled={gBusy} className="mt-6 flex w-full items-center justify-center gap-3 rounded-xl border border-[#E7ECF3] bg-white py-3 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-60" data-testid="auth-google-btn">
              {gBusy ? <Loader2 size={18} className="animate-spin" /> : <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.7 1.2 9.2 3.6l6.9-6.9C35.9 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l8 6.2C12.5 13.6 17.8 9.5 24 9.5z"/><path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.5 5.8c4.4-4.1 7.1-10.1 7.1-17.5z"/><path fill="#FBBC05" d="M10.6 28.6A14.5 14.5 0 0 1 9.5 24c0-1.6.3-3.1.8-4.6l-8-6.2A24 24 0 0 0 0 24c0 3.9.9 7.5 2.6 10.8l8-6.2z"/><path fill="#34A853" d="M24 48c6.3 0 11.7-2.1 15.6-5.7l-7.5-5.8c-2.1 1.4-4.8 2.3-8.1 2.3-6.2 0-11.5-4.1-13.4-9.8l-8 6.2C6.5 42.6 14.6 48 24 48z"/></svg>}
              {mode === "login" ? "Masuk dengan Google" : "Daftar dengan Google"}
            </button>
            <div className="mt-5 flex items-center gap-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400"><span className="h-px flex-1 bg-[#E7ECF3]" />atau dengan email<span className="h-px flex-1 bg-[#E7ECF3]" /></div>
          </>)}

          <form onSubmit={submit} className={`${mode !== "forgot" && googleOn ? "mt-5" : "mt-7"} space-y-4`}>
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
            {mode !== "forgot" && (
              <div className="relative">
                <Lock size={17} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                <input className="input-dark px-11" type={show ? "text" : "password"} placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} data-testid="auth-password-input" />
                <button type="button" onClick={() => setShow(!show)} className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400" data-testid="auth-toggle-show">{show ? <EyeOff size={17} /> : <Eye size={17} />}</button>
              </div>
            )}
            {mode === "register" && (
              <div>
                <div className="relative">
                  <KeyRound size={17} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input className={`input-dark pl-11 ${mismatch ? "border-[#EF4444]" : ""}`} type={show ? "text" : "password"} placeholder="Ulangi Password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required minLength={6} data-testid="auth-confirm-input" />
                </div>
                {mismatch && <p className="mt-1.5 text-xs font-medium text-[#EF4444]" data-testid="auth-confirm-error">Password tidak sama.</p>}
              </div>
            )}

            {mode === "login" && (
              <div className="flex items-center justify-between text-sm">
                <label className="flex items-center gap-2 text-slate-500"><input type="checkbox" className="h-4 w-4 rounded accent-[#2F6BFF]" defaultChecked /> Ingat saya</label>
                <button type="button" className="font-semibold text-[#2F6BFF] hover:underline" onClick={() => switchMode("forgot")} data-testid="auth-forgot-btn">Lupa password?</button>
              </div>
            )}

            {unverified && (
              <div className="flex items-center justify-between gap-2 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800" data-testid="login-unverified">
                <span>Email belum diverifikasi.</span>
                <button type="button" onClick={resend} className="font-bold text-[#2F6BFF]" data-testid="login-resend-btn">Kirim ulang tautan</button>
              </div>
            )}

            <button className="btn-grad flex w-full items-center justify-center gap-2 rounded-xl py-3.5 text-sm" disabled={busy || mismatch} data-testid="auth-submit-btn">
              {busy ? "..." : mode === "login" ? "Masuk" : mode === "register" ? "Daftar" : "Kirim tautan reset"} <ArrowRight size={17} />
            </button>
          </form>

          <p className="mt-7 text-center text-sm text-slate-500">
            {mode === "forgot" ? (
              <button className="font-semibold text-[#2F6BFF]" data-testid="auth-back-login" onClick={() => switchMode("login")}>Kembali ke halaman masuk</button>
            ) : (<>
              {mode === "login" ? "Belum punya akun?" : "Sudah punya akun?"}{" "}
              <button className="font-semibold text-[#2F6BFF]" data-testid="auth-toggle-btn" onClick={() => switchMode(mode === "login" ? "register" : "login")}>
                {mode === "login" ? "Daftar sekarang" : "Masuk"}
              </button>
            </>)}
          </p>
          <p className="mt-4 text-center text-[11px] text-slate-400" data-testid="auth-legal-links">Dengan masuk atau mendaftar, Anda menyetujui <a href="/terms" target="_blank" rel="noreferrer" className="font-semibold text-[#2F6BFF] hover:underline" data-testid="auth-terms-link">Ketentuan Layanan</a> dan <a href="/privacy" target="_blank" rel="noreferrer" className="font-semibold text-[#2F6BFF] hover:underline" data-testid="auth-privacy-link">Kebijakan Privasi</a>.</p>
        </div>
      </div>
    </div>
  );
}
