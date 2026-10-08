import React, { useEffect, useState } from "react";
import { Globe, Code2, ImageIcon, Search, Zap, Check } from "lucide-react";
import { api } from "../lib/api";

const ICON = { web_search: Globe, google_search: Search, code_interpreter: Code2, code_execution: Code2, image_generation: ImageIcon };

// Provider built-in tools (web search, code execution, image generation) a persona may use; filtered by the provider of its model.
export function ToolsPicker({ modelKey, value = [], onChange, compact = false }) {
  const [tools, setTools] = useState([]);
  const [models, setModels] = useState([]);
  useEffect(() => {
    api.get("/tools").then((r) => setTools(r.data.tools || [])).catch(() => {});
    api.get("/models").then((r) => setModels(r.data.models || [])).catch(() => {});
  }, []);
  const provider = (models.find((m) => m.id === modelKey) || {}).provider;
  const list = tools.filter((t) => t.provider === provider);
  if (!provider || !list.length) return null;
  const toggle = (id) => onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id]);
  return (
    <div data-testid="tools-picker">
      <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Kemampuan Tambahan ({list[0].provider_label})</label>
      <p className="mb-2 text-xs text-slate-400">Alat bawaan model: asisten memutuskan sendiri kapan memakainya. Biaya per pemakaian ditambahkan ke biaya pesan.</p>
      <div className={`grid gap-2 ${compact ? "grid-cols-1" : "sm:grid-cols-3"}`}>
        {list.map((t) => {
          const on = value.includes(t.id);
          const Icon = ICON[t.id.split(":")[1]] || Zap;
          const off = !t.available;
          return (
            <button type="button" key={t.id} disabled={off} onClick={() => toggle(t.id)} data-testid={`tool-toggle-${t.id.replace(":", "-")}`} aria-pressed={on}
              className={`flex items-start gap-2 rounded-xl border p-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${on ? "border-[#2F6BFF] bg-[#EEF3FF]" : "border-[#E7ECF3] hover:bg-slate-50"}`}>
              <span className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border ${on ? "btn-grad border-transparent text-white" : "border-slate-300"}`}>{on && <Check size={10} />}</span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5 text-sm font-bold text-slate-900"><Icon size={13} className="text-[#2F6BFF]" /> {t.label}</span>
                <span className="block text-xs text-slate-400">{t.desc}</span>
                <span className="mt-1 flex items-center gap-1 text-[11px] font-semibold text-slate-600" data-testid={`tool-rate-${t.id.replace(":", "-")}`}>
                  <Zap size={10} /> {t.credits > 0 ? `+${t.credits} kredit / ${t.unit}` : "hanya biaya token"}{off ? " · kunci provider belum diatur" : ""}
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
