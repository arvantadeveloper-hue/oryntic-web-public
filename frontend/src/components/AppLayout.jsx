import React, { useState } from "react";
import { NavLink, useNavigate, Outlet } from "react-router-dom";
import { Home, Users, MessageSquare, Briefcase, Bell, Wallet, User, Shield, LogOut, Menu, X, Sparkles } from "lucide-react";
import { Logo } from "./Logo";
import { useAuth } from "../context/AuthContext";
import { useI18n } from "../i18n";
import { IncomingCall } from "./IncomingCall";

export function AppLayout() {
  const { user, logout } = useAuth();
  const { t, lang, setLang } = useI18n();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);

  const items = [
    { to: "/home", icon: Home, label: t("nav.home"), id: "home" },
    { to: "/personas", icon: Users, label: t("nav.personas"), id: "personas" },
    { to: "/chat", icon: MessageSquare, label: t("nav.chat"), id: "chat" },
    { to: "/workspace", icon: Briefcase, label: t("nav.workspace"), id: "workspace" },
    { to: "/reminders", icon: Bell, label: t("nav.reminders"), id: "reminders" },
    { to: "/wallet", icon: Wallet, label: t("nav.wallet"), id: "wallet" },
    { to: "/profile", icon: User, label: t("nav.profile"), id: "profile" },
  ];
  if (user?.role === "admin") items.push({ to: "/admin", icon: Shield, label: t("nav.admin"), id: "admin" });

  const handleLogout = () => { logout(); nav("/"); };

  const SidebarInner = (
    <div className="flex h-full flex-col">
      <div className="px-5 py-5"><Logo /></div>
      <nav className="flex-1 space-y-1 px-3">
        {items.map((it) => (
          <NavLink
            key={it.id}
            to={it.to}
            data-testid={`nav-${it.id}`}
            onClick={() => setOpen(false)}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition ${
                isActive ? "text-white" : "text-slate-400 hover:text-white hover:bg-[#1C2D5A]"
              }`
            }
            style={({ isActive }) => isActive ? { background: "linear-gradient(135deg, rgba(0,209,255,.18), rgba(124,58,237,.22))", border: "1px solid rgba(0,209,255,.3)" } : {}}
          >
            <it.icon size={18} /> {it.label}
          </NavLink>
        ))}
      </nav>
      <div className="p-3">
        <div className="mb-2 flex items-center justify-center gap-1 rounded-xl bg-[#0e1830] p-1 text-xs">
          {["id", "en"].map((l) => (
            <button key={l} data-testid={`lang-${l}`} onClick={() => setLang(l)}
              className={`flex-1 rounded-lg px-2 py-1.5 font-semibold uppercase transition ${lang === l ? "btn-grad" : "text-slate-400"}`}>
              {l}
            </button>
          ))}
        </div>
        <button onClick={handleLogout} data-testid="logout-btn"
          className="flex w-full items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium text-slate-400 transition hover:bg-[#1C2D5A] hover:text-white">
          <LogOut size={18} /> {t("nav.logout")}
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen mesh-bg">
      <aside className="hidden w-64 shrink-0 border-r border-[rgba(0,209,255,0.1)] glass md:block">{SidebarInner}</aside>

      {/* mobile header */}
      <div className="fixed inset-x-0 top-0 z-30 flex h-16 items-center justify-between border-b border-[rgba(0,209,255,0.1)] glass px-4 md:hidden">
        <Logo size={30} />
        <button data-testid="mobile-menu-btn" onClick={() => setOpen(true)} className="text-white"><Menu /></button>
      </div>
      {open && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-0 h-full w-72 glass border-r border-[rgba(0,209,255,0.1)]">
            <button className="absolute right-3 top-4 text-slate-400" onClick={() => setOpen(false)}><X /></button>
            {SidebarInner}
          </div>
        </div>
      )}

      <main className="flex-1 pt-16 md:pt-0">
        <div className="hidden items-center justify-end gap-4 px-8 pt-5 md:flex">
          <div className="flex items-center gap-2 rounded-full border border-[rgba(0,209,255,0.25)] bg-[#0e1830] px-4 py-2 text-sm" data-testid="topbar-credits">
            <Sparkles size={15} className="text-[#00D1FF]" />
            <span className="font-semibold text-white">{user?.credits ?? 0}</span>
            <span className="text-slate-400">{t("common.credits")}</span>
          </div>
        </div>
        <Outlet />
      </main>

      <IncomingCall />
    </div>
  );
}
