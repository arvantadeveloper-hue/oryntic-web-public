import React, { useState } from "react";
import { Volume2, VolumeX, BellOff } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Switch } from "./ui/switch";

export const isMuted = (user) => !!user?.settings?.mute_sounds;

export function useMuteSounds() {
  const { user, setUser } = useAuth();
  const [busy, setBusy] = useState(false);
  const muted = isMuted(user);
  const set = async (v) => {
    setBusy(true);
    try { const r = await api.put("/auth/settings", { mute_sounds: v }); setUser(r.data); toast.success(v ? "Semua bunyi disenyapkan" : "Bunyi diaktifkan kembali"); }
    catch (e) { toast.error("Gagal menyimpan setelan bunyi"); } finally { setBusy(false); }
  };
  return { muted, busy, set, toggle: () => set(!muted) };
}

// Header quick toggle.
export function SoundToggleButton() {
  const { muted, busy, toggle } = useMuteSounds();
  return (
    <button onClick={toggle} disabled={busy} data-testid="sound-toggle-btn" aria-pressed={muted} title={muted ? "Bunyi disenyapkan — klik untuk mengaktifkan" : "Senyapkan semua bunyi (dering, getar, suara pengingat)"}
      className={`flex h-10 w-10 items-center justify-center rounded-full transition disabled:opacity-50 ${muted ? "bg-amber-50 text-amber-600 hover:bg-amber-100" : "text-slate-500 hover:bg-slate-100"}`}>
      {muted ? <VolumeX size={19} /> : <Volume2 size={19} />}
    </button>
  );
}

// Settings page card.
export function SoundSettingsCard() {
  const { muted, busy, set } = useMuteSounds();
  return (
    <div className="mt-4 aivora-card p-6" data-testid="sound-settings-card">
      <div className="flex items-start gap-4">
        <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${muted ? "bg-amber-50 text-amber-600" : "bg-[#EEF3FF] text-[#2F6BFF]"}`}>{muted ? <BellOff size={18} /> : <Volume2 size={18} />}</span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-slate-900">Senyapkan Semua Bunyi</p>
          <p className="mt-1 text-xs text-slate-500">Mematikan nada dering & getar panggilan masuk dari teman, pembacaan suara saat asisten mengingatkan lewat panggilan, dan bunyi notifikasi push di perangkat. Panggilan dan pengingat tetap muncul secara visual dan bisa diangkat seperti biasa.</p>
          <p className="mt-2 text-[11px] font-semibold text-slate-400">Juga tersedia sebagai ikon speaker di bar atas.</p>
        </div>
        <Switch checked={muted} disabled={busy} onCheckedChange={set} data-testid="sound-mute-switch" />
      </div>
    </div>
  );
}
