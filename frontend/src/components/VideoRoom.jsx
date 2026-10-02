import React, { useEffect, useRef, useState } from "react";
import { Mic, MicOff, PhoneOff, Gavel, Loader2, Captions, Radio, Send, Hand } from "lucide-react";
import { toast } from "sonner";
import { api, API_BASE, getToken, streamChatWithAtt, streamSSE } from "../lib/api";
import { MicPipeline, loadMicPrefs, saveMicPrefs } from "../lib/micPipeline";
import { MicSettingsMenu } from "./MicSettingsMenu";
import { MeetingChatPanel, ChatToggleButton, useMeetingChat } from "./MeetingChatPanel";
import { MeetingShell, LayoutMenu, useMeetingLayout } from "./MeetingShell";
import { useNotulenGate } from "./ConversationTools";
import { useAuth } from "../context/AuthContext";

const ME = "__me__";
const MOD = "__moderator__";

const FALLBACK_REACTIONS = ["💬", "✨", "👍", "💡", "🙌", "😄"];
function reactionFor(text) {
  const t = (text || "").toLowerCase();
  if (/(haha|wkwk|lucu|😂|ngakak|kocak)/.test(t)) return "😂";
  if (/(terima kasih|makasih|apresiasi)/.test(t)) return "🙏";
  if (/(ide|gagasan|bagaimana kalau|usul|saran)/.test(t)) return "💡";
  if (/(wow|hebat|luar biasa|keren banget|mantap banget)/.test(t)) return "🎉";
  if (/(setuju|mantap|bagus|keren|oke|sip|betul|sepakat)/.test(t)) return "👍";
  if (/(\?\s*$)|(bagaimana|apakah|kenapa|gimana)/.test(t)) return "🤔";
  return FALLBACK_REACTIONS[Math.floor(Math.random() * FALLBACK_REACTIONS.length)];
}

function Waveform({ active, color = "#10B981" }) {
  if (!active) return null;
  return (
    <span className="flex items-end gap-0.5" style={{ height: 16 }}>
      {[0, 1, 2, 3, 4].map((i) => (
        <span key={i} className="vr-bar w-0.5 rounded-full" style={{ height: 16, background: color, animationDelay: `${i * 0.12}s` }} />
      ))}
    </span>
  );
}

export function Tile({ name, portrait, status, isMe, isMod, micLevel = 0, reaction }) {
  const speaking = status === "speaking";
  const thinking = status === "thinking";
  return (
    <div data-testid={`vr-tile-${isMe ? "me" : isMod ? "mod" : name}`}
      className={`relative flex items-center justify-center overflow-hidden rounded-2xl border-2 transition-all duration-200 ${speaking ? "border-emerald-400 vr-speaking" : thinking ? "border-amber-300/70" : "border-white/10"}`}
      style={{ aspectRatio: "4/3", background: "#0b1324" }}>
      {portrait ? (
        <img src={portrait} alt={name} className="h-full w-full object-cover" style={{ transform: `scale(${speaking ? 1.03 : 1})`, transition: "transform .3s" }} />
      ) : (
        <div className="flex h-full w-full items-center justify-center" style={{ background: isMod ? "linear-gradient(135deg,#0B132B,#1f2a4d)" : "linear-gradient(135deg,#2F6BFF,#7C3AED)" }}>
          {isMod ? <Gavel className="text-white/90" size={40} /> : <span className="text-4xl font-extrabold text-white/95">{(name || "?")[0].toUpperCase()}</span>}
        </div>
      )}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/70 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 flex items-center justify-between px-3 py-2">
        <span className="flex items-center gap-1.5 truncate text-xs font-semibold text-white">
          {isMe ? <Mic size={13} className={micLevel > 0.06 ? "text-emerald-400" : "text-white/70"} /> : isMod ? <Gavel size={13} className="text-amber-300" /> : null}
          <span className="truncate">{isMe ? "Anda" : (name || "Asisten")}</span>
        </span>
        {speaking && <Waveform active color={isMod ? "#FBBF24" : "#10B981"} />}
        {thinking && <Loader2 size={14} className="animate-spin text-amber-300" />}
      </div>
      {speaking && <span className="absolute left-3 top-3 flex items-center gap-1 rounded-full bg-emerald-500/90 px-2 py-0.5 text-[10px] font-bold text-white"><Radio size={10} /> BICARA</span>}
      {reaction && <span key={reaction.k} className="vr-reaction pointer-events-none absolute left-1/2 top-4 z-10 -translate-x-1/2 text-4xl drop-shadow-lg" data-testid="vr-reaction">{reaction.e}</span>}
    </div>
  );
}

