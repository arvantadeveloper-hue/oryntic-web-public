import React, { useEffect, useRef, useState } from "react";
import { Video, Loader2, Coins, Clock, X, ShieldAlert, RefreshCw } from "lucide-react";
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
          <p className="flex items-center gap-2" data-testid="video-avatar-name"><Video size={14} className="text-[#8FB0FF]" /> Avatar: <b>{cfg.avatar_name || "—"}</b></p>
          <p className="flex items-start gap-2 text-white/60"><ShieldAlert size={14} className="mt-0.5 shrink-0" /> Biaya ini di luar tarif panggilan suara per menit. Video bisa dimatikan kapan saja; tagihan dihitung per detik yang berjalan.</p>
          {cfg.sandbox && (
            <p className="flex items-start gap-2 rounded-lg bg-amber-400/10 p-2.5 text-amber-200" data-testid="video-sandbox-warning">
              <ShieldAlert size={14} className="mt-0.5 shrink-0" /> <span>Mode uji coba (sandbox) aktif: yang tampil adalah <b>avatar sandbox LiveAvatar</b>{cfg.configured_avatar_name ? <>, bukan avatar pilihan Anda (<b>{cfg.configured_avatar_name}</b>)</> : null}, dan sesi dibatasi ±1 menit. Matikan Sandbox di Admin Platform untuk memakai avatar pilihan Anda.</span>
            </p>
          )}
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

