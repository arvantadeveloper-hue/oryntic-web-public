import React, { useEffect, useState } from "react";
import { NavLink, Navigate, Outlet, Route, Routes, useNavigate } from "react-router-dom";
import { LayoutDashboard, Percent, Package, Users, ShieldCheck, Timer, LogOut, Loader2, Lock } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "../../context/AuthContext";
import { api } from "../../lib/api";
import PlatformDashboard from "./PlatformDashboard";
import PlatformPricing from "./PlatformPricing";
import PlatformPackages from "./PlatformPackages";
import PlatformUsers from "./PlatformUsers";
import PlatformStaff from "./PlatformStaff";
import PlatformTrial from "./PlatformTrial";

// Separate back-office site (future admin.oryntix.com). Menu depends on the staff role: super_admin = everything, finance = reports only.
const NAV = [
  { to: "/platform", end: true, icon: LayoutDashboard, label: "Dasbor", roles: ["super_admin", "finance"] },
  { to: "/platform/pricing", icon: Percent, label: "Tarif & Margin", roles: ["super_admin", "finance"] },
  { to: "/platform/packages", icon: Package, label: "Paket Kredit", roles: ["super_admin"] },
  { to: "/platform/users", icon: Users, label: "Pengguna", roles: ["super_admin", "finance"] },
  { to: "/platform/staff", icon: ShieldCheck, label: "Staf & Peran", roles: ["super_admin"] },
  { to: "/platform/trial", icon: Timer, label: "Trial & Batas", roles: ["super_admin"] },
];
export const ROLE_LABEL = { super_admin: "Super Admin", finance: "Finance" };

function PlatformLogin() {
  const { login } = useAuth();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try { const u = await login(email, password); if (!u.platform_role) toast.error("Akun ini bukan staf platform"); }
    catch (err) { toast.error(err?.response?.data?.detail?.message || err?.response?.data?.detail || "Login gagal"); } finally { setBusy(false); }
  };
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#070B18] p-6" data-testid="platform-login">
      <form onSubmit={submit} className="w-full max-w-sm rounded-3xl border border-white/10 bg-[#0B132B] p-8 text-white shadow-2xl">
        <div className="flex items-center gap-2"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#2F6BFF]"><Lock size={16} /></span><div><p className="text-sm font-black tracking-tight">Oryntix Platform</p><p className="text-[11px] text-white/50">Back-office · khusus staf</p></div></div>
        <input className="mt-6 w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm outline-none focus:border-[#2F6BFF]" type="email" placeholder="Email staf" value={email} onChange={(e) => setEmail(e.target.value)} required data-testid="platform-login-email" />
        <input className="mt-3 w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm outline-none focus:border-[#2F6BFF]" type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required data-testid="platform-login-password" />
        <button disabled={busy} className="btn-grad mt-5 w-full rounded-xl py-2.5 text-sm font-bold disabled:opacity-60" data-testid="platform-login-submit">{busy ? <Loader2 size={14} className="mx-auto animate-spin" /> : "Masuk"}</button>
      </form>
    </div>
  );
}

function Denied({ onLogout }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#070B18] p-6 text-center text-white" data-testid="platform-denied">
      <ShieldCheck size={36} className="text-rose-400" /><h1 className="mt-4 text-xl font-bold">Akses ditolak</h1>
      <p className="mt-1 max-w-sm text-sm text-white/60">Akun Anda tidak memiliki peran staf platform. Minta Super Admin menambahkan Anda di menu Staf & Peran.</p>
      <button onClick={onLogout} className="mt-6 rounded-xl border border-white/15 px-4 py-2 text-sm font-semibold hover:bg-white/5" data-testid="platform-denied-logout">Keluar</button>
    </div>
  );
}

function Shell() {
  const { user, logout } = useAuth(); const nav = useNavigate();
  const role = user.platform_role;
  const items = NAV.filter((n) => n.roles.includes(role));
  return (
    <div className="flex min-h-screen bg-[#F3F6FB]" data-testid="platform-shell">
      <aside className="flex w-60 shrink-0 flex-col bg-[#070B18] text-white">
        <div className="flex items-center gap-2 px-5 py-5"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#2F6BFF] text-sm font-black">O</span><div><p className="text-sm font-black tracking-tight">Oryntix Platform</p><p className="text-[10px] uppercase tracking-widest text-white/40">Back-office</p></div></div>
        <nav className="mt-2 flex-1 space-y-1 px-3">
          {items.map((n) => <NavLink key={n.to} to={n.to} end={n.end} data-testid={`pnav-${n.to.split("/").pop() || "dashboard"}`} className={({ isActive }) => `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors ${isActive ? "bg-[#2F6BFF] text-white" : "text-white/65 hover:bg-white/5 hover:text-white"}`}><n.icon size={17} /> {n.label}</NavLink>)}
        </nav>
        <div className="border-t border-white/10 p-4">
          <p className="truncate text-xs font-semibold">{user.name || user.email}</p>
          <p className="text-[11px] text-white/50" data-testid="platform-role-badge">{ROLE_LABEL[role]}</p>
          <button onClick={() => { logout(); nav("/platform"); }} className="mt-3 flex items-center gap-2 text-xs text-white/60 hover:text-white" data-testid="platform-logout"><LogOut size={13} /> Keluar</button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto p-6 lg:p-10"><Outlet context={{ role }} /></main>
    </div>
  );
}

export default function PlatformApp() {
  const { user, loading, logout } = useAuth();
  const [checked, setChecked] = useState(false);
  useEffect(() => { if (user?.platform_role) api.get("/platform/me").catch(() => {}).finally(() => setChecked(true)); else setChecked(true); }, [user]);
  if (loading || !checked) return <div className="flex min-h-screen items-center justify-center bg-[#070B18] text-white/60"><Loader2 className="animate-spin" /></div>;
  if (!user) return <PlatformLogin />;
  if (!user.platform_role) return <Denied onLogout={logout} />;
  const can = (roles) => roles.includes(user.platform_role);
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<PlatformDashboard />} />
        <Route path="pricing" element={<PlatformPricing readOnly={!can(["super_admin"])} />} />
        <Route path="packages" element={can(["super_admin"]) ? <PlatformPackages /> : <Navigate to="/platform" replace />} />
        <Route path="users" element={<PlatformUsers readOnly={!can(["super_admin"])} />} />
        <Route path="staff" element={can(["super_admin"]) ? <PlatformStaff /> : <Navigate to="/platform" replace />} />
        <Route path="trial" element={can(["super_admin"]) ? <PlatformTrial /> : <Navigate to="/platform" replace />} />
        <Route path="*" element={<Navigate to="/platform" replace />} />
      </Route>
    </Routes>
  );
}
