import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Loader2, MailCheck, MailX } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Logo } from "../components/Logo";
import { useAuth } from "../context/AuthContext";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { applyAuth } = useAuth();
  const [state, setState] = useState("loading"); // loading|ok|error
  const [error, setError] = useState("");
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return; ran.current = true;
    const token = params.get("token");
    if (!token) { setState("error"); setError("Tautan tidak lengkap"); return; }
    api.get(`/auth/verify-email?token=${encodeURIComponent(token)}`)
      .then((r) => { const u = applyAuth(r.data); setState("ok"); toast.success("Email terverifikasi — selamat datang!"); setTimeout(() => nav(u.onboarded ? "/home" : "/onboarding", { replace: true }), 1200); })
      .catch((e) => { setState("error"); setError(e?.response?.data?.detail || "Tautan verifikasi tidak valid"); });
    // eslint-disable-next-line
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center bg-white p-6">
      <div className="w-full max-w-md text-center fade-up" data-testid="verify-email-page">
        <Logo size={40} />
        {state === "loading" && <p className="mt-8 flex items-center justify-center gap-2 text-sm text-slate-500"><Loader2 size={16} className="animate-spin" /> Memverifikasi email...</p>}
        {state === "ok" && (<>
          <span className="mx-auto mt-8 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-50 text-emerald-600"><MailCheck size={30} /></span>
          <h2 className="mt-6 text-2xl font-bold text-slate-900" data-testid="verify-success">Email terverifikasi</h2>
          <p className="mt-2 text-sm text-slate-500">Mengarahkan Anda ke workspace...</p>
        </>)}
        {state === "error" && (<>
          <span className="mx-auto mt-8 flex h-16 w-16 items-center justify-center rounded-full bg-red-50 text-[#EF4444]"><MailX size={30} /></span>
          <h2 className="mt-6 text-2xl font-bold text-slate-900" data-testid="verify-error">Verifikasi gagal</h2>
          <p className="mt-2 text-sm text-slate-500">{error}</p>
          <button onClick={() => nav("/")} className="btn-grad mt-6 rounded-xl px-5 py-2.5 text-sm" data-testid="verify-go-login">Ke halaman masuk</button>
        </>)}
      </div>
    </div>
  );
}
