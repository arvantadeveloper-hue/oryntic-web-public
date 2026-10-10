import React, { useEffect, useMemo, useState } from "react";
import { Loader2, History, UserPlus, ShieldCheck, UserMinus, Coins, Ban, CheckCircle2, Download, RefreshCw, Search, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../lib/api";
import { ROLE_LABEL } from "./PlatformApp";

const fmt = (iso) => (iso ? new Date(iso).toLocaleString("id-ID", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "-");
const roleName = (r) => ROLE_LABEL[r] || r || "—";

// action code → { category, icon, tint, describe(target, meta) }
const ACTIONS = {
  "staff.grant": { cat: "staff", icon: UserPlus, tint: "text-emerald-600 bg-emerald-50", label: "Tambah staf",
    describe: (t, m) => `${m?.created ? "Mengundang" : "Memberi peran"} ${t} sebagai ${roleName(m?.role)}` },
  "staff.role": { cat: "staff", icon: ShieldCheck, tint: "text-blue-600 bg-blue-50", label: "Ubah peran",
    describe: (t, m) => `Mengubah peran ${t}: ${roleName(m?.from)} → ${roleName(m?.to)}` },
  "staff.revoke": { cat: "staff", icon: UserMinus, tint: "text-rose-600 bg-rose-50", label: "Cabut akses",
    describe: (t, m) => `Mencabut akses platform ${t} (${roleName(m?.role)})` },
  "user.credits": { cat: "credits", icon: Coins, tint: "text-amber-600 bg-amber-50", label: "Top up kredit",
    describe: (t, m) => `Top up +${new Intl.NumberFormat("id-ID").format(m?.delta ?? 0)} kredit untuk ${t} (saldo ${m?.balance_after ?? "—"})${m?.note ? ` · ${m.note}` : ""}` },
  "user.disable": { cat: "status", icon: Ban, tint: "text-rose-600 bg-rose-50", label: "Suspend akun",
    describe: (t, m) => `Men-suspend ${t}${m?.reason ? ` · ${m.reason}` : ""}` },
  "user.enable": { cat: "status", icon: CheckCircle2, tint: "text-emerald-600 bg-emerald-50", label: "Aktifkan akun",
    describe: (t, m) => `Mengaktifkan kembali ${t}${m?.reason ? ` · ${m.reason}` : ""}` },
  "finance.export": { cat: "export", icon: Download, tint: "text-violet-600 bg-violet-50", label: "Ekspor laporan",
    describe: (t, m) => `Ekspor laporan keuangan ${t}${m?.group ? ` (per ${m.group})` : ""}` },
  "audit.export": { cat: "export", icon: Download, tint: "text-violet-600 bg-violet-50", label: "Ekspor audit",
    describe: (t, m) => `Mengunduh jejak audit (${m?.count ?? 0} baris)${t ? ` · ${t}` : ""}` },
  "expense.create": { cat: "expense", icon: Coins, tint: "text-amber-600 bg-amber-50", label: "Pengeluaran",
    describe: (t, m) => `Mencatat pengeluaran ${t} · ${new Intl.NumberFormat("id-ID").format(m?.amount_idr ?? 0)} IDR${m?.taxable ? ` (PPN ${new Intl.NumberFormat("id-ID").format(m?.ppn_idr ?? 0)})` : ""}` },
  "expense.delete": { cat: "expense", icon: UserMinus, tint: "text-rose-600 bg-rose-50", label: "Hapus pengeluaran",
    describe: (t, m) => `Menghapus pengeluaran ${t}${m?.amount_idr ? ` · ${new Intl.NumberFormat("id-ID").format(m.amount_idr)} IDR` : ""}` },
  "expense.export": { cat: "export", icon: Download, tint: "text-violet-600 bg-violet-50", label: "Ekspor pengeluaran",
    describe: (t, m) => `Mengunduh data pengeluaran (${m?.count ?? 0} baris)${t ? ` · ${t}` : ""}` },
  "expense.efaktur": { cat: "expense", icon: Download, tint: "text-blue-600 bg-blue-50", label: "Unggah e-faktur",
    describe: (t) => `Mengunggah e-faktur untuk ${t}` },
  "recurring.create": { cat: "expense", icon: Coins, tint: "text-emerald-600 bg-emerald-50", label: "Langganan baru",
    describe: (t, m) => `Membuat langganan ${t} · ${new Intl.NumberFormat("id-ID").format(m?.amount_idr ?? 0)} IDR/bln` },
  "recurring.update": { cat: "expense", icon: ShieldCheck, tint: "text-blue-600 bg-blue-50", label: "Ubah langganan",
    describe: (t, m) => `Memperbarui langganan ${t}${m && "active" in m ? ` · ${m.active ? "aktif" : "nonaktif"}` : ""}` },
  "recurring.delete": { cat: "expense", icon: UserMinus, tint: "text-rose-600 bg-rose-50", label: "Hapus langganan",
    describe: (t) => `Menghapus langganan ${t}` },
  "recurring.run": { cat: "expense", icon: Coins, tint: "text-amber-600 bg-amber-50", label: "Jalankan langganan",
    describe: (t, m) => `Membuat ${m?.created ?? 0} pengeluaran langganan untuk ${t}` },
  "ppn.export": { cat: "export", icon: Download, tint: "text-violet-600 bg-violet-50", label: "Ekspor SPT PPN",
    describe: (t) => `Mengunduh SPT PPN tahun ${t}` },
  "pnl.export": { cat: "export", icon: Download, tint: "text-violet-600 bg-violet-50", label: "Ekspor laba rugi",
    describe: (t) => `Mengunduh laporan laba rugi ${t}` },
  "budget.set": { cat: "expense", icon: ShieldCheck, tint: "text-blue-600 bg-blue-50", label: "Atur anggaran",
    describe: (t, m) => `Menetapkan anggaran bulanan ${new Intl.NumberFormat("id-ID").format(m?.monthly_idr ?? 0)} IDR` },
  "pricing.update": { cat: "config", icon: ShieldCheck, tint: "text-indigo-600 bg-indigo-50", label: "Ubah tarif",
    describe: (t, m) => `Mengubah tarif & margin${summarizeChanged(m?.changed)}` },
  "trial.update": { cat: "config", icon: ShieldCheck, tint: "text-indigo-600 bg-indigo-50", label: "Ubah trial",
    describe: (t, m) => `Mengubah pengaturan trial${summarizeChanged(m?.changed)}` },
  "rate_limits.update": { cat: "config", icon: ShieldCheck, tint: "text-indigo-600 bg-indigo-50", label: "Ubah batas",
    describe: (t, m) => `Mengubah batas & rate limit${summarizeChanged(m?.changed)}` },
};

// Turn the audit `changed` map ({field:[old,new]} or {field:"diubah"}) into a short human sentence.
function summarizeChanged(changed) {
  if (!changed || typeof changed !== "object") return "";
  const keys = Object.keys(changed);
  if (!keys.length) return "";
  const parts = keys.slice(0, 4).map((k) => {
    const v = changed[k];
    return Array.isArray(v) ? `${k}: ${v[0]} → ${v[1]}` : `${k}`;
  });
  const extra = keys.length > 4 ? ` +${keys.length - 4} lainnya` : "";
  return ` · ${parts.join(", ")}${extra}`;
}
const fallback = (code) => ({ cat: "other", icon: History, tint: "text-slate-600 bg-slate-100", label: code, describe: (t, m) => `${t || ""}${m && Object.keys(m).length ? ` · ${JSON.stringify(m)}` : ""}` });

const FILTERS = [
  { id: "all", label: "Semua" },
  { id: "staff", label: "Staf & Peran" },
  { id: "credits", label: "Kredit" },
  { id: "expense", label: "Pengeluaran" },
  { id: "config", label: "Tarif & Batas" },
  { id: "status", label: "Status akun" },
  { id: "export", label: "Ekspor" },
];

export default function PlatformAudit() {
  const [items, setItems] = useState(null);
  const [limit, setLimit] = useState(50);
  const [filter, setFilter] = useState("all");
  const [refreshing, setRefreshing] = useState(false);
  const [q, setQ] = useState("");
  const [dq, setDq] = useState(""); // debounced actor query
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [downloading, setDownloading] = useState(false);

  useEffect(() => { const t = setTimeout(() => setDq(q.trim()), 350); return () => clearTimeout(t); }, [q]);

  const params = useMemo(() => {
    const p = { limit };
    if (dq) p.q = dq;
    if (start) p.start = start;
    if (end) p.end = end;
    return p;
  }, [limit, dq, start, end]);

  const load = () => {
    setRefreshing(true);
    api.get("/platform/audit", { params })
      .then((r) => setItems(r.data.items))
      .catch((e) => { setItems([]); if (e?.response?.status === 400) toast.error("Format tanggal harus YYYY-MM-DD"); })
      .finally(() => setRefreshing(false));
  };
  useEffect(load, [params]);

  const download = async () => {
    setDownloading(true);
    try {
      const p = {}; if (dq) p.q = dq; if (start) p.start = start; if (end) p.end = end;
      const r = await api.get("/platform/audit/export.csv", { params: p, responseType: "blob" });
      const url = URL.createObjectURL(r.data); const a = document.createElement("a");
      a.href = url; a.download = `oryntix-audit-${start || "awal"}-${end || "kini"}.csv`; a.click(); URL.revokeObjectURL(url);
    } catch (e) { toast.error("Gagal mengunduh CSV"); } finally { setDownloading(false); }
  };

  const clearFilters = () => { setQ(""); setDq(""); setStart(""); setEnd(""); setFilter("all"); };
  const hasFilter = q || start || end || filter !== "all";

  const rows = useMemo(() => {
    const list = items || [];
    return filter === "all" ? list : list.filter((a) => (ACTIONS[a.action] || fallback(a.action)).cat === filter);
  }, [items, filter]);

  return (
    <div data-testid="platform-audit-page">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-black text-slate-900"><History size={22} className="text-[#2F6BFF]" /> Jejak Audit</h1>
          <p className="text-sm text-slate-500">Riwayat aksi staf platform — pemberian/pencabutan peran, penyesuaian kredit, status akun, dan ekspor laporan.</p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button onClick={download} disabled={downloading} className="btn-grad inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-bold disabled:opacity-50" data-testid="audit-download">
            {downloading ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} Unduh CSV
          </button>
          <button onClick={load} disabled={refreshing} className="inline-flex items-center gap-1.5 rounded-xl border border-[#E7ECF3] bg-white px-3 py-2 text-xs font-bold text-slate-600 hover:border-[#2F6BFF] disabled:opacity-50" data-testid="audit-refresh">
            <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} /> Segarkan
          </button>
        </div>
      </div>

      <div className="mt-5 aivora-card flex flex-wrap items-end gap-3 p-4" data-testid="audit-filterbar">
        <label className="min-w-[220px] flex-1">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Cari aktor (email)</span>
          <div className="relative mt-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="mis. admin@oryntix.com" data-testid="audit-search" className="w-full rounded-xl border border-[#E7ECF3] py-2 pl-9 pr-3 text-sm outline-none focus:border-[#2F6BFF]" />
          </div>
        </label>
        <label>
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Dari</span>
          <input type="date" value={start} max={end || undefined} onChange={(e) => setStart(e.target.value)} data-testid="audit-start" className="mt-1 block rounded-xl border border-[#E7ECF3] bg-white px-3 py-2 text-sm outline-none focus:border-[#2F6BFF]" />
        </label>
        <label>
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Sampai</span>
          <input type="date" value={end} min={start || undefined} onChange={(e) => setEnd(e.target.value)} data-testid="audit-end" className="mt-1 block rounded-xl border border-[#E7ECF3] bg-white px-3 py-2 text-sm outline-none focus:border-[#2F6BFF]" />
        </label>
        {hasFilter && (
          <button onClick={clearFilters} className="inline-flex items-center gap-1 rounded-xl bg-slate-100 px-3 py-2 text-xs font-bold text-slate-600 hover:bg-slate-200" data-testid="audit-clear">
            <X size={13} /> Reset
          </button>
        )}
      </div>

      <div className="mt-4 flex flex-wrap gap-2" data-testid="audit-filters">
        {FILTERS.map((f) => (
          <button key={f.id} onClick={() => setFilter(f.id)} data-testid={`audit-filter-${f.id}`}
            className={`rounded-full px-3.5 py-1.5 text-xs font-bold transition-colors ${filter === f.id ? "bg-[#2F6BFF] text-white" : "bg-white text-slate-600 border border-[#E7ECF3] hover:border-[#2F6BFF]"}`}>
            {f.label}
          </button>
        ))}
      </div>

      <div className="mt-4 aivora-card divide-y divide-slate-100 overflow-hidden" data-testid="audit-list">
        {items === null ? (
          <p className="flex items-center gap-2 p-6 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p>
        ) : rows.length === 0 ? (
          <p className="p-6 text-sm text-slate-400" data-testid="audit-empty">Tidak ada aktivitas yang cocok dengan filter.</p>
        ) : rows.map((a) => {
          const def = ACTIONS[a.action] || fallback(a.action);
          const Icon = def.icon;
          return (
            <div key={a.id} className="flex items-start gap-3 px-4 py-3" data-testid={`audit-row-${a.id}`}>
              <span className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${def.tint}`}><Icon size={16} /></span>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-slate-800"><span className="font-bold">{a.actor_email}</span> · {def.describe(a.target, a.meta)}</p>
                <p className="mt-0.5 flex items-center gap-2 text-[11px] text-slate-400">
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-slate-500">{def.label}</span>
                  {fmt(a.created_at)}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {items !== null && items.length >= limit && limit < 500 && (
        <div className="mt-4 text-center">
          <button onClick={() => setLimit((l) => Math.min(l + 50, 500))} className="rounded-xl border border-[#E7ECF3] bg-white px-4 py-2 text-xs font-bold text-slate-600 hover:border-[#2F6BFF]" data-testid="audit-load-more">
            Muat lebih banyak
          </button>
        </div>
      )}
    </div>
  );
}
