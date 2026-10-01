import React, { useState } from "react";
import { toast } from "sonner";
import { Logo } from "../components/Logo";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n";
import { useNavigate } from "react-router-dom";

export default function Auth() {
  const { login, register } = useAuth();
  const { t, lang, setLang } = useI18n();
  const nav = useNavigate();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      let u;
      if (mode === "login") u = await login(email, password);
      else u = await register(email, password, name);
      toast.success(mode === "login" ? "Welcome back" : "Account created");
      nav(u.onboarded ? "/home" : "/onboarding");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Something went wrong");
    } finally { setBusy(false); }
  };

  return (
    <div className="flex min-h-screen mesh-bg">
      {/* left hero */}
      <div className="relative hidden flex-1 flex-col justify-between overflow-hidden p-12 lg:flex">
        <Logo size={40} />
        <div className="relative z-10">
          <h1 className="max-w-xl text-5xl font-extrabold leading-tight tracking-tight text-white">
            Asisten AI personal yang <span className="grad-text">benar-benar bekerja</span> untuk Anda.
          </h1>
          <p className="mt-5 max-w-md text-lg text-slate-400">
            Buat persona Anda sendiri, delegasikan tugas ke tim agent, dan dapatkan hasil nyata — semua dalam satu tempat.
          </p>
          <div className="mt-8 flex gap-6 text-sm text-slate-400">
            <div><div className="text-2xl font-bold text-white">Persona</div>buatan Anda</div>
            <div><div className="text-2xl font-bold text-white">Multi-Agent</div>kolaborasi</div>
            <div><div className="text-2xl font-bold text-white">Workspace</div>hasil kerja</div>
          </div>
        </div>
        <div className="absolute -right-24 top-1/4 h-96 w-96 rounded-full" style={{ background: "radial-gradient(circle, rgba(124,58,237,0.4), transparent 70%)" }} />
        <p className="relative z-10 text-sm text-slate-500">{t("auth.tagline")}</p>
      </div>

      {/* right form */}
      <div className="flex w-full items-center justify-center p-6 lg:w-[520px]">
        <div className="w-full max-w-sm fade-up">
          <div className="mb-6 flex items-center justify-between lg:hidden"><Logo /></div>
          <div className="mb-6 flex items-center justify-end gap-1 rounded-xl bg-[#0e1830] p-1 text-xs w-24 ml-auto">
            {["id", "en"].map((l) => (
              <button key={l} data-testid={`auth-lang-${l}`} onClick={() => setLang(l)}
                className={`flex-1 rounded-lg px-2 py-1.5 font-semibold uppercase ${lang === l ? "btn-grad" : "text-slate-400"}`}>{l}</button>
            ))}
          </div>
          <h2 className="text-3xl font-extrabold text-white">{t("auth.welcome")}</h2>
          <p className="mt-2 text-sm text-slate-400">{mode === "login" ? t("auth.login") : t("auth.register")}</p>

          <form onSubmit={submit} className="mt-8 space-y-4">
            {mode === "register" && (
              <input className="input-dark" placeholder={t("auth.name")} value={name} onChange={(e) => setName(e.target.value)} data-testid="auth-name-input" />
            )}
            <input className="input-dark" type="email" placeholder={t("auth.email")} value={email} onChange={(e) => setEmail(e.target.value)} required data-testid="auth-email-input" />
            <input className="input-dark" type="password" placeholder={t("auth.password")} value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} data-testid="auth-password-input" />
            <button className="btn-grad w-full rounded-xl py-3.5 text-sm" disabled={busy} data-testid="auth-submit-btn">
              {busy ? "..." : (mode === "login" ? t("auth.login") : t("auth.register"))}
            </button>
          </form>

          <p className="mt-6 text-center text-sm text-slate-400">
            {mode === "login" ? t("auth.noAccount") : t("auth.hasAccount")}{" "}
            <button className="font-semibold text-[#00D1FF]" data-testid="auth-toggle-btn"
              onClick={() => setMode(mode === "login" ? "register" : "login")}>
              {mode === "login" ? t("auth.register") : t("auth.login")}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
