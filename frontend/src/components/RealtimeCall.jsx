import React, { useEffect, useRef, useState } from "react";
import { Mic, MicOff, PhoneOff, Loader2, Zap, MonitorUp, MonitorOff, Camera } from "lucide-react";
import { toast } from "sonner";
import { api, API_BASE, getToken } from "../lib/api";
import { vadUpdate, reportUsage, ContextPruner, runVoiceTool, isBackchannel, RESUME_AFTER_BACKCHANNEL, removeAllCallAudio, bargeMs, loadBehaviour, BEHAVIOUR } from "../lib/realtimeSession";
import { captureFrame } from "../lib/peerAudio";
import { MicPipeline, loadMicPrefs, saveMicPrefs } from "../lib/micPipeline";
import { MicSettingsMenu } from "./MicSettingsMenu";
import { MeetingChatPanel, ChatToggleButton, useMeetingChat } from "./MeetingChatPanel";
import { MeetingShell, LayoutMenu, useMeetingLayout } from "./MeetingShell";
import { InviteButton, InviteDialog } from "./InviteToCall";
import { useAuth } from "../context/AuthContext";

// ChatGPT-Voice style call: speech-to-speech via OpenAI Realtime (WebRTC), negotiated through our backend.
export function RealtimeCall({ conv, cid, messages = [], onClose, onRefresh, onConvChange, opening = null }) {
  const { user } = useAuth();
  const persona = (conv.members || [])[0] || {};
  const isHost = !conv.user_id || conv.user_id === user?.id;
  const [layout, setLayout] = useMeetingLayout();
  const [invite, setInvite] = useState(false);
  // screen share: local preview only (no other humans here); the assistant sees single snapshots on request
  const [screen, setScreen] = useState(null);
  const screenRef = useRef(null);
  const videoRef = useRef(null);
  const [snaps, setSnaps] = useState({ n: 0, credits: 0, busy: false });
  const [visionRate, setVisionRate] = useState(null);
  const snapshotItemRef = useRef(null);
  useEffect(() => { screenRef.current = screen; if (videoRef.current) videoRef.current.srcObject = screen?.stream || null; }, [screen]);
  useEffect(() => { api.get("/realtime/vision-rate").then((r) => setVisionRate(r.data.credits)).catch(() => {}); }, []);
  const [phase, setPhase] = useState("connecting"); // connecting|listening|user_speaking|thinking|speaking|ended
  const [muted, setMuted] = useState(false);
  const [, setLive] = useState(""); // assistant transcript being spoken (shown only in the chat panel)
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
  const prunerRef = useRef(null);

  const secs = () => (startedAtRef.current ? Math.round((Date.now() - startedAtRef.current) / 1000) : 0);

  const send = (ev) => { try { if (dcRef.current?.readyState === "open") dcRef.current.send(JSON.stringify(ev)); } catch (e) {} };
  // one active response per session: queue response.create while one runs, flush on response.done
  const respActiveRef = useRef(false);
  const respQueueRef = useRef([]);
  const lastRespRef = useRef(null);
  const createResponse = (ev = { type: "response.create" }) => {
    if (respActiveRef.current) { respQueueRef.current.push(ev); return; }
    lastRespRef.current = ev; send(ev);
  };
  const flushResponses = () => { const next = respQueueRef.current.shift(); if (next) { lastRespRef.current = next; send(next); } };
  const saveTranscript = (role, content) => {
    if (!callIdRef.current || !content.trim()) return;
    api.post(`/realtime/calls/${callIdRef.current}/transcript`, { role, content }).then(() => onRefresh && onRefresh()).catch(() => {});
  };

  const flushLive = () => {
    const t = liveRef.current.trim();
    if (!t) return;
    liveRef.current = ""; setLive("");
    saveTranscript("assistant", t);
  };

  const stopShare = () => {
    const s = screenRef.current; if (!s) return;
    s.stream.getTracks().forEach((t) => { try { t.stop(); } catch (e) {} });
    setScreen(null);
  };
  const startShare = async () => {
    if (!navigator.mediaDevices?.getDisplayMedia) { toast.error("Peramban ini tidak mendukung bagikan layar"); return; }
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: { ideal: 10, max: 15 }, width: { max: 1920 } }, audio: false });
      stream.getVideoTracks()[0].onended = stopShare;
      setScreen({ kind: "local", stream, name: user?.name || "Anda" });
    } catch (e) { if (e?.name !== "NotAllowedError") toast.error("Gagal membagikan layar"); }
  };
  const showToAssistant = async () => {
    if (!callIdRef.current || !screenRef.current || snaps.busy || dcRef.current?.readyState !== "open") return;
    const img = captureFrame(videoRef.current);
    if (!img) { toast.error("Layar belum siap ditangkap"); return; }
    setSnaps((s) => ({ ...s, busy: true }));
    try {
      const r = await api.post(`/realtime/calls/${callIdRef.current}/snapshot`);
      if (["speaking", "thinking"].includes(phaseRef.current)) { send({ type: "response.cancel" }); send({ type: "output_audio_buffer.clear" }); liveRef.current = ""; setLive(""); }
      const itemId = `img_${Date.now().toString(36)}`; snapshotItemRef.current = itemId;
      send({ type: "conversation.item.create", item: { id: itemId, type: "message", role: "user", content: [
        { type: "input_image", image_url: img, detail: "low" },
        { type: "input_text", text: `[${user?.name || "User"} shows you a snapshot of their shared screen. Look at it and comment briefly in 2-4 spoken sentences on what is relevant; ask if they want details.]` }] } });
      createResponse({ type: "response.create", response: { instructions: "The user just showed you a screenshot of their screen. Describe what matters on it briefly and respond to it." } });
      setPhase("thinking");
      setSnaps((s) => ({ n: s.n + 1, credits: s.credits + (r.data.credits || 0), busy: false }));
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengirim cuplikan"); setSnaps((s) => ({ ...s, busy: false })); }
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
    reportUsage(callIdRef.current, ev);
    prunerRef.current?.onEvent(ev);
    switch (ev.type) {
      case "session.created":
      case "session.updated":
        setPhase((p) => (p === "connecting" ? "listening" : p)); break;
      case "response.created":
        respActiveRef.current = true; break;
      case "input_audio_buffer.speech_started":
        confirmInterrupt(); break;
      case "input_audio_buffer.speech_stopped":
        setPhase("thinking"); break;
      case "conversation.item.input_audio_transcription.completed": {
        const t = (ev.transcript || "").trim();
        if (t && isBackchannel(t) && BEHAVIOUR.backchannel_resume && Date.now() - interruptedAtRef.current < (BEHAVIOUR.backchannel_window_ms || 8000)) {
          interruptedAtRef.current = 0;
          if (respActiveRef.current) { send({ type: "response.cancel" }); send({ type: "output_audio_buffer.clear" }); } // server VAD already started answering the "hmm"
          createResponse({ type: "response.create", response: { instructions: RESUME_AFTER_BACKCHANNEL(t) } });
          break;
        }
        if (t) saveTranscript("user", t);
        break;
      }
      case "response.output_audio.delta":
      case "response.audio.delta":
        setPhase("speaking"); break;
      case "response.output_audio_transcript.delta":
      case "response.audio_transcript.delta":
        liveRef.current += ev.delta || ""; setLive(liveRef.current); setPhase("speaking"); break;
      case "response.output_audio_transcript.done":
      case "response.audio_transcript.done": {
        const t = ev.transcript || liveRef.current;
        if (t) saveTranscript("assistant", t);
        liveRef.current = ""; setLive("");
        break;
      }
      case "response.function_call_arguments.done": {
        let args = {}; try { args = JSON.parse(ev.arguments || "{}"); } catch (e) {}
        setPhase("thinking");
        runVoiceTool(ev.name, args, cid, callIdRef.current).then((out) => {
          if (out.ok && ev.name === "update_task") { toast.success(`Revisi v${out.version} tersimpan di Ruang Kerja`); onRefresh && onRefresh(); }
          if (out.ok && ev.name === "assign_task") toast.success(`Tugas dicatat ke Ruang Kerja (${out.when})`);
          if (out.ok && ev.name === "web_search") { toast.success("Sumber pencarian web dikirim ke chat"); onRefresh && onRefresh(); }
          if (out.ok && ev.name === "run_code") { toast.success("Hasil perhitungan dikirim ke chat"); onRefresh && onRefresh(); }
          if (out.ok && ev.name === "add_calendar_event") { toast.success("Tercatat di kalender"); onRefresh && onRefresh(); }
          if (out.ok && ev.name === "search_workspace") { toast.success(`${out.count} hasil Ruang Kerja dikirim ke chat`); onRefresh && onRefresh(); }
          send({ type: "conversation.item.create", item: { type: "function_call_output", call_id: ev.call_id, output: JSON.stringify(out) } });
          createResponse({ type: "response.create", response: { instructions: "In one casual spoken sentence, tell the user what you just did (from the tool result). No follow-up question unless needed." } });
        });
        break;
      }
      case "response.done":
        respActiveRef.current = false; flushResponses();
        if (snapshotItemRef.current) { send({ type: "conversation.item.delete", item_id: snapshotItemRef.current }); snapshotItemRef.current = null; }
        flushLive();
        prunerRef.current?.prune();
        setPhase((p) => (p === "user_speaking" ? p : "listening")); break;
      case "error":
        if (ev.error?.code === "conversation_already_has_active_response") { respActiveRef.current = true; if (lastRespRef.current) respQueueRef.current.unshift(lastRespRef.current); break; }
        if (ev.error?.code === "response_cancel_not_active") break;
        if (!/item/i.test(ev.error?.message || "")) toast.error(ev.error?.message || "Realtime error"); break;
      default: break;
    }
  };

  const reconnectRef = useRef({ attempts: 0, timer: null, busy: false });
  const streamRef = useRef(null);

  const teardownPeer = () => {
    if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    try { acRef.current?.close(); } catch (e) {}
    try { if (dcRef.current) { dcRef.current.onmessage = null; dcRef.current.onopen = null; dcRef.current.close(); } } catch (e) {}
    try { if (pcRef.current) { pcRef.current.onconnectionstatechange = null; pcRef.current.ontrack = null; pcRef.current.close(); } } catch (e) {}
    try { if (audioElRef.current) { audioElRef.current.srcObject = null; audioElRef.current.remove(); audioElRef.current = null; } } catch (e) {}
  };

  // Build the WebRTC leg (peer, audio sink, data channel, SDP negotiate). Used for the first connect and for every reconnect.
  const setupPeer = async (run, { resume = false } = {}) => {
    const stale = () => run !== runIdRef.current || endedRef.current;
    const pc = new RTCPeerConnection(); pcRef.current = pc;
    const audioEl = document.createElement("audio"); audioEl.autoplay = true; audioElRef.current = audioEl; document.body.appendChild(audioEl);
    pc.ontrack = (e) => { audioEl.srcObject = e.streams[0]; monitor(e.streams[0]); };
    streamRef.current.getTracks().forEach((t) => pc.addTrack(t, streamRef.current));
    const dc = pc.createDataChannel("oai-events"); dcRef.current = dc;
    prunerRef.current = new ContextPruner({ send });
    dc.onmessage = (e) => { try { handleEvent(JSON.parse(e.data)); } catch (err) {} };
    dc.onopen = () => {
      if (stale()) return;
      reconnectRef.current.attempts = 0;
      if (!startedAtRef.current) startedAtRef.current = Date.now();
      setPhase("listening");
      if (resume) {
        toast.success("Koneksi tersambung kembali");
        send({ type: "conversation.item.create", item: { type: "message", role: "user", content: [{ type: "input_text", text: "[System: the call connection dropped briefly and is now restored. Continue naturally where you left off; do not restart the conversation.]" }] } });
      } else if (opening) createResponse(); // the assistant only speaks first when IT is calling (reminder delivery)
      if (tickRef.current) clearInterval(tickRef.current);
      tickRef.current = setInterval(async () => {
        try { await api.post(`/realtime/calls/${callIdRef.current}/tick`, { elapsed_seconds: secs() }); onRefresh && onRefresh(); }
        catch (e) { if (e?.response?.status === 402) { toast.error(e.response.data?.detail || "Kredit habis"); hangup(); } }
      }, 60000);
    };
    pc.onconnectionstatechange = () => {
      if (stale() || pcRef.current !== pc) return;
      if (["failed", "disconnected", "closed"].includes(pc.connectionState)) scheduleReconnect(run);
    };
    const offer = await pc.createOffer(); await pc.setLocalDescription(offer);
    const res = await fetch(`${API_BASE}/realtime/calls/${callIdRef.current}/negotiate?sensitivity=${micPrefs.sensitivity}`, { method: "POST", headers: { "Content-Type": "application/sdp", Authorization: `Bearer ${getToken()}` }, body: offer.sdp });
    if (!res.ok) { let d = "Negosiasi gagal"; try { d = (await res.json()).detail || d; } catch (e) {} throw new Error(d); }
    const answer = await res.text();
    if (stale()) return;
    await pc.setRemoteDescription({ type: "answer", sdp: answer });
  };

  // Connection dropped: keep the call screen, show "Koneksi terputus, sedang menyambung kembali…" and retry with backoff (≈90 s) before giving up.
  const scheduleReconnect = (run, delay = 1500) => {
    const rc = reconnectRef.current;
    if (endedRef.current || run !== runIdRef.current || rc.timer) return;
    setPhase("reconnecting");
    if (["speaking", "thinking"].includes(phaseRef.current)) { liveRef.current = ""; setLive(""); }
    rc.timer = setTimeout(async () => {
      rc.timer = null;
      if (endedRef.current || run !== runIdRef.current) return;
      if (!navigator.onLine) { scheduleReconnect(run, 2000); return; } // wait for the network to come back
      rc.attempts += 1;
      if (rc.attempts > 8) { toast.error("Koneksi tidak dapat dipulihkan. Panggilan diakhiri."); hangup(); return; }
      teardownPeer();
      try { await setupPeer(run, { resume: true }); }
      catch (e) { scheduleReconnect(run, Math.min(15000, 1500 * rc.attempts)); }
    }, delay);
  };

  const connect = async (run) => {
    await loadBehaviour(); // platform Conversation Behaviour (turn detection, barge-in, backchannel) before any session.update
    const stale = () => run !== runIdRef.current;
    try {
      const c = await api.post("/realtime/calls", { conversation_id: cid, opening });
      if (stale()) { api.post(`/realtime/calls/${c.data.call_id}/end`, { elapsed_seconds: 0 }).catch(() => {}); return; }
      callIdRef.current = c.data.call_id; setCpm(c.data.credits_per_min);
      const mic = new MicPipeline(micPrefs);
      const stream = await mic.start();
      if (stale()) { mic.stop(); return; }
      pipeRef.current = mic; setPipe(mic); streamRef.current = stream;
      await setupPeer(run);
    } catch (e) {
      if (stale()) return;
      toast.error(e?.response?.data?.detail || e?.message || "Gagal memulai panggilan");
      hangup();
    }
  };

  const cleanup = () => {
    if (reconnectRef.current.timer) { clearTimeout(reconnectRef.current.timer); reconnectRef.current.timer = null; }
    if (bargeTimerRef.current) clearTimeout(bargeTimerRef.current);
    teardownPeer();
    try { pipeRef.current?.stop(); } catch (e) {}
    stopShare();
    window.__oryntixInCall = false; removeAllCallAudio();
  };

  // user truly barged in (sustained voice near the mic) → stop the assistant mid-sentence
  const interruptedAtRef = useRef(0); // when we cut the assistant off; a backchannel transcript right after → resume instead of answering "hmm"
  const userInterrupted = () => {
    respQueueRef.current = [];
    if (["speaking", "thinking"].includes(phaseRef.current)) { interruptedAtRef.current = Date.now(); send({ type: "response.cancel" }); send({ type: "output_audio_buffer.clear" }); }
    liveRef.current = ""; setLive(""); setPhase("user_speaking");
  };
  const confirmInterrupt = () => {
    const openFor = pipeRef.current ? pipeRef.current.openFor() : Infinity;
    if (openFor >= bargeMs()) { userInterrupted(); return; }
    if (bargeTimerRef.current) clearTimeout(bargeTimerRef.current);
    bargeTimerRef.current = setTimeout(() => { if (!endedRef.current && pipeRef.current?.isOpen()) userInterrupted(); }, Math.max(60, bargeMs() - openFor));
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
  useEffect(() => {
    // browser network events: react right away instead of waiting for ICE to notice
    const offline = () => { if (!endedRef.current) scheduleReconnect(runIdRef.current, 2000); };
    const online = () => { const rc = reconnectRef.current; if (phaseRef.current === "reconnecting" && rc.timer) { clearTimeout(rc.timer); rc.timer = null; scheduleReconnect(runIdRef.current, 300); } };
    window.addEventListener("offline", offline); window.addEventListener("online", online);
    return () => { window.removeEventListener("offline", offline); window.removeEventListener("online", online); };
    // eslint-disable-next-line
  }, []);

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
  const label = { connecting: "Menyambungkan...", reconnecting: "Koneksi terputus, sedang menyambung kembali...", listening: "Mendengarkan — bicara saja", user_speaking: "Anda berbicara...", thinking: "Hmm...", speaking: `${persona.name || "Asisten"} berbicara — sela kapan saja`, ended: "Panggilan selesai" }[phase];
  const speaking = phase === "speaking";
  const ring = 1 + (speaking ? level * 0.35 : phase === "user_speaking" ? 0.06 : 0);

  const participants = [{ id: "me", isMe: true, name: user?.name || "Anda", status: phase === "user_speaking" ? "speaking" : "listening", level: phase === "user_speaking" ? 0.5 : 0 }, { id: persona.id || "p", name: persona.name, portrait: persona.portrait, status: speaking ? "speaking" : phase === "thinking" ? "thinking" : "", level }];
  const avatar = (size) => (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <span className="absolute inset-0 rounded-full transition-transform duration-100" style={{ transform: `scale(${ring + 0.25})`, background: "radial-gradient(circle, rgba(47,107,255,.35) 0%, rgba(124,58,237,.12) 55%, transparent 70%)", opacity: speaking ? 0.9 : 0.45 }} />
      <span className={`absolute inset-6 rounded-full border-2 transition-transform duration-100 ${speaking ? "border-[#2F6BFF]" : phase === "user_speaking" ? "border-emerald-400" : "border-white/15"}`} style={{ transform: `scale(${ring})` }} />
      <div className="relative overflow-hidden rounded-full shadow-2xl" data-testid="rt-avatar" style={{ width: size * 0.62, height: size * 0.62, transform: `scale(${1 + (speaking ? level * 0.08 : 0)})`, transition: "transform .1s" }}>
        {persona.portrait ? <img src={persona.portrait} alt="" className="h-full w-full object-cover" /> : <div className="flex h-full w-full items-center justify-center text-5xl font-bold" style={{ background: "linear-gradient(135deg,#2F6BFF,#7C3AED)" }}>{(persona.name || "A")[0]}</div>}
      </div>
    </div>
  );
  const stage = screen ? (
    <div className="flex flex-1 gap-4 overflow-hidden px-4 pb-2 sm:px-6">
      <div className="relative flex min-w-0 flex-1 items-center justify-center overflow-hidden rounded-2xl border border-white/10 bg-black" data-testid="rt-screen">
        <video ref={videoRef} autoPlay muted playsInline className="max-h-full max-w-full object-contain" />
        <span className="absolute left-3 top-3 flex items-center gap-1.5 rounded-full bg-black/60 px-2.5 py-1 text-[11px] font-bold text-white backdrop-blur" data-testid="rt-screen-label"><MonitorUp size={12} className="text-emerald-300" /> Layar Anda</span>
        <button onClick={showToAssistant} disabled={snaps.busy || phase === "connecting"} data-testid="rt-show-assistant" title="Kirim satu cuplikan layar ke asisten (ditagih per cuplikan)" className="absolute bottom-3 right-3 flex items-center gap-2 rounded-full bg-[#2F6BFF] px-4 py-2 text-xs font-bold text-white shadow-lg transition hover:brightness-110 disabled:opacity-60">
          {snaps.busy ? <Loader2 size={14} className="animate-spin" /> : <Camera size={14} />} Tunjukkan ke asisten{visionRate ? ` · ${visionRate} kredit` : ""}</button>
      </div>
      <div className="flex w-44 shrink-0 flex-col items-center justify-center gap-2">
        {avatar(150)}
        <h2 className="text-base font-bold">{persona.name || "Asisten"}</h2>
        <p className={`flex items-center gap-1.5 text-center text-[11px] ${phase === "reconnecting" ? "font-semibold text-amber-300" : "text-white/70"}`} data-testid="rt-phase">{["connecting", "reconnecting"].includes(phase) && <Loader2 size={12} className="animate-spin" />}{label}</p>
      </div>
    </div>
  ) : (
    <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-6">
      {avatar(260)}
      <h2 className="mt-6 text-2xl font-bold">{persona.name || "Asisten"}</h2>
      <p className={`mt-1 flex items-center gap-2 text-sm ${phase === "reconnecting" ? "font-semibold text-amber-300" : "text-white/70"}`} data-testid="rt-phase">{["connecting", "reconnecting"].includes(phase) && <Loader2 size={14} className="animate-spin" />}{label}</p>
    </div>
  );
  const captionEl = layout === "chat" ? <p className={`text-center text-xs ${phase === "reconnecting" ? "font-semibold text-amber-300" : "text-white/60"}`} data-testid="rt-phase-rail">{label}</p> : null;
  const controls = (
    <div className="flex items-center justify-center gap-3 px-4 py-8 sm:gap-4">
      <button onClick={toggleMute} data-testid="rt-mute" className={`flex h-14 w-14 items-center justify-center rounded-full transition ${muted ? "bg-[#EF4444]" : "bg-white/15 hover:bg-white/25"}`}>{muted ? <MicOff size={22} /> : <Mic size={22} />}</button>
      <MicSettingsMenu prefs={micPrefs} onChange={changeMic} pipeline={pipe} />
      <LayoutMenu layout={layout} onChange={setLayout} />
      <button onClick={screen ? stopShare : startShare} disabled={phase === "connecting"} data-testid="rt-share-screen" title={screen ? "Berhenti membagikan layar" : "Bagikan layar — lalu tekan “Tunjukkan ke asisten” agar asisten melihatnya"} className={`flex h-14 w-14 items-center justify-center rounded-full transition disabled:opacity-50 ${screen ? "bg-emerald-500" : "bg-white/15 hover:bg-white/25"}`}>{screen ? <MonitorOff size={22} /> : <MonitorUp size={22} />}</button>
      {isHost && onConvChange && <InviteButton onClick={() => setInvite(true)} disabled={phase === "connecting"} />}
      {layout !== "chat" && <ChatToggleButton open={chat.open} unread={chat.unread} onClick={chat.toggle} />}
      <button onClick={hangup} data-testid="rt-end" className="flex h-14 items-center gap-2 rounded-full bg-[#EF4444] px-6 text-sm font-bold transition hover:brightness-105"><PhoneOff size={20} /> Akhiri</button>
    </div>
  );

  return (
    <div className="fixed inset-0 z-[97] flex flex-col text-white" style={{ background: "radial-gradient(900px 600px at 50% 20%, #1a2550 0%, #0a0f1f 65%)" }} data-testid="realtime-call">
      <div className="flex items-center gap-3 px-5 py-4">
        <span className="flex h-9 items-center gap-2 rounded-full bg-white/10 px-3 text-sm font-semibold backdrop-blur"><span className={`h-2 w-2 rounded-full ${phase === "connecting" ? "bg-amber-400 animate-pulse" : "bg-emerald-400"}`} /> {conv.title}</span>
        <span className="hidden items-center gap-1 rounded-full bg-[#2F6BFF]/20 px-2.5 py-1 text-[11px] font-bold text-[#8FB0FF] sm:flex" data-testid="rt-badge"><Zap size={11} /> Realtime</span>
        {snaps.n > 0 && <span className="flex h-9 items-center gap-1.5 rounded-full bg-[#2F6BFF]/25 px-3 text-xs font-semibold text-[#BFD3FF] backdrop-blur" data-testid="rt-snapshots" title="Cuplikan layar yang ditunjukkan ke asisten"><Camera size={12} /> {snaps.n} cuplikan · {snaps.credits} kredit</span>}
        <span className="ml-auto font-mono text-sm text-white/80" data-testid="rt-timer">{mm}:{ss}</span>
        {cpm && <span className="hidden text-xs text-white/50 sm:block">{cpm} kredit/mnt</span>}
      </div>
      <MeetingShell layout={layout} chatOpen={chat.open} stage={stage} caption={captionEl} controls={controls} participants={participants}
        chat={(variant) => <MeetingChatPanel variant={variant} cid={cid} messages={messages} onRefresh={onRefresh} onClose={chat.close} onExchange={onChatExchange} />} />
      {invite && <InviteDialog conv={conv} onClose={() => setInvite(false)} onInvited={(c) => onConvChange && onConvChange(c)} />}
    </div>
  );
}
