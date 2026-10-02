import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight, Plus, ClipboardList, Bell, Video, CalendarDays, Trash2, X, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

const KIND = {
  task: { label: "Tugas", color: "#2F6BFF", Icon: ClipboardList },
  reminder: { label: "Pengingat", color: "#F59E0B", Icon: Bell },
  meeting: { label: "Meeting", color: "#7C3AED", Icon: Video },
  event: { label: "Event", color: "#10B981", Icon: CalendarDays },
};
const DAYS = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"];
const MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"];
const dayKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const timeStr = (iso) => new Date(iso).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
const STATUS_ID = { scheduled: "terjadwal", completed: "selesai", running: "berjalan", queued: "antre", failed: "gagal", ringing: "berdering", done: "selesai" };

function EventForm({ date, onClose, onSaved }) {
  const [f, setF] = useState({ title: "", time: "09:00", notes: "" });
  const [busy, setBusy] = useState(false);
  const save = async (e) => {
    e.preventDefault(); setBusy(true);
    try {
      const start = new Date(`${dayKey(date)}T${f.time}:00`);
      await api.post("/events", { title: f.title, start_at: start.toISOString(), notes: f.notes });
      toast.success("Event ditambahkan"); onSaved(); onClose();
    } catch (err) { toast.error(err?.response?.data?.detail || "Gagal menyimpan"); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={save} className="mt-3 space-y-2 rounded-xl border border-[#E7ECF3] bg-slate-50 p-3" data-testid="event-form">
      <input className="input-dark py-2 text-sm" placeholder="Judul event" required value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} data-testid="event-title" />
      <div className="flex gap-2">
        <input type="time" className="input-dark w-32 py-2 text-sm" value={f.time} onChange={(e) => setF({ ...f, time: e.target.value })} data-testid="event-time" />
        <input className="input-dark flex-1 py-2 text-sm" placeholder="Catatan (opsional)" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} data-testid="event-notes" />
      </div>
      <div className="flex gap-2"><button disabled={busy} className="btn-grad rounded-lg px-4 py-1.5 text-xs" data-testid="event-save">{busy ? <Loader2 size={12} className="animate-spin" /> : "Simpan"}</button><button type="button" onClick={onClose} className="rounded-lg px-3 py-1.5 text-xs text-slate-500">Batal</button></div>
    </form>
  );
}

