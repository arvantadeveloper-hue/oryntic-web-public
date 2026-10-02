import React, { useEffect, useState } from "react";
import { Sunrise, MessageSquare, Phone, Send, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";

const CHANNELS = [
  { id: "chat", label: "Chat setiap pagi", Icon: MessageSquare },
  { id: "call", label: "Panggilan dari asisten", Icon: Phone },
  { id: "both", label: "Dua-duanya", Icon: Sunrise },
];

// Calendar settings: should the assistant send a morning digest (today's agenda + finished tasks), and how?
export function DailyDigestCard() {
  const { user, setUser } = useAuth();
  const saved = user?.settings?.daily_digest || {};
  const [cfg, setCfg] = useState({ enabled: !!saved.enabled, channel: saved.channel || "chat", time: saved.time || "07:00", persona_id: saved.persona_id || "" });
  const [personas, setPersonas] = useState([]);
  const [busy, setBusy] = useState("");
  useEffect(() => { api.get("/personas").then((r) => setPersonas(r.data)).catch(() => {}); }, []);

  const save = async (next) => {
    setCfg(next); setBusy("save");
    try { const r = await api.put("/auth/settings", { daily_digest: { ...next, persona_id: next.persona_id || null } }); setUser(r.data); toast.success(next.enabled ? "Ringkasan harian aktif" : "Ringkasan harian dimatikan"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan"); } finally { setBusy(""); }
  };
  const sendNow = async () => {
    setBusy("send");
    try { const r = await api.post("/digest/send-now"); toast.success(r.data.sent ? `Ringkasan dikirim via ${r.data.channel === "both" ? "chat & panggilan" : r.data.channel === "call" ? "panggilan" : "chat"}` : `Tidak terkirim: ${r.data.reason}`); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengirim"); } finally { setBusy(""); }
  };

  return (
    <div className="aivora-card p-4" data-testid="digest-card">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-100 text-amber-600"><Sunrise size={16} /></span>
          <div><p className="text-sm font-bold text-slate-900">Ringkasan Harian</p><p className="text-[11px] text-slate-500">Asisten mengirim agenda hari ini & tugas yang selesai</p></div></div>
        <button onClick={() => save({ ...cfg, enabled: !cfg.enabled })} disabled={busy === "save"} data-testid="digest-toggle" className={`relative h-6 w-11 shrink-0 rounded-full transition ${cfg.enabled ? "bg-[#2F6BFF]" : "bg-slate-300"}`}>
          <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${cfg.enabled ? "left-[22px]" : "left-0.5"}`} /></button>
      </div>
      {cfg.enabled && (
        <div className="mt-4 space-y-3" data-testid="digest-options">
          <div>
            <p className="mb-1.5 text-xs font-semibold text-slate-600">Kirim melalui</p>
            <div className="grid grid-cols-3 gap-1.5">
              {CHANNELS.map((c) => (
                <button key={c.id} onClick={() => save({ ...cfg, channel: c.id })} data-testid={`digest-channel-${c.id}`} className={`flex flex-col items-center gap-1 rounded-xl border px-2 py-2 text-[11px] font-semibold transition ${cfg.channel === c.id ? "border-[#2F6BFF] bg-[#EEF3FF] text-[#2F6BFF]" : "border-[#E7ECF3] text-slate-600 hover:bg-slate-50"}`}><c.Icon size={15} /> {c.label}</button>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <label className="flex-1 text-xs font-semibold text-slate-600">Jam<input type="time" value={cfg.time} onChange={(e) => setCfg({ ...cfg, time: e.target.value })} onBlur={() => save(cfg)} className="input-dark mt-1 py-2 text-sm" data-testid="digest-time" /></label>
            <label className="flex-[2] text-xs font-semibold text-slate-600">Asisten<select value={cfg.persona_id} onChange={(e) => save({ ...cfg, persona_id: e.target.value })} className="input-dark mt-1 py-2 text-sm" data-testid="digest-persona">
              <option value="">Asisten pertama</option>{personas.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
          </div>
          <button onClick={sendNow} disabled={!!busy} className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#0B132B] py-2 text-xs font-bold text-white disabled:opacity-60" data-testid="digest-send-now">{busy === "send" ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />} Kirim ringkasan sekarang</button>
        </div>
      )}
    </div>
  );
}
