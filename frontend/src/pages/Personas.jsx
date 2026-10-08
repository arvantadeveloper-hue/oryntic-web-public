import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, MessageSquare, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useI18n } from "../i18n";

export default function Personas() {
  const { t } = useI18n();
  const nav = useNavigate();
  const [items, setItems] = useState(null);

  const load = () => api.get("/personas").then((r) => setItems(r.data)).catch(() => setItems([]));
  useEffect(() => { load(); }, []);

  const startChat = async (p, e) => {
    e.stopPropagation();
    const r = await api.post("/conversations", { persona_ids: [p.id], type: "private" });
    nav(`/chat/${r.data.id}`);
  };

  const del = async (p, e) => {
    e.stopPropagation();
    if (!window.confirm(`Hapus ${p.name}?`)) return;
    await api.delete(`/personas/${p.id}`);
    toast.success("Persona dihapus");
    load();
  };

  return (
    <div className="p-5 sm:p-8 lg:p-10 fade-up" data-testid="personas-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900">{t("nav.personas")}</h1>
          <p className="text-sm text-slate-500">Karakter AI buatan Anda.</p>
        </div>
        <button onClick={() => nav("/personas/new")} data-testid="create-persona-btn" className="btn-grad flex items-center gap-2 rounded-xl px-5 py-3 text-sm">
          <Plus size={18} /> {t("persona.create")}
        </button>
      </div>

      {items === null ? (
        <p className="mt-10 text-slate-500">{t("common.loading")}</p>
      ) : items.length === 0 ? (
        <div className="mt-16 flex flex-col items-center text-center">
          <div className="mb-4 h-20 w-20 rounded-full" style={{ background: "radial-gradient(circle, rgba(0,209,255,.3), transparent 70%)" }} />
          <h3 className="text-lg font-bold text-slate-900">Belum ada persona</h3>
          <p className="mt-1 max-w-sm text-sm text-slate-500">Buat karakter AI dengan mendeskripsikannya atau mengunggah foto referensi.</p>
          <button onClick={() => nav("/personas/new")} className="btn-grad mt-6 rounded-xl px-6 py-3 text-sm">{t("persona.create")}</button>
        </div>
      ) : (
        <div className="mt-8 grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-4">
          {items.map((p) => (
            <div key={p.id} onClick={(e) => (p.builtin ? startChat(p, e) : nav(`/personas/${p.id}`))} data-testid={`persona-card-${p.id}`}
              className={`aivora-card aivora-card-hover group cursor-pointer overflow-hidden ${p.builtin ? "ring-2 ring-[#2F6BFF]/40" : ""}`}>
              <div className="relative aspect-square bg-slate-50">
                {p.builtin && <span className="absolute left-2 top-2 z-10 rounded-full bg-[#2F6BFF] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white" data-testid="persona-support-badge">Dukungan</span>}
                {p.portrait ? <img src={p.portrait} alt={p.name} className="h-full w-full object-cover" />
                  : <div className="flex h-full w-full items-center justify-center text-4xl font-bold text-slate-600">{p.name[0]}</div>}
                <div className="absolute inset-x-0 bottom-0 flex gap-2 p-3 opacity-0 transition group-hover:opacity-100" style={{ background: "linear-gradient(transparent, rgba(11,19,43,.9))" }}>
                  <button onClick={(e) => startChat(p, e)} data-testid={`persona-chat-${p.id}`} className="btn-grad flex flex-1 items-center justify-center gap-1 rounded-lg py-2 text-xs"><MessageSquare size={13} /> Chat</button>
                  {!p.builtin && <button onClick={(e) => del(p, e)} data-testid={`persona-del-${p.id}`} className="rounded-lg bg-[#EF4444]/80 px-3 text-slate-900"><Trash2 size={14} /></button>}
                </div>
              </div>
              <div className="p-3">
                <p className="truncate font-semibold text-slate-900">{p.name}</p>
                <p className="truncate text-xs text-slate-500">{p.summary || "Persona"}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
