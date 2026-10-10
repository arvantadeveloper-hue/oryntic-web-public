import React, { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, MessageSquare, RefreshCw, Wand2, Copy, Trash2, Brain, Plus, Volume2, Loader2, Star } from "lucide-react";
import { toast } from "sonner";
import { api, API_BASE, getToken } from "../lib/api";
import { VoiceModelPicker } from "../components/VoiceModelPicker";
import { ToolsPicker } from "../components/ToolsPicker";
import { CharacterPicker } from "../components/CharacterPicker";
import { KnowledgeTab } from "../components/KnowledgeTab";
import { useAuth } from "../context/AuthContext";

const VOICE_LABELS = {
  alloy: "Netral & seimbang", nova: "Hangat & ramah", shimmer: "Lembut & cerah",
  echo: "Tenang & jernih", fable: "Ekspresif & bercerita", onyx: "Dalam & berwibawa",
  coral: "Ceria & bersahabat", sage: "Bijak & menenangkan", ash: "Mantap & percaya diri",
};
const VOICE_SAMPLE = "Halo, senang berkenalan dengan Anda. Saya siap membantu kapan saja.";

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
  const [voices, setVoices] = useState([]);
  const [previewing, setPreviewing] = useState(null);
  const previewAudioRef = useRef(null);

  useEffect(() => { api.get("/models").then((r) => setModels(r.data.models)).catch(() => {}); api.get("/voice/voices").then((r) => setVoices(r.data.voices)).catch(() => {}); }, []);
  useEffect(() => () => { try { previewAudioRef.current?.pause(); } catch (e) {} }, []);
  const modelLabel = (key) => (models.find((m) => m.id === key) || {}).label || key;
  const changeModel = async (key) => { const r = await api.put(`/personas/${id}`, { profile: p.profile, model: key }); setP(r.data); toast.success("Model diperbarui"); };
  const changeCharacter = async (character_id) => {
    try { const r = await api.put(`/personas/${id}`, { profile: p.profile, character_id }); setP(r.data); toast.success("Karakter persona diperbarui — berlaku di chat & panggilan berikutnya"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengubah karakter"); }
  };
  const changeTools = async (tools) => { const r = await api.put(`/personas/${id}`, { profile: p.profile, tools }); setP(r.data); toast.success("Kemampuan tambahan diperbarui"); };
  const changeVoice = async (v) => { const r = await api.put(`/personas/${id}`, { profile: p.profile, voice: v }); setP(r.data); toast.success("Suara diperbarui"); };
  const previewVoice = async (v) => {
    try { previewAudioRef.current?.pause(); } catch (e) {}
    setPreviewing(v);
    try {
      const res = await fetch(`${API_BASE}/voice/tts`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` }, body: JSON.stringify({ text: VOICE_SAMPLE, voice: v }) });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const a = new Audio(URL.createObjectURL(blob)); previewAudioRef.current = a;
      a.onended = () => setPreviewing(null); a.onerror = () => setPreviewing(null);
      await a.play(); refreshUser();
    } catch (e) { setPreviewing(null); toast.error("Gagal memutar contoh suara"); }
  };

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
  const pinMem = async (m) => { await api.put(`/memory/${m.id}`, { pinned: !m.pinned }); loadMem(); };
  const delMem = async (m) => { await api.delete(`/memory/${m.id}`); loadMem(); };

  return (
    <div className="mx-auto max-w-5xl p-5 sm:p-8 lg:p-10 fade-up" data-testid="persona-detail-page">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <button onClick={() => nav("/personas")} className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"><ArrowLeft size={16} /> Kembali</button>
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 overflow-hidden rounded-full bg-[#EEF3FF]">{p.portrait ? <img src={p.portrait} alt={p.name} className="h-full w-full object-cover" /> : <div className="flex h-full w-full items-center justify-center text-sm font-bold text-slate-600">{p.name[0]}</div>}</div>
          <div><h1 className="text-lg font-bold leading-tight text-slate-900">{p.name}</h1><p className="text-xs text-slate-500">v{p.version} · {modelLabel(p.model)}</p></div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={dup} data-testid="persona-duplicate" className="flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 hover:bg-slate-100"><Copy size={14} /> <span className="hidden sm:inline">Duplikat</span></button>
          <button onClick={del} data-testid="persona-delete" className="flex items-center gap-1.5 rounded-xl border border-[#EF4444]/40 bg-white px-3 py-2.5 text-sm text-[#EF4444] hover:bg-[#EF4444]/10"><Trash2 size={15} /> <span className="hidden sm:inline">Hapus</span></button>
          <button onClick={startChat} data-testid="persona-start-chat" className="btn-grad flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm"><MessageSquare size={16} /> Mulai Chat</button>
        </div>
      </div>

      <div className="aivora-card overflow-hidden" data-testid="persona-tabs-card">
      <div className="flex gap-1 overflow-x-auto border-b border-[#E7ECF3] bg-slate-50/70 px-3">
        {[["profile", "Profil"], ["settings", "Pengaturan"], ["appearance", "Penampilan"], ["memory", "Memori"], ["knowledge", "Pengetahuan"]].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`persona-tab-${k}`}
            className={`-mb-px shrink-0 border-b-2 px-4 py-3 text-sm font-medium transition ${tab === k ? "border-[#2F6BFF] text-slate-900" : "border-transparent text-slate-500 hover:text-slate-700"}`}>{l}</button>
        ))}
      </div>
      <div className="bg-white p-5 sm:p-6">

      {tab === "profile" && (
        <div className="grid gap-6 md:grid-cols-[280px_1fr]" data-testid="persona-profile-tab">
          <div>
            <div className="overflow-hidden rounded-2xl border border-[#E7ECF3] bg-slate-50">
              <div className="aspect-square">
                {p.portrait ? <img src={p.portrait} alt={p.name} className="h-full w-full object-cover" data-testid="persona-portrait" />
                  : <div className="flex h-full w-full items-center justify-center text-5xl font-bold text-slate-600">{p.name[0]}</div>}
              </div>
            </div>
            <button onClick={regen} disabled={busy} data-testid="persona-regen-portrait" className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 py-2.5 text-sm text-slate-700 hover:bg-slate-100"><RefreshCw size={15} /> Buat Ulang Potret (25 kredit)</button>
          </div>
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
        </div>
      )}

      {tab === "settings" && (
        <div className="grid gap-6 md:grid-cols-2" data-testid="persona-settings-tab">
          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">Otak Persona (Model AI)</label>
              <select className="input-dark py-2.5" value={p.model} onChange={(e) => changeModel(e.target.value)} data-testid="persona-model-select">
                {["openai", "anthropic", "gemini"].filter((pv) => models.some((m) => m.provider === pv)).map((pv) => (
                  <optgroup key={pv} label={models.find((m) => m.provider === pv)?.provider_label || pv}>
                    {models.filter((m) => m.provider === pv).map((m) => <option key={m.id} value={m.id}>{m.label} — {m.tagline}{m.credits_typical != null ? ` (≈${m.credits_typical} kredit/pesan)` : ""}</option>)}
                  </optgroup>
                ))}
              </select>
            </div>
            <CharacterPicker value={p.character_id} onChange={changeCharacter} testid="persona-character-select" />
            <ToolsPicker modelKey={p.model} value={p.tools || []} onChange={changeTools} compact />
            <VoiceModelPicker compact />
          </div>
          <div className="space-y-4">
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">Karakter Suara</label>
                <button onClick={() => previewVoice(p.voice || "alloy")} data-testid="persona-voice-preview-current" className="flex items-center gap-1 text-xs font-semibold text-[#2F6BFF]" title="Dengar suara saat ini">
                  {previewing === (p.voice || "alloy") ? <Loader2 size={13} className="animate-spin" /> : <Volume2 size={13} />} Dengar
                </button>
              </div>
              <div className="grid grid-cols-1 gap-2">
                {voices.map((v) => {
                  const on = (p.voice || "alloy") === v;
                  return (
                    <div key={v} data-testid={`persona-voice-${v}`}
                      className={`flex items-center gap-2 rounded-xl border p-2.5 transition ${on ? "border-[#2F6BFF] bg-[#EEF3FF]" : "border-[#E7ECF3] hover:bg-slate-50"}`}>
                      <button type="button" onClick={() => changeVoice(v)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
                        <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${on ? "btn-grad border-transparent" : "border-slate-300"}`}>{on && <span className="h-1.5 w-1.5 rounded-full bg-white" />}</span>
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-bold capitalize text-slate-900">{v}</span>
                          <span className="block truncate text-xs text-slate-400">{VOICE_LABELS[v] || "Suara"}</span>
                        </span>
                      </button>
                      <button type="button" onClick={() => previewVoice(v)} data-testid={`persona-voice-preview-${v}`}
                        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[#E7ECF3] text-[#2F6BFF] hover:bg-[#EEF3FF]" title="Dengar contoh">
                        {previewing === v ? <Loader2 size={15} className="animate-spin" /> : <Volume2 size={15} />}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
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
      {tab === "knowledge" && <KnowledgeTab personaId={id} />}
      {tab === "memory" && (
        <div>
          <div className="mb-4 flex gap-2">
            <input className="input-dark" placeholder="Tambah memori (mis. Saya suka kopi hitam)" value={newMem} onChange={(e) => setNewMem(e.target.value)} data-testid="mem-input" />
            <button onClick={addMem} data-testid="mem-add" className="btn-grad rounded-xl px-4"><Plus size={18} /></button>
          </div>
          <p className="mb-3 text-xs text-slate-500">Memori ⭐ <b>prioritas</b> selalu ikut di setiap percakapan; memori lain dipilih otomatis sesuai relevansi pesan (maks 10) untuk menghemat token.</p>
          {mems.length === 0 ? <p className="text-sm text-slate-500">Belum ada memori untuk persona ini.</p> : [...mems].sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0)).map((m) => (
            <div key={m.id} className="mb-2 flex items-center justify-between rounded-xl bg-slate-50 px-4 py-3" data-testid={`mem-${m.id}`}>
              <span className={`flex items-center gap-2 text-sm ${m.enabled ? "text-slate-700" : "text-slate-500 line-through"}`}>{m.pinned && <Star size={13} className="shrink-0 fill-[#F59E0B] text-[#F59E0B]" />}{m.content}</span>
              <div className="flex items-center gap-3">
                <button onClick={() => pinMem(m)} title={m.pinned ? "Lepas prioritas" : "Jadikan prioritas (selalu diingat)"} className={m.pinned ? "text-[#F59E0B]" : "text-slate-400 hover:text-[#F59E0B]"} data-testid={`mem-pin-${m.id}`}><Star size={15} className={m.pinned ? "fill-[#F59E0B]" : ""} /></button>
                <button onClick={() => toggleMem(m)} className="text-xs text-[#2F6BFF]">{m.enabled ? "Nonaktif" : "Aktif"}</button>
                <button onClick={() => delMem(m)} className="text-slate-500 hover:text-[#EF4444]"><Trash2 size={14} /></button>
              </div>
            </div>
          ))}
        </div>
      )}

      </div>
      </div>

      {(tab === "profile" || tab === "appearance") && (
        <div className="mt-6 aivora-card p-4">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900"><Wand2 size={15} className="text-[#7C3AED]" /> Edit dengan bahasa alami</h3>
          <div className="flex gap-2">
            <input className="input-dark" placeholder="mis. Buat lebih tenang dan ubah rambut jadi pendek" value={instr} onChange={(e) => setInstr(e.target.value)} data-testid="persona-edit-input" />
            <button onClick={applyEdit} disabled={busy} className="btn-grad rounded-xl px-5 text-sm" data-testid="persona-edit-apply">Terapkan</button>
          </div>
        </div>
      )}
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
