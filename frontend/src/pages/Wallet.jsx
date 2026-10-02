import { LoadMore } from "../components/ConversationTools";
import React, { useEffect, useState } from "react";
import { Sparkles, Check, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import { ResponsiveContainer, BarChart, Bar, XAxis, Tooltip, Cell } from "recharts";
import { api } from "../lib/api";
import { TrialBanner } from "../components/TrialBanner";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n";

const COLORS = ["#00D1FF", "#7C3AED", "#06B6D4", "#F59E0B", "#10B981", "#EF4444"];

export default function Wallet() {
  const { user, setCredits } = useAuth();
  const { t } = useI18n();
  const [shown, setShown] = useState(20);
  const [wallet, setWallet] = useState(null);
  const [packages, setPackages] = useState([]);
  const [busy, setBusy] = useState(null);

  const load = () => api.get("/wallet").then((r) => setWallet(r.data)).catch(() => {});
  useEffect(() => { load(); api.get("/wallet/packages").then((r) => setPackages(r.data)).catch(() => {}); }, []);

  const topup = async (pkg) => {
    setBusy(pkg.id);
    try { const r = await api.post("/wallet/topup", { package_id: pkg.id }); setCredits(r.data.credits); load(); toast.success(`+${r.data.added} kredit (simulasi)`); }
    catch (e) { toast.error("Gagal"); } finally { setBusy(null); }
  };

  const chartData = (wallet?.breakdown || []).map((b, i) => ({ name: b.feature, credits: b.credits, fill: COLORS[i % COLORS.length] }));

  return (
    <div className="mx-auto max-w-5xl p-5 sm:p-8 lg:p-10 fade-up" data-testid="wallet-page">
      <h1 className="text-3xl font-extrabold text-slate-900">{t("nav.wallet")}</h1>
      <div className="mt-4"><TrialBanner /></div>
      <p className="text-sm text-slate-500">Kredit adalah satuan penggunaan layanan Oryntix (bukan nilai uang langsung).</p>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="aivora-card overflow-hidden p-6" style={{ background: "linear-gradient(135deg, rgba(0,209,255,.14), rgba(124,58,237,.16))" }}>
          <p className="flex items-center gap-2 text-sm text-slate-600"><Sparkles size={16} className="text-[#2F6BFF]" /> {t("wallet.balance")}</p>
          <p className="mt-2 text-5xl font-extrabold text-slate-900" data-testid="wallet-balance">{wallet?.available ?? user?.credits ?? 0}</p>
          <p className="text-sm text-slate-500">tersedia · {wallet?.consumed ?? 0} terpakai</p>
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

      <h2 className="mt-10 text-lg font-bold text-slate-900">{t("wallet.topup")} <span className="text-sm font-normal text-slate-500">(simulasi — tanpa pembayaran nyata)</span></h2>
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {packages.map((p) => (
          <div key={p.id} className={`aivora-card aivora-card-hover relative p-5 ${p.best_value ? "ring-1 ring-[#00D1FF]" : ""}`} data-testid={`pkg-${p.id}`}>
            {p.best_value && <span className="absolute -top-2 left-1/2 -translate-x-1/2 rounded-full btn-grad px-3 py-0.5 text-[10px] font-bold">BEST VALUE</span>}
            <p className="text-sm font-bold text-slate-900">{p.name}</p>
            <p className="mt-2 text-3xl font-extrabold grad-text">{p.credits}</p>
            <p className="text-xs text-slate-500">kredit</p>
            <p className="mt-3 text-sm text-slate-600">Rp {p.price_idr.toLocaleString("id-ID")}</p>
            <button onClick={() => topup(p)} disabled={busy === p.id} className="btn-grad mt-4 w-full rounded-xl py-2.5 text-sm" data-testid={`topup-${p.id}`}>{busy === p.id ? "..." : "Beli"}</button>
          </div>
        ))}
      </div>

      <h2 className="mt-10 text-lg font-bold text-slate-900">{t("wallet.history")}</h2>
      <div className="mt-4 aivora-card divide-y divide-slate-100">
        {(wallet?.transactions || []).length === 0 ? <p className="p-6 text-sm text-slate-500">Belum ada transaksi.</p> :
          wallet.transactions.slice(0, shown).map((tx) => (
            <div key={tx.id} className="flex items-center justify-between px-5 py-3" data-testid={`txn-${tx.id}`}>
              <div>
                <p className="text-sm text-slate-700">{tx.description}</p>
                <p className="text-xs text-slate-500">{new Date(tx.created_at).toLocaleString()}</p>
              </div>
              <span className={`text-sm font-semibold ${tx.amount >= 0 ? "text-[#10B981]" : "text-[#EF4444]"}`}>{tx.amount >= 0 ? "+" : ""}{tx.amount}</span>
            </div>
          ))}
          {(wallet?.transactions?.length || 0) > shown && <LoadMore onClick={() => setShown((n) => n + 20)} testid="tx-load-more" />}
      </div>
    </div>
  );
}
