import React, { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Plus, Send, Search, Trash2, Copy, RefreshCw, Bookmark } from "lucide-react";
import { toast } from "sonner";
import { api, streamChat } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n";
import { Markdown } from "../components/Markdown";
import { AIVORA_MARK } from "../components/Logo";

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
  const [stream, setStream] = useState("");
  const endRef = useRef(null);

  const loadConvs = (query = "") => api.get(`/conversations${query ? `?q=${encodeURIComponent(query)}` : ""}`).then((r) => setConvs(r.data)).catch(() => {});
  useEffect(() => { loadConvs(); }, []);
  useEffect(() => {
    if (id) api.get(`/conversations/${id}/messages`).then((r) => { setConv(r.data.conversation); setMessages(r.data.messages); }).catch(() => {});
    else { setConv(null); setMessages([]); }
  }, [id]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, stream]);

  const newChat = async () => {
    const r = await api.post("/conversations", { title: "New conversation" });
    loadConvs(); nav(`/chat/${r.data.id}`);
  };

  const send = async () => {
    if (!input.trim() || streaming) return;
    let cid = id;
    if (!cid) { const r = await api.post("/conversations", {}); cid = r.data.id; nav(`/chat/${cid}`); }
    const text = input;
    setInput("");
    setMessages((m) => [...m, { id: "tmp-u", role: "user", content: text }]);
    setStreaming(true); setStream("");
    try {
      await streamChat(cid, text, (delta) => setStream((s) => s + delta), (done) => { refreshUser(); });
      // reload canonical messages
      const r = await api.get(`/conversations/${cid}/messages`);
      setMessages(r.data.messages); setStream(""); loadConvs();
    } catch (e) { toast.error("Gagal mengirim pesan"); } finally { setStreaming(false); }
  };

  const delConv = async (c, e) => { e.stopPropagation(); await api.delete(`/conversations/${c.id}`); loadConvs(); if (c.id === id) nav("/chat"); };
  const copy = (txt) => { navigator.clipboard.writeText(txt); toast.success("Disalin"); };
  const saveMem = async (txt) => { await api.post("/memory", { persona_id: conv?.persona_id || null, content: txt.slice(0, 300) }); toast.success("Disimpan ke memori"); };
  const regen = async (mid) => {
    setStreaming(true);
    try { const r = await api.post(`/conversations/${id}/messages/${mid}/regenerate`); const mr = await api.get(`/conversations/${id}/messages`); setMessages(mr.data.messages); refreshUser(); }
    catch (e) { toast.error("Gagal"); } finally { setStreaming(false); }
  };

  return (
    <div className="flex h-[calc(100vh-4rem)] md:h-screen" data-testid="chat-page">
      {/* conversation list */}
      <div className="hidden w-72 shrink-0 flex-col border-r border-[rgba(0,209,255,.1)] p-4 md:flex">
        <button onClick={newChat} data-testid="new-chat-btn" className="btn-grad mb-4 flex items-center justify-center gap-2 rounded-xl py-2.5 text-sm"><Plus size={16} /> {t("chat.new")}</button>
        <div className="relative mb-3">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input className="input-dark pl-9 py-2" placeholder={t("common.search")} value={q} onChange={(e) => { setQ(e.target.value); loadConvs(e.target.value); }} data-testid="chat-search" />
        </div>
        <div className="flex-1 space-y-1 overflow-y-auto">
          {convs.map((c) => (
            <div key={c.id} onClick={() => nav(`/chat/${c.id}`)} data-testid={`conv-${c.id}`}
              className={`group flex cursor-pointer items-center justify-between rounded-xl px-3 py-2.5 text-sm ${c.id === id ? "bg-[#1C2D5A] text-white" : "text-slate-300 hover:bg-[#162244]"}`}>
              <span className="truncate">{c.title}</span>
              <button onClick={(e) => delConv(c, e)} className="opacity-0 transition group-hover:opacity-100 text-slate-500 hover:text-[#EF4444]"><Trash2 size={13} /></button>
            </div>
          ))}
        </div>
      </div>

      {/* messages */}
      <div className="flex flex-1 flex-col">
        <div className="glass flex items-center gap-3 border-b border-[rgba(0,209,255,.1)] px-5 py-3">
          <img src={AIVORA_MARK} alt="" className="h-8 w-8" />
          <div><p className="text-sm font-semibold text-white">{conv?.title || "Aivora"}</p><p className="text-xs text-slate-500">Asisten AI</p></div>
          <button onClick={newChat} className="ml-auto rounded-lg border border-slate-600 px-3 py-1.5 text-xs text-slate-300 md:hidden">+ Baru</button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {messages.length === 0 && !streaming && (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <img src={AIVORA_MARK} alt="" className="mb-4 h-16 w-16 opacity-80" />
              <h3 className="text-lg font-bold text-white">Mulai percakapan</h3>
              <p className="mt-1 max-w-sm text-sm text-slate-400">Tanya apa saja, atau mulai chat dari halaman persona Anda.</p>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={m.id || i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`group max-w-[78%] rounded-2xl px-4 py-3 text-sm ${m.role === "user" ? "text-[#06111f]" : "aivora-card text-slate-100"}`}
                style={m.role === "user" ? { background: "linear-gradient(135deg,#00D1FF,#7C3AED)" } : {}} data-testid={`msg-${m.role}`}>
                {m.role === "user" ? <p className="whitespace-pre-wrap">{m.content}</p> : <Markdown content={m.content} />}
                {m.role === "assistant" && (
                  <div className="mt-2 flex gap-3 opacity-0 transition group-hover:opacity-100">
                    <button onClick={() => copy(m.content)} className="text-slate-500 hover:text-white" title="Salin"><Copy size={13} /></button>
                    <button onClick={() => saveMem(m.content)} className="text-slate-500 hover:text-white" title="Simpan ke memori"><Bookmark size={13} /></button>
                    <button onClick={() => regen(m.id)} className="text-slate-500 hover:text-white" title="Regenerate"><RefreshCw size={13} /></button>
                  </div>
                )}
              </div>
            </div>
          ))}
          {streaming && (
            <div className="flex justify-start">
              <div className="aivora-card max-w-[78%] rounded-2xl px-4 py-3 text-sm text-slate-100" data-testid="msg-streaming">
                {stream ? <Markdown content={stream} /> : <span className="text-slate-500">Aivora sedang mengetik...</span>}
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <div className="border-t border-[rgba(0,209,255,.1)] p-4">
          <div className="flex items-end gap-2">
            <textarea className="input-dark max-h-32 min-h-[48px] resize-none" rows={1} placeholder={t("chat.placeholder")}
              value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} data-testid="chat-input" />
            <button onClick={send} disabled={streaming || !input.trim()} className="btn-grad flex h-12 w-12 shrink-0 items-center justify-center rounded-xl" data-testid="chat-send-btn"><Send size={18} /></button>
          </div>
        </div>
      </div>
    </div>
  );
}
