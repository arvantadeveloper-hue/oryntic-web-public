import React from "react";
import { Phone, MessageSquare, Repeat } from "lucide-react";

export const OFFSETS = [{ v: 10, l: "10 menit" }, { v: 30, l: "30 menit" }, { v: 60, l: "1 jam" }, { v: 1440, l: "1 hari" }];
export const REPEATS = [{ v: "none", l: "Tidak berulang" }, { v: "daily", l: "Setiap hari" }, { v: "weekly", l: "Setiap minggu" }, { v: "monthly", l: "Setiap bulan" }];
export const repeatLabel = (r) => ({ daily: "setiap hari", weekly: "setiap minggu", monthly: "setiap bulan" }[r] || "");
export const offsetLabel = (m) => (m % 1440 === 0 ? `${m / 1440} hari` : m % 60 === 0 ? `${m / 60} jam` : `${m} menit`);

// Shared "how & when to remind me" chooser for reminders and calendar events.
export function RemindOptions({ mode, offsets, onMode, onOffsets, personas = [], personaId, onPersona, repeat, onRepeat, compact = false }) {
  const toggle = (v) => onOffsets(offsets.includes(v) ? offsets.filter((x) => x !== v) : [...offsets, v].sort((a, b) => a - b));
  return (
    <div className={`grid gap-3 ${compact ? "" : "sm:grid-cols-2 lg:grid-cols-4"}`} data-testid="remind-options">
      <div>
        <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">Cara ingatkan</label>
        <div className="flex gap-1.5">
          {[["call", Phone, "Panggilan"], ["chat", MessageSquare, "Chat"]].map(([m, Icon, l]) => (
            <button type="button" key={m} onClick={() => onMode(m)} data-testid={`remind-mode-${m}`} aria-pressed={mode === m}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg border px-2 py-2 text-xs font-bold transition ${mode === m ? "border-[#2F6BFF] bg-[#EEF3FF] text-[#2F6BFF]" : "border-[#E7ECF3] text-slate-600 hover:bg-slate-50"}`}>
              <Icon size={13} /> {l}
            </button>
          ))}
        </div>
      </div>
      <div>
        <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">Ingatkan sebelum</label>
        <div className="flex flex-wrap gap-1.5">
          {OFFSETS.map((o) => (
            <button type="button" key={o.v} onClick={() => toggle(o.v)} data-testid={`remind-offset-${o.v}`} aria-pressed={offsets.includes(o.v)}
              className={`rounded-full border px-2.5 py-1 text-xs font-semibold transition ${offsets.includes(o.v) ? "border-[#2F6BFF] bg-[#2F6BFF] text-white" : "border-[#E7ECF3] text-slate-600 hover:bg-slate-50"}`}>{o.l}</button>
          ))}
        </div>
      </div>
      {onRepeat && (
        <div>
          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">Pengulangan</label>
          <select className="input-dark py-2 text-sm" value={repeat || "none"} onChange={(e) => onRepeat(e.target.value)} data-testid="remind-repeat">
            {REPEATS.map((r) => <option key={r.v} value={r.v}>{r.l}</option>)}
          </select>
        </div>
      )}
      {onPersona && (
        <div>
          <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">Asisten</label>
          <select className="input-dark py-2 text-sm" value={personaId || ""} onChange={(e) => onPersona(e.target.value)} data-testid="remind-persona">
            <option value="">Oryntix</option>
            {personas.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      )}
    </div>
  );
}

export function RemindSummary({ remind, className = "" }) {
  if (!remind) return null;
  const Icon = remind.mode === "chat" ? MessageSquare : Phone;
  const rep = repeatLabel(remind.repeat);
  return <span className={`inline-flex items-center gap-1 ${className}`} data-testid="remind-summary"><Icon size={11} /> {remind.mode === "chat" ? "chat" : "panggilan"} · {(remind.offsets || []).map(offsetLabel).join(", ")} sebelum{rep && <span className="inline-flex items-center gap-0.5" data-testid="remind-repeat-label"> · <Repeat size={11} /> {rep}</span>}</span>;
}
