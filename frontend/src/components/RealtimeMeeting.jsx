import React, { useEffect, useRef, useState } from "react";
import { Mic, MicOff, PhoneOff, Loader2, Captions, Zap } from "lucide-react";
import { toast } from "sonner";
import { api, API_BASE, getToken } from "../lib/api";
import { RealtimeSession } from "../lib/realtimeSession";
import { Tile } from "./VideoRoom";
import { useAuth } from "../context/AuthContext";

const ME = "__me__";
const MOD = "__moderator__";
const SILENCE_MS = 20000;

// Multi-assistant meeting where every agent has its own Realtime voice; the browser orchestrates turns.
export function RealtimeMeeting({ conv, cid, onClose, onRefresh }) {
  const { user } = useAuth();
  const members = conv.members || [];
  const [phase, setPhase] = useState("connecting"); // connecting|listening|user_speaking|responding|ending
  const [statusMap, setStatusMap] = useState({});
  const [levels, setLevels] = useState({});
  const [caption, setCaption] = useState(null);
  const [showCaption, setShowCaption] = useState(true);
  const [muted, setMuted] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [cpmTotal, setCpmTotal] = useState(null);

  const sessionsRef = useRef([]); // RealtimeSession[]
  const streamRef = useRef(null);
  const startedAtRef = useRef(null);
  const endedRef = useRef(false);
  const runIdRef = useRef(0);
  const tickRef = useRef(null);
  const rafRef = useRef(null);
  const queueRef = useRef([]); // callIds waiting to speak this turn
  const activeRef = useRef(null); // callId currently speaking
  const liveRef = useRef({}); // callId -> transcript buffer
  const rotateRef = useRef(0);
  const doneTimerRef = useRef(null);
  const userTimerRef = useRef(null);
  const silenceTimerRef = useRef(null);
  const modAudioRef = useRef(null);
  const userTurnsRef = useRef(0);
  const turnHadAgentRef = useRef(false);
  const msgCountRef = useRef(0);

  const secs = () => (startedAtRef.current ? Math.round((Date.now() - startedAtRef.current) / 1000) : 0);
  const setStatus = (id, s) => setStatusMap((m) => ({ ...m, [id]: s }));
  const byCall = (callId) => sessionsRef.current.find((s) => s.callId === callId);

  const saveTranscript = (callId, role, content) => {
    if (!content.trim()) return;
    msgCountRef.current += 1;
    api.post(`/realtime/calls/${callId}/transcript`, { role, content }).then(() => onRefresh && onRefresh()).catch(() => {});
  };

  const flushLive = () => {
    sessionsRef.current.forEach((s) => {
      const t = (liveRef.current[s.callId] || "").trim();
      if (!t) return;
      liveRef.current[s.callId] = "";
      saveTranscript(s.callId, "assistant", t);
    });
  };

  // ---------- moderator (TTS, only when stuck or silent) ----------
  const stopModerator = () => {
    const a = modAudioRef.current; if (!a) return;
    try { a.onended = null; a.pause(); URL.revokeObjectURL(a.src); } catch (e) {}
    modAudioRef.current = null; setStatus(MOD, "");
  };
  const clearSilence = () => { if (silenceTimerRef.current) { clearTimeout(silenceTimerRef.current); silenceTimerRef.current = null; } };
  const armSilence = () => {
    clearSilence();
    silenceTimerRef.current = setTimeout(() => { if (!endedRef.current && !activeRef.current && queueRef.current.length === 0 && !modAudioRef.current) moderatorSpeak("silence"); }, SILENCE_MS);
  };
  const moderatorSpeak = async (reason) => {
    if (endedRef.current || modAudioRef.current) return;
    try {
      setStatus(MOD, "thinking");
      const r = await api.post(`/conversations/${cid}/moderate`, { reason });
      if (endedRef.current || activeRef.current || !r.data.content) { setStatus(MOD, ""); if (!activeRef.current && reason !== "silence") armSilence(); return; }
      const text = r.data.content;
      setCaption({ name: "Moderator", text });
      sessionsRef.current.forEach((o) => o.inject(`[Moderator]: ${text}`));
      const res = await fetch(`${API_BASE}/voice/tts`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` }, body: JSON.stringify({ text: text.slice(0, 1500), voice: r.data.voice || "onyx" }) });
      if (!res.ok || endedRef.current) { setStatus(MOD, ""); return; }
      const a = new Audio(URL.createObjectURL(await res.blob())); modAudioRef.current = a;
      setStatus(MOD, "speaking"); setPhase("responding");
      a.onended = () => { stopModerator(); if (!endedRef.current) { setPhase("listening"); setStatusMap({ [ME]: "listening" }); if (reason !== "silence") armSilence(); } };
      await a.play();
      onRefresh && onRefresh();
    } catch (e) { setStatus(MOD, ""); }
  };

  // ---------- orchestration ----------
  const planTurn = (userText) => {
    const t = userText.toLowerCase();
    const mentioned = sessionsRef.current.filter((s) => t.includes((s.persona.name || "").toLowerCase()) && s.persona.name);
    let order;
    if (mentioned.length === 1) order = mentioned;
    else {
      const all = sessionsRef.current;
      const start = rotateRef.current % all.length; rotateRef.current += 1;
      order = [...all.slice(start), ...all.slice(0, start)];
      if (mentioned.length > 1) order = [...mentioned, ...order.filter((s) => !mentioned.includes(s))];
    }
    queueRef.current = order.map((s) => s.callId);
    startNext();
  };

  const startNext = () => {
    if (endedRef.current) return;
    if (doneTimerRef.current) { clearTimeout(doneTimerRef.current); doneTimerRef.current = null; }
    const next = queueRef.current.shift();
    if (!next) {
      activeRef.current = null; setPhase("listening"); setStatusMap({ [ME]: "listening" });
      if (turnHadAgentRef.current && userTurnsRef.current >= 2) { turnHadAgentRef.current = false; moderatorSpeak("stuck"); } else armSilence();
      return;
    }
    turnHadAgentRef.current = true;
    activeRef.current = next;
    setPhase("responding"); setStatusMap({ [byCall(next).persona.id]: "thinking" });
    const isFirst = !liveRef.current.__turnStarted;
    liveRef.current.__turnStarted = true;
    byCall(next).respond(isFirst ? undefined : "Respond briefly to the user and to what the other assistants just said; add something new or a short agreement.");
  };

  const finishedSpeaking = (callId) => {
    if (activeRef.current !== callId) return;
    setStatus(byCall(callId).persona.id, "");
    startNext();
  };

  const userInterrupted = () => {
    clearSilence(); stopModerator();
    queueRef.current = []; liveRef.current.__turnStarted = false;
    const act = activeRef.current;
    if (act) { byCall(act)?.cancel(); setStatus(byCall(act).persona.id, ""); }
    activeRef.current = null;
    if (doneTimerRef.current) { clearTimeout(doneTimerRef.current); doneTimerRef.current = null; }
    setPhase("user_speaking"); setStatus(ME, "speaking");
  };

  const handleEvent = (s, ev) => {
    const pid = s.persona.id;
    switch (ev.type) {
      case "input_audio_buffer.speech_started":
        if (s.primary) userInterrupted(); break;
      case "input_audio_buffer.speech_stopped":
        if (s.primary) {
          setStatus(ME, "listening");
          if (userTimerRef.current) clearTimeout(userTimerRef.current);
          userTimerRef.current = setTimeout(() => { if (!activeRef.current && queueRef.current.length === 0 && !endedRef.current) { setPhase("listening"); setStatusMap({ [ME]: "listening" }); } }, 7000);
        }
        break;
      case "conversation.item.input_audio_transcription.failed":
        if (s.primary && !activeRef.current) { setPhase("listening"); setStatusMap({ [ME]: "listening" }); }
        break;
      case "conversation.item.input_audio_transcription.completed":
        if (userTimerRef.current) clearTimeout(userTimerRef.current);
        if (s.primary && !(ev.transcript || "").trim()) { if (!activeRef.current) { setPhase("listening"); setStatusMap({ [ME]: "listening" }); } break; }
        if (s.primary && ev.transcript) {
          setCaption({ name: user?.name || "Anda", text: ev.transcript });
          saveTranscript(s.callId, "user", ev.transcript);
          userTurnsRef.current += 1;
          liveRef.current.__turnStarted = false;
          planTurn(ev.transcript);
        }
        break;
      case "output_audio_buffer.started":
      case "response.output_audio.delta":
        if (activeRef.current === s.callId) setStatus(pid, "speaking"); break;
      case "response.output_audio_transcript.delta":
        liveRef.current[s.callId] = (liveRef.current[s.callId] || "") + (ev.delta || "");
        setCaption({ name: s.persona.name, text: liveRef.current[s.callId] });
        break;
      case "response.output_audio_transcript.done": {
        const t = ev.transcript || liveRef.current[s.callId] || "";
        liveRef.current[s.callId] = "";
        if (t) {
          saveTranscript(s.callId, "assistant", t);
          sessionsRef.current.forEach((o) => { if (o !== s) o.inject(`[${s.persona.name}]: ${t}`); });
        }
        break;
      }
      case "response.done":
        if (liveRef.current[s.callId]) { const t = liveRef.current[s.callId]; liveRef.current[s.callId] = ""; saveTranscript(s.callId, "assistant", t); }
        // audio may still be playing; wait for the buffer to drain (fallback timer)
        if (activeRef.current === s.callId) { if (doneTimerRef.current) clearTimeout(doneTimerRef.current); doneTimerRef.current = setTimeout(() => finishedSpeaking(s.callId), 15000); }
        break;
      case "output_audio_buffer.stopped":
      case "output_audio_buffer.cleared":
        finishedSpeaking(s.callId); break;
      case "error":
        if (ev.error?.code !== "response_cancel_not_active") toast.error(ev.error?.message || "Realtime error"); break;
      default: break;
    }
  };

  // ---------- lifecycle ----------
  const connect = async (run) => {
    const stale = () => run !== runIdRef.current;
    let created = [];
    try {
      const c = await api.post("/realtime/calls", { conversation_id: cid });
      created = c.data.sessions;
      if (stale()) { created.forEach((x) => api.post(`/realtime/calls/${x.call_id}/end`, { elapsed_seconds: 0 }).catch(() => {})); return; }
      setCpmTotal(c.data.credits_per_min_total);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      if (stale()) { stream.getTracks().forEach((t) => t.stop()); return; }
      streamRef.current = stream;
      const sessions = created.map((x) => new RealtimeSession({ callId: x.call_id, persona: x.persona, primary: x.primary, stream, onEvent: handleEvent, onError: () => { if (!endedRef.current) { toast.message("Koneksi salah satu peserta terputus"); } } }));
      sessionsRef.current = sessions;
      await Promise.all(sessions.map((s) => s.connect()));
      if (stale()) return;
      startedAtRef.current = Date.now();
      setPhase("listening"); setStatusMap({ [ME]: "listening" });
      // the first assistant greets the room
      activeRef.current = sessions[0].callId; setPhase("responding"); setStatus(sessions[0].persona.id, "thinking");
      sessions[0].respond();
      tickRef.current = setInterval(async () => {
        try { await Promise.all(sessionsRef.current.map((s) => api.post(`/realtime/calls/${s.callId}/tick`, { elapsed_seconds: secs() }))); onRefresh && onRefresh(); }
        catch (e) { toast.error(e?.response?.data?.detail || "Kredit habis"); hangupAll(false); }
      }, 60000);
      const loop = () => { const l = {}; sessionsRef.current.forEach((s) => { l[s.persona.id] = s.readLevel(); }); setLevels(l); rafRef.current = requestAnimationFrame(loop); };
      loop();
    } catch (e) {
      if (stale()) return;
      toast.error(e?.response?.data?.detail || e?.message || "Gagal memulai meeting realtime");
      hangupAll(false);
    }
  };

  const cleanup = () => {
    if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    if (doneTimerRef.current) clearTimeout(doneTimerRef.current);
    if (userTimerRef.current) clearTimeout(userTimerRef.current);
    clearSilence(); stopModerator();
    sessionsRef.current.forEach((s) => s.close());
    try { streamRef.current?.getTracks().forEach((t) => t.stop()); } catch (e) {}
  };

  const endSessions = () => {
    const s = secs();
    sessionsRef.current.forEach((x) => api.post(`/realtime/calls/${x.callId}/end`, { elapsed_seconds: s }).catch(() => {}));
  };

  const hangupAll = async (withSummary) => {
    if (endedRef.current) return;
    endedRef.current = true;
    flushLive(); cleanup(); endSessions();
    if (withSummary && msgCountRef.current > 0) {
      setPhase("ending");
      try { await api.post(`/conversations/${cid}/summary`); toast.success("Notulen meeting tersimpan di Ruang Kerja"); }
      catch (e) { toast.message(e?.response?.data?.detail || "Meeting diakhiri"); }
    }
    onRefresh && onRefresh();
    onClose();
  };

  useEffect(() => {
    endedRef.current = false;
    const run = ++runIdRef.current;
    connect(run);
    const t = setInterval(() => setElapsed(secs()), 1000);
    return () => { clearInterval(t); runIdRef.current++; if (!endedRef.current) { endedRef.current = true; flushLive(); cleanup(); endSessions(); } };
    // eslint-disable-next-line
  }, []);

  const toggleMute = () => { const nv = !muted; setMuted(nv); streamRef.current?.getAudioTracks().forEach((t) => { t.enabled = !nv; }); };
  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0"), ss = String(elapsed % 60).padStart(2, "0");
  const label = { connecting: "Menyambungkan semua peserta...", listening: "Mendengarkan Anda — bicara saja, sebut nama untuk bertanya ke agen tertentu. Moderator hanya menyela saat buntu/hening.", user_speaking: "Anda berbicara...", responding: "Agen merespons — sela kapan saja", ending: "Menyusun notulen..." }[phase];
  const tiles = [{ id: ME, isMe: true, name: user?.name || "Anda" }, ...members.map((m) => ({ id: m.id, name: m.name, portrait: m.portrait })), { id: MOD, isMod: true, name: "Moderator" }];

  return (
    <div className="fixed inset-0 z-[96] flex flex-col" style={{ background: "radial-gradient(1200px 500px at 50% -10%, #16213e 0%, #0a0f1f 60%)" }} data-testid="realtime-meeting">
      <div className="flex items-center gap-3 px-4 py-3 text-white sm:px-6">
        <span className="flex h-9 items-center gap-2 rounded-full bg-white/10 px-3 text-sm font-semibold backdrop-blur"><span className={`h-2 w-2 rounded-full ${phase === "connecting" ? "bg-amber-400 animate-pulse" : "bg-emerald-400"}`} /> {conv.title}</span>
        <span className="flex items-center gap-1 rounded-full bg-[#2F6BFF]/20 px-2.5 py-1 text-[11px] font-bold text-[#8FB0FF]" data-testid="rtm-badge"><Zap size={11} /> Realtime · {members.length} agen + Moderator</span>
        <span className="ml-auto font-mono text-sm text-white/80" data-testid="rtm-timer">{mm}:{ss}</span>
        {cpmTotal && <span className="hidden text-xs text-white/50 sm:block">{cpmTotal} kredit/mnt</span>}
      </div>
      <p className="px-6 text-center text-xs text-white/60" data-testid="rtm-phase">{phase === "connecting" && <Loader2 size={12} className="mr-1 inline animate-spin" />}{label}</p>

      <div className="flex flex-1 items-center overflow-y-auto px-4 pb-2 sm:px-6">
        <div className="mx-auto grid w-full max-w-6xl gap-4" style={{ gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, ${tiles.length <= 2 ? 360 : tiles.length <= 4 ? 280 : 220}px), 1fr))` }}>
          {tiles.map((tl) => (
            <Tile key={tl.id} name={tl.name} portrait={tl.portrait} status={statusMap[tl.id] || ""} isMe={tl.isMe} isMod={tl.isMod} micLevel={tl.isMe ? (statusMap[ME] === "speaking" ? 0.5 : 0) : (levels[tl.id] || 0)} />
          ))}
        </div>
      </div>

      {showCaption && caption && (
        <div className="px-4 pb-2 sm:px-6" data-testid="rtm-caption">
          <div className="mx-auto max-w-3xl rounded-2xl bg-black/50 px-4 py-3 text-center backdrop-blur">
            <p className="text-xs font-bold uppercase tracking-wider text-emerald-300">{caption.name}</p>
            <p className="mt-1 max-h-24 overflow-y-auto text-sm leading-relaxed text-white/90">{caption.text}</p>
          </div>
        </div>
      )}

      <div className="flex items-center justify-center gap-3 px-4 py-5 sm:gap-4">
        <button onClick={toggleMute} data-testid="rtm-mute" className={`flex h-14 w-14 items-center justify-center rounded-full text-white transition ${muted ? "bg-[#EF4444]" : "bg-white/15 hover:bg-white/25"}`}>{muted ? <MicOff size={22} /> : <Mic size={22} />}</button>
        <button onClick={() => setShowCaption((s) => !s)} data-testid="rtm-captions" className={`flex h-14 w-14 items-center justify-center rounded-full text-white transition ${showCaption ? "bg-white/25" : "bg-white/10 hover:bg-white/20"}`}><Captions size={22} /></button>
        <button onClick={() => hangupAll(true)} disabled={phase === "ending"} data-testid="rtm-end-save" className="flex h-14 items-center gap-2 rounded-full bg-[#EF4444] px-5 text-sm font-bold text-white transition hover:brightness-105 disabled:opacity-60">
          {phase === "ending" ? <Loader2 size={20} className="animate-spin" /> : <PhoneOff size={20} />}<span className="hidden sm:inline">Akhiri & Simpan Notulen</span>
        </button>
        <button onClick={() => hangupAll(false)} data-testid="rtm-leave" title="Keluar tanpa notulen" className="flex h-14 w-14 items-center justify-center rounded-full bg-white/10 text-white/80 transition hover:bg-white/20"><PhoneOff size={20} /></button>
      </div>
    </div>
  );
}
