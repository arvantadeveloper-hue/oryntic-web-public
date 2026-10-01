import React, { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Plus, Send, Search, Trash2, Copy, RefreshCw, Bookmark, Users, User, X, Check, Bot, Paperclip, Mic, Square, Volume2, VolumeX, FileText, Image as ImageIcon, Gavel, Phone, PhoneOff, MessageSquare, Video } from "lucide-react";
import { toast } from "sonner";
import { api, API_BASE, getToken, streamChatWithAtt } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n";
import { Markdown } from "../components/Markdown";
import { VideoRoom } from "../components/VideoRoom";

function Avatar({ name, portrait, size = 32, moderator }) {
  if (moderator) return <span className="flex items-center justify-center rounded-full bg-[#0B132B] text-white" style={{ width: size, height: size }}><Gavel size={size * 0.5} /></span>;
  if (portrait) return <img src={portrait} alt={name} className="rounded-full object-cover" style={{ width: size, height: size }} />;
  return <span className="flex items-center justify-center rounded-full font-bold text-white" style={{ width: size, height: size, fontSize: size * 0.42, background: "linear-gradient(135deg,#2F6BFF,#7C3AED)" }}>{(name || "?")[0].toUpperCase()}</span>;
}

const fileToData = (file) => new Promise((res) => {
  const r = new FileReader();
  r.onload = () => res(r.result);
  if (file.type.startsWith("image/") || file.type === "application/pdf") r.readAsDataURL(file);
  else r.readAsText(file);
});

