import React, { useEffect, useRef, useState } from "react";
import { Mic, MicOff, PhoneOff, Loader2, Captions, Zap } from "lucide-react";
import { toast } from "sonner";
import { api, API_BASE, getToken } from "../lib/api";
import { vadUpdate } from "../lib/realtimeSession";
import { MicPipeline, loadMicPrefs, saveMicPrefs, BARGE_CONFIRM_MS } from "../lib/micPipeline";
import { MicSettingsMenu } from "./MicSettingsMenu";
import { MeetingChatPanel, ChatToggleButton, useMeetingChat } from "./MeetingChatPanel";
import { useAuth } from "../context/AuthContext";

// ChatGPT-Voice style call: speech-to-speech via OpenAI Realtime (WebRTC), negotiated through our backend.
export function RealtimeCall({ conv, cid, messages = [], onClose, onRefresh, opening = null }) {
  const { user } = useAuth();
  const persona = (conv.members || [])[0] || {};
  const [phase, setPhase] = useState("connecting"); // connecting|listening|user_speaking|thinking|speaking|ended
  const [muted, setMuted] = useState(false);
  const [showCaption, setShowCaption] = useState(true);
  const [captions, setCaptions] = useState([]); // [{role, text}]
  const [live, setLive] = useState(""); // assistant transcript being spoken
  const [level, setLevel] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [cpm, setCpm] = useState(null);
  const [micPrefs, setMicPrefs] = useState(() => loadMicPrefs(user));
  const [pipe, setPipe] = useState(null);
  const chat = useMeetingChat(messages);

  const pcRef = useRef(null);
  const dcRef = useRef(null);
  const pipeRef = useRef(null);
  const phaseRef = useRef("connecting");
  const bargeTimerRef = useRef(null);
  const audioElRef = useRef(null);
  const acRef = useRef(null);
  const rafRef = useRef(null);
  const callIdRef = useRef(null);
  const startedAtRef = useRef(null);
  const liveRef = useRef("");
  const endedRef = useRef(false);
  const tickRef = useRef(null);
  const runIdRef = useRef(0);

  const secs = () => (startedAtRef.current ? Math.round((Date.now() - startedAtRef.current) / 1000) : 0);

  const send = (ev) => { try { if (dcRef.current?.readyState === "open") dcRef.current.send(JSON.stringify(ev)); } catch (e) {} };
  const saveTranscript = (role, content) => {
    if (!callIdRef.current || !content.trim()) return;
    api.post(`/realtime/calls/${callIdRef.current}/transcript`, { role, content }).then(() => onRefresh && onRefresh()).catch(() => {});
  };

  const flushLive = () => {
    const t = liveRef.current.trim();
    if (!t) return;
    liveRef.current = ""; setLive("");
    setCaptions((c) => [...c.slice(-5), { role: "assistant", text: t }]);
    saveTranscript("assistant", t);
  };

  const monitor = (stream) => {
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      const ac = new AC(); acRef.current = ac;
      const an = ac.createAnalyser(); an.fftSize = 512;
      ac.createMediaStreamSource(stream).connect(an);
      const buf = new Uint8Array(an.fftSize);
      const loop = () => {
        an.getByteTimeDomainData(buf);
        let s = 0; for (let i = 0; i < buf.length; i++) { const d = (buf[i] - 128) / 128; s += d * d; }
        setLevel(Math.min(1, Math.sqrt(s / buf.length) * 4));
        rafRef.current = requestAnimationFrame(loop);
      };
      loop();
    } catch (e) {}
  };

  const handleEvent = (ev) => {
    switch (ev.type) {
      case "session.created":
      case "session.updated":
        setPhase((p) => (p === "connecting" ? "listening" : p)); break;
      case "input_audio_buffer.speech_started":
        confirmInterrupt(); break;
      case "input_audio_buffer.speech_stopped":
        setPhase("thinking"); break;
      case "conversation.item.input_audio_transcription.completed":
        if (ev.transcript) { setCaptions((c) => [...c.slice(-5), { role: "user", text: ev.transcript }]); saveTranscript("user", ev.transcript); }
        break;
      case "response.output_audio.delta":
      case "response.audio.delta":
        setPhase("speaking"); break;
      case "response.output_audio_transcript.delta":
      case "response.audio_transcript.delta":
        liveRef.current += ev.delta || ""; setLive(liveRef.current); setPhase("speaking"); break;
      case "response.output_audio_transcript.done":
      case "response.audio_transcript.done": {
        const t = ev.transcript || liveRef.current;
        if (t) { setCaptions((c) => [...c.slice(-5), { role: "assistant", text: t }]); saveTranscript("assistant", t); }
        liveRef.current = ""; setLive("");
        break;
      }
      case "response.done":
        flushLive();
        setPhase((p) => (p === "user_speaking" ? p : "listening")); break;
      case "error":
        toast.error(ev.error?.message || "Realtime error"); break;
      default: break;
    }
  };

  const connect = async (run) => {
    const stale = () => run !== runIdRef.current;
    try {
      const c = await api.post("/realtime/calls", { conversation_id: cid, opening });
      if (stale()) { api.post(`/realtime/calls/${c.data.call_id}/end`, { elapsed_seconds: 0 }).catch(() => {}); return; }
      callIdRef.current = c.data.call_id; setCpm(c.data.credits_per_min);
      const mic = new MicPipeline(micPrefs);
      const stream = await mic.start();
      if (stale()) { mic.stop(); return; }
      pipeRef.current = mic; setPipe(mic);
      const pc = new RTCPeerConnection(); pcRef.current = pc;
      const audioEl = document.createElement("audio"); audioEl.autoplay = true; audioElRef.current = audioEl; document.body.appendChild(audioEl);
      pc.ontrack = (e) => { audioEl.srcObject = e.streams[0]; monitor(e.streams[0]); };
      stream.getTracks().forEach((t) => pc.addTrack(t, stream));
      const dc = pc.createDataChannel("oai-events"); dcRef.current = dc;
      dc.onmessage = (e) => { try { handleEvent(JSON.parse(e.data)); } catch (err) {} };
      dc.onopen = () => {
        startedAtRef.current = Date.now(); setPhase("listening");
        // the assistant speaks first (reminder delivery or a short greeting), like a real phone call
        send({ type: "response.create" });
        tickRef.current = setInterval(async () => {
          try { await api.post(`/realtime/calls/${callIdRef.current}/tick`, { elapsed_seconds: secs() }); onRefresh && onRefresh(); }
          catch (e) { if (e?.response?.status === 402) { toast.error(e.response.data?.detail || "Kredit habis"); hangup(); } }
        }, 60000);
      };
      pc.onconnectionstatechange = () => { if (["failed", "disconnected", "closed"].includes(pc.connectionState) && !endedRef.current) { toast.message("Koneksi panggilan terputus"); hangup(); } };
      const offer = await pc.createOffer(); await pc.setLocalDescription(offer);
      const res = await fetch(`${API_BASE}/realtime/calls/${callIdRef.current}/negotiate?sensitivity=${micPrefs.sensitivity}`, { method: "POST", headers: { "Content-Type": "application/sdp", Authorization: `Bearer ${getToken()}` }, body: offer.sdp });
      if (!res.ok) { let d = "Negosiasi gagal"; try { d = (await res.json()).detail || d; } catch (e) {} throw new Error(d); }
      const answer = await res.text();
      if (stale()) return;
      await pc.setRemoteDescription({ type: "answer", sdp: answer });
    } catch (e) {
      if (stale()) return;
      toast.error(e?.response?.data?.detail || e?.message || "Gagal memulai panggilan");
      hangup();
    }
  };

  const cleanup = () => {
    if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    if (bargeTimerRef.current) clearTimeout(bargeTimerRef.current);
    try { acRef.current?.close(); } catch (e) {}
    try { dcRef.current?.close(); } catch (e) {}
    try { pcRef.current?.close(); } catch (e) {}
    try { pipeRef.current?.stop(); } catch (e) {}
    try { if (audioElRef.current) { audioElRef.current.srcObject = null; audioElRef.current.remove(); } } catch (e) {}
  };

  // user truly barged in (sustained voice near the mic) → stop the assistant mid-sentence
  const userInterrupted = () => {
    if (["speaking", "thinking"].includes(phaseRef.current)) { send({ type: "response.cancel" }); send({ type: "output_audio_buffer.clear" }); }
    liveRef.current = ""; setLive(""); setPhase("user_speaking");
  };
  const confirmInterrupt = () => {
    const openFor = pipeRef.current ? pipeRef.current.openFor() : Infinity;
    if (openFor >= BARGE_CONFIRM_MS) { userInterrupted(); return; }
    if (bargeTimerRef.current) clearTimeout(bargeTimerRef.current);
    bargeTimerRef.current = setTimeout(() => { if (!endedRef.current && pipeRef.current?.isOpen()) userInterrupted(); }, Math.max(60, BARGE_CONFIRM_MS - openFor));
  };
  const changeMic = (p) => {
    setMicPrefs(p); saveMicPrefs(p);
    pipeRef.current?.setSensitivity(p.sensitivity); pipeRef.current?.setNoise(p.noise);
    send(vadUpdate(p.sensitivity, true));
  };
  const onChatExchange = (q, a) => {
    send({ type: "conversation.item.create", item: { type: "message", role: "user", content: [{ type: "input_text", text: `[Chat panel] ${user?.name || "User"} typed: ${q}\n[Chat panel] You replied in text: ${a.slice(0, 600)}` }] } });
  };
  useEffect(() => { phaseRef.current = phase; }, [phase]);

  const hangup = () => {
    if (endedRef.current) return;
    endedRef.current = true; setPhase("ended");
    flushLive();
    const s = secs(); cleanup();
    onClose();
    if (callIdRef.current) api.post(`/realtime/calls/${callIdRef.current}/end`, { elapsed_seconds: s }).then(() => onRefresh && onRefresh()).catch(() => {});
  };

  useEffect(() => {
    endedRef.current = false;
    const run = ++runIdRef.current;
    connect(run);
    const t = setInterval(() => setElapsed(secs()), 1000);
    return () => {
      clearInterval(t); runIdRef.current++;
      if (!endedRef.current) { endedRef.current = true; flushLive(); const s = secs(); cleanup(); if (callIdRef.current) api.post(`/realtime/calls/${callIdRef.current}/end`, { elapsed_seconds: s }).catch(() => {}); callIdRef.current = null; startedAtRef.current = null; }
    };
    // eslint-disable-next-line
  }, []);

  const toggleMute = () => { const nv = !muted; setMuted(nv); pipeRef.current?.setMuted(nv); };
  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0"), ss = String(elapsed % 60).padStart(2, "0");
  const label = { connecting: "Menyambungkan...", listening: "Mendengarkan — bicara saja", user_speaking: "Anda berbicara...", thinking: "Hmm...", speaking: `${persona.name || "Asisten"} berbicara — sela kapan saja`, ended: "Panggilan selesai" }[phase];
  const speaking = phase === "speaking";
  const ring = 1 + (speaking ? level * 0.35 : phase === "user_speaking" ? 0.06 : 0);

  return (
    <div className="fixed inset-0 z-[97] flex flex-col text-white" style={{ background: "radial-gradient(900px 600px at 50% 20%, #1a2550 0%, #0a0f1f 65%)" }} data-testid="realtime-call">
      <div className="flex items-center gap-3 px-5 py-4">
        <span className="flex h-9 items-center gap-2 rounded-full bg-white/10 px-3 text-sm font-semibold backdrop-blur"><span className={`h-2 w-2 rounded-full ${phase === "connecting" ? "bg-amber-400 animate-pulse" : "bg-emerald-400"}`} /> {conv.title}</span>
        <span className="hidden items-center gap-1 rounded-full bg-[#2F6BFF]/20 px-2.5 py-1 text-[11px] font-bold text-[#8FB0FF] sm:flex" data-testid="rt-badge"><Zap size={11} /> Realtime</span>
        <span className="ml-auto font-mono text-sm text-white/80" data-testid="rt-timer">{mm}:{ss}</span>
        {cpm && <span className="hidden text-xs text-white/50 sm:block">{cpm} kredit/mnt</span>}
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-6">
            <div className="relative flex items-center justify-center" style={{ width: 260, height: 260 }}>
              <span className="absolute inset-0 rounded-full transition-transform duration-100" style={{ transform: `scale(${ring + 0.25})`, background: "radial-gradient(circle, rgba(47,107,255,.35) 0%, rgba(124,58,237,.12) 55%, transparent 70%)", opacity: speaking ? 0.9 : 0.45 }} />
              <span className={`absolute inset-6 rounded-full border-2 transition-transform duration-100 ${speaking ? "border-[#2F6BFF]" : phase === "user_speaking" ? "border-emerald-400" : "border-white/15"}`} style={{ transform: `scale(${ring})` }} />
              <div className="relative h-40 w-40 overflow-hidden rounded-full shadow-2xl" data-testid="rt-avatar" style={{ transform: `scale(${1 + (speaking ? level * 0.08 : 0)})`, transition: "transform .1s" }}>
                {persona.portrait ? <img src={persona.portrait} alt="" className="h-full w-full object-cover" /> : <div className="flex h-full w-full items-center justify-center text-5xl font-bold" style={{ background: "linear-gradient(135deg,#2F6BFF,#7C3AED)" }}>{(persona.name || "A")[0]}</div>}
              </div>
            </div>
            <h2 className="mt-6 text-2xl font-bold">{persona.name || "Asisten"}</h2>
            <p className="mt-1 flex items-center gap-2 text-sm text-white/70" data-testid="rt-phase">{phase === "connecting" && <Loader2 size={14} className="animate-spin" />}{label}</p>

            {showCaption && (live || captions.length > 0) && (
              <div className="mt-8 w-full max-w-2xl space-y-2" data-testid="rt-captions">
                {captions.slice(-2).map((c, i) => (
                  <p key={i} className={`text-center text-sm ${c.role === "user" ? "text-emerald-200/80" : "text-white/60"}`}><span className="mr-1 text-[10px] font-bold uppercase tracking-wider opacity-70">{c.role === "user" ? "Anda" : persona.name}</span>{c.text}</p>
                ))}
                {live && <p className="text-center text-base leading-relaxed text-white">{live}</p>}
              </div>
            )}
          </div>

          <div className="flex items-center justify-center gap-3 px-4 py-8 sm:gap-4">
            <button onClick={toggleMute} data-testid="rt-mute" className={`flex h-14 w-14 items-center justify-center rounded-full transition ${muted ? "bg-[#EF4444]" : "bg-white/15 hover:bg-white/25"}`}>{muted ? <MicOff size={22} /> : <Mic size={22} />}</button>
            <MicSettingsMenu prefs={micPrefs} onChange={changeMic} pipeline={pipe} />
            <button onClick={() => setShowCaption((s) => !s)} data-testid="rt-captions-toggle" className={`flex h-14 w-14 items-center justify-center rounded-full transition ${showCaption ? "bg-white/25" : "bg-white/10 hover:bg-white/20"}`}><Captions size={22} /></button>
            <ChatToggleButton open={chat.open} unread={chat.unread} onClick={chat.toggle} />
            <button onClick={hangup} data-testid="rt-end" className="flex h-14 items-center gap-2 rounded-full bg-[#EF4444] px-6 text-sm font-bold transition hover:brightness-105"><PhoneOff size={20} /> Akhiri</button>
          </div>
        </div>

        {chat.open && <MeetingChatPanel cid={cid} messages={messages} onRefresh={onRefresh} onClose={chat.close} onExchange={onChatExchange} />}
      </div>
    </div>
  );
}
