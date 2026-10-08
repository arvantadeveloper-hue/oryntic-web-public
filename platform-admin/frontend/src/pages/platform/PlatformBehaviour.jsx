import React, { useEffect, useState } from "react";
import { Loader2, Save, AudioWaveform } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../lib/api";

const SEL = "input-dark w-full py-2 text-sm";
const Row = ({ label, hint, children }) => (
  <label className="block"><span className="mb-1 block text-xs font-semibold text-slate-700">{label}</span>{children}{hint && <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>}</label>
);

// Platform-wide Conversation Behaviour for Realtime calls (turn-taking, barge-in, backchannel). Default: semantic_vad + eagerness=low.
export default function PlatformBehaviour() {
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.get("/admin/realtime-behaviour").then((r) => setF(r.data)).catch(() => toast.error("Gagal memuat")); }, []);
  if (!f) return <p className="flex items-center gap-2 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p>;
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.type === "number" ? parseFloat(e.target.value) || 0 : e.target.value });
  const save = async () => {
    setBusy(true);
    try { const r = await api.put("/admin/realtime-behaviour", f); setF(r.data); toast.success("Conversation Behaviour disimpan — berlaku untuk panggilan berikutnya"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan"); } finally { setBusy(false); }
  };
  const semantic = f.turn_detection === "semantic_vad";
  return (
    <div data-testid="platform-behaviour">
      <h1 className="text-2xl font-black text-slate-900">Conversation Behaviour</h1>
      <p className="mt-1 text-sm text-slate-500">Cara asisten bergiliran bicara di panggilan Realtime (semua persona, semua pengguna). Default: deteksi giliran <b>semantic</b> dengan eagerness <b>low</b>.</p>
      <div className="mt-5 aivora-card p-5">
        <div className="flex items-center gap-2"><span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#2F6BFF]/10 text-[#2F6BFF]"><AudioWaveform size={18} /></span><p className="text-sm font-bold text-slate-900">Deteksi giliran (OpenAI turn_detection)</p></div>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <Row label="Turn detection" hint="semantic_vad: model menilai apakah pengguna sudah selesai bicara. server_vad: berdasarkan keheningan.">
            <select value={f.turn_detection} onChange={set("turn_detection")} data-testid="beh-turn-detection" className={SEL}><option value="semantic_vad">semantic_vad (disarankan)</option><option value="server_vad">server_vad</option></select></Row>
          {semantic && <Row label="Eagerness" hint="low = sabar menunggu pengguna selesai (default); high = cepat merespons.">
            <select value={f.eagerness} onChange={set("eagerness")} data-testid="beh-eagerness" className={SEL}><option value="low">low (default)</option><option value="medium">medium</option><option value="high">high</option><option value="auto">auto</option></select></Row>}
          {!semantic && <>
            <Row label="Threshold (0–1)"><input type="number" step="0.05" min="0" max="1" value={f.threshold} onChange={set("threshold")} data-testid="beh-threshold" className={SEL} /></Row>
            <Row label="Prefix padding (ms)"><input type="number" step="50" value={f.prefix_padding_ms} onChange={set("prefix_padding_ms")} data-testid="beh-prefix" className={SEL} /></Row>
            <Row label="Silence duration (ms)" hint="Hening selama ini dianggap selesai bicara."><input type="number" step="50" value={f.silence_duration_ms} onChange={set("silence_duration_ms")} data-testid="beh-silence" className={SEL} /></Row>
          </>}
          <Row label="Interrupt response (server)" hint="Mati = pemutusan dikendalikan aplikasi lewat ambang barge-in di bawah (disarankan).">
            <label className="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={!!f.interrupt_response} onChange={set("interrupt_response")} data-testid="beh-interrupt" /> Server langsung memotong saat pengguna bersuara</label></Row>
        </div>
      </div>
      <div className="mt-4 aivora-card p-5">
        <p className="text-sm font-bold text-slate-900">Barge-in & backchannel (sisi aplikasi)</p>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <Row label="Ambang barge-in (ms)" hint="Suara pengguna harus berlangsung selama ini sebelum asisten dipotong. 'hmm/iya' singkat tetap di bawah ambang."><input type="number" step="100" min="200" max="5000" value={f.barge_confirm_ms} onChange={set("barge_confirm_ms")} data-testid="beh-barge" className={SEL} /></Row>
          <Row label="Lanjutkan setelah backchannel" hint="Transkrip 'hmm/iya/oke' tepat setelah terpotong → asisten melanjutkan dari titik berhenti."><label className="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={!!f.backchannel_resume} onChange={set("backchannel_resume")} data-testid="beh-backchannel" /> Aktif</label></Row>
          <Row label="Jendela backchannel (ms)"><input type="number" step="500" min="1000" max="30000" value={f.backchannel_window_ms} onChange={set("backchannel_window_ms")} data-testid="beh-window" className={SEL} /></Row>
        </div>
      </div>
      <div className="mt-4 flex justify-end"><button onClick={save} disabled={busy} data-testid="beh-save" className="btn-primary py-2">{busy ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Simpan</button></div>
    </div>
  );
}
