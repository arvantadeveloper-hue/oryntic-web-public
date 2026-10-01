import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, MessageSquare, RefreshCw, Wand2, Copy, Trash2, Brain, Plus } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";

export default function PersonaDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const { refreshUser } = useAuth();
  const [p, setP] = useState(null);
  const [tab, setTab] = useState("profile");
  const [instr, setInstr] = useState("");
  const [busy, setBusy] = useState(false);
  const [mems, setMems] = useState([]);
  const [newMem, setNewMem] = useState("");
  const [models, setModels] = useState([]);

  useEffect(() => { api.get("/models").then((r) => setModels(r.data.models)).catch(() => {}); }, []);
  const modelLabel = (key) => (models.find((m) => m.id === key) || {}).label || key;
  const changeModel = async (key) => { const r = await api.put(`/personas/${id}`, { profile: p.profile, model: key }); setP(r.data); toast.success("Model diperbarui"); };

  const load = () => api.get(`/personas/${id}`).then((r) => setP(r.data)).catch(() => toast.error("Tidak ditemukan"));
  const loadMem = () => api.get(`/memory?persona_id=${id}`).then((r) => setMems(r.data)).catch(() => {});
  useEffect(() => { load(); loadMem(); /* eslint-disable-next-line */ }, [id]);

  if (!p) return <div className="p-10 text-slate-500">Memuat...</div>;
  const prof = p.profile || {};

  const regen = async () => {
    setBusy(true);
    try { const r = await api.post(`/personas/${id}/portrait`, { style: prof.appearance?.visual_style || "cinematic realistic", use_reference: !!p.reference_photo }); setP({ ...p, portrait: r.data.portrait }); refreshUser(); toast.success("Potret diperbarui"); }
    catch (e) { toast.error("Gagal membuat potret"); } finally { setBusy(false); }
  };

  const applyEdit = async () => {
    if (!instr.trim()) return;
    setBusy(true);
    try { const r = await api.post(`/personas/${id}/edit`, { instruction: instr }); setP(r.data); setInstr(""); refreshUser(); toast.success("Persona diperbarui"); }
    catch (e) { toast.error("Gagal mengedit"); } finally { setBusy(false); }
  };

  const startChat = async () => {
    const r = await api.post("/conversations", { persona_ids: [id], type: "private" });
    nav(`/chat/${r.data.id}`);
  };

  const dup = async () => { const r = await api.post(`/personas/${id}/duplicate`); toast.success("Diduplikasi"); nav(`/personas/${r.data.id}`); };
  const del = async () => { if (!window.confirm("Hapus persona ini?")) return; await api.delete(`/personas/${id}`); toast.success("Dihapus"); nav("/personas"); };

  const addMem = async () => {
    if (!newMem.trim()) return;
    await api.post("/memory", { persona_id: id, content: newMem });
    setNewMem(""); loadMem(); toast.success("Memori disimpan");
  };
  const toggleMem = async (m) => { await api.put(`/memory/${m.id}`, { enabled: !m.enabled }); loadMem(); };
  const delMem = async (m) => { await api.delete(`/memory/${m.id}`); loadMem(); };

  return (
    <div className="mx-auto max-w-5xl p-5 sm:p-8 lg:p-10 fade-up" data-testid="persona-detail-page">
      <button onClick={() => nav("/personas")} className="mb-4 flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"><ArrowLeft size={16} /> {p.name}</button>

      <div className="grid gap-6 md:grid-cols-[320px_1fr]">
        <div>
          <div className="aivora-card overflow-hidden">
            <div className="aspect-square bg-slate-50">
              {p.portrait ? <img src={p.portrait} alt={p.name} className="h-full w-full object-cover" data-testid="persona-portrait" />
                : <div className="flex h-full w-full items-center justify-center text-5xl font-bold text-slate-600">{p.name[0]}</div>}
            </div>
            <div className="p-4">
              <h1 className="text-xl font-bold text-slate-900">{p.name}</h1>
              <p className="text-xs text-slate-500">v{p.version} · {modelLabel(p.model)}</p>
            </div>
          </div>
          <div className="mt-3">
            <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">Otak Persona (Model AI)</label>
            <select className="input-dark py-2.5" value={p.model} onChange={(e) => changeModel(e.target.value)} data-testid="persona-model-select">
              {models.map((m) => <option key={m.id} value={m.id}>{m.label} — {m.tagline}</option>)}
            </select>
          </div>
          <div className="mt-3 space-y-2">
            <button onClick={startChat} data-testid="persona-start-chat" className="btn-grad flex w-full items-center justify-center gap-2 rounded-xl py-3 text-sm"><MessageSquare size={16} /> Mulai Chat</button>
            <button onClick={regen} disabled={busy} data-testid="persona-regen-portrait" className="flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 py-2.5 text-sm text-slate-700 hover:bg-slate-100"><RefreshCw size={15} /> Buat Ulang Potret (25 kredit)</button>
            <div className="flex gap-2">
              <button onClick={dup} className="flex flex-1 items-center justify-center gap-1 rounded-xl border border-slate-200 py-2.5 text-sm text-slate-700 hover:bg-slate-100"><Copy size={14} /> Duplikat</button>
              <button onClick={del} data-testid="persona-delete" className="rounded-xl border border-[#EF4444]/40 px-4 text-[#EF4444] hover:bg-[#EF4444]/10"><Trash2 size={16} /></button>
            </div>
          </div>
        </div>

        <div>
          <div className="mb-4 flex gap-2 border-b border-slate-200">
            {[["profile", "Profil"], ["appearance", "Penampilan"], ["memory", "Memori"]].map(([k, l]) => (
              <button key={k} onClick={() => setTab(k)} data-testid={`persona-tab-${k}`}
                className={`-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition ${tab === k ? "border-[#00D1FF] text-slate-900" : "border-transparent text-slate-500"}`}>{l}</button>
            ))}
          </div>

          {tab === "profile" && (
            <div className="space-y-4">
              <Row label="Ringkasan" value={prof.identity?.summary} />
              <Row label="Latar belakang" value={prof.identity?.background} />
              <Row label="Pekerjaan" value={prof.identity?.occupation} />
              <Row label="Sifat utama" value={(prof.personality?.primary_traits || []).join(", ")} />
              <Row label="Gaya komunikasi" value={prof.personality?.communication_style} />
              <Row label="Formalitas" value={prof.personality?.formality} />
              <Row label="Batasan" value={prof.personality?.boundaries} />
              <Row label="Instruksi sistem" value={prof.system_instructions} />
            </div>
          )}
          {tab === "appearance" && (
            <div className="space-y-4">
              <Row label="Wajah" value={prof.appearance?.face} />
              <Row label="Rambut" value={prof.appearance?.hair} />
              <Row label="Mata" value={prof.appearance?.eyes} />
              <Row label="Pakaian" value={prof.appearance?.clothing} />
              <Row label="Ciri khas" value={prof.appearance?.distinctive} />
              <Row label="Gaya visual" value={prof.appearance?.visual_style} />
            </div>
          )}
          {tab === "memory" && (
            <div>
              <div className="mb-4 flex gap-2">
                <input className="input-dark" placeholder="Tambah memori (mis. Saya suka kopi hitam)" value={newMem} onChange={(e) => setNewMem(e.target.value)} data-testid="mem-input" />
                <button onClick={addMem} data-testid="mem-add" className="btn-grad rounded-xl px-4"><Plus size={18} /></button>
              </div>
              {mems.length === 0 ? <p className="text-sm text-slate-500">Belum ada memori untuk persona ini.</p> : mems.map((m) => (
                <div key={m.id} className="mb-2 flex items-center justify-between rounded-xl bg-slate-50 px-4 py-3" data-testid={`mem-${m.id}`}>
                  <span className={`text-sm ${m.enabled ? "text-slate-700" : "text-slate-500 line-through"}`}>{m.content}</span>
                  <div className="flex items-center gap-3">
                    <button onClick={() => toggleMem(m)} className="text-xs text-[#2F6BFF]">{m.enabled ? "Nonaktif" : "Aktif"}</button>
                    <button onClick={() => delMem(m)} className="text-slate-500 hover:text-[#EF4444]"><Trash2 size={14} /></button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="mt-6 aivora-card p-4">
            <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900"><Wand2 size={15} className="text-[#7C3AED]" /> Edit dengan bahasa alami</h3>
            <div className="flex gap-2">
              <input className="input-dark" placeholder="mis. Buat lebih tenang dan ubah rambut jadi pendek" value={instr} onChange={(e) => setInstr(e.target.value)} data-testid="persona-edit-input" />
              <button onClick={applyEdit} disabled={busy} className="btn-grad rounded-xl px-5 text-sm" data-testid="persona-edit-apply">Terapkan</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }) {
  if (!value) return null;
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</p>
      <p className="mt-0.5 text-sm text-slate-700">{value}</p>
    </div>
  );
}
