import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, Image as ImageIcon, Layers, ArrowLeft, Upload, Wand2, Check } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n";

const METHODS = [
  { id: "describe", icon: Sparkles, title: "Describe with AI", desc: "Tulis karakter yang Anda inginkan, AI menyusun profilnya." },
  { id: "photo", icon: ImageIcon, title: "Upload a Photo", desc: "Unggah foto sebagai referensi penampilan." },
  { id: "combine", icon: Layers, title: "Combine Both", desc: "Foto + instruksi teks untuk kontrol penuh." },
];

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
      const r = await api.post("/personas", { profile, reference_photo: photo || null });
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
      <button onClick={() => (step === "method" ? nav("/personas") : setStep("method"))} className="mb-4 flex items-center gap-1 text-sm text-slate-400 hover:text-white">
        <ArrowLeft size={16} /> {t("common.back")}
      </button>
      <h1 className="text-3xl font-extrabold text-white">{t("persona.create")}</h1>

      {step === "method" && (
        <>
          <p className="mt-1 text-sm text-slate-400">Pilih cara membuat persona Anda.</p>
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            {METHODS.map((m) => (
              <button key={m.id} data-testid={`method-${m.id}`} onClick={() => { setMethod(m.id); setStep("input"); }}
                className="aivora-card aivora-card-hover flex flex-col items-start gap-3 p-5 text-left">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl" style={{ background: "rgba(0,209,255,.14)", color: "#00D1FF" }}><m.icon size={22} /></span>
                <span className="font-bold text-white">{m.title}</span>
                <span className="text-xs text-slate-400">{m.desc}</span>
              </button>
            ))}
          </div>
        </>
      )}

      {step === "input" && (
        <div className="mt-6 space-y-5">
          {needPhoto && (
            <div>
              <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-400">Foto referensi</label>
              <label className="flex cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed border-slate-600 py-8 hover:border-[#00D1FF]" data-testid="photo-upload">
                {photo ? <img src={photo} alt="" className="h-28 w-28 rounded-xl object-cover" /> : <><Upload className="mb-2 text-slate-500" /><span className="text-sm text-slate-400">Klik untuk unggah</span></>}
                <input type="file" accept="image/*" className="hidden" onChange={onFile} />
              </label>
              <button onClick={() => setConsent(!consent)} data-testid="photo-consent" className="mt-3 flex items-center gap-2 text-left text-xs text-slate-300">
                <span className={`flex h-4 w-4 items-center justify-center rounded border ${consent ? "btn-grad border-transparent" : "border-slate-500"}`}>{consent && <Check size={11} />}</span>
                Saya memiliki hak untuk menggunakan foto ini. Foto hanya dipakai sebagai referensi visual.
              </button>
            </div>
          )}
          <div>
            <label className="mb-2 block text-xs font-semibold uppercase tracking-wider text-slate-400">
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
          <p className="text-sm text-slate-400">Tinjau & edit profil sebelum menyimpan.</p>
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
      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-400">{label}</label>
      <input className="input-dark" value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid} />
    </div>
  );
}
function FieldArea({ label, value, onChange, testid }) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-400">{label}</label>
      <textarea className="input-dark min-h-[80px]" value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid} />
    </div>
  );
}
