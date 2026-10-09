import React, { useEffect, useState } from "react";
import { Percent, Gift, Save } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

// Hanya pengali global — harga provider diatur di tab Katalog Harga (satu-satunya sumber tarif)
const PRICE_FIELDS = [
  ["margin_pct", "Margin platform (%)", 1], ["tax_pct", "PPN (%)", 0.5], ["usd_to_idr", "Kurs USD → IDR", 100], ["usd_per_credit", "Nilai 1 kredit (USD)", 0.0001], ["idr_per_credit", "Nilai 1 kredit (IDR, tampilan)", 1],
  ["chars_per_token", "Karakter per token (estimasi teks)", 0.5], ["video_res_480_mult", "Pengali video 480p", 0.1], ["video_res_1080_mult", "Pengali video 1080p", 0.1], ["video_real_person_mult", "Pengali video orang nyata", 0.05], ["package_margin_pct", "Margin paket kredit (%)", 1],
];
const RATE_LABELS = { text_per_1k: "kredit / 1k karakter (model tanpa harga)", image: "kredit / gambar", profile: "kredit / profil", stt: "kredit / transkripsi", tts: "kredit / TTS", realtime_per_min: "kredit / menit GPT-Live", vision: "kredit / cuplikan layar", bandwidth_per_mb: "kredit / MB data panggilan", video_per_sec: "kredit / detik video" };

export function PlatformPricingCard({ pricing, rates, tools, onSaved }) {
  const [form, setForm] = useState(pricing);
  const [saving, setSaving] = useState(false);
  useEffect(() => setForm(pricing), [pricing]);
  if (!form) return null;
  const save = async () => {
    setSaving(true);
    try { const r = await api.put("/admin/pricing", form); toast.success("Tarif platform disimpan"); onSaved && onSaved(r.data); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan"); } finally { setSaving(false); }
  };
  return (
    <div className="aivora-card p-5" data-testid="platform-pricing-card">
      <div className="flex items-center gap-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#7C3AED]/10 text-[#7C3AED]"><Percent size={18} /></span>
        <div><p className="text-sm font-bold text-slate-900">Margin & Pengali Global</p><p className="text-xs text-slate-500">Kredit = harga provider (dari <b>Katalog Harga</b>) × (1 + margin) × (1 + PPN) ÷ nilai kredit. Harga provider per model/layanan hanya diubah di tab Katalog Harga.</p></div>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-5">
        {PRICE_FIELDS.map(([k, label, step]) => (
          <label key={k} className="block"><span className="mb-1 block text-[11px] font-semibold text-slate-500">{label}</span>
            <input type="number" step={step} min="0" value={form[k]} onChange={(e) => setForm({ ...form, [k]: parseFloat(e.target.value) || 0 })} data-testid={`pp-${k}`} className="input-dark py-2 text-sm" /></label>
        ))}
      </div>
      {tools && (
        <div className="mt-5" data-testid="pp-tools">
          <p className="mb-2 text-xs font-bold text-slate-700">Alat bawaan provider — dibaca dari Katalog Harga (ubah di tab Katalog Harga)</p>
          <div className="flex flex-wrap gap-2">{tools.map((t) => (
            <span key={t.id} className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700" data-testid={`pp-tool-${t.id.replace(":", "-")}-credits`}>{t.label} <span className="text-slate-400">({t.provider})</span> · <b className="text-[#2F6BFF]">{t.credits > 0 ? `${t.credits} kredit` : "token saja"}</b></span>
          ))}</div>
        </div>
      )}
      {rates && (
        <div className="mt-4 flex flex-wrap gap-2" data-testid="pp-rates">
          {Object.entries(RATE_LABELS).map(([k, l]) => <span key={k} className="rounded-full bg-[#EEF3FF] px-3 py-1 text-xs font-semibold text-[#2F6BFF]">{rates[k]} {l}</span>)}
        </div>
      )}
      <div className="mt-3 flex justify-end"><button onClick={save} disabled={saving} data-testid="pp-save" className="btn-primary py-2"><Save size={14} /> Simpan Tarif</button></div>
    </div>
  );
}

export function TrialCard({ trial, onSaved }) {
  const [form, setForm] = useState(trial);
  const [saving, setSaving] = useState(false);
  useEffect(() => setForm(trial), [trial]);
  if (!form) return null;
  const save = async () => {
    setSaving(true);
    try { const r = await api.put("/admin/trial", form); toast.success("Paket percobaan disimpan"); onSaved && onSaved(r.data.trial); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan"); } finally { setSaving(false); }
  };
  return (
    <div className="aivora-card p-5" data-testid="trial-card">
      <div className="flex items-center gap-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#F59E0B]/10 text-[#F59E0B]"><Gift size={18} /></span>
        <div><p className="text-sm font-bold text-slate-900">Paket Percobaan Workspace Baru</p><p className="text-xs text-slate-500">Berlaku untuk pendaftar baru. Setelah masa percobaan habis, workspace wajib membeli paket kredit.</p></div>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        {[["trial_days", "Durasi (hari)"], ["trial_daily_limit", "Kuota harian (kredit)"], ["trial_credits", "Kredit awal"]].map(([k, label]) => (
          <label key={k} className="block"><span className="mb-1 block text-[11px] font-semibold text-slate-500">{label}</span>
            <input type="number" min="0" value={form[k]} onChange={(e) => setForm({ ...form, [k]: parseInt(e.target.value || "0", 10) })} data-testid={`trial-${k}`} className="input-dark py-2 text-sm" /></label>
        ))}
      </div>
      <div className="mt-3 flex justify-end"><button onClick={save} disabled={saving} data-testid="trial-save" className="btn-primary py-2"><Save size={14} /> Simpan Paket</button></div>
    </div>
  );
}
