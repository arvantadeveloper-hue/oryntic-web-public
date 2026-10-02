import React, { useEffect, useRef, useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { Plus, Send, Search, Trash2, Copy, RefreshCw, Bookmark, Users, User, X, Check, Bot, Paperclip, Mic, Square, Volume2, VolumeX, FileText, Image as ImageIcon, Gavel, Phone, PhoneOff, MessageSquare, Video, UserPlus, Link as LinkIcon, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, API_BASE, getToken, streamChatWithAtt, openConvSocket } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n";
import { Markdown } from "../components/Markdown";
import { VideoRoom } from "../components/VideoRoom";
import { RealtimeCall } from "../components/RealtimeCall";
import { RealtimeMeeting } from "../components/RealtimeMeeting";
import { MediaList, ToolRequestCard, ModelBadge } from "../components/MessageExtras";
import { useRealtimeStatus } from "../hooks/useRealtimeStatus";

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
  const location = useLocation();
  const { refreshUser, user } = useAuth();
  const { t } = useI18n();
  const isAdmin = user?.role === "admin";
  const rt = useRealtimeStatus();
  const [convs, setConvs] = useState([]);
  const [q, setQ] = useState("");
  const [conv, setConv] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [liveMap, setLiveMap] = useState({});
  const [liveOrder, setLiveOrder] = useState([]);
  const [personas, setPersonas] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [picked, setPicked] = useState([]);
  const [mode, setMode] = useState("chat");
  const [attachments, setAttachments] = useState([]);
  const [recording, setRecording] = useState(false);
  const [speaker, setSpeaker] = useState(false);
  const [videoOpen, setVideoOpen] = useState(false);
  const [showConvList, setShowConvList] = useState(false);
  const [showInvite, setShowInvite] = useState(false);
  const [wsUsers, setWsUsers] = useState([]);
  const streamingRef = useRef(false);
  const endRef = useRef(null);
  const fileRef = useRef(null);
  const recRef = useRef(null);
  const audioRef = useRef(null);

  useEffect(() => { streamingRef.current = streaming; }, [streaming]);

  const loadConvs = (query = "") => api.get(`/conversations${query ? `?q=${encodeURIComponent(query)}` : ""}`).then((r) => setConvs(r.data)).catch(() => {});
  useEffect(() => { loadConvs(); api.get("/personas").then((r) => setPersonas(r.data)).catch(() => {}); }, [user?.id]);
  useEffect(() => {
    if (id) api.get(`/conversations/${id}/messages`).then((r) => {
      setConv(r.data.conversation); setMessages(r.data.messages);
      if (location.state?.openMeeting) { setVideoOpen(true); nav(location.pathname, { replace: true, state: {} }); }
    }).catch(() => {});
    else { setConv(null); setMessages([]); setVideoOpen(false); }
    const pre = sessionStorage.getItem("aivora_prefill");
    if (pre && id) { setInput(pre); sessionStorage.removeItem("aivora_prefill"); }
  }, [id]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, liveMap]);

  // realtime: other humans' and AI messages in shared meetings/groups
  useEffect(() => {
    if (!id) return;
    let ws;
    try {
      ws = openConvSocket(id, (ev) => {
        if ((ev.type === "message" || ev.type === "participants") && !streamingRef.current) {
          api.get(`/conversations/${id}/messages`).then((r) => { setConv(r.data.conversation); setMessages(r.data.messages); }).catch(() => {});
        }
      });
    } catch (e) {}
    return () => { try { ws && ws.close(); } catch (e) {} };
  }, [id]);

  const openModal = (m = "chat") => {
    if (personas === null) return;
    if (personas.length === 0) { toast.message(isAdmin ? "Buat agen AI dulu untuk memulai percakapan" : "Belum ada agen AI di workspace ini"); if (isAdmin) nav("/personas/new"); return; }
    setPicked([]); setMode(m); setShowModal(true);
  };
  const togglePick = (pid) => setPicked((p) => p.includes(pid) ? p.filter((x) => x !== pid) : [...p, pid]);
  const startConv = async () => {
    if (picked.length === 0) { toast.error("Pilih minimal satu persona"); return; }
    const type = mode === "meeting" ? "meeting" : picked.length > 1 ? "group" : "private";
    const r = await api.post("/conversations", { persona_ids: picked, type });
    setShowModal(false); loadConvs();
    nav(`/chat/${r.data.id}`, { state: { openMeeting: mode === "meeting" } });
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
      if (audioRef.current) { try { audioRef.current.pause(); URL.revokeObjectURL(audioRef.current.src); } catch (e) {} }
      const a = new Audio(URL.createObjectURL(blob)); audioRef.current = a;
      a.onended = () => { try { URL.revokeObjectURL(a.src); } catch (e) {} };
      a.play();
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
        if (pid && ev.status) {
          setLiveMap((prev) => { const cur = prev[pid] || { name: ev.persona_name, portrait: ev.portrait, moderator: ev.is_moderator, text: "" }; return { ...prev, [pid]: { ...cur, status: ev.status } }; });
        }
        if (pid && ev.delta !== undefined) {
          setLiveMap((prev) => { const cur = prev[pid] || { name: ev.persona_name, portrait: ev.portrait, moderator: ev.is_moderator, text: "" }; return { ...prev, [pid]: { ...cur, status: "", text: cur.text + ev.delta } }; });
        }
        if (pid && ev.final && speaker && ev.content) playTTS(ev.content, ev.voice);
        if (ev.done) refreshUser();
      });
      const r = await api.get(`/conversations/${id}/messages`);
      setMessages(r.data.messages); setLiveMap({}); setLiveOrder([]); loadConvs();
    } catch (e) { toast.error(e?.detail || (e?.status === 429 ? "Terlalu banyak pesan, tunggu sebentar." : e?.status === 402 ? "Kuota kredit harian habis." : "Gagal mengirim pesan")); } finally { setStreaming(false); }
  };

  const delConv = async (c, e) => { e.stopPropagation(); await api.delete(`/conversations/${c.id}`); loadConvs(); if (c.id === id) nav("/chat"); };
  const refreshMsgs = () => { refreshUser(); return api.get(`/conversations/${id}/messages`).then((r) => setMessages(r.data.messages)).catch(() => {}); };
  const copy = (txt) => { navigator.clipboard.writeText(txt); toast.success("Disalin"); };
  const saveMem = async (m) => { await api.post("/memory", { persona_id: m.persona_id || conv?.persona_id || null, content: m.content.slice(0, 300) }); toast.success("Disimpan ke memori"); };
  const regen = async (mid) => { setStreaming(true); try { await api.post(`/conversations/${id}/messages/${mid}/regenerate`); const mr = await api.get(`/conversations/${id}/messages`); setMessages(mr.data.messages); refreshUser(); } catch (e) { toast.error("Gagal"); } finally { setStreaming(false); } };

  const [savingNotes, setSavingNotes] = useState(false);
  const saveNotes = async () => {
    setSavingNotes(true);
    try {
      await api.post(`/conversations/${id}/summary`);
      const r = await api.get(`/conversations/${id}/messages`); setMessages(r.data.messages); refreshUser();
      toast.success("Notulen tersimpan di Ruang Kerja");
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat notulen"); } finally { setSavingNotes(false); }
  };

  const openInvite = () => { api.get("/admin/workspace-users").then((r) => setWsUsers(r.data)).catch(() => {}); setShowInvite(true); };
  const invite = async (uid) => {
    try { await api.post(`/conversations/${id}/participants`, { user_ids: [uid] }); toast.success("Pengguna diundang"); api.get(`/conversations/${id}/messages`).then((r) => setConv(r.data.conversation)); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengundang"); }
  };

  const isMulti = conv && conv.type !== "private";

  const convListInner = (mobile) => (
    <div className="flex h-full flex-col p-4">
      <button onClick={() => { openModal(); if (mobile) setShowConvList(false); }} data-testid={mobile ? "new-chat-btn-mobile" : "new-chat-btn"} className="btn-grad mb-2 flex items-center justify-center gap-2 rounded-xl py-2.5 text-sm"><Plus size={16} /> {t("chat.new")}</button>
      <button onClick={() => { openModal("meeting"); if (mobile) setShowConvList(false); }} data-testid={mobile ? "new-meeting-btn-mobile" : "new-meeting-btn"} className="mb-4 flex items-center justify-center gap-2 rounded-xl border border-[#2F6BFF]/40 py-2.5 text-sm font-semibold text-[#2F6BFF] transition hover:bg-[#EEF3FF]"><Video size={16} /> Meeting Baru</button>
      <div className="relative mb-3">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input className="input-dark py-2 pl-9" placeholder={t("common.search")} value={q} onChange={(e) => { setQ(e.target.value); loadConvs(e.target.value); }} data-testid={mobile ? "chat-search-mobile" : "chat-search"} />
      </div>
      <div className="flex-1 space-y-1 overflow-y-auto">
        {convs.map((c) => (
          <div key={c.id} onClick={() => { nav(`/chat/${c.id}`); if (mobile) setShowConvList(false); }} data-testid={`${mobile ? "conv-m-" : "conv-"}${c.id}`}
            className={`group flex cursor-pointer items-center gap-2 rounded-xl px-3 py-2.5 text-sm ${c.id === id ? "bg-[#EEF3FF] text-[#2F6BFF]" : "text-slate-600 hover:bg-slate-50"}`}>
            {c.type === "meeting" ? <Video size={15} className="shrink-0" /> : c.type === "group" ? <Users size={15} className="shrink-0" /> : <User size={15} className="shrink-0" />}
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
                <p className="truncate text-xs text-slate-400">{conv.type === "meeting" ? `Meeting · ${conv.members?.length} asisten${(conv.members?.length || 0) > 1 ? " + Moderator" : ""}` : conv.type === "group" ? `Chat grup · ${conv.members?.length} asisten` : "Chat privat"}</p></div>
            </>
          ) : <p className="truncate text-sm font-semibold text-slate-500">Pilih atau mulai percakapan</p>}
          {conv && (
            <div className="ml-auto flex shrink-0 items-center gap-2">
              {conv.type === "private" && <button onClick={() => setVideoOpen(true)} title={rt.enabled ? "Panggilan suara realtime" : "Mode panggilan suara"} data-testid="call-mode-btn" className="flex h-9 items-center gap-1.5 rounded-lg bg-[#10B981] px-2.5 text-xs font-semibold text-white sm:px-3"><Phone size={15} /> <span className="hidden sm:inline">Panggil{rt.enabled ? " · Realtime" : ""}</span></button>}
              {conv.type !== "private" && <button onClick={() => setVideoOpen(true)} title="Masuk ruang meeting" data-testid="video-call-btn" className="flex h-9 items-center gap-1.5 rounded-lg bg-[#2F6BFF] px-2.5 text-xs font-semibold text-white sm:px-3"><Video size={15} /> <span className="hidden sm:inline">Masuk Meeting</span></button>}
              {conv.type !== "private" && <button onClick={saveNotes} disabled={savingNotes} title="Buat & simpan notulen ke Ruang Kerja" data-testid="save-notes-btn" className="flex h-9 items-center gap-1.5 rounded-lg border border-[#E6EAF2] bg-white px-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50 sm:px-3">{savingNotes ? <RefreshCw size={15} className="animate-spin" /> : <FileText size={15} />} <span className="hidden sm:inline">Notulen</span></button>}
              {conv.type === "meeting" && isAdmin && <button onClick={openInvite} title="Undang pengguna" data-testid="invite-user-btn" className="flex h-9 items-center gap-1.5 rounded-lg border border-[#2F6BFF]/40 px-2.5 text-xs font-semibold text-[#2F6BFF] sm:px-3"><UserPlus size={15} /> <span className="hidden sm:inline">Undang</span></button>}
              <button onClick={() => setSpeaker(!speaker)} title="Baca jawaban dengan suara" data-testid="speaker-toggle" className={`flex h-9 w-9 items-center justify-center rounded-lg border ${speaker ? "btn-grad border-transparent" : "border-[#E7ECF3] text-slate-500"}`}>{speaker ? <Volume2 size={16} /> : <VolumeX size={16} />}</button>
            </div>
          )}
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {!conv && (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <Bot size={44} className="mb-4 text-[#2F6BFF]" />
              <h3 className="text-lg font-bold text-slate-900">Mulai percakapan dengan tim Anda</h3>
              <p className="mt-1 max-w-sm text-sm text-slate-500">Pilih satu atau beberapa asisten untuk chat teks, atau langsung masuk ruang meeting suara.</p>
              <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
                <button onClick={() => openModal()} data-testid="empty-new-chat-btn" className="btn-grad rounded-xl px-6 py-3 text-sm">+ Mulai Chat</button>
                <button onClick={() => openModal("meeting")} data-testid="empty-new-meeting-btn" className="flex items-center gap-2 rounded-xl border border-[#2F6BFF]/40 px-6 py-3 text-sm font-semibold text-[#2F6BFF] transition hover:bg-[#EEF3FF]"><Video size={16} /> Meeting Baru</button>
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            m.role === "user" ? (
              <div key={m.id || i} className="flex flex-col items-end">
                {isMulti && m.sender_user_id && m.sender_user_id !== user?.id && <p className="mb-1 mr-1 text-xs font-semibold text-slate-500">{m.sender_name}</p>}
                <div className="max-w-[78%] rounded-2xl rounded-tr-sm px-4 py-3 text-sm text-white" style={{ background: "linear-gradient(135deg,#2F6BFF,#7C3AED)" }} data-testid="msg-user">
                  {(m.attachments || []).length > 0 && <div className="mb-2 flex flex-wrap gap-1.5">{m.attachments.map((a, k) => <span key={k} className="flex items-center gap-1 rounded-lg bg-white/20 px-2 py-1 text-xs">{a.type === "image" ? <ImageIcon size={11} /> : <FileText size={11} />}{a.name}</span>)}</div>}
                  <p className="whitespace-pre-wrap">{m.content}</p>
                </div>
              </div>
            ) : (
              <div key={m.id || i} className="flex justify-start gap-2.5">
                <div className="mt-1 shrink-0"><Avatar name={m.persona_name} portrait={m.portrait} size={32} moderator={m.is_moderator} /></div>
                <div className="group max-w-[78%]">
                  <p className="mb-1 text-xs font-semibold text-slate-500">{m.persona_name}{m.is_moderator && " · moderator"}</p>
                  <div className={`rounded-2xl rounded-tl-sm px-4 py-3 text-sm ${m.is_moderator ? "border border-[#2F6BFF]/30 bg-[#EEF3FF] text-slate-700" : "aivora-card text-slate-700"}`} data-testid="msg-assistant">
                    <Markdown content={m.content} />
                    <MediaList media={m.media || []} />
                    <ToolRequestCard m={m} cid={id} onDone={refreshMsgs} />
                  </div>
                  <ModelBadge m={m} />
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
                    {l.status ? <span className="flex items-center gap-2 text-slate-500" data-testid="msg-streaming-status"><Loader2 size={13} className="animate-spin" /> {l.status}</span> : l.text ? <Markdown content={l.text} /> : <span className="inline-flex gap-1"><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" /><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: ".15s" }} /><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: ".3s" }} /></span>}
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

      {videoOpen && conv && (conv.type === "private" && rt.enabled
        ? <RealtimeCall conv={conv} cid={id} messages={messages} onClose={() => setVideoOpen(false)} onRefresh={refreshMsgs} />
        : conv.type !== "private" && rt.enabled
        ? <RealtimeMeeting conv={conv} cid={id} messages={messages} onClose={() => setVideoOpen(false)} onRefresh={refreshMsgs} />
        : <VideoRoom conv={conv} cid={id} messages={messages} isPrivate={conv.type === "private"} onClose={() => setVideoOpen(false)} onRefresh={refreshMsgs} />)}

      {showInvite && conv && (
        <div className="fixed inset-0 z-[92] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setShowInvite(false)} />
          <div className="relative w-full max-w-md rounded-3xl border border-[#E7ECF3] bg-white p-6 shadow-2xl fade-up" data-testid="invite-modal">
            <button onClick={() => setShowInvite(false)} className="absolute right-4 top-4 text-slate-400"><X size={18} /></button>
            <h3 className="text-lg font-bold text-slate-900">Undang ke Meeting</h3>
            <p className="mt-1 text-sm text-slate-500">Pilih pengguna workspace untuk bergabung ke rapat ini secara real-time.</p>
            <button onClick={async () => { try { const r = await api.post(`/conversations/${id}/invite-link`); const url = `${window.location.origin}${r.data.path}`; try { await navigator.clipboard.writeText(url); } catch (e) {} toast.success("Tautan undangan disalin"); } catch (e) { toast.error("Gagal membuat tautan"); } }} data-testid="copy-invite-link-btn" className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-[#2F6BFF]/40 py-2.5 text-sm font-semibold text-[#2F6BFF] hover:bg-[#EEF3FF]"><LinkIcon size={15} /> Salin Tautan Undangan Sekali Klik</button>
            <div className="mt-4 max-h-80 space-y-2 overflow-y-auto">
              {wsUsers.filter((wu) => !wu.is_admin).map((wu) => {
                const joined = (conv.participants || []).includes(wu.id);
                return (
                  <div key={wu.id} className="flex items-center gap-3 rounded-xl border border-[#E7ECF3] p-3" data-testid={`invite-row-${wu.email}`}>
                    <span className="flex h-9 w-9 items-center justify-center rounded-full text-sm font-bold text-white" style={{ background: "linear-gradient(135deg,#2F6BFF,#7C3AED)" }}>{(wu.name || "U")[0].toUpperCase()}</span>
                    <span className="min-w-0 flex-1"><span className="block truncate text-sm font-bold text-slate-900">{wu.name}</span><span className="block truncate text-xs text-slate-400">{wu.email}</span></span>
                    {joined ? <span className="text-xs font-semibold text-[#10B981]">Bergabung</span>
                      : <button onClick={() => invite(wu.id)} data-testid={`invite-btn-${wu.email}`} className="btn-grad rounded-lg px-3 py-1.5 text-xs">Undang</button>}
                  </div>
                );
              })}
              {wsUsers.filter((wu) => !wu.is_admin).length === 0 && <p className="py-4 text-center text-xs text-slate-400">Belum ada pengguna. Tambah di menu Tim.</p>}
            </div>
          </div>
        </div>
      )}

      {showModal && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setShowModal(false)} />
          <div className="relative w-full max-w-md rounded-3xl border border-[#E7ECF3] bg-white p-6 shadow-2xl fade-up" data-testid="new-chat-modal">
            <button onClick={() => setShowModal(false)} className="absolute right-4 top-4 text-slate-400"><X size={18} /></button>
            <h3 className="text-lg font-bold text-slate-900">{mode === "meeting" ? "Meeting Baru" : "Chat Baru"}</h3>
            <p className="mt-1 text-sm text-slate-500">{mode === "meeting" ? "Pilih satu atau lebih asisten. Ruang meeting langsung terbuka setelah Anda menekan Mulai." : "Pilih satu atau lebih asisten untuk diajak chat."}</p>
            <div className="mt-4 max-h-72 space-y-2 overflow-y-auto">
              {(personas || []).map((p) => {
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
            <div className="mt-4 flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500">{picked.length === 0 ? "Belum dipilih" : mode === "meeting" ? `Meeting · ${picked.length} asisten` : picked.length > 1 ? `Chat grup · ${picked.length} asisten` : "Chat privat"}</span>
              <button onClick={startConv} className="btn-grad flex items-center gap-2 rounded-xl px-6 py-2.5 text-sm" data-testid="start-conv-btn">{mode === "meeting" && <Video size={15} />} {mode === "meeting" ? "Mulai Meeting" : "Mulai"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
