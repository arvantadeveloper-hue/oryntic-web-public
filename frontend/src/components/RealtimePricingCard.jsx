import React, { useEffect, useState } from "react";
import { Zap, Save } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

const FIELDS = [
  ["provider_usd_per_min", "Biaya provider (USD/menit)", 0.01],
  ["margin_pct", "Margin platform (%)", 1],
  ["tax_pct", "PPN (%)", 0.5],
  ["usd_to_idr", "Kurs USD → IDR", 100],
  ["idr_per_credit", "Nilai 1 kredit (IDR)", 1],
];

function preview(f) {
  const idr = f.provider_usd_per_min * (1 + f.margin_pct / 100) * (1 + f.tax_pct / 100) * f.usd_to_idr;
  return { idr: Math.round(idr), credits: Math.max(1, Math.ceil(idr / Math.max(f.idr_per_credit, 0.01))) };
}

export function RealtimePricingCard() {
  const [form, setForm] = useState(null);
  const [meta, setMeta] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/admin/realtime-pricing").then((r) => {
      const { credits_per_min, model, enabled, ...f } = r.data;
      setForm(f); setMeta({ credits_per_min, model, enabled });
    }).catch(() => {});
  }, []);

  if (!form) return null;
  const pv = preview(form);
  const save = async () => {
    setSaving(true);
    try { const r = await api.put("/admin/realtime-pricing", form); setMeta((m) => ({ ...m, credits_per_min: r.data.credits_per_min })); toast.success("Tarif Realtime disimpan"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan"); } finally { setSaving(false); }
  };

  return (
    <div className="aivora-card p-5" data-testid="realtime-pricing-card">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#2F6BFF]/10 text-[#2F6BFF]"><Zap size={18} /></span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-bold text-slate-900">Panggilan Suara Realtime (speech-to-speech)</p>
          <p className="text-xs text-slate-500">Model {meta.model} · {meta.enabled ? "Aktif" : "Nonaktif (OPENAI_API_KEY belum diatur)"}</p>
        </div>
        <span className="rounded-full bg-[#10B981]/15 px-3 py-1 text-xs font-bold text-[#10B981]" data-testid="rt-credits-per-min">{meta.credits_per_min} kredit/menit</span>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-5">
        {FIELDS.map(([k, label, step]) => (
          <label key={k} className="block">
            <span className="mb-1 block text-[11px] font-semibold text-slate-500">{label}</span>
            <input type="number" step={step} min="0" value={form[k]} onChange={(e) => setForm({ ...form, [k]: parseFloat(e.target.value) || 0 })} data-testid={`rt-pricing-${k}`} className="input-dark py-2 text-sm" />
          </label>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-slate-500">Perhitungan: biaya × (1 + margin) × (1 + PPN) × kurs = <b>Rp {pv.idr.toLocaleString("id-ID")}/menit</b> ≈ <b>{pv.credits} kredit/menit</b> (dibulatkan ke atas, ditagih per menit berjalan).</p>
        <button onClick={save} disabled={saving} data-testid="rt-pricing-save" className="btn-primary py-2"><Save size={14} /> Simpan Tarif</button>
      </div>
    </div>
  );
}