const VOICE_THRESHOLD = 0.045;      // user starts speaking (listening phase)
const BARGE_THRESHOLD = 0.09;       // louder & sustained → interrupt the assistant
const BARGE_TICKS = 3;              // ~300ms sustained voice
const SILENCE_AFTER_SPEECH_MS = 1400;
const NUDGE_AFTER_MS = 20000;       // quiet for 20s → gentle check-in (moderator / persona)

export function VideoRoom({ conv, cid, messages = [], onClose, onRefresh, isPrivate = false }) {
  const { user } = useAuth();
  const members = conv.members || [];
  const hasModerator = !isPrivate && members.length > 1;
  const [statusMap, setStatusMap] = useState({});
  const [reactionMap, setReactionMap] = useState({});
  const [caption, setCaption] = useState(null);
  const [showCaption, setShowCaption] = useState(true);
  const [muted, setMuted] = useState(false);
  const [phase, setPhase] = useState("connecting"); // connecting|listening|thinking|speaking|ending
  const [micLevel, setMicLevel] = useState(0);
  const [barged, setBarged] = useState(false);
  const [micPrefs, setMicPrefs] = useState(() => loadMicPrefs(user));
  const [pipe, setPipe] = useState(null);
  const chat = useMeetingChat(messages);
  const [layout, setLayout] = useMeetingLayout();
  const notulen = useNotulenGate(cid);

  const openRef = useRef(true);
  const mutedRef = useRef(false);
  const phaseRef = useRef("connecting");
  const streamRef = useRef(null);
  const pipeRef = useRef(null);
  const acRef = useRef(null);
  const monitorRef = useRef(null);
  const recRef = useRef(null);
  const recMetaRef = useRef({ speechStarted: false, lastVoiceAt: 0, discard: false, since: 0 });
  const bargeTicksRef = useRef(0);
  const nudgedRef = useRef(false);
  const interruptedRef = useRef(false);
  const turnRef = useRef(0);
  const abortRef = useRef(null);
  const audioRef = useRef(null);
  const queueRef = useRef([]);
  const playingRef = useRef(false);
  const streamDoneRef = useRef(true);

  const setStatus = (id, s) => setStatusMap((m) => ({ ...m, [id]: s }));
  const clearStatuses = () => setStatusMap({});
  const goPhase = (p) => { phaseRef.current = p; setPhase(p); };
  const fireReaction = (id, text) => {
    const e = reactionFor(text);
    setReactionMap((m) => ({ ...m, [id]: { e, k: Date.now() } }));
    setTimeout(() => setReactionMap((m) => { const n = { ...m }; delete n[id]; return n; }), 2600);
  };

  // ---------- mic (persistent for the whole session) ----------
  const stopAll = () => {
    if (monitorRef.current) { clearInterval(monitorRef.current); monitorRef.current = null; }
    recMetaRef.current.discard = true;
    try { recRef.current?.state !== "inactive" && recRef.current?.stop(); } catch (e) {}
    recRef.current = null;
    try { acRef.current?.close(); } catch (e) {}
    acRef.current = null;
    try { pipeRef.current?.stop(); } catch (e) {}
    pipeRef.current = null;
    streamRef.current = null;
    setMicLevel(0);
  };

  const releaseAudio = () => {
    const a = audioRef.current;
    if (!a) return;
    try { a.onended = null; a.onerror = null; a.pause(); URL.revokeObjectURL(a.src); } catch (e) {}
    audioRef.current = null;
  };

  const stopSpeech = () => {
    try { abortRef.current?.abort(); } catch (e) {}
    abortRef.current = null;
    releaseAudio();
    queueRef.current = [];
    playingRef.current = false;
    streamDoneRef.current = true;
  };

  const restartRecorder = () => {
    const stream = streamRef.current;
    if (!stream || !openRef.current || mutedRef.current) return;
    recMetaRef.current.discard = true;
    try { recRef.current?.state !== "inactive" && recRef.current?.stop(); } catch (e) {}
    const chunks = [];
    const mr = new MediaRecorder(stream);
    const meta = { speechStarted: false, lastVoiceAt: 0, discard: false, since: Date.now() };
    recMetaRef.current = meta;
    mr.ondataavailable = (ev) => chunks.push(ev.data);
    mr.onstop = () => {
      if (meta.discard || !openRef.current || mutedRef.current) return;
      const wasInterrupted = interruptedRef.current; interruptedRef.current = false;
      const blob = new Blob(chunks, { type: "audio/webm" });
      restartRecorder(); // keep listening so the user can interrupt while we think
      const reader = new FileReader();
      reader.onload = async () => {
        const myTurn = ++turnRef.current;
        goPhase("thinking"); setStatus(ME, "");
        try {
          const tr = await api.post("/voice/transcribe", { audio_b64: reader.result, filename: "audio.webm" });
          const text = (tr.data.text || "").trim();
          if (myTurn !== turnRef.current) return;
          if (!text) { backToListening(); return; }
          setCaption({ name: "Anda", text });
          await runTurn(text, wasInterrupted, myTurn);
        } catch (e) { if (myTurn === turnRef.current) backToListening(); }
      };
      reader.readAsDataURL(blob);
    };
    mr.start(); recRef.current = mr;
  };

  const backToListening = () => {
    if (!openRef.current || phaseRef.current === "ending") return;
    clearStatuses(); setBarged(false);
    goPhase("listening"); setStatus(ME, "listening");
    nudgedRef.current = false;
    restartRecorder();
  };

  const initMic = async () => {
    try {
      const mic = new MicPipeline(micPrefs);
      const stream = await mic.start(); // noise-suppressed + gated: distant voices arrive as silence
      if (!openRef.current) { mic.stop(); return; }
      pipeRef.current = mic; setPipe(mic);
      streamRef.current = stream;
      const AC = window.AudioContext || window.webkitAudioContext;
      const ac = new AC(); acRef.current = ac;
      const analyser = ac.createAnalyser(); analyser.fftSize = 1024;
      ac.createMediaStreamSource(stream).connect(analyser);
      const buf = new Uint8Array(analyser.fftSize);
      monitorRef.current = setInterval(() => {
        if (!openRef.current || mutedRef.current) return;
        analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) { const d = (buf[i] - 128) / 128; sum += d * d; }
        const rms = Math.sqrt(sum / buf.length);
        setMicLevel(Math.min(1, rms * 6));
        const now = Date.now();
        const ph = phaseRef.current;
        const meta = recMetaRef.current;
        if (ph === "speaking" || ph === "thinking") {
          // barge-in: sustained loud voice while the assistant talks/thinks
          bargeTicksRef.current = rms > BARGE_THRESHOLD ? bargeTicksRef.current + 1 : 0;
          if (bargeTicksRef.current >= BARGE_TICKS) { bargeTicksRef.current = 0; bargeIn(now); }
          return;
        }
        if (ph !== "listening") return;
        if (rms > VOICE_THRESHOLD) { meta.speechStarted = true; meta.lastVoiceAt = now; }
        if (meta.speechStarted && now - meta.lastVoiceAt > SILENCE_AFTER_SPEECH_MS) { sendNow(); return; }
        if (!meta.speechStarted && !nudgedRef.current && now - meta.since > NUDGE_AFTER_MS) { nudgedRef.current = true; nudge(); }
      }, 100);
      backToListening();
    } catch (e) { goPhase("listening"); toast.error("Mikrofon tidak tersedia"); }
  };

  const bargeIn = (now) => {
    turnRef.current += 1; // invalidate in-flight turn
    stopSpeech();
    clearStatuses(); setBarged(true);
    interruptedRef.current = true;
    goPhase("listening"); setStatus(ME, "listening");
    if (!recRef.current || recRef.current.state === "inactive") restartRecorder();
    const meta = recMetaRef.current; meta.speechStarted = true; meta.lastVoiceAt = now; meta.since = now;
  };

  const sendNow = () => { try { recRef.current?.state !== "inactive" && recRef.current?.stop(); } catch (e) {} };

  useEffect(() => {
    openRef.current = true;
    const t = setTimeout(() => { if (openRef.current) initMic(); }, 500);
    return () => { clearTimeout(t); openRef.current = false; stopSpeech(); stopAll(); };
    // eslint-disable-next-line
  }, []);

  // ---------- turns ----------
  const consume = (ev, myTurn) => {
    if (myTurn !== turnRef.current) return;
    if (ev.persona_id && ev.start) setStatus(ev.persona_id, "thinking");
    if (ev.persona_id && ev.final && ev.content) {
      queueRef.current.push({ id: ev.persona_id, name: ev.persona_name, voice: ev.voice || (ev.is_moderator ? "onyx" : "nova"), content: ev.content, turn: myTurn });
      drainQueue();
    }
  };

  const runTurn = async (text, interrupted, myTurn) => {
    goPhase("thinking"); clearStatuses();
    streamDoneRef.current = false;
    const ctrl = new AbortController(); abortRef.current = ctrl;
    try {
      await streamChatWithAtt(cid, text, [], (ev) => consume(ev, myTurn), { moderator: false, voice_mode: true, interrupted }, ctrl.signal);
    } catch (e) { if (e?.name !== "AbortError" && myTurn === turnRef.current) turnFailed(e); }
    if (myTurn !== turnRef.current) return;
    streamDoneRef.current = true;
    onRefresh && onRefresh();
    drainQueue();
  };

  const turnFailed = (e) => {
    const quota = e?.status === 402;
    const msg = quota ? "Kuota kredit harian habis — hubungi admin." : "Gagal mendapatkan jawaban, coba bicara lagi.";
    toast.error(msg);
    setCaption({ name: "Sistem", text: msg });
  };

  const nudge = async () => {
    const myTurn = ++turnRef.current;
    goPhase("thinking");
    streamDoneRef.current = false;
    const ctrl = new AbortController(); abortRef.current = ctrl;
    restartRecorder();
    try { await streamSSE(`/conversations/${cid}/nudge`, {}, (ev) => consume(ev, myTurn), ctrl.signal); } catch (e) { if (e?.name !== "AbortError") console.warn("nudge failed", e); }
    if (myTurn !== turnRef.current) return;
    streamDoneRef.current = true;
    onRefresh && onRefresh();
    drainQueue();
  };

  const drainQueue = async () => {
    if (playingRef.current) return;
    if (queueRef.current.length === 0) {
      if (streamDoneRef.current && openRef.current && phaseRef.current !== "ending") backToListening();
      return;
    }
    playingRef.current = true;
    const item = queueRef.current.shift();
    const myTurn = item.turn;
    clearStatuses(); setStatus(item.id, "speaking"); goPhase("speaking"); setBarged(false);
    fireReaction(item.id, item.content);
    setCaption({ name: item.name, text: item.content });
    restartRecorder(); // only capture what the user says over this utterance
    const finish = () => { releaseAudio(); if (myTurn !== turnRef.current) return; setStatus(item.id, ""); playingRef.current = false; drainQueue(); };
    try {
      const res = await fetch(`${API_BASE}/voice/tts`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` }, body: JSON.stringify({ text: item.content.slice(0, 1500), voice: item.voice }), signal: abortRef.current?.signal });
      if (myTurn !== turnRef.current) return;
      if (!res.ok) throw new Error("tts");
      const ab = await res.blob();
      releaseAudio();
      const a = new Audio(URL.createObjectURL(ab)); audioRef.current = a;
      a.onended = finish; a.onerror = finish;
      await a.play();
    } catch (e) { finish(); }
  };

  const toggleMute = () => {
    const nv = !muted; setMuted(nv); mutedRef.current = nv;
    pipeRef.current?.setMuted(nv);
    if (nv) { recMetaRef.current.discard = true; try { recRef.current?.stop(); } catch (e) {} setStatus(ME, ""); setMicLevel(0); }
    else if (phaseRef.current === "listening") backToListening();
    else restartRecorder();
  };

  const changeMic = (p) => { setMicPrefs(p); saveMicPrefs(p); pipeRef.current?.setSensitivity(p.sensitivity); pipeRef.current?.setNoise(p.noise); };

  const endMeeting = async () => {
    if (isPrivate) {
      openRef.current = false; stopSpeech(); stopAll();
      toast.message("Panggilan diakhiri");
      onClose();
      return;
    }
    if (!(await notulen.gate())) return;
    goPhase("ending");
    stopSpeech(); stopAll();
    setStatus(MOD, "speaking");
    try {
      const r = await api.post(`/conversations/${cid}/summary`);
      api.post(`/conversations/${cid}/compact`).catch(() => {});
      const summary = r.data.summary || "";
      onRefresh && onRefresh();
      toast.success("Notulen meeting tersimpan di Ruang Kerja");
      if (summary) {
        setCaption({ name: "Moderator", text: summary });
        try {
          const res = await fetch(`${API_BASE}/voice/tts`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` }, body: JSON.stringify({ text: summary.slice(0, 1500), voice: "onyx" }) });
          const ab = await res.blob();
          const a = new Audio(URL.createObjectURL(ab)); audioRef.current = a;
          await Promise.race([
            new Promise((resolve) => { a.onended = resolve; a.onerror = resolve; a.play().catch(resolve); }),
            new Promise((resolve) => setTimeout(resolve, 25000)),
          ]);
          releaseAudio();
        } catch (e) {}
      }
    } catch (e) {
      toast.message(e?.response?.data?.detail || "Meeting diakhiri");
    }
    openRef.current = false; onClose();
  };

  const leaveNoSummary = () => { openRef.current = false; stopSpeech(); stopAll(); onClose(); };

  const tiles = [{ id: ME, isMe: true, name: user?.name || "Anda" }, ...members.map((m) => ({ id: m.id, name: m.name, portrait: m.portrait })), ...(hasModerator ? [{ id: MOD, isMod: true, name: "Moderator" }] : [])];
  const phaseLabel = {
    connecting: "Menyambungkan...",
    listening: barged ? "Anda menyela — silakan lanjutkan, saya mendengarkan" : "Mendengarkan Anda — bicara saja, otomatis terkirim saat berhenti",
    thinking: "Asisten sedang berpikir... (bicara kapan saja untuk menyela)",
    speaking: "Sedang berbicara — Anda bisa menyela kapan saja",
    ending: "Moderator merangkum meeting...",
  }[phase];

  const participants = tiles.map((tl) => ({ ...tl, status: statusMap[tl.id] || "", level: tl.isMe ? micLevel : 0 }));
  const stage = (
    <div className="flex flex-1 items-center overflow-y-auto px-4 pb-2 sm:px-6">
      <div className="mx-auto grid w-full max-w-6xl gap-4" style={{ gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, ${tiles.length <= 2 ? 360 : tiles.length <= 4 ? 280 : 220}px), 1fr))` }}>
        {tiles.map((tl) => (
          <Tile key={tl.id} name={tl.name} portrait={tl.portrait} status={statusMap[tl.id] || ""} isMe={tl.isMe} isMod={tl.isMod} micLevel={tl.isMe ? micLevel : 0} reaction={reactionMap[tl.id]} />
        ))}
      </div>
    </div>
  );
  const captionEl = (
    <>
      {barged && (
        <div className="px-4 pb-2 text-center sm:px-6">
          <span className="vr-barge inline-flex items-center gap-1.5 rounded-full bg-amber-400/90 px-3 py-1 text-xs font-bold text-slate-900" data-testid="vr-barge-pill"><Hand size={12} /> Anda menyela</span>
        </div>
      )}
      {showCaption && caption && (
        <div className={layout === "chat" ? "" : "px-4 pb-2 sm:px-6"} data-testid="vr-caption">
          <div className="mx-auto max-w-3xl rounded-2xl bg-black/50 px-4 py-3 text-center backdrop-blur">
            <p className="text-xs font-bold uppercase tracking-wider text-emerald-300">{caption.name}</p>
            <p className="mt-1 max-h-24 overflow-y-auto text-sm leading-relaxed text-white/90">{caption.text}</p>
          </div>
        </div>
      )}
    </>
  );
  const controls = (
    <div className="flex items-center justify-center gap-3 px-4 py-5 sm:gap-4">
      <button onClick={toggleMute} data-testid="vr-mute" title={muted ? "Nyalakan mic" : "Matikan mic"}
        className={`flex h-14 w-14 items-center justify-center rounded-full text-white transition ${muted ? "bg-[#EF4444]" : "bg-white/15 hover:bg-white/25"}`}>
        {muted ? <MicOff size={22} /> : <Mic size={22} />}
      </button>
      <MicSettingsMenu prefs={micPrefs} onChange={changeMic} pipeline={pipe} />
      <LayoutMenu layout={layout} onChange={setLayout} />
      <button onClick={sendNow} disabled={phase !== "listening" || muted} data-testid="vr-send" title="Kirim sekarang"
        className="flex h-14 w-14 items-center justify-center rounded-full bg-[#2F6BFF] text-white transition disabled:opacity-40">
        <Send size={22} />
      </button>
      <button onClick={() => setShowCaption((s) => !s)} data-testid="vr-captions" title="Teks langsung"
        className={`flex h-14 w-14 items-center justify-center rounded-full text-white transition ${showCaption ? "bg-white/25" : "bg-white/10 hover:bg-white/20"}`}>
        <Captions size={22} />
      </button>
      {layout !== "chat" && <ChatToggleButton open={chat.open} unread={chat.unread} onClick={chat.toggle} />}
      <button onClick={endMeeting} disabled={phase === "ending"} data-testid="vr-end-save"
        className="flex h-14 items-center gap-2 rounded-full bg-[#EF4444] px-5 text-sm font-bold text-white transition hover:brightness-105 disabled:opacity-60">
        {phase === "ending" ? <Loader2 size={20} className="animate-spin" /> : <PhoneOff size={20} />}
        <span className="hidden sm:inline">{isPrivate ? "Akhiri Panggilan" : "Akhiri & Simpan Notulen"}</span>
      </button>
      {!isPrivate && (
        <button onClick={leaveNoSummary} data-testid="vr-leave" title="Keluar tanpa menyimpan"
          className="flex h-14 w-14 items-center justify-center rounded-full bg-white/10 text-white/80 transition hover:bg-white/20">
          <PhoneOff size={20} />
        </button>
      )}
    </div>
  );

  return (
    <div className="fixed inset-0 z-[96] flex flex-col" style={{ background: "radial-gradient(1200px 500px at 50% -10%, #16213e 0%, #0a0f1f 60%)" }} data-testid="video-room">
      <div className="flex items-center gap-3 px-4 py-3 text-white sm:px-6">
        <span className="flex h-9 items-center gap-2 rounded-full bg-white/10 px-3 text-sm font-semibold backdrop-blur">
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" /> {conv.title}
        </span>
        <span className="hidden text-xs text-white/60 sm:block">{isPrivate ? "Panggilan suara" : `Meeting · ${members.length} asisten${hasModerator ? " + Moderator" : ""}`}</span>
        <span className="ml-auto truncate text-xs text-white/70" data-testid="vr-phase">{phaseLabel}</span>
      </div>
      <MeetingShell layout={layout} chatOpen={chat.open} stage={stage} caption={captionEl} controls={controls} participants={participants}
        chat={(variant) => <MeetingChatPanel variant={variant} cid={cid} messages={messages} onRefresh={onRefresh} onClose={chat.close} />} />
      {notulen.dialog}
    </div>
  );
}
