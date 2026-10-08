import React, { useEffect, useState } from "react";
import { Check, Mic2, Zap } from "lucide-react";
import { api } from "../lib/api";

// Realtime voice model per persona (gpt-realtime-2.1 / 2.1-mini default / 2.0) with live credits/min from platform pricing.
export function VoiceModelPicker({ value, onChange, compact = false }) {
  const [models, setModels] = useState([]);
  useEffect(() => { api.get("/realtime/status").then((r) => setModels(r.data.models || [])).catch(() => {}); }, []);
  const cur = value || models.find((m) => m.default)?.id;
  return (
    <div data-testid="voice-model-picker">
      <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Model Suara (Panggilan Realtime)</label>
      <p className="mb-2 text-xs text-slate-400">Otak percakapan suara saat panggilan. Tarif per menit mengikuti pengaturan platform.</p>
      <div className={`grid gap-2 ${compact ? "grid-cols-1" : "sm:grid-cols-3"}`}>
        {models.map((m) => {
          const on = cur === m.id;
          return (
            <button type="button" key={m.id} onClick={() => onChange(m.id)} data-testid={`voice-model-${m.id}`}
              className={`flex items-start gap-2 rounded-xl border p-3 text-left transition ${on ? "border-[#2F6BFF] bg-[#EEF3FF]" : "border-[#E7ECF3] hover:bg-slate-50"}`}>
              <span className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${on ? "btn-grad border-transparent" : "border-slate-300"}`}>{on && <Check size={10} />}</span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5 text-sm font-bold text-slate-900"><Mic2 size={13} className="text-[#2F6BFF]" /> {m.label}{m.default && <span className="rounded bg-[#2F6BFF]/10 px-1 text-[9px] font-bold uppercase tracking-wider text-[#2F6BFF]">default</span>}</span>
                <span className="block text-xs text-slate-400">{m.tagline}</span>
                <span className="mt-1 flex items-center gap-1 text-[11px] font-semibold text-slate-600" data-testid={`voice-model-rate-${m.id}`}><Zap size={10} /> ~{m.credits_per_min} kredit/menit</span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
