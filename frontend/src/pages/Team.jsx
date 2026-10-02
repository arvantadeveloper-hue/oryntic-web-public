import React, { useEffect, useState } from "react";
import { UserPlus, Trash2, Shield, User as UserIcon, Loader2, Mail, KeyRound } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { UsageReport } from "../components/UsageReport";
import { SmartRoutingToggle } from "../components/ModelRoutingCard";
import { useAuth } from "../context/AuthContext";

function QuotaControl({ user, onSaved }) {
  const [val, setVal] = useState(String(user.daily_credit_limit || 0));
  const [saving, setSaving] = useState(false);
  const save = async () => {
    setSaving(true);
    try { await api.patch(`/admin/users/${user.id}`, { daily_credit_limit: parseInt(val || "0", 10) }); toast.success("Kuota diperbarui"); onSaved && onSaved(); }
    catch (e) { toast.error("Gagal menyimpan kuota"); } finally { setSaving(false); }
  };
  return (
    <span className="flex items-center gap-1">
      <input type="number" min="0" value={val} onChange={(e) => setVal(e.target.value)} className="input-dark w-20 py-1.5 text-xs" placeholder="0 = ∞" data-testid={`quota-input-${user.email}`} title="Jatah kredit harian (0 = tanpa batas)" />
      <button onClick={save} disabled={saving} className="rounded-lg border border-[#E7ECF3] px-2 py-1.5 text-xs font-semibold text-[#2F6BFF] hover:bg-[#EEF3FF]" data-testid={`quota-save-${user.email}`}>{saving ? "..." : "Set"}</button>
    </span>
  );
}

export default function Team() {
  const { user, refreshUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);

  const load = () => {
    setLoading(true);
    api.get("/admin/workspace-users").then((r) => setUsers(r.data)).catch(() => {}).finally(() => setLoading(false));
  };
  useEffect(load, []);

  const create = async (e) => {
    e.preventDefault();
    if (!form.email || form.password.length < 6) { toast.error("Email wajib & kata sandi minimal 6 karakter"); return; }
    setBusy(true);
    try {
      await api.post("/admin/users", form);
      toast.success(`Pengguna ${form.name || form.email} dibuat`);
      setForm({ name: "", email: "", password: "" });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal membuat pengguna");
    } finally { setBusy(false); }
  };

  const remove = async (u) => {
    if (!window.confirm(`Hapus pengguna ${u.name}?`)) return;
    try { await api.delete(`/admin/users/${u.id}`); toast.success("Pengguna dihapus"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menghapus"); }
  };

  return (
    <div className="mx-auto max-w-5xl p-5 sm:p-8" data-testid="team-page">
      <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">Tim & Pengguna</h1>
      <p className="mt-1 text-sm text-slate-500">Kelola anggota workspace. Pengguna biasa dapat chat & ikut meeting, tetapi tidak bisa mengubah setelan, kredit, atau membuat persona.</p>
      <SmartRoutingToggle user={user} onSaved={refreshUser} />

      <form onSubmit={create} className="aivora-card mt-6 grid gap-3 p-5 sm:grid-cols-[1fr_1fr_1fr_auto]" data-testid="create-user-form">
        <div className="relative"><UserIcon size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input-dark py-2.5 pl-9" placeholder="Nama" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="new-user-name" /></div>
        <div className="relative"><Mail size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input-dark py-2.5 pl-9" placeholder="Email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="new-user-email" /></div>
        <div className="relative"><KeyRound size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input-dark py-2.5 pl-9" placeholder="Kata sandi (min 6)" type="text" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="new-user-password" /></div>
        <button disabled={busy} className="btn-grad flex items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-sm" data-testid="create-user-btn">
          {busy ? <Loader2 size={16} className="animate-spin" /> : <UserPlus size={16} />} Tambah
        </button>
      </form>

      <div className="mt-6 space-y-2">
        {loading ? <p className="text-sm text-slate-400">Memuat...</p> : users.map((u) => (
          <div key={u.id} className="aivora-card flex flex-wrap items-center gap-3 p-4" data-testid={`team-user-${u.email}`}>
            <span className="flex h-10 w-10 items-center justify-center rounded-full text-sm font-bold text-white" style={{ background: u.is_admin ? "#0B132B" : "linear-gradient(135deg,#2F6BFF,#7C3AED)" }}>{(u.name || "U")[0].toUpperCase()}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-bold text-slate-900">{u.name}</p>
              <p className="truncate text-xs text-slate-400">{u.email}</p>
            </div>
            <span className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${u.is_admin ? "bg-[#0B132B] text-white" : "bg-[#EEF3FF] text-[#2F6BFF]"}`}>
              {u.is_admin ? <Shield size={12} /> : <UserIcon size={12} />} {u.is_admin ? "Administrator" : "Pengguna"}
            </span>
            {!u.is_admin && (
              <div className="flex items-center gap-2" data-testid={`quota-${u.email}`}>
                <span className="text-xs text-slate-500">Hari ini: <b className="text-slate-800">{u.today_usage ?? 0}</b> kredit</span>
                <QuotaControl user={u} onSaved={load} />
                <button onClick={() => remove(u)} className="text-slate-400 transition hover:text-[#EF4444]" data-testid={`delete-user-${u.email}`}><Trash2 size={16} /></button>
              </div>
            )}
          </div>
        ))}
      </div>
      <UsageReport />
    </div>
  );
}
