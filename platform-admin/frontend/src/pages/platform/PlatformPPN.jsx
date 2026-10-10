import React, { useEffect, useState } from "react";
import { Loader2, Download, FileSpreadsheet } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../lib/api";
import { rp } from "./PlatformDashboard";

const monthLabel = (ym) => new Date(ym + "-01T00:00:00").toLocaleDateString("id-ID", { month: "long", year: "numeric" });
const statusOf = (net) => (net < 0 ? { t: "Lebih bayar", c: "text-emerald-600 bg-emerald-50" } : net > 0 ? { t: "Kurang bayar", c: "text-rose-600 bg-rose-50" } : { t: "Nihil", c: "text-slate-500 bg-slate-100" });

export default function PlatformPPN() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const years = Array.from({ length: 6 }, (_, i) => now.getFullYear() - i);

  useEffect(() => {
    setData(null);
    api.get("/platform/finance/ppn", { params: { year } }).then((r) => setData(r.data)).catch(() => { toast.error("Gagal memuat SPT PPN"); setData({ months: [], total: {} }); });
  }, [year]);

  const download = async () => {
    setBusy(true);
    try {
      const r = await api.get("/platform/finance/ppn/export.csv", { params: { year }, responseType: "blob" });
      const url = URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = url; a.download = `oryntix-spt-ppn-${year}.csv`; a.click(); URL.revokeObjectURL(url);
    } catch (e) { toast.error("Gagal mengunduh CSV"); } finally { setBusy(false); }
  };

  const t = data?.total || {};
  return (
    <div data-testid="platform-ppn">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-black text-slate-900"><FileSpreadsheet size={22} className="text-[#2F6BFF]" /> SPT PPN Bulanan</h1>
          <p className="text-sm text-slate-500">Ringkasan PPN Keluaran vs Masukan tiap bulan, siap lapor. PPN Neto &gt; 0 = kurang bayar, &lt; 0 = lebih bayar.</p>
        </div>
        <div className="flex items-end gap-2">
          <label className="text-xs text-slate-500">Tahun
            <select value={year} onChange={(e) => setYear(Number(e.target.value))} data-testid="ppn-year" className="mt-1 block rounded-xl border border-[#E7ECF3] bg-white px-3 py-2 text-sm outline-none">{years.map((y) => <option key={y} value={y}>{y}</option>)}</select>
          </label>
          <button onClick={download} disabled={busy || !data} className="btn-grad flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-bold disabled:opacity-50" data-testid="ppn-download">{busy ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />} Unduh CSV</button>
        </div>
      </div>

      {!data ? <p className="mt-6 flex items-center gap-2 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p> : (
        <>
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            <div className="aivora-card p-5" data-testid="ppn-total-out"><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">PPN Keluaran (setahun)</p><p className="mt-2 text-2xl font-black text-slate-900">{rp(t.ppn_out)}</p></div>
            <div className="aivora-card p-5" data-testid="ppn-total-in"><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">PPN Masukan (setahun)</p><p className="mt-2 text-2xl font-black text-slate-900">{rp(t.ppn_in)}</p></div>
            <div className="aivora-card p-5 ring-1 ring-[#2F6BFF]/20" data-testid="ppn-total-net"><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">PPN Disetor (setahun)</p><p className={`mt-2 text-2xl font-black ${t.ppn_net < 0 ? "text-emerald-600" : "text-slate-900"}`}>{rp(t.ppn_net)}</p><p className="text-xs text-slate-500">{t.ppn_net < 0 ? "lebih bayar (kompensasi)" : t.ppn_net > 0 ? "kurang bayar ke negara" : "nihil"}</p></div>
          </div>
          <div className="mt-6 aivora-card overflow-hidden">
            <table className="w-full text-sm" data-testid="ppn-table">
              <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-2.5 text-left">Masa Pajak</th><th className="px-3 py-2.5 text-right">Pendapatan</th><th className="px-3 py-2.5 text-right">PPN Keluaran</th><th className="px-3 py-2.5 text-right">Pengeluaran</th><th className="px-3 py-2.5 text-right">PPN Masukan</th><th className="px-3 py-2.5 text-right">PPN Neto</th><th className="px-4 py-2.5 text-center">Status</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.months.map((m) => { const s = statusOf(m.ppn_net); return (
                  <tr key={m.month} data-testid={`ppn-row-${m.month}`}>
                    <td className="px-4 py-2 font-semibold capitalize text-slate-800">{monthLabel(m.month)}</td>
                    <td className="px-3 py-2 text-right text-slate-700">{rp(m.revenue_idr)}</td>
                    <td className="px-3 py-2 text-right text-slate-700">{rp(m.ppn_out)}</td>
                    <td className="px-3 py-2 text-right text-slate-700">{rp(m.expenses_idr)}</td>
                    <td className="px-3 py-2 text-right text-slate-700">{rp(m.ppn_in)}</td>
                    <td className={`px-3 py-2 text-right font-bold ${m.ppn_net < 0 ? "text-emerald-600" : m.ppn_net > 0 ? "text-slate-900" : "text-slate-400"}`}>{rp(m.ppn_net)}</td>
                    <td className="px-4 py-2 text-center"><span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${s.c}`}>{s.t}</span></td>
                  </tr>); })}
              </tbody>
              <tfoot><tr className="border-t-2 border-slate-200 bg-slate-50 font-bold"><td className="px-4 py-2.5 text-slate-900" data-testid="ppn-foot-total">TOTAL {year}</td><td className="px-3 py-2.5 text-right">{rp(t.revenue_idr)}</td><td className="px-3 py-2.5 text-right">{rp(t.ppn_out)}</td><td className="px-3 py-2.5 text-right">{rp(t.expenses_idr)}</td><td className="px-3 py-2.5 text-right">{rp(t.ppn_in)}</td><td className="px-3 py-2.5 text-right">{rp(t.ppn_net)}</td><td /></tr></tfoot>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
