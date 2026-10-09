import React, { useEffect, useState } from "react";
import { Mic2, Zap, Lock } from "lucide-react";
import { api } from "../lib/api";

// Voice model is locked platform-wide to GPT-Live; the persona's own "brain" model does the reasoning during calls (delegation).
export function VoiceModelPicker({ compact = false }) {
  const [m, setM] = useState(null);
  useEffect(() => { api.get("/realtime/status").then((r) => setM((r.data.models || []).find((x) => x.default) || r.data.models?.[0] || null)).catch(() => {}); }, []);
  return (
    <div data-testid="voice-model-picker">
      <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Model Suara (Panggilan)</label>
      <p className="mb-2 text-xs text-slate-400">Semua panggilan memakai GPT-Live. Penalaran & alat di dalam panggilan tetap memakai model otak asisten ini.</p>
      <div className={`flex items-start gap-2 rounded-xl border border-[#2F6BFF] bg-[#EEF3FF] p-3 ${compact ? "" : "sm:max-w-sm"}`} data-testid="voice-model-gpt-live-1">
        <Lock size={14} className="mt-0.5 shrink-0 text-[#2F6BFF]" />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5 text-sm font-bold text-slate-900"><Mic2 size={13} className="text-[#2F6BFF]" /> {m?.label || "GPT-Live"}</span>
          <span className="block text-xs text-slate-400">{m?.tagline || "Model suara terbaru"}</span>
          {m && <span className="mt-1 flex items-center gap-1 text-[11px] font-semibold text-slate-600" data-testid="voice-model-rate-gpt-live-1"><Zap size={10} /> ~{m.credits_per_min} kredit/menit</span>}
        </span>
      </div>
    </div>
  );
}
