import React, { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Plus, Send, Search, Trash2, Copy, RefreshCw, Bookmark, Users, User, X, Check, Bot } from "lucide-react";
import { toast } from "sonner";
import { api, streamChat } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n";
import { Markdown } from "../components/Markdown";

function Avatar({ name, portrait, size = 32 }) {
  if (portrait) return <img src={portrait} alt={name} className="rounded-full object-cover" style={{ width: size, height: size }} />;
  return (
    <span className="flex items-center justify-center rounded-full font-bold text-white" style={{ width: size, height: size, fontSize: size * 0.42, background: "linear-gradient(135deg,#2F6BFF,#7C3AED)" }}>
      {(name || "?")[0].toUpperCase()}
    </span>
  );
}

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
  const [liveMap, setLiveMap] = useState({}); // persona_id -> {name, portrait, text}
  const [liveOrder, setLiveOrder] = useState([]);
  const [personas, setPersonas] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [picked, setPicked] = useState([]);
  const endRef = useRef(null);

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
    setPicked([]); setShowModal(true);
  };
  const togglePick = (pid) => setPicked((p) => p.includes(pid) ? p.filter((x) => x !== pid) : [...p, pid]);
  const startConv = async () => {
    if (picked.length === 0) { toast.error("Pilih minimal satu persona"); return; }
    const type = picked.length > 1 ? "group" : "private";
    const r = await api.post("/conversations", { persona_ids: picked, type });
    setShowModal(false); loadConvs(); nav(`/chat/${r.data.id}`);
  };

  const send = async () => {
    if (!input.trim() || streaming || !id) return;
    const text = input; setInput("");
    setMessages((m) => [...m, { id: "tmp-u-" + Date.now(), role: "user", content: text }]);
    setStreaming(true); setLiveMap({}); setLiveOrder([]);
    try {
      await streamChat(id, text, (ev) => {
        if (ev.persona_id && ev.delta !== undefined) {
          setLiveMap((prev) => {
            const cur = prev[ev.persona_id] || { name: ev.persona_name, portrait: ev.portrait, text: "" };
            return { ...prev, [ev.persona_id]: { ...cur, text: cur.text + ev.delta } };
          });
          setLiveOrder((o) => (o.includes(ev.persona_id) ? o : [...o, ev.persona_id]));
        }
        if (ev.done) refreshUser();
      });
      const r = await api.get(`/conversations/${id}/messages`);
      setMessages(r.data.messages); setLiveMap({}); setLiveOrder([]); loadConvs();
    } catch (e) { toast.error("Gagal mengirim pesan"); } finally { setStreaming(false); }
  };

  const delConv = async (c, e) => { e.stopPropagation(); await api.delete(`/conversations/${c.id}`); loadConvs(); if (c.id === id) nav("/chat"); };
  const copy = (txt) => { navigator.clipboard.writeText(txt); toast.success("Disalin"); };
  const saveMem = async (m) => { await api.post("/memory", { persona_id: m.persona_id || conv?.persona_id || null, content: m.content.slice(0, 300) }); toast.success("Disimpan ke memori"); };
  const regen = async (mid) => {
    setStreaming(true);
    try { await api.post(`/conversations/${id}/messages/${mid}/regenerate`); const mr = await api.get(`/conversations/${id}/messages`); setMessages(mr.data.messages); refreshUser(); }
    catch (e) { toast.error("Gagal"); } finally { setStreaming(false); }
  };

  const isGroup = conv?.type === "group";

  return (
    <div className="flex h-[calc(100vh-4rem)]" data-testid="chat-page">
      {/* conversation list */}
      <div className="hidden w-72 shrink-0 flex-col border-r border-[#E7ECF3] bg-white p-4 md:flex">
        <button onClick={openModal} data-testid="new-chat-btn" className="btn-grad mb-4 flex items-center justify-center gap-2 rounded-xl py-2.5 text-sm"><Plus size={16} /> {t("chat.new")}</button>
        <div className="relative mb-3">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input-dark py-2 pl-9" placeholder={t("common.search")} value={q} onChange={(e) => { setQ(e.target.value); loadConvs(e.target.value); }} data-testid="chat-search" />
        </div>
        <div className="flex-1 space-y-1 overflow-y-auto">
          {convs.map((c) => (
            <div key={c.id} onClick={() => nav(`/chat/${c.id}`)} data-testid={`conv-${c.id}`}
              className={`group flex cursor-pointer items-center gap-2 rounded-xl px-3 py-2.5 text-sm ${c.id === id ? "bg-[#EEF3FF] text-[#2F6BFF]" : "text-slate-600 hover:bg-slate-50"}`}>
              {c.type === "group" ? <Users size={15} className="shrink-0" /> : <User size={15} className="shrink-0" />}
              <span className="flex-1 truncate">{c.title}</span>
              <button onClick={(e) => delConv(c, e)} className="opacity-0 transition group-hover:opacity-100 text-slate-400 hover:text-[#EF4444]"><Trash2 size={13} /></button>
            </div>
          ))}
        </div>
      </div>

      {/* messages */}
      <div className="flex flex-1 flex-col bg-[#F8FAFC]">
        <div className="flex items-center gap-3 border-b border-[#E7ECF3] bg-white px-5 py-3">
          {conv ? (
            <>
              <div className="flex -space-x-2">
                {(conv.members || []).slice(0, 4).map((m) => <div key={m.id} className="ring-2 ring-white rounded-full"><Avatar name={m.name} portrait={m.portrait} size={32} /></div>)}
              </div>
              <div><p className="text-sm font-bold text-slate-900">{conv.title}</p>
                <p className="text-xs text-slate-400">{isGroup ? `Grup · ${conv.members?.length} asisten` : "Chat privat"}</p></div>
            </>
          ) : <p className="text-sm font-semibold text-slate-500">Pilih atau mulai percakapan</p>}
          <button onClick={openModal} className="ml-auto rounded-lg border border-[#E7ECF3] px-3 py-1.5 text-xs font-semibold text-slate-600 md:hidden">+ Baru</button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {!conv && (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <Bot size={44} className="mb-4 text-[#2F6BFF]" />
              <h3 className="text-lg font-bold text-slate-900">Mulai percakapan dengan tim Anda</h3>
              <p className="mt-1 max-w-sm text-sm text-slate-500">Pilih satu asisten untuk chat privat, atau beberapa untuk diskusi grup.</p>
              <button onClick={openModal} className="btn-grad mt-5 rounded-xl px-6 py-3 text-sm">+ Mulai Chat</button>
            </div>
          )}
          {messages.map((m, i) => (
            m.role === "user" ? (
              <div key={m.id || i} className="flex justify-end">
                <div className="max-w-[78%] rounded-2xl rounded-tr-sm px-4 py-3 text-sm text-white" style={{ background: "linear-gradient(135deg,#2F6BFF,#7C3AED)" }} data-testid="msg-user">
                  <p className="whitespace-pre-wrap">{m.content}</p>
                </div>
              </div>
            ) : (
              <div key={m.id || i} className="flex justify-start gap-2.5">
                <div className="mt-1 shrink-0"><Avatar name={m.persona_name} portrait={m.portrait} size={32} /></div>
                <div className="group max-w-[78%]">
                  <p className="mb-1 text-xs font-semibold text-slate-500">{m.persona_name}</p>
                  <div className="aivora-card rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-slate-700" data-testid="msg-assistant"><Markdown content={m.content} /></div>
                  <div className="mt-1.5 flex gap-3 opacity-0 transition group-hover:opacity-100">
                    <button onClick={() => copy(m.content)} className="text-slate-400 hover:text-slate-700"><Copy size={13} /></button>
                    <button onClick={() => saveMem(m)} className="text-slate-400 hover:text-slate-700"><Bookmark size={13} /></button>
                    <button onClick={() => regen(m.id)} className="text-slate-400 hover:text-slate-700"><RefreshCw size={13} /></button>
                  </div>
                </div>
              </div>
            )
          ))}
          {/* live streaming bubbles */}
          {liveOrder.map((pid) => {
            const l = liveMap[pid];
            return (
              <div key={pid} className="flex justify-start gap-2.5">
                <div className="mt-1 shrink-0"><Avatar name={l.name} portrait={l.portrait} size={32} /></div>
                <div className="max-w-[78%]">
                  <p className="mb-1 text-xs font-semibold text-slate-500">{l.name}</p>
                  <div className="aivora-card rounded-2xl rounded-tl-sm px-4 py-3 text-sm text-slate-700" data-testid="msg-streaming">
                    {l.text ? <Markdown content={l.text} /> : <span className="text-slate-400">sedang mengetik...</span>}
                  </div>
                </div>
              </div>
            );
          })}
          {streaming && liveOrder.length === 0 && <p className="pl-11 text-sm text-slate-400">menyiapkan jawaban...</p>}
          <div ref={endRef} />
        </div>

        {conv && (
          <div className="border-t border-[#E7ECF3] bg-white p-4">
            <div className="flex items-end gap-2">
              <textarea className="input-dark max-h-32 min-h-[48px] resize-none" rows={1} placeholder={t("chat.placeholder")}
                value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} data-testid="chat-input" />
              <button onClick={send} disabled={streaming || !input.trim()} className="btn-grad flex h-12 w-12 shrink-0 items-center justify-center rounded-xl" data-testid="chat-send-btn"><Send size={18} /></button>
            </div>
          </div>
        )}
      </div>

      {/* new chat modal */}
      {showModal && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setShowModal(false)} />
          <div className="relative w-full max-w-md rounded-3xl border border-[#E7ECF3] bg-white p-6 shadow-2xl fade-up" data-testid="new-chat-modal">
            <button onClick={() => setShowModal(false)} className="absolute right-4 top-4 text-slate-400"><X size={18} /></button>
            <h3 className="text-lg font-bold text-slate-900">Mulai Percakapan</h3>
            <p className="mt-1 text-sm text-slate-500">Pilih 1 asisten untuk privat, atau beberapa untuk grup.</p>
            <div className="mt-4 max-h-80 space-y-2 overflow-y-auto">
              {personas.map((p) => {
                const on = picked.includes(p.id);
                return (
                  <button key={p.id} onClick={() => togglePick(p.id)} data-testid={`pick-${p.id}`}
                    className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left transition ${on ? "border-[#2F6BFF] bg-[#EEF3FF]" : "border-[#E7ECF3] hover:bg-slate-50"}`}>
                    <Avatar name={p.name} portrait={p.portrait} size={40} />
                    <span className="min-w-0 flex-1"><span className="block truncate text-sm font-bold text-slate-900">{p.name}</span>
                      <span className="block truncate text-xs text-slate-400">{p.summary || "Persona"}</span></span>
                    <span className={`flex h-5 w-5 items-center justify-center rounded-md border ${on ? "btn-grad border-transparent" : "border-slate-300"}`}>{on && <Check size={13} />}</span>
                  </button>
                );
              })}
            </div>
            <div className="mt-4 flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500">{picked.length > 1 ? `Grup · ${picked.length} asisten` : picked.length === 1 ? "Chat privat" : "Belum dipilih"}</span>
              <button onClick={startConv} className="btn-grad rounded-xl px-6 py-2.5 text-sm" data-testid="start-conv-btn">Mulai</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