// Lifecycle of the LiveAvatar video inside a Realtime call: start/stop sessions, per-15s billing ticks, cap warning, graceful limit end,
// and "Sambung ulang" after a drop (a new LiveAvatar session that only gets the leftover time of the one that broke).
export function useAvatarVideo({ callIdRef, remoteStreamRef, audioElRef, inject, phaseRef, enabled }) {
  const [cfg, setCfg] = useState(null);
  const [state, setState] = useState("off"); // off|confirm|starting|on|ending
  const [track, setTrack] = useState(null);
  const [remaining, setRemaining] = useState(null);
  const [credits, setCredits] = useState(0);
  const [resumable, setResumable] = useState(null); // {remaining, credits} after a disconnect → user may continue the leftover time
  const bridgeRef = useRef(null);
  const startedRef = useRef(null);      // wall-clock start of the current CONNECTED stretch (null while disconnected)
  const connectedMsRef = useRef(0);     // connected time accumulated before the current stretch — the limit counts only connected seconds
  const [link, setLink] = useState("connected"); // connected | reconnecting | disconnected
  const tickRef = useRef(null);
  const warnedRef = useRef(false);
  const sessRef = useRef(null);
  const audioSinkRef = useRef(null);
  const baseCreditsRef = useRef(0);     // credits of earlier sessions in this call (resume chain) — shown cumulatively
  useEffect(() => { if (enabled) api.get("/support/video-config").then((r) => setCfg(r.data)).catch(() => {}); }, [enabled]);
  useEffect(() => () => { bridgeRef.current?.endSession(); bridgeRef.current = null; try { audioSinkRef.current?.remove(); } catch (e) {} }, []); // unmount: never leave a LiveAvatar session open

  const elapsed = () => Math.round((connectedMsRef.current + (startedRef.current ? Date.now() - startedRef.current : 0)) / 1000);
  const pauseClock = () => { if (startedRef.current) { connectedMsRef.current += Date.now() - startedRef.current; startedRef.current = null; } };
  const resumeClock = () => { if (!startedRef.current) startedRef.current = Date.now(); };
  const total = (sessionCredits) => Math.round((baseCreditsRef.current + (sessionCredits || 0)) * 100) / 100;

  const releaseMedia = () => { // tear down the LiveAvatar session + every local sink so the old stream can never linger
    bridgeRef.current?.endSession(); bridgeRef.current = null;
    try { audioSinkRef.current?.remove(); } catch (e) {} audioSinkRef.current = null;
    if (audioElRef.current) audioElRef.current.muted = false;
    setTrack(null);
  };

  const stop = async (reason = "user") => {
    if (!bridgeRef.current && !sessRef.current) return;
    setState("ending");
    if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
    const secs = elapsed();
    releaseMedia();
    setRemaining(null); pauseClock(); startedRef.current = null; connectedMsRef.current = 0; setLink("connected");
    let res = null;
    if (sessRef.current && callIdRef.current && reason !== "server") {
      try { const r = await api.post(`/realtime/calls/${callIdRef.current}/video/stop`, { elapsed_seconds: secs, reason: reason === "disconnected" ? "DISCONNECTED" : "USER_CLOSED" }); res = r.data; setCredits(total(res.credits)); } catch (e) {}
    }
    sessRef.current = null;
    setState("off");
    if (reason === "limit") { inject(END_TEXT); toast("Batas waktu video tercapai — panggilan suara tetap berlanjut"); }
    if (reason === "disconnected") {
      if (res?.resumable) { setResumable({ remaining: res.remaining, credits: total(res.credits) }); toast.error("Koneksi video terputus — hitung mundur dijeda. Tekan \"Sambung ulang\" untuk melanjutkan sisa waktu."); }
      else toast.error("Koneksi video terputus — hanya waktu tersambung yang dihitung.");
    } else if (reason === "credits") toast.error("Kredit tidak cukup untuk melanjutkan video");
  };

  const start = async ({ resume = false } = {}) => {
    if (!callIdRef.current) return;
    setState("starting"); setResumable(null);
    try {
      const r = await api.post(`/realtime/calls/${callIdRef.current}/video/start`, { resume });
      sessRef.current = r.data;
      if (!resume) warnedRef.current = false; // a resumed session keeps the "two minutes left" notice from before
      baseCreditsRef.current = resume ? Number(r.data.prior_credits || 0) : 0; setCredits(total(0));
      const bridge = new AvatarBridge({
        onError: (m) => { if (!bridge.closed) toast.error(m); },
        onState: () => {},
        onConnection: (st) => { // the clock only runs while the LiveKit room is connected
          if (st === "connected") { resumeClock(); setLink("connected"); }
          else if (st === "reconnecting") { pauseClock(); setLink("reconnecting"); }
          else if (st === "disconnected" && sessRef.current) { pauseClock(); setLink("disconnected"); stop(elapsed() >= (sessRef.current?.max_seconds || 0) - 5 ? "limit" : "disconnected"); }
        },
        onVideoTrack: (t) => setTrack(t),
        onAudioTrack: (t) => { const el = t.attach(); el.autoplay = true; document.body.appendChild(el); audioSinkRef.current = el; if (audioElRef.current) audioElRef.current.muted = true; },
      });
      bridgeRef.current = bridge;
      connectedMsRef.current = 0; startedRef.current = null;
      await bridge.start(r.data, remoteStreamRef.current);
      resumeClock(); setRemaining(r.data.max_seconds); setState("on");
      if (resume) toast.success("Video tersambung kembali — melanjutkan sisa waktu");
      if (phaseRef.current === "speaking") bridge.speakStart();
      tickRef.current = setInterval(async () => {
        const s = elapsed(); const rem = (sessRef.current?.max_seconds || 0) - s; setRemaining(Math.max(0, rem));
        if (!warnedRef.current && s >= (sessRef.current?.warn_seconds || Infinity)) { warnedRef.current = true; inject(WARN_TEXT(cfg?.max_minutes || Math.round((sessRef.current?.max_seconds || 1200) / 60))); }
        if (!startedRef.current) return; // paused (reconnecting): no countdown, no billing tick
        if (s % 15 === 0 || rem <= 0) {
          try {
            const t = await api.post(`/realtime/calls/${callIdRef.current}/video/tick`, { elapsed_seconds: s });
            setCredits(total(t.data.credits));
            if (t.data.ended) { sessRef.current = null; stop(t.data.reason === "limit" ? "limit" : "credits"); }
          } catch (e) { if (e?.response?.status === 404) { sessRef.current = null; stop("server"); } }
        }
      }, 1000);
    } catch (e) {
      releaseMedia(); sessRef.current = null; setState("off");
      toast.error(e?.response?.data?.detail || e?.message || "Gagal memulai video");
    }
  };

  // hooks called from the Realtime event stream
  const onAssistantAudioStart = () => bridgeRef.current?.speakStart();
  const onAssistantAudioStop = () => bridgeRef.current?.speakEnd();
  const onInterrupt = () => bridgeRef.current?.interrupt();
  const onUserSpeaking = (on) => bridgeRef.current?.listening(on);
  const attachStream = (stream) => bridgeRef.current?.attachAudio(stream);

  return { cfg, state, link, track, remaining, credits, resumable, start, resume: () => start({ resume: true }), dismissResume: () => setResumable(null), stop, setState, onAssistantAudioStart, onAssistantAudioStop, onInterrupt, onUserSpeaking, attachStream };
}

