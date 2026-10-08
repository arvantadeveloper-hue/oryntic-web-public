import { LoadMore } from "../components/ConversationTools";
import { useLiveSync } from "../lib/userEvents";
import React, { useEffect, useState } from "react";
import { Bell, Plus, Trash2, Clock, CalendarDays, Pencil, Check, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useI18n } from "../i18n";
import { RemindOptions, RemindSummary } from "../components/RemindOptions";

const statusColor = { scheduled: "#00D1FF", ringing: "#F59E0B", answered: "#10B981", sent: "#10B981", declined: "#94A3B8", missed: "#EF4444" };
const STATUS_ID = { scheduled: "terjadwal", ringing: "berdering", answered: "dijawab", sent: "terkirim", declined: "ditolak", missed: "terlewat" };

const toLocalInput = (iso) => { const d = new Date(iso); const p = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`; };

// Inline editor for an existing reminder (title, notes, time, mode, offsets, persona) → PUT /reminders/{id}
function ReminderEditor({ r, personas, onSaved, onCancel }) {
  const [f, setF] = useState({ title: r.title, description: r.description || "", start: toLocalInput(r.start_at), mode: r.mode || "call", offsets: r.offsets || [r.remind_minutes || 30], personaId: r.persona_id || "" });
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (!f.title.trim() || !f.start) { toast.error("Isi judul & waktu"); return; }
    if (!f.offsets.length) { toast.error("Pilih minimal satu waktu ingatkan"); return; }
    setBusy(true);
    try {
      await api.put(`/reminders/${r.id}`, { title: f.title.trim(), description: f.description, start_at: new Date(f.start).toISOString(), mode: f.mode, offsets: f.offsets, persona_id: f.personaId || null });
      toast.success("Pengingat diperbarui"); onSaved();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan"); } finally { setBusy(false); }
  };
  return (
    <div className="aivora-card space-y-3 border-2 border-[#2F6BFF]/40 p-4" data-testid={`rem-edit-${r.id}`}>
      <input className="input-dark py-2 text-sm" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} data-testid="rem-edit-title" />
      <input className="input-dark py-2 text-sm" placeholder="Deskripsi / catatan (opsional)" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} data-testid="rem-edit-desc" />
      <input type="datetime-local" className="input-dark py-2 text-sm sm:max-w-xs" value={f.start} onChange={(e) => setF({ ...f, start: e.target.value })} data-testid="rem-edit-start" />
      <RemindOptions mode={f.mode} offsets={f.offsets} onMode={(m) => setF({ ...f, mode: m })} onOffsets={(o) => setF({ ...f, offsets: o })} personas={personas} personaId={f.personaId} onPersona={(p) => setF({ ...f, personaId: p })} />
      <div className="flex gap-2">
        <button onClick={save} disabled={busy} className="btn-grad flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs" data-testid="rem-edit-save">{busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} Simpan perubahan</button>
        <button onClick={onCancel} className="rounded-lg px-3 py-2 text-xs font-semibold text-slate-500 hover:bg-slate-100" data-testid="rem-edit-cancel">Batal</button>
      </div>
    </div>
  );
}

export default function Reminders() {
  const { t } = useI18n();
  const [shown, setShown] = useState(20);
  const [items, setItems] = useState([]);
  const [personas, setPersonas] = useState([]);
  const [editing, setEditing] = useState(null);
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [start, setStart] = useState("");
  const [mode, setMode] = useState("call");
  const [offsets, setOffsets] = useState([30]);
  const [personaId, setPersonaId] = useState("");

  const load = () => api.get("/reminders").then((r) => setItems(r.data)).catch(() => {});
  useEffect(() => { load(); api.get("/personas").then((r) => setPersonas(r.data)).catch(() => {}); }, []);
  useLiveSync(load, ["reminder_due", "push", "message_new"], 60000, []);

  const create = async () => {
    if (!title.trim() || !start) { toast.error("Isi judul & waktu"); return; }
    if (!offsets.length) { toast.error("Pilih minimal satu waktu ingatkan"); return; }
    try {
      await api.post("/reminders", { title, description: desc, start_at: new Date(start).toISOString(), offsets, mode, persona_id: personaId || null });
      setTitle(""); setDesc(""); setStart(""); load();
      toast.success("Pengingat dibuat");
    } catch (e) { toast.error("Gagal"); }
  };
  const del = async (id) => { await api.delete(`/reminders/${id}`); load(); };

  return (
    <div className="mx-auto max-w-4xl p-5 sm:p-8 lg:p-10 fade-up" data-testid="reminders-page">
      <h1 className="flex items-center gap-2 text-3xl font-extrabold text-slate-900"><Bell className="text-[#F59E0B]" /> {t("nav.reminders")}</h1>
      <p className="text-sm text-slate-500">Asisten akan menelepon atau mengirim pesan di chat saat waktunya tiba. Semua pengingat juga tampil di Kalender.</p>

      <div className="mt-6 aivora-card p-5">
        <h2 className="mb-4 text-sm font-semibold text-slate-900">{t("reminders.new")}</h2>
        <div className="space-y-4">
          <input className="input-dark" placeholder={t("reminders.title")} value={title} onChange={(e) => setTitle(e.target.value)} data-testid="rem-title" />
          <input className="input-dark" placeholder="Deskripsi / catatan (opsional)" value={desc} onChange={(e) => setDesc(e.target.value)} data-testid="rem-desc" />
          <div>
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">{t("reminders.when")}</label>
            <input type="datetime-local" className="input-dark sm:max-w-xs" value={start} onChange={(e) => setStart(e.target.value)} data-testid="rem-start" />
          </div>
          <RemindOptions mode={mode} offsets={offsets} onMode={setMode} onOffsets={setOffsets} personas={personas} personaId={personaId} onPersona={setPersonaId} />
          <button onClick={create} className="btn-grad flex items-center gap-2 rounded-xl px-5 py-3 text-sm" data-testid="rem-create"><Plus size={16} /> Buat Pengingat</button>
        </div>
      </div>

      <div className="mt-6 space-y-3">
        {items.length === 0 ? <p className="py-8 text-center text-slate-500">Belum ada pengingat.</p> : items.slice(0, shown).map((r) => editing === r.id ? (
          <ReminderEditor key={r.id} r={r} personas={personas} onSaved={() => { setEditing(null); load(); }} onCancel={() => setEditing(null)} />
        ) : (
          <div key={r.id} className="aivora-card flex items-center justify-between gap-3 p-4" data-testid={`rem-${r.id}`}>
            <div className="min-w-0">
              <p className="flex flex-wrap items-center gap-2 font-semibold text-slate-900">{r.title}
                {r.event_id && <span className="inline-flex items-center gap-1 rounded-full bg-[#10B981]/15 px-2 py-0.5 text-[10px] font-bold text-[#0f8f63]" data-testid="rem-from-calendar"><CalendarDays size={10} /> Dari kalender</span>}
              </p>
              {r.description && <p className="truncate text-xs text-slate-500">{r.description}</p>}
              <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-slate-500">
                <span className="inline-flex items-center gap-1"><Clock size={12} /> {new Date(r.start_at).toLocaleString("id-ID")}</span>
                <RemindSummary remind={{ mode: r.mode || "call", offsets: r.offsets || [r.remind_minutes] }} />
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-3">
              <span className="rounded-full px-3 py-1 text-xs font-semibold" style={{ background: `${statusColor[r.status] || "#94A3B8"}22`, color: statusColor[r.status] || "#94A3B8" }} data-testid="rem-status">{STATUS_ID[r.status] || r.status}</span>
              <button onClick={() => setEditing(r.id)} className="text-slate-500 hover:text-[#2F6BFF]" title="Ubah" data-testid={`rem-edit-btn-${r.id}`}><Pencil size={15} /></button>
              <button onClick={() => del(r.id)} className="text-slate-500 hover:text-[#EF4444]" data-testid={`rem-delete-${r.id}`}><Trash2 size={15} /></button>
            </div>
          </div>
        ))}
        {items.length > shown && <LoadMore onClick={() => setShown((n) => n + 20)} testid="reminders-load-more" />}
      </div>
    </div>
  );
}
