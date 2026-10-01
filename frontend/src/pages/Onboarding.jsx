import React, { useState } from "react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { Logo } from "../components/Logo";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n";
import { Check } from "lucide-react";

const LANGS = [
  { v: "id", l: "Bahasa Indonesia" }, { v: "en", l: "English" },
  { v: "zh", l: "中文" }, { v: "es", l: "Español" }, { v: "ar", l: "العربية" },
];
const TZ = ["Asia/Jakarta", "Asia/Singapore", "Asia/Tokyo", "Europe/London", "America/New_York"];

export default function Onboarding() {
  const { user, setUser, logout } = useAuth();
  const { t } = useI18n();
  const nav = useNavigate();
  const [name, setName] = useState(user?.name || "");
  const [appLang, setAppLang] = useState("id");
  const [convLang, setConvLang] = useState("id");
  const [tz, setTz] = useState("Asia/Jakarta");
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);

  if (!user) { nav("/"); return null; }

  const finish = async () => {
    if (!agree) { toast.error("Mohon setujui syarat & kebijakan privasi"); return; }
    setBusy(true);
    try {
      const r = await api.post("/auth/onboard", {
        name, app_language: appLang, conversation_language: convLang, timezone: tz,
      });
      setUser(r.data);
      toast.success("Siap! Buat asisten AI pertama Anda");
      nav("/personas/new");
    } catch (e) { toast.error("Gagal menyimpan"); } finally { setBusy(false); }
  };

  return (
    <div className="flex min-h-screen items-center justify-center mesh-bg p-6">
      <div className="w-full max-w-lg fade-up">
        <div className="mb-8 flex justify-center"><Logo size={44} /></div>
        <div className="aivora-card p-8">
          <h1 className="text-2xl font-bold text-slate-900">Mari atur akun Anda</h1>
          <p className="mt-1 text-sm text-slate-500">Beberapa preferensi dasar untuk memulai.</p>

          <div className="mt-6 space-y-5">
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">Nama panggilan</label>
              <input className="input-dark" value={name} onChange={(e) => setName(e.target.value)} data-testid="onboard-name" placeholder="Nama Anda" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">Bahasa Aplikasi</label>
                <select className="input-dark" value={appLang} onChange={(e) => setAppLang(e.target.value)} data-testid="onboard-applang">
                  {LANGS.map((l) => <option key={l.v} value={l.v}>{l.l}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">Bahasa Percakapan</label>
                <select className="input-dark" value={convLang} onChange={(e) => setConvLang(e.target.value)} data-testid="onboard-convlang">
                  {LANGS.map((l) => <option key={l.v} value={l.v}>{l.l}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500">Zona Waktu</label>
              <select className="input-dark" value={tz} onChange={(e) => setTz(e.target.value)} data-testid="onboard-tz">
                {TZ.map((z) => <option key={z} value={z}>{z}</option>)}
              </select>
            </div>
            <button onClick={() => setAgree(!agree)} data-testid="onboard-agree"
              className="flex w-full items-center gap-3 rounded-xl bg-slate-50 px-4 py-3 text-left text-sm text-slate-600">
              <span className={`flex h-5 w-5 items-center justify-center rounded-md border ${agree ? "btn-grad border-transparent" : "border-slate-300"}`}>
                {agree && <Check size={14} />}
              </span>
              Saya menyetujui Syarat Layanan dan Kebijakan Privasi.
            </button>
          </div>

          <button onClick={finish} disabled={busy} className="btn-grad mt-7 w-full rounded-xl py-3.5 text-sm" data-testid="onboard-finish">
            {busy ? "..." : "Mulai menggunakan Oryntix"}
          </button>
          <button onClick={() => { logout(); nav("/"); }} className="mt-3 w-full text-center text-xs text-slate-500">Keluar</button>
        </div>
      </div>
    </div>
  );
}
