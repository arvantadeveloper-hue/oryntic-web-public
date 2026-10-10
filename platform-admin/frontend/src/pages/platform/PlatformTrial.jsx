import React, { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { api } from "../../lib/api";
import { TrialCard } from "../../components/PlatformPricingCards";
import { RateLimitsCard } from "../../components/RateLimitsCard";

export default function PlatformTrial() {
  const [trial, setTrial] = useState(null);
  useEffect(() => { api.get("/platform/trial").then((r) => setTrial(r.data.trial)).catch(() => setTrial({})); }, []);
  return (
    <div data-testid="platform-trial">
      <h1 className="text-2xl font-black text-slate-900">Trial & Batas</h1>
      <p className="text-sm text-slate-500">Paket percobaan untuk pendaftar baru dan batas pemakaian (rate limit) seluruh platform.</p>
      <div className="mt-6 space-y-5">
        {trial ? <TrialCard trial={trial} onSaved={setTrial} /> : <p className="flex items-center gap-2 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p>}
        <RateLimitsCard />
      </div>
    </div>
  );
}