export default function Calendar() {
  const nav = useNavigate();
  const [cursor, setCursor] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(() => new Date());
  const [adding, setAdding] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = () => {
    const start = new Date(cursor.getFullYear(), cursor.getMonth(), 1 - 7);
    const end = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 7);
    setLoading(true);
    api.get(`/calendar?start=${start.toISOString()}&end=${end.toISOString()}`).then((r) => setItems(r.data)).catch(() => {}).finally(() => setLoading(false));
  };
  useEffect(load, [cursor]); // eslint-disable-line

  const byDay = useMemo(() => { const m = {}; items.forEach((it) => { if (!it.at) return; const k = dayKey(new Date(it.at)); (m[k] = m[k] || []).push(it); }); return m; }, [items]);
  const cells = useMemo(() => {
    const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const offset = (first.getDay() + 6) % 7;
    const start = new Date(first); start.setDate(1 - offset);
    return Array.from({ length: 42 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d; });
  }, [cursor]);
  const todayKey = dayKey(new Date());
  const selItems = byDay[dayKey(selected)] || [];

  const removeEvent = async (id) => { try { await api.delete(`/events/${id}`); toast.success("Event dihapus"); load(); } catch (e) { toast.error("Gagal menghapus"); } };

  return (
    <div className="mx-auto max-w-6xl p-5 sm:p-8" data-testid="calendar-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 sm:text-3xl">Kalender</h1>
          <p className="mt-1 text-sm text-slate-500">Tugas terjadwal, pengingat, meeting, dan event tim dalam satu tampilan.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))} className="rounded-lg border border-[#E7ECF3] p-2 hover:bg-slate-50" data-testid="cal-prev"><ChevronLeft size={16} /></button>
          <span className="min-w-[160px] text-center text-sm font-bold text-slate-800" data-testid="cal-month">{MONTHS[cursor.getMonth()]} {cursor.getFullYear()}</span>
          <button onClick={() => setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))} className="rounded-lg border border-[#E7ECF3] p-2 hover:bg-slate-50" data-testid="cal-next"><ChevronRight size={16} /></button>
          <button onClick={() => { const d = new Date(); setCursor(new Date(d.getFullYear(), d.getMonth(), 1)); setSelected(d); }} className="rounded-lg border border-[#E7ECF3] px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50" data-testid="cal-today">Hari ini</button>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="aivora-card overflow-hidden">
          <div className="grid grid-cols-7 border-b border-[#E7ECF3] bg-slate-50 text-center text-[11px] font-bold uppercase tracking-wider text-slate-500">{DAYS.map((d) => <div key={d} className="py-2">{d}</div>)}</div>
          <div className="grid grid-cols-7" data-testid="cal-grid">
            {cells.map((d) => {
              const k = dayKey(d); const list = byDay[k] || []; const inMonth = d.getMonth() === cursor.getMonth(); const sel = k === dayKey(selected);
              return (
                <button key={k} onClick={() => { setSelected(d); setAdding(false); }} data-testid={`cal-day-${k}`} className={`min-h-[88px] border-b border-r border-[#E7ECF3] p-1.5 text-left align-top transition hover:bg-[#EEF3FF]/60 ${inMonth ? "" : "bg-slate-50/60 text-slate-300"} ${sel ? "ring-2 ring-inset ring-[#2F6BFF]" : ""}`}>
                  <span className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${k === todayKey ? "bg-[#2F6BFF] text-white" : inMonth ? "text-slate-700" : ""}`}>{d.getDate()}</span>
                  <div className="mt-1 space-y-0.5">
                    {list.slice(0, 3).map((it) => <div key={it.kind + it.id} className="truncate rounded px-1 text-[10px] font-semibold text-white" style={{ background: KIND[it.kind].color }}>{it.title}</div>)}
                    {list.length > 3 && <div className="text-[10px] text-slate-400">+{list.length - 3} lagi</div>}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="aivora-card p-4" data-testid="cal-day-panel">
          <div className="flex items-center justify-between">
            <p className="text-sm font-bold text-slate-900">{selected.toLocaleDateString("id-ID", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</p>
            <button onClick={() => setAdding((a) => !a)} className="flex items-center gap-1 rounded-lg bg-[#0B132B] px-2.5 py-1.5 text-xs font-bold text-white" data-testid="cal-add-event">{adding ? <X size={13} /> : <Plus size={13} />} Event</button>
          </div>
          {adding && <EventForm date={selected} onClose={() => setAdding(false)} onSaved={load} />}
          <div className="mt-3 space-y-2" data-testid="cal-day-items">
            {loading && <p className="text-xs text-slate-400">Memuat...</p>}
            {!loading && selItems.length === 0 && <p className="rounded-xl bg-slate-50 p-4 text-center text-xs text-slate-400">Tidak ada agenda di tanggal ini.</p>}
            {selItems.map((it) => {
              const K = KIND[it.kind];
              return (
                <div key={it.kind + it.id} className="flex items-start gap-3 rounded-xl border border-[#E7ECF3] p-3" data-testid={`cal-item-${it.kind}`}>
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-white" style={{ background: K.color }}><K.Icon size={15} /></span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-slate-900">{it.title}</p>
                    <p className="text-[11px] text-slate-500">{timeStr(it.at)} · {K.label}{it.status ? ` · ${STATUS_ID[it.status] || it.status}` : ""}{it.who ? ` · ${it.who}` : ""}</p>
                    {it.notes && <p className="mt-1 text-xs text-slate-500">{it.notes}</p>}
                  </div>
                  {it.link && <button onClick={() => nav(it.link)} className="text-xs font-semibold text-[#2F6BFF]">Buka</button>}
                  {it.kind === "event" && it.mine && <button onClick={() => removeEvent(it.id)} className="text-slate-400 hover:text-[#EF4444]" data-testid={`event-delete-${it.id}`}><Trash2 size={14} /></button>}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
