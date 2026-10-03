import React, { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Lock, KeyRound, Eye, EyeOff, ArrowRight, MailX } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Logo } from "../components/Logo";
import { useAuth } from "../context/AuthContext";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { applyAuth } = useAuth();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const mismatch = confirm.length > 0 && confirm !== password;

  const submit = async (e) => {
    e.preventDefault();
    if (password !== confirm) { toast.error("Ulangi password tidak sama"); return; }
    setBusy(true); setError("");
    try {
      const r = await api.post("/auth/reset-password", { token, password });
      const u = applyAuth(r.data);
      toast.success("Password berhasil diubah");
      nav(u.onboarded ? "/home" : "/onboarding", { replace: true });
    } catch (err) { setError(err?.response?.data?.detail || "Tautan reset tidak valid"); }
    finally { setBusy(false); }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-white p-6">
      <div className="w-full max-w-sm fade-up" data-testid="reset-password-page">
        <Logo size={40} />
        {!token || error ? (
          <div className="mt-8 text-center">
            <span className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-red-50 text-[#EF4444]"><MailX size={30} /></span>
            <h2 className="mt-6 text-2xl font-bold text-slate-900" data-testid="reset-error">Tautan tidak valid</h2>
            <p className="mt-2 text-sm text-slate-500">{error || "Tautan reset tidak lengkap."} Minta tautan baru dari halaman masuk.</p>
            <button onClick={() => nav("/")} className="btn-grad mt-6 rounded-xl px-5 py-2.5 text-sm" data-testid="reset-go-login">Ke halaman masuk</button>
          </div>
        ) : (
          <form onSubmit={submit} className="mt-8 space-y-4">
            <h2 className="text-2xl font-bold tracking-tight text-slate-900">Buat password baru</h2>
            <p className="text-sm text-slate-500">Minimal 6 karakter. Setelah disimpan Anda langsung masuk.</p>
            <div className="relative">
              <Lock size={17} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
              <input className="input-dark px-11" type={show ? "text" : "password"} placeholder="Password baru" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} data-testid="reset-password-input" />
              <button type="button" onClick={() => setShow(!show)} className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400">{show ? <EyeOff size={17} /> : <Eye size={17} />}</button>
            </div>
            <div>
              <div className="relative">
                <KeyRound size={17} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                <input className={`input-dark pl-11 ${mismatch ? "border-[#EF4444]" : ""}`} type={show ? "text" : "password"} placeholder="Ulangi password baru" value={confirm} onChange={(e) => setConfirm(e.target.value)} required minLength={6} data-testid="reset-confirm-input" />
              </div>
              {mismatch && <p className="mt-1.5 text-xs font-medium text-[#EF4444]" data-testid="reset-confirm-error">Password tidak sama.</p>}
            </div>
            <button className="btn-grad flex w-full items-center justify-center gap-2 rounded-xl py-3.5 text-sm" disabled={busy || mismatch} data-testid="reset-submit-btn">
              {busy ? "..." : "Simpan password"} <ArrowRight size={17} />
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
