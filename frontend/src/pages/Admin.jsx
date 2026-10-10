import React, { useEffect, useState } from "react";
import { Users, Briefcase, MessageSquare, Sparkles, Bell, Server } from "lucide-react";
import { api } from "../lib/api";
import { SupportAgentCard } from "../components/SupportAgentCard";
import { PricingCatalogCard } from "../components/PricingCatalogCard";
import { ModelRoutingCard } from "../components/ModelRoutingCard";

export default function Admin() {
  const [tab, setTab] = useState("overview");
  const [ov, setOv] = useState(null);
  const [users, setUsers] = useState([]);
  const [tasks, setTasks] = useState([]);

  useEffect(() => {
    api.get("/admin/overview").then((r) => setOv(r.data)).catch(() => {});
    api.get("/admin/users").then((r) => setUsers(r.data)).catch(() => {});
    api.get("/admin/tasks").then((r) => setTasks(r.data)).catch(() => {});
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
      <h1 className="text-3xl font-extrabold text-slate-900">Admin Console</h1>

      <div className="mt-5 flex gap-2 border-b border-slate-200">
        {[["overview", "Ringkasan"], ["users", "Pengguna"], ["tasks", "Tugas"], ["catalog", "Pricing"], ["support", "Asisten Oryntix"]].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`admin-tab-${k}`}
            className={`-mb-px border-b-2 px-4 py-2.5 text-sm font-medium ${tab === k ? "border-[#00D1FF] text-slate-900" : "border-transparent text-slate-500"}`}>{l}</button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {stats.map((s) => (
            <div key={s.label} className="aivora-card p-5">
              <s.icon size={20} style={{ color: s.c }} />
              <p className="mt-3 text-2xl font-extrabold text-slate-900">{s.value}</p>
              <p className="text-xs text-slate-500">{s.label}</p>
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
                <tr key={u.id} className="border-t border-slate-200" data-testid={`admin-user-${u.id}`}>
                  <td className="p-4 text-slate-900">{u.name}</td><td className="p-4 text-slate-600">{u.email}</td>
                  <td className="p-4"><span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{u.role}</span></td>
                  <td className="p-4 text-slate-600">{u.credits}</td>
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
                <tr key={tk.id} className="border-t border-slate-200">
                  <td className="max-w-md truncate p-4 text-slate-900">{tk.goal}</td>
                  <td className="p-4 capitalize text-slate-600">{tk.status}</td>
                  <td className="p-4 text-slate-600">{tk.credits_used || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "catalog" && (
        <div className="mt-6 space-y-6" data-testid="admin-catalog-tab">
          <PricingCatalogCard />
          <div>
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">Model Routing</h3>
            <ModelRoutingCard />
          </div>
        </div>
      )}

      {tab === "support" && (
        <div className="mt-6" data-testid="admin-support-tab"><SupportAgentCard /></div>
      )}

    </div>
  );
}
