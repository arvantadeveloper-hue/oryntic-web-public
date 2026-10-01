import React, { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, AreaChart, Area, CartesianGrid } from "recharts";
import { Loader2, TrendingUp } from "lucide-react";
import { api } from "../lib/api";

const COLORS = ["#2F6BFF", "#7C3AED", "#10B981", "#F59E0B", "#EC4899", "#22B8FF", "#F97316", "#64748B"];
const fmt = (n) => (n || 0).toLocaleString("id-ID");

function Card({ title, children, testId }) {
  return (
    <div className="aivora-card p-4" data-testid={testId}>
      <p className="text-sm font-bold text-slate-900">{title}</p>
      <div className="mt-3">{children}</div>
    </div>
  );
}

export function UsageReport() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/admin/usage-report?days=${days}`).then((r) => setData(r.data)).catch(() => {}).finally(() => setLoading(false));
  }, [days]);

  const top = data?.by_user?.[0];
  return (
    <section className="mt-8" data-testid="usage-report">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900">Laporan Pemakaian Kredit</h2>
          <p className="text-xs text-slate-500">Siapa dan fitur apa yang paling banyak memakai kredit workspace.</p>
        </div>
        <div className="flex gap-1 rounded-xl border border-[#E6EAF2] bg-white p-1">
          {[7, 30, 90].map((d) => (
            <button key={d} onClick={() => setDays(d)} data-testid={`usage-range-${d}`} className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${days === d ? "bg-[#2F6BFF] text-white" : "text-slate-600 hover:bg-slate-50"}`}>{d} hari</button>
          ))}
        </div>
      </div>

      {loading && !data ? <div className="flex justify-center py-10"><Loader2 className="animate-spin text-[#2F6BFF]" /></div> : data && (
        <>
          <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <div className="aivora-card p-4" data-testid="usage-total"><p className="text-xs text-slate-500">Total kredit terpakai</p><p className="text-2xl font-bold text-slate-900">{fmt(data.total)}</p></div>
            <div className="aivora-card p-4"><p className="text-xs text-slate-500">Rata-rata / hari</p><p className="text-2xl font-bold text-slate-900">{fmt(Math.round(data.total / data.days))}</p></div>
            <div className="aivora-card p-4"><p className="text-xs text-slate-500">Aktivitas</p><p className="text-2xl font-bold text-slate-900">{fmt(data.events)}</p></div>
            <div className="aivora-card p-4" data-testid="usage-top-user"><p className="text-xs text-slate-500">Paling boros</p><p className="truncate text-base font-bold text-slate-900">{top ? top.name : "-"}</p>{top && <p className="text-xs text-slate-500">{fmt(top.credits)} kredit</p>}</div>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title="Per anggota" testId="usage-by-user">
              {data.by_user.length === 0 ? <p className="py-8 text-center text-sm text-slate-400">Belum ada pemakaian.</p> : (
                <ResponsiveContainer width="100%" height={Math.max(160, data.by_user.length * 40)}>
                  <BarChart data={data.by_user} layout="vertical" margin={{ left: 8, right: 24 }}>
                    <XAxis type="number" hide />
                    <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 12, fill: "#475569" }} axisLine={false} tickLine={false} />
                    <Tooltip formatter={(v) => [`${fmt(v)} kredit`, "Pemakaian"]} cursor={{ fill: "#F1F5F9" }} />
                    <Bar dataKey="credits" radius={[0, 8, 8, 0]} label={{ position: "right", fontSize: 11, fill: "#334155", formatter: fmt }}>
                      {data.by_user.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </Card>
            <Card title="Per fitur" testId="usage-by-feature">
              {data.by_feature.length === 0 ? <p className="py-8 text-center text-sm text-slate-400">Belum ada pemakaian.</p> : (
                <div className="flex flex-col items-center gap-4 sm:flex-row">
                  <ResponsiveContainer width="55%" height={200}>
                    <PieChart>
                      <Pie data={data.by_feature} dataKey="credits" nameKey="label" innerRadius={55} outerRadius={85} paddingAngle={2} stroke="none">
                        {data.by_feature.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                      </Pie>
                      <Tooltip formatter={(v, n) => [`${fmt(v)} kredit`, n]} />
                    </PieChart>
                  </ResponsiveContainer>
                  <ul className="flex-1 space-y-1.5 text-xs">
                    {data.by_feature.map((f, i) => (
                      <li key={f.feature} className="flex items-center justify-between gap-2" data-testid={`usage-feature-${f.feature}`}>
                        <span className="flex items-center gap-2 text-slate-600"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: COLORS[i % COLORS.length] }} />{f.label}</span>
                        <span className="font-semibold text-slate-900">{fmt(f.credits)} <span className="font-normal text-slate-400">({data.total ? Math.round((f.credits / data.total) * 100) : 0}%)</span></span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>
          </div>

          <div className="mt-4">
            <Card title={<span className="flex items-center gap-2"><TrendingUp size={15} className="text-[#2F6BFF]" /> Tren harian</span>} testId="usage-daily">
              <ResponsiveContainer width="100%" height={180}>
                <AreaChart data={data.daily} margin={{ left: 0, right: 8 }}>
                  <defs><linearGradient id="ug" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#2F6BFF" stopOpacity={0.35} /><stop offset="100%" stopColor="#2F6BFF" stopOpacity={0} /></linearGradient></defs>
                  <CartesianGrid vertical={false} stroke="#EEF2F7" />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94A3B8" }} tickFormatter={(d) => d.slice(5)} interval="preserveStartEnd" axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 10, fill: "#94A3B8" }} axisLine={false} tickLine={false} width={40} />
                  <Tooltip formatter={(v) => [`${fmt(v)} kredit`, "Pemakaian"]} />
                  <Area type="monotone" dataKey="credits" stroke="#2F6BFF" strokeWidth={2} fill="url(#ug)" />
                </AreaChart>
              </ResponsiveContainer>
            </Card>
          </div>
        </>
      )}
    </section>
  );
}
