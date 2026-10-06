import React, { useState, useEffect } from "react";
import { NavLink, useNavigate, Outlet } from "react-router-dom";
import { Share2, Home, MessageSquare, Bot, FileText, Bell, Wallet, User, Shield, LogOut, Menu, X, Sparkles, Search, HelpCircle, Plug, Plus, Settings, CalendarDays, Images, Archive, Users } from "lucide-react";
import { Logo } from "./Logo";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import { useI18n } from "../i18n";
import { IncomingCall } from "./IncomingCall";
import { FriendCallRing } from "./FriendCallRing";
import { TaskNotifier } from "./TaskChatTools";
import { UpgradePlanDialog } from "./UpgradePlanDialog";
import { NotificationBell } from "./NotificationBell";
import { registerAssetWorker } from "../lib/firebase";
import { WelcomeTour, openTour } from "./WelcomeTour";
import { PublishHost } from "./PublishDialog";
import { SoundToggleButton } from "./SoundToggle";
import { onUserEvent, useLiveSync, useWsConnected } from "../lib/userEvents";

export function AppLayout() {
  const { user, logout } = useAuth();
  const { t } = useI18n();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [badges, setBadges] = useState({ friend_requests: 0, unread_chats: 0 });
  useEffect(() => { registerAssetWorker(); }, []);
  // badges ride on every WebSocket event (ev.badges); GET only while the socket is down / after resume
  useEffect(() => { if (!user) return undefined; return onUserEvent(["message_new", "friend_request", "notification", "reminder_due", "incoming_call", "task_update", "archived"], (ev) => { if (ev.badges) setBadges(ev.badges); }); }, [user]);
  useLiveSync(() => { if (!user) return; api.get("/notifications/badges").then((r) => setBadges(r.data)).catch(() => {}); }, [], 60000, [user?.id]);
  useEffect(() => {
    if (!user) return undefined;
    const pull = () => api.get("/notifications/badges").then((r) => setBadges(r.data)).catch(() => {});
    window.addEventListener("oryntix:badges", pull);
    return () => window.removeEventListener("oryntix:badges", pull);
  }, [user]);
  const badgeOf = (id) => (id === "friends" ? badges.friend_requests : id === "chat" ? badges.unread_chats : 0);

  const isAdmin = user?.role === "admin";
  const allItems = [
    { to: "/home", icon: Home, label: "Dashboard", id: "home" },
    { to: "/chat", icon: MessageSquare, label: t("nav.chat"), id: "chat" },
    { to: "/personas", icon: Bot, label: "AI Agents", id: "personas", adminOnly: true },
    { to: "/workspace", icon: FileText, label: t("nav.workspace"), id: "workspace" },
    { to: "/reminders", icon: Bell, label: t("nav.reminders"), id: "reminders" },
    { to: "/calendar", icon: CalendarDays, label: "Kalender", id: "calendar" },
    { to: "/gallery", icon: Images, label: "Galeri", id: "gallery" },
    { to: "/integrations", icon: Plug, label: "Integrasi", id: "integrations" },
    { to: "/social", icon: Share2, label: "Social Media", id: "social" },
    { to: "/archives", icon: Archive, label: "Arsip", id: "archives" },
    { to: "/friends", icon: Users, label: "Teman", id: "friends" },
    { to: "/wallet", icon: Wallet, label: t("nav.wallet"), id: "wallet", adminOnly: true },
    { to: "/profile", icon: Settings, label: "Settings", id: "profile" },
  ];
  const items = allItems.filter((it) => !it.adminOnly || isAdmin);
  if (user?.platform_role) items.push({ to: "/platform", icon: Shield, label: "Oryntix Platform", id: "platform" });
  if (user?.is_platform_admin) items.push({ to: "/admin", icon: Shield, label: t("nav.admin"), id: "admin" });

  const handleLogout = () => { logout(); nav("/"); };
  const doSearch = (e) => { if (e.key === "Enter" && q.trim()) { nav("/chat"); } };
  const credits = user?.credits ?? 0;
  const pct = Math.min(100, Math.round((credits / Math.max(user?.credits_cap || credits || 1, 1)) * 100));
  const [showUpgrade, setShowUpgrade] = useState(false);

  const SidebarInner = (
    <div className="flex h-full flex-col sidebar-dark text-white">
      <div className="px-5 pb-3 pt-6"><Logo light size={32} /></div>
      <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto px-3">
        {items.map((it) => (
          <NavLink key={it.id} to={it.to} data-testid={`nav-${it.id}`} onClick={() => setOpen(false)}
            className={({ isActive }) => `nav-item flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] font-medium md:text-sm ${isActive ? "active" : ""}`}>
            <it.icon size={18} className="nav-ico" />
            <span className="flex-1">{it.label}</span>
            {badgeOf(it.id) > 0 && <span className="flex h-5 min-w-[20px] items-center justify-center rounded-full bg-[#EF4444] px-1.5 text-[11px] font-bold text-white" data-testid={`badge-${it.id}`}>{badgeOf(it.id) > 99 ? "99+" : badgeOf(it.id)}</span>}
          </NavLink>
        ))}
      </nav>
      <div className="shrink-0 p-3">
        {isAdmin && (
          <div className="rounded-2xl bg-white/[0.06] p-4" data-testid="sidebar-usage">
            <p className="text-xs font-medium text-white/70">Workspace Usage</p>
            <div className="mt-3 flex items-center gap-3">
              <span className="relative flex h-12 w-12 items-center justify-center rounded-full" style={{ background: `conic-gradient(#2F6BFF ${pct}%, rgba(255,255,255,.12) 0)` }}>
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#0F1A3A] text-[10px] font-bold">{pct}%</span>
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{credits} <span className="text-xs font-normal text-white/60">kredit</span></p>
                <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-[#2F6BFF]" style={{ width: `${pct}%` }} /></div>
              </div>
            </div>
            <button type="button" onClick={() => { setOpen(false); setShowUpgrade(true); }} data-testid="upgrade-btn" className="mt-3 w-full rounded-lg bg-white/10 py-2 text-xs font-semibold transition hover:bg-white/15">{user?.plan === "trial" ? "Upgrade Plan" : "Tambah Kredit"}</button>
          </div>
        )}
        <div className="mt-3 flex items-center gap-2.5 rounded-xl px-2 py-2">
          <button onClick={() => nav("/profile")} className="flex min-w-0 flex-1 items-center gap-2.5 text-left" data-testid="sidebar-user">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-bold text-white" style={{ background: "linear-gradient(135deg,#2F6BFF,#7C3AED)" }}>{(user?.name || "U")[0].toUpperCase()}</span>
            <span className="min-w-0 leading-tight">
              <span className="block truncate text-sm font-semibold">{user?.name}</span>
              <span className="block truncate text-[11px] text-white/55">{user?.is_platform_admin ? "Platform Admin" : isAdmin ? (user?.plan === "trial" ? "Workspace Owner · Trial" : "Workspace Owner") : "Member"}</span>
            </span>
          </button>
          <button onClick={handleLogout} data-testid="logout-btn" title={t("nav.logout")} className="flex h-8 w-8 items-center justify-center rounded-lg text-white/60 transition hover:bg-white/10 hover:text-white"><LogOut size={16} /></button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen mesh-bg">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 md:block">{SidebarInner}</aside>

      {open && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-0 h-full w-72 shadow-xl">
            <button className="absolute right-3 top-5 z-10 text-white/70" onClick={() => setOpen(false)}><X /></button>
            {SidebarInner}
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-[#E6EAF2] glass px-4 sm:px-6">
          <button className="text-slate-500 md:hidden" onClick={() => setOpen(true)} data-testid="mobile-menu-btn"><Menu /></button>
          <div className="relative hidden max-w-xl flex-1 sm:block">
            <Search size={17} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={doSearch} data-testid="top-search"
              placeholder="Search anything... (agents, projects, documents)" className="w-full rounded-xl border border-transparent bg-[#EEF1F7] py-2.5 pl-11 pr-4 text-sm outline-none transition focus:border-[#2F6BFF] focus:bg-white" />
          </div>
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            {isAdmin && (
              <button onClick={() => nav("/wallet")} className="hidden h-10 items-center gap-1.5 rounded-full border border-[#E6EAF2] bg-white px-3 text-sm sm:flex" data-testid="topbar-credits">
                <Sparkles size={15} className="text-[#2F6BFF]" />
                <span className="font-bold text-slate-900">{credits}</span>
              </button>
            )}
            <button onClick={openTour} data-testid="help-tour-btn" className="hidden h-10 w-10 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100 sm:flex" title="Bantuan — tur singkat"><HelpCircle size={19} /></button>
            <ConnectionDot />
            <SoundToggleButton />
            <NotificationBell />
            <WelcomeTour user={user} />
            <button onClick={() => nav("/chat")} className="btn-primary h-10 rounded-xl px-3.5 sm:px-4" data-testid="topbar-new"><Plus size={16} /> <span className="hidden sm:inline">New</span></button>
            <button onClick={() => nav("/profile")} className="flex h-10 w-10 items-center justify-center rounded-full text-sm font-bold text-white" style={{ background: "linear-gradient(135deg,#2F6BFF,#7C3AED)" }} data-testid="topbar-user">{(user?.name || "U")[0].toUpperCase()}</button>
          </div>
        </header>

        <main className="min-w-0 flex-1"><Outlet /></main>
      </div>

      <IncomingCall />
      <FriendCallRing />
      <TaskNotifier />
      {showUpgrade && <UpgradePlanDialog onClose={() => setShowUpgrade(false)} />}
      <PublishHost />
    </div>
  );
}


// Realtime status: green = WebSocket live (push mode), amber pulsing = reconnecting (temporary GET fallback).
function ConnectionDot() {
  const on = useWsConnected();
  return (
    <span title={on ? "Realtime terhubung — pembaruan langsung via WebSocket" : "Menyambung ulang… sementara memakai pembaruan berkala"} data-testid="ws-status-dot"
      data-state={on ? "connected" : "reconnecting"} className="flex items-center gap-1.5 rounded-full border border-[#E7ECF3] bg-white px-2 py-1 text-[11px] font-semibold text-slate-500">
      <span className={`h-2 w-2 rounded-full ${on ? "bg-emerald-500" : "bg-amber-400 animate-pulse"}`} />
      <span className="hidden sm:inline">{on ? "Terhubung" : "Menyambung ulang…"}</span>
    </span>
  );
}
