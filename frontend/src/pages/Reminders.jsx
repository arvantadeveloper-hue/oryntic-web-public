import React, { useEffect, useState } from "react";
import { Bell, Plus, Trash2, Clock } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useI18n } from "../i18n";

const MINS = [5, 10, 15, 30, 60, 120];
const statusColor = { scheduled: "#00D1FF", ringing: "#F59E0B", answered: "#10B981", declined: "#94A3B8", missed: "#EF4444" };

export default function Reminders() {
  const { t } = useI18n();
  const [items, setItems] = useState([]);
  const [personas, setPersonas] = useState([]);
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [start, setStart] = useState("");
  const [mins, setMins] = useState(30);
  const [personaId, setPersonaId] = useState("");

  const load = () => api.get("/reminders").then((r) => setItems(r.data)).catch(() => {});
  useEffect(() => { load(); api.get("/personas").then((r) => setPersonas(r.data)).catch(() => {}); }, []);
  useEffect(() => { const iv = setInterval(load, 8000); return () => clearInterval(iv); }, []);

  const create = async () => {
    if (!title.trim() || !start) { toast.error("Isi judul & waktu"); return; }
    try {
      await api.post("/reminders", { title, description: desc, start_at: new Date(start).toISOString(), remind_minutes: mins, persona_id: personaId || null });
      setTitle(""); setDesc(""); setStart(""); load();
      toast.success("Pengingat dibuat");
    } catch (e) { toast.error("Gagal"); }
  };
  const del = async (id) => { await api.delete(`/reminders/${id}`); load(); };

  return (
    <div className="mx-auto max-w-4xl p-5 sm:p-8 lg:p-10 fade-up" data-testid="reminders-page">
      <h1 className="flex items-center gap-2 text-3xl font-extrabold text-slate-900"><Bell className="text-[#F59E0B]" /> {t("nav.reminders")}</h1>
      <p className="text-sm text-slate-500">Aivora akan "menelepon" Anda di dalam aplikasi saat waktunya tiba.</p>

      <div className="mt-6 aivora-card p-5">
        <h2 className="mb-4 text-sm font-semibold text-slate-900">{t("reminders.new")}</h2>
        <div className="space-y-4">
          <input className="input-dark" placeholder={t("reminders.title")} value={title} onChange={(e) => setTitle(e.target.value)} data-testid="rem-title" />
          <input className="input-dark" placeholder="Deskripsi / catatan (opsional)" value={desc} onChange={(e) => setDesc(e.target.value)} data-testid="rem-desc" />
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">{t("reminders.when")}</label>
              <input type="datetime-local" className="input-dark" value={start} onChange={(e) => setStart(e.target.value)} data-testid="rem-start" />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">{t("reminders.before")}</label>
              <select className="input-dark" value={mins} onChange={(e) => setMins(Number(e.target.value))} data-testid="rem-mins">
                {MINS.map((m) => <option key={m} value={m}>{m} {t("common.minutes")}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">Persona</label>
              <select className="input-dark" value={personaId} onChange={(e) => setPersonaId(e.target.value)} data-testid="rem-persona">
                <option value="">Aivora</option>
                {personas.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
          </div>
          <button onClick={create} className="btn-grad flex items-center gap-2 rounded-xl px-5 py-3 text-sm" data-testid="rem-create"><Plus size={16} /> Buat Pengingat</button>
        </div>
      </div>

      <div className="mt-6 space-y-3">
        {items.length === 0 ? <p className="py-8 text-center text-slate-500">Belum ada pengingat.</p> : items.map((r) => (
          <div key={r.id} className="aivora-card flex items-center justify-between p-4" data-testid={`rem-${r.id}`}>
            <div>
              <p className="font-semibold text-slate-900">{r.title}</p>
              <p className="flex items-center gap-1 text-xs text-slate-500"><Clock size={12} /> {new Date(r.start_at).toLocaleString()} · ingatkan {r.remind_minutes}m sebelum</p>
            </div>
            <div className="flex items-center gap-3">
              <span className="rounded-full px-3 py-1 text-xs font-semibold capitalize" style={{ background: `${statusColor[r.status]}22`, color: statusColor[r.status] }}>{r.status}</span>
              <button onClick={() => del(r.id)} className="text-slate-500 hover:text-[#EF4444]"><Trash2 size={15} /></button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
