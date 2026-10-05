import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Logo } from "../components/Logo";

// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
export const googleRedirectUri = () => window.location.origin + "/auth/google";

export async function startGoogleLogin() {
  const r = await api.post("/auth/google/start", { redirect_uri: googleRedirectUri() });
  if (window.self !== window.top) { window.open(r.data.authorization_url, "_blank"); return; }  // Google blocks its login page inside iframes (e.g. preview panel)
  window.location.href = r.data.authorization_url;
}

// Google sends the browser back here with ?code&state; we hand both to the backend and receive our own JWT.
export default function GoogleCallback() {
  const nav = useNavigate();
  const { applyAuth } = useAuth();
  const [error, setError] = useState("");
  const ran = useRef(false);
  useEffect(() => {
    if (ran.current) return; ran.current = true;
    const p = new URLSearchParams(window.location.search);
    if (p.get("error") || !p.get("code") || !p.get("state")) { setError(p.get("error") === "access_denied" ? "Anda membatalkan login Google." : "Respons Google tidak lengkap."); return; }
    api.post("/auth/google/exchange", { code: p.get("code"), state: p.get("state"), redirect_uri: googleRedirectUri() })
      .then((r) => { const u = applyAuth(r.data); toast.success(r.data.created ? "Akun Oryntix dibuat dengan Google — selamat datang!" : "Masuk dengan Google berhasil"); nav(u.onboarded ? "/home" : "/onboarding", { replace: true }); })
      .catch((e) => setError(e?.response?.data?.detail || "Login Google gagal"));
  }, [applyAuth, nav]);
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#F8FAFC] p-6" data-testid="google-callback-page">
      <Logo size={36} />
      {error ? (
        <div className="mt-6 max-w-sm text-center">
          <AlertTriangle size={28} className="mx-auto text-[#EF4444]" />
          <p className="mt-3 text-sm font-semibold text-slate-800" data-testid="google-callback-error">{error}</p>
          <button onClick={() => nav("/", { replace: true })} className="btn-grad mt-5 rounded-xl px-5 py-2.5 text-sm" data-testid="google-callback-back">Kembali ke halaman masuk</button>
        </div>
      ) : <p className="mt-6 flex items-center gap-2 text-sm text-slate-500" data-testid="google-callback-loading"><Loader2 size={16} className="animate-spin" /> Menyelesaikan login Google…</p>}
    </div>
  );
}
