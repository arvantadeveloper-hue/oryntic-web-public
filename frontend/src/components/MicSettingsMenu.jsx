import React, { useEffect, useState } from "react";
import { Settings2 } from "lucide-react";
import { Popover, PopoverTrigger, PopoverContent } from "./ui/popover";
import { Switch } from "./ui/switch";
import { SENSITIVITIES, SENS_LABEL, SENS_HINT } from "../lib/micPipeline";

const pct = (v) => `${Math.round(Math.min(100, Math.max(0, ((20 * Math.log10(Math.max(v || 1e-4, 1e-4))) + 60) / 60 * 100)))}%`;

// Gear button → context menu with mic sensitivity, AI noise suppression and a live level meter.
export function MicSettingsMenu({ prefs, onChange, pipeline }) {
  const [open, setOpen] = useState(false);
  const [meter, setMeter] = useState(null);

  useEffect(() => {
    if (!open || !pipeline) return undefined;
    return pipeline.onMeter((m) => setMeter(m));
  }, [open, pipeline]);

  const noiseAvailable = !pipeline || pipeline.hasNoise;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button data-testid="mic-settings-btn" title="Pengaturan mikrofon" className={`flex h-14 w-14 items-center justify-center rounded-full text-white transition ${open ? "bg-white/25" : "bg-white/10 hover:bg-white/20"}`}>
          <Settings2 size={22} />
        </button>
      </PopoverTrigger>
      <PopoverContent side="top" align="center" sideOffset={12} className="z-[120] w-80 rounded-2xl border-white/10 bg-[#0f172a] p-4 text-white shadow-2xl" data-testid="mic-settings-menu">
        <p className="text-[11px] font-bold uppercase tracking-wider text-white/50">Pengaturan Mikrofon</p>

        <p className="mt-3 text-sm font-semibold">Sensitivitas</p>
        <div className="mt-1.5 grid grid-cols-3 gap-1 rounded-xl bg-white/5 p-1">
          {SENSITIVITIES.map((s) => (
            <button key={s} data-testid={`mic-sens-${s}`} onClick={() => onChange({ ...prefs, sensitivity: s })}
              className={`rounded-lg py-1.5 text-xs font-semibold transition ${prefs.sensitivity === s ? "bg-[#2F6BFF] text-white" : "text-white/70 hover:bg-white/10"}`}>{SENS_LABEL[s]}</button>
          ))}
        </div>
        <p className="mt-1.5 text-[11px] leading-relaxed text-white/50">{SENS_HINT[prefs.sensitivity]}</p>

        <div className="mt-4 flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold">Peredam bising (AI)</p>
            <p className="text-[11px] text-white/50">{noiseAvailable ? "RNNoise — meredam kipas, ketikan, lalu lintas" : "Tidak didukung di browser ini"}</p>
          </div>
          <Switch data-testid="mic-noise-toggle" checked={!!prefs.noise} disabled={!noiseAvailable} onCheckedChange={(v) => onChange({ ...prefs, noise: v })} className="data-[state=checked]:bg-[#2F6BFF] data-[state=unchecked]:bg-white/20" />
        </div>

        <div className="mt-4" data-testid="mic-meter">
          <div className="flex items-center justify-between text-[11px] text-white/50">
            <span>Level suara Anda</span>
            <span className={meter?.open ? "font-bold text-emerald-300" : ""}>{!pipeline?.ready ? "—" : meter?.open ? "Lolos ke asisten" : "Latar (diabaikan)"}</span>
          </div>
          <div className="relative mt-1.5 h-2 overflow-visible rounded-full bg-white/10">
            <div className={`h-full rounded-full transition-[width] duration-75 ${meter?.open ? "bg-emerald-400" : "bg-white/40"}`} style={{ width: pct(meter?.level) }} />
            <span className="absolute -top-[3px] h-3.5 w-0.5 rounded bg-amber-300" style={{ left: pct(meter?.threshold) }} />
          </div>
          <p className="mt-1.5 text-[11px] text-white/50">Suara di bawah garis kuning dianggap latar dan tidak dikirim.</p>
        </div>
      </PopoverContent>
    </Popover>
  );
}
