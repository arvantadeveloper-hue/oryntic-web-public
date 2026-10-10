import React, { useEffect, useState } from "react";
import { Sparkles, Check, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import { ResponsiveContainer, BarChart, Bar, XAxis, Tooltip, Cell } from "recharts";
import { api } from "../lib/api";
import { TrialBanner } from "../components/TrialBanner";
import { WalletHistoryTabs } from "../components/WalletHistoryTabs";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n";

const COLORS = ["#00D1FF", "#7C3AED", "#06B6D4", "#F59E0B", "#10B981", "#EF4444"];

export default function Wallet() {
  const { user, setCredits, refreshUser } = useAuth();
  const { t } = useI18n();
  const [wallet, setWallet] = useState(null);
  const [packages, setPackages] = useState([]);
  const [busy, setBusy] = useState(null);
  const highlight = typeof window !== "undefined" && window.location.hash === "#packages";

  const load = () => api.get("/wallet").then((r) => { setWallet(r.data); setCredits(r.data.available); }).catch(() => {});
  useEffect(() => { load(); refreshUser(); api.get("/wallet/packages").then((r) => setPackages(r.data)).catch(() => {}); /* eslint-disable-next-line */ }, []);
  useEffect(() => { if (highlight) setTimeout(() => document.getElementById("packages")?.scrollIntoView({ behavior: "smooth", block: "start" }), 300); }, [highlight]);

  const topup = async (pkg) => {
    setBusy(pkg.id);
    try { const r = await api.post("/wallet/topup", { package_id: pkg.id }); setCredits(r.data.credits); load(); refreshUser(); toast.success(`+${r.data.added} kredit (simulasi)`); }
    catch (e) { toast.error("Gagal"); } finally { setBusy(null); }
  };

  const chartData = (wallet?.breakdown || []).map((b, i) => ({ name: b.feature, credits: b.credits, fill: COLORS[i % COLORS.length] }));
  const cap = Math.max(wallet?.credits_cap || user?.credits_cap || 1, 1);
  const bal = wallet?.available ?? user?.credits ?? 0;

  return (
    <div className="mx-auto max-w-5xl p-5 sm:p-8 lg:p-10 fade-up" data-testid="wallet-page">
      <h1 className="text-3xl font-extrabold text-slate-900">{t("nav.wallet")}</h1>
      <div className="mt-4"><TrialBanner /></div>
      <p className="text-sm text-slate-500">Kredit adalah satuan penggunaan layanan Oryntix (bukan nilai uang langsung).</p>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="aivora-card overflow-hidden p-6" style={{ background: "linear-gradient(135deg, rgba(0,209,255,.14), rgba(124,58,237,.16))" }}>
          <p className="flex items-center gap-2 text-sm text-slate-600"><Sparkles size={16} className="text-[#2F6BFF]" /> {t("wallet.balance")}</p>
          <p className="mt-2 text-5xl font-extrabold text-slate-900" data-testid="wallet-balance">{bal}</p>
          <p className="text-sm text-slate-500">tersedia dari {cap} kredit · {wallet?.consumed ?? 0} terpakai</p>
          <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-white/60"><div className="h-full rounded-full bg-[#2F6BFF]" style={{ width: `${Math.min(100, Math.round((bal / cap) * 100))}%` }} data-testid="wallet-gauge" /></div>
          {wallet?.daily_limit > 0 && <p className="mt-2 text-xs text-slate-600" data-testid="wallet-daily">Kuota hari ini: <b>{Math.max(0, wallet.daily_limit - (wallet.daily_used || 0))}</b> dari {wallet.daily_limit} kredit tersisa</p>}
        </div>
        <div className="aivora-card p-6 lg:col-span-2">
          <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900"><TrendingUp size={15} className="text-[#7C3AED]" /> Penggunaan per fitur</p>
          {chartData.length === 0 ? <p className="py-8 text-center text-sm text-slate-500">Belum ada penggunaan.</p> : (
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={chartData}>
                <XAxis dataKey="name" tick={{ fill: "#94A3B8", fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: "#111C3A", border: "1px solid rgba(0,209,255,.2)", borderRadius: 12, color: "#fff" }} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                <Bar dataKey="credits" radius={[6, 6, 0, 0]}>{chartData.map((e, i) => <Cell key={i} fill={e.fill} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <h2 id="packages" className="mt-10 scroll-mt-6 text-lg font-bold text-slate-900">{t("wallet.topup")} <span className="text-sm font-normal text-slate-500">(simulasi — tanpa pembayaran nyata)</span></h2>
      <div className={`mt-4 grid gap-4 rounded-3xl transition sm:grid-cols-2 lg:grid-cols-5 ${highlight ? "ring-2 ring-[#2F6BFF]/50 ring-offset-4" : ""}`} data-testid="packages-grid">
        {packages.map((p) => (
          <div key={p.id} className={`aivora-card aivora-card-hover relative p-5 ${p.best_value ? "ring-1 ring-[#00D1FF]" : ""}`} data-testid={`pkg-${p.id}`}>
            {p.best_value && <span className="absolute -top-2 left-1/2 -translate-x-1/2 rounded-full btn-grad px-3 py-0.5 text-[10px] font-bold">BEST VALUE</span>}
            <p className="text-sm font-bold text-slate-900">{p.name}</p>
            <p className="mt-2 text-3xl font-extrabold grad-text">{p.credits.toLocaleString("id-ID")}</p>
            <p className="text-xs text-slate-500">kredit</p>
            <p className="mt-3 text-sm font-semibold text-slate-700">Rp {p.price_idr.toLocaleString("id-ID")}</p>
            {p.discount_pct > 0 && <span className="mt-1 inline-block rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700" data-testid={`pkg-discount-${p.id}`}>Hemat {p.discount_pct}%</span>}
            <button onClick={() => topup(p)} disabled={busy === p.id} className="btn-grad mt-4 w-full rounded-xl py-2.5 text-sm" data-testid={`topup-${p.id}`}>{busy === p.id ? "..." : "Beli"}</button>
          </div>
        ))}
      </div>

      <WalletHistoryTabs transactions={wallet?.transactions || []} />
    </div>
  );
}