const mmss = (s) => `${String(Math.floor((s || 0) / 60)).padStart(2, "0")}:${String((s || 0) % 60).padStart(2, "0")}`;

// Shown in place of the video after a drop: continue the leftover time with one tap (no new confirmation — same price, same cap).
export function VideoResumeBar({ resumable, state, onResume, onDismiss }) {
  if (!resumable) return null;
  const busy = state === "starting";
  return (
    <div className="mx-auto mt-3 flex w-full max-w-md flex-wrap items-center gap-3 rounded-2xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100" data-testid="rt-video-resume">
      <RefreshCw size={16} className={`shrink-0 text-amber-300 ${busy ? "animate-spin" : ""}`} />
      <div className="min-w-0 flex-1">
        <p className="font-semibold">Video terputus — sisa waktu <span className="font-mono" data-testid="rt-video-resume-remaining">{mmss(resumable.remaining)}</span></p>
        <p className="text-xs text-amber-100/70">Hitung mundur dijeda. Sambung ulang untuk melanjutkan tanpa menyalakan dari awal.</p>
      </div>
      <button onClick={onResume} disabled={busy} className="rounded-xl bg-[#2F6BFF] px-3 py-1.5 text-xs font-bold text-white hover:brightness-110 disabled:opacity-50" data-testid="rt-video-resume-btn">{busy ? "Menyambung…" : "Sambung ulang"}</button>
      <button onClick={onDismiss} disabled={busy} className="rounded-xl bg-white/10 px-3 py-1.5 text-xs font-semibold text-white hover:bg-white/15 disabled:opacity-50" data-testid="rt-video-resume-dismiss">Tutup</button>
    </div>
  );
}

export function AvatarVideoView({ track, remaining, credits, name, onStop, state, link = "connected" }) {
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
  const mm = remaining == null ? "--" : String(Math.floor(remaining / 60)).padStart(2, "0"), ss = remaining == null ? "--" : String(remaining % 60).padStart(2, "0");
  return (
    <div className="relative flex h-full w-full items-center justify-center overflow-hidden rounded-2xl border border-white/10 bg-black" data-testid="rt-avatar-video">
      <video ref={ref} autoPlay playsInline muted className="h-full w-full object-cover" />
      {!track && <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-white/70"><Loader2 size={22} className="animate-spin" /> <span className="text-xs">{state === "starting" ? "Menyiapkan avatar video…" : "Menunggu video…"}</span></div>}
      <span className="absolute left-3 top-3 flex items-center gap-1.5 rounded-full bg-black/60 px-2.5 py-1 text-[11px] font-bold text-white backdrop-blur"><Video size={12} className="text-[#8FB0FF]" /> {name} · video</span>
      {link !== "connected" && <span className="absolute inset-x-0 top-12 mx-auto w-max rounded-full bg-amber-500/90 px-3 py-1 text-[11px] font-bold text-black" data-testid="rt-video-link">Koneksi video terputus — menyambung ulang… (hitung mundur dijeda)</span>}
      <span className={`absolute right-3 top-3 rounded-full px-2.5 py-1 font-mono text-[11px] font-bold backdrop-blur ${(remaining || 0) <= 120 ? "bg-amber-500/80 text-black" : "bg-black/60 text-white"}`} data-testid="rt-video-remaining" title="Sisa waktu video">{mm}:{ss}</span>
      <span className="absolute bottom-3 left-3 flex items-center gap-1 rounded-full bg-black/60 px-2.5 py-1 text-[11px] text-white/80 backdrop-blur" data-testid="rt-video-credits"><Coins size={11} /> {Math.round(credits || 0)} kredit</span>
      <button onClick={onStop} className="absolute bottom-3 right-3 rounded-full bg-white/15 px-3 py-1.5 text-[11px] font-bold text-white backdrop-blur hover:bg-[#EF4444]" data-testid="rt-video-stop">Matikan video</button>
    </div>
  );
}
