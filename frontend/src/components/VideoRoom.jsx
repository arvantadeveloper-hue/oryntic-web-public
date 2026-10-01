import React, { useEffect, useRef, useState } from "react";
import { Mic, MicOff, PhoneOff, Gavel, Loader2, Captions, Radio, Send } from "lucide-react";
import { toast } from "sonner";
import { api, API_BASE, getToken, streamChatWithAtt } from "../lib/api";

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

function Tile({ name, portrait, status, isMe, isMod, micLevel = 0, reaction }) {
  const speaking = status === "speaking";
  const thinking = status === "thinking";
  const ring = isMe ? 1 + micLevel * 0.08 : 1;
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
      {/* darken for label legibility */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/70 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 flex items-center justify-between px-3 py-2">
        <span className="flex items-center gap-1.5 truncate text-xs font-semibold text-white">
          {isMe ? (micLevel > 0.06 ? <Mic size={13} className="text-emerald-400" /> : <Mic size={13} className="text-white/70" />) : isMod ? <Gavel size={13} className="text-amber-300" /> : null}
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

export function VideoRoom({ conv, cid, onClose, onRefresh }) {
  const members = conv.members || [];
  const [statusMap, setStatusMap] = useState({});
  const [reactionMap, setReactionMap] = useState({});
  const [caption, setCaption] = useState(null); // {name, text}
  const [showCaption, setShowCaption] = useState(true);
  const [muted, setMuted] = useState(false);
  const [phase, setPhase] = useState("connecting"); // connecting|listening|thinking|speaking|ending
  const [micLevel, setMicLevel] = useState(0);

  const openRef = useRef(true);
  const mutedRef = useRef(false);
  const recRef = useRef(null);
  const streamRef = useRef(null);
  const acRef = useRef(null);
  const monitorRef = useRef(null);
  const audioRef = useRef(null);
  const queueRef = useRef([]);
  const playingRef = useRef(false);
  const streamDoneRef = useRef(true);

  const VOICE_THRESHOLD = 0.045;
  const SILENCE_AFTER_SPEECH_MS = 1400;

  const setStatus = (id, s) => setStatusMap((m) => ({ ...m, [id]: s }));
  const clearStatuses = () => setStatusMap({});
  const fireReaction = (id, text) => {
    const e = reactionFor(text);
    setReactionMap((m) => ({ ...m, [id]: { e, k: Date.now() } }));
    setTimeout(() => setReactionMap((m) => { const n = { ...m }; delete n[id]; return n; }), 2600);
  };

  const cleanupMic = () => {
    if (monitorRef.current) { clearInterval(monitorRef.current); monitorRef.current = null; }
    try { acRef.current?.close(); } catch (e) {}
    acRef.current = null;
    try { streamRef.current?.getTracks().forEach((t) => t.stop()); } catch (e) {}
    streamRef.current = null;
    setMicLevel(0);
  };

  useEffect(() => {
    openRef.current = true;
    const t = setTimeout(() => { if (openRef.current) startListening(); }, 600);
    return () => {
      clearTimeout(t);
      openRef.current = false;
      try { recRef.current?.stop(); } catch (e) {}
      try { audioRef.current?.pause(); } catch (e) {}
      cleanupMic();
    };
    // eslint-disable-next-line
  }, []);

  const startListening = async () => {
    if (!openRef.current || mutedRef.current || playingRef.current) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mr = new MediaRecorder(stream); recRef.current = mr; const chunks = [];
      mr.ondataavailable = (ev) => chunks.push(ev.data);
      mr.onstop = async () => {
        if (monitorRef.current) { clearInterval(monitorRef.current); monitorRef.current = null; }
        try { acRef.current?.close(); } catch (e) {}
        acRef.current = null;
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        setMicLevel(0); setStatus(ME, "");
        if (!openRef.current || mutedRef.current) return;
        const blob = new Blob(chunks, { type: "audio/webm" });
        const reader = new FileReader();
        reader.onload = async () => {
          try {
            const tr = await api.post("/voice/transcribe", { audio_b64: reader.result, filename: "audio.webm" });
            const text = (tr.data.text || "").trim();
            if (!text) { if (openRef.current && !mutedRef.current) startListening(); return; }
            await runTurn(text);
          } catch (e) { if (openRef.current && !mutedRef.current) startListening(); }
        };
        reader.readAsDataURL(blob);
      };
      mr.start(); setPhase("listening"); setStatus(ME, "listening");

      const AC = window.AudioContext || window.webkitAudioContext;
      const ac = new AC(); acRef.current = ac;
      const src = ac.createMediaStreamSource(stream);
      const analyser = ac.createAnalyser(); analyser.fftSize = 1024;
      src.connect(analyser);
      const buf = new Uint8Array(analyser.fftSize);
      let speechStarted = false; let lastVoiceAt = Date.now();
      monitorRef.current = setInterval(() => {
        if (!openRef.current) return;
        analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) { const d = (buf[i] - 128) / 128; sum += d * d; }
        const rms = Math.sqrt(sum / buf.length);
        setMicLevel(Math.min(1, rms * 6));
        const now = Date.now();
        if (rms > VOICE_THRESHOLD) { speechStarted = true; lastVoiceAt = now; }
        if (speechStarted && now - lastVoiceAt > SILENCE_AFTER_SPEECH_MS) {
          if (monitorRef.current) { clearInterval(monitorRef.current); monitorRef.current = null; }
          try { mr.state !== "inactive" && mr.stop(); } catch (e) {}
        }
      }, 120);
    } catch (e) { setPhase("listening"); }
  };

  const sendNow = () => { if (monitorRef.current) { clearInterval(monitorRef.current); monitorRef.current = null; } try { recRef.current?.state !== "inactive" && recRef.current?.stop(); } catch (e) {} };

  const runTurn = async (text) => {
    setPhase("thinking"); clearStatuses();
    streamDoneRef.current = false;
    try {
      await streamChatWithAtt(cid, text, [], (ev) => {
        if (ev.persona_id && ev.start) setStatus(ev.persona_id, "thinking");
        if (ev.persona_id && ev.final && ev.content) {
          queueRef.current.push({ id: ev.persona_id, name: ev.persona_name, voice: ev.voice || (ev.is_moderator ? "onyx" : "nova"), content: ev.content, isMod: !!ev.is_moderator });
          drainQueue();
        }
      }, { moderator: false });
    } catch (e) {}
    streamDoneRef.current = true;
    onRefresh && onRefresh();
    drainQueue();
  };

  const drainQueue = async () => {
    if (playingRef.current) return;
    if (queueRef.current.length === 0) {
      if (streamDoneRef.current && openRef.current && !mutedRef.current && phaseNotEnding()) {
        clearStatuses(); startListening();
      }
      return;
    }
    playingRef.current = true;
    const item = queueRef.current.shift();
    clearStatuses(); setStatus(item.id, "speaking"); setPhase("speaking");
    fireReaction(item.id, item.content);
    setCaption({ name: item.name, text: item.content });
    try {
      const res = await fetch(`${API_BASE}/voice/tts`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` }, body: JSON.stringify({ text: item.content.slice(0, 1500), voice: item.voice }) });
      const ab = await res.blob();
      const a = new Audio(URL.createObjectURL(ab)); audioRef.current = a;
      a.onended = () => { setStatus(item.id, ""); playingRef.current = false; drainQueue(); };
      a.onerror = () => { setStatus(item.id, ""); playingRef.current = false; drainQueue(); };
      await a.play();
    } catch (e) { setStatus(item.id, ""); playingRef.current = false; drainQueue(); }
  };

  const phaseRef = useRef("connecting");
  useEffect(() => { phaseRef.current = phase; }, [phase]);
  const phaseNotEnding = () => phaseRef.current !== "ending";

  const toggleMute = () => {
    const nv = !muted; setMuted(nv); mutedRef.current = nv;
    if (nv) { try { recRef.current?.stop(); } catch (e) {} cleanupMic(); setStatus(ME, ""); }
    else if (!playingRef.current) startListening();
  };

  const endMeeting = async () => {
    setPhase("ending");
    try { recRef.current?.stop(); } catch (e) {}
    try { audioRef.current?.pause(); } catch (e) {}
    cleanupMic(); queueRef.current = []; playingRef.current = false;
    setStatus(MOD, "speaking");
    try {
      const r = await api.post(`/conversations/${cid}/summary`);
      const summary = r.data.summary || "";
      onRefresh && onRefresh();
      toast.success("Notulen rapat tersimpan di Ruang Kerja");
      if (summary) {
        setCaption({ name: "Moderator", text: summary });
        try {
          const res = await fetch(`${API_BASE}/voice/tts`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` }, body: JSON.stringify({ text: summary.slice(0, 1500), voice: "onyx" }) });
          const ab = await res.blob();
          const a = new Audio(URL.createObjectURL(ab)); audioRef.current = a;
          // Let the moderator speak, but never block the close for more than 25s
          await Promise.race([
            new Promise((resolve) => { a.onended = resolve; a.onerror = resolve; a.play().catch(resolve); }),
            new Promise((resolve) => setTimeout(resolve, 25000)),
          ]);
        } catch (e) {}
      }
    } catch (e) {
      const msg = e?.response?.data?.detail || "Rapat diakhiri";
      toast.message(msg);
    }
    finishClose();
  };

  // helper: keep openRef true during summary so audio plays; listening is blocked via phase 'ending'
  const finishClose = () => { openRef.current = false; cleanupMic(); onClose(); };

  const leaveNoSummary = () => { openRef.current = false; try { recRef.current?.stop(); } catch (e) {} try { audioRef.current?.pause(); } catch (e) {} cleanupMic(); onClose(); };

  const tiles = [{ id: ME, isMe: true }, ...members.map((m) => ({ id: m.id, name: m.name, portrait: m.portrait })), { id: MOD, isMod: true, name: "Moderator" }];
  const phaseLabel = { connecting: "Menyambungkan...", listening: "Mendengarkan Anda — bicara, otomatis terkirim saat berhenti", thinking: "Asisten sedang berpikir...", speaking: "Sedang berbicara...", ending: "Moderator merangkum rapat..." }[phase];

  return (
    <div className="fixed inset-0 z-[96] flex flex-col" style={{ background: "radial-gradient(1200px 500px at 50% -10%, #16213e 0%, #0a0f1f 60%)" }} data-testid="video-room">
      {/* header */}
      <div className="flex items-center gap-3 px-4 py-3 text-white sm:px-6">
        <span className="flex h-9 items-center gap-2 rounded-full bg-white/10 px-3 text-sm font-semibold backdrop-blur">
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" /> {conv.title}
        </span>
        <span className="hidden text-xs text-white/60 sm:block">{members.length} asisten + Moderator</span>
        <span className="ml-auto truncate text-xs text-white/70">{phaseLabel}</span>
      </div>

      {/* tiles grid */}
      <div className="flex-1 overflow-y-auto px-4 pb-2 sm:px-6">
        <div className="mx-auto grid max-w-5xl gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
          {tiles.map((tl) => (
            <Tile key={tl.id} name={tl.name} portrait={tl.portrait} status={statusMap[tl.id] || ""} isMe={tl.isMe} isMod={tl.isMod} micLevel={tl.isMe ? micLevel : 0} reaction={reactionMap[tl.id]} />
          ))}
        </div>
      </div>

      {/* caption */}
      {showCaption && caption && (
        <div className="px-4 pb-2 sm:px-6" data-testid="vr-caption">
          <div className="mx-auto max-w-3xl rounded-2xl bg-black/50 px-4 py-3 text-center backdrop-blur">
            <p className="text-xs font-bold uppercase tracking-wider text-emerald-300">{caption.name}</p>
            <p className="mt-1 max-h-24 overflow-y-auto text-sm leading-relaxed text-white/90">{caption.text}</p>
          </div>
        </div>
      )}

      {/* controls */}
      <div className="flex items-center justify-center gap-3 px-4 py-5 sm:gap-4">
        <button onClick={toggleMute} data-testid="vr-mute" title={muted ? "Nyalakan mic" : "Matikan mic"}
          className={`flex h-14 w-14 items-center justify-center rounded-full text-white transition ${muted ? "bg-[#EF4444]" : "bg-white/15 hover:bg-white/25"}`}>
          {muted ? <MicOff size={22} /> : <Mic size={22} />}
        </button>
        <button onClick={sendNow} disabled={phase !== "listening" || muted} data-testid="vr-send" title="Kirim sekarang"
          className="flex h-14 w-14 items-center justify-center rounded-full bg-[#2F6BFF] text-white transition disabled:opacity-40">
          <Send size={22} />
        </button>
        <button onClick={() => setShowCaption((s) => !s)} data-testid="vr-captions" title="Teks langsung"
          className={`flex h-14 w-14 items-center justify-center rounded-full text-white transition ${showCaption ? "bg-white/25" : "bg-white/10 hover:bg-white/20"}`}>
          <Captions size={22} />
        </button>
        <button onClick={endMeeting} disabled={phase === "ending"} data-testid="vr-end-save"
          className="flex h-14 items-center gap-2 rounded-full bg-[#EF4444] px-5 text-sm font-bold text-white transition hover:brightness-105 disabled:opacity-60">
          {phase === "ending" ? <Loader2 size={20} className="animate-spin" /> : <PhoneOff size={20} />}
          <span className="hidden sm:inline">Akhiri & Simpan Notulen</span>
        </button>
        <button onClick={leaveNoSummary} data-testid="vr-leave" title="Keluar tanpa menyimpan"
          className="flex h-14 w-14 items-center justify-center rounded-full bg-white/10 text-white/80 transition hover:bg-white/20">
          <PhoneOff size={20} />
        </button>
      </div>
    </div>
  );
}
