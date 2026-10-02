import React, { useEffect, useRef, useState } from "react";
import { X, Send, Paperclip, Loader2, MessageSquare, FileText, Image as ImageIcon, Download } from "lucide-react";
import { toast } from "sonner";
import { streamChatWithAtt } from "../lib/api";
import { Markdown } from "./Markdown";

const VIDEO_RE = /https?:\/\/[^\s)>"']+\.(?:mp4|webm)(?:\?[^\s)>"']*)?/gi;
const IMAGE_RE = /https?:\/\/[^\s)>"']+\.(?:png|jpe?g|gif|webp)(?:\?[^\s)>"']*)?/gi;
const OPEN_KEY = "aivora_meeting_chat_open";
const isChat = (m) => m.via === "meeting_chat";

const fileToData = (file) => new Promise((res) => {
  const r = new FileReader();
  r.onload = () => res(r.result);
  if (file.type.startsWith("image/") || file.type === "application/pdf") r.readAsDataURL(file); else r.readAsText(file);
});

// Panel open state (desktop default open, mobile default closed) + unread badge for assistant messages.
export function useMeetingChat(messages = []) {
  const [open, setOpen] = useState(() => { const s = localStorage.getItem(OPEN_KEY); return s !== null ? s === "1" : window.innerWidth >= 1024; });
  const [unread, setUnread] = useState(0);
  const seenRef = useRef(null);
  const count = messages.filter((m) => isChat(m) && m.role === "assistant").length;
  useEffect(() => {
    if (seenRef.current === null || open) { seenRef.current = count; setUnread(0); return; }
    setUnread(Math.max(0, count - seenRef.current));
  }, [count, open]);
  const set = (v) => { localStorage.setItem(OPEN_KEY, v ? "1" : "0"); setOpen(v); };
  return { open, unread, toggle: () => set(!open), close: () => set(false) };
}

export function ChatToggleButton({ open, unread, onClick }) {
  return (
    <button onClick={onClick} data-testid="meeting-chat-toggle" title="Chat meeting" className={`relative flex h-14 w-14 items-center justify-center rounded-full text-white transition ${open ? "bg-white/25" : "bg-white/10 hover:bg-white/20"}`}>
      <MessageSquare size={22} />
      {unread > 0 && <span data-testid="meeting-chat-unread" className="absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-[#2F6BFF] px-1 text-[11px] font-bold">{unread}</span>}
    </button>
  );
}

function Media({ m }) {
  const media = [...(m.media || [])];
  const seen = new Set(media.map((x) => x.url));
  for (const match of (m.content || "").matchAll(VIDEO_RE)) if (!seen.has(match[0])) { seen.add(match[0]); media.push({ type: "video", url: match[0] }); }
  for (const match of (m.content || "").matchAll(IMAGE_RE)) if (!seen.has(match[0])) { seen.add(match[0]); media.push({ type: "image", url: match[0] }); }
  if (!media.length) return null;
  return (
    <div className="mt-2 space-y-2">
      {media.map((x, i) => x.type === "video" ? (
        <div key={i} className="overflow-hidden rounded-xl bg-black" data-testid="mc-video">
          <video src={x.url} controls preload="metadata" className="max-h-56 w-full" />
          <div className="flex items-center justify-between px-3 py-1.5 text-[11px] text-white/70"><span className="truncate">{x.name || "Video"}</span><a href={x.url} download target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-white"><Download size={12} /> Unduh</a></div>
        </div>
      ) : x.type === "image" ? (
        <a key={i} href={x.url} target="_blank" rel="noreferrer" data-testid="mc-image"><img src={x.url} alt={x.name || ""} className="max-h-56 w-full rounded-xl object-cover" /></a>
      ) : (
        <a key={i} href={x.url} target="_blank" rel="noreferrer" data-testid="mc-file" className="flex items-center gap-2 rounded-lg bg-white/10 px-3 py-2 text-xs hover:bg-white/15"><FileText size={14} /><span className="flex-1 truncate">{x.name || x.url}</span><Download size={14} /></a>
      ))}
    </div>
  );
}

