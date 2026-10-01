import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, Image as ImageIcon, Layers, ArrowLeft, Upload, Wand2, Check, Volume2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, API_BASE, getToken } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n";

const METHODS = [
  { id: "describe", icon: Sparkles, title: "Describe with AI", desc: "Tulis karakter yang Anda inginkan, AI menyusun profilnya." },
  { id: "photo", icon: ImageIcon, title: "Upload a Photo", desc: "Unggah foto sebagai referensi penampilan." },
  { id: "combine", icon: Layers, title: "Combine Both", desc: "Foto + instruksi teks untuk kontrol penuh." },
];

const VOICE_LABELS = {
  alloy: "Netral & seimbang", nova: "Hangat & ramah", shimmer: "Lembut & cerah",
  echo: "Tenang & jernih", fable: "Ekspresif & bercerita", onyx: "Dalam & berwibawa",
  coral: "Ceria & bersahabat", sage: "Bijak & menenangkan", ash: "Mantap & percaya diri",
};
const VOICE_SAMPLE = "Halo, senang berkenalan dengan Anda. Saya siap membantu kapan saja.";

export default function CreatePersona() {
  const nav = useNavigate();
  const { refreshUser } = useAuth();
  const { t } = useI18n();
  const [step, setStep] = useState("method");
  const [method, setMethod] = useState("describe");
  const [desc, setDesc] = useState("");
  const [photo, setPhoto] = useState(null);
  const [consent, setConsent] = useState(false);
  const [profile, setProfile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [models, setModels] = useState([]);
  const [modelKey, setModelKey] = useState("gpt-terra");
  const [voices, setVoices] = useState([]);
  const [voice, setVoice] = useState("nova");
  const [previewing, setPreviewing] = useState(null);
  const previewAudioRef = useRef(null);

  useEffect(() => { api.get("/models").then((r) => { setModels(r.data.models); setModelKey(r.data.default); }).catch(() => {}); }, []);
  useEffect(() => { api.get("/voice/voices").then((r) => setVoices(r.data.voices || [])).catch(() => {}); }, []);
  useEffect(() => () => { try { previewAudioRef.current?.pause(); } catch (e) {} }, []);

  const previewVoice = async (v) => {
    try { previewAudioRef.current?.pause(); } catch (e) {}
    setPreviewing(v);
    try {
      const res = await fetch(`${API_BASE}/voice/tts`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` }, body: JSON.stringify({ text: VOICE_SAMPLE, voice: v }) });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const a = new Audio(URL.createObjectURL(blob));
      previewAudioRef.current = a;
      a.onended = () => setPreviewing(null);
      a.onerror = () => setPreviewing(null);
      await a.play();
      refreshUser();
    } catch (e) { setPreviewing(null); toast.error("Gagal memutar contoh suara"); }
  };

  const onFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => setPhoto(reader.result);
    reader.readAsDataURL(f);
  };

  const needPhoto = method !== "describe";

  const generate = async () => {
    if (!desc.trim() && method !== "photo") { toast.error("Jelaskan karakter Anda"); return; }
    if (needPhoto && !photo) { toast.error("Unggah foto terlebih dahulu"); return; }
    if (needPhoto && !consent) { toast.error("Konfirmasi hak penggunaan foto"); return; }
    setBusy(true);
    try {
      const body = { description: desc || "Buat persona berdasarkan foto referensi.", method };
      if (photo) body.photo_b64 = photo.split(",")[1];
      const r = await api.post("/personas/generate-profile", body);
      setProfile(r.data.profile);
      refreshUser();
      setStep("review");
      toast.success(`Profil dibuat (${r.data.credits_used} kredit)`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat profil"); } finally { setBusy(false); }
  };

  const setPath = (section, key, val) => setProfile((p) => ({ ...p, [section]: { ...(p[section] || {}), [key]: val } }));

  const saveAndPortrait = async () => {
    setBusy(true);
    try {
      const r = await api.post("/personas", { profile, reference_photo: photo || null, model: modelKey, voice });
      const pid = r.data.id;
      toast.success("Persona disimpan, membuat potret...");
      try {
        await api.post(`/personas/${pid}/portrait`, { style: profile?.appearance?.visual_style || "cinematic realistic", use_reference: !!photo });
        refreshUser();
      } catch (e) { toast.message("Potret gagal dibuat, Anda bisa coba lagi di editor."); }
      nav(`/personas/${pid}`);
    } catch (e) { toast.error("Gagal menyimpan"); } finally { setBusy(false); }
  };

  return (
    <div className="mx-auto max-w-3xl p-5 sm:p-8 lg:p-10 fade-up" data-testid="create-persona-page">
      <button onClick={() => (step === "method" ? nav("/personas") : setStep("method"))} className="mb-4 flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900">
        <ArrowLeft size={16} /> {t("common.back")}
      </button>
      <h1 className="text-3xl font-extrabold text-slate-900">{t("persona.create")}</h1>

      {step === "method" && (
        <>
          <p className="mt-1 text-sm text-slate-500">Pilih cara membuat persona Anda.</p>
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            {METHODS.map((m) => (
              <button key={m.id} data-testid={`method-${m.id}`} onClick={() => { setMethod(m.id); setStep("input"); }}
                className="aivora-card aivora-card-hover flex flex-col items-start gap-3 p-5 text-left">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl" style={{ background: "rgba(0,209,255,.14)", color: "#00D1FF" }}><m.icon size={22} /></span>
                <span className="font-bold text-slate-900">{m.title}</span>
                <span className="text-xs text-slate-500">{m.desc}</span>
              </button>
            ))}
          </div>
        </>
      )}

      {step === "input" && (
        <div className="mt-6 space-y-5">
          {needPhoto && (
            <div>
              <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-500">Foto referensi</label>
              <label className="flex cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed border-slate-200 py-8 hover:border-[#00D1FF]" data-testid="photo-upload">
                {photo ? <img src={photo} alt="" className="h-28 w-28 rounded-xl object-cover" /> : <><Upload className="mb-2 text-slate-500" /><span className="text-sm text-slate-500">Klik untuk unggah</span></>}
                <input type="file" accept="image/*" className="hidden" onChange={onFile} />
              </label>
              <button onClick={() => setConsent(!consent)} data-testid="photo-consent" className="mt-3 flex items-center gap-2 text-left text-xs text-slate-600">
                <span className={`flex h-4 w-4 items-center justify-center rounded border ${consent ? "btn-grad border-transparent" : "border-slate-300"}`}>{consent && <Check size={11} />}</span>
                Saya memiliki hak untuk menggunakan foto ini. Foto hanya dipakai sebagai referensi visual.
              </button>
            </div>
          )}
          <div>
            <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-500">
              {method === "photo" ? "Catatan tambahan (opsional)" : "Deskripsikan karakter Anda"}
            </label>
            <textarea className="input-dark min-h-[140px]" data-testid="persona-desc"
              placeholder="Contoh: Mentor produktivitas bernama Nadia, tenang, cerdas, humoris, suka kopi, membantu saya merencanakan minggu."
              value={desc} onChange={(e) => setDesc(e.target.value)} />
          </div>
          <button onClick={generate} disabled={busy} data-testid="generate-profile-btn" className="btn-grad flex w-full items-center justify-center gap-2 rounded-xl py-3.5 text-sm">
            <Wand2 size={18} /> {busy ? "Membuat profil..." : "Buat Profil dengan AI"}
          </button>
        </div>
      )}

      {step === "review" && profile && (
        <div className="mt-6 space-y-5" data-testid="profile-review">
          <p className="text-sm text-slate-500">Tinjau & edit profil sebelum menyimpan.</p>
          <Field label="Nama" value={profile.identity?.name || ""} onChange={(v) => setPath("identity", "name", v)} testid="rev-name" />
          <FieldArea label="Ringkasan" value={profile.identity?.summary || ""} onChange={(v) => setPath("identity", "summary", v)} testid="rev-summary" />
          <FieldArea label="Gaya komunikasi" value={profile.personality?.communication_style || ""} onChange={(v) => setPath("personality", "communication_style", v)} testid="rev-style" />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Rambut" value={profile.appearance?.hair || ""} onChange={(v) => setPath("appearance", "hair", v)} testid="rev-hair" />
            <Field label="Pakaian" value={profile.appearance?.clothing || ""} onChange={(v) => setPath("appearance", "clothing", v)} testid="rev-clothing" />
            <Field label="Gaya visual" value={profile.appearance?.visual_style || ""} onChange={(v) => setPath("appearance", "visual_style", v)} testid="rev-visual" />
            <Field label="Bahasa utama" value={profile.language?.primary || ""} onChange={(v) => setPath("language", "primary", v)} testid="rev-lang" />
          </div>
          <FieldArea label="Instruksi sistem" value={profile.system_instructions || ""} onChange={(v) => setProfile((p) => ({ ...p, system_instructions: v }))} testid="rev-sysinstr" />
          <div>
            <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-500">Otak Persona (Model AI)</label>
            <div className="grid gap-2 sm:grid-cols-2">
              {models.map((m) => {
                const on = modelKey === m.id;
                return (
                  <button key={m.id} type="button" onClick={() => setModelKey(m.id)} data-testid={`model-${m.id}`}
                    className={`flex items-start gap-3 rounded-xl border p-3 text-left transition ${on ? "border-[#2F6BFF] bg-[#EEF3FF]" : "border-[#E7ECF3] hover:bg-slate-50"}`}>
                    <span className="mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: m.accent }} />
                    <span><span className="block text-sm font-bold text-slate-900">{m.label}</span>
                      <span className="block text-xs text-slate-400">{m.tagline}</span></span>
                  </button>
                );
              })}
            </div>
          </div>
          <div>
            <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-500">Suara Persona (TTS)</label>
            <p className="mb-2 text-xs text-slate-400">Pilih suara untuk jawaban audio & mode panggilan. Tekan ikon untuk mendengar contoh.</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {voices.map((v) => {
                const on = voice === v;
                return (
                  <div key={v} data-testid={`voice-${v}`}
                    className={`flex items-center gap-2 rounded-xl border p-3 transition ${on ? "border-[#2F6BFF] bg-[#EEF3FF]" : "border-[#E7ECF3] hover:bg-slate-50"}`}>
                    <button type="button" onClick={() => setVoice(v)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
                      <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${on ? "btn-grad border-transparent" : "border-slate-300"}`}>{on && <Check size={10} />}</span>
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-bold capitalize text-slate-900">{v}</span>
                        <span className="block truncate text-xs text-slate-400">{VOICE_LABELS[v] || "Suara"}</span>
                      </span>
                    </button>
                    <button type="button" onClick={() => previewVoice(v)} data-testid={`voice-preview-${v}`}
                      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[#E7ECF3] text-[#2F6BFF] hover:bg-[#EEF3FF]" title="Dengar contoh">
                      {previewing === v ? <Loader2 size={15} className="animate-spin" /> : <Volume2 size={15} />}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
          <button onClick={saveAndPortrait} disabled={busy} data-testid="save-persona-btn" className="btn-grad flex w-full items-center justify-center gap-2 rounded-xl py-3.5 text-sm">
            <Sparkles size={18} /> {busy ? "Menyimpan & membuat potret..." : "Simpan & Buat Potret"}
          </button>
        </div>
      )}
    </div>
  );
}

function Field({ label, value, onChange, testid }) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</label>
      <input className="input-dark" value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid} />
    </div>
  );
}
function FieldArea({ label, value, onChange, testid }) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">{label}</label>
      <textarea className="input-dark min-h-[80px]" value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid} />
    </div>
  );
}
