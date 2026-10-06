import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { X, Sparkles, Check, Loader2, Gift, Zap } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";

// "Pilih Paket" — trial → paid explainer + package picker (opened from the sidebar "Upgrade Plan" button).
export function UpgradePlanDialog({ onClose }) {
  const { user, refreshUser } = useAuth();
  const nav = useNavigate();
  const [packages, setPackages] = useState(null);
  const [busy, setBusy] = useState("");
  useEffect(() => { api.get("/wallet/packages").then((r) => setPackages(r.data)).catch(() => setPackages([])); }, []);
  useEffect(() => { const k = (e) => e.key === "Escape" && onClose(); window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [onClose]);
  const trial = user?.plan === "trial";
  const daysLeft = user?.trial_ends_at ? Math.max(0, Math.ceil((new Date(user.trial_ends_at) - Date.now()) / 86400000)) : 0;
  const buy = async (p) => {
    setBusy(p.id);
    try { const r = await api.post("/wallet/topup", { package_id: p.id }); await refreshUser(); toast.success(`+${r.data.added} kredit — paket ${p.name} aktif (simulasi)`); onClose(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal membeli paket"); }
    finally { setBusy(""); }
  };
  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center p-4" data-testid="upgrade-dialog">
      <div className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-2xl overflow-hidden rounded-3xl border border-[#E7ECF3] bg-white shadow-2xl fade-up">
        <button onClick={onClose} className="absolute right-4 top-4 z-10 text-slate-400 hover:text-slate-700" data-testid="upgrade-close"><X size={18} /></button>
        <div className="sidebar-dark p-6 text-white">
          <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.18em] text-white/60"><Sparkles size={13} /> Pilih Paket</p>
          <h3 className="mt-2 text-2xl font-black">Buka kuota penuh untuk tim AI Anda</h3>
          {trial
            ? <p className="mt-2 text-sm text-white/75">Anda sedang di <b>paket percobaan</b> ({daysLeft} hari lagi): sisa saldo <b>{user?.credits}</b> kredit dengan batas <b>{user?.daily_credit_limit}</b> kredit/hari. Membeli paket mana pun menghapus batas harian dan menambah saldo seketika.</p>
            : <p className="mt-2 text-sm text-white/75">Saldo saat ini <b>{user?.credits}</b> kredit. Tambah paket kapan saja — kredit tidak hangus.</p>}
          <div className="mt-4 grid gap-2 text-xs text-white/80 sm:grid-cols-3">
            {[["Tanpa batas harian", Zap], ["Kredit tidak kedaluwarsa", Gift], ["Semua model & panggilan suara", Check]].map(([l, I]) => <span key={l} className="flex items-center gap-1.5 rounded-lg bg-white/10 px-2.5 py-1.5"><I size={12} /> {l}</span>)}
          </div>
        </div>
        <div className="p-6">
          {packages === null ? <p className="flex items-center gap-2 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat paket…</p> : (
            <div className="grid gap-3 sm:grid-cols-3">
              {packages.map((p) => (
                <div key={p.id} className={`relative rounded-2xl border p-4 ${p.best_value ? "border-[#2F6BFF] bg-[#EEF3FF]/60" : "border-[#E7ECF3]"}`} data-testid={`upgrade-pkg-${p.id}`}>
                  {p.best_value && <span className="absolute -top-2.5 left-4 rounded-full bg-[#2F6BFF] px-2 py-0.5 text-[10px] font-bold text-white">Paling hemat</span>}
                  <p className="text-sm font-bold text-slate-900">{p.name}</p>
                  <p className="mt-1 text-2xl font-black text-slate-900">{p.credits.toLocaleString("id-ID")} <span className="text-xs font-normal text-slate-500">kredit</span></p>
                  <p className="text-xs text-slate-500">Rp {Number(p.price_idr).toLocaleString("id-ID")}{p.discount_pct > 0 && <span className="ml-1.5 rounded-full bg-emerald-50 px-1.5 py-0.5 text-[10px] font-bold text-emerald-700">Hemat {p.discount_pct}%</span>}</p>
                  <button onClick={() => buy(p)} disabled={!!busy} className="btn-grad mt-3 w-full rounded-xl py-2 text-xs" data-testid={`upgrade-buy-${p.id}`}>{busy === p.id ? <Loader2 size={13} className="mx-auto animate-spin" /> : "Pilih paket"}</button>
                </div>
              ))}
            </div>
          )}
          <div className="mt-5 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
            <span>Pembayaran saat ini bersifat simulasi (belum terhubung ke gateway pembayaran).</span>
            <button onClick={() => { onClose(); nav("/wallet#packages"); }} className="font-semibold text-[#2F6BFF] hover:underline" data-testid="upgrade-open-wallet">Lihat detail di Dompet →</button>
          </div>
        </div>
      </div>
    </div>
  );
}
