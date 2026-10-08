import React, { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Save, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../lib/api";

// Shared state/logic for the tariff + package editors: edit a draft of `platform_pricing`, preview (never saved) on every change, Save = PUT.
export function usePricingDraft() {
  const [saved, setSaved] = useState(null);
  const [draft, setDraft] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef(null);
  const load = useCallback(async () => {
    const r = await api.get("/admin/pricing");
    setSaved(r.data.pricing); setDraft(r.data.pricing);
    setPreview({ rates: r.data.rates, features: r.data.features, packages: r.data.packages, models: r.data.models, realtime_models: r.data.realtime_models });
  }, []);
  useEffect(() => { load().catch(() => toast.error("Gagal memuat tarif")); }, [load]);
  const update = (patch) => {
    setDraft((d) => {
      const nd = typeof patch === "function" ? patch(d) : { ...d, ...patch };
      clearTimeout(timer.current);
      timer.current = setTimeout(() => api.post("/admin/pricing/preview", nd).then((r) => setPreview(r.data)).catch(() => {}), 350);
      return nd;
    });
  };
  const save = async () => {
    setBusy(true);
    try { const r = await api.put("/admin/pricing", draft); setSaved(r.data.pricing); setDraft(r.data.pricing); setPreview({ rates: r.data.rates, features: r.data.features, packages: r.data.packages, models: r.data.models, realtime_models: r.data.realtime_models }); toast.success("Tarif disimpan"); }
    catch (e) { const d = e?.response?.data?.detail; toast.error(Array.isArray(d) ? d.map((x) => x.msg).join(", ") : d || "Gagal menyimpan"); } finally { setBusy(false); }
  };
  const reset = () => { setDraft(saved); api.post("/admin/pricing/preview", saved).then((r) => setPreview(r.data)).catch(() => {}); };
  const dirty = JSON.stringify(saved) !== JSON.stringify(draft);
  return { draft, preview, update, save, reset, busy, dirty };
}

export function NumField({ label, value, onChange, step = 1, min = 0, suffix, testid, disabled }) {
  return (
    <label className="block">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{label}</span>
      <span className="mt-1 flex items-center gap-2">
        <input type="number" step={step} min={min} disabled={disabled} value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} data-testid={testid} className="w-full rounded-xl border border-[#E7ECF3] bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-[#2F6BFF] disabled:bg-slate-50 disabled:text-slate-500" />
        {suffix && <span className="text-xs text-slate-400">{suffix}</span>}
      </span>
    </label>
  );
}

export function SaveBar({ dirty, busy, onSave, onReset, readOnly, testid = "pricing" }) {
  if (readOnly) return <p className="rounded-xl bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-700" data-testid={`${testid}-readonly`}>Mode baca — hanya Super Admin yang dapat mengubah.</p>;
  return (
    <div className="flex items-center gap-2">
      {dirty && <button onClick={onReset} className="flex items-center gap-1.5 rounded-xl border border-[#E7ECF3] bg-white px-3 py-2 text-xs font-semibold text-slate-600" data-testid={`${testid}-reset`}><RotateCcw size={13} /> Batalkan</button>}
      <button onClick={onSave} disabled={!dirty || busy} className="btn-grad flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-bold disabled:opacity-50" data-testid={`${testid}-save`}>{busy ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Simpan</button>
    </div>
  );
}
