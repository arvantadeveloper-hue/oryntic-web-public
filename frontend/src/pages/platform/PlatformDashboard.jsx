import React, { useEffect, useState } from "react";
import { Users, Coins, Wallet, PhoneCall, Loader2, TrendingUp } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { api } from "../../lib/api";

export const rp = (n) => `Rp ${Number(n || 0).toLocaleString("id-ID")}`;
export const num = (n) => Number(n || 0).toLocaleString("id-ID");

function Stat({ icon: Icon, label, value, sub, testid }) {
  return (
    <div className="aivora-card p-5" data-testid={testid}>
      <div className="flex items-center justify-between"><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</p><Icon size={16} className="text-[#2F6BFF]" /></div>
      <p className="mt-2 text-2xl font-black text-slate-900">{value}</p>
      {sub && <p className="text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

export default function PlatformDashboard() {
  const [days, setDays] = useState(30);
  const [s, setS] = useState(null);
  useEffect(() => { setS(null); api.get("/platform/stats", { params: { days } }).then((r) => setS(r.data)).catch(() => setS({})); }, [days]);
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