const MD_DARK = "[&_.md-body_p]:!text-white/90 [&_.md-body_li]:!text-white/90 [&_.md-body_ul]:!text-white/90 [&_.md-body_ol]:!text-white/90 [&_.md-body_h1]:!text-white [&_.md-body_h2]:!text-white [&_.md-body_h3]:!text-white [&_.md-body_strong]:!text-white [&_.md-body_a]:!text-[#8FB0FF] [&_.md-body_code]:!bg-black/30 [&_.md-body_code]:!text-emerald-200 [&_.md-body_pre]:!bg-black/40 [&_.md-body_th]:!border-white/15 [&_.md-body_td]:!border-white/15 [&_.md-body_table]:text-xs [&_.md-body_th]:bg-white/5";

function Bubble({ m, me }) {
  const time = m.created_at ? new Date(m.created_at).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }) : "";
  return (
    <div data-testid={me ? "mc-msg-user" : "mc-msg-assistant"} className={`rounded-2xl px-3.5 py-2.5 text-sm ${me ? "ml-8 bg-[#2F6BFF] text-white" : "mr-3 bg-white/[0.07] text-white/90"}`}>
      <div className="mb-1 flex items-center justify-between gap-2 text-[10px] font-bold uppercase tracking-wider opacity-60">
        <span className="truncate">{me ? (m.sender_name || "Anda") : (m.persona_name || "Asisten")}</span><span className="font-mono normal-case tracking-normal">{time}</span>
      </div>
      {(m.attachments || []).length > 0 && <div className="mb-1.5 flex flex-wrap gap-1">{m.attachments.map((a, k) => <span key={k} className="flex items-center gap-1 rounded-md bg-white/20 px-1.5 py-0.5 text-[11px]">{a.type === "image" ? <ImageIcon size={10} /> : <FileText size={10} />}{a.name}</span>)}</div>}
      {me ? <p className="whitespace-pre-wrap break-words">{m.content}</p> : <div className={MD_DARK}><Markdown content={m.content} /></div>}
      <Media m={m} />
    </div>
  );
}

