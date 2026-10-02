import React, { useEffect, useState } from "react";
import { Percent, Gift, Save } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

const PRICE_FIELDS = [
  ["margin_pct", "Margin platform (%)", 1], ["tax_pct", "PPN (%)", 0.5], ["usd_to_idr", "Kurs USD → IDR", 100], ["usd_per_credit", "Nilai 1 kredit (USD)", 0.0001], ["idr_per_credit", "Nilai 1 kredit (IDR, tampilan)", 1],
  ["text_usd_per_1k_chars", "Teks (USD / 1k karakter)", 0.0001], ["image_usd", "Gambar (USD / gambar)", 0.001], ["profile_usd", "Profil persona (USD)", 0.001],
  ["stt_usd", "Transkripsi (USD / permintaan)", 0.001], ["tts_usd", "Suara TTS (USD / permintaan)", 0.001], ["provider_usd_per_min", "Biaya koneksi Realtime (USD / menit)", 0.01],
  ["rt_audio_in_usd_1m", "Realtime audio masuk (USD / 1M token)", 1], ["rt_audio_out_usd_1m", "Realtime audio keluar (USD / 1M token)", 1], ["rt_text_in_usd_1m", "Realtime teks masuk (USD / 1M token)", 0.5], ["rt_text_out_usd_1m", "Realtime teks keluar (USD / 1M token)", 0.5], ["rt_cached_in_usd_1m", "Realtime cache (USD / 1M token)", 0.1], ["video_usd_per_sec", "Video Seedance (USD / detik)", 0.001],
];
const RATE_LABELS = { text_per_1k: "kredit / 1k karakter", image: "kredit / gambar", profile: "kredit / profil", stt: "kredit / transkripsi", tts: "kredit / TTS", realtime_per_min: "kredit / menit koneksi realtime (+ token audio aktual)", video_per_sec: "kredit / detik video" };

export function PlatformPricingCard({ pricing, rates, onSaved }) {
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
        <div><p className="text-sm font-bold text-slate-900">Tarif & Margin Platform</p><p className="text-xs text-slate-500">Semua kredit dihitung: biaya provider × (1 + margin) × (1 + PPN) × kurs ÷ nilai kredit, dibulatkan ke atas.</p></div>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-5">
        {PRICE_FIELDS.map(([k, label, step]) => (
          <label key={k} className="block"><span className="mb-1 block text-[11px] font-semibold text-slate-500">{label}</span>
            <input type="number" step={step} min="0" value={form[k]} onChange={(e) => setForm({ ...form, [k]: parseFloat(e.target.value) || 0 })} data-testid={`pp-${k}`} className="input-dark py-2 text-sm" /></label>
        ))}
      </div>
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
