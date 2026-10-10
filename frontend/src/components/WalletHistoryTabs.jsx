import React, { useEffect, useState } from "react";
import { PhoneCall, Video, Receipt, Loader2, RefreshCw, FlaskConical } from "lucide-react";
import { api } from "../lib/api";
import { LoadMore } from "./ConversationTools";
import { CallReport } from "./CallReport";

const dur = (s) => (s >= 3600 ? `${Math.floor(s / 3600)}j ${Math.floor((s % 3600) / 60)}m` : s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}d` : `${s}d`);
const fmt = (iso) => (iso ? new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "-");
const END_CLS = { USER_CLOSED: "bg-slate-100 text-slate-600", DISCONNECTED: "bg-amber-50 text-amber-700", STALE: "bg-amber-50 text-amber-700", MAX_DURATION_REACHED: "bg-[#EEF3FF] text-[#2F6BFF]", NO_CREDITS: "bg-rose-50 text-rose-600" };

// One card per call; the sessions inside it (incl. "Sambung ulang" continuations) with connected seconds + credits.
function VideoCallCard({ call }) {
  return (
    <div className="px-5 py-4" data-testid={`video-call-${call.id}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <p className="font-semibold text-slate-800">{call.title}</p>
        <span className="text-xs text-slate-500">{fmt(call.started_at)}</span>
        <span className="ml-auto text-xs text-slate-500">{call.sessions.length} sesi · tersambung <b className="text-slate-700">{dur(call.seconds)}</b></span>
        <span className="rounded-full bg-[#EEF3FF] px-2.5 py-0.5 text-xs font-bold text-[#2F6BFF]" data-testid={`video-call-credits-${call.id}`}>{call.credits} kredit</span>
      </div>
      <ul className="mt-2 divide-y divide-slate-100 rounded-xl border border-slate-100 text-xs">
        {call.sessions.map((s, i) => (
          <li key={s.id} className="flex flex-wrap items-center gap-2 px-3 py-2" data-testid={`video-session-${s.id}`}>
            <span className="w-14 font-mono text-slate-400">Sesi {i + 1}</span>
            <span className="text-slate-500">{fmt(s.started_at)}</span>
            {s.resumed && <span className="flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700" title="Lanjutan sisa waktu setelah koneksi terputus"><RefreshCw size={10} /> lanjutan</span>}
            {s.sandbox && <span className="flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-slate-500"><FlaskConical size={10} /> sandbox</span>}
            <span className={`rounded-full px-2 py-0.5 font-semibold ${s.status === "active" ? "bg-emerald-50 text-emerald-700" : END_CLS[s.end_reason] || "bg-slate-100 text-slate-600"}`}>{s.end_label}</span>
            <span className="ml-auto text-slate-600">tersambung <b>{dur(s.seconds)}</b> <span className="text-slate-400">/ {dur(s.max_seconds)}</span></span>
            <span className="w-20 text-right font-semibold text-slate-800">{s.credits} kredit</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function VideoSessionReport() {
  const [items, setItems] = useState(null);
  const [next, setNext] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = async (before) => {
    setBusy(true);
    try { const r = await api.get("/wallet/video-sessions", { params: { limit: 20, before } }); setItems((x) => (before ? [...(x || []), ...r.data.items] : r.data.items)); setNext(r.data.has_more ? r.data.next_before : null); }
    catch (e) { setItems((x) => x || []); } finally { setBusy(false); }
  };
  useEffect(() => { load(); }, []);
  return (
    <div data-testid="video-report">
      <p className="px-5 pt-4 text-xs text-slate-500">Sesi video interaktif Oryntix per panggilan: hanya detik <b>tersambung</b> yang dihitung; sesi "lanjutan" memakai sisa waktu sesi yang terputus.</p>
      {items === null ? <p className="flex items-center gap-2 p-6 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p>
        : items.length === 0 ? <p className="p-6 text-sm text-slate-500" data-testid="video-report-empty">Belum ada sesi video.</p>
          : <div className="mt-2 divide-y divide-slate-100">{items.map((c) => <VideoCallCard key={c.id} call={c} />)}</div>}
      {next && !busy && <LoadMore onClick={() => load(next)} testid="video-report-more" />}
    </div>
  );
}

function TransactionList({ transactions }) {
  const [shown, setShown] = useState(20);
  if (!transactions.length) return <p className="p-6 text-sm text-slate-500" data-testid="txn-empty">Belum ada transaksi.</p>;
  return (
    <div className="divide-y divide-slate-100" data-testid="txn-list">
      {transactions.slice(0, shown).map((tx) => (
        <div key={tx.id} className="flex items-center justify-between px-5 py-3" data-testid={`txn-${tx.id}`}>
          <div><p className="text-sm text-slate-700">{tx.description}</p><p className="text-xs text-slate-500">{new Date(tx.created_at).toLocaleString()}</p></div>
          <span className={`text-sm font-semibold ${tx.amount >= 0 ? "text-[#10B981]" : "text-[#EF4444]"}`}>{tx.amount >= 0 ? "+" : ""}{tx.amount}</span>
        </div>
      ))}
      {transactions.length > shown && <LoadMore onClick={() => setShown((n) => n + 20)} testid="tx-load-more" />}
    </div>
  );
}

const TABS = [
  { id: "calls", label: "Panggilan", icon: PhoneCall },
  { id: "video", label: "Sesi Video", icon: Video },
  { id: "txns", label: "Transaksi", icon: Receipt },
];

// The three history boxes of the Credits page as one tabbed card.
export function WalletHistoryTabs({ transactions = [] }) {
  const [tab, setTab] = useState("calls");
  return (
    <div className="mt-10" data-testid="wallet-history">
      <h2 className="text-lg font-bold text-slate-900">Riwayat</h2>
      <div className="mt-4 aivora-card overflow-hidden">
        <div className="flex gap-1 border-b border-slate-100 bg-slate-50/60 p-1.5" role="tablist" data-testid="wallet-history-tabs">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)} data-testid={`wallet-tab-${id}`}
              className={`flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-sm font-semibold transition ${tab === id ? "bg-white text-[#2F6BFF] shadow-sm" : "text-slate-500 hover:text-slate-800"}`}>
              <Icon size={14} /> {label}
            </button>
          ))}
        </div>
        <div data-testid={`wallet-tab-panel-${tab}`}>
          {tab === "calls" && <CallReport embedded />}
          {tab === "video" && <VideoSessionReport />}
          {tab === "txns" && <TransactionList transactions={transactions} />}
        </div>
      </div>
    </div>
  );
}
