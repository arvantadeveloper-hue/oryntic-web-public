import React, { useEffect, useState } from "react";
import { Bell, BellOff, Loader2, Send } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { enablePush, disablePush, pushEnabledHere, pushSupported } from "../lib/firebase";

const KINDS = [["reminders", "Pengingat jatuh tempo"], ["calls", "Panggilan masuk dari teman"], ["messages", "Pesan baru (saat tab tidak aktif)"], ["tasks", "Tugas Ruang Kerja selesai"]];

// Settings → Notifikasi: enable web push on this device + choose which events may notify you.
export function PushSettingsCard() {
  const [st, setSt] = useState(null);
  const [supported, setSupported] = useState(false);
  const [busy, setBusy] = useState(false);
  const [here, setHere] = useState(pushEnabledHere());
  const load = () => api.get("/push/status").then((r) => setSt(r.data)).catch(() => setSt({ configured: false, devices: 0, prefs: {} }));
  useEffect(() => { load(); pushSupported().then(setSupported).catch(() => setSupported(false)); }, []);
  const toggle = async () => {
    setBusy(true);
    try {
      if (here) { await disablePush(); setHere(false); toast.success("Notifikasi push dimatikan di perangkat ini"); }
      else { await enablePush(); setHere(true); toast.success("Notifikasi push aktif di perangkat ini"); }
      load();
    } catch (e) { toast.error(e?.message || "Gagal mengubah notifikasi"); } finally { setBusy(false); }
  };
  const setPref = async (k, v) => {
    const prefs = { ...st.prefs, [k]: v }; setSt({ ...st, prefs });
    try { await api.put("/push/prefs", prefs); } catch (e) { toast.error("Gagal menyimpan preferensi"); }
  };
  const test = async () => { try { const r = await api.post("/push/test"); toast[r.data.sent ? "success" : "error"](r.data.sent ? `Notifikasi uji terkirim ke ${r.data.sent} perangkat` : "Tidak ada perangkat terdaftar"); } catch (e) { toast.error("Gagal mengirim uji"); } };
  if (!st) return null;
  return (
    <div className="mt-4 aivora-card p-6" data-testid="push-settings-card">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="flex items-center gap-2 text-base font-bold text-slate-900 md:text-lg"><Bell size={18} className="text-[#2F6BFF]" /> Notifikasi Push</h3>
          <p className="mt-1 text-sm text-slate-500">Dapatkan pemberitahuan di perangkat ini walau tab Oryntix tertutup — pengingat, panggilan masuk, pesan baru, dan tugas selesai. Saat aplikasi terbuka, semuanya tetap tersinkron langsung tanpa notifikasi ganda.</p>
          {!st.configured && <p className="mt-2 text-xs text-amber-600" data-testid="push-not-configured">Push belum dikonfigurasi admin platform (FCM).</p>}
          {st.configured && !supported && <p className="mt-2 text-xs text-amber-600" data-testid="push-unsupported">Browser ini tidak mendukung notifikasi push (coba Chrome/Edge/Firefox, atau tambahkan Oryntix ke layar utama di iOS).</p>}
          <p className="mt-2 text-xs text-slate-400" data-testid="push-devices">{st.devices} perangkat terdaftar</p>
        </div>
        <button onClick={toggle} disabled={busy || !st.configured || !supported} data-testid="push-toggle" className={`flex shrink-0 items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold disabled:opacity-50 ${here ? "border border-[#E7ECF3] text-slate-700 hover:bg-slate-50" : "btn-grad"}`}>
          {busy ? <Loader2 size={15} className="animate-spin" /> : here ? <BellOff size={15} /> : <Bell size={15} />} {here ? "Matikan di perangkat ini" : "Aktifkan di perangkat ini"}
        </button>
      </div>
      <div className="mt-5 grid gap-2 sm:grid-cols-2">
        {KINDS.map(([k, label]) => (
          <label key={k} className="flex items-center gap-3 rounded-xl border border-[#E7ECF3] px-3 py-2.5 text-sm text-slate-700">
            <input type="checkbox" checked={st.prefs?.[k] !== false} onChange={(e) => setPref(k, e.target.checked)} data-testid={`push-pref-${k}`} className="h-4 w-4 accent-[#2F6BFF]" /> {label}
          </label>
        ))}
      </div>
      {here && <button onClick={test} className="mt-4 flex items-center gap-1.5 text-xs font-semibold text-[#2F6BFF] hover:underline" data-testid="push-test"><Send size={12} /> Kirim notifikasi uji</button>}
    </div>
  );
}
