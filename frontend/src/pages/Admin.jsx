import React, { useEffect, useState } from "react";
import { Users, Briefcase, MessageSquare, Sparkles, Bell, Server } from "lucide-react";
import { api } from "../lib/api";

export default function Admin() {
  const [tab, setTab] = useState("overview");
  const [ov, setOv] = useState(null);
  const [users, setUsers] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [pricing, setPricing] = useState(null);

  useEffect(() => {
    api.get("/admin/overview").then((r) => setOv(r.data)).catch(() => {});
    api.get("/admin/users").then((r) => setUsers(r.data)).catch(() => {});
    api.get("/admin/tasks").then((r) => setTasks(r.data)).catch(() => {});
    api.get("/admin/pricing").then((r) => setPricing(r.data)).catch(() => {});
  }, []);

  const stats = ov ? [
    { icon: Users, label: "Users", value: ov.users, c: "#00D1FF" },
    { icon: Sparkles, label: "Personas", value: ov.personas, c: "#7C3AED" },
    { icon: Briefcase, label: "Tasks", value: ov.tasks, c: "#06B6D4" },
    { icon: MessageSquare, label: "Conversations", value: ov.conversations, c: "#10B981" },
    { icon: Bell, label: "Reminders", value: ov.reminders, c: "#F59E0B" },
    { icon: Server, label: "Credits used", value: ov.credits_consumed, c: "#EF4444" },
  ] : [];

  return (
    <div className="mx-auto max-w-6xl p-5 sm:p-8 lg:p-10 fade-up" data-testid="admin-page">
      <h1 className="text-3xl font-extrabold text-white">Admin Console</h1>

      <div className="mt-5 flex gap-2 border-b border-[rgba(148,163,184,.15)]">
        {[["overview", "Overview"], ["users", "Users"], ["tasks", "Tasks"], ["pricing", "Pricing"]].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`admin-tab-${k}`}
            className={`-mb-px border-b-2 px-4 py-2.5 text-sm font-medium ${tab === k ? "border-[#00D1FF] text-white" : "border-transparent text-slate-400"}`}>{l}</button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {stats.map((s) => (
            <div key={s.label} className="aivora-card p-5">
              <s.icon size={20} style={{ color: s.c }} />
              <p className="mt-3 text-2xl font-extrabold text-white">{s.value}</p>
              <p className="text-xs text-slate-400">{s.label}</p>
            </div>
          ))}
        </div>
      )}

      {tab === "users" && (
        <div className="mt-6 aivora-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs uppercase text-slate-500"><th className="p-4">Name</th><th className="p-4">Email</th><th className="p-4">Role</th><th className="p-4">Credits</th></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-[rgba(148,163,184,.1)]" data-testid={`admin-user-${u.id}`}>
                  <td className="p-4 text-white">{u.name}</td><td className="p-4 text-slate-300">{u.email}</td>
                  <td className="p-4"><span className="rounded-full bg-[#1C2D5A] px-2 py-0.5 text-xs text-slate-300">{u.role}</span></td>
                  <td className="p-4 text-slate-300">{u.credits}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "tasks" && (
        <div className="mt-6 aivora-card overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs uppercase text-slate-500"><th className="p-4">Goal</th><th className="p-4">Status</th><th className="p-4">Credits</th></tr></thead>
            <tbody>
              {tasks.map((tk) => (
                <tr key={tk.id} className="border-t border-[rgba(148,163,184,.1)]">
                  <td className="max-w-md truncate p-4 text-white">{tk.goal}</td>
                  <td className="p-4 capitalize text-slate-300">{tk.status}</td>
                  <td className="p-4 text-slate-300">{tk.credits_used || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "pricing" && pricing && (
        <div className="mt-6 space-y-6">
          <div>
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">Credit Packages</h3>
            <div className="grid gap-4 sm:grid-cols-5">
              {pricing.packages.map((p) => (
                <div key={p.id} className="aivora-card p-4">
                  <p className="font-bold text-white">{p.name}</p>
                  <p className="text-sm text-slate-300">{p.credits} kredit</p>
                  <p className="text-xs text-slate-500">Rp {p.price_idr.toLocaleString("id-ID")}</p>
                  <p className="mt-1 text-xs text-[#00D1FF]">Margin {(p.margin * 100).toFixed(0)}%</p>
                </div>
              ))}
            </div>
          </div>
          <div>
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">Providers & Tariff</h3>
            <div className="aivora-card p-5 text-sm text-slate-300">
              {pricing.providers.map((pr, i) => (
                <div key={i} className="flex items-center justify-between border-b border-[rgba(148,163,184,.1)] py-2 last:border-0">
                  <span>{pr.provider} · <span className="text-slate-500">{pr.model}</span></span>
                  <span className="rounded-full bg-[#10B981]/20 px-2 py-0.5 text-xs text-[#10B981]">{pr.status}</span>
                </div>
              ))}
              <p className="mt-3 text-xs text-slate-500">Metode: {pricing.tariff.method}. Teks: {pricing.tariff.text_credits_per_1k_chars} kredit/1k char · Gambar: {pricing.tariff.image_generation_credits} kredit · Profil: {pricing.tariff.profile_generation_credits} kredit.</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
