import React, { useEffect, useRef, useState } from "react";
import { Video, Loader2, Coins, Clock, X, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { AvatarBridge } from "../lib/avatarVideo";

// Confirmation shown before starting the interactive video with Oryntix: per-second credits + duration cap set by the platform admin.
export function VideoConfirmModal({ cfg, onConfirm, onClose }) {
  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/70 p-4" data-testid="video-confirm-modal">
      <div className="w-full max-w-md rounded-2xl border border-white/10 bg-[#0f1733] p-6 text-white shadow-2xl">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#2F6BFF]/20 text-[#8FB0FF]"><Video size={20} /></span>
          <div className="min-w-0 flex-1">
            <h3 className="text-lg font-bold">Aktifkan video interaktif?</h3>
            <p className="mt-1 text-sm text-white/70">Oryntix akan tampil sebagai avatar video realtime yang bicara mengikuti suaranya. Panggilan suara tetap berjalan seperti biasa.</p>
          </div>
          <button onClick={onClose} className="rounded-lg p-1 text-white/60 hover:bg-white/10" data-testid="video-confirm-close"><X size={16} /></button>
        </div>
        <div className="mt-4 grid gap-2 rounded-xl bg-white/5 p-4 text-sm">
          <p className="flex items-center gap-2" data-testid="video-price"><Coins size={14} className="text-amber-300" /> Biaya video: <b>{cfg.credits_per_sec} kredit/detik</b> <span className="text-white/50">(±{cfg.credits_per_sec * 60} kredit/menit)</span></p>
          <p className="flex items-center gap-2" data-testid="video-limit"><Clock size={14} className="text-[#8FB0FF]" /> Durasi maksimal video: <b>{cfg.max_minutes} menit</b> <span className="text-white/50">(maks ±{cfg.max_cost} kredit)</span></p>
          <p className="flex items-start gap-2 text-white/60"><ShieldAlert size={14} className="mt-0.5 shrink-0" /> Biaya ini di luar tarif panggilan suara per menit. Video bisa dimatikan kapan saja; tagihan dihitung per detik yang berjalan.{cfg.sandbox ? " Mode uji coba (sandbox): sesi dibatasi ±1 menit." : ""}</p>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-xl bg-white/10 px-4 py-2 text-sm font-semibold hover:bg-white/15" data-testid="video-confirm-cancel">Batal</button>
          <button onClick={onConfirm} className="rounded-xl bg-[#2F6BFF] px-4 py-2 text-sm font-bold hover:brightness-110" data-testid="video-confirm-ok">Setuju & mulai video</button>
        </div>
      </div>
    </div>
  );
}

const WARN_TEXT = (mins) => `[System notice — do NOT interrupt the user: wait until they have clearly finished their current turn. Then, at your next natural turn, first apologise warmly for a system limitation, mention in one friendly natural sentence that the video session can only last about ${mins} minutes in total so the video will switch off in roughly two minutes while the voice call simply continues, and then carry on helping with whatever you were discussing. Say this only once.]`;
const END_TEXT = "[System notice: the video avatar has just been switched off because the video time limit was reached. The voice call continues normally. At your next natural turn, mention this briefly and kindly in one sentence and keep helping — do not interrupt the user.]";

