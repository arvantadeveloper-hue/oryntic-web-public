import React, { useCallback, useEffect, useState } from "react";
import { Headset, Loader2, Save, Video, CheckCircle2, AlertTriangle, RefreshCw, Image as ImageIcon, Sparkles, Send } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../lib/api";
import { apiErr } from "../../lib/apiErr";

const MODELS = ["gpt-luna", "gpt-astra", "gpt-terra", "gpt-5-5", "claude-sonnet", "gemini-pro"];
const VOICE_MODELS = ["gpt-realtime-2.1-mini", "gpt-realtime-2.1", "gpt-realtime-2.0"];
const VOICES = ["marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"];

const Label = ({ children }) => <label className="mb-1 block text-xs font-semibold text-slate-600">{children}</label>;

export default function PlatformSupportAgent() {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);
  const [avatars, setAvatars] = useState(null);
  const [loadingAv, setLoadingAv] = useState(false);
  const [avScope, setAvScope] = useState("mine");
  const [previewById, setPreviewById] = useState({});
  const [pvMsg, setPvMsg] = useState("");
  const [pvReply, setPvReply] = useState("");
  const [pvBusy, setPvBusy] = useState(false);
  const [pvSession, setPvSession] = useState(null);

  useEffect(() => { api.get("/platform/support-agent").then((r) => setCfg(r.data)).catch(() => setCfg({})); }, []);
  const set = (k, v) => setCfg((c) => ({ ...c, [k]: v }));

  const save = async () => {
    setSaving(true);
    try {
      const { liveavatar_key_set, updated_at, ...body } = cfg;
      const r = await api.put("/platform/support-agent", body);
      setCfg(r.data);
      toast.success("Pengaturan Oryntix disimpan — berlaku untuk percakapan & panggilan berikutnya");
    } catch (e) {
      toast.error(apiErr(e, "Gagal menyimpan pengaturan"));
    } finally { setSaving(false); }
  };

  // Keep numeric fields always a valid in-range integer so we never PUT NaN/null (-> 422 crash).
  const setNum = (k, raw, min, max) => {
    let n = parseInt(raw, 10);
    if (Number.isNaN(n)) n = min;
    n = Math.max(min, Math.min(max, n));
    set(k, n);
  };

  const loadAvatars = useCallback(async (scope) => {
    setLoadingAv(true);
    try {
      const r = await api.get("/platform/support-agent/avatars", { params: { mine: scope === "mine", page_size: 24 } });
      const items = r.data.items || [];
      setAvatars(items);
      setPreviewById((m) => ({ ...m, ...Object.fromEntries(items.filter((a) => a.preview).map((a) => [a.id, a.preview])) }));
    } catch (e) {
      toast.error(apiErr(e, "Gagal memuat daftar avatar"));
      setAvatars([]);
    } finally { setLoadingAv(false); }
  }, []);

  // Resolve the current avatar's preview live by id on mount (stored path/URL may be main-app-only or stale).
  const keySet = Boolean(cfg?.liveavatar_key_set);
  useEffect(() => { if (keySet) loadAvatars("mine"); }, [keySet, loadAvatars]);

  const pickAvatar = (a) => { setCfg((c) => ({ ...c, avatar_id: a.id, avatar_name: a.name || "", avatar_preview: a.preview || "", portrait: a.preview || c.portrait })); };

  // Keep the (read-only) portrait URL in sync with the selected avatar's real LiveAvatar photo once resolved.
  useEffect(() => {
    if (!cfg) return;
    const resolved = previewById[cfg.avatar_id];
    if (resolved && resolved !== cfg.portrait) set("portrait", resolved);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewById, cfg?.avatar_id]);

  const sendPreview = async () => {
    const msg = pvMsg.trim();
    if (!msg) return;
    setPvBusy(true); setPvReply("");
    try {
      const r = await api.post("/platform/support-agent/preview", { message: msg, session_id: pvSession });
      setPvReply(r.data.reply || ""); setPvSession(r.data.session_id || null);
    } catch (e) {
      toast.error(apiErr(e, "Gagal menghasilkan balasan"));
    } finally { setPvBusy(false); }
  };

  if (!cfg) return <p className="flex items-center gap-2 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p>;

  return (
    <div data-testid="platform-support-agent" className="mx-auto max-w-4xl">
      <div className="flex items-center gap-3">
        <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#2F6BFF] text-white"><Headset size={20} /></span>
        <div>
          <h1 className="text-2xl font-black text-slate-900">Asisten Bawaan — Oryntix</h1>
          <p className="max-w-2xl text-sm text-slate-500">Customer Support Agent yang tampil untuk semua workspace. Hanya dapat diatur dari sini; pengguna tidak bisa mengedit/menghapusnya. Tanpa alat model (web search, kode, gambar) — hanya pengetahuan Oryntix.</p>
        </div>
      </div>

      {/* Kartu 1 — Identitas & model */}
      <div className="mt-6 aivora-card p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-900">Identitas & model</h2>
          <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <input type="checkbox" checked={!!cfg.enabled} onChange={(e) => set("enabled", e.target.checked)} data-testid="sa-enabled" className="h-4 w-4 rounded border-slate-300 text-[#2F6BFF]" />
            Aktif untuk semua pengguna
          </label>
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div><Label>Nama</Label><input className="input-dark" value={cfg.name || ""} onChange={(e) => set("name", e.target.value)} maxLength={40} data-testid="sa-name" /></div>
          <div><Label>Ringkasan</Label><input className="input-dark" value={cfg.summary || ""} onChange={(e) => set("summary", e.target.value)} maxLength={120} data-testid="sa-summary" /></div>
          <div className="sm:col-span-2"><Label>URL foto profil</Label><input className="input-dark cursor-not-allowed bg-slate-50 text-slate-500" readOnly value={cfg.portrait || ""} data-testid="sa-portrait" /><p className="mt-1 text-xs text-slate-400">Otomatis terisi dengan URL foto asli dari avatar yang dipilih di bawah.</p></div>
          <div>
            <Label>Model otak</Label>
            <select className="input-dark" value={cfg.model} onChange={(e) => set("model", e.target.value)} data-testid="sa-model">{MODELS.map((m) => <option key={m} value={m}>{m}</option>)}</select>
          </div>
          <div>
            <Label>Model suara (Realtime)</Label>
            <select className="input-dark" value={cfg.voice_model} onChange={(e) => set("voice_model", e.target.value)} data-testid="sa-voice-model">{VOICE_MODELS.map((m) => <option key={m} value={m}>{m}</option>)}</select>
          </div>
          <div>
            <Label>Suara</Label>
            <select className="input-dark" value={cfg.voice} onChange={(e) => set("voice", e.target.value)} data-testid="sa-voice">{VOICES.map((m) => <option key={m} value={m}>{m}</option>)}</select>
          </div>
        </div>
        <div className="mt-4">
          <Label>System prompt (peran)</Label>
          <textarea className="input-dark font-mono text-xs" rows={8} value={cfg.system_prompt || ""} onChange={(e) => set("system_prompt", e.target.value)} maxLength={20000} data-testid="sa-prompt" />
        </div>
        <div className="mt-4">
          <Label>Pengetahuan Oryntix (knowledge base)</Label>
          <textarea className="input-dark font-mono text-xs" rows={8} value={cfg.knowledge || ""} onChange={(e) => set("knowledge", e.target.value)} maxLength={60000} data-testid="sa-knowledge" />
        </div>
      </div>

      {/* Kartu 2 — Video interaktif (LiveAvatar) */}
      <div className="mt-6 aivora-card p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-sm font-bold text-slate-900"><Video size={16} className="text-[#2F6BFF]" /> Video interaktif (LiveAvatar)</h2>
          {cfg.liveavatar_key_set
            ? <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700" data-testid="sa-la-key"><CheckCircle2 size={13} /> LIVEAVATAR_API_KEY terpasang</span>
            : <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700" data-testid="sa-la-key"><AlertTriangle size={13} /> LIVEAVATAR_API_KEY belum diatur</span>}
        </div>

        <label className="mt-4 flex items-center gap-2 text-sm font-semibold text-slate-700">
          <input type="checkbox" checked={!!cfg.video_enabled} onChange={(e) => set("video_enabled", e.target.checked)} data-testid="sa-video-enabled" className="h-4 w-4 rounded border-slate-300 text-[#2F6BFF]" />
          Tawarkan video di panggilan
        </label>

        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <div><Label>Harga video (kredit/detik)</Label><input type="number" min={0} max={1000} className="input-dark" value={cfg.video_credits_per_sec} onChange={(e) => setNum("video_credits_per_sec", e.target.value, 0, 1000)} data-testid="sa-video-price" /></div>
          <div><Label>Durasi maksimal (menit)</Label><input type="number" min={1} max={240} className="input-dark" value={cfg.video_max_minutes} onChange={(e) => setNum("video_max_minutes", e.target.value, 1, 240)} data-testid="sa-video-max" /></div>
          <div><Label>Peringatan sebelum batas (menit)</Label><input type="number" min={1} max={30} className="input-dark" value={cfg.video_warn_minutes} onChange={(e) => setNum("video_warn_minutes", e.target.value, 1, 30)} data-testid="sa-video-warn" /></div>
        </div>

        <label className="mt-4 flex items-start gap-2 text-sm font-semibold text-slate-700">
          <input type="checkbox" checked={!!cfg.sandbox} onChange={(e) => set("sandbox", e.target.checked)} data-testid="sa-sandbox" className="mt-0.5 h-4 w-4 rounded border-slate-300 text-[#2F6BFF]" />
          <span>Mode sandbox<span className="block text-xs font-normal text-slate-500">Uji coba tanpa kredit LiveAvatar (avatar Wayne, maks ±1 menit). Matikan untuk produksi.</span></span>
        </label>

        {/* Avatar terpilih */}
        <div className="mt-6 rounded-2xl border border-[#E7ECF3] bg-[#F8FAFF] p-4" data-testid="sa-avatar-current">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Avatar terpilih</p>
          {(() => {
            const previewUrl = previewById[cfg.avatar_id] || [cfg.avatar_preview, cfg.portrait].find((u) => /^https?:\/\//.test(u || "")) || "";
            return (
              <div className="mt-3 flex items-center gap-4">
                <div className="relative h-16 w-16 shrink-0 overflow-hidden rounded-xl bg-slate-200">
                  <div className="absolute inset-0 flex items-center justify-center text-slate-400"><ImageIcon size={20} /></div>
                  {previewUrl && <img key={previewUrl} src={previewUrl} alt="" data-testid="sa-avatar-preview-img" className="absolute inset-0 h-full w-full object-cover" onError={(e) => { e.currentTarget.style.display = "none"; }} />}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-bold text-slate-900">{cfg.avatar_name || "—"}</p>
                  <p className="truncate font-mono text-xs text-slate-500">{cfg.avatar_id}</p>
                </div>
              </div>
            );
          })()}
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div><Label>Nama avatar</Label><input className="input-dark" value={cfg.avatar_name || ""} onChange={(e) => set("avatar_name", e.target.value)} maxLength={120} placeholder="mis. Oryntix (custom)" data-testid="sa-avatar-name" /></div>
            <div><Label>Avatar ID (terpilih)</Label><input className="input-dark cursor-not-allowed bg-slate-50 font-mono text-xs text-slate-500" readOnly value={cfg.avatar_id || ""} data-testid="sa-avatar-id" /></div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-600"><input type="radio" name="avscope" checked={avScope === "mine"} onChange={() => setAvScope("mine")} /> Avatar saya</label>
            <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-600"><input type="radio" name="avscope" checked={avScope === "public"} onChange={() => setAvScope("public")} /> Publik</label>
            <button onClick={() => loadAvatars(avScope)} disabled={loadingAv} className="btn-soft !py-1.5 !text-xs" data-testid="sa-load-avatars">{loadingAv ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Muat daftar</button>
          </div>

          {avatars && (
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="sa-avatar-grid">
              {avatars.length === 0 && <p className="col-span-full text-xs text-slate-400">Tidak ada avatar ditemukan.</p>}
              {avatars.map((a) => {
                const active = a.status && String(a.status).toUpperCase() === "ACTIVE";
                const selected = a.id === cfg.avatar_id;
                return (
                  <button key={a.id} onClick={() => pickAvatar(a)} data-testid={`sa-avatar-${a.id}`} className={`relative overflow-hidden rounded-xl border bg-white text-left transition ${selected ? "border-[#2F6BFF] ring-2 ring-[#2F6BFF]" : "border-[#E7ECF3] hover:border-[#B9CBFF]"}`}>
                    {selected && <span className="absolute right-1.5 top-1.5 z-10 rounded-full bg-[#2F6BFF] p-0.5 text-white"><CheckCircle2 size={14} /></span>}
                    <div className="aspect-square bg-slate-100">{a.preview ? <img src={a.preview} alt="" className="h-full w-full object-cover" /> : <div className="flex h-full w-full items-center justify-center text-slate-300"><ImageIcon size={22} /></div>}</div>
                    <div className="p-2">
                      <p className="truncate text-xs font-semibold text-slate-800">{a.name || a.id}</p>
                      <span className={`mt-1 inline-block rounded-full px-1.5 py-0.5 text-[10px] font-bold ${active ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>{a.status || "?"}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Kartu 3 — Pratinjau (uji chat) */}
      <div className="mt-6 aivora-card p-6" data-testid="sa-preview">
        <h2 className="flex items-center gap-2 text-sm font-bold text-slate-900"><Sparkles size={16} className="text-[#2F6BFF]" /> Pratinjau — uji chat Oryntix</h2>
        <p className="mt-1 text-xs text-slate-500">Uji kepribadian & pengetahuan dengan konfigurasi tersimpan saat ini. Pratinjau memakai model otak yang dikonfigurasi di atas (sama dengan produksi). Simpan dulu bila Anda baru mengubah prompt/knowledge.</p>
        <div className="mt-4 flex gap-2">
          <input className="input-dark flex-1" placeholder="Tulis pertanyaan uji, mis. Bagaimana cara membuat asisten?" value={pvMsg} onChange={(e) => setPvMsg(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !pvBusy) sendPreview(); }} maxLength={2000} data-testid="sa-preview-input" />
          <button onClick={sendPreview} disabled={pvBusy || !pvMsg.trim()} className="btn-primary shrink-0" data-testid="sa-preview-send">{pvBusy ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />} Kirim</button>
        </div>
        {(pvReply || pvBusy) && (
          <div className="mt-4 rounded-2xl border border-[#E7ECF3] bg-[#F8FAFF] p-4" data-testid="sa-preview-reply">
            <p className="mb-1 flex items-center gap-1.5 text-xs font-bold text-[#2F6BFF]"><Headset size={13} /> {cfg.name || "Oryntix"}</p>
            {pvBusy && !pvReply ? <p className="flex items-center gap-2 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Menyusun balasan…</p>
              : <p className="whitespace-pre-wrap text-sm text-slate-700">{pvReply}</p>}
          </div>
        )}
      </div>

      <div className="sticky bottom-4 mt-6 flex justify-end">
        <button onClick={save} disabled={saving} className="btn-primary shadow-lg" data-testid="sa-save">{saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Simpan</button>
      </div>
    </div>
  );
}
