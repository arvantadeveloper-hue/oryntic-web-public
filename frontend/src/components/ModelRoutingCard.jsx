import React, { useEffect, useState } from "react";
import { Route, Save } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Switch } from "./ui/switch";

// Platform admin: which model answers IT/coding and long research turns, and when tools must ask first.
export function ModelRoutingCard() {
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { api.get("/admin/model-routing").then((r) => setForm(r.data)).catch(() => {}); }, []);
  if (!form) return null;
  const save = async () => {
    setSaving(true);
    try {
      const r = await api.put("/admin/model-routing", { enabled: form.enabled, it_model: form.it_model, research_model: form.research_model, confirm_threshold: form.confirm_threshold });
      setForm(r.data); toast.success("Routing model disimpan");
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan"); } finally { setSaving(false); }
  };
  const sel = (k, label) => (
    <label className="block">
      <span className="mb-1 block text-[11px] font-semibold text-slate-500">{label}</span>
      <select value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} data-testid={`routing-${k}`} className="input-dark py-2 text-sm">
        {form.models.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
      </select>
    </label>
  );
  return (
    <div className="aivora-card p-5" data-testid="model-routing-card">
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#7C3AED]/10 text-[#7C3AED]"><Route size={18} /></span>
        <div className="flex-1"><p className="text-sm font-bold text-slate-900">Routing Model & Alat</p><p className="text-xs text-slate-500">Satu persona, otak berganti sesuai topik. Alat dengan biaya ≥ ambang akan meminta konfirmasi pengguna.</p></div>
        <Switch checked={form.enabled} onCheckedChange={(v) => setForm({ ...form, enabled: v })} data-testid="routing-enabled" />
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        {sel("it_model", "Topik IT / coding →")}
        {sel("research_model", "Riset & analisis panjang →")}
        <label className="block">
          <span className="mb-1 block text-[11px] font-semibold text-slate-500">Konfirmasi alat jika ≥ (kredit)</span>
          <input type="number" min="0" value={form.confirm_threshold} onChange={(e) => setForm({ ...form, confirm_threshold: parseInt(e.target.value || "0", 10) })} data-testid="routing-confirm_threshold" className="input-dark py-2 text-sm" />
        </label>
      </div>
      <div className="mt-3 flex justify-end"><button onClick={save} disabled={saving} data-testid="routing-save" className="btn-primary py-2"><Save size={14} /> Simpan Routing</button></div>
    </div>
  );
}

// Workspace owner: opt out of smart routing for this workspace.
export function SmartRoutingToggle({ user, onSaved }) {
  const on = user?.settings?.smart_routing !== false;
  const toggle = async (v) => {
    try { await api.put("/auth/settings", { smart_routing: v }); toast.success(v ? "Routing cerdas aktif" : "Routing cerdas dimatikan"); onSaved?.(); }
    catch (e) { toast.error("Gagal menyimpan"); }
  };
  return (
    <div className="aivora-card mt-6 flex items-center gap-3 p-4" data-testid="smart-routing-card">
      <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#7C3AED]/10 text-[#7C3AED]"><Route size={18} /></span>
      <div className="flex-1"><p className="text-sm font-bold text-slate-900">Routing cerdas</p><p className="text-xs text-slate-500">Asisten otomatis memakai Claude untuk topik IT/coding dan Gemini untuk riset panjang. Jawaban diberi label "via …".</p></div>
      <Switch checked={on} onCheckedChange={toggle} data-testid="smart-routing-toggle" />
    </div>
  );
}