// Lifecycle of the LiveAvatar video inside a Realtime call: start/stop sessions, per-15s billing ticks, cap warning, graceful limit end.
export function useAvatarVideo({ callIdRef, remoteStreamRef, audioElRef, inject, phaseRef, enabled }) {
  const [cfg, setCfg] = useState(null);
  const [state, setState] = useState("off"); // off|confirm|starting|on|ending
  const [track, setTrack] = useState(null);
  const [remaining, setRemaining] = useState(null);
  const [credits, setCredits] = useState(0);
  const bridgeRef = useRef(null);
  const startedRef = useRef(null);
  const tickRef = useRef(null);
  const warnedRef = useRef(false);
  const sessRef = useRef(null);
  const audioSinkRef = useRef(null);
  useEffect(() => { if (enabled) api.get("/support/video-config").then((r) => setCfg(r.data)).catch(() => {}); }, [enabled]);

  const elapsed = () => (startedRef.current ? Math.round((Date.now() - startedRef.current) / 1000) : 0);

  const stop = async (reason = "user") => {
    if (!bridgeRef.current && !sessRef.current) return;
    setState("ending");
    if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
    const secs = elapsed();
    bridgeRef.current?.stop(); bridgeRef.current = null;
    try { audioSinkRef.current?.remove(); } catch (e) {} audioSinkRef.current = null;
    if (audioElRef.current) audioElRef.current.muted = false;
    setTrack(null); setRemaining(null); startedRef.current = null;
    if (sessRef.current && callIdRef.current && reason !== "server") {
      try { const r = await api.post(`/realtime/calls/${callIdRef.current}/video/stop`, { elapsed_seconds: secs }); setCredits(r.data.credits || 0); } catch (e) {}
    }
    sessRef.current = null;
    setState("off");
    if (reason === "limit") { inject(END_TEXT); toast("Batas waktu video tercapai — panggilan suara tetap berlanjut"); }
    else if (reason === "credits") toast.error("Kredit tidak cukup untuk melanjutkan video");
  };

  const start = async () => {
    if (!callIdRef.current) return;
    setState("starting");
    try {
      const r = await api.post(`/realtime/calls/${callIdRef.current}/video/start`);
      sessRef.current = r.data; warnedRef.current = false;
      const bridge = new AvatarBridge({
        onError: (m) => { toast.error(m); },
        onState: () => {},
        onVideoTrack: (t) => setTrack(t),
        onAudioTrack: (t) => { const el = t.attach(); el.autoplay = true; document.body.appendChild(el); audioSinkRef.current = el; if (audioElRef.current) audioElRef.current.muted = true; },
      });
      bridgeRef.current = bridge;
      await bridge.start(r.data, remoteStreamRef.current);
      startedRef.current = Date.now(); setRemaining(r.data.max_seconds); setState("on");
      if (phaseRef.current === "speaking") bridge.speakStart();
      tickRef.current = setInterval(async () => {
        const s = elapsed(); const rem = (sessRef.current?.max_seconds || 0) - s; setRemaining(Math.max(0, rem));
        if (!warnedRef.current && s >= (sessRef.current?.warn_seconds || Infinity)) { warnedRef.current = true; inject(WARN_TEXT(cfg?.max_minutes || Math.round((sessRef.current?.max_seconds || 1200) / 60))); }
        if (s % 15 === 0 || rem <= 0) {
          try {
            const t = await api.post(`/realtime/calls/${callIdRef.current}/video/tick`, { elapsed_seconds: s });
            setCredits(t.data.credits || 0);
            if (t.data.ended) { sessRef.current = null; stop(t.data.reason === "limit" ? "limit" : "credits"); }
          } catch (e) { if (e?.response?.status === 404) { sessRef.current = null; stop("server"); } }
        }
      }, 1000);
    } catch (e) {
      bridgeRef.current?.stop(); bridgeRef.current = null; sessRef.current = null; setState("off");
      toast.error(e?.response?.data?.detail || e?.message || "Gagal memulai video");
    }
  };

  // hooks called from the Realtime event stream
  const onAssistantAudioStart = () => bridgeRef.current?.speakStart();
  const onAssistantAudioStop = () => bridgeRef.current?.speakEnd();
  const onInterrupt = () => bridgeRef.current?.interrupt();
  const onUserSpeaking = (on) => bridgeRef.current?.listening(on);
  const attachStream = (stream) => bridgeRef.current?.attachAudio(stream);

  return { cfg, state, track, remaining, credits, start, stop, setState, onAssistantAudioStart, onAssistantAudioStop, onInterrupt, onUserSpeaking, attachStream };
}

export function AvatarVideoView({ track, remaining, credits, name, onStop, state }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!track || !el) return undefined;
    try { track.attach(el); } catch (e) {}
    if (!el.srcObject && track.mediaStreamTrack) el.srcObject = new MediaStream([track.mediaStreamTrack]);
    el.play?.().catch(() => {});
    const guard = setInterval(() => { // LiveKit re-subscriptions reuse the track object and clear srcObject → re-attach
      if (!el.srcObject && track.mediaStreamTrack && track.mediaStreamTrack.readyState === "live") { el.srcObject = new MediaStream([track.mediaStreamTrack]); el.play?.().catch(() => {}); }
    }, 700);
    return () => { clearInterval(guard); try { track.detach(el); } catch (e) {} };
  }, [track]);
  const mm = String(Math.floor((remaining || 0) / 60)).padStart(2, "0"), ss = String((remaining || 0) % 60).padStart(2, "0");
  return (
    <div className="relative flex h-full w-full items-center justify-center overflow-hidden rounded-2xl border border-white/10 bg-black" data-testid="rt-avatar-video">
      <video ref={ref} autoPlay playsInline muted className="h-full w-full object-cover" />
      {!track && <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-white/70"><Loader2 size={22} className="animate-spin" /> <span className="text-xs">{state === "starting" ? "Menyiapkan avatar video…" : "Menunggu video…"}</span></div>}
      <span className="absolute left-3 top-3 flex items-center gap-1.5 rounded-full bg-black/60 px-2.5 py-1 text-[11px] font-bold text-white backdrop-blur"><Video size={12} className="text-[#8FB0FF]" /> {name} · video</span>
      <span className={`absolute right-3 top-3 rounded-full px-2.5 py-1 font-mono text-[11px] font-bold backdrop-blur ${(remaining || 0) <= 120 ? "bg-amber-500/80 text-black" : "bg-black/60 text-white"}`} data-testid="rt-video-remaining" title="Sisa waktu video">{mm}:{ss}</span>
      <span className="absolute bottom-3 left-3 flex items-center gap-1 rounded-full bg-black/60 px-2.5 py-1 text-[11px] text-white/80 backdrop-blur" data-testid="rt-video-credits"><Coins size={11} /> {credits} kredit</span>
      <button onClick={onStop} className="absolute bottom-3 right-3 rounded-full bg-white/15 px-3 py-1.5 text-[11px] font-bold text-white backdrop-blur hover:bg-[#EF4444]" data-testid="rt-video-stop">Matikan video</button>
    </div>
  );
}
