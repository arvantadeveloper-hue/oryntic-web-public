import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Loader2, Users, Check, X, KeyRound, User as UserIcon, LogIn } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Logo } from "../components/Logo";
import { useAuth } from "../context/AuthContext";

// Team invitation landing page: new users create a password; existing users log in (or are already logged in) and accept/reject.
export default function InvitePage() {
  const { token } = useParams();
  const nav = useNavigate();
  const { user, loading, applyAuth, logout } = useAuth();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ name: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null); // joined|rejected

  useEffect(() => {
    api.get(`/team/invites/by-token/${token}`).then((r) => setInfo(r.data)).catch((e) => setError(e?.response?.data?.detail || "Undangan tidak valid"));
  }, [token]);

  const accept = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/team/invites/by-token/${token}/accept`, info.existing_user ? {} : form);
      applyAuth(r.data); setDone("joined");
      toast.success(`Anda bergabung ke workspace ${info.workspace_name}`);
      setTimeout(() => nav("/home", { replace: true }), 1200);
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error((typeof d === "string" && d) || d?.message || "Gagal menerima undangan");
    } finally { setBusy(false); }
  };

  const reject = async () => {
    setBusy(true);
    try { await api.post(`/team/invites/by-token/${token}/reject`); setDone("rejected"); toast.message("Undangan ditolak"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menolak"); } finally { setBusy(false); }
  };

  const wrongAccount = info?.existing_user && user && user.email !== info.email;
  const needLogin = info?.existing_user && !user;

  return (
    <div className="flex min-h-screen items-center justify-center bg-white p-6">
      <div className="w-full max-w-md fade-up" data-testid="invite-page">
        <Logo size={40} />
        {!info && !error && <p className="mt-8 flex items-center gap-2 text-sm text-slate-500"><Loader2 size={16} className="animate-spin" /> Memuat undangan...</p>}
        {error && <div className="mt-8" data-testid="invite-error"><h2 className="text-2xl font-bold text-slate-900">Undangan tidak ditemukan</h2><p className="mt-2 text-sm text-slate-500">{error}</p><button onClick={() => nav("/")} className="btn-grad mt-6 rounded-xl px-5 py-2.5 text-sm">Ke halaman masuk</button></div>}
        {info && (
          <div className="mt-8">
            <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#EEF3FF] text-[#2F6BFF]"><Users size={26} /></span>
            <h2 className="mt-5 text-2xl font-bold text-slate-900" data-testid="invite-title">Undangan ke workspace {info.workspace_name}</h2>
            <p className="mt-2 text-sm text-slate-500"><b className="text-slate-800">{info.inviter_name}</b> mengundang <b className="text-slate-800">{info.email}</b> untuk bergabung sebagai anggota tim.</p>

            {done === "joined" && <p className="mt-6 rounded-xl bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700" data-testid="invite-joined">Berhasil bergabung — mengarahkan ke workspace...</p>}
            {done === "rejected" && <p className="mt-6 rounded-xl bg-slate-100 px-4 py-3 text-sm font-semibold text-slate-600" data-testid="invite-rejected">Undangan ditolak. Anda bisa menutup halaman ini.</p>}
            {!done && info.status === "joined" && <p className="mt-6 rounded-xl bg-slate-100 px-4 py-3 text-sm text-slate-600" data-testid="invite-already">Undangan ini sudah diterima. <button className="font-semibold text-[#2F6BFF]" onClick={() => nav("/")}>Masuk</button></p>}

            {!done && info.status !== "joined" && (
              <div className="mt-6 space-y-4">
                {!info.existing_user && (<>
                  <p className="text-sm text-slate-600">Buat akun Anda untuk menerima undangan:</p>
                  <div className="relative"><UserIcon size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" /><input className="input-dark pl-11" placeholder="Nama Anda" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="invite-name" /></div>
                  <div className="relative"><KeyRound size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" /><input className="input-dark pl-11" type="password" placeholder="Kata sandi (min 6)" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="invite-password" /></div>
                </>)}
                {needLogin && <p className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800" data-testid="invite-need-login">Akun dengan email ini sudah ada. Masuk dulu, lalu buka tautan ini lagi.</p>}
                {wrongAccount && <p className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800" data-testid="invite-wrong-account">Anda masuk sebagai {user.email}. Undangan ini untuk {info.email}.</p>}
                <div className="flex gap-3">
                  {needLogin || wrongAccount
                    ? <button onClick={() => { logout(); sessionStorage.setItem("after_login", `/invite/${token}`); nav("/"); }} className="btn-grad flex flex-1 items-center justify-center gap-2 rounded-xl py-3 text-sm" data-testid="invite-login-btn"><LogIn size={16} /> Masuk dengan {info.email}</button>
                    : <button onClick={accept} disabled={busy || loading || (!info.existing_user && form.password.length < 6)} className="btn-grad flex flex-1 items-center justify-center gap-2 rounded-xl py-3 text-sm disabled:opacity-60" data-testid="invite-accept-btn">{busy ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />} Bergabung</button>}
                  <button onClick={reject} disabled={busy} className="flex items-center gap-2 rounded-xl border border-[#E7ECF3] px-4 py-3 text-sm font-semibold text-slate-600 hover:bg-slate-50" data-testid="invite-reject-btn"><X size={16} /> Tolak</button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
