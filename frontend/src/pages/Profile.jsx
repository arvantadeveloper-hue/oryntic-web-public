import { NotulenFormatCard } from "../components/NotulenFormatCard";
import React, { useState } from "react";
import { toast } from "sonner";
import { User, Globe, Shield, Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n";

const LANGS = [{ v: "id", l: "Bahasa Indonesia" }, { v: "en", l: "English" }, { v: "zh", l: "中文" }, { v: "es", l: "Español" }, { v: "ar", l: "العربية" }];

export default function Profile() {
  const { user, setUser } = useAuth();
  const { t, setLang } = useI18n();
  const s = user?.settings || {};
  const [name, setName] = useState(user?.name || "");
  const [appLang, setAppLang] = useState(s.app_language || "id");
  const [convLang, setConvLang] = useState(s.conversation_language || "id");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      const r = await api.post("/auth/onboard", { name, app_language: appLang, conversation_language: convLang, timezone: s.timezone || "Asia/Jakarta" });
      setUser(r.data); setLang(appLang); toast.success("Tersimpan");
    } catch (e) { toast.error("Gagal"); } finally { setBusy(false); }
  };

  return (
    <div className="mx-auto max-w-2xl p-5 sm:p-8 lg:p-10 fade-up" data-testid="profile-page">
      <h1 className="text-3xl font-extrabold text-slate-900">{t("nav.profile")}</h1>

      <div className="mt-6 aivora-card p-6">
        <div className="flex items-center gap-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-full text-2xl font-bold text-[#06111f]" style={{ background: "linear-gradient(135deg,#00D1FF,#7C3AED)" }}>{(user?.name || "U")[0].toUpperCase()}</div>
          <div>
            <p className="text-lg font-bold text-slate-900">{user?.name}</p>
            <p className="text-sm text-slate-500">{user?.email}</p>
            {user?.role === "admin" && <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-[#7C3AED]/20 px-2 py-0.5 text-xs text-[#a78bfa]"><Shield size={11} /> Admin</span>}
          </div>
          <div className="ml-auto flex items-center gap-1.5 rounded-full border border-[rgba(0,209,255,.25)] bg-slate-50 px-3 py-1.5 text-sm"><Sparkles size={14} className="text-[#2F6BFF]" /> <span className="font-semibold text-slate-900">{user?.credits}</span></div>
        </div>

        <div className="mt-6 space-y-4">
          <div>
            <label className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500"><User size={13} /> Nama</label>
            <input className="input-dark" value={name} onChange={(e) => setName(e.target.value)} data-testid="profile-name" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500"><Globe size={13} /> Bahasa Aplikasi</label>
              <select className="input-dark" value={appLang} onChange={(e) => setAppLang(e.target.value)} data-testid="profile-applang">{LANGS.map((l) => <option key={l.v} value={l.v}>{l.l}</option>)}</select>
            </div>
            <div>
              <label className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500"><Globe size={13} /> Bahasa Percakapan</label>
              <select className="input-dark" value={convLang} onChange={(e) => setConvLang(e.target.value)} data-testid="profile-convlang">{LANGS.map((l) => <option key={l.v} value={l.v}>{l.l}</option>)}</select>
            </div>
          </div>
          <button onClick={save} disabled={busy} className="btn-grad rounded-xl px-6 py-3 text-sm" data-testid="profile-save">{busy ? "..." : t("common.save")}</button>
        </div>
      </div>

      {user?.role === "admin" && <NotulenFormatCard user={user} onSaved={() => api.get("/auth/me").then((r) => setUser(r.data)).catch(() => {})} />}

      <div className="mt-4 aivora-card p-6 text-sm text-slate-500">
        <p className="font-semibold text-slate-900">Privasi & Data</p>
        <p className="mt-1">Data percakapan & memori Anda hanya digunakan untuk menjalankan layanan. Foto referensi persona hanya dipakai untuk penampilan visual. Anda dapat menghapus persona, memori, dan percakapan kapan saja.</p>
      </div>
    </div>
  );
}
