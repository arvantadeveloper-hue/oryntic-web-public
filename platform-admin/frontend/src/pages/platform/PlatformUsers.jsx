import React, { useEffect, useState } from "react";
import { Search, Loader2, Coins, Ban, CheckCircle2, X, History, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../lib/api";
import { apiErr } from "../../lib/apiErr";
import { LoadMore } from "../../components/LoadMore";
import { num } from "./PlatformDashboard";

const fmt = (iso) => (iso ? new Date(iso).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" }) : "-");
const fmtDT = (iso) => (iso ? new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "-");

function CreditDialog({ user, onClose, onDone }) {
  const [amount, setAmount] = useState(1000); const [note, setNote] = useState(""); const [busy, setBusy] = useState(false);
  const amt = Math.max(0, Math.floor(Number(amount) || 0));
  const submit = async () => {
    setBusy(true);
    try { const r = await api.post(`/platform/users/${user.id}/credits`, { delta: amt, note }); toast.success(`Top up berhasil · saldo ${user.email}: ${num(r.data.credits)} kredit`); onDone(r.data.credits); onClose(); }
    catch (e) { toast.error(apiErr(e, "Gagal top up")); } finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4" data-testid="pu-credit-dialog">
      <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl">
        <h3 className="flex items-center gap-2 font-bold text-slate-900"><Coins size={16} className="text-[#2F6BFF]" /> Top up kredit</h3>
        <p className="text-xs text-slate-500">{user.email} · saldo {num(user.credits)} → <b className="text-slate-800">{num(user.credits + amt)}</b></p>
        <input type="number" min={1} value={amount} onChange={(e) => setAmount(e.target.value)} data-testid="pu-credit-delta" className="mt-4 w-full rounded-xl border border-[#E7ECF3] px-3 py-2 text-sm outline-none focus:border-[#2F6BFF]" placeholder="Jumlah kredit (hanya menambah)" />
        <div className="mt-2 flex flex-wrap gap-1.5">{[1000, 5000, 10000, 50000].map((v) => <button key={v} type="button" onClick={() => setAmount(v)} data-testid={`pu-credit-preset-${v}`} className="rounded-full border border-[#E7ECF3] px-2.5 py-1 text-xs font-semibold text-slate-600 hover:border-[#2F6BFF] hover:text-[#2F6BFF]">+{num(v)}</button>)}</div>
        <input value={note} onChange={(e) => setNote(e.target.value)} data-testid="pu-credit-note" className="mt-3 w-full rounded-xl border border-[#E7ECF3] px-3 py-2 text-sm outline-none focus:border-[#2F6BFF]" placeholder="Catatan (opsional)" />
        <p className="mt-2 text-[11px] text-slate-400">Kredit hanya dapat ditambah; pengurangan tidak tersedia. Semua top up tercatat di Jejak Audit.</p>
        <div className="mt-4 flex justify-end gap-2"><button onClick={onClose} className="rounded-xl border border-[#E7ECF3] px-3 py-2 text-xs font-semibold text-slate-600" data-testid="pu-credit-cancel">Batal</button><button onClick={submit} disabled={busy || amt < 1} className="btn-grad rounded-xl px-4 py-2 text-xs font-bold disabled:opacity-50" data-testid="pu-credit-submit">{busy ? "..." : `Top up +${num(amt)}`}</button></div>
      </div>
    </div>
  );
}

function SuspendDialog({ user, onClose, onDone }) {
  const [reason, setReason] = useState(""); const [busy, setBusy] = useState(false);
  const r = reason.trim();
  const submit = async () => {
    setBusy(true);
    try { await api.post(`/platform/users/${user.id}/disable`, { disabled: true, reason: r }); toast.success(`${user.email} disuspend`); onDone(); onClose(); }
    catch (e) { toast.error(apiErr(e, "Gagal suspend")); } finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4" data-testid="pu-suspend-dialog">
      <div className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-2xl">
        <h3 className="flex items-center gap-2 font-bold text-slate-900"><Ban size={16} className="text-rose-600" /> Suspend akun</h3>
        <p className="text-xs text-slate-500">{user.email}</p>
        <label className="mt-4 block text-xs font-semibold text-slate-600">Alasan suspend <span className="text-rose-500">*</span></label>
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} maxLength={200} data-testid="pu-suspend-reason" className="mt-1 w-full rounded-xl border border-[#E7ECF3] px-3 py-2 text-sm outline-none focus:border-rose-400" placeholder="mis. Pelanggaran ketentuan, aktivitas mencurigakan…" />
        <p className="mt-2 text-[11px] text-slate-400">Alasan wajib diisi dan akan tercatat di Jejak Audit.</p>
        <div className="mt-4 flex justify-end gap-2"><button onClick={onClose} className="rounded-xl border border-[#E7ECF3] px-3 py-2 text-xs font-semibold text-slate-600" data-testid="pu-suspend-cancel">Batal</button><button onClick={submit} disabled={busy || r.length < 1} className="rounded-xl bg-rose-600 px-4 py-2 text-xs font-bold text-white disabled:opacity-50" data-testid="pu-suspend-submit">{busy ? "..." : "Suspend"}</button></div>
      </div>
    </div>
  );
}

function HistoryDialog({ user, onClose }) {
  const [data, setData] = useState(null);
  useEffect(() => { api.get(`/platform/users/${user.id}/history`).then((r) => setData(r.data)).catch((e) => { toast.error(apiErr(e, "Gagal memuat riwayat")); setData({ transactions: [], usage: [] }); }); }, [user.id]);
  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4" data-testid="pu-history-dialog" onClick={onClose}>
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between border-b border-[#E7ECF3] p-5">
          <div><h3 className="flex items-center gap-2 font-bold text-slate-900"><History size={16} className="text-[#2F6BFF]" /> Riwayat — {user.name || user.email}</h3><p className="text-xs text-slate-500">{user.email} · saldo {num(user.credits)} kredit</p></div>
          <button onClick={onClose} className="rounded-lg p-1 text-slate-400 hover:bg-slate-100" data-testid="pu-history-close"><X size={18} /></button>
        </div>
        {!data ? <p className="flex items-center gap-2 p-6 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p> : (
          <div className="grid gap-5 overflow-y-auto p-5 sm:grid-cols-2">
            <div data-testid="pu-history-topups">
              <p className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">Top up & penyesuaian</p>
              <div className="space-y-2">
                {data.transactions.length === 0 && <p className="text-xs text-slate-400">Belum ada transaksi kredit.</p>}
                {data.transactions.map((t, i) => (
                  <div key={i} className="flex items-start justify-between rounded-xl border border-[#E7ECF3] px-3 py-2">
                    <div><p className="flex items-center gap-1 text-sm font-semibold text-emerald-600"><ArrowUpRight size={13} /> +{num(t.amount)}</p><p className="text-[11px] text-slate-500">{t.description || "—"}{t.meta?.by ? ` · ${t.meta.by}` : ""}</p></div>
                    <div className="text-right"><p className="text-[11px] text-slate-400">{fmtDT(t.created_at)}</p><p className="text-[11px] text-slate-500">saldo {num(t.balance_after)}</p></div>
                  </div>
                ))}
              </div>
            </div>
            <div data-testid="pu-history-usage">
              <p className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">Pemakaian kredit</p>
              <div className="space-y-2">
                {data.usage.length === 0 && <p className="text-xs text-slate-400">Belum ada pemakaian.</p>}
                {data.usage.map((e, i) => (
                  <div key={i} className="flex items-start justify-between rounded-xl border border-[#E7ECF3] px-3 py-2">
                    <p className="flex items-center gap-1 text-sm font-semibold text-rose-600"><ArrowDownRight size={13} /> -{num(e.credits)}</p>
                    <div className="text-right"><p className="text-xs font-medium text-slate-700">{e.label}</p><p className="text-[11px] text-slate-400">{fmtDT(e.created_at)}</p></div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function PlatformUsers({ readOnly }) {
  const [q, setQ] = useState(""); const [items, setItems] = useState(null); const [next, setNext] = useState(null); const [busy, setBusy] = useState(false); const [dlg, setDlg] = useState(null); const [suspendFor, setSuspendFor] = useState(null); const [historyFor, setHistoryFor] = useState(null);
  const load = async (before, query = q) => {
    setBusy(true);
    try { const r = await api.get("/platform/users", { params: { q: query || undefined, before, limit: 30 } }); setItems((x) => (before ? [...(x || []), ...r.data.items] : r.data.items)); setNext(r.data.has_more ? r.data.next_before : null); }
    catch (e) { setItems((x) => x || []); } finally { setBusy(false); }
  };
  useEffect(() => { const t = setTimeout(() => load(null, q), 300); return () => clearTimeout(t); }, [q]); // eslint-disable-line react-hooks/exhaustive-deps
  const markDisabled = (uid, val) => setItems((x) => x.map((i) => (i.id === uid ? { ...i, disabled: val } : i)));
  const enable = async (u) => {
    try { await api.post(`/platform/users/${u.id}/disable`, { disabled: false }); markDisabled(u.id, false); toast.success("Akun diaktifkan kembali"); }
    catch (e) { toast.error(apiErr(e, "Gagal")); }
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
                <tr key={u.id} data-testid={`pu-row-${u.id}`} onClick={() => setHistoryFor(u)} className={`cursor-pointer hover:bg-slate-50 ${u.disabled ? "bg-rose-50/40" : ""}`}>
                  <td className="px-4 py-2.5"><p className="font-semibold text-slate-800">{u.name || "—"}</p><p className="text-[11px] text-slate-400">{u.email}{u.platform_role ? ` · staf ${u.platform_role}` : ""}</p></td>
                  <td className="whitespace-nowrap px-3 py-2.5 text-xs text-slate-500">{fmt(u.created_at)}</td>
                  <td className="px-3 py-2.5 text-right font-bold text-slate-900" data-testid={`pu-credits-${u.id}`}>{num(u.credits)}</td>
                  <td className="px-3 py-2.5 text-right text-slate-700">{num(u.used_30d)}</td>
                  <td className="px-3 py-2.5 text-right text-slate-700">{u.personas}</td>
                  <td className="px-3 py-2.5 text-xs">{u.disabled ? <span className="rounded-full bg-rose-100 px-2 py-0.5 font-semibold text-rose-700">Disuspend</span> : <span className="rounded-full bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700">{u.plan === "trial" ? "Trial" : "Aktif"}</span>}</td>
                  {!readOnly && <td className="whitespace-nowrap px-4 py-2.5 text-right" onClick={(e) => e.stopPropagation()}>
                    <button onClick={() => setDlg(u)} className="mr-1 inline-flex items-center gap-1 rounded-lg bg-[#EEF3FF] px-2.5 py-1.5 text-xs font-bold text-[#2F6BFF]" data-testid={`pu-credit-${u.id}`}><Coins size={13} /> Top up</button>
                    {!u.platform_role && <button onClick={() => (u.disabled ? enable(u) : setSuspendFor(u))} className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-bold ${u.disabled ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-600"}`} data-testid={`pu-toggle-${u.id}`}>{u.disabled ? <><CheckCircle2 size={13} /> Aktifkan</> : <><Ban size={13} /> Suspend</>}</button>}
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
      {suspendFor && <SuspendDialog user={suspendFor} onClose={() => setSuspendFor(null)} onDone={() => markDisabled(suspendFor.id, true)} />}
      {historyFor && <HistoryDialog user={historyFor} onClose={() => setHistoryFor(null)} />}
    </div>
  );
}
