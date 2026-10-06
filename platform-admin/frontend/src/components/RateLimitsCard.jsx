import React, { useEffect, useState } from "react";
import { ShieldCheck, Save } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

const FIELDS = [
  ["chat_per_min", "Pesan chat / menit"],
  ["chat_per_hour", "Pesan chat / jam"],
  ["chat_min_interval_ms", "Jeda minimal antar pesan (ms)"],
  ["chat_max_inflight", "Balasan yang boleh diproses bersamaan"],
  ["chat_dup_per_30s", "Pesan identik maksimal / 30 detik"],
  ["voice_per_min", "Permintaan suara (STT/TTS) / menit"],
  ["calls_per_hour", "Panggilan realtime / jam"],
  ["max_call_minutes", "Durasi maksimal panggilan (menit)"],
  ["generation_per_hour", "Pembuatan profil/gambar / jam"],
  ["storage_quota_mb", "Kuota penyimpanan file per pengguna (MB)"],
];

export function RateLimitsCard() {
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { api.get("/admin/rate-limits").then((r) => setForm(r.data)).catch(() => {}); }, []);
  if (!form) return null;
  const save = async () => {
    setSaving(true);
    try { const r = await api.put("/admin/rate-limits", form); setForm(r.data); toast.success("Batas pemakaian disimpan"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan"); } finally { setSaving(false); }
  };
  return (
    <div className="aivora-card p-5" data-testid="rate-limits-card">
      <div className="flex items-center gap-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#10B981]/10 text-[#10B981]"><ShieldCheck size={18} /></span>
        <div><p className="text-sm font-bold text-slate-900">Batas Pemakaian per Pengguna</p><p className="text-xs text-slate-500">Melindungi kredit workspace dari penyalahgunaan. Berlaku untuk semua anggota, termasuk admin.</p></div>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-5">
        {FIELDS.map(([k, label]) => (
          <label key={k} className="block">
            <span className="mb-1 block text-[11px] font-semibold text-slate-500">{label}</span>
            <input type="number" min="1" value={form[k]} onChange={(e) => setForm({ ...form, [k]: parseInt(e.target.value || "0", 10) })} data-testid={`rl-${k}`} className="input-dark py-2 text-sm" />
          </label>
        ))}
      </div>
      <div className="mt-3 flex justify-end"><button onClick={save} disabled={saving} data-testid="rl-save" className="btn-primary py-2"><Save size={14} /> Simpan Batas</button></div>
    </div>
  );
}
