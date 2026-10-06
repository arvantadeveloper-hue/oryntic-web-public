import React, { useEffect, useRef, useState } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { Send, Search, Trash2, RefreshCw, Users, X, Check, Bot, Paperclip, Mic, Square, Volume2, VolumeX, FileText, Image as ImageIcon, Gavel, Phone, MessageSquare, Video, Loader2, Images, ExternalLink, HardDrive, Reply, Forward, CornerUpLeft } from "lucide-react";
import { toast } from "sonner";
import { api, API_BASE, getToken, streamChatWithAtt, openConvSocket } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { onUserEvent } from "../lib/userEvents";
import { useI18n } from "../i18n";
import { Markdown } from "../components/Markdown";
import { VideoRoom } from "../components/VideoRoom";
import { RealtimeCall } from "../components/RealtimeCall";
import { RealtimeMeeting } from "../components/RealtimeMeeting";
import { MediaList, ToolRequestCard, ModelBadge, RenderingBox, MessageCta, downloadUrl } from "../components/MessageExtras";
import { GalleryPicker } from "../components/GalleryPicker";
import { DrivePicker } from "../components/DrivePicker";
import { SummaryPrompt } from "../components/ConversationTools";
import { ChatArchivesModal } from "../components/ChatArchives";
import { useRealtimeStatus } from "../hooks/useRealtimeStatus";
import { TaskContextCard, AddPersonaMenu, TaskOfferButtons, WorkspaceResults, ArchiveResults } from "../components/TaskChatTools";
import { TaskCard, TaskSidePanel } from "../components/TaskPanel";

function Avatar({ name, portrait, size = 32, moderator }) {
  if (moderator) return <span className="flex items-center justify-center rounded-full bg-[#0B132B] text-white" style={{ width: size, height: size }}><Gavel size={size * 0.5} /></span>;
  if (portrait) return <img src={portrait} alt={name} className="rounded-full object-cover" style={{ width: size, height: size }} />;
  return <span className="flex items-center justify-center rounded-full font-bold text-white" style={{ width: size, height: size, fontSize: size * 0.42, background: "linear-gradient(135deg,#2F6BFF,#7C3AED)" }}>{(name || "?")[0].toUpperCase()}</span>;
}

