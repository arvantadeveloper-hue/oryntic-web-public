import React, { useState } from "react";
import { NavLink, useNavigate, Outlet } from "react-router-dom";
import { Home, MessageSquare, Bot, FileText, Bell, Wallet, User, Shield, LogOut, Menu, X, Sparkles, Search, HelpCircle, Crown, ChevronDown, Users } from "lucide-react";
import { Logo } from "./Logo";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n";
import { IncomingCall } from "./IncomingCall";

export function AppLayout() {
  const { user, logout } = useAuth();
  const { t, lang, setLang } = useI18n();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");

  const isAdmin = user?.role === "admin";
  const allItems = [
    { to: "/home", icon: Home, label: t("nav.home"), id: "home" },
    { to: "/chat", icon: MessageSquare, label: t("nav.chat"), id: "chat" },
    { to: "/personas", icon: Bot, label: "Agen AI", id: "personas", adminOnly: true },
    { to: "/workspace", icon: FileText, label: t("nav.workspace"), id: "workspace" },
    { to: "/reminders", icon: Bell, label: t("nav.reminders"), id: "reminders" },
    { to: "/wallet", icon: Wallet, label: t("nav.wallet"), id: "wallet", adminOnly: true },
    { to: "/profile", icon: User, label: t("nav.profile"), id: "profile" },
  ];
  const items = allItems.filter((it) => !it.adminOnly || isAdmin);
  if (isAdmin) {
    items.splice(3, 0, { to: "/team", icon: Users, label: "Tim", id: "team" });
    items.push({ to: "/admin", icon: Shield, label: t("nav.admin"), id: "admin" });
  }

  const handleLogout = () => { logout(); nav("/"); };
  const doSearch = (e) => { if (e.key === "Enter" && q.trim()) { nav("/chat"); } };

  const SidebarInner = (
    <div className="flex h-full flex-col">
      <div className="px-6 py-6"><Logo /></div>
      <nav className="flex-1 space-y-1.5 px-4">
        {items.map((it) => (
          <NavLink
            key={it.id}
            to={it.to}
            data-testid={`nav-${it.id}`}
            onClick={() => setOpen(false)}
            className={({ isActive }) =>
              `group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition ${
                isActive ? "bg-[#EEF3FF] text-[#2F6BFF]" : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span className={`flex h-8 w-8 items-center justify-center rounded-lg transition ${isActive ? "bg-white text-[#2F6BFF] shadow-sm" : "text-slate-400 group-hover:text-slate-700"}`}>
                  <it.icon size={18} />
                </span>
                {it.label}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="p-4">
        {isAdmin && (
          <div className="rounded-2xl p-4 text-white" style={{ background: "linear-gradient(135deg,#2F6BFF,#7C3AED)" }}>
            <Crown size={22} />
            <p className="mt-2 text-sm font-bold">Upgrade Plan</p>
            <p className="mt-0.5 text-xs text-white/80">Dapatkan lebih banyak kredit & fitur AI.</p>
            <button onClick={() => nav("/wallet")} data-testid="upgrade-btn" className="mt-3 w-full rounded-lg bg-white py-2 text-xs font-bold text-[#2F6BFF] transition hover:bg-white/90">Lihat Paket</button>
          </div>
        )}
        <button onClick={handleLogout} data-testid="logout-btn"
          className="mt-3 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-slate-500 transition hover:bg-slate-50 hover:text-slate-900">
          <LogOut size={18} /> {t("nav.logout")}
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen mesh-bg">
      <aside className="hidden w-64 shrink-0 border-r border-[#E7ECF3] bg-white md:block">{SidebarInner}</aside>

      {/* mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-0 h-full w-72 bg-white shadow-xl">
            <button className="absolute right-3 top-5 text-slate-400" onClick={() => setOpen(false)}><X /></button>
            {SidebarInner}
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* top header */}
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-[#E7ECF3] glass px-4 sm:px-6">
          <button className="text-slate-500 md:hidden" onClick={() => setOpen(true)} data-testid="mobile-menu-btn"><Menu /></button>
          <div className="relative hidden max-w-xl flex-1 sm:block">
            <Search size={17} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={doSearch} data-testid="top-search"
              placeholder="Tanyakan apa saja kepada Aivora..." className="w-full rounded-xl border border-[#E7ECF3] bg-slate-50 py-2.5 pl-11 pr-4 text-sm outline-none transition focus:border-[#2F6BFF] focus:bg-white" />
          </div>
          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            {isAdmin && (
              <button onClick={() => nav("/wallet")} className="flex items-center gap-1.5 rounded-full border border-[#E7ECF3] bg-white px-3 py-1.5 text-sm" data-testid="topbar-credits">
                <Sparkles size={15} className="text-[#2F6BFF]" />
                <span className="font-bold text-slate-900">{user?.credits ?? 0}</span>
              </button>
            )}
            <button className="relative hidden h-10 w-10 items-center justify-center rounded-full border border-[#E7ECF3] bg-white text-slate-500 sm:flex" onClick={() => nav("/reminders")}>
              <Bell size={18} /><span className="absolute right-2.5 top-2.5 h-2 w-2 rounded-full bg-[#EF4444]" />
            </button>
            <button onClick={() => nav("/profile")} className="flex items-center gap-2.5 rounded-full border border-[#E7ECF3] bg-white py-1.5 pl-1.5 pr-3" data-testid="topbar-user">
              <span className="flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold text-white" style={{ background: "linear-gradient(135deg,#2F6BFF,#7C3AED)" }}>{(user?.name || "U")[0].toUpperCase()}</span>
              <span className="hidden text-left leading-tight sm:block">
                <span className="block text-xs font-bold text-slate-900">{user?.name}</span>
                <span className="block text-[11px] text-slate-400">Workspace</span>
              </span>
              <ChevronDown size={14} className="hidden text-slate-400 sm:block" />
            </button>
          </div>
        </header>

        <main className="min-w-0 flex-1"><Outlet /></main>
      </div>

      <IncomingCall />
    </div>
  );
}
