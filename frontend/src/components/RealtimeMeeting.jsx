import React, { useEffect, useRef, useState } from "react";
import { Mic, MicOff, PhoneOff, Loader2, Captions, Zap, Gavel, VolumeX, Volume2, MonitorUp, MonitorOff, Camera } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { RealtimeSession, runVoiceTool } from "../lib/realtimeSession";
import { PeerMesh, createMixer, captureFrame } from "../lib/peerAudio";
import { PresentationPanel } from "./PresentationPanel";
import { MicPipeline, loadMicPrefs, saveMicPrefs, BARGE_CONFIRM_MS } from "../lib/micPipeline";
import { MicSettingsMenu } from "./MicSettingsMenu";
import { MeetingChatPanel, ChatToggleButton, useMeetingChat } from "./MeetingChatPanel";
import { MeetingShell, LayoutMenu, useMeetingLayout } from "./MeetingShell";
import { useNotulenGate } from "./ConversationTools";
import { Tile } from "./VideoRoom";
import { useAuth } from "../context/AuthContext";

const ME = "__me__";
const nameIn = (text, name) => !!name && new RegExp(`(^|[^\\p{L}])${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}([^\\p{L}]|$)`, "iu").test(text);

// Moderator-led meeting: one assistant (the moderator) hears the user and talks; panelists only receive text and speak when asked or delegated to.
export function RealtimeMeeting({ conv, cid, messages = [], onClose, onRefresh }) {
  const { user } = useAuth();
  const members = conv.members || [];
  const [modId, setModId] = useState(conv.moderator_persona_id || members[0]?.id);
  const [phase, setPhase] = useState("connecting"); // connecting|listening|user_speaking|responding|ending
  const [statusMap, setStatusMap] = useState({});
  const [levels, setLevels] = useState({});
  const [caption, setCaption] = useState(null);
  const [showCaption, setShowCaption] = useState(false);  // transcripts live in the chat panel; stage captions are opt-in
  const [muted, setMuted] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [cpmTotal, setCpmTotal] = useState(null);
  const [micPrefs, setMicPrefs] = useState(() => loadMicPrefs(user));
  const [pipe, setPipe] = useState(null);
  const chat = useMeetingChat(messages);
  const [layout, setLayout] = useMeetingLayout();
  const notulen = useNotulenGate(cid);

  const sessionsRef = useRef([]); // RealtimeSession[], [0] = moderator
  // humans: WebRTC mesh; the host (group owner) runs the single assistant session and mixes audio both ways
  const humans = (conv.humans || []).filter((h) => h.id !== user?.id);
  const isHost = !conv.user_id || conv.user_id === user?.id;
  const hasAI = (conv.persona_ids || members.map((m) => m.id)).length > 0;
  // assistants join only on the call host's client (the person who started the call); decided at connect time
  const runAIRef = useRef(isHost && hasAI);
  const [runAI, setRunAI] = useState(isHost && hasAI);
  const meshRef = useRef(null);
  const mixRef = useRef(null); // { ac, inMix, outMix, audioEls: {} }
  const [peers, setPeers] = useState([]);
  const [turn, setTurn] = useState(null);
  const [mutedPeers, setMutedPeers] = useState({});
  const [callHost, setCallHost] = useState(null); // {is_host, host}
  const [bw, setBw] = useState({ mb: 0, credits: 0 });
  const bytesRef = useRef(0);
  const readBytes = async () => { // total WebRTC bytes (sent+received) across peers
    let total = 0;
    for (const p of Object.values(meshRef.current?.peers || {})) {
      try { const st = await p.pc.getStats(); st.forEach((r) => { if (r.type === "transport") total += (r.bytesSent || 0) + (r.bytesReceived || 0); }); } catch (e) {}
    }
    return total;
  }; // peerId -> true (local-only mute; host also stops feeding them to the assistant)
  const presenceRef = useRef(null);
  const sessionIdRef = useRef(null); // friend-call session id (presence) → links data + assistant costs in the Credits report
  // screen share: my display (sent P2P to friends) or a friend's; the assistant only ever gets single snapshots on request
  const [screen, setScreen] = useState(null); // {kind:"local"|"remote", stream, name, peerId}
  const screenRef = useRef(null);
  const videoRef = useRef(null);
  const [snaps, setSnaps] = useState({ n: 0, credits: 0, busy: false });
  const [visionRate, setVisionRate] = useState(null);
  const snapshotItemRef = useRef(null); // image item id awaiting the assistant's answer (deleted afterwards to stop paying for it)
  useEffect(() => { screenRef.current = screen; if (videoRef.current) videoRef.current.srcObject = screen?.stream || null; }, [screen]);
  useEffect(() => { api.get("/realtime/vision-rate").then((r) => setVisionRate(r.data.credits)).catch(() => {}); }, []);
  const stopShare = () => {
    const s = screenRef.current; if (s?.kind !== "local") return;
    s.stream.getTracks().forEach((t) => { try { t.stop(); } catch (e) {} });
    meshRef.current?.stopScreen(); setScreen(null);
  };
  const startShare = async () => {
    if (!navigator.mediaDevices?.getDisplayMedia) { toast.error("Peramban ini tidak mendukung bagikan layar"); return; }
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: { ideal: 10, max: 15 }, width: { max: 1920 } }, audio: false });
      stream.getVideoTracks()[0].onended = stopShare;
      setScreen({ kind: "local", stream, name: user?.name || "Anda" });
      meshRef.current?.shareScreen(stream);
    } catch (e) { if (e?.name !== "NotAllowedError") toast.error("Gagal membagikan layar"); }
  };
  const showToAssistant = async () => {
    const m = mod(); if (!m || !screenRef.current || snaps.busy) return;
    const img = captureFrame(videoRef.current);
    if (!img) { toast.error("Layar belum siap ditangkap"); return; }
    setSnaps((s) => ({ ...s, busy: true }));
    try {
      const r = await api.post(`/realtime/calls/${m.callId}/snapshot`);
      const itemId = `img_${Date.now().toString(36)}`; snapshotItemRef.current = itemId;
      m.send({ type: "conversation.item.create", item: { id: itemId, type: "message", role: "user", content: [
        { type: "input_image", image_url: img, detail: "low" },
        { type: "input_text", text: `[${user?.name || "User"} shows you a snapshot of the shared screen (${screenRef.current.kind === "local" ? "their own" : `${screenRef.current.name}'s`} screen). Look at it and comment briefly in 2-4 spoken sentences on what is relevant; ask if they want details.]` }] } });
      if (activeRef.current) userInterrupted();
      enqueue(m, "The user just showed you a screenshot of the shared screen. Describe what matters on it briefly and respond to it.");
      startNext();
      setSnaps((s) => ({ n: s.n + 1, credits: s.credits + (r.data.credits || 0), busy: false }));
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengirim cuplikan"); setSnaps((s) => ({ ...s, busy: false })); }
  };
  const mutedPeersRef = useRef({});
  useEffect(() => { mutedPeersRef.current = mutedPeers; }, [mutedPeers]);
  const togglePeerMute = (pid) => {
    setMutedPeers((m) => {
      const next = { ...m, [pid]: !m[pid] };
      const mx = mixRef.current; const el = mx?.audioEls[pid];
      if (el) { el.muted = !!next[pid]; if (runAIRef.current && el.srcObject) { if (next[pid]) mx.inMix.remove(el.srcObject); else mx.inMix.add(el.srcObject); } }
      return next;
    });
  };
  const pipeRef = useRef(null);
  const bargeTimerRef = useRef(null);
  const startedAtRef = useRef(null);
  const endedRef = useRef(false);
  const runIdRef = useRef(0);
  const tickRef = useRef(null);
  const rafRef = useRef(null);
  const queueRef = useRef([]); // [{callId, instructions}]
  const activeRef = useRef(null); // callId currently speaking
  const liveRef = useRef({}); // callId -> transcript buffer
  const saidRef = useRef({}); // callId -> last full transcript
  const delegationRef = useRef(null); // {call_id, assistant, brief} from the moderator's tool call
  const returnRef = useRef(null); // {call_id, name, callId} panelist answering on behalf of the moderator
  const toolRef = useRef(null); // {callId, call_id, name, promise} assign_task / update_task in flight
  const [taskTick, setTaskTick] = useState(0);
  const doneTimerRef = useRef(null);
  const userTimerRef = useRef(null);
  const msgCountRef = useRef(0);

  const secs = () => (startedAtRef.current ? Math.round((Date.now() - startedAtRef.current) / 1000) : 0);
  const setStatus = (id, s) => setStatusMap((m) => ({ ...m, [id]: s }));
  const byCall = (callId) => sessionsRef.current.find((s) => s.callId === callId);
  const mod = () => sessionsRef.current[0];
  const panelists = () => sessionsRef.current.slice(1);
  const listening = () => { setPhase("listening"); setStatusMap({ [ME]: "listening" }); };

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

  // ---------- orchestration ----------
  const enqueue = (s, instructions) => queueRef.current.push({ callId: s.callId, instructions });

  const planTurn = (userText) => {
    const asked = panelists().filter((s) => nameIn(userText, s.persona.name));
    if (asked.length) asked.forEach((s) => enqueue(s, `${user?.name || "The user"} addressed you directly. Respond naturally — as short as the moment calls for (one word is fine), longer only if they asked something that needs it.`));
    else enqueue(mod(), undefined);
    startNext();
  };

  const startNext = () => {
    if (endedRef.current) return;
    if (doneTimerRef.current) { clearTimeout(doneTimerRef.current); doneTimerRef.current = null; }
    const next = queueRef.current.shift();
    if (!next) {
      activeRef.current = null; listening();
      sessionsRef.current.forEach((s) => s.pruner.prune());
      return;
    }
    const s = byCall(next.callId);
    if (!s) { startNext(); return; }
    activeRef.current = next.callId;
    setPhase("responding"); setStatusMap({ [s.persona.id]: "thinking" });
    s.respond(next.instructions);
  };

  const finishedSpeaking = (callId) => {
    if (activeRef.current !== callId) return;
    const s = byCall(callId);
    setStatus(s.persona.id, "");
    if (toolRef.current?.callId === callId) {
      const t = toolRef.current; toolRef.current = null; activeRef.current = null;
      setStatus(s.persona.id, "thinking");
      t.promise.then((out) => {
        if (out.ok && t.name === "update_task") { toast.success(`Revisi v${out.version} tersimpan`); setTaskTick((x) => x + 1); onRefresh && onRefresh(); }
        if (out.ok && t.name === "assign_task") toast.success(`Tugas dicatat ke Ruang Kerja (${out.when})`);
        if (out.ok && t.name === "search_workspace") { toast.success(`${out.count} hasil Ruang Kerja dikirim ke panel chat`); onRefresh && onRefresh(); }
        if (out.ok && ["drive_save", "drive_update", "drive_link", "assign_task", "update_task"].includes(t.name)) onRefresh && onRefresh();
        s.toolOutput(t.call_id, out);
        enqueue(s, "In one casual spoken sentence, tell the user what you just did (from the tool result). No follow-up question unless needed.");
        startNext();
      });
      return;
    }
    if (s === mod() && delegationRef.current) {
      const d = delegationRef.current; delegationRef.current = null;
      const target = panelists().find((p) => p.persona.name === d.assistant) || panelists().find((p) => nameIn(d.assistant || "", p.persona.name));
      if (target) {
        returnRef.current = { call_id: d.call_id, name: target.persona.name, callId: target.callId };
        enqueue(target, `The moderator handed you the floor: ${d.brief || "please answer the user's question"}. Answer naturally in spoken sentences; keep it as short as the question allows.`);
      } else mod().toolOutput(d.call_id, { error: "assistant not found" });
    } else if (returnRef.current?.callId === callId) {
      const r = returnRef.current; returnRef.current = null;
      mod().toolOutput(r.call_id, { assistant: r.name, said: saidRef.current[callId] || "" });
      enqueue(mod(), `${r.name} just answered. Briefly complement or agree in 1-2 short sentences, then hand back to the user.`);
    }
    startNext();
  };

  const settleTools = () => {
    if (delegationRef.current) { mod().toolOutput(delegationRef.current.call_id, { status: "interrupted by user" }); delegationRef.current = null; }
    if (returnRef.current) { mod().toolOutput(returnRef.current.call_id, { status: "interrupted by user" }); returnRef.current = null; }
  };

  const userInterrupted = () => {
    queueRef.current = [];
    const act = activeRef.current;
    if (act) { byCall(act)?.cancel(); setStatus(byCall(act).persona.id, ""); }
    if (toolRef.current) { const t = toolRef.current; toolRef.current = null; t.promise.then((out) => { byCall(t.callId)?.toolOutput(t.call_id, out); if (out.ok && t.name === "update_task") setTaskTick((x) => x + 1); }); }
    activeRef.current = null; settleTools();
    if (doneTimerRef.current) { clearTimeout(doneTimerRef.current); doneTimerRef.current = null; }
    setPhase("user_speaking"); setStatus(ME, "speaking");
  };

  // Like ChatGPT Voice: only a sustained voice near the mic interrupts; stray sounds are ignored.
  const confirmInterrupt = () => {
    const openFor = pipeRef.current ? pipeRef.current.openFor() : Infinity;
    if (openFor >= BARGE_CONFIRM_MS) { userInterrupted(); return; }
    if (bargeTimerRef.current) clearTimeout(bargeTimerRef.current);
    bargeTimerRef.current = setTimeout(() => { if (!endedRef.current && pipeRef.current?.isOpen()) userInterrupted(); }, Math.max(60, BARGE_CONFIRM_MS - openFor));
  };

  const changeMic = (p) => {
    setMicPrefs(p); saveMicPrefs(p);
    pipeRef.current?.setSensitivity(p.sensitivity); pipeRef.current?.setNoise(p.noise);
    sessionsRef.current.forEach((s) => s.updateVad(p.sensitivity));
  };

  // typed Q&A in the chat panel is shared with every voice agent as context
  const onChatExchange = (q, a, name) => {
    sessionsRef.current.forEach((o) => o.inject(`[Chat panel] ${user?.name || "User"} typed: ${q}\n[Chat panel] ${name} replied in text: ${a.slice(0, 600)}`));
  };
  // a file attached in the chat panel becomes shared context, and the speaking assistant briefly brings it up
  const onChatAttach = (names, context) => {
    const who = user?.name || "User";
    sessionsRef.current.forEach((o) => o.inject(`[Chat panel] ${who} attached: ${(names || []).join(", ")}\n[Attachment content]\n${(context || "").slice(0, 2000)}`));
    const s = mod() || sessionsRef.current[0];
    toast.info(`Lampiran dibagikan ke ${s?.persona?.name || "asisten"} di panggilan`);
    if (s) { enqueue(s, "The user just attached a file in the chat panel (see [Attachment content]). In one or two casual spoken sentences, mention that you have seen it and say what it is about, so you can discuss it together. No list, no reading it out loud."); if (!activeRef.current) startNext(); }
  };

  const handleEvent = (s, ev) => {
    const pid = s.persona.id;
    switch (ev.type) {
      case "input_audio_buffer.speech_started":
        confirmInterrupt(); break;
      case "input_audio_buffer.speech_stopped":
        setStatus(ME, "listening");
        if (userTimerRef.current) clearTimeout(userTimerRef.current);
        userTimerRef.current = setTimeout(() => { if (!activeRef.current && queueRef.current.length === 0 && !endedRef.current) listening(); }, 7000);
        break;
      case "conversation.item.input_audio_transcription.failed":
        if (!activeRef.current) listening();
        break;
      case "conversation.item.input_audio_transcription.completed": {
        if (userTimerRef.current) clearTimeout(userTimerRef.current);
        const t = (ev.transcript || "").trim();
        if (!t) { if (!activeRef.current) listening(); break; }
        setCaption({ name: user?.name || "Anda", text: t });
        saveTranscript(s.callId, "user", t);
        panelists().forEach((o) => o.inject(`[${user?.name || "User"}]: ${t}`));
        planTurn(t);
        break;
      }
      case "response.function_call_arguments.done": {
        let a = {}; try { a = JSON.parse(ev.arguments || "{}"); } catch (e) {}
        if (s === mod() && ev.name === "delegate") { delegationRef.current = { call_id: ev.call_id, ...a }; break; }
        if (["assign_task", "update_task", "search_workspace"].includes(ev.name)) {
          toolRef.current = { callId: s.callId, call_id: ev.call_id, name: ev.name, promise: runVoiceTool(ev.name, { ...a, persona_id: s.persona.id }, cid, s.callId) };
        }
        break;
      }
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
          saidRef.current[s.callId] = t;
          saveTranscript(s.callId, "assistant", t);
          const skipMod = returnRef.current?.callId === s.callId; // the moderator gets this via the tool result instead
          sessionsRef.current.forEach((o) => { if (o !== s && !(skipMod && o === mod())) o.inject(`[${s.persona.name}]: ${t}`); });
        }
        break;
      }
      case "response.done":
        if (snapshotItemRef.current && s === mod()) { s.send({ type: "conversation.item.delete", item_id: snapshotItemRef.current }); snapshotItemRef.current = null; }
        if (liveRef.current[s.callId]) { const t = liveRef.current[s.callId]; liveRef.current[s.callId] = ""; saidRef.current[s.callId] = t; saveTranscript(s.callId, "assistant", t); }
        // audio may still be playing; wait for the buffer to drain (fallback timer)
        if (activeRef.current === s.callId) { if (doneTimerRef.current) clearTimeout(doneTimerRef.current); doneTimerRef.current = setTimeout(() => finishedSpeaking(s.callId), 15000); }
        break;
      case "output_audio_buffer.stopped":
      case "output_audio_buffer.cleared":
        finishedSpeaking(s.callId); break;
      case "error":
        if (!["response_cancel_not_active", "item_not_found"].includes(ev.error?.code) && !/item/i.test(ev.error?.message || "")) toast.error(ev.error?.message || "Realtime error");
        break;
      default: break;
    }
  };

  // ---------- lifecycle ----------
  const connect = async (run) => {
    const stale = () => run !== runIdRef.current;
    let created = [];
    try {
      if (humans.length > 0) {
        try { const pres = await api.post(`/conversations/${cid}/call/presence`, { bytes_delta: 0 }); setCallHost(pres.data); sessionIdRef.current = pres.data.call_session_id || null; runAIRef.current = !!pres.data.is_host && hasAI; setRunAI(runAIRef.current); } catch (e) {}
      }
      let runAI = runAIRef.current;
      if (runAI) {
        try {
          const c = await api.post("/realtime/calls", { conversation_id: cid, call_session_id: sessionIdRef.current });
          created = c.data.sessions;
          if (stale()) { created.forEach((x) => api.post(`/realtime/calls/${x.call_id}/end`, { elapsed_seconds: 0 }).catch(() => {})); return; }
          setCpmTotal(c.data.credits_per_min_total); setModId(c.data.moderator_persona_id);
        } catch (e) {
          if (humans.length === 0) throw e; // solo call with assistants must surface the error
          runAI = false; runAIRef.current = false; setRunAI(false); toast.message("Asisten di grup ini bukan milik Anda — panggilan berjalan tanpa asisten.");
        }
      }
      const mic = new MicPipeline(micPrefs);
      const stream = await mic.start();
      if (stale()) { mic.stop(); return; }
      pipeRef.current = mic; setPipe(mic);
      let aiInput = stream;
      if (humans.length > 0) {
        const ac = new (window.AudioContext || window.webkitAudioContext)();
        const inMix = createMixer(ac); const outMix = createMixer(ac);
        inMix.add(stream); outMix.add(stream);
        mixRef.current = { ac, inMix, outMix, audioEls: {} };
        if (runAI) aiInput = inMix.stream; // assistant hears me + every friend
        const mesh = new PeerMesh({
          cid, myId: user?.id, localStream: runAI ? outMix.stream : stream, // friends hear me (+ the assistant when I host it)
          onPeers: setPeers,
          onRemoteVideo: (pid, vs, name) => {
            const cur = screenRef.current;
            if (vs) { if (cur?.kind === "local") stopShare(); setScreen({ kind: "remote", stream: vs, name: name || "Teman", peerId: pid }); }
            else if (cur?.kind === "remote" && cur.peerId === pid) setScreen(null);
          },
          onRemoteStream: (pid, rs) => {
            const m = mixRef.current; if (!m) return;
            const old = m.audioEls[pid];
            if (old) { try { if (old.srcObject) m.inMix.remove(old.srcObject); old.srcObject = null; old.remove(); } catch (e) {} delete m.audioEls[pid]; }
            if (rs) { const el = document.createElement("audio"); el.autoplay = true; el.srcObject = rs; el.muted = !!mutedPeersRef.current[pid]; document.body.appendChild(el); m.audioEls[pid] = el; if (runAIRef.current && !mutedPeersRef.current[pid]) m.inMix.add(rs); }
          },
        });
        meshRef.current = mesh;
        await mesh.start(); setTurn(mesh.turn);
        if (stale()) { mesh.close(); return; }
        window.__oryntixInCall = true;
        const beat = async () => {
          const total = await readBytes(); const delta = Math.max(0, total - bytesRef.current); bytesRef.current = total;
          try { const r = await api.post(`/conversations/${cid}/call/presence`, { bytes_delta: delta }); setCallHost(r.data); if (r.data.is_host) setBw((b) => ({ mb: b.mb + delta / 1e6, credits: b.credits + (r.data.charged || 0) })); } catch (e) {}
        };
        await beat(); presenceRef.current = setInterval(beat, 30000);
      }
      if (!runAI) { startedAtRef.current = Date.now(); listening(); return; }
      const sessions = created.map((x) => new RealtimeSession({ callId: x.call_id, persona: x.persona, primary: x.primary, role: x.role, stream: aiInput, sendAudio: x.role !== "panelist", sensitivity: micPrefs.sensitivity, createResponse: false, onEvent: handleEvent, onError: () => { if (!endedRef.current) toast.message("Koneksi salah satu peserta terputus"); },
        onTrack: (rs) => { if (mixRef.current) mixRef.current.outMix.add(rs); } }));
      sessionsRef.current = sessions;
      await Promise.all(sessions.map((s) => s.connect()));
      if (stale()) return;
      startedAtRef.current = Date.now();
      // the user opens the conversation — no automatic greeting from the moderator
      tickRef.current = setInterval(async () => {
        try { await Promise.all(sessionsRef.current.map((s) => api.post(`/realtime/calls/${s.callId}/tick`, { elapsed_seconds: secs() }))); onRefresh && onRefresh(); }
        catch (e) { toast.error(e?.response?.data?.detail || "Kredit habis"); hangupAll(false); }
      }, 60000);
      const loop = () => { const l = {}; sessionsRef.current.forEach((s) => { l[s.persona.id] = s.readLevel(); }); setLevels(l); rafRef.current = requestAnimationFrame(loop); };
      loop();
    } catch (e) {
      if (stale()) return;
      toast.error(e?.response?.data?.detail || e?.message || "Gagal memulai panggilan realtime");
      hangupAll(false);
    }
  };

  const cleanup = () => {
    if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    if (doneTimerRef.current) clearTimeout(doneTimerRef.current);
    if (userTimerRef.current) clearTimeout(userTimerRef.current);
    if (bargeTimerRef.current) clearTimeout(bargeTimerRef.current);
    sessionsRef.current.forEach((s) => s.close());
    stopShare();
    try { meshRef.current?.close(); } catch (e) {}
    if (presenceRef.current) { clearInterval(presenceRef.current); presenceRef.current = null; api.post(`/conversations/${cid}/call/leave`).catch(() => {}); }
    window.__oryntixInCall = false;
    try { const m = mixRef.current; if (m) { Object.values(m.audioEls).forEach((el) => { el.srcObject = null; el.remove(); }); m.inMix.close(); m.outMix.close(); m.ac.close(); mixRef.current = null; } } catch (e) {}
    try { pipeRef.current?.stop(); } catch (e) {}
  };

  const endSessions = () => {
    const s = secs();
    sessionsRef.current.forEach((x) => api.post(`/realtime/calls/${x.callId}/end`, { elapsed_seconds: s }).catch(() => {}));
  };

  const changeModerator = async (pid) => {
    if (!pid || pid === modId) return;
    try { await api.patch(`/conversations/${cid}/moderator`, { persona_id: pid }); } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengganti moderator"); return; }
    setModId(pid);
    toast.message(`Moderator: ${members.find((m) => m.id === pid)?.name || "asisten"} — menyambungkan ulang...`);
    flushLive(); cleanup(); endSessions();
    sessionsRef.current = []; queueRef.current = []; activeRef.current = null; delegationRef.current = null; returnRef.current = null; liveRef.current = {}; startedAtRef.current = null;
    setStatusMap({}); setCaption(null); setPhase("connecting");
    connect(++runIdRef.current);
  };

  const hangupAll = async (withSummary) => {
    if (endedRef.current) return;
    if (withSummary && msgCountRef.current > 0 && !(await notulen.gate())) return;
    if (endedRef.current) return;
    endedRef.current = true;
    flushLive(); cleanup(); endSessions();
    if (withSummary && msgCountRef.current > 0) {
      setPhase("ending");
      try { await api.post(`/conversations/${cid}/summary`); await api.post(`/conversations/${cid}/compact`).catch(() => {}); toast.success("Notulen tersimpan di Ruang Kerja; transkrip lama diarsipkan"); }
      catch (e) { toast.message(e?.response?.data?.detail || "Panggilan diakhiri"); }
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

  const toggleMute = () => { const nv = !muted; setMuted(nv); pipeRef.current?.setMuted(nv); };
  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0"), ss = String(elapsed % 60).padStart(2, "0");
  const modName = members.find((m) => m.id === modId)?.name || "Moderator";
  const label = { connecting: "Menyambungkan semua peserta...", listening: !runAI ? (hasAI ? "Terhubung dengan teman — asisten aktif saat pemilik grup bergabung." : "Panggilan suara dengan teman (WebRTC).") : `Mendengarkan Anda — ${modName} memandu; sebut nama asisten lain untuk minta pendapatnya.`, user_speaking: "Anda berbicara...", responding: "Agen merespons — sela kapan saja", ending: "Menyusun notulen..." }[phase];
  const tiles = [{ id: ME, isMe: true, name: user?.name || "Anda" },
    ...humans.map((h) => { const p = peers.find((x) => x.id === h.id); return { id: h.id, name: h.name, isHuman: true, online: !!p, state: p?.state }; }),
    ...members.map((m) => ({ id: m.id, name: m.name, portrait: m.portrait, isMod: m.id === modId }))];

  const participants = tiles.map((tl) => ({ ...tl, status: statusMap[tl.id] || "", level: tl.isMe ? (statusMap[ME] === "speaking" ? 0.5 : 0) : (levels[tl.id] || 0) }));
  const rail = !!conv.task_id || !!screen;
  const stage = (
    <>
      <p className="px-6 text-center text-xs text-white/60" data-testid="rtm-phase">{phase === "connecting" && <Loader2 size={12} className="mr-1 inline animate-spin" />}{label}</p>
      <div className={`flex flex-1 overflow-hidden px-4 pb-2 sm:px-6 ${rail ? "gap-4" : "items-center overflow-y-auto"}`}>
        {screen && (
          <div className="relative flex min-w-0 flex-1 items-center justify-center overflow-hidden rounded-2xl border border-white/10 bg-black" data-testid="rtm-screen">
            <video ref={videoRef} autoPlay muted playsInline className="max-h-full max-w-full object-contain" />
            <span className="absolute left-3 top-3 flex items-center gap-1.5 rounded-full bg-black/60 px-2.5 py-1 text-[11px] font-bold text-white backdrop-blur" data-testid="rtm-screen-label"><MonitorUp size={12} className="text-emerald-300" /> Layar {screen.kind === "local" ? "Anda" : screen.name}</span>
            {runAI && <button onClick={showToAssistant} disabled={snaps.busy || phase === "connecting"} data-testid="rtm-show-assistant" title="Kirim satu cuplikan layar ke asisten (ditagih per cuplikan)" className="absolute bottom-3 right-3 flex items-center gap-2 rounded-full bg-[#2F6BFF] px-4 py-2 text-xs font-bold text-white shadow-lg transition hover:brightness-110 disabled:opacity-60">
              {snaps.busy ? <Loader2 size={14} className="animate-spin" /> : <Camera size={14} />} Tunjukkan ke asisten{visionRate ? ` · ${visionRate} kredit` : ""}</button>}
          </div>
        )}
        {conv.task_id && !screen && <PresentationPanel taskId={conv.task_id} refreshKey={taskTick} />}
        <div className={rail ? "flex w-56 shrink-0 flex-col gap-3 overflow-y-auto" : "mx-auto grid w-full max-w-6xl gap-4"} style={rail ? {} : { gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, ${tiles.length <= 2 ? 360 : tiles.length <= 4 ? 280 : 220}px), 1fr))` }}>
          {tiles.map((tl) => (
            <Tile key={tl.id} name={tl.name} portrait={tl.portrait} status={tl.isHuman ? (tl.online ? (tl.state === "connected" ? "terhubung" : "menyambung…") : "belum bergabung") : (statusMap[tl.id] || "")} isMe={tl.isMe} isMod={tl.isMod} micLevel={tl.isMe ? (statusMap[ME] === "speaking" ? 0.5 : 0) : (levels[tl.id] || 0)} dim={tl.isHuman && !!mutedPeers[tl.id]}
              extra={tl.isHuman ? <button onClick={() => togglePeerMute(tl.id)} data-testid={`peer-mute-${tl.id}`} title={mutedPeers[tl.id] ? "Bunyikan kembali" : "Bisukan hanya untuk saya"} className={`pointer-events-auto flex h-7 w-7 items-center justify-center rounded-full ${mutedPeers[tl.id] ? "bg-[#EF4444] text-white" : "bg-white/15 text-white/80 hover:bg-white/30"}`}>{mutedPeers[tl.id] ? <VolumeX size={13} /> : <Volume2 size={13} />}</button> : null} />
          ))}
        </div>
      </div>
    </>
  );
  const captionEl = showCaption && caption ? (
    <div className={layout === "chat" ? "" : "px-4 pb-2 sm:px-6"} data-testid="rtm-caption">
      <div className="mx-auto max-w-3xl rounded-2xl bg-black/50 px-4 py-3 text-center backdrop-blur">
        <p className="text-xs font-bold uppercase tracking-wider text-emerald-300">{caption.name}</p>
        <p className="mt-1 max-h-24 overflow-y-auto text-sm leading-relaxed text-white/90">{caption.text}</p>
      </div>
    </div>
  ) : null;
  const controls = (
    <div className="flex items-center justify-center gap-3 px-4 py-5 sm:gap-4">
      <button onClick={toggleMute} data-testid="rtm-mute" className={`flex h-14 w-14 items-center justify-center rounded-full text-white transition ${muted ? "bg-[#EF4444]" : "bg-white/15 hover:bg-white/25"}`}>{muted ? <MicOff size={22} /> : <Mic size={22} />}</button>
      <MicSettingsMenu prefs={micPrefs} onChange={changeMic} pipeline={pipe} />
      <LayoutMenu layout={layout} onChange={setLayout} />
      <button onClick={screen?.kind === "local" ? stopShare : startShare} disabled={phase === "connecting" || phase === "ending" || screen?.kind === "remote"} data-testid="rtm-share-screen" title={screen?.kind === "local" ? "Berhenti membagikan layar" : screen?.kind === "remote" ? `${screen.name} sedang membagikan layar` : "Bagikan layar ke teman (P2P, tanpa biaya asisten)"} className={`flex h-14 w-14 items-center justify-center rounded-full text-white transition disabled:opacity-50 ${screen?.kind === "local" ? "bg-emerald-500" : "bg-white/15 hover:bg-white/25"}`}>{screen?.kind === "local" ? <MonitorOff size={22} /> : <MonitorUp size={22} />}</button>
      <button onClick={() => setShowCaption((s) => !s)} data-testid="rtm-captions" className={`flex h-14 w-14 items-center justify-center rounded-full text-white transition ${showCaption ? "bg-white/25" : "bg-white/10 hover:bg-white/20"}`}><Captions size={22} /></button>
      {layout !== "chat" && <ChatToggleButton open={chat.open} unread={chat.unread} onClick={chat.toggle} />}
      <button onClick={() => hangupAll(true)} disabled={phase === "ending"} data-testid="rtm-end-save" className="flex h-14 items-center gap-2 rounded-full bg-[#EF4444] px-5 text-sm font-bold text-white transition hover:brightness-105 disabled:opacity-60">
        {phase === "ending" ? <Loader2 size={20} className="animate-spin" /> : <PhoneOff size={20} />}<span className="hidden sm:inline">Akhiri & Simpan Notulen</span>
      </button>
      <button onClick={() => hangupAll(false)} data-testid="rtm-leave" title="Keluar tanpa notulen" className="flex h-14 w-14 items-center justify-center rounded-full bg-white/10 text-white/80 transition hover:bg-white/20"><PhoneOff size={20} /></button>
    </div>
  );

  return (
    <div className="fixed inset-0 z-[96] flex flex-col" style={{ background: "radial-gradient(1200px 500px at 50% -10%, #16213e 0%, #0a0f1f 60%)" }} data-testid="realtime-meeting">
      <div className="flex flex-wrap items-center gap-3 px-4 py-3 text-white sm:px-6">
        <span className="flex h-9 items-center gap-2 rounded-full bg-white/10 px-3 text-sm font-semibold backdrop-blur"><span className={`h-2 w-2 rounded-full ${phase === "connecting" ? "bg-amber-400 animate-pulse" : "bg-emerald-400"}`} /> {conv.title}</span>
        {humans.length > 0 && callHost && <span className="flex h-9 items-center gap-1.5 rounded-full bg-white/10 px-3 text-xs font-semibold text-white/80 backdrop-blur" data-testid="rtm-bandwidth" title="Biaya data panggilan (tarif per GB dari platform) ditanggung host (pemulai panggilan)">{callHost.is_host ? `Host · ${bw.mb.toFixed(1)} MB · ${bw.credits} kredit` : "Gratis · host membayar data"}</span>}
        {snaps.n > 0 && <span className="flex h-9 items-center gap-1.5 rounded-full bg-[#2F6BFF]/25 px-3 text-xs font-semibold text-[#BFD3FF] backdrop-blur" data-testid="rtm-snapshots" title="Cuplikan layar yang ditunjukkan ke asisten"><Camera size={12} /> {snaps.n} cuplikan · {snaps.credits} kredit</span>}
        {humans.length > 0 && <span className="flex h-9 items-center gap-1.5 rounded-full bg-white/10 px-3 text-xs font-semibold text-white/80 backdrop-blur" data-testid="rtm-humans" title={turn === false ? "Tanpa server TURN (hanya STUN) — di jaringan ketat suara teman bisa gagal tersambung" : "WebRTC + TURN aktif"}>{peers.filter((p) => p.state === "connected").length}/{humans.length} teman terhubung{runAI ? " · asisten via host" : hasAI ? " · asisten dijalankan host" : ""}</span>}
        <span className="flex items-center gap-1 rounded-full bg-[#2F6BFF]/20 px-2.5 py-1 text-[11px] font-bold text-[#8FB0FF]" data-testid="rtm-badge"><Zap size={11} /> Realtime · {members.length} agen</span>
        <label className="flex h-9 items-center gap-1.5 rounded-full bg-amber-400/15 px-3 text-xs font-semibold text-amber-200" data-testid="rtm-moderator-picker">
          <Gavel size={13} /> Moderator
          <select value={modId || ""} onChange={(e) => changeModerator(e.target.value)} disabled={phase === "connecting" || phase === "ending"} data-testid="rtm-moderator-select" className="rounded-md bg-transparent text-xs font-bold text-white outline-none disabled:opacity-60 [&>option]:text-slate-900">
            {members.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </label>
        <span className="ml-auto font-mono text-sm text-white/80" data-testid="rtm-timer">{mm}:{ss}</span>
        {cpmTotal && <span className="hidden text-xs text-white/50 sm:block">{cpmTotal} kredit/mnt</span>}
      </div>
      <MeetingShell layout={layout} chatOpen={chat.open} stage={stage} caption={captionEl} controls={controls} participants={participants}
        chat={(variant) => <MeetingChatPanel variant={variant} cid={cid} messages={messages} onRefresh={onRefresh} onClose={chat.close} onExchange={onChatExchange} onAttach={onChatAttach} />} />
      {notulen.dialog}
    </div>
  );
}
