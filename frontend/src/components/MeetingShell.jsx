import React, { useState } from "react";
import { LayoutGrid, MessageSquareText, Columns2, Gavel, Mic, Loader2 } from "lucide-react";
import { Popover, PopoverTrigger, PopoverContent } from "./ui/popover";

const KEY = "aivora_meeting_layout";
export const LAYOUTS = [
  { id: "tiles", label: "Peserta utama", hint: "Tile besar, chat di panel kanan", Icon: LayoutGrid },
  { id: "chat", label: "Chat utama", hint: "Chat memenuhi layar, peserta di kolom kanan", Icon: MessageSquareText },
  { id: "split", label: "Sejajar", hint: "Peserta dan chat berdampingan 50:50", Icon: Columns2 },
];

export function useMeetingLayout() {
  const [layout, setLayoutState] = useState(() => (LAYOUTS.some((l) => l.id === localStorage.getItem(KEY)) ? localStorage.getItem(KEY) : "tiles"));
  const setLayout = (v) => { localStorage.setItem(KEY, v); setLayoutState(v); };
  return [layout, setLayout];
}

export function LayoutMenu({ layout, onChange }) {
  const [open, setOpen] = useState(false);
  const cur = LAYOUTS.find((l) => l.id === layout) || LAYOUTS[0];
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button data-testid="layout-btn" title={`Layout: ${cur.label}`} className={`flex h-14 w-14 items-center justify-center rounded-full text-white transition ${open ? "bg-white/25" : "bg-white/10 hover:bg-white/20"}`}><cur.Icon size={22} /></button>
      </PopoverTrigger>
      <PopoverContent side="top" align="center" sideOffset={12} className="z-[120] w-72 rounded-2xl border-white/10 bg-[#0f172a] p-2 text-white shadow-2xl" data-testid="layout-menu">
        <p className="px-2 pb-1 pt-1 text-[11px] font-bold uppercase tracking-wider text-white/50">Tata letak panggilan</p>
        {LAYOUTS.map((l) => (
          <button key={l.id} data-testid={`layout-opt-${l.id}`} onClick={() => { onChange(l.id); setOpen(false); }}
            className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition ${layout === l.id ? "bg-[#2F6BFF] text-white" : "hover:bg-white/10"}`}>
            <l.Icon size={18} className="shrink-0" />
            <span className="min-w-0"><span className="block text-sm font-semibold">{l.label}</span><span className={`block text-[11px] ${layout === l.id ? "text-white/80" : "text-white/50"}`}>{l.hint}</span></span>
          </button>
        ))}
      </PopoverContent>
    </Popover>
  );
}

const STATUS_LABEL = { speaking: "Berbicara", thinking: "Berpikir...", listening: "Mendengarkan" };

function RailItem({ p, compact }) {
  const speaking = p.status === "speaking";
  return (
    <div data-testid={`rail-${p.isMe ? "me" : p.isMod ? "mod" : p.name}`} className={`flex items-center gap-3 rounded-xl px-2 py-2 transition ${speaking ? "bg-emerald-400/10" : ""} ${compact ? "flex-col gap-1 px-1 py-1 text-center" : ""}`}>
      <span className={`relative flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-full border-2 ${speaking ? "border-emerald-400" : p.status === "thinking" ? "border-amber-300/70" : "border-white/10"}`}
        style={{ background: p.isMod ? "linear-gradient(135deg,#0B132B,#1f2a4d)" : "linear-gradient(135deg,#2F6BFF,#7C3AED)" }}>
        {p.portrait ? <img src={p.portrait} alt="" className="h-full w-full object-cover" /> : p.isMod ? <Gavel size={18} className="text-white/90" /> : <span className="text-base font-bold text-white">{(p.name || "?")[0].toUpperCase()}</span>}
      </span>
      <span className="min-w-0">
        <span className="flex items-center gap-1 truncate text-xs font-semibold text-white">{p.isMe && <Mic size={11} className={p.level > 0.06 ? "text-emerald-400" : "text-white/60"} />}{p.isMe ? "Anda" : p.name}</span>
        {!compact && <span className={`flex items-center gap-1 text-[11px] ${speaking ? "text-emerald-300" : "text-white/45"}`}>{p.status === "thinking" && <Loader2 size={10} className="animate-spin" />}{STATUS_LABEL[p.status] || "—"}</span>}
      </span>
    </div>
  );
}

export function ParticipantRail({ participants, caption }) {
  return (
    <>
      <aside data-testid="participant-rail" className="hidden w-[280px] shrink-0 flex-col border-l border-white/10 bg-[#0b1324]/60 lg:flex">
        <p className="px-4 pb-1 pt-4 text-[11px] font-bold uppercase tracking-wider text-white/50">Peserta · {participants.length}</p>
        <div className="flex-1 space-y-1 overflow-y-auto px-2">{participants.map((p) => <RailItem key={p.id} p={p} />)}</div>
        {caption && <div className="border-t border-white/10 p-3">{caption}</div>}
      </aside>
      <div className="flex gap-1 overflow-x-auto border-b border-white/10 px-2 py-1 lg:hidden" data-testid="participant-strip">{participants.map((p) => <RailItem key={p.id} p={p} compact />)}</div>
    </>
  );
}

// Arranges stage (tiles/avatar), caption, controls and the chat panel according to the chosen layout.
export function MeetingShell({ layout, chatOpen, stage, caption, controls, chat, participants }) {
  if (layout === "chat") {
    return (
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row" data-testid="meeting-shell" data-layout="chat">
        <div className="order-2 flex min-h-0 flex-1 flex-col lg:order-1">{chat("main")}{controls}</div>
        <div className="order-1 flex min-h-0 lg:order-2"><ParticipantRail participants={participants} caption={caption} /></div>
      </div>
    );
  }
  if (layout === "split") {
    return (
      <div className="flex min-h-0 flex-1" data-testid="meeting-shell" data-layout="split">
        <div className="flex min-h-0 flex-1 flex-col lg:w-1/2 lg:flex-none">{stage}{caption}{controls}</div>
        <div className="hidden min-h-0 flex-1 border-l border-white/10 lg:flex">{chat("main")}</div>
        {chatOpen && <div className="lg:hidden">{chat("side")}</div>}
      </div>
    );
  }
  return (
    <div className="flex min-h-0 flex-1" data-testid="meeting-shell" data-layout="tiles">
      <div className="flex min-h-0 flex-1 flex-col">{stage}{caption}{controls}</div>
      {chatOpen && chat("side")}
    </div>
  );
}
