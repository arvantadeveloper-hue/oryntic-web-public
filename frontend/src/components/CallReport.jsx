import React, { useEffect, useState } from "react";
import { PhoneCall, Loader2, Bot, Wifi, Camera } from "lucide-react";
import { api } from "../lib/api";
import { LoadMore } from "./ConversationTools";

const dur = (s) => (s >= 3600 ? `${Math.floor(s / 3600)}j ${Math.floor((s % 3600) / 60)}m` : s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}d` : `${s}d`);
const fmt = (iso) => (iso ? new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "-");

// Per-call cost breakdown: assistant tokens, WebRTC data (host pays), screen snapshots.
export function CallReport() {
  const [items, setItems] = useState(null);
  const [next, setNext] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = async (before) => {
    setBusy(true);
    try { const r = await api.get("/wallet/calls", { params: { limit: 20, before } }); setItems((x) => (before ? [...(x || []), ...r.data.items] : r.data.items)); setNext(r.data.has_more ? r.data.next_before : null); }
    catch (e) { setItems((x) => x || []); } finally { setBusy(false); }
  };
  useEffect(() => { load(); }, []);

  return (
    <div data-testid="call-report">
      <h2 className="mt-10 flex items-center gap-2 text-lg font-bold text-slate-900"><PhoneCall size={18} className="text-[#2F6BFF]" /> Riwayat Panggilan</h2>
      <p className="text-xs text-slate-500">Rincian biaya tiap panggilan: asisten (token suara), data WebRTC teman ($0,75/GB — ditanggung host), dan cuplikan layar yang ditunjukkan ke asisten.</p>
      <div className="mt-4 aivora-card overflow-hidden">
        {items === null ? <p className="flex items-center gap-2 p-6 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p>
          : items.length === 0 ? <p className="p-6 text-sm text-slate-500" data-testid="call-report-empty">Belum ada panggilan.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="call-report-table">
                <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
                  <tr><th className="px-4 py-2.5 text-left">Waktu</th><th className="px-4 py-2.5 text-left">Panggilan</th><th className="px-3 py-2.5 text-right">Durasi</th>
                    <th className="px-3 py-2.5 text-right"><span className="inline-flex items-center gap-1"><Bot size={12} /> Asisten</span></th>
                    <th className="px-3 py-2.5 text-right"><span className="inline-flex items-center gap-1"><Wifi size={12} /> Data</span></th>
                    <th className="px-3 py-2.5 text-right"><span className="inline-flex items-center gap-1"><Camera size={12} /> Cuplikan</span></th>
                    <th className="px-4 py-2.5 text-right">Total</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {items.map((r) => (
                    <tr key={r.id} data-testid={`call-row-${r.id}`} className="hover:bg-slate-50/60">
                      <td className="whitespace-nowrap px-4 py-2.5 text-xs text-slate-500">{fmt(r.started_at)}</td>
                      <td className="max-w-[220px] px-4 py-2.5"><p className="truncate font-semibold text-slate-800">{r.title}</p>{r.personas?.length > 0 && <p className="truncate text-[11px] text-slate-400">{r.personas.join(", ")}</p>}</td>
                      <td className="whitespace-nowrap px-3 py-2.5 text-right text-slate-600">{dur(r.seconds || 0)}</td>
                      <td className="px-3 py-2.5 text-right text-slate-700">{r.assistant_credits || "–"}</td>
                      <td className="whitespace-nowrap px-3 py-2.5 text-right text-slate-700">{r.data_credits ? <>{r.data_credits} <span className="text-[11px] text-slate-400">({r.data_mb} MB)</span></> : "–"}</td>
                      <td className="whitespace-nowrap px-3 py-2.5 text-right text-slate-700">{r.snapshot_count ? <>{r.snapshot_credits} <span className="text-[11px] text-slate-400">({r.snapshot_count}×)</span></> : "–"}</td>
                      <td className="px-4 py-2.5 text-right font-bold text-slate-900" data-testid={`call-total-${r.id}`}>{r.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        {next && !busy && <LoadMore onClick={() => load(next)} testid="call-report-more" />}
        {busy && items && <p className="flex items-center justify-center gap-2 p-3 text-xs text-slate-400"><Loader2 size={12} className="animate-spin" /> Memuat…</p>}
      </div>
    </div>
  );
}