export default function Chat() {
  const { id } = useParams();
  const nav = useNavigate();
  const { refreshUser } = useAuth();
  const { t } = useI18n();
  const [convs, setConvs] = useState([]);
  const [q, setQ] = useState("");
  const [conv, setConv] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [liveMap, setLiveMap] = useState({});
  const [liveOrder, setLiveOrder] = useState([]);
  const [personas, setPersonas] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [picked, setPicked] = useState([]);
  const [mode, setMode] = useState("group");
  const [attachments, setAttachments] = useState([]);
  const [recording, setRecording] = useState(false);
  const [speaker, setSpeaker] = useState(false);
  const [callOpen, setCallOpen] = useState(false);
  const [videoOpen, setVideoOpen] = useState(false);
  const [showConvList, setShowConvList] = useState(false);
  const endRef = useRef(null);
  const fileRef = useRef(null);
  const recRef = useRef(null);
  const audioRef = useRef(null);

  const loadConvs = (query = "") => api.get(`/conversations${query ? `?q=${encodeURIComponent(query)}` : ""}`).then((r) => setConvs(r.data)).catch(() => {});
  useEffect(() => { loadConvs(); api.get("/personas").then((r) => setPersonas(r.data)).catch(() => {}); }, []);
  useEffect(() => {
    if (id) api.get(`/conversations/${id}/messages`).then((r) => { setConv(r.data.conversation); setMessages(r.data.messages); }).catch(() => {});
    else { setConv(null); setMessages([]); }
    const pre = sessionStorage.getItem("aivora_prefill");
    if (pre && id) { setInput(pre); sessionStorage.removeItem("aivora_prefill"); }
  }, [id]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, liveMap]);

  const openModal = () => {
    if (personas.length === 0) { toast.message("Buat persona dulu untuk memulai percakapan"); nav("/personas/new"); return; }
    setPicked([]); setMode("group"); setShowModal(true);
  };
  const togglePick = (pid) => setPicked((p) => p.includes(pid) ? p.filter((x) => x !== pid) : [...p, pid]);
  const startConv = async () => {
    if (picked.length === 0) { toast.error("Pilih minimal satu persona"); return; }
    const type = picked.length > 1 ? mode : "private";
    const r = await api.post("/conversations", { persona_ids: picked, type });
    setShowModal(false); loadConvs(); nav(`/chat/${r.data.id}`);
  };

  const onFiles = async (e) => {
    const files = Array.from(e.target.files || []);
    const out = [];
    for (const f of files.slice(0, 5)) {
      const type = f.type.startsWith("image/") ? "image" : f.type === "application/pdf" ? "pdf" : "text";
      out.push({ type, name: f.name, data: await fileToData(f) });
    }
    setAttachments((a) => [...a, ...out].slice(0, 5));
    e.target.value = "";
  };

  const playTTS = async (text, voice = "nova") => {
    try {
      const res = await fetch(`${API_BASE}/voice/tts`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` }, body: JSON.stringify({ text: text.slice(0, 1500), voice: voice || "nova" }) });
      if (!res.ok) return;
      const blob = await res.blob();
      if (audioRef.current) { audioRef.current.pause(); }
      const a = new Audio(URL.createObjectURL(blob)); audioRef.current = a; a.play();
    } catch (e) {}
  };
  const voiceFor = (pid) => (conv?.members || []).find((m) => m.id === pid)?.voice || "nova";

  const toggleRecord = async () => {
    if (recording) { recRef.current?.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream); recRef.current = mr; const chunks = [];
      mr.ondataavailable = (ev) => chunks.push(ev.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        const blob = new Blob(chunks, { type: "audio/webm" });
        const reader = new FileReader();
        reader.onload = async () => {
          toast.message("Mentranskrip suara...");
          try { const r = await api.post("/voice/transcribe", { audio_b64: reader.result, filename: "audio.webm" }); setInput((v) => (v ? v + " " : "") + r.data.text); refreshUser(); }
          catch (e) { toast.error("Gagal transkrip"); }
        };
        reader.readAsDataURL(blob);
      };
      mr.start(); setRecording(true);
    } catch (e) { toast.error("Mikrofon tidak tersedia"); }
  };

  const send = async () => {
    if ((!input.trim() && attachments.length === 0) || streaming || !id) return;
    const text = input; const atts = attachments;
    setInput(""); setAttachments([]);
    setMessages((m) => [...m, { id: "tmp-u-" + Date.now(), role: "user", content: text, attachments: atts.map((a) => ({ type: a.type, name: a.name })) }]);
    setStreaming(true); setLiveMap({}); setLiveOrder([]);
    try {
      await streamChatWithAtt(id, text, atts, (ev) => {
        const pid = ev.persona_id;
        if (pid && ev.start) {
          setLiveMap((prev) => ({ ...prev, [pid]: { name: ev.persona_name, portrait: ev.portrait, moderator: ev.is_moderator, text: "" } }));
          setLiveOrder((o) => (o.includes(pid) ? o : [...o, pid]));
        }
        if (pid && ev.delta !== undefined) {
          setLiveMap((prev) => { const cur = prev[pid] || { name: ev.persona_name, portrait: ev.portrait, moderator: ev.is_moderator, text: "" }; return { ...prev, [pid]: { ...cur, text: cur.text + ev.delta } }; });
        }
        if (pid && ev.final && speaker && ev.content) playTTS(ev.content, ev.voice);
        if (ev.done) refreshUser();
      });
      const r = await api.get(`/conversations/${id}/messages`);
      setMessages(r.data.messages); setLiveMap({}); setLiveOrder([]); loadConvs();
    } catch (e) { toast.error("Gagal mengirim pesan"); } finally { setStreaming(false); }
  };

  const delConv = async (c, e) => { e.stopPropagation(); await api.delete(`/conversations/${c.id}`); loadConvs(); if (c.id === id) nav("/chat"); };
  const copy = (txt) => { navigator.clipboard.writeText(txt); toast.success("Disalin"); };
  const saveMem = async (m) => { await api.post("/memory", { persona_id: m.persona_id || conv?.persona_id || null, content: m.content.slice(0, 300) }); toast.success("Disimpan ke memori"); };
  const regen = async (mid) => { setStreaming(true); try { await api.post(`/conversations/${id}/messages/${mid}/regenerate`); const mr = await api.get(`/conversations/${id}/messages`); setMessages(mr.data.messages); refreshUser(); } catch (e) { toast.error("Gagal"); } finally { setStreaming(false); } };

  const isMulti = conv && conv.type !== "private";

  const convListInner = (mobile) => (
    <div className="flex h-full flex-col p-4">
      <button onClick={() => { openModal(); if (mobile) setShowConvList(false); }} data-testid={mobile ? "new-chat-btn-mobile" : "new-chat-btn"} className="btn-grad mb-4 flex items-center justify-center gap-2 rounded-xl py-2.5 text-sm"><Plus size={16} /> {t("chat.new")}</button>
      <div className="relative mb-3">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input className="input-dark py-2 pl-9" placeholder={t("common.search")} value={q} onChange={(e) => { setQ(e.target.value); loadConvs(e.target.value); }} data-testid={mobile ? "chat-search-mobile" : "chat-search"} />
      </div>
      <div className="flex-1 space-y-1 overflow-y-auto">
        {convs.map((c) => (
          <div key={c.id} onClick={() => { nav(`/chat/${c.id}`); if (mobile) setShowConvList(false); }} data-testid={`${mobile ? "conv-m-" : "conv-"}${c.id}`}
            className={`group flex cursor-pointer items-center gap-2 rounded-xl px-3 py-2.5 text-sm ${c.id === id ? "bg-[#EEF3FF] text-[#2F6BFF]" : "text-slate-600 hover:bg-slate-50"}`}>
            {c.type === "meeting" ? <Gavel size={15} className="shrink-0" /> : c.type === "group" ? <Users size={15} className="shrink-0" /> : <User size={15} className="shrink-0" />}
            <span className="flex-1 truncate">{c.title}</span>
            <button onClick={(e) => delConv(c, e)} className="text-slate-400 transition hover:text-[#EF4444] md:opacity-0 md:group-hover:opacity-100"><Trash2 size={13} /></button>
          </div>
        ))}
        {convs.length === 0 && <p className="px-2 py-4 text-center text-xs text-slate-400">Belum ada percakapan.</p>}
      </div>
    </div>
  );

  return (
    <div className="flex h-[calc(100vh-4rem)]" data-testid="chat-page">
      <div className="hidden w-72 shrink-0 border-r border-[#E7ECF3] bg-white md:block">
        {convListInner(false)}
      </div>

      {/* mobile conversations drawer */}
      {showConvList && (
        <div className="fixed inset-0 z-[88] md:hidden" data-testid="mobile-conv-drawer">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setShowConvList(false)} />
          <div className="absolute left-0 top-0 h-full w-72 bg-white shadow-xl">
            <button className="absolute right-2 top-2 z-10 flex h-7 w-7 items-center justify-center rounded-full bg-white/90 text-slate-500 shadow" onClick={() => setShowConvList(false)}><X size={16} /></button>
            {convListInner(true)}
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col bg-[#F8FAFC]">
        <div className="flex items-center gap-2 border-b border-[#E7ECF3] bg-white px-3 py-3 sm:gap-3 sm:px-5">
          <button onClick={() => setShowConvList(true)} data-testid="mobile-conv-btn" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[#E7ECF3] text-slate-500 md:hidden"><MessageSquare size={17} /></button>
          {conv ? (
            <>
              <div className="flex -space-x-2">{(conv.members || []).slice(0, 4).map((m) => <div key={m.id} className="rounded-full ring-2 ring-white"><Avatar name={m.name} portrait={m.portrait} size={32} /></div>)}</div>
              <div className="min-w-0"><p className="truncate text-sm font-bold text-slate-900">{conv.title}</p>
                <p className="truncate text-xs text-slate-400">{conv.type === "meeting" ? `Meeting · ${conv.members?.length} asisten + Moderator` : conv.type === "group" ? `Grup · ${conv.members?.length} asisten` : "Chat privat"}</p></div>
            </>
          ) : <p className="truncate text-sm font-semibold text-slate-500">Pilih atau mulai percakapan</p>}
          {conv && (
            <div className="ml-auto flex shrink-0 items-center gap-2">
              {conv.type === "private" && <button onClick={() => setCallOpen(true)} title="Mode panggilan suara" data-testid="call-mode-btn" className="flex h-9 items-center gap-1.5 rounded-lg bg-[#10B981] px-2.5 text-xs font-semibold text-white sm:px-3"><Phone size={15} /> <span className="hidden sm:inline">Panggil</span></button>}
              {conv.type !== "private" && <button onClick={() => setVideoOpen(true)} title="Ruang video call" data-testid="video-call-btn" className="flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-xs font-semibold text-white sm:px-3" style={{ background: "linear-gradient(135deg,#2F6BFF,#7C3AED)" }}><Video size={15} /> <span className="hidden sm:inline">Video Call</span></button>}
              <button onClick={() => setSpeaker(!speaker)} title="Baca jawaban dengan suara" data-testid="speaker-toggle" className={`flex h-9 w-9 items-center justify-center rounded-lg border ${speaker ? "btn-grad border-transparent" : "border-[#E7ECF3] text-slate-500"}`}>{speaker ? <Volume2 size={16} /> : <VolumeX size={16} />}</button>
            </div>
          )}
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {!conv && (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <Bot size={44} className="mb-4 text-[#2F6BFF]" />
              <h3 className="text-lg font-bold text-slate-900">Mulai percakapan dengan tim Anda</h3>
              <p className="mt-1 max-w-sm text-sm text-slate-500">Pilih satu asisten untuk chat privat, beberapa untuk grup, atau adakan meeting.</p>
              <button onClick={openModal} className="btn-grad mt-5 rounded-xl px-6 py-3 text-sm">+ Mulai Chat</button>
            </div>
          )}
          {messages.map((m, i) => (
            m.role === "user" ? (
              <div key={m.id || i} className="flex justify-end">
                <div className="max-w-[78%] rounded-2xl rounded-tr-sm px-4 py-3 text-sm text-white" style={{ background: "linear-gradient(135deg,#2F6BFF,#7C3AED)" }} data-testid="msg-user">
                  {(m.attachments || []).length > 0 && <div className="mb-2 flex flex-wrap gap-1.5">{m.attachments.map((a, k) => <span key={k} className="flex items-center gap-1 rounded-lg bg-white/20 px-2 py-1 text-xs">{a.type === "image" ? <ImageIcon size={11} /> : <FileText size={11} />}{a.name}</span>)}</div>}
                  <p className="whitespace-pre-wrap">{m.content}</p>
                </div>
              </div>
            ) : (
              <div key={m.id || i} className="flex justify-start gap-2.5">
                <div className="mt-1 shrink-0"><Avatar name={m.persona_name} portrait={m.portrait} size={32} moderator={m.is_moderator} /></div>
                <div className="group max-w-[78%]">
                  <p className="mb-1 text-xs font-semibold text-slate-500">{m.persona_name}{m.is_moderator && " · ringkasan meeting"}</p>
                  <div className={`rounded-2xl rounded-tl-sm px-4 py-3 text-sm ${m.is_moderator ? "border border-[#2F6BFF]/30 bg-[#EEF3FF] text-slate-700" : "aivora-card text-slate-700"}`} data-testid="msg-assistant"><Markdown content={m.content} /></div>
                  <div className="mt-1.5 flex gap-3 opacity-0 transition group-hover:opacity-100">
                    <button onClick={() => copy(m.content)} className="text-slate-400 hover:text-slate-700"><Copy size={13} /></button>
                    <button onClick={() => playTTS(m.content, voiceFor(m.persona_id))} className="text-slate-400 hover:text-slate-700"><Volume2 size={13} /></button>
                    {!m.is_moderator && <button onClick={() => saveMem(m)} className="text-slate-400 hover:text-slate-700"><Bookmark size={13} /></button>}
                    {!m.is_moderator && <button onClick={() => regen(m.id)} className="text-slate-400 hover:text-slate-700"><RefreshCw size={13} /></button>}
                  </div>
                </div>
              </div>
            )
          ))}
          {liveOrder.map((pid) => {
            const l = liveMap[pid];
            return (
              <div key={pid} className="flex justify-start gap-2.5">
                <div className="mt-1 shrink-0"><Avatar name={l.name} portrait={l.portrait} size={32} moderator={l.moderator} /></div>
                <div className="max-w-[78%]">
                  <p className="mb-1 text-xs font-semibold text-slate-500">{l.name}</p>
                  <div className={`rounded-2xl rounded-tl-sm px-4 py-3 text-sm ${l.moderator ? "border border-[#2F6BFF]/30 bg-[#EEF3FF]" : "aivora-card"} text-slate-700`} data-testid="msg-streaming">
                    {l.text ? <Markdown content={l.text} /> : <span className="inline-flex gap-1"><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" /><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: ".15s" }} /><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: ".3s" }} /></span>}
                  </div>
                </div>
              </div>
            );
          })}
          <div ref={endRef} />
        </div>

        {conv && (
          <div className="border-t border-[#E7ECF3] bg-white p-4">
            {attachments.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-2">
                {attachments.map((a, k) => (
                  <span key={k} className="flex items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-1.5 text-xs text-slate-600" data-testid={`att-${k}`}>
                    {a.type === "image" ? <ImageIcon size={12} /> : <FileText size={12} />}{a.name}
                    <button onClick={() => setAttachments((p) => p.filter((_, j) => j !== k))}><X size={12} /></button>
                  </span>
                ))}
              </div>
            )}
            {isMulti && <p className="mb-2 text-xs text-slate-400">Tip: sebut @NamaAsisten untuk menuju satu asisten tertentu.</p>}
            <div className="flex items-end gap-2">
              <input ref={fileRef} type="file" multiple accept="image/*,application/pdf,.txt,.md,.csv" className="hidden" onChange={onFiles} />
              <button onClick={() => fileRef.current?.click()} data-testid="attach-btn" className="flex h-12 w-11 shrink-0 items-center justify-center rounded-xl border border-[#E7ECF3] text-slate-500 hover:bg-slate-50"><Paperclip size={18} /></button>
              <button onClick={toggleRecord} data-testid="mic-btn" className={`flex h-12 w-11 shrink-0 items-center justify-center rounded-xl border ${recording ? "animate-pulse border-[#EF4444] bg-[#EF4444] text-white" : "border-[#E7ECF3] text-slate-500 hover:bg-slate-50"}`}>{recording ? <Square size={16} /> : <Mic size={18} />}</button>
              <textarea className="input-dark max-h-32 min-h-[48px] resize-none" rows={1} placeholder={t("chat.placeholder")} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} data-testid="chat-input" />
              <button onClick={send} disabled={streaming || (!input.trim() && attachments.length === 0)} className="btn-grad flex h-12 w-12 shrink-0 items-center justify-center rounded-xl" data-testid="chat-send-btn"><Send size={18} /></button>
            </div>
          </div>
        )}
      </div>

      {callOpen && conv && <CallMode conv={conv} cid={id} onClose={() => setCallOpen(false)} onRefresh={() => { api.get(`/conversations/${id}/messages`).then((r) => setMessages(r.data.messages)).catch(() => {}); refreshUser(); }} />}

      {videoOpen && conv && <VideoRoom conv={conv} cid={id} onClose={() => setVideoOpen(false)} onRefresh={() => { api.get(`/conversations/${id}/messages`).then((r) => setMessages(r.data.messages)).catch(() => {}); refreshUser(); }} />}

      {showModal && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setShowModal(false)} />
          <div className="relative w-full max-w-md rounded-3xl border border-[#E7ECF3] bg-white p-6 shadow-2xl fade-up" data-testid="new-chat-modal">
            <button onClick={() => setShowModal(false)} className="absolute right-4 top-4 text-slate-400"><X size={18} /></button>
            <h3 className="text-lg font-bold text-slate-900">Mulai Percakapan</h3>
            <p className="mt-1 text-sm text-slate-500">Pilih 1 asisten untuk privat, atau beberapa untuk grup/meeting.</p>
            <div className="mt-4 max-h-72 space-y-2 overflow-y-auto">
              {personas.map((p) => {
                const on = picked.includes(p.id);
                return (
                  <button key={p.id} onClick={() => togglePick(p.id)} data-testid={`pick-${p.id}`} className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left transition ${on ? "border-[#2F6BFF] bg-[#EEF3FF]" : "border-[#E7ECF3] hover:bg-slate-50"}`}>
                    <Avatar name={p.name} portrait={p.portrait} size={40} />
                    <span className="min-w-0 flex-1"><span className="block truncate text-sm font-bold text-slate-900">{p.name}</span><span className="block truncate text-xs text-slate-400">{p.summary || "Persona"}</span></span>
                    <span className={`flex h-5 w-5 items-center justify-center rounded-md border ${on ? "btn-grad border-transparent" : "border-slate-300"}`}>{on && <Check size={13} />}</span>
                  </button>
                );
              })}
            </div>
            {picked.length > 1 && (
              <div className="mt-3 flex gap-2">
                {[["group", "Grup", Users], ["meeting", "Meeting", Gavel]].map(([v, l, Ic]) => (
                  <button key={v} onClick={() => setMode(v)} data-testid={`mode-${v}`} className={`flex flex-1 items-center justify-center gap-1.5 rounded-xl border py-2 text-xs font-semibold ${mode === v ? "border-[#2F6BFF] bg-[#EEF3FF] text-[#2F6BFF]" : "border-[#E7ECF3] text-slate-500"}`}><Ic size={14} /> {l}</button>
                ))}
              </div>
            )}
            <div className="mt-4 flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500">{picked.length > 1 ? `${mode === "meeting" ? "Meeting" : "Grup"} · ${picked.length} asisten` : picked.length === 1 ? "Chat privat" : "Belum dipilih"}</span>
              <button onClick={startConv} className="btn-grad rounded-xl px-6 py-2.5 text-sm" data-testid="start-conv-btn">Mulai</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CallMode({ conv, cid, onClose, onRefresh }) {
  const member = (conv.members || [])[0] || {};
  const [status, setStatus] = useState("idle"); // idle | listening | thinking | speaking
  const [level, setLevel] = useState(0); // live mic level 0..1 for the visualizer
  const recRef = useRef(null);
  const audioRef = useRef(null);
  const openRef = useRef(true);
  const acRef = useRef(null);
  const monitorRef = useRef(null);
  const streamRef = useRef(null);

  const VOICE_THRESHOLD = 0.045;      // RMS above this = speaking
  const SILENCE_AFTER_SPEECH_MS = 1400; // auto-send after this much silence following speech
  const MAX_IDLE_MS = 12000;          // no speech at all for this long -> end call

  const cleanupAudio = () => {
    if (monitorRef.current) { clearInterval(monitorRef.current); monitorRef.current = null; }
    try { acRef.current?.close(); } catch (e) {}
    acRef.current = null;
    try { streamRef.current?.getTracks().forEach((t) => t.stop()); } catch (e) {}
    streamRef.current = null;
  };

  useEffect(() => {
    openRef.current = true;
    return () => {
      openRef.current = false;
      try { recRef.current?.stop(); } catch (e) {}
      try { audioRef.current?.pause(); } catch (e) {}
      cleanupAudio();
    };
  }, []);

  const endCall = () => { openRef.current = false; try { recRef.current?.stop(); } catch (e) {} cleanupAudio(); toast.message("Panggilan diakhiri (tidak ada suara)."); onClose(); };

  const startListening = async () => {
    if (!openRef.current) return;
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
        setLevel(0);
        if (!openRef.current) return;
        setStatus("thinking");
        const blob = new Blob(chunks, { type: "audio/webm" });
        const reader = new FileReader();
        reader.onload = async () => {
          try {
            const tr = await api.post("/voice/transcribe", { audio_b64: reader.result, filename: "audio.webm" });
            const text = (tr.data.text || "").trim();
            if (!text) { if (openRef.current) startListening(); return; }
            let reply = "";
            await streamChatWithAtt(cid, text, [], (ev) => { if (ev.final && ev.content) reply = ev.content; });
            onRefresh && onRefresh();
            if (!reply) { if (openRef.current) startListening(); return; }
            setStatus("speaking");
            const res = await fetch(`${API_BASE}/voice/tts`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` }, body: JSON.stringify({ text: reply.slice(0, 1500), voice: member.voice || "nova" }) });
            const ab = await res.blob();
            const a = new Audio(URL.createObjectURL(ab)); audioRef.current = a;
            a.onended = () => { if (openRef.current) startListening(); };
            a.play();
          } catch (e) { if (openRef.current) startListening(); }
        };
        reader.readAsDataURL(blob);
      };
      mr.start(); setStatus("listening");

      // --- Voice Activity Detection on the same stream ---
      const AC = window.AudioContext || window.webkitAudioContext;
      const ac = new AC(); acRef.current = ac;
      const src = ac.createMediaStreamSource(stream);
      const analyser = ac.createAnalyser(); analyser.fftSize = 1024;
      src.connect(analyser);
      const buf = new Uint8Array(analyser.fftSize);
      const startedAt = Date.now();
      let speechStarted = false;
      let lastVoiceAt = Date.now();
      monitorRef.current = setInterval(() => {
        if (!openRef.current) return;
        analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (let i = 0; i < buf.length; i++) { const d = (buf[i] - 128) / 128; sum += d * d; }
        const rms = Math.sqrt(sum / buf.length);
        setLevel(Math.min(1, rms * 6));
        const now = Date.now();
        if (rms > VOICE_THRESHOLD) { speechStarted = true; lastVoiceAt = now; }
        // End the call if the user never speaks for a while
        if (!speechStarted && now - startedAt > MAX_IDLE_MS) { endCall(); return; }
        // Auto-send once the user has spoken and then goes silent
        if (speechStarted && now - lastVoiceAt > SILENCE_AFTER_SPEECH_MS) {
          if (monitorRef.current) { clearInterval(monitorRef.current); monitorRef.current = null; }
          try { mr.state !== "inactive" && mr.stop(); } catch (e) {}
        }
      }, 120);
    } catch (e) { setStatus("idle"); }
  };

  useEffect(() => { startListening(); /* auto start */ /* eslint-disable-next-line */ }, []);

  const sendNow = () => { if (monitorRef.current) { clearInterval(monitorRef.current); monitorRef.current = null; } try { recRef.current?.state !== "inactive" && recRef.current?.stop(); } catch (e) {} };
  const label = {
    idle: "Menyiapkan mikrofon...",
    listening: "Mendengarkan — bicara, saya kirim otomatis saat Anda berhenti",
    thinking: "Memproses...",
    speaking: "Berbicara...",
  }[status];

  const ringScale = status === "listening" ? 1 + level * 0.18 : 1;

  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center p-4" data-testid="call-mode-overlay">
      <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm" />
      <div className="relative w-full max-w-sm rounded-3xl border border-[#E7ECF3] bg-white p-6 text-center shadow-2xl fade-up sm:p-8">
        <p className="mb-5 text-xs font-semibold uppercase tracking-widest text-[#10B981]">Panggilan suara</p>
        <div className={`mx-auto mb-5 h-28 w-28 overflow-hidden rounded-full transition-transform ${status === "listening" ? "glow-ring" : ""}`} style={{ border: "3px solid #10B981", transform: `scale(${ringScale})` }}>
          {member.portrait ? <img src={member.portrait} alt="" className="h-full w-full object-cover" /> : <span className="flex h-full w-full items-center justify-center text-3xl font-bold text-white" style={{ background: "linear-gradient(135deg,#2F6BFF,#7C3AED)" }}>{(member.name || "?")[0]}</span>}
        </div>
        <h2 className="truncate text-2xl font-bold text-slate-900">{member.name}</h2>
        <p className="mx-auto mt-2 min-h-[2.5rem] max-w-[17rem] text-sm text-slate-500">{label}</p>
        <div className="mt-6 flex items-center justify-center gap-6">
          <button onClick={sendNow} disabled={status !== "listening"} data-testid="call-send-turn" title="Kirim sekarang" className="flex h-14 w-14 items-center justify-center rounded-full bg-[#2F6BFF] text-white transition disabled:opacity-40"><Send size={22} /></button>
          <button onClick={() => { openRef.current = false; cleanupAudio(); onClose(); }} data-testid="call-hangup" title="Akhiri panggilan" className="flex h-16 w-16 items-center justify-center rounded-full bg-[#EF4444] text-white transition hover:brightness-105"><PhoneOff size={26} /></button>
        </div>
      </div>
    </div>
  );
}
