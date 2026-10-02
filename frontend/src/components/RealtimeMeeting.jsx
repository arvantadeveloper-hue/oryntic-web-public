import React, { useEffect, useRef, useState } from "react";
import { Mic, MicOff, PhoneOff, Loader2, Captions, Zap, Gavel } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { RealtimeSession, runVoiceTool } from "../lib/realtimeSession";
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
  const [showCaption, setShowCaption] = useState(true);
  const [muted, setMuted] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [cpmTotal, setCpmTotal] = useState(null);
  const [micPrefs, setMicPrefs] = useState(() => loadMicPrefs(user));
  const [pipe, setPipe] = useState(null);
  const chat = useMeetingChat(messages);
  const [layout, setLayout] = useMeetingLayout();
  const notulen = useNotulenGate(cid);

  const sessionsRef = useRef([]); // RealtimeSession[], [0] = moderator
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
    if (asked.length) asked.forEach((s) => enqueue(s, `${user?.name || "The user"} asked you directly. Answer the question in 2-5 short spoken sentences.`));
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
        s.toolOutput(t.call_id, out);
        enqueue(s, "Confirm briefly (1-2 sentences) what you just did based on the tool result, then hand back to the user.");
        startNext();
      });
      return;
    }
    if (s === mod() && delegationRef.current) {
      const d = delegationRef.current; delegationRef.current = null;
      const target = panelists().find((p) => p.persona.name === d.assistant) || panelists().find((p) => nameIn(d.assistant || "", p.persona.name));
      if (target) {
        returnRef.current = { call_id: d.call_id, name: target.persona.name, callId: target.callId };
        enqueue(target, `The moderator handed you the floor: ${d.brief || "please answer the user's question"}. Answer in 2-5 short spoken sentences.`);
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
        if (["assign_task", "update_task"].includes(ev.name)) {
          toolRef.current = { callId: s.callId, call_id: ev.call_id, name: ev.name, promise: runVoiceTool(ev.name, { ...a, persona_id: s.persona.id }, cid) };
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
      const c = await api.post("/realtime/calls", { conversation_id: cid });
      created = c.data.sessions;
      if (stale()) { created.forEach((x) => api.post(`/realtime/calls/${x.call_id}/end`, { elapsed_seconds: 0 }).catch(() => {})); return; }
      setCpmTotal(c.data.credits_per_min_total); setModId(c.data.moderator_persona_id);
      const mic = new MicPipeline(micPrefs);
      const stream = await mic.start();
      if (stale()) { mic.stop(); return; }
      pipeRef.current = mic; setPipe(mic);
      const sessions = created.map((x) => new RealtimeSession({ callId: x.call_id, persona: x.persona, primary: x.primary, role: x.role, stream, sendAudio: x.role !== "panelist", sensitivity: micPrefs.sensitivity, createResponse: false, onEvent: handleEvent, onError: () => { if (!endedRef.current) toast.message("Koneksi salah satu peserta terputus"); } }));
      sessionsRef.current = sessions;
      await Promise.all(sessions.map((s) => s.connect()));
      if (stale()) return;
      startedAtRef.current = Date.now();
      // the moderator opens the meeting
      enqueue(sessions[0], undefined); startNext();
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
    if (bargeTimerRef.current) clearTimeout(bargeTimerRef.current);
    sessionsRef.current.forEach((s) => s.close());
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

  const toggleMute = () => { const nv = !muted; setMuted(nv); pipeRef.current?.setMuted(nv); };
  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0"), ss = String(elapsed % 60).padStart(2, "0");
  const modName = members.find((m) => m.id === modId)?.name || "Moderator";
  const label = { connecting: "Menyambungkan semua peserta...", listening: `Mendengarkan Anda — ${modName} memandu; sebut nama asisten lain untuk minta pendapatnya.`, user_speaking: "Anda berbicara...", responding: "Agen merespons — sela kapan saja", ending: "Menyusun notulen..." }[phase];
  const tiles = [{ id: ME, isMe: true, name: user?.name || "Anda" }, ...members.map((m) => ({ id: m.id, name: m.name, portrait: m.portrait, isMod: m.id === modId }))];

  const participants = tiles.map((tl) => ({ ...tl, status: statusMap[tl.id] || "", level: tl.isMe ? (statusMap[ME] === "speaking" ? 0.5 : 0) : (levels[tl.id] || 0) }));
  const stage = (
    <>
      <p className="px-6 text-center text-xs text-white/60" data-testid="rtm-phase">{phase === "connecting" && <Loader2 size={12} className="mr-1 inline animate-spin" />}{label}</p>
      <div className={`flex flex-1 overflow-hidden px-4 pb-2 sm:px-6 ${conv.task_id ? "gap-4" : "items-center overflow-y-auto"}`}>
        {conv.task_id && <PresentationPanel taskId={conv.task_id} refreshKey={taskTick} />}
        <div className={conv.task_id ? "flex w-56 shrink-0 flex-col gap-3 overflow-y-auto" : "mx-auto grid w-full max-w-6xl gap-4"} style={conv.task_id ? {} : { gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, ${tiles.length <= 2 ? 360 : tiles.length <= 4 ? 280 : 220}px), 1fr))` }}>
          {tiles.map((tl) => (
            <Tile key={tl.id} name={tl.name} portrait={tl.portrait} status={statusMap[tl.id] || ""} isMe={tl.isMe} isMod={tl.isMod} micLevel={tl.isMe ? (statusMap[ME] === "speaking" ? 0.5 : 0) : (levels[tl.id] || 0)} />
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
        chat={(variant) => <MeetingChatPanel variant={variant} cid={cid} messages={messages} onRefresh={onRefresh} onClose={chat.close} onExchange={onChatExchange} />} />
      {notulen.dialog}
    </div>
  );
}