const fileToData = (file) => new Promise((res) => {
  const r = new FileReader();
  r.onload = () => res(r.result);
  if (file.type.startsWith("image/") || file.type === "application/pdf" || /\.pdf$/i.test(file.name)) r.readAsDataURL(file);
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
  const cacheKey = `oryntix_chatlist_${user?.id || "anon"}`;
  const cached = useRef(null);
  if (cached.current === null) { try { cached.current = JSON.parse(localStorage.getItem(cacheKey) || "null") || {}; } catch (e) { cached.current = {}; } }
  const [convs, setConvs] = useState(cached.current.convs || []);
  const [msgHasMore, setMsgHasMore] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [archivedCount, setArchivedCount] = useState(0);
  const [summaryRequest, setSummaryRequest] = useState(false);
  const [showArchive, setShowArchive] = useState(false);
  const listRef = useRef(null);
  const [q, setQ] = useState("");
  const [conv, setConv] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [activeStreams, setActiveStreams] = useState(0);
  const streaming = activeStreams > 0;
  const [cooldown, setCooldown] = useState(0); // seconds left after a 429 (message throttling)
  useEffect(() => { if (cooldown <= 0) return undefined; const t = setTimeout(() => setCooldown((c) => c - 1), 1000); return () => clearTimeout(t); }, [cooldown]);
  const [liveMap, setLiveMap] = useState({});
  const [personas, setPersonas] = useState(cached.current.personas || null);
  const [friends, setFriends] = useState(cached.current.friends || []);
  // persist the chat list (conversations, assistants, friends) so the page paints instantly on the next visit (long strings such as base64 portraits are dropped to stay within the storage quota)
  useEffect(() => {
    if (!user?.id) return;
    const slim = (v) => Array.isArray(v) ? v.map(slim) : v && typeof v === "object" ? Object.fromEntries(Object.entries(v).filter(([, x]) => !(typeof x === "string" && x.length > 1500)).map(([k, x]) => [k, slim(x)])) : v;
    try { localStorage.setItem(cacheKey, JSON.stringify({ convs: slim(convs.slice(0, 200)), personas: slim(personas), friends: slim(friends), at: Date.now() })); } catch (e) {}
  }, [convs, personas, friends, cacheKey, user?.id]);
  const [pickedFriends, setPickedFriends] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [picked, setPicked] = useState([]);
  const [mode, setMode] = useState("chat");
  const [attachments, setAttachments] = useState([]);
  const [replyTo, setReplyTo] = useState(null);
  const [forwardMsg, setForwardMsg] = useState(null);
  const [recording, setRecording] = useState(false);
  const [speaker, setSpeaker] = useState(false);
  const [videoOpen, setVideoOpen] = useState(false);
  const [showConvList, setShowConvList] = useState(false);
  const [showGallery, setShowGallery] = useState(false);
  const [showDrive, setShowDrive] = useState(false);
  const [panelTask, setPanelTask] = useState(null);
  // /workspace/<id> links inside messages open the side panel instead of leaving the chat
  const onListClick = (e) => {
    const a = e.target.closest && e.target.closest("a[href]");
    if (!a) return;
    const mt = (a.getAttribute("href") || "").match(/\/workspace\/([\w-]+)/);
    if (mt && !a.getAttribute("href").includes("/api/")) { e.preventDefault(); e.stopPropagation(); setPanelTask(mt[1]); }
  };
  const [driveOn, setDriveOn] = useState(false);
  useEffect(() => { api.get("/integrations/google/status").then((r) => setDriveOn(!!r.data.connected)).catch(() => setDriveOn(false)); }, []);
  const [convsLoading, setConvsLoading] = useState(!(cached.current.convs || []).length);
  const [msgsLoading, setMsgsLoading] = useState(false);
  const streamingRef = useRef(false);
  const endRef = useRef(null);
  const fileRef = useRef(null);
  const recRef = useRef(null);
  const audioRef = useRef(null);

  useEffect(() => { streamingRef.current = streaming; }, [streaming]);

  const PAGE = 200;
  useEffect(() => { const h = () => { if (id) refreshMsgs(); }; window.addEventListener("oryntix:task-done", h); return () => window.removeEventListener("oryntix:task-done", h); /* eslint-disable-next-line */ }, [id]);
  const loadConvs = (query = "", more = false) => {
    setConvsLoading(true);
    return api.get(`/conversations?limit=${PAGE}&offset=${more ? convs.length : 0}${query ? `&q=${encodeURIComponent(query)}` : ""}`)
      .then((r) => { setConvs((prev) => (more ? [...prev, ...r.data] : r.data)); }).catch(() => {}).finally(() => setConvsLoading(false));
  };
  const applyPage = (data) => { setMessages(data.messages); setMsgHasMore(!!data.has_more); setArchivedCount(data.archives_count || 0); setSummaryRequest(!!data.long_chat); };
  const loadOlder = async () => {
    if (!msgHasMore || loadingOlder || !messages.length) return;
    setLoadingOlder(true);
    const el = listRef.current; const prevH = el ? el.scrollHeight : 0;
    try {
      const r = await api.get(`/conversations/${id}/messages?limit=50&before=${encodeURIComponent(messages[0].created_at)}`);
      skipScroll.current = true;
      setMessages((m) => [...r.data.messages, ...m]); setMsgHasMore(!!r.data.has_more);
      requestAnimationFrame(() => { if (el) el.scrollTop = el.scrollHeight - prevH; });
    } catch (e) {} finally { setLoadingOlder(false); }
  };
  useEffect(() => { loadConvs(); api.get("/personas").then((r) => setPersonas(r.data)).catch(() => {}); api.get("/friends").then((r) => setFriends(r.data.friends || [])).catch(() => {}); }, [user?.id]);
  useEffect(() => {
    if (id) { setMsgsLoading(true); setMessages([]); api.get(`/conversations/${id}/messages?limit=50`).then((r) => {
      setConv(r.data.conversation); applyPage(r.data);
      if (location.state?.openMeeting) { setVideoOpen(true); nav(location.pathname, { replace: true, state: {} }); }
    }).catch(() => {}).finally(() => setMsgsLoading(false)); }
    else { setConv(null); setMessages([]); setVideoOpen(false); }
    const pre = sessionStorage.getItem("aivora_prefill");
    if (pre && id) { setInput(pre); sessionStorage.removeItem("aivora_prefill"); }
  }, [id]);
  const skipScroll = useRef(false);
  useEffect(() => { if (skipScroll.current) { skipScroll.current = false; return; } endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, liveMap]);

  // realtime: messages arrive over the conversation WebSocket with their full payload → upsert locally (no GET per event)
  const convWs = useRef(null);
  const upsertMsg = (msg) => {
    if (!msg || !msg.id) return;
    setMessages((prev) => {
      const i = prev.findIndex((m) => m.id === msg.id);
      if (i >= 0) { const next = prev.slice(); next[i] = { ...prev[i], ...msg }; return next; }
      if (msg.role === "user" && msg.sender_user_id === user?.id) {
        const t = prev.findIndex((m) => String(m.id).startsWith("tmp-u-") && m.content === msg.content);
        if (t >= 0) { const next = prev.slice(); next[t] = msg; return next; }
      }
      return [...prev, msg].sort((a, b) => String(a.created_at || "").localeCompare(String(b.created_at || "")));
    });
    if (msg.role === "assistant" && msg.persona_id) {
      // the final message replaces the oldest live bubble of that persona
      setLiveMap((prev) => { const k = Object.keys(prev).find((key) => prev[key].pid === msg.persona_id); if (!k) return prev; const { [k]: _gone, ...rest } = prev; return rest; });
    }
  };
  useEffect(() => {
    if (!id) return;
    let ws;
    try {
      ws = openConvSocket(id, (ev) => {
        if (ev.type === "message" && ev.message) { upsertMsg(ev.message); return; }
        if ((ev.type === "message" || ev.type === "participants") && !streamingRef.current) {
          api.get(`/conversations/${id}/messages`).then((r) => { setConv(r.data.conversation); setMessages(r.data.messages); }).catch(() => {});
        }
      });
      convWs.current = ws;
    } catch (e) {}
    return () => { convWs.current = null; try { ws && ws.close(); } catch (e) {} };
    /* eslint-disable-next-line */
  }, [id]);
  useEffect(() => { const off = onUserEvent(["message_new"], () => loadConvs()); return off; /* eslint-disable-next-line */ }, []);

  const openModal = (m = "group") => {
    if (personas === null) return;
    if (personas.length === 0) { toast.message(isAdmin ? "Buat agen AI dulu untuk memulai percakapan" : "Belum ada agen AI di workspace ini"); if (isAdmin) nav("/personas/new"); return; }
    setPicked([]); setMode(m); setShowModal(true);
  };
  const openDirect = async (pid, mobile) => {
    try { const r = await api.post("/conversations/direct", { persona_id: pid }); if (mobile) setShowConvList(false); nav(`/chat/${r.data.id}`); loadConvs(); }
    catch (e) { toast.error("Gagal membuka chat"); }
  };
  const directOf = (pid) => convs.find((c) => c.type === "private" && (c.persona_ids || [])[0] === pid);
  const fmtTime = (iso) => { if (!iso) return ""; const d = new Date(iso); const today = new Date().toDateString() === d.toDateString(); return today ? d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }) : d.toLocaleDateString("id-ID", { day: "numeric", month: "short" }); };
  useEffect(() => { if (id) { api.post(`/conversations/${id}/read`).then(() => window.dispatchEvent(new Event("oryntix:badges"))).catch(() => {}); setConvs((cs) => cs.map((c) => (c.id === id ? { ...c, unread: false } : c))); } }, [id, messages.length]);
  const togglePick = (pid) => setPicked((p) => p.includes(pid) ? p.filter((x) => x !== pid) : [...p, pid]);
  const [groupTitle, setGroupTitle] = useState("");
  const canCreate = picked.length + pickedFriends.length >= 2 && (picked.length > 0 || pickedFriends.length > 0);
  const startConv = async () => {
    if (!canCreate) { toast.error("Pilih minimal dua anggota (asisten dan/atau teman)"); return; }
    try {
      const r = await api.post("/conversations", { persona_ids: picked, participant_ids: pickedFriends, type: "group", title: groupTitle.trim() || undefined });
      setShowModal(false); setGroupTitle(""); setPickedFriends([]); loadConvs();
      nav(`/chat/${r.data.id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat grup"); }
  };
  const dmOf = (fid) => convs.find((c) => c.type === "dm" && (c.participants || []).includes(fid));
  const openFriend = async (f, mobile) => {
    try { const r = await api.post(`/friends/${f.id}/chat`); if (mobile) setShowConvList(false); nav(`/chat/${r.data.id}`); loadConvs(); }
    catch (e) { toast.error("Gagal membuka chat"); }
  };

  const onFiles = async (e) => {
    const files = Array.from(e.target.files || []);
    const out = [];
    for (const f of files.slice(0, 5)) {
      if (f.size > 8 * 1024 * 1024) { toast.error(`${f.name}: maksimal 8 MB`); continue; }
      const isPdf = f.type === "application/pdf" || /\.pdf$/i.test(f.name);
      const type = f.type.startsWith("image/") ? "image" : isPdf ? "pdf" : "text";
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
    if ((!input.trim() && attachments.length === 0) || !id || cooldown > 0) return;
    const text = input; const atts = attachments; const quote = replyTo;
    const reqId = Date.now().toString(36);
    setInput(""); setAttachments([]); setReplyTo(null);
    setMessages((m) => [...m, { id: "tmp-u-" + reqId, role: "user", content: text, reply_to: quote || undefined, created_at: new Date().toISOString(), attachments: atts.map((a) => ({ type: a.type, name: a.name })) }]);
    setActiveStreams((n) => n + 1);
    const key = (pid) => `${reqId}:${pid}`;
    const keys = new Set();
    try {
      await streamChatWithAtt(id, text, atts, (ev) => {
        const pid = ev.persona_id;
        if (!pid) { if (ev.summary_request) setSummaryRequest(true); if (ev.done) refreshUser(); return; }
        const k = key(pid); keys.add(k);
        const base = { pid, name: ev.persona_name, portrait: ev.portrait, moderator: ev.is_moderator, text: "" };
        if (ev.start) setLiveMap((prev) => ({ ...prev, [k]: { ...base } }));
        if (ev.status) setLiveMap((prev) => ({ ...prev, [k]: { ...(prev[k] || base), status: ev.status, rendering: ev.rendering || "" } }));
        if (ev.delta !== undefined) setLiveMap((prev) => { const cur = prev[k] || base; return { ...prev, [k]: { ...cur, status: "", rendering: "", text: cur.text + ev.delta } }; });
        if (ev.final && speaker && ev.content) playTTS(ev.content, ev.voice);
        if (ev.summary_request) setSummaryRequest(true);
        if (ev.done) refreshUser();
      }, quote ? { reply_to: quote } : {});
      if (!convWs.current || convWs.current.readyState !== 1) { const r = await api.get(`/conversations/${id}/messages?limit=50`); applyPage(r.data); }
      loadConvs();
    } catch (e) {
      if (e?.status === 429) { setCooldown(Math.min(60, e.retryAfter || 3)); setInput((v) => v || text); }
      setMessages((m) => m.filter((x) => x.id !== "tmp-u-" + reqId)); // rejected — put the text back, drop the optimistic bubble
      toast.error(e?.detail || (e?.status === 429 ? "Terlalu banyak pesan, tunggu sebentar." : e?.status === 402 ? "Kuota kredit harian habis." : "Gagal mengirim pesan"));
    }
    finally {
      setActiveStreams((n) => Math.max(0, n - 1));
      // drop any live bubble of this request that the WebSocket did not already replace
      setLiveMap((prev) => { const rest = { ...prev }; keys.forEach((k) => delete rest[k]); return rest; });
      setMessages((m) => m.filter((x) => x.id !== "tmp-u-" + reqId || !m.some((y) => y.role === "user" && !String(y.id).startsWith("tmp-u-") && y.content === text)));
    }
  };

  const delConv = async (c, e) => { e.stopPropagation(); await api.delete(`/conversations/${c.id}`); loadConvs(); if (c.id === id) nav("/chat"); };
  const refreshMsgs = () => { refreshUser(); return api.get(`/conversations/${id}/messages?limit=50`).then((r) => applyPage(r.data)).catch(() => {}); };

  const [savingNotes, setSavingNotes] = useState(false);
  const saveNotes = async () => {
    setSavingNotes(true);
    try {
      await api.post(`/conversations/${id}/summary`);
      const r = await api.get(`/conversations/${id}/messages`); setMessages(r.data.messages); refreshUser();
      toast.success("Notulen tersimpan di Ruang Kerja");
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal membuat notulen"); } finally { setSavingNotes(false); }
  };

  const isMulti = conv && conv.type !== "private";

  const ql = q.trim().toLowerCase();
  const groups = convs.filter((c) => c.type !== "private" && c.type !== "dm" && (!ql || (c.title || "").toLowerCase().includes(ql)));
  const asst = (personas || []).filter((p) => !ql || p.name.toLowerCase().includes(ql)).sort((a, b) => { const ta = directOf(a.id)?.updated_at || "", tb = directOf(b.id)?.updated_at || ""; return ta !== tb ? (tb > ta ? 1 : -1) : a.name.localeCompare(b.name); });
  const Row = ({ onClick, active, avatar, title, sub, time, unread, testid, icon }) => (
    <div onClick={onClick} data-testid={testid} className={`group flex cursor-pointer items-center gap-3 rounded-xl px-2.5 py-2.5 ${active ? "bg-[#EEF3FF]" : "hover:bg-slate-50"}`}>
      {avatar}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2"><span className={`flex-1 truncate text-sm ${unread ? "font-bold text-slate-900" : "font-semibold text-slate-800"}`}>{title}</span><span className="shrink-0 text-[10px] text-slate-400">{time}</span></div>
        <div className="flex items-center gap-2"><span className={`flex-1 truncate text-xs ${unread ? "font-semibold text-slate-700" : "text-slate-400"}`}>{sub}</span>{unread && <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-[#2F6BFF]" data-testid="unread-dot" />}{icon}</div>
      </div>
    </div>
  );
  const convListInner = (mobile) => (
    <div className="flex h-full flex-col p-3">
      <div className="relative mb-2">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input className="input-dark py-2 pl-9" placeholder="Cari asisten atau grup" value={q} onChange={(e) => setQ(e.target.value)} data-testid={mobile ? "chat-search-mobile" : "chat-search"} />
      </div>
      <div className="flex-1 space-y-1 overflow-y-auto">
        {convsLoading && convs.length === 0 && <p className="flex items-center justify-center gap-2 px-2 py-3 text-xs text-slate-400" data-testid="conv-loading"><Loader2 size={13} className="animate-spin" /> Memuat percakapan…</p>}
        <div className="flex items-center justify-between px-2 pt-1"><p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Asisten</p>{isAdmin && <button onClick={() => nav("/personas/new")} className="text-[11px] font-semibold text-[#2F6BFF]" data-testid="side-new-persona">+ Baru</button>}</div>
        {asst.map((p) => { const c = directOf(p.id); return (
          <Row key={p.id} onClick={() => (c ? (nav(`/chat/${c.id}`), mobile && setShowConvList(false)) : openDirect(p.id, mobile))} active={c && c.id === id} testid={`${mobile ? "asst-m-" : "asst-"}${p.id}`}
            avatar={<Avatar name={p.name} portrait={p.portrait} size={40} />} title={p.name} sub={c?.last_message || p.summary || "Ketuk untuk mulai chat"} time={c ? fmtTime(c.updated_at) : ""} unread={!!c?.unread} />
        ); })}
        {personas && asst.length === 0 && <p className="px-2 py-2 text-xs text-slate-400">Tidak ada asisten.</p>}
        {friends.length > 0 && (<>
          <div className="flex items-center justify-between px-2 pt-3"><p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Teman</p><button onClick={() => nav("/friends")} className="text-[11px] font-semibold text-[#2F6BFF]" data-testid="side-friends">Kelola</button></div>
          {friends.filter((f) => !ql || f.name.toLowerCase().includes(ql)).sort((a, b) => ((dmOf(b.id)?.updated_at || "") > (dmOf(a.id)?.updated_at || "") ? 1 : -1)).map((f) => { const c = dmOf(f.id); return (
            <Row key={f.id} onClick={() => (c ? (nav(`/chat/${c.id}`), mobile && setShowConvList(false)) : openFriend(f, mobile))} active={c && c.id === id} testid={`${mobile ? "friend-m-" : "friend-"}${f.id}`}
              avatar={<span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#10B981] text-sm font-bold text-white">{(f.name || "?")[0].toUpperCase()}</span>} title={f.name} sub={c?.last_message || "Teman · ketuk untuk chat"} time={c ? fmtTime(c.updated_at) : ""} unread={!!c?.unread} />
          ); })}
        </>)}
        <div className="flex items-center justify-between px-2 pt-3"><p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Grup</p><button onClick={() => { openModal("group"); if (mobile) setShowConvList(false); }} className="text-[11px] font-semibold text-[#2F6BFF]" data-testid={mobile ? "new-group-btn-mobile" : "new-group-btn"}>+ Grup Baru</button></div>
        {groups.map((c) => (
          <Row key={c.id} onClick={() => { nav(`/chat/${c.id}`); if (mobile) setShowConvList(false); }} active={c.id === id} testid={`${mobile ? "conv-m-" : "conv-"}${c.id}`}
            avatar={<span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#0B132B] text-white">{c.type === "meeting" ? <Video size={17} /> : <Users size={17} />}</span>}
            title={c.title} sub={c.last_message || `${c.members?.length || 0} asisten${(c.humans || []).length > 1 ? ` · ${c.humans.length} orang` : ""}`} time={fmtTime(c.updated_at)} unread={!!c.unread}
            icon={<button onClick={(e) => delConv(c, e)} className="shrink-0 text-slate-300 transition hover:text-[#EF4444] md:opacity-0 md:group-hover:opacity-100" data-testid={`del-${c.id}`}><Trash2 size={13} /></button>} />
        ))}
        {!convsLoading && groups.length === 0 && <p className="px-2 py-2 text-xs text-slate-400">Belum ada grup. Buat grup untuk mengajak beberapa asisten sekaligus.</p>}
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

      <div className="relative flex min-w-0 flex-1 flex-col bg-[#F8FAFC]">
        {panelTask && <TaskSidePanel taskId={panelTask} onClose={() => setPanelTask(null)} />}
        <div className="flex items-center gap-2 border-b border-[#E7ECF3] bg-white px-3 py-3 sm:gap-3 sm:px-5">
          <button onClick={() => setShowConvList(true)} data-testid="mobile-conv-btn" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[#E7ECF3] text-slate-500 md:hidden"><MessageSquare size={17} /></button>
          {conv ? (
            <>
              <div className="flex -space-x-2">{(conv.members || []).slice(0, 4).map((m) => <div key={m.id} className="rounded-full ring-2 ring-white"><Avatar name={m.name} portrait={m.portrait} size={32} /></div>)}</div>
              <div className="min-w-0"><p className="truncate text-sm font-bold text-slate-900">{conv.title}</p>
                <p className="truncate text-xs text-slate-400">{conv.type === "dm" ? `Teman${(conv.members || []).length ? ` · asisten: ${conv.members.map((m) => m.name).join(", ")}` : " · tambahkan asisten dengan tombol +"}` : conv.type === "private" ? (conv.members?.[0]?.summary || "Asisten AI") : `Grup · ${[...(conv.humans || []).filter((h) => h.id !== user?.id).map((h) => h.name), ...(conv.members || []).map((m) => m.name)].join(", ")}`}</p></div>
            </>
          ) : <p className="truncate text-sm font-semibold text-slate-500">Pilih atau mulai percakapan</p>}
          {conv && (
            <div className="ml-auto flex shrink-0 items-center gap-2">
              {conv.type === "private" && <button onClick={() => setVideoOpen(true)} title={rt.enabled ? "Panggilan suara realtime" : "Mode panggilan suara"} data-testid="call-mode-btn" className="flex h-9 items-center gap-1.5 rounded-lg bg-[#10B981] px-2.5 text-xs font-semibold text-white sm:px-3"><Phone size={15} /> <span className="hidden sm:inline">Panggil{rt.enabled ? " · Realtime" : ""}</span></button>}
              {conv.type !== "private" && <button onClick={() => setVideoOpen(true)} title="Masuk ruang panggilan" data-testid="video-call-btn" className="flex h-9 items-center gap-1.5 rounded-lg bg-[#2F6BFF] px-2.5 text-xs font-semibold text-white sm:px-3"><Video size={15} /> <span className="hidden sm:inline">Masuk Panggilan</span></button>}
              {conv.type !== "private" && <button onClick={saveNotes} disabled={savingNotes} title="Buat & simpan notulen ke Ruang Kerja" data-testid="save-notes-btn" className="flex h-9 items-center gap-1.5 rounded-lg border border-[#E6EAF2] bg-white px-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50 sm:px-3">{savingNotes ? <RefreshCw size={15} className="animate-spin" /> : <FileText size={15} />} <span className="hidden sm:inline">Notulen</span></button>}
              <AddPersonaMenu conv={conv} personas={personas || []} onAdded={(c) => { setConv(c); refreshMsgs(); loadConvs(); }} />
              <button onClick={() => setSpeaker(!speaker)} title="Baca jawaban dengan suara" data-testid="speaker-toggle" className={`flex h-9 w-9 items-center justify-center rounded-lg border ${speaker ? "btn-grad border-transparent" : "border-[#E7ECF3] text-slate-500"}`}>{speaker ? <Volume2 size={16} /> : <VolumeX size={16} />}</button>
            </div>
          )}
        </div>

        <div ref={listRef} onClickCapture={onListClick} onScroll={(e) => { if (e.currentTarget.scrollTop < 60) loadOlder(); }} className="flex-1 space-y-5 overflow-y-auto p-5" data-testid="message-list">
          {msgsLoading && <div className="flex h-full items-center justify-center gap-2 text-sm text-slate-400" data-testid="msgs-loading"><Loader2 size={18} className="animate-spin" /> Memuat percakapan…</div>}
          {conv && !msgsLoading && msgHasMore && <div className="flex items-center justify-center gap-2 text-xs text-slate-400" data-testid="msg-older-hint">{loadingOlder ? <><Loader2 size={13} className="animate-spin" /> Memuat pesan lama…</> : "Gulir ke atas untuk pesan lama"}</div>}
          {conv && archivedCount > 0 && <div className="text-center"><button onClick={() => setShowArchive(true)} data-testid="archive-btn" className="rounded-full border border-[#E7ECF3] bg-white px-3 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50">Arsip percakapan ({archivedCount})</button></div>}
          {conv?.task_id && <TaskContextCard taskId={conv.task_id} refreshKey={messages.length} cid={id} onDetach={() => setConv((c) => ({ ...c, task_id: null }))} />}
          {!conv && !msgsLoading && (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <Bot size={44} className="mb-4 text-[#2F6BFF]" />
              <h3 className="text-lg font-bold text-slate-900">Pilih asisten atau grup di panel kiri</h3>
              <p className="mt-1 max-w-sm text-sm text-slate-500">Setiap asisten punya satu ruang chat. Buat grup untuk mengajak beberapa asisten sekaligus; panggilan suara dimulai dari dalam chat.</p>
              <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
                <button onClick={() => setShowConvList(true)} data-testid="empty-open-list-btn" className="btn-grad rounded-xl px-6 py-3 text-sm md:hidden">Buka daftar chat</button>
                <button onClick={() => openModal("group")} data-testid="empty-new-group-btn" className="flex items-center gap-2 rounded-xl border border-[#2F6BFF]/40 px-6 py-3 text-sm font-semibold text-[#2F6BFF] transition hover:bg-[#EEF3FF]"><Users size={16} /> Grup Baru</button>
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            m.role === "user" ? (
              <div key={m.id || i} className="flex flex-col items-end">
                {isMulti && m.sender_user_id && m.sender_user_id !== user?.id && <p className="mb-1 mr-1 text-xs font-semibold text-slate-500">{m.sender_name}</p>}
                <div className="max-w-[78%] rounded-2xl rounded-tr-sm px-4 py-3 text-sm text-white" style={{ background: "linear-gradient(135deg,#2F6BFF,#7C3AED)" }} data-testid="msg-user">
                  {(m.attachments || []).length > 0 && <div className="mb-2 flex flex-wrap gap-1.5">{m.attachments.map((a, k) => a.task_id
                    ? <a key={k} href={`${window.location.origin}/workspace/${a.task_id}`} target="_blank" rel="noreferrer" className="flex items-center gap-1 rounded-lg bg-white/20 px-2 py-1 text-xs underline-offset-2 hover:underline" data-testid="att-link-task"><FileText size={11} />{a.name}<ExternalLink size={10} /></a>
                    : a.link
                    ? <a key={k} href={a.link} target="_blank" rel="noreferrer" className="flex items-center gap-1 rounded-lg bg-white/20 px-2 py-1 text-xs underline-offset-2 hover:underline" data-testid="att-link-drive"><HardDrive size={11} />{a.name}<ExternalLink size={10} /></a>
                    : a.path
                    ? <a key={k} href={downloadUrl(a.path)} target="_blank" rel="noreferrer" download={a.name} className="flex items-center gap-1 rounded-lg bg-white/20 px-2 py-1 text-xs underline-offset-2 hover:underline" data-testid="att-link-file">{a.kind === "image" ? <ImageIcon size={11} /> : <FileText size={11} />}{a.name}<ExternalLink size={10} /></a>
                    : <span key={k} className="flex items-center gap-1 rounded-lg bg-white/20 px-2 py-1 text-xs">{a.type === "image" ? <ImageIcon size={11} /> : <FileText size={11} />}{a.name}</span>)}</div>}
                  {m.reply_to?.content && <div className="mb-2 rounded-lg border-l-2 border-white/70 bg-white/15 px-2.5 py-1.5 text-xs" data-testid="msg-quote"><p className="font-semibold">{m.reply_to.name || "Asisten"}</p><p className="line-clamp-2 opacity-90">{m.reply_to.content}</p></div>}
                  {m.forwarded && <p className="mb-1 flex items-center gap-1 text-[11px] italic opacity-80" data-testid="msg-forwarded"><Forward size={11} /> Diteruskan</p>}
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
                    {m.rendering && !(m.media || []).length && <RenderingBox kind={m.rendering} />}
                    <MediaList media={m.media || []} />
                    {m.task_id && <TaskCard m={m} onOpen={setPanelTask} />}
                    <ToolRequestCard m={m} cid={id} onDone={refreshMsgs} />
                    <MessageCta m={m} />
                    <TaskOfferButtons m={m} cid={id} onDone={refreshMsgs} isLast={i === messages.length - 1} />
                    <WorkspaceResults m={m} />
                    <ArchiveResults m={m} cid={id} onDone={refreshMsgs} isLast={i === messages.length - 1} />
                  </div>
                  <ModelBadge m={m} />
                  <div className="mt-1.5 flex gap-3 opacity-0 transition group-hover:opacity-100">
                    <button onClick={() => setReplyTo({ id: m.id, name: m.persona_name, content: m.content })} title="Balas (kutip)" aria-label="Balas" data-testid="msg-reply-btn" className="text-slate-400 hover:text-slate-700"><Reply size={14} /></button>
                    <button onClick={() => setForwardMsg(m)} title="Teruskan pesan" aria-label="Teruskan" data-testid="msg-forward-btn" className="text-slate-400 hover:text-slate-700"><Forward size={14} /></button>
                  </div>
                </div>
              </div>
            )
          ))}
          {Object.entries(liveMap).map(([k, l]) => {
            return (
              <div key={k} className="flex justify-start gap-2.5">
                <div className="mt-1 shrink-0"><Avatar name={l.name} portrait={l.portrait} size={32} moderator={l.moderator} /></div>
                <div className="max-w-[78%]">
                  <p className="mb-1 text-xs font-semibold text-slate-500">{l.name}</p>
                  <div className={`rounded-2xl rounded-tl-sm px-4 py-3 text-sm ${l.moderator ? "border border-[#2F6BFF]/30 bg-[#EEF3FF]" : "aivora-card"} text-slate-700`} data-testid="msg-streaming">
                    {l.rendering ? <RenderingBox kind={l.rendering} /> : l.status ? <span className="flex items-center gap-2 text-slate-500" data-testid="msg-streaming-status"><Loader2 size={13} className="animate-spin" /> {l.status}</span> : l.text ? <Markdown content={l.text} /> : <span className="inline-flex gap-1"><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" /><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: ".15s" }} /><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: ".3s" }} /></span>}
                  </div>
                </div>
              </div>
            );
          })}
          {conv && summaryRequest && !streaming && <SummaryPrompt cid={id} onDone={refreshMsgs} onLater={() => setSummaryRequest(false)} />}
          <div ref={endRef} />
        </div>

        {conv && (
          <div className="border-t border-[#E7ECF3] bg-white p-4">
            {attachments.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-2">
                {attachments.map((a, k) => (
                  <span key={k} className="flex items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-1.5 text-xs text-slate-600" data-testid={`att-${k}`}>
                    {a.type === "drive" ? <HardDrive size={12} className="text-[#2F6BFF]" /> : a.type === "gallery" ? <Images size={12} className="text-[#2F6BFF]" /> : a.type === "image" ? <ImageIcon size={12} /> : <FileText size={12} />}{a.name}
                    <button onClick={() => setAttachments((p) => p.filter((_, j) => j !== k))}><X size={12} /></button>
                  </span>
                ))}
              </div>
            )}
            {isMulti && <p className="mb-2 text-xs text-slate-400">Tip: sebut @NamaAsisten untuk menuju satu asisten tertentu.</p>}
            {replyTo && (
              <div className="mb-2 flex items-start gap-2 rounded-xl border-l-4 border-[#2F6BFF] bg-[#EEF3FF] px-3 py-2 text-xs" data-testid="reply-preview">
                <CornerUpLeft size={14} className="mt-0.5 shrink-0 text-[#2F6BFF]" />
                <div className="min-w-0 flex-1"><p className="font-semibold text-[#2F6BFF]">Membalas {replyTo.name || "asisten"}</p><p className="line-clamp-2 text-slate-600">{replyTo.content}</p></div>
                <button onClick={() => setReplyTo(null)} aria-label="Batal balas" data-testid="reply-cancel-btn" className="text-slate-400 hover:text-slate-700"><X size={14} /></button>
              </div>
            )}
            <div className="flex items-end gap-2">
              <input ref={fileRef} type="file" multiple accept="image/*,application/pdf,.txt,.md,.csv" className="hidden" onChange={onFiles} />
              <button onClick={() => fileRef.current?.click()} data-testid="attach-btn" title="Unggah berkas" className="flex h-12 w-11 shrink-0 items-center justify-center rounded-xl border border-[#E7ECF3] text-slate-500 hover:bg-slate-50"><Paperclip size={18} /></button>
              <button onClick={() => setShowGallery(true)} data-testid="attach-gallery-btn" title="Lampirkan dari Galeri" className="hidden h-12 w-11 shrink-0 items-center justify-center rounded-xl border border-[#E7ECF3] text-slate-500 hover:bg-slate-50 sm:flex"><Images size={18} /></button>
              {driveOn && <button onClick={() => setShowDrive(true)} data-testid="attach-drive-btn" title="Lampirkan dari Google Drive" className="hidden h-12 w-11 shrink-0 items-center justify-center rounded-xl border border-[#E7ECF3] text-slate-500 hover:bg-slate-50 sm:flex"><HardDrive size={18} /></button>}
              <button onClick={toggleRecord} data-testid="mic-btn" className={`flex h-12 w-11 shrink-0 items-center justify-center rounded-xl border ${recording ? "animate-pulse border-[#EF4444] bg-[#EF4444] text-white" : "border-[#E7ECF3] text-slate-500 hover:bg-slate-50"}`}>{recording ? <Square size={16} /> : <Mic size={18} />}</button>
              <textarea className="input-dark max-h-32 min-h-[48px] resize-none" rows={1} placeholder={t("chat.placeholder")} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} data-testid="chat-input" />
              <button onClick={send} disabled={cooldown > 0 || (!input.trim() && attachments.length === 0)} title={cooldown > 0 ? `Tunggu ${cooldown} dtk` : undefined} className="btn-grad flex h-12 w-12 shrink-0 items-center justify-center rounded-xl" data-testid="chat-send-btn"><Send size={18} /></button>
            </div>
          </div>
        )}
      </div>

      {forwardMsg && <ForwardDialog msg={forwardMsg} convs={convs} currentId={id} onClose={() => setForwardMsg(null)} />}
      {showArchive && conv && <ChatArchivesModal cid={id} onClose={() => setShowArchive(false)} onRestored={() => refreshMsgs()} />}
      {videoOpen && conv && (conv.type === "private" && rt.enabled
        ? <RealtimeCall conv={conv} cid={id} messages={messages} onClose={() => setVideoOpen(false)} onRefresh={refreshMsgs} />
        : conv.type !== "private" && (rt.enabled || (conv.humans || []).length > 1)
        ? <RealtimeMeeting conv={conv} cid={id} messages={messages} onClose={() => setVideoOpen(false)} onRefresh={refreshMsgs} />
        : <VideoRoom conv={conv} cid={id} messages={messages} isPrivate={conv.type === "private"} onClose={() => setVideoOpen(false)} onRefresh={refreshMsgs} />)}

      {showGallery && conv && <GalleryPicker onClose={() => setShowGallery(false)} onPick={(items) => setAttachments((a) => [...a, ...items].slice(0, 5))} max={5 - attachments.length} />}
      {showDrive && conv && <DrivePicker onClose={() => setShowDrive(false)} onPick={(items) => setAttachments((a) => [...a, ...items].slice(0, 5))} max={5 - attachments.length} />}

      {showModal && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setShowModal(false)} />
          <div className="relative w-full max-w-md rounded-3xl border border-[#E7ECF3] bg-white p-6 shadow-2xl fade-up" data-testid="new-chat-modal">
            <button onClick={() => setShowModal(false)} className="absolute right-4 top-4 text-slate-400"><X size={18} /></button>
            <h3 className="text-lg font-bold text-slate-900">Grup Baru</h3>
            <p className="mt-1 text-sm text-slate-500">Pilih asisten dan/atau teman (minimal dua anggota). Di grup, asisten yang relevan yang menjawab — atau sebut @Nama. Bila ada teman, asisten hanya menjawab saat jelas ditanya.</p>
            <input className="input-dark mt-3 py-2.5" placeholder="Nama grup (opsional)" value={groupTitle} onChange={(e) => setGroupTitle(e.target.value)} data-testid="group-title-input" />
            <div className="mt-4 max-h-72 space-y-2 overflow-y-auto">
              {friends.length > 0 && <p className="px-1 text-[11px] font-bold uppercase tracking-wider text-slate-400">Teman</p>}
              {friends.map((f) => { const on = pickedFriends.includes(f.id); return (
                <button key={f.id} onClick={() => setPickedFriends((p) => (p.includes(f.id) ? p.filter((x) => x !== f.id) : [...p, f.id]))} data-testid={`pick-friend-${f.id}`} className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left transition ${on ? "border-[#10B981] bg-emerald-50" : "border-[#E7ECF3] hover:bg-slate-50"}`}>
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#10B981] text-sm font-bold text-white">{(f.name || "?")[0].toUpperCase()}</span>
                  <span className="min-w-0 flex-1"><span className="block truncate text-sm font-bold text-slate-900">{f.name}</span><span className="block truncate text-xs text-slate-400">{f.email}</span></span>
                  <span className={`flex h-5 w-5 items-center justify-center rounded-md border ${on ? "border-transparent bg-[#10B981] text-white" : "border-slate-300"}`}>{on && <Check size={13} />}</span>
                </button>
              ); })}
              {friends.length > 0 && <p className="px-1 pt-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">Asisten</p>}
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
              <span className="text-xs font-semibold text-slate-500">{picked.length + pickedFriends.length === 0 ? "Belum dipilih" : `${picked.length} asisten${pickedFriends.length ? ` · ${pickedFriends.length} teman` : ""}`}</span>
              <button onClick={startConv} disabled={!canCreate} className="btn-grad flex items-center gap-2 rounded-xl px-6 py-2.5 text-sm disabled:opacity-50" data-testid="start-conv-btn"><Users size={15} /> Buat Grup</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// Pick a conversation and forward an assistant message there (WhatsApp-style).
