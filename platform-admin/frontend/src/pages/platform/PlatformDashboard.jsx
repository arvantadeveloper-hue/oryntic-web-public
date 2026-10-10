import React, { useEffect, useState } from "react";
import { Users, Coins, Wallet, PhoneCall, Loader2, TrendingUp, Scale, Download, FileText, PiggyBank, AlertTriangle, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ComposedChart, Line, Legend, CartesianGrid } from "recharts";
import { api } from "../../lib/api";

export const rp = (n) => `Rp ${Number(n || 0).toLocaleString("id-ID")}`;
export const num = (n) => Number(n || 0).toLocaleString("id-ID");
const monthShort = (ym) => new Date(ym + "-01T00:00:00").toLocaleDateString("id-ID", { month: "short", year: "2-digit" });

function Stat({ icon: Icon, label, value, sub, testid }) {
  return (
    <div className="aivora-card p-5" data-testid={testid}>
      <div className="flex items-center justify-between"><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</p><Icon size={16} className="text-[#2F6BFF]" /></div>
      <p className="mt-2 text-2xl font-black text-slate-900">{value}</p>
      {sub && <p className="text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

function BudgetSummary({ budget }) {
  if (!budget) return null;
  const monthLabel = budget.month ? new Date(budget.month + "-01T00:00:00").toLocaleDateString("id-ID", { month: "long", year: "numeric" }) : "";
  const hasOverall = (budget.monthly_idr || 0) > 0;
  const cats = (budget.categories || []).filter((c) => (c.spent_idr || 0) > 0).sort((a, b) => (b.spent_idr || 0) - (a.spent_idr || 0));
  const configured = hasOverall || (budget.categories || []).some((c) => (c.budget_idr || 0) > 0);
  if (!configured) {
    return (
      <div className="mt-6 aivora-card flex flex-wrap items-center justify-between gap-3 p-5" data-testid="pdash-budget-empty">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#EEF3FF] text-[#2F6BFF]"><PiggyBank size={18} /></span>
          <div><p className="text-sm font-bold text-slate-900">Anggaran bulanan belum diatur</p><p className="text-xs text-slate-500">Atur anggaran pengeluaran untuk memantau sisa & kategori paling boros.</p></div>
        </div>
        <Link to="/expenses" data-testid="pdash-budget-setup" className="inline-flex items-center gap-1.5 rounded-lg bg-[#0B132B] px-3 py-2 text-xs font-bold text-white hover:bg-[#1a2540]">Atur anggaran <ArrowRight size={13} /></Link>
      </div>
    );
  }
  const pct = Math.min(100, budget.pct || 0);
  const barColor = budget.over ? "#F04438" : pct >= 80 ? "#F0A33D" : "#12B76A";
  const topCats = cats.slice(0, 3);
  return (
    <div className="mt-6 grid gap-4 lg:grid-cols-5" data-testid="pdash-budget">
      <div className="aivora-card p-5 lg:col-span-2">
        <div className="flex items-center justify-between">
          <p className="flex items-center gap-2 text-sm font-bold text-slate-900"><PiggyBank size={15} className="text-[#2F6BFF]" /> Anggaran {monthLabel}</p>
          <Link to="/expenses" data-testid="pdash-budget-link" className="inline-flex items-center gap-1 text-xs font-semibold text-[#2F6BFF] hover:underline">Kelola <ArrowRight size={12} /></Link>
        </div>
        {hasOverall ? (
          <>
            <p className="mt-3 text-2xl font-black text-slate-900" data-testid="pdash-budget-remaining">{rp(budget.remaining_idr)} <span className="text-sm font-semibold text-slate-400">sisa</span></p>
            <p className="text-xs text-slate-500">{rp(budget.spent_idr)} terpakai dari {rp(budget.monthly_idr)} · {budget.pct || 0}%</p>
            <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-slate-100"><div className="h-2 rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: barColor }} /></div>
            {budget.over && <p className="mt-2 flex items-center gap-1 text-xs font-semibold text-rose-600" data-testid="pdash-budget-over"><AlertTriangle size={13} /> Melebihi anggaran bulan ini</p>}
          </>
        ) : (
          <p className="mt-3 text-xs text-slate-500">Anggaran total belum diatur. {rp(budget.spent_idr)} terpakai bulan ini.</p>
        )}
      </div>
      <div className="aivora-card p-5 lg:col-span-3" data-testid="pdash-budget-top">
        <p className="text-sm font-bold text-slate-900">Kategori paling boros · {monthLabel}</p>
        <div className="mt-3 space-y-2.5">
          {topCats.map((c) => {
            const cp = c.budget_idr ? Math.min(100, c.pct || 0) : 0;
            const col = c.over ? "#F04438" : (c.pct || 0) >= 80 ? "#F0A33D" : "#2F6BFF";
            return (
              <div key={c.category} data-testid={`pdash-budget-cat-${c.category}`}>
                <div className="flex justify-between text-xs">
                  <span className="font-semibold text-slate-700">{c.label}{c.over && <span className="ml-1 inline-flex items-center gap-0.5 text-rose-600"><AlertTriangle size={11} /> lewat</span>}</span>
                  <span className="text-slate-500">{rp(c.spent_idr)}{c.budget_idr ? ` · ${c.pct}%` : ""}</span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-slate-100"><div className="h-1.5 rounded-full" style={{ width: `${c.budget_idr ? cp : 100}%`, backgroundColor: col, opacity: c.budget_idr ? 1 : 0.4 }} /></div>
              </div>
            );
          })}
          {!topCats.length && <p className="text-xs text-slate-400">Belum ada pengeluaran bulan ini.</p>}
        </div>
      </div>
    </div>
  );
}

export default function PlatformDashboard() {
  const [days, setDays] = useState(30);
  const [s, setS] = useState(null);
  const [budget, setBudget] = useState(null);
  const nowYear = new Date().getFullYear();
  const [pnlYear, setPnlYear] = useState(nowYear);
  const [pnlMode, setPnlMode] = useState("year");
  const todayISO = new Date().toISOString().slice(0, 10);
  const firstOfYearISO = `${nowYear}-01-01`;
  const [rangeFrom, setRangeFrom] = useState(firstOfYearISO);
  const [rangeTo, setRangeTo] = useState(todayISO);
  const [rangeGroup, setRangeGroup] = useState("month");
  const [dl, setDl] = useState("");
  useEffect(() => { setS(null); api.get("/platform/stats", { params: { days } }).then((r) => setS(r.data)).catch(() => setS({})); }, [days]);
  useEffect(() => { api.get("/platform/expenses/budget").then((r) => setBudget(r.data)).catch(() => setBudget({})); }, []);
  const dlPnl = async (fmt) => {
    setDl(fmt);
    try {
      let url_, name_;
      if (pnlMode === "range") {
        const r = await api.get(`/platform/finance/pnl/range/export.${fmt}`, { params: { date_from: rangeFrom, date_to: rangeTo, group: rangeGroup }, responseType: "blob" });
        url_ = URL.createObjectURL(r.data); name_ = `oryntix-laba-rugi-${rangeFrom}-${rangeTo}.${fmt}`;
      } else {
        const r = await api.get(`/platform/finance/pnl/export.${fmt}`, { params: { year: pnlYear }, responseType: "blob" });
        url_ = URL.createObjectURL(r.data); name_ = `oryntix-laba-rugi-${pnlYear}.${fmt}`;
      }
      const a = document.createElement("a"); a.href = url_; a.download = name_; a.click(); URL.revokeObjectURL(url_);
    } catch (e) { /* ignore */ } finally { setDl(""); }
  };
  if (!s) return <p className="flex items-center gap-2 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p>;
  return (
    <div data-testid="platform-dashboard">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-black text-slate-900">Dasbor</h1><p className="text-sm text-slate-500">Ringkasan platform {days} hari terakhir.</p></div>
        <div className="flex gap-1 rounded-full border border-[#E7ECF3] bg-white p-1">{[7, 30, 90].map((d) => <button key={d} onClick={() => setDays(d)} data-testid={`pdash-days-${d}`} className={`rounded-full px-3 py-1 text-xs font-semibold ${days === d ? "bg-[#0B132B] text-white" : "text-slate-600"}`}>{d} hari</button>)}</div>
      </div>
      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat icon={Users} label="Pengguna" value={num(s.users_total)} sub={`+${num(s.users_new)} baru`} testid="pstat-users" />
        <Stat icon={Wallet} label="Pendapatan" value={rp(s.revenue_idr)} sub={`${num(s.topups)} top-up · ${num(s.credits_sold)} kredit terjual`} testid="pstat-revenue" />
        <Stat icon={Coins} label="Kredit terpakai" value={num(s.credits_consumed)} sub={`${num(s.credits_outstanding)} kredit saldo pengguna`} testid="pstat-consumed" />
        <Stat icon={PhoneCall} label="Panggilan aktif" value={num(s.active_calls)} sub={`${num(s.active_rooms)} ruang panggilan hidup`} testid="pstat-calls" />
      </div>
      <BudgetSummary budget={budget} />
      <div className="mt-6 aivora-card p-5" data-testid="pdash-pnl">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="flex items-center gap-2 text-sm font-bold text-slate-900"><Scale size={15} className="text-[#2F6BFF]" /> Pendapatan vs Pengeluaran &amp; Laba Bersih (6 bulan)</p>
          <div className="flex flex-wrap items-center gap-2">
            {(() => { const last = (s.pnl || [])[(s.pnl || []).length - 1]; return last ? <span className="mr-1 text-xs text-slate-500" data-testid="pdash-pnl-latest">Bulan ini: laba <b className={last.profit < 0 ? "text-rose-600" : "text-emerald-600"}>{rp(last.profit)}</b></span> : null; })()}
            <div className="flex gap-1 rounded-lg border border-[#E7ECF3] bg-white p-0.5">
              <button onClick={() => setPnlMode("year")} data-testid="pnl-mode-year" className={`rounded-md px-2 py-1 text-xs font-semibold ${pnlMode === "year" ? "bg-[#0B132B] text-white" : "text-slate-600"}`}>Tahun</button>
              <button onClick={() => setPnlMode("range")} data-testid="pnl-mode-range" className={`rounded-md px-2 py-1 text-xs font-semibold ${pnlMode === "range" ? "bg-[#0B132B] text-white" : "text-slate-600"}`}>Rentang</button>
            </div>
            {pnlMode === "year"
              ? <select value={pnlYear} onChange={(e) => setPnlYear(Number(e.target.value))} data-testid="pnl-year" className="rounded-lg border border-[#E7ECF3] bg-white px-2 py-1.5 text-xs font-semibold outline-none">{Array.from({ length: 5 }, (_, i) => nowYear - i).map((y) => <option key={y} value={y}>{y}</option>)}</select>
              : (<>
                  <input type="date" value={rangeFrom} max={rangeTo} onChange={(e) => setRangeFrom(e.target.value)} data-testid="pnl-range-from" className="rounded-lg border border-[#E7ECF3] bg-white px-2 py-1.5 text-xs font-semibold outline-none" />
                  <span className="text-xs text-slate-400">s/d</span>
                  <input type="date" value={rangeTo} min={rangeFrom} max={todayISO} onChange={(e) => setRangeTo(e.target.value)} data-testid="pnl-range-to" className="rounded-lg border border-[#E7ECF3] bg-white px-2 py-1.5 text-xs font-semibold outline-none" />
                  <select value={rangeGroup} onChange={(e) => setRangeGroup(e.target.value)} data-testid="pnl-range-group" className="rounded-lg border border-[#E7ECF3] bg-white px-2 py-1.5 text-xs font-semibold outline-none"><option value="month">per bulan</option><option value="day">per hari</option></select>
                </>)}
            <button onClick={() => dlPnl("csv")} disabled={!!dl} className="inline-flex items-center gap-1 rounded-lg border border-[#E7ECF3] bg-white px-2.5 py-1.5 text-xs font-bold text-slate-600 hover:border-[#2F6BFF] disabled:opacity-50" data-testid="pnl-csv">{dl === "csv" ? <Loader2 size={12} className="animate-spin" /> : <Download size={12} />} CSV</button>
            <button onClick={() => dlPnl("pdf")} disabled={!!dl} className="inline-flex items-center gap-1 rounded-lg border border-[#E7ECF3] bg-white px-2.5 py-1.5 text-xs font-bold text-slate-600 hover:border-[#2F6BFF] disabled:opacity-50" data-testid="pnl-pdf">{dl === "pdf" ? <Loader2 size={12} className="animate-spin" /> : <FileText size={12} />} PDF</button>
          </div>
        </div>
        {pnlMode === "range" && <p className="mt-1 text-xs text-slate-400" data-testid="pnl-range-hint">Ekspor CSV/PDF mengikuti rentang {rangeFrom} s/d {rangeTo} ({rangeGroup === "month" ? "per bulan" : "per hari"}). Grafik di bawah tetap menampilkan tren 6 bulan.</p>}
        <div className="mt-3 h-64">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={(s.pnl || []).map((p) => ({ ...p, label: monthShort(p.month) }))}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#EEF2F7" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 10 }} width={54} tickFormatter={(v) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(0)}jt` : `${Math.round(v / 1e3)}rb`)} />
              <Tooltip formatter={(v, n) => [rp(v), n]} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar name="Pendapatan" dataKey="revenue_idr" fill="#2F6BFF" radius={[4, 4, 0, 0]} maxBarSize={28} />
              <Bar name="Pengeluaran" dataKey="expenses_idr" fill="#F0A33D" radius={[4, 4, 0, 0]} maxBarSize={28} />
              <Line name="Laba Bersih" type="monotone" dataKey="profit" stroke="#12B76A" strokeWidth={2.5} dot={{ r: 3 }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="mt-6 grid gap-4 lg:grid-cols-5">
        <div className="aivora-card p-5 lg:col-span-3" data-testid="pdash-daily">
          <p className="flex items-center gap-2 text-sm font-bold text-slate-900"><TrendingUp size={15} className="text-[#2F6BFF]" /> Kredit terpakai per hari</p>
          <div className="mt-3 h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={s.daily || []}><XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(5)} interval="preserveStartEnd" /><YAxis tick={{ fontSize: 10 }} width={40} /><Tooltip formatter={(v) => [`${num(v)} kredit`, ""]} /><Bar dataKey="credits" fill="#2F6BFF" radius={[4, 4, 0, 0]} /></BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="aivora-card p-5 lg:col-span-2" data-testid="pdash-features">
          <p className="text-sm font-bold text-slate-900">Per fitur</p>
          <div className="mt-3 space-y-2">
            {(s.by_feature || []).slice(0, 8).map((f) => { const pct = s.credits_consumed ? Math.round((f.credits / s.credits_consumed) * 100) : 0; return (
              <div key={f.feature}><div className="flex justify-between text-xs"><span className="font-semibold text-slate-700">{f.label}</span><span className="text-slate-500">{num(f.credits)} · {pct}%</span></div><div className="mt-1 h-1.5 rounded-full bg-slate-100"><div className="h-1.5 rounded-full bg-[#2F6BFF]" style={{ width: `${pct}%` }} /></div></div>); })}
            {!(s.by_feature || []).length && <p className="text-xs text-slate-400">Belum ada pemakaian.</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
