import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, CheckCheck, Loader2, MessageSquare, ClipboardList, Users, Phone, Sparkles } from "lucide-react";
import { api } from "../lib/api";
import { onUserEvent } from "../lib/userEvents";

const ICON = { messages: MessageSquare, tasks: ClipboardList, friends: Users, calls: Phone, reminders: Bell, system: Sparkles };
const ago = (iso) => { const s = Math.max(0, (Date.now() - new Date(iso)) / 1000); return s < 60 ? "baru saja" : s < 3600 ? `${Math.floor(s / 60)} mnt` : s < 86400 ? `${Math.floor(s / 3600)} jam` : `${Math.floor(s / 86400)} hr`; };

// Bell + anchored popover. Fed by /notifications/feed (same log as FCM pushes) and refreshed live via the user WebSocket / foreground FCM.
export function NotificationBell() {
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [feed, setFeed] = useState(null);
  const box = useRef(null);
  const load = () => api.get("/notifications/feed").then((r) => setFeed(r.data)).catch(() => {});
  useEffect(() => { load(); const off = onUserEvent(["notification", "push", "reminder_due", "friend_request", "task_update", "incoming_call"], load); const t = setInterval(load, 120000); return () => { off(); clearInterval(t); }; }, []);
  useEffect(() => {
    if (!open) return undefined;
    load();
    const h = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    const k = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", h); window.addEventListener("keydown", k);
    return () => { document.removeEventListener("mousedown", h); window.removeEventListener("keydown", k); };
  }, [open]);
  const markAll = async () => { await api.post("/notifications/seen").catch(() => {}); load(); window.dispatchEvent(new Event("oryntix:badges")); };
  const go = (it) => { setOpen(false); nav(it.link || "/home"); };
  const unseen = feed?.unseen || 0;
  return (
    <div className="relative" ref={box}>
      <button className="relative flex h-10 w-10 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100" onClick={() => setOpen((o) => !o)} data-testid="topbar-bell" aria-label="Notifikasi">
        <Bell size={19} />
        {unseen > 0 && <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-[#EF4444] px-1 text-[10px] font-bold text-white ring-2 ring-white" data-testid="bell-unseen">{unseen > 9 ? "9+" : unseen}</span>}
      </button>
      {open && (
        <div className="fade-up absolute right-0 top-12 z-[80] w-[360px] max-w-[92vw] overflow-hidden rounded-2xl border border-[#E7ECF3] bg-white shadow-2xl" data-testid="notification-panel">
          <span className="absolute -top-1.5 right-4 h-3 w-3 rotate-45 border-l border-t border-[#E7ECF3] bg-white" />
          <div className="flex items-center justify-between border-b border-[#E7ECF3] px-4 py-3">
            <p className="text-sm font-bold text-slate-900">Notifikasi {unseen > 0 && <span className="ml-1 rounded-full bg-[#EEF3FF] px-2 py-0.5 text-[11px] font-bold text-[#2F6BFF]">{unseen} baru</span>}</p>
            <button onClick={markAll} className="flex items-center gap-1 text-xs font-semibold text-[#2F6BFF] hover:underline" data-testid="notif-mark-all"><CheckCheck size={13} /> Tandai semua dibaca</button>
          </div>
          <div className="max-h-[420px] overflow-y-auto" data-testid="notification-list">
            {feed === null && <p className="flex items-center gap-2 p-4 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p>}
            {feed && feed.items.length === 0 && <p className="p-6 text-center text-sm text-slate-400" data-testid="notif-empty">Belum ada notifikasi.</p>}
            {(feed?.items || []).map((it) => { const I = ICON[it.kind] || Sparkles; return (
              <button key={it.id} onClick={() => go(it)} className={`flex w-full items-start gap-3 px-4 py-3 text-left transition hover:bg-slate-50 ${it.read ? "" : "bg-[#EEF3FF]/50"}`} data-testid={`notif-item-${it.kind}`}>
                <span className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${it.read ? "bg-slate-100 text-slate-500" : "bg-[#2F6BFF] text-white"}`}><I size={14} /></span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-semibold text-slate-900">{it.title}</span>
                  {it.body && <span className="block truncate text-xs text-slate-500">{it.body}</span>}
                </span>
                <span className="shrink-0 text-[10px] text-slate-400">{ago(it.created_at)}</span>
              </button>
            ); })}
          </div>
          <button onClick={() => { setOpen(false); nav("/reminders"); }} className="w-full border-t border-[#E7ECF3] py-2.5 text-center text-xs font-semibold text-slate-600 hover:bg-slate-50" data-testid="notif-open-reminders">Buka Pengingat & Jadwal</button>
        </div>
      )}
    </div>
  );
}
