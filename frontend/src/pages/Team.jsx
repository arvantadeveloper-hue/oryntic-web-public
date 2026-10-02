import React, { useEffect, useState } from "react";
import { UserPlus, Trash2, Shield, User as UserIcon, Loader2, Mail, Send, RotateCw, X, Clock, Check, Ban } from "lucide-react";
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

const STATUS = {
  pending: { label: "Menunggu tanggapan", cls: "bg-amber-50 text-amber-700", Icon: Clock },
  joined: { label: "Bergabung", cls: "bg-emerald-50 text-emerald-700", Icon: Check },
  rejected: { label: "Ditolak", cls: "bg-red-50 text-[#EF4444]", Icon: Ban },
  removed: { label: "Dikeluarkan", cls: "bg-slate-100 text-slate-500", Icon: X },
};

function InviteRow({ inv, onChanged }) {
  const [busy, setBusy] = useState(false);
  const s = STATUS[inv.status] || STATUS.pending;
  const resend = async () => {
    setBusy(true);
    try { const r = await api.post(`/team/invites/${inv.id}/resend`, { app_url: window.location.origin }); toast.success(r.data.mail_sent === false ? "Undangan diperbarui (email belum terkirim)" : "Undangan dikirim ulang"); onChanged(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengirim ulang"); } finally { setBusy(false); }
  };
  const cancel = async () => {
    if (!window.confirm(`Batalkan undangan untuk ${inv.email}?`)) return;
    try { await api.delete(`/team/invites/${inv.id}`); toast.success("Undangan dibatalkan"); onChanged(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal membatalkan"); }
  };
  return (
    <div className="flex flex-wrap items-center gap-3 border-t border-[#E7ECF3] px-4 py-3 first:border-t-0" data-testid={`invite-row-${inv.email}`}>
      <Mail size={15} className="text-slate-400" />
      <div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-slate-800">{inv.email}</p><p className="text-[11px] text-slate-400">Diundang {new Date(inv.created_at).toLocaleString("id-ID")}{inv.responded_at ? ` · ditanggapi ${new Date(inv.responded_at).toLocaleString("id-ID")}` : ""}</p></div>
      <span className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${s.cls}`} data-testid={`invite-status-${inv.email}`}><s.Icon size={12} /> {s.label}</span>
      {inv.status !== "joined" && (
        <span className="flex items-center gap-1">
          <button onClick={resend} disabled={busy} title="Kirim ulang" className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-[#2F6BFF]" data-testid={`invite-resend-${inv.email}`}>{busy ? <Loader2 size={15} className="animate-spin" /> : <RotateCw size={15} />}</button>
          <button onClick={cancel} title="Batalkan" className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-[#EF4444]" data-testid={`invite-cancel-${inv.email}`}><X size={15} /></button>
        </span>
      )}
    </div>
  );
}

export default function Team() {
  const { user, refreshUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [invites, setInvites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => {
    setLoading(true);
    Promise.all([api.get("/admin/workspace-users"), api.get("/team/invites")])
      .then(([u, i]) => { setUsers(u.data); setInvites(i.data); }).catch(() => {}).finally(() => setLoading(false));
  };
  useEffect(load, []);

  const invite = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    try {
      const r = await api.post("/team/invites", { email: email.trim(), app_url: window.location.origin });
      toast.success(r.data.mail_sent === false ? `Undangan dibuat untuk ${email} (email belum terkirim — periksa SMTP)` : `Undangan dikirim ke ${email}${r.data.existing_user ? " (pengguna terdaftar: juga tampil di notifikasi aplikasi)" : ""}`);
      setEmail(""); load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Gagal mengirim undangan");
    } finally { setBusy(false); }
  };

  const remove = async (u) => {
    if (!window.confirm(`Keluarkan ${u.name} dari workspace ini? Akun dan workspace pribadinya tetap ada.`)) return;
    try { await api.delete(`/team/members/${u.id}`); toast.success("Anggota dikeluarkan"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengeluarkan"); }
  };

  return (
    <div className="mx-auto max-w-5xl p-5 sm:p-8" data-testid="team-page">
      <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">Tim & Pengguna</h1>
      <p className="mt-1 text-sm text-slate-500">Undang rekan lewat email. Mereka membuat kata sandi sendiri (atau menerima dari akun yang sudah ada) dan bisa chat & ikut panggilan di workspace ini, tetapi tidak bisa mengubah setelan, kredit, atau persona.</p>
      <SmartRoutingToggle user={user} onSaved={refreshUser} />

      <form onSubmit={invite} className="aivora-card mt-6 flex flex-col gap-3 p-5 sm:flex-row" data-testid="invite-form">
        <div className="relative flex-1"><Mail size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input-dark py-2.5 pl-9" placeholder="Email rekan yang diundang" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} data-testid="invite-email" /></div>
        <button disabled={busy} className="btn-grad flex items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-sm" data-testid="invite-send-btn">
          {busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />} Undang via Email
        </button>
      </form>

      {invites.length > 0 && (
        <div className="aivora-card mt-6 overflow-hidden" data-testid="invite-list">
          <p className="flex items-center gap-2 px-4 py-3 text-xs font-bold uppercase tracking-wider text-slate-500"><UserPlus size={14} /> Undangan · {invites.length}</p>
          {invites.map((inv) => <InviteRow key={inv.id} inv={inv} onChanged={load} />)}
        </div>
      )}

      <p className="mt-6 text-xs font-bold uppercase tracking-wider text-slate-500">Anggota · {users.length}</p>
      <div className="mt-2 space-y-2">
        {loading ? <p className="text-sm text-slate-400">Memuat...</p> : users.map((u) => (
          <div key={u.id} className="aivora-card flex flex-wrap items-center gap-3 p-4" data-testid={`team-user-${u.email}`}>
            <span className="flex h-10 w-10 items-center justify-center rounded-full text-sm font-bold text-white" style={{ background: u.is_admin ? "#0B132B" : "linear-gradient(135deg,#2F6BFF,#7C3AED)" }}>{(u.name || "U")[0].toUpperCase()}</span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-bold text-slate-900">{u.name}</p>
              <p className="truncate text-xs text-slate-400">{u.email}</p>
            </div>
            <span className={`flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${u.is_admin ? "bg-[#0B132B] text-white" : "bg-[#EEF3FF] text-[#2F6BFF]"}`}>
              {u.is_admin ? <Shield size={12} /> : <UserIcon size={12} />} {u.is_admin ? "Administrator" : "Anggota"}
            </span>
            {!u.is_admin && (
              <div className="flex items-center gap-2" data-testid={`quota-${u.email}`}>
                <span className="text-xs text-slate-500">Hari ini: <b className="text-slate-800">{u.today_usage ?? 0}</b> kredit</span>
                <QuotaControl user={u} onSaved={load} />
                <button onClick={() => remove(u)} className="text-slate-400 transition hover:text-[#EF4444]" title="Keluarkan dari workspace" data-testid={`delete-user-${u.email}`}><Trash2 size={16} /></button>
              </div>
            )}
          </div>
        ))}
      </div>
      <UsageReport />
    </div>
  );
}
