import React, { useEffect, useState } from "react";
import { Zap } from "lucide-react";
import { api } from "../lib/api";

// Read-only: the GPT-Live per-minute price is a catalog component (openai/gpt-live/per_minute)
export function RealtimePricingCard() {
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/admin/realtime-pricing").then((r) => setD(r.data)).catch(() => {}); }, []);
  if (!d) return null;
  return (
    <div className="aivora-card p-5" data-testid="realtime-pricing-card">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#2F6BFF]/10 text-[#2F6BFF]"><Zap size={18} /></span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-bold text-slate-900">Panggilan Suara GPT-Live</p>
          <p className="text-xs text-slate-500">Model {d.model} · {d.enabled ? "Aktif" : "Nonaktif (OPENAI_API_KEY belum diatur)"}</p>
        </div>
        <span className="rounded-full bg-[#10B981]/15 px-3 py-1 text-xs font-bold text-[#10B981]" data-testid="rt-credits-per-min">{d.credits_per_min} kredit/menit</span>
      </div>
      <p className="mt-3 text-xs text-slate-500" data-testid="rt-pricing-formula">
        ${Number(d.provider_usd_per_min).toFixed(3)}/menit (katalog <code className="rounded bg-slate-100 px-1">{d.catalog_path}</code>) × (1 + margin {d.margin_pct}%) × (1 + PPN {d.tax_pct}%) ÷ nilai kredit = <b>{d.credits_per_min} kredit/menit</b>, ditagih per detik.
        Ubah harga per menit di tab <b>Katalog Harga</b>; model otak persona ditagih terpisah per token.
      </p>
    </div>
  );
}