function ForwardDialog({ msg, convs, currentId, onClose }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState("");
  const nav = useNavigate();
  const list = convs.filter((c) => c.id !== currentId && (!q || (c.title || "").toLowerCase().includes(q.toLowerCase())));
  const go = async (c) => {
    setBusy(c.id);
    try {
      await api.post(`/conversations/${c.id}/send`, { content: msg.content, forwarded: true });
      toast.success(`Pesan diteruskan ke ${c.title}`);
      onClose(); nav(`/chat/${c.id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal meneruskan pesan"); setBusy(""); }
  };
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} />
      <div className="relative flex max-h-[80vh] w-full max-w-md flex-col rounded-3xl border border-[#E7ECF3] bg-white p-5 shadow-2xl fade-up" data-testid="forward-dialog">
        <button onClick={onClose} className="absolute right-4 top-4 text-slate-400" aria-label="Tutup"><X size={18} /></button>
        <h3 className="flex items-center gap-2 text-lg font-bold text-slate-900"><Forward size={18} /> Teruskan pesan</h3>
        <p className="mt-1 line-clamp-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">{msg.content}</p>
        <input autoFocus className="input-dark mt-3 py-2" placeholder="Cari percakapan…" value={q} onChange={(e) => setQ(e.target.value)} data-testid="forward-search" />
        <div className="mt-2 min-h-0 flex-1 space-y-1 overflow-y-auto">
          {list.map((c) => (
            <button key={c.id} onClick={() => go(c)} disabled={!!busy} data-testid={`forward-target-${c.id}`} className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left hover:bg-[#EEF3FF] disabled:opacity-60">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#EEF3FF] text-[#2F6BFF]">{c.type === "private" ? <Bot size={16} /> : c.type === "dm" ? <MessageSquare size={16} /> : <Users size={16} />}</span>
              <span className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-slate-800">{c.title}</p><p className="truncate text-[11px] text-slate-400">{c.last_message || ""}</p></span>
              {busy === c.id && <Loader2 size={14} className="animate-spin text-slate-400" />}
            </button>
          ))}
          {list.length === 0 && <p className="py-6 text-center text-sm text-slate-400">Tidak ada percakapan lain.</p>}
        </div>
      </div>
    </div>
  );
}
