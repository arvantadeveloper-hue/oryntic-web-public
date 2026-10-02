import React, { useState } from "react";
import { FileText, Plus, Trash2, Save } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

const DEFAULTS = [
  { name: "Agenda", required: true }, { name: "Pembahasan", required: true }, { name: "Keputusan", required: true },
  { name: "Tindak lanjut (PIC & tenggat)", required: true }, { name: "Isu terbuka", required: false },
];

// Workspace owner defines the minutes template; required fields are checked before a meeting ends.
export function NotulenFormatCard({ user, onSaved }) {
  const [fields, setFields] = useState(() => (user?.settings?.notulen_fields?.length ? user.settings.notulen_fields : DEFAULTS));
  const [saving, setSaving] = useState(false);
  const upd = (i, patch) => setFields((f) => f.map((x, k) => (k === i ? { ...x, ...patch } : x)));
  const save = async () => {
    const clean = fields.filter((f) => f.name.trim());
    if (!clean.length) { toast.error("Minimal satu kolom"); return; }
    setSaving(true);
    try { await api.put("/auth/settings", { notulen_fields: clean }); toast.success("Format notulen disimpan"); onSaved?.(); }
    catch (e) { toast.error("Gagal menyimpan"); } finally { setSaving(false); }
  };
  return (
    <div className="mt-4 aivora-card p-6" data-testid="notulen-format-card">
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#2F6BFF]/10 text-[#2F6BFF]"><FileText size={18} /></span>
        <div className="flex-1"><p className="text-sm font-bold text-slate-900">Format Notulen</p><p className="text-xs text-slate-500">Kolom yang harus ada di setiap notulen meeting. Kolom <b>wajib</b> dicek asisten sebelum meeting diakhiri.</p></div>
      </div>
      <div className="mt-4 space-y-2">
        {fields.map((f, i) => (
          <div key={i} className="flex items-center gap-2" data-testid={`notulen-field-${i}`}>
            <input value={f.name} onChange={(e) => upd(i, { name: e.target.value })} data-testid={`notulen-field-name-${i}`} className="input-dark flex-1 py-2 text-sm" placeholder="Nama kolom" />
            <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-600"><input type="checkbox" checked={!!f.required} onChange={(e) => upd(i, { required: e.target.checked })} data-testid={`notulen-field-required-${i}`} /> Wajib</label>
            <button onClick={() => setFields((x) => x.filter((_, k) => k !== i))} data-testid={`notulen-field-del-${i}`} className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-500"><Trash2 size={14} /></button>
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center justify-between">
        <button onClick={() => setFields((x) => (x.length < 12 ? [...x, { name: "", required: false }] : x))} data-testid="notulen-field-add" className="flex items-center gap-1 text-xs font-semibold text-[#2F6BFF]"><Plus size={14} /> Tambah kolom</button>
        <button onClick={save} disabled={saving} data-testid="notulen-save" className="btn-primary py-2"><Save size={14} /> Simpan Format</button>
      </div>
    </div>
  );
}
