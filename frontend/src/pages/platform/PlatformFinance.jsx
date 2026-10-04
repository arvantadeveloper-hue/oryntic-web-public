import React, { useEffect, useState } from "react";
import { Download, Loader2, Receipt } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../lib/api";
import { rp, num } from "./PlatformDashboard";

const iso = (d) => d.toISOString().slice(0, 10);

export default function PlatformFinance() {
  const [from, setFrom] = useState(() => iso(new Date(Date.now() - 29 * 86400000)));
  const [to, setTo] = useState(() => iso(new Date()));
  const [group, setGroup] = useState("day");
  const [data, setData] = useState(null); const [busy, setBusy] = useState(false);
  useEffect(() => {
    setData(null);
    api.get("/platform/finance", { params: { date_from: from, date_to: to, group } }).then((r) => setData(r.data)).catch((e) => { toast.error(e?.response?.data?.detail || "Gagal memuat laporan"); setData({ rows: [], total: {}, packages: [] }); });
  }, [from, to, group]);
  const download = async () => {
    setBusy(true);
    try {
      const r = await api.get("/platform/finance/export.csv", { params: { date_from: from, date_to: to, group }, responseType: "blob" });
      const url = URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = url; a.download = `oryntix-keuangan-${from}-${to}.csv`; a.click(); URL.revokeObjectURL(url);
    } catch (e) { toast.error("Gagal mengunduh CSV"); } finally { setBusy(false); }
  };
  const t = data?.total || {};
  return (
    <div data-testid="platform-finance">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-black text-slate-900">Laporan Keuangan</h1><p className="text-sm text-slate-500">Pendapatan top-up, penyesuaian kredit, dan kredit terpakai per periode.</p></div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-xs text-slate-500">Dari<input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} data-testid="fin-from" className="mt-1 block rounded-xl border border-[#E7ECF3] bg-white px-3 py-2 text-sm text-slate-900 outline-none" /></label>
          <label className="text-xs text-slate-500">Sampai<input type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} data-testid="fin-to" className="mt-1 block rounded-xl border border-[#E7ECF3] bg-white px-3 py-2 text-sm text-slate-900 outline-none" /></label>
          <div className="flex gap-1 rounded-xl border border-[#E7ECF3] bg-white p-1">{[["day", "Harian"], ["month", "Bulanan"]].map(([g, l]) => <button key={g} onClick={() => setGroup(g)} data-testid={`fin-group-${g}`} className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${group === g ? "bg-[#0B132B] text-white" : "text-slate-600"}`}>{l}</button>)}</div>
          <button onClick={download} disabled={busy || !data} className="btn-grad flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-bold disabled:opacity-50" data-testid="fin-download">{busy ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />} Unduh CSV</button>
        </div>
      </div>
      {!data ? <p className="mt-6 flex items-center gap-2 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p> : (
        <>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[["Pendapatan", rp(t.revenue_idr), `${num(t.topups)} top-up · ${num(t.buyers)} pembeli`, "fin-revenue"], ["Kredit terjual", num(t.credits_sold), "dari top-up", "fin-sold"], ["Penyesuaian", `${t.credits_adjusted > 0 ? "+" : ""}${num(t.credits_adjusted)}`, `${num(t.adjustments)} transaksi manual`, "fin-adj"], ["Kredit terpakai", num(t.credits_consumed), "beban layanan periode ini", "fin-consumed"]].map(([l, v, s, id]) => (
              <div key={id} className="aivora-card p-5" data-testid={id}><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{l}</p><p className="mt-2 text-2xl font-black text-slate-900">{v}</p><p className="text-xs text-slate-500">{s}</p></div>))}
          </div>
          <div className="mt-6 grid gap-4 lg:grid-cols-3">
            <div className="aivora-card overflow-hidden lg:col-span-2">
              <table className="w-full text-sm" data-testid="fin-table">
                <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-2.5 text-left">Periode</th><th className="px-3 py-2.5 text-right">Top-up</th><th className="px-3 py-2.5 text-right">Kredit terjual</th><th className="px-3 py-2.5 text-right">Pendapatan</th><th className="px-3 py-2.5 text-right">Penyesuaian</th><th className="px-4 py-2.5 text-right">Terpakai</th></tr></thead>
                <tbody className="divide-y divide-slate-100">
                  {data.rows.map((r) => <tr key={r.period} data-testid={`fin-row-${r.period}`}><td className="px-4 py-2 font-semibold text-slate-800">{r.period}</td><td className="px-3 py-2 text-right">{num(r.topups)}</td><td className="px-3 py-2 text-right">{num(r.credits_sold)}</td><td className="px-3 py-2 text-right font-bold text-slate-900">{rp(r.revenue_idr)}</td><td className="px-3 py-2 text-right">{r.credits_adjusted ? `${r.credits_adjusted > 0 ? "+" : ""}${num(r.credits_adjusted)}` : "–"}</td><td className="px-4 py-2 text-right">{num(r.credits_consumed)}</td></tr>)}
                  {data.rows.length === 0 && <tr><td colSpan={6} className="p-6 text-center text-sm text-slate-500" data-testid="fin-empty">Tidak ada transaksi pada periode ini.</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="aivora-card p-5" data-testid="fin-packages">
              <p className="flex items-center gap-2 text-sm font-bold text-slate-900"><Receipt size={15} className="text-[#2F6BFF]" /> Per paket</p>
              <div className="mt-3 divide-y divide-slate-100">
                {data.packages.map((p) => <div key={p.package} className="flex items-center justify-between py-2 text-sm"><div><p className="font-semibold capitalize text-slate-800">{p.package}</p><p className="text-[11px] text-slate-400">{num(p.count)}× · {num(p.credits)} kredit</p></div><p className="font-bold text-slate-900">{rp(p.revenue_idr)}</p></div>)}
                {data.packages.length === 0 && <p className="py-2 text-xs text-slate-400">Belum ada penjualan.</p>}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
