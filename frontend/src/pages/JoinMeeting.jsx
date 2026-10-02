import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Gavel, Loader2, UserPlus, LogIn } from "lucide-react";
import { toast } from "sonner";
import { api, setAuthToken } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Mark } from "../components/Logo";

export default function JoinMeeting() {
  const { token } = useParams();
  const nav = useNavigate();
  const { user, refreshUser } = useAuth();
  const [info, setInfo] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "" });

  useEffect(() => {
    api.get(`/invites/${token}`).then((r) => setInfo(r.data)).catch(() => setErr("Undangan tidak valid atau sudah kedaluwarsa."));
  }, [token]);

  const joinExisting = async () => {
    setBusy(true);
    try { const r = await api.post(`/invites/${token}/join`); toast.success("Berhasil bergabung"); nav(`/chat/${r.data.conversation_id}`); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal bergabung"); } finally { setBusy(false); }
  };

  const registerJoin = async (e) => {
    e.preventDefault();
    if (!form.name || !form.email || form.password.length < 6) { toast.error("Lengkapi nama, email & kata sandi (min 6)"); return; }
    setBusy(true);
    try {
      const r = await api.post(`/invites/${token}/register`, form);
      setAuthToken(r.data.access_token);
      await refreshUser();
      toast.success("Akun dibuat & bergabung ke panggilan");
      nav(`/chat/${r.data.conversation_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mendaftar"); } finally { setBusy(false); }
  };

  return (
    <div className="flex min-h-screen items-center justify-center mesh-bg p-4" data-testid="join-page">
      <div className="w-full max-w-md rounded-3xl border border-[#E7ECF3] bg-white p-8 shadow-2xl fade-up">
        <div className="mb-4 flex items-center gap-2"><Mark size={30} /><span className="text-lg font-bold text-slate-900">Oryntix</span></div>
        {err ? (
          <p className="text-sm text-[#EF4444]">{err}</p>
        ) : !info ? (
          <div className="flex items-center gap-2 text-slate-400"><Loader2 size={16} className="animate-spin" /> Memuat undangan...</div>
        ) : (
          <>
            <span className="flex items-center gap-2 rounded-full bg-[#EEF3FF] px-3 py-1 text-xs font-semibold text-[#2F6BFF]"><Gavel size={13} /> Undangan Panggilan</span>
            <h1 className="mt-3 text-2xl font-bold text-slate-900">{info.title}</h1>
            <p className="mt-1 text-sm text-slate-500">Workspace {info.workspace} · {info.members?.length || 0} asisten AI</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {(info.members || []).map((m, i) => <span key={i} className="rounded-full border border-[#E7ECF3] px-3 py-1 text-xs text-slate-600">{m.name || "Asisten"}</span>)}
            </div>

            {user ? (
              <button onClick={joinExisting} disabled={busy} data-testid="join-existing-btn" className="btn-grad mt-6 flex w-full items-center justify-center gap-2 rounded-xl py-3 text-sm">
                {busy ? <Loader2 size={16} className="animate-spin" /> : <LogIn size={16} />} Gabung sebagai {user.name}
              </button>
            ) : (
              <form onSubmit={registerJoin} className="mt-6 space-y-3" data-testid="join-register-form">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Buat akun untuk bergabung</p>
                <input className="input-dark py-2.5" placeholder="Nama" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="join-name" />
                <input className="input-dark py-2.5" type="email" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="join-email" />
                <input className="input-dark py-2.5" type="password" placeholder="Kata sandi (min 6)" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="join-password" />
                <button disabled={busy} data-testid="join-register-btn" className="btn-grad flex w-full items-center justify-center gap-2 rounded-xl py-3 text-sm">
                  {busy ? <Loader2 size={16} className="animate-spin" /> : <UserPlus size={16} />} Daftar & Gabung
                </button>
              </form>
            )}
          </>
        )}
      </div>
    </div>
  );
}
