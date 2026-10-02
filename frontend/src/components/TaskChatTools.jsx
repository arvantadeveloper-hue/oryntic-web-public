import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ClipboardList, ExternalLink, Bot, Plus, Check } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

// Workspace task pinned at the top of a task-linked chat so the discussion stays on topic.
export function TaskContextCard({ taskId, refreshKey }) {
  const nav = useNavigate();
  const [task, setTask] = useState(null);
  useEffect(() => { if (taskId) api.get(`/tasks/${taskId}`).then((r) => setTask(r.data)).catch(() => setTask(null)); }, [taskId, refreshKey]);
  if (!task) return null;
  const status = { completed: ["#10B981", "Selesai"], running: ["#8B5CF6", "Berjalan"], queued: ["#F59E0B", "Antre"], failed: ["#EF4444", "Gagal"], scheduled: ["#2F6BFF", "Terjadwal"] }[task.status] || ["#94A3B8", task.status];
  return (
    <div className="mx-auto mb-3 w-full max-w-3xl rounded-2xl border border-[#2F6BFF]/25 bg-[#EEF3FF] p-3.5" data-testid="task-context-card">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#2F6BFF] text-white"><ClipboardList size={17} /></span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-bold uppercase tracking-wider text-[#2F6BFF]">Tugas Ruang Kerja · v{task.version}</p>
          <p className="truncate text-sm font-semibold text-slate-900" data-testid="task-context-title">{task.goal}</p>
          <p className="mt-0.5 line-clamp-2 text-xs text-slate-500">{(task.revision_note || task.summary || (task.final_output || "").slice(0, 160)).replace(/\*\*/g, "")}</p>
        </div>
        <span className="shrink-0 rounded-full px-2.5 py-1 text-[11px] font-bold" style={{ background: `${status[0]}22`, color: status[0] }}>{status[1]}</span>
      </div>
      <div className="mt-2 flex items-center justify-between text-xs">
        <span className="text-slate-500">Minta perubahan di chat ini → revisi tersimpan otomatis sebagai versi baru.</span>
        <button onClick={() => nav(`/workspace/${task.id}`)} className="flex items-center gap-1 font-semibold text-[#2F6BFF]" data-testid="task-context-open"><ExternalLink size={12} /> Buka di Ruang Kerja</button>
      </div>
    </div>
  );
}

// "+ Asisten": invite another persona into the current conversation.
export function AddPersonaMenu({ conv, personas, onAdded }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState("");
  const inConv = new Set((conv.persona_ids || []).concat((conv.members || []).map((m) => m.id)));
  const options = (personas || []).filter((p) => !inConv.has(p.id));
  const add = async (p) => {
    setBusy(p.id);
    try { const r = await api.post(`/conversations/${conv.id}/personas`, { persona_id: p.id }); toast.success(`${p.name} bergabung`); setOpen(false); onAdded(r.data); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menambah asisten"); } finally { setBusy(""); }
  };
  return (
    <div className="relative">
      <button onClick={() => setOpen((o) => !o)} title="Undang asisten lain ke percakapan ini" data-testid="add-persona-btn" className="flex h-9 items-center gap-1.5 rounded-lg border border-[#E6EAF2] bg-white px-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 sm:px-3"><Bot size={15} /><Plus size={12} /> <span className="hidden sm:inline">Asisten</span></button>
      {open && (
        <div className="absolute right-0 top-11 z-40 w-64 rounded-2xl border border-[#E7ECF3] bg-white p-2 shadow-xl" data-testid="add-persona-menu">
          <p className="px-2 py-1 text-[11px] font-bold uppercase tracking-wider text-slate-400">Undang asisten</p>
          {options.length === 0 && <p className="px-2 py-2 text-xs text-slate-500">Semua asisten sudah ada di percakapan ini.</p>}
          {options.map((p) => (
            <button key={p.id} onClick={() => add(p)} disabled={!!busy} data-testid={`add-persona-${p.id}`} className="flex w-full items-center gap-2 rounded-xl px-2 py-2 text-left text-sm hover:bg-slate-50 disabled:opacity-60">
              {p.portrait ? <img src={p.portrait} alt="" className="h-7 w-7 rounded-full object-cover" /> : <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[#2F6BFF] text-xs font-bold text-white">{(p.name || "A")[0]}</span>}
              <span className="min-w-0 flex-1 truncate font-semibold text-slate-800">{p.name}</span>
              {busy === p.id ? <span className="text-xs text-slate-400">...</span> : <Check size={14} className="text-slate-300" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// Quick replies under the assistant's offer: "bahas satu per satu" vs "terima beres".
export function TaskOfferButtons({ m, cid, onDone, isLast }) {
  const [busy, setBusy] = useState("");
  if (m.tool !== "task_offer" || !isLast) return null;
  const pick = async (mode) => {
    setBusy(mode);
    try { await api.post(`/conversations/${cid}/tasks/accept`, { mode }); onDone && onDone(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal"); } finally { setBusy(""); }
  };
  return (
    <div className="mt-2 flex flex-wrap gap-2" data-testid="task-offer-buttons">
      <button onClick={() => pick("discuss")} disabled={!!busy} className="rounded-full border border-[#2F6BFF]/40 bg-white px-4 py-1.5 text-xs font-bold text-[#2F6BFF] hover:bg-[#EEF3FF] disabled:opacity-60" data-testid="task-offer-discuss">{busy === "discuss" ? "..." : "Bahas satu per satu"}</button>
      <button onClick={() => pick("delegate")} disabled={!!busy} className="rounded-full bg-[#2F6BFF] px-4 py-1.5 text-xs font-bold text-white hover:brightness-105 disabled:opacity-60" data-testid="task-offer-delegate">{busy === "delegate" ? "..." : "Terima beres"}</button>
    </div>
  );
}

// Polls for finished assigned tasks and shows a toast with a link to the result.
export function TaskNotifier() {
  const nav = useNavigate();
  useEffect(() => {
    let stop = false;
    const poll = async () => {
      try {
        const r = await api.get("/task-notifications");
        if (stop || !r.data.length) return;
        r.data.forEach((t) => toast(t.status === "completed" ? `Tugas selesai: ${t.goal}` : `Tugas gagal: ${t.goal}`, { description: t.persona_name ? `oleh ${t.persona_name}` : undefined, action: { label: "Buka", onClick: () => nav(`/workspace/${t.id}`) }, duration: 12000 }));
        window.dispatchEvent(new CustomEvent("oryntix:task-done", { detail: r.data }));
        await api.post("/task-notifications/ack");
      } catch (e) {}
    };
    poll(); const iv = setInterval(poll, 20000);
    return () => { stop = true; clearInterval(iv); };
  }, [nav]);
  return null;
}
