import React, { useEffect, useState } from "react";
import { Loader2, UserPlus, Trash2, Crown, Link2, History } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../lib/api";
import { apiErr } from "../../lib/apiErr";
import { useAuth } from "../../context/AuthContext";
import { ROLE_LABEL } from "./PlatformApp";

const fmt = (iso) => (iso ? new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "-");

export default function PlatformStaff() {
  const { user } = useAuth();
  const [items, setItems] = useState(null); const [audit, setAudit] = useState([]);
  const [email, setEmail] = useState(""); const [role, setRole] = useState("finance"); const [busy, setBusy] = useState(false); const [inviteLink, setInviteLink] = useState("");
  const load = () => { api.get("/platform/staff").then((r) => setItems(r.data.items)).catch(() => setItems([])); api.get("/platform/audit", { params: { limit: 30 } }).then((r) => setAudit(r.data.items)).catch(() => {}); };
  useEffect(load, []);
  const add = async (e) => {
    e.preventDefault(); setBusy(true); setInviteLink("");
    try { const r = await api.post("/platform/staff", { email, role }); toast.success(r.data.created ? `Undangan dikirim ke ${email}` : `${email} kini ${ROLE_LABEL[role]}`); if (r.data.debug_link) setInviteLink(r.data.debug_link); setEmail(""); load(); }
    catch (err) { toast.error(apiErr(err, "Gagal")); } finally { setBusy(false); }
  };
  const setR = async (s, r) => { try { await api.put(`/platform/staff/${s.id}`, { role: r }); toast.success("Peran diperbarui"); load(); } catch (e) { toast.error(apiErr(e, "Gagal")); } };
  const revoke = async (s) => { if (!window.confirm(`Cabut akses platform ${s.email}?`)) return; try { await api.delete(`/platform/staff/${s.id}`); toast.success("Akses dicabut"); load(); } catch (e) { toast.error(apiErr(e, "Gagal")); } };
  return (
    <div data-testid="platform-staff">
      <h1 className="text-2xl font-black text-slate-900">Staf & Peran</h1>
      <p className="text-sm text-slate-500"><b>Super Admin</b> mengelola semuanya; <b>Finance</b> hanya membaca dasbor, tarif, pengguna, dan laporan keuangan.</p>
      <form onSubmit={add} className="mt-6 aivora-card flex flex-wrap items-end gap-3 p-4" data-testid="staff-add-form">
        <label className="min-w-[240px] flex-1"><span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Email</span><input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} data-testid="staff-email" placeholder="nama@perusahaan.com" className="mt-1 w-full rounded-xl border border-[#E7ECF3] px-3 py-2 text-sm outline-none focus:border-[#2F6BFF]" /></label>
        <label><span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Peran</span><select value={role} onChange={(e) => setRole(e.target.value)} data-testid="staff-role" className="mt-1 block rounded-xl border border-[#E7ECF3] bg-white px-3 py-2 text-sm outline-none">{Object.entries(ROLE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <button disabled={busy} className="btn-grad flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-bold disabled:opacity-50" data-testid="staff-add"><UserPlus size={14} /> {busy ? "..." : "Tambah staf"}</button>
        {inviteLink && <p className="w-full break-all rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800" data-testid="staff-invite-link"><Link2 size={12} className="mr-1 inline" /> Tautan atur password (preview): {inviteLink}</p>}
      </form>
      <div className="mt-6 aivora-card overflow-hidden">
        {items === null ? <p className="flex items-center gap-2 p-6 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p> : (
          <table className="w-full text-sm" data-testid="staff-table">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-2.5 text-left">Staf</th><th className="px-3 py-2.5 text-left">Peran</th><th className="px-3 py-2.5 text-left">Login terakhir</th><th className="px-4 py-2.5 text-right">Aksi</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((s) => { const me = s.id === user.id; return (
                <tr key={s.id} data-testid={`staff-row-${s.id}`}>
                  <td className="px-4 py-2.5"><p className="flex items-center gap-1.5 font-semibold text-slate-800">{s.is_owner && <Crown size={13} className="text-amber-500" />}{s.name || "—"}{me && <span className="text-[10px] text-slate-400">(Anda)</span>}</p><p className="text-[11px] text-slate-400">{s.email}</p></td>
                  <td className="px-3 py-2.5">{s.is_owner || me ? <span className="rounded-full bg-[#EEF3FF] px-2 py-0.5 text-xs font-bold text-[#2F6BFF]">{ROLE_LABEL[s.platform_role]}{s.is_owner ? " · Pemilik" : ""}</span>
                    : <select value={s.platform_role} onChange={(e) => setR(s, e.target.value)} data-testid={`staff-role-${s.id}`} className="rounded-lg border border-[#E7ECF3] bg-white px-2 py-1 text-xs font-semibold outline-none">{Object.entries(ROLE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>}</td>
                  <td className="px-3 py-2.5 text-xs text-slate-500">{fmt(s.last_login_at)}</td>
                  <td className="px-4 py-2.5 text-right">{!s.is_owner && !me && <button onClick={() => revoke(s)} className="inline-flex items-center gap-1 rounded-lg bg-rose-50 px-2.5 py-1.5 text-xs font-bold text-rose-600" data-testid={`staff-revoke-${s.id}`}><Trash2 size={13} /> Cabut</button>}</td>
                </tr>); })}
            </tbody>
          </table>
        )}
      </div>
      <div className="mt-8" data-testid="staff-audit">
        <p className="flex items-center gap-2 text-sm font-bold text-slate-900"><History size={15} className="text-[#2F6BFF]" /> Jejak audit</p>
        <div className="mt-2 aivora-card divide-y divide-slate-100">
          {audit.length === 0 && <p className="p-4 text-xs text-slate-400">Belum ada aktivitas.</p>}
          {audit.map((a) => <div key={a.id} className="flex items-center gap-3 px-4 py-2 text-xs"><span className="w-28 shrink-0 text-slate-400">{fmt(a.created_at)}</span><span className="font-semibold text-slate-700">{a.actor_email}</span><span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10px] text-slate-600">{a.action}</span><span className="truncate text-slate-500">{a.target}{a.meta && Object.keys(a.meta).length ? ` · ${JSON.stringify(a.meta)}` : ""}</span></div>)}
        </div>
      </div>
    </div>
  );
}
