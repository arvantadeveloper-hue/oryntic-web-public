import React from "react";
import { useNavigate } from "react-router-dom";
import { Gift, AlertTriangle } from "lucide-react";
import { useAuth } from "../context/AuthContext";

// Trial status banner for workspace owners on the trial plan.
export function TrialBanner({ compact = false }) {
  const { user } = useAuth();
  const nav = useNavigate();
  if (!user || user.plan !== "trial" || user.role !== "admin") return null;
  const ends = user.trial_ends_at ? new Date(user.trial_ends_at) : null;
  const daysLeft = ends ? Math.ceil((ends - Date.now()) / 86400000) : 0;
  const expired = daysLeft <= 0;
  return (
    <div data-testid="trial-banner" className={`flex flex-wrap items-center gap-3 rounded-2xl border px-4 py-3 ${expired ? "border-[#EF4444]/30 bg-[#FEF2F2]" : "border-[#F59E0B]/30 bg-[#FFFBEB]"} ${compact ? "text-xs" : "text-sm"}`}>
      <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${expired ? "bg-[#EF4444]/10 text-[#EF4444]" : "bg-[#F59E0B]/15 text-[#D97706]"}`}>{expired ? <AlertTriangle size={16} /> : <Gift size={16} />}</span>
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-slate-900">{expired ? "Masa percobaan berakhir" : `Paket percobaan · ${daysLeft} hari lagi`}</p>
        <p className="text-xs text-slate-600">{expired ? "Beli paket kredit untuk melanjutkan penggunaan AI." : `Kuota ${user.daily_credit_limit} kredit/hari · sisa saldo ${user.credits} kredit. Beli paket kapan saja untuk membuka kuota penuh.`}</p>
      </div>
      <button onClick={() => nav("/wallet")} data-testid="trial-upgrade-btn" className="btn-primary py-2 text-xs">Beli Paket Kredit</button>
    </div>
  );
}
