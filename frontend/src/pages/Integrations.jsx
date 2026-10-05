import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { HardDrive, Link2, Unplug, Loader2, CheckCircle2, AlertTriangle, Plug } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

const mb = (b) => (b / 1048576).toFixed(1);

export function StorageMeter({ storage, compact = false }) {
  if (!storage) return null;
  const warn = storage.pct >= 80;
  return (
    <div className={`${compact ? "" : "aivora-card p-4"}`} data-testid="storage-meter">
      <div className="flex items-center justify-between text-xs"><span className="font-semibold text-slate-700">Penyimpanan platform</span><span className={warn ? "font-bold text-amber-600" : "text-slate-500"} data-testid="storage-usage">{mb(storage.used_bytes)} / {mb(storage.quota_bytes)} MB</span></div>
      <div className="mt-1.5 h-2 rounded-full bg-slate-100"><div className={`h-2 rounded-full ${warn ? "bg-amber-500" : "bg-[#2F6BFF]"}`} style={{ width: `${storage.pct}%` }} /></div>
      {warn && <p className="mt-2 flex items-start gap-1.5 text-[11px] text-amber-700" data-testid="storage-tip"><AlertTriangle size={12} className="mt-0.5 shrink-0" /> Hampir penuh. Hubungkan Google Drive agar dokumen tersimpan di Drive Anda tanpa batas platform.</p>}
    </div>
  );
}

export default function Integrations() {
  const [data, setData] = useState(null); const [busy, setBusy] = useState(false);
  const [params, setParams] = useSearchParams();
  const load = () => api.get("/integrations").then((r) => setData(r.data)).catch(() => setData({ items: [], storage: null }));
  useEffect(() => { load(); }, []);
  useEffect(() => {
    if (params.get("connected")) { toast.success("Google Drive terhubung"); setParams({}, { replace: true }); }
    if (params.get("error")) { toast.error(`Gagal menghubungkan Google Drive (${params.get("error")})`); setParams({}, { replace: true }); }
  }, [params, setParams]);
  const connect = async () => { setBusy(true); try { const r = await api.get("/integrations/google/connect"); window.location.href = r.data.authorization_url; } catch (e) { toast.error(e?.response?.data?.detail || "Gagal"); setBusy(false); } };
  const disconnect = async () => { if (!window.confirm("Putuskan Google Drive? Tautan di Galeri tetap ada, tapi asisten tidak bisa lagi mengakses Drive.")) return; await api.delete("/integrations/google"); toast.success("Google Drive diputus"); load(); };
  const g = data?.items?.[0];
  return (
    <div className="mx-auto max-w-4xl" data-testid="integrations-page">
      <h1 className="text-2xl font-black text-slate-900">Integrasi</h1>
      <p className="text-sm text-slate-500">Hubungkan layanan lain agar asisten bisa bekerja langsung di sana.</p>
      {data === null ? <p className="mt-6 flex items-center gap-2 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p> : (
        <>
          <div className="mt-6"><StorageMeter storage={data.storage} /></div>
          <div className="mt-6 aivora-card p-5" data-testid="integration-google_drive">
            <div className="flex flex-wrap items-start gap-4">
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#EEF3FF] text-[#2F6BFF]"><HardDrive size={22} /></span>
              <div className="min-w-0 flex-1">
                <p className="text-base font-bold text-slate-900">{g.name}</p>
                {g.connected ? <p className="mt-0.5 flex items-center gap-1 text-xs text-emerald-700" data-testid="gdrive-status"><CheckCircle2 size={13} /> Terhubung sebagai {g.account_email}</p>
                  : g.configured ? <p className="mt-0.5 text-xs text-slate-500" data-testid="gdrive-status">Belum terhubung</p>
                    : <p className="mt-0.5 flex items-center gap-1 text-xs text-amber-700" data-testid="gdrive-status"><AlertTriangle size={13} /> Belum dikonfigurasi admin platform (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)</p>}
                <ul className="mt-3 grid gap-1 text-xs text-slate-600 sm:grid-cols-2">{g.capabilities.map((c) => <li key={c} className="flex items-center gap-1.5"><Link2 size={11} className="text-[#2F6BFF]" /> {c}</li>)}</ul>
                <p className="mt-3 text-[11px] text-slate-400">Contoh perintah ke asisten: "simpan dokumen ini ke Google Drive", "update dokumen Proposal di Drive, tambahkan bagian anggaran", "kirim link drive laporan Q3".</p>
              </div>
              {g.connected ? <button onClick={disconnect} className="flex items-center gap-1.5 rounded-xl border border-rose-200 px-3 py-2 text-xs font-bold text-rose-600 hover:bg-rose-50" data-testid="gdrive-disconnect"><Unplug size={14} /> Putuskan</button>
                : <button onClick={connect} disabled={!g.configured || busy} className="btn-grad flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-bold disabled:opacity-50" data-testid="gdrive-connect">{busy ? <Loader2 size={14} className="animate-spin" /> : <Plug size={14} />} Hubungkan Google Drive</button>}
            </div>
          </div>
          <p className="mt-8 text-xs font-semibold uppercase tracking-wider text-slate-400">Segera hadir</p>
          <div className="mt-2 grid gap-3 sm:grid-cols-4" data-testid="integrations-coming-soon">{(data.coming_soon || []).map((n) => <div key={n} className="rounded-2xl border border-dashed border-[#CBD5E1] px-4 py-3 text-sm font-semibold text-slate-400">{n}</div>)}</div>
        </>
      )}
    </div>
  );
}
