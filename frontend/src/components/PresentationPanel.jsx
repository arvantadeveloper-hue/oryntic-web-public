import React, { useEffect, useState } from "react";
import { useLiveSync } from "../lib/userEvents";
import { MonitorUp, Loader2 } from "lucide-react";
import { api } from "../lib/api";
import { Markdown } from "./Markdown";

// "Share screen" of the Workspace result during a meeting; refreshes when the assistant saves a revision.
export function PresentationPanel({ taskId, refreshKey }) {
  const [task, setTask] = useState(null);
  const load = () => api.get(`/tasks/${taskId}`).then((r) => setTask(r.data)).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [taskId, refreshKey]);
  useLiveSync(load, ["task_update"], 60000, [taskId]);
  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-white/10 bg-white" data-testid="presentation-panel">
      <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-50 px-4 py-2 text-xs font-semibold text-slate-600">
        <MonitorUp size={14} className="text-[#2F6BFF]" /> Presentasi · {task?.goal || "Memuat..."}
        {task && <span className="ml-auto rounded-full bg-[#EEF3FF] px-2 py-0.5 text-[11px] font-bold text-[#2F6BFF]" data-testid="presentation-version">v{task.version}</span>}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-5 text-sm text-slate-800">
        {!task ? <p className="flex items-center gap-2 text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat hasil tugas...</p>
          : task.final_output ? <Markdown content={task.final_output} /> : <p className="text-slate-400">Tugas ini belum memiliki hasil (status: {task.status}).</p>}
      </div>
    </div>
  );
}
