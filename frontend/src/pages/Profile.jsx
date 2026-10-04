import React, { useState } from "react";
import { toast } from "sonner";
import { User, Globe, Shield, Sparkles, KeyRound, Lock, Eye, EyeOff } from "lucide-react";
import { NotulenFormatCard } from "../components/NotulenFormatCard";
import { SmartRoutingToggle } from "../components/ModelRoutingCard";
import { api, setAuthToken } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n";

const LANGS = [{ v: "id", l: "Bahasa Indonesia" }, { v: "en", l: "English" }, { v: "zh", l: "中文" }, { v: "es", l: "Español" }, { v: "ar", l: "العربية" }];

function ChangePasswordCard() {
  const [cur, setCur] = useState("");
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const mismatch = confirm.length > 0 && confirm !== pw;
  const submit = async (e) => {
    e.preventDefault();
    if (pw !== confirm) { toast.error("Ulangi password tidak sama"); return; }
    setBusy(true);
    try { const r = await api.post("/auth/change-password", { current_password: cur, new_password: pw }); if (r.data?.access_token) setAuthToken(r.data.access_token); toast.success("Password berhasil diubah"); setCur(""); setPw(""); setConfirm(""); }
    catch (err) { toast.error(err?.response?.data?.detail || "Gagal mengubah password"); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="mt-4 aivora-card p-6" data-testid="change-password-card">
      <p className="flex items-center gap-2 font-semibold text-slate-900"><KeyRound size={16} className="text-[#2F6BFF]" /> Ubah Password</p>
      <p className="mt-1 text-xs text-slate-500">Masukkan password lama untuk verifikasi, lalu password baru (minimal 6 karakter).</p>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <div className="relative"><Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input-dark pl-10" type={show ? "text" : "password"} placeholder="Password lama" value={cur} onChange={(e) => setCur(e.target.value)} required data-testid="pw-current" /></div>
        <div className="relative"><KeyRound size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input-dark pl-10" type={show ? "text" : "password"} placeholder="Password baru" value={pw} onChange={(e) => setPw(e.target.value)} required minLength={6} data-testid="pw-new" /></div>
        <div className="relative"><KeyRound size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className={`input-dark pl-10 ${mismatch ? "border-[#EF4444]" : ""}`} type={show ? "text" : "password"} placeholder="Ulangi password baru" value={confirm} onChange={(e) => setConfirm(e.target.value)} required minLength={6} data-testid="pw-confirm" /></div>
      </div>
      {mismatch && <p className="mt-1.5 text-xs font-medium text-[#EF4444]" data-testid="pw-confirm-error">Password tidak sama.</p>}
      <div className="mt-4 flex items-center gap-3">
        <button className="btn-grad rounded-xl px-5 py-2.5 text-sm disabled:opacity-50" disabled={busy || mismatch} data-testid="pw-submit">{busy ? "..." : "Simpan Password"}</button>
        <button type="button" onClick={() => setShow(!show)} className="flex items-center gap-1.5 text-xs font-semibold text-slate-500" data-testid="pw-toggle-show">{show ? <EyeOff size={14} /> : <Eye size={14} />} {show ? "Sembunyikan" : "Tampilkan"}</button>
      </div>
    </form>
  );
}

const ARCHIVE_OPTS = [[0, "Mati"], [24, "24 jam"], [72, "3 hari"], [168, "7 hari"], [336, "14 hari"]];
function AutoArchiveCard({ user, onSaved }) {
  const cur = user?.settings?.auto_archive_hours ?? 24;
  const [busy, setBusy] = useState(false);
  const set = async (h) => {
    setBusy(true);
    try { const r = await api.put("/auth/settings", { auto_archive_hours: h }); onSaved(r.data); toast.success(h === 0 ? "Arsip otomatis dimatikan" : `Chat diarsipkan setelah ${ARCHIVE_OPTS.find((o) => o[0] === h)[1]} tidak aktif`); }
    catch (e) { toast.error("Gagal menyimpan"); } finally { setBusy(false); }
  };
  return (
    <div className="mt-4 aivora-card p-6" data-testid="auto-archive-card">
      <p className="font-semibold text-slate-900">Arsip Otomatis Percakapan</p>
      <p className="mt-1 text-xs text-slate-500">Chat yang tidak aktif selama jeda ini dirangkum jadi memori asisten dan pesan lamanya dipindah ke Arsip (bisa dicari & dipulihkan). Menghemat token karena asisten hanya membaca rangkuman.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {ARCHIVE_OPTS.map(([h, l]) => <button key={h} onClick={() => set(h)} disabled={busy} data-testid={`auto-archive-${h}`} className={`rounded-full px-3.5 py-1.5 text-xs font-semibold ${cur === h ? "btn-grad" : "border border-[#E7ECF3] bg-white text-slate-600 hover:bg-slate-50"}`}>{l}</button>)}
      </div>
    </div>
  );
}

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

      <ChangePasswordCard />
      <AutoArchiveCard user={user} onSaved={(u2) => setUser(u2)} />
      {user?.role === "admin" && <SmartRoutingToggle user={user} onSaved={() => api.get("/auth/me").then((r) => setUser(r.data)).catch(() => {})} />}
      {user?.role === "admin" && <NotulenFormatCard user={user} onSaved={() => api.get("/auth/me").then((r) => setUser(r.data)).catch(() => {})} />}

      <div className="mt-4 aivora-card p-6 text-sm text-slate-500">
        <p className="font-semibold text-slate-900">Privasi & Data</p>
        <p className="mt-1">Data percakapan & memori Anda hanya digunakan untuk menjalankan layanan. Foto referensi persona hanya dipakai untuk penampilan visual. Anda dapat menghapus persona, memori, dan percakapan kapan saja.</p>
      </div>
    </div>
  );
}
