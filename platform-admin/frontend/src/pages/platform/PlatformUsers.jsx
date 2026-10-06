import React, { useEffect, useState } from "react";
import { Search, Loader2, Coins, Ban, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../lib/api";
import { LoadMore } from "../../components/LoadMore";
import { num } from "./PlatformDashboard";

const fmt = (iso) => (iso ? new Date(iso).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" }) : "-");

function CreditDialog({ user, onClose, onDone }) {
  const [delta, setDelta] = useState(1000); const [note, setNote] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try { const r = await api.post(`/platform/users/${user.id}/credits`, { delta: Number(delta), note }); toast.success(`Saldo ${user.email}: ${num(r.data.credits)} kredit`); onDone(r.data.credits); onClose(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal"); } finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4" data-testid="pu-credit-dialog">
      <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl">
        <h3 className="font-bold text-slate-900">Sesuaikan kredit</h3><p className="text-xs text-slate-500">{user.email} · saldo {num(user.credits)}</p>
        <input type="number" value={delta} onChange={(e) => setDelta(e.target.value)} data-testid="pu-credit-delta" className="mt-4 w-full rounded-xl border border-[#E7ECF3] px-3 py-2 text-sm outline-none focus:border-[#2F6BFF]" placeholder="± kredit (negatif = kurangi)" />
        <input value={note} onChange={(e) => setNote(e.target.value)} data-testid="pu-credit-note" className="mt-2 w-full rounded-xl border border-[#E7ECF3] px-3 py-2 text-sm outline-none focus:border-[#2F6BFF]" placeholder="Catatan (opsional)" />
        <div className="mt-4 flex justify-end gap-2"><button onClick={onClose} className="rounded-xl border border-[#E7ECF3] px-3 py-2 text-xs font-semibold text-slate-600" data-testid="pu-credit-cancel">Batal</button><button onClick={submit} disabled={busy || !Number(delta)} className="btn-grad rounded-xl px-4 py-2 text-xs font-bold disabled:opacity-50" data-testid="pu-credit-submit">{busy ? "..." : "Terapkan"}</button></div>
      </div>
    </div>
  );
}

export default function PlatformUsers({ readOnly }) {
  const [q, setQ] = useState(""); const [items, setItems] = useState(null); const [next, setNext] = useState(null); const [busy, setBusy] = useState(false); const [dlg, setDlg] = useState(null);
  const load = async (before, query = q) => {
    setBusy(true);
    try { const r = await api.get("/platform/users", { params: { q: query || undefined, before, limit: 30 } }); setItems((x) => (before ? [...(x || []), ...r.data.items] : r.data.items)); setNext(r.data.has_more ? r.data.next_before : null); }
    catch (e) { setItems((x) => x || []); } finally { setBusy(false); }
  };
  useEffect(() => { const t = setTimeout(() => load(null, q), 300); return () => clearTimeout(t); }, [q]); // eslint-disable-line react-hooks/exhaustive-deps
  const toggle = async (u) => {
    try { await api.post(`/platform/users/${u.id}/disable`, { disabled: !u.disabled }); setItems((x) => x.map((i) => (i.id === u.id ? { ...i, disabled: !u.disabled } : i))); toast.success(u.disabled ? "Akun diaktifkan" : "Akun dinonaktifkan"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal"); }
  };
  return (
    <div data-testid="platform-users">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-black text-slate-900">Pengguna</h1><p className="text-sm text-slate-500">Semua akun, saldo kredit, dan pemakaian 30 hari.</p></div>
        <label className="flex items-center gap-2 rounded-xl border border-[#E7ECF3] bg-white px-3 py-2"><Search size={14} className="text-slate-400" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari email / nama" data-testid="pu-search" className="w-56 text-sm outline-none" /></label>
      </div>
      <div className="mt-6 aivora-card overflow-hidden">
        {items === null ? <p className="flex items-center gap-2 p-6 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p> : (
          <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="pu-table">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-2.5 text-left">Pengguna</th><th className="px-3 py-2.5 text-left">Daftar</th><th className="px-3 py-2.5 text-right">Saldo</th><th className="px-3 py-2.5 text-right">Terpakai 30h</th><th className="px-3 py-2.5 text-right">Asisten</th><th className="px-3 py-2.5 text-left">Status</th>{!readOnly && <th className="px-4 py-2.5 text-right">Aksi</th>}</tr></thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((u) => (
                <tr key={u.id} data-testid={`pu-row-${u.id}`} className={u.disabled ? "bg-rose-50/40" : ""}>
                  <td className="px-4 py-2.5"><p className="font-semibold text-slate-800">{u.name || "—"}</p><p className="text-[11px] text-slate-400">{u.email}{u.platform_role ? ` · staf ${u.platform_role}` : ""}</p></td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-xs text-slate-500">{fmt(u.created_at)}</td>
                  <td className="px-3 py-2.5 text-right font-bold text-slate-900" data-testid={`pu-credits-${u.id}`}>{num(u.credits)}</td>
                  <td className="px-3 py-2.5 text-right text-slate-700">{num(u.used_30d)}</td>
                  <td className="px-3 py-2.5 text-right text-slate-700">{u.personas}</td>
                  <td className="px-3 py-2.5 text-xs">{u.disabled ? <span className="rounded-full bg-rose-100 px-2 py-0.5 font-semibold text-rose-700">Nonaktif</span> : <span className="rounded-full bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700">{u.plan === "trial" ? "Trial" : "Aktif"}</span>}</td>
                  {!readOnly && <td className="whitespace-nowrap px-4 py-2.5 text-right">
                    <button onClick={() => setDlg(u)} className="mr-1 inline-flex items-center gap-1 rounded-lg bg-[#EEF3FF] px-2.5 py-1.5 text-xs font-bold text-[#2F6BFF]" data-testid={`pu-credit-${u.id}`}><Coins size={13} /> Kredit</button>
                    {!u.platform_role && <button onClick={() => toggle(u)} className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-bold ${u.disabled ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-600"}`} data-testid={`pu-toggle-${u.id}`}>{u.disabled ? <><CheckCircle2 size={13} /> Aktifkan</> : <><Ban size={13} /> Nonaktifkan</>}</button>}
                  </td>}
                </tr>
              ))}
              {items.length === 0 && <tr><td colSpan={7} className="p-6 text-center text-sm text-slate-500">Tidak ada pengguna.</td></tr>}
            </tbody>
          </table></div>
        )}
        {next && !busy && <LoadMore onClick={() => load(next)} testid="pu-more" />}
      </div>
      {dlg && <CreditDialog user={dlg} onClose={() => setDlg(null)} onDone={(c) => setItems((x) => x.map((i) => (i.id === dlg.id ? { ...i, credits: c } : i)))} />}
    </div>
  );
}
