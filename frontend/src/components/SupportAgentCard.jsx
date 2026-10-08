import React, { useEffect, useState } from "react";
import { Loader2, Save, Headset, Video, RefreshCw, CheckCircle2, Image as ImageIcon } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

const SEL = "input-dark w-full py-2 text-sm";
const Row = ({ label, hint, children, className = "" }) => (
  <label className={`block ${className}`}><span className="mb-1 block text-xs font-semibold text-slate-700">{label}</span>{children}{hint && <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>}</label>
);
const BRAINS = [["gpt-luna", "GPT Luna (default)"], ["gpt-astra", "GPT Astra"], ["gpt-terra", "GPT Terra"], ["gpt-5-5", "GPT 5.5"], ["claude-sonnet", "Claude Sonnet 5.5"], ["gemini-pro", "Gemini 3.1 Pro"]];
const VOICE_MODELS = [["gpt-realtime-2.1-mini", "GPT Realtime 2.1 Mini (default)"], ["gpt-realtime-2.1", "GPT Realtime 2.1"], ["gpt-realtime-2.0", "GPT Realtime 2.0"]];
const VOICES = ["marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"];

// Pengaturan asisten bawaan Oryntix (Customer Support Agent) — hanya untuk platform admin.
export const SupportAgentCard = () => {
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  const [avatars, setAvatars] = useState(null);
  const [mine, setMine] = useState(true);

  useEffect(() => { api.get("/admin/support-agent").then((r) => setF(r.data)).catch((e) => toast.error(e?.response?.data?.detail || "Gagal memuat pengaturan Oryntix")); }, []);

  const loadAvatars = async (m = mine) => {
    setAvatars("loading");
    try { const r = await api.get("/admin/support-agent/avatars", { params: { mine: m, page_size: 24 } }); setAvatars(r.data.items); }
    catch (e) { setAvatars([]); toast.error(e?.response?.data?.detail || "Gagal memuat avatar LiveAvatar"); }
  };

  if (!f) return <p className="flex items-center gap-2 text-sm text-slate-400" data-testid="sa-loading"><Loader2 size={14} className="animate-spin" /> Memuat…</p>;

  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.type === "number" ? parseInt(e.target.value, 10) || 0 : e.target.value });
  const save = async () => {
    setBusy(true);
    try {
      const { liveavatar_key_set, updated_at, ...body } = f;
      const r = await api.put("/admin/support-agent", body);
      setF({ ...r.data, liveavatar_key_set });
      toast.success("Pengaturan Oryntix disimpan — berlaku untuk percakapan & panggilan berikutnya");
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan"); } finally { setBusy(false); }
  };
  const pickAvatar = (a) => setF({ ...f, avatar_id: a.id, avatar_name: a.name, avatar_preview: a.preview || "" });

  return (
    <div data-testid="support-agent-settings">
      <p className="text-sm text-slate-500">Customer Support Agent yang tampil untuk semua workspace. Hanya dapat diatur dari sini; pengguna tidak bisa mengedit atau menghapusnya. Tanpa alat model (web search, kode, gambar) — hanya pengetahuan Oryntix.</p>

      <div className="mt-4 aivora-card p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#2F6BFF]/10 text-[#2F6BFF]"><Headset size={18} /></span>
          <p className="text-sm font-bold text-slate-900">Identitas & model</p>
          <label className="ml-auto flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={!!f.enabled} onChange={set("enabled")} data-testid="sa-enabled" /> Aktif untuk semua pengguna</label>
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <Row label="Nama"><input value={f.name} onChange={set("name")} data-testid="sa-name" className={SEL} /></Row>
          <Row label="Ringkasan"><input value={f.summary} onChange={set("summary")} data-testid="sa-summary" className={SEL} /></Row>
          <Row label="URL foto profil" hint="Path di aplikasi ini (mis. /brand/oryntix-support.jpg) atau URL penuh.">
            <div className="flex items-center gap-2">
              {f.portrait ? <img src={f.portrait} alt="" className="h-9 w-9 shrink-0 rounded-lg border border-[#E7ECF3] object-cover" data-testid="sa-portrait-preview" />
                : <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-400"><ImageIcon size={16} /></span>}
              <input value={f.portrait} onChange={set("portrait")} data-testid="sa-portrait" className={SEL} />
            </div>
          </Row>
          <Row label="Model otak (chat)"><select value={f.model} onChange={set("model")} data-testid="sa-model" className={SEL}>{BRAINS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Row>
          <Row label="Model suara (Realtime)"><select value={f.voice_model} onChange={set("voice_model")} data-testid="sa-voice-model" className={SEL}>{VOICE_MODELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Row>
          <Row label="Suara"><select value={f.voice} onChange={set("voice")} data-testid="sa-voice" className={SEL}>{VOICES.map((v) => <option key={v} value={v}>{v}</option>)}</select></Row>
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <Row label="System prompt (peran)" hint="Kosongkan untuk memakai peran dukungan bawaan platform."><textarea rows={8} value={f.system_prompt} onChange={set("system_prompt")} data-testid="sa-prompt" className={`${SEL} font-mono text-xs`} /></Row>
          <Row label="Pengetahuan Oryntix (knowledge base)" hint="Markdown bebas. Kosongkan untuk memakai knowledge base bawaan."><textarea rows={8} value={f.knowledge} onChange={set("knowledge")} data-testid="sa-knowledge" className={`${SEL} font-mono text-xs`} /></Row>
        </div>
      </div>

      <div className="mt-4 aivora-card p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#7C3AED]/10 text-[#7C3AED]"><Video size={18} /></span>
          <p className="text-sm font-bold text-slate-900">Video interaktif (LiveAvatar)</p>
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${f.liveavatar_key_set ? "bg-emerald-50 text-emerald-600" : "bg-amber-50 text-amber-700"}`} data-testid="sa-la-key">{f.liveavatar_key_set ? "LIVEAVATAR_API_KEY terpasang" : "LIVEAVATAR_API_KEY belum diatur"}</span>
          <label className="ml-auto flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={!!f.video_enabled} onChange={set("video_enabled")} data-testid="sa-video-enabled" /> Tawarkan video di panggilan</label>
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-4">
          <Row label="Harga video (kredit / detik)" hint="Ditagih per detik video berjalan, di luar tarif panggilan suara."><input type="number" min="0" value={f.video_credits_per_sec} onChange={set("video_credits_per_sec")} data-testid="sa-video-price" className={SEL} /></Row>
          <Row label="Durasi maksimal (menit)" hint="Video berhenti otomatis; suara tetap berlanjut."><input type="number" min="1" max="240" value={f.video_max_minutes} onChange={set("video_max_minutes")} data-testid="sa-video-max" className={SEL} /></Row>
          <Row label="Peringatan sebelum batas (menit)" hint="Oryntix memberi tahu dengan sopan tanpa memotong pengguna."><input type="number" min="1" max="30" value={f.video_warn_minutes} onChange={set("video_warn_minutes")} data-testid="sa-video-warn" className={SEL} /></Row>
          <Row label="Mode sandbox" hint="Uji coba tanpa kredit LiveAvatar: avatar sandbox (Wayne), maks ±1 menit — avatar pilihan di bawah TIDAK dipakai. Matikan untuk produksi."><label className="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={!!f.sandbox} onChange={set("sandbox")} data-testid="sa-sandbox" /> Sandbox aktif</label></Row>
        </div>
        {f.sandbox && <p className="mt-3 rounded-lg bg-amber-50 p-2.5 text-xs text-amber-700" data-testid="sa-sandbox-note">Sandbox aktif: pengguna akan melihat avatar sandbox LiveAvatar, bukan <b>{f.avatar_name || "avatar pilihan"}</b>, dan sesi dibatasi ±1 menit.</p>}
        <div className="mt-4 rounded-xl border border-[#E7ECF3] p-4">
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-sm font-semibold text-slate-900">Avatar terpilih</p>
            <span className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-1.5 text-xs" data-testid="sa-avatar-current">{f.avatar_preview && <img src={f.avatar_preview} alt="" className="h-8 w-8 rounded-md object-cover" />}<b>{f.avatar_name || "—"}</b><span className="font-mono text-slate-400">{f.avatar_id || "belum dipilih"}</span></span>
            <input value={f.avatar_id} onChange={set("avatar_id")} placeholder="Avatar ID LiveAvatar" data-testid="sa-avatar-id" className="input-dark w-72 py-1.5 font-mono text-xs" />
            <div className="ml-auto flex items-center gap-2 text-xs">
              <label className="flex items-center gap-1"><input type="radio" checked={mine} onChange={() => setMine(true)} data-testid="sa-avatars-mine" /> Avatar saya</label>
              <label className="flex items-center gap-1"><input type="radio" checked={!mine} onChange={() => setMine(false)} data-testid="sa-avatars-public" /> Publik</label>
              <button onClick={() => loadAvatars(mine)} className="flex items-center gap-1 rounded-lg bg-slate-100 px-3 py-1.5 font-semibold text-slate-700 hover:bg-slate-200" data-testid="sa-load-avatars"><RefreshCw size={12} /> Muat daftar</button>
            </div>
          </div>
          {avatars === "loading" && <p className="mt-3 flex items-center gap-2 text-xs text-slate-400"><Loader2 size={12} className="animate-spin" /> Memuat avatar…</p>}
          {Array.isArray(avatars) && (
            <div className="mt-3 grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-6" data-testid="sa-avatar-grid">
              {avatars.length === 0 && <p className="col-span-full text-xs text-slate-400">Tidak ada avatar.</p>}
              {avatars.map((a) => (
                <button key={a.id} onClick={() => pickAvatar(a)} data-testid={`sa-avatar-${a.id}`} className={`overflow-hidden rounded-xl border text-left transition hover:shadow ${f.avatar_id === a.id ? "border-[#2F6BFF] ring-2 ring-[#2F6BFF]/30" : "border-[#E7ECF3]"}`}>
                  <div className="relative aspect-square bg-slate-100">{a.preview && <img src={a.preview} alt={a.name} className="h-full w-full object-cover" />}{f.avatar_id === a.id && <CheckCircle2 size={16} className="absolute right-1.5 top-1.5 text-[#2F6BFF]" />}</div>
                  <div className="p-2"><p className="truncate text-xs font-semibold text-slate-800">{a.name}</p><p className={`text-[10px] ${a.status === "ACTIVE" ? "text-emerald-600" : "text-amber-600"}`}>{a.status}</p></div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 flex items-center justify-end gap-3">
        {f.updated_at && <span className="text-[11px] text-slate-400" data-testid="sa-updated">Terakhir disimpan: {new Date(f.updated_at).toLocaleString("id-ID")}</span>}
        <button onClick={save} disabled={busy} data-testid="sa-save" className="btn-primary py-2">{busy ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Simpan</button>
      </div>
    </div>
  );
};