// Text/data side channel of a live meeting: assistant replies in text only (tables, code, links, embedded media).
export function MeetingChatPanel({ cid, messages = [], onRefresh, onClose, onExchange }) {
  const items = messages.filter(isChat);
  const [input, setInput] = useState("");
  const [atts, setAtts] = useState([]);
  const [pending, setPending] = useState(null);
  const [live, setLive] = useState(null);
  const [busy, setBusy] = useState(false);
  const endRef = useRef(null);
  const fileRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [items.length, live?.text, pending]);

  const pick = async (e) => {
    const out = [];
    for (const f of Array.from(e.target.files || []).slice(0, 5)) {
      const type = f.type.startsWith("image/") ? "image" : f.type === "application/pdf" ? "pdf" : "text";
      out.push({ type, name: f.name, data: await fileToData(f) });
    }
    setAtts((a) => [...a, ...out].slice(0, 5)); e.target.value = "";
  };

  const send = async () => {
    if ((!input.trim() && atts.length === 0) || busy) return;
    const text = input, a = atts;
    setInput(""); setAtts([]); setBusy(true);
    setPending({ content: text, attachments: a.map((x) => ({ type: x.type, name: x.name })), created_at: new Date().toISOString(), sender_name: "Anda" });
    const reply = { name: "", text: "" };
    try {
      await streamChatWithAtt(cid, text, a, (ev) => {
        if (ev.persona_id && ev.start) { reply.name = ev.persona_name; reply.text = ""; setLive({ ...reply }); }
        if (ev.persona_id && ev.delta !== undefined) { reply.text += ev.delta; setLive({ ...reply }); }
        if (ev.persona_id && ev.final && ev.content) onExchange?.(text, ev.content, ev.persona_name);
      }, { channel: "meeting_chat" });
      await onRefresh?.();
    } catch (e) {
      toast.error(e?.detail || (e?.status === 402 ? "Kuota kredit habis" : e?.status === 429 ? "Terlalu banyak pesan, tunggu sebentar." : "Gagal mengirim pesan"));
    } finally { setBusy(false); setLive(null); setPending(null); }
  };

  return (
    <aside data-testid="meeting-chat-panel" className="fixed inset-x-0 bottom-0 z-30 flex h-[70vh] flex-col rounded-t-3xl border-t border-white/10 bg-[#0b1324]/95 shadow-2xl backdrop-blur lg:static lg:h-auto lg:w-[360px] lg:shrink-0 lg:rounded-none lg:border-l lg:border-t-0 lg:bg-[#0b1324]/70">
      <div className="flex items-center gap-2 px-4 py-3">
        <span className="mx-auto mb-1 block h-1 w-10 rounded-full bg-white/20 lg:hidden" />
      </div>
      <div className="-mt-3 flex items-center gap-2 px-4 pb-3">
        <MessageSquare size={16} className="text-[#8FB0FF]" />
        <span className="text-sm font-bold text-white">Chat Meeting</span>
        <span className="hidden text-[11px] text-white/40 sm:inline">teks & data dari asisten</span>
        <button onClick={onClose} data-testid="meeting-chat-close" className="ml-auto rounded-lg p-1.5 text-white/60 transition hover:bg-white/10 hover:text-white"><X size={16} /></button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 pb-3" data-testid="meeting-chat-list">
        {items.length === 0 && !pending && (
          <div className="mt-10 px-4 text-center text-xs leading-relaxed text-white/40" data-testid="meeting-chat-empty">
            Belum ada pesan. Ketik pertanyaan di sini — asisten menjawab dalam teks (tabel, kode, tautan, video) tanpa mengganggu pembicaraan.
          </div>
        )}
        {items.map((m) => <Bubble key={m.id} m={m} me={m.role === "user"} />)}
        {pending && <Bubble m={pending} me />}
        {live && (
          <div className="mr-3 rounded-2xl bg-white/[0.07] px-3.5 py-2.5 text-sm text-white/90" data-testid="mc-live">
            <div className="mb-1 text-[10px] font-bold uppercase tracking-wider opacity-60">{live.name || "Asisten"}</div>
            {live.text ? <div className={MD_DARK}><Markdown content={live.text} /></div> : <span className="inline-flex gap-1"><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-white/60" /><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-white/60" style={{ animationDelay: ".15s" }} /><span className="h-1.5 w-1.5 animate-bounce rounded-full bg-white/60" style={{ animationDelay: ".3s" }} /></span>}
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="border-t border-white/10 p-3">
        {atts.length > 0 && <div className="mb-2 flex flex-wrap gap-1.5">{atts.map((a, k) => <span key={k} className="flex items-center gap-1 rounded-lg bg-white/10 px-2 py-1 text-[11px] text-white/80">{a.type === "image" ? <ImageIcon size={11} /> : <FileText size={11} />}{a.name}<button onClick={() => setAtts((x) => x.filter((_, i) => i !== k))} className="ml-1 text-white/50 hover:text-white"><X size={11} /></button></span>)}</div>}
        <div className="flex items-end gap-2">
          <button onClick={() => fileRef.current?.click()} data-testid="meeting-chat-attach" title="Lampirkan" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/10 text-white/70 transition hover:bg-white/15 hover:text-white"><Paperclip size={16} /></button>
          <input ref={fileRef} type="file" hidden multiple accept="image/*,.pdf,.txt,.md,.csv" onChange={pick} />
          <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={1} data-testid="meeting-chat-input" placeholder="Ketik pesan… (Enter kirim)"
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            className="max-h-28 min-h-10 flex-1 resize-none rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white placeholder:text-white/35 focus:border-[#2F6BFF]/60 focus:outline-none" />
          <button onClick={send} disabled={busy || (!input.trim() && atts.length === 0)} data-testid="meeting-chat-send" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#2F6BFF] text-white transition hover:brightness-110 disabled:opacity-40">{busy ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}</button>
        </div>
      </div>
    </aside>
  );
}
