import React from "react";
import { Loader2 } from "lucide-react";
import { usePricingDraft, NumField, SaveBar } from "./pricingDraft";

const FIELD = { text: "text_usd_per_1k_chars", image: "image_usd", profile: "profile_usd", stt: "stt_usd", tts: "tts_usd", realtime_call: "provider_usd_per_min", vision: "vision_usd", call_bandwidth: "bandwidth_usd_per_gb", video: "video_usd_per_sec" };
const RT = [["rt_audio_in_usd_1m", "Audio masuk"], ["rt_audio_out_usd_1m", "Audio keluar"], ["rt_text_in_usd_1m", "Teks masuk"], ["rt_text_out_usd_1m", "Teks keluar"], ["rt_cached_in_usd_1m", "Cache"]];

export default function PlatformPricing({ readOnly }) {
  const { draft, preview, update, save, reset, busy, dirty } = usePricingDraft();
  if (!draft || !preview) return <p className="flex items-center gap-2 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p>;
  const ov = draft.margin_overrides || {};
  const setOv = (f, v) => update((d) => { const o = { ...(d.margin_overrides || {}) }; if (v === "" || v === null) delete o[f]; else o[f] = v; return { ...d, margin_overrides: o }; });
  return (
    <div data-testid="platform-pricing">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-black text-slate-900">Tarif & Margin</h1><p className="text-sm text-slate-500">kredit = biaya provider × (1 + margin) × (1 + PPN) ÷ nilai 1 kredit — dibulatkan ke atas. Pratinjau diperbarui langsung; belum tersimpan sampai Anda menekan Simpan.</p></div>
        <SaveBar dirty={dirty} busy={busy} onSave={save} onReset={reset} readOnly={readOnly} />
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-4">
        <NumField label="Margin global" value={draft.margin_pct} onChange={(v) => update({ margin_pct: v })} suffix="%" step={0.5} testid="pp-margin" disabled={readOnly} />
        <NumField label="PPN" value={draft.tax_pct} onChange={(v) => update({ tax_pct: v })} suffix="%" step={0.5} testid="pp-tax" disabled={readOnly} />
        <NumField label="Kurs USD → IDR" value={draft.usd_to_idr} onChange={(v) => update({ usd_to_idr: v })} suffix="Rp" step={100} testid="pp-fx" disabled={readOnly} />
        <NumField label="Nilai 1 kredit" value={draft.usd_per_credit} onChange={(v) => update({ usd_per_credit: v })} suffix="USD" step={0.0001} testid="pp-usd-per-credit" disabled={readOnly} />
      </div>
      <div className="mt-6 aivora-card overflow-hidden">
        <table className="w-full text-sm" data-testid="pp-feature-table">
          <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-2.5 text-left">Fitur</th><th className="px-3 py-2.5 text-left">Biaya provider (USD)</th><th className="px-3 py-2.5 text-left">Margin fitur</th><th className="px-3 py-2.5 text-right">Kredit ditagih</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {preview.features.map((f) => (
              <tr key={f.feature} data-testid={`pp-row-${f.feature}`}>
                <td className="px-4 py-2.5"><p className="font-semibold text-slate-800">{f.label}</p><p className="text-[11px] text-slate-400">per {f.unit}</p></td>
                <td className="px-3 py-2.5"><input type="number" step="0.0001" min="0" disabled={readOnly} value={draft[FIELD[f.feature]] ?? ""} onChange={(e) => update({ [FIELD[f.feature]]: Number(e.target.value) })} data-testid={`pp-cost-${f.feature}`} className="w-32 rounded-lg border border-[#E7ECF3] px-2 py-1.5 text-sm outline-none focus:border-[#2F6BFF] disabled:bg-slate-50" /></td>
                <td className="px-3 py-2.5"><span className="flex items-center gap-2"><input type="number" step="0.5" min="0" disabled={readOnly} placeholder={`global ${draft.margin_pct}%`} value={ov[f.feature] ?? ""} onChange={(e) => setOv(f.feature, e.target.value === "" ? "" : Number(e.target.value))} data-testid={`pp-override-${f.feature}`} className="w-28 rounded-lg border border-[#E7ECF3] px-2 py-1.5 text-sm outline-none focus:border-[#2F6BFF] disabled:bg-slate-50" /><span className="text-xs text-slate-400">%{f.override ? "" : " (global)"}</span></span></td>
                <td className="px-3 py-2.5 text-right"><p className="font-black text-slate-900" data-testid={`pp-credits-${f.feature}`}>{f.credits}</p><p className="text-[11px] text-slate-400">{f.credits_exact} eksak</p></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-6 aivora-card p-5" data-testid="pp-realtime">
        <p className="text-sm font-bold text-slate-900">Harga token OpenAI Realtime — gpt-realtime-2.1 (USD / 1M token)</p>
        <p className="text-xs text-slate-500">Ditagih per respons dari laporan pemakaian OpenAI, memakai margin fitur "Koneksi Realtime". Harga resmi gpt-realtime-2.1: audio masuk $32, audio keluar $64, teks masuk $4, teks keluar $24, cache $0,40.</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-5">{RT.map(([k, l]) => <NumField key={k} label={l} value={draft[k]} onChange={(v) => update({ [k]: v })} step={0.1} testid={`pp-${k}`} disabled={readOnly} />)}</div>
      </div>
    </div>
  );
}
