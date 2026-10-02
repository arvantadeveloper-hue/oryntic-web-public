import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2, ChevronDown, Check, X, Mail, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";

// Sidebar block: active workspace picker + pending team invitations (accept / reject in-app).
export function WorkspaceSwitcher() {
  const { user, switchWorkspace, refreshUser, applyAuth } = useAuth();
  const nav = useNavigate();
  const [spaces, setSpaces] = useState([]);
  const [invites, setInvites] = useState([]);
  const [busy, setBusy] = useState(null);

  const load = () => {
    api.get("/auth/workspaces").then((r) => setSpaces(r.data)).catch(() => {});
    api.get("/team/my-invites").then((r) => setInvites(r.data)).catch(() => {});
  };
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, [user?.owner_id]);

  const change = async (wid) => {
    if (wid === user?.owner_id) return;
    setBusy("switch");
    try { await switchWorkspace(wid); toast.success("Workspace diganti"); nav("/home"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal berpindah workspace"); } finally { setBusy(null); }
  };

  const respond = async (inv, action) => {
    setBusy(inv.id);
    try {
      const r = await api.post(`/team/my-invites/${inv.id}/${action}`);
      if (action === "accept") { applyAuth(r.data); toast.success(`Bergabung ke workspace ${inv.workspace_name}`); nav("/home"); }
      else { toast.message("Undangan ditolak"); await refreshUser(); }
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menanggapi undangan"); } finally { setBusy(null); }
  };

  const active = spaces.find((s) => s.active);
  return (
    <div className="px-3 pb-2" data-testid="workspace-switcher">
      <label className="relative flex items-center gap-2 rounded-xl bg-white/[0.06] px-3 py-2 text-xs text-white/80">
        <Building2 size={14} className="shrink-0 text-[#8FB0FF]" />
        <select value={user?.owner_id || ""} onChange={(e) => change(e.target.value)} disabled={busy === "switch"} data-testid="workspace-select"
          className="min-w-0 flex-1 appearance-none bg-transparent pr-5 text-sm font-semibold text-white outline-none [&>option]:text-slate-900">
          {spaces.length === 0 && <option value={user?.owner_id || ""}>{user?.name || "Workspace"}</option>}
          {spaces.map((s) => <option key={s.id} value={s.id}>{s.is_home ? `${s.name} (milik saya)` : s.name}</option>)}
        </select>
        <ChevronDown size={14} className="pointer-events-none absolute right-3 text-white/50" />
      </label>
      {active && !active.is_home && <p className="mt-1 px-1 text-[10px] text-white/45">Anda anggota di workspace {active.owner_email}</p>}
      {invites.length > 0 && (
        <div className="mt-2 space-y-1.5" data-testid="pending-invites">
          {invites.map((inv) => (
            <div key={inv.id} className="rounded-xl border border-amber-400/30 bg-amber-400/10 p-2.5 text-xs text-white" data-testid={`pending-invite-${inv.id}`}>
              <p className="flex items-center gap-1.5 font-semibold"><Mail size={12} className="text-amber-300" /> Undangan tim</p>
              <p className="mt-0.5 text-white/75"><b>{inv.inviter_name}</b> mengundang Anda ke workspace <b>{inv.workspace_name}</b></p>
              <div className="mt-2 flex gap-1.5">
                <button onClick={() => respond(inv, "accept")} disabled={busy === inv.id} className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-emerald-500 py-1.5 font-bold text-white hover:brightness-110" data-testid={`invite-accept-${inv.id}`}>{busy === inv.id ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />} Bergabung</button>
                <button onClick={() => respond(inv, "reject")} disabled={busy === inv.id} className="flex items-center justify-center gap-1 rounded-lg bg-white/10 px-2.5 py-1.5 font-semibold hover:bg-white/20" data-testid={`invite-reject-${inv.id}`}><X size={12} /> Tolak</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
