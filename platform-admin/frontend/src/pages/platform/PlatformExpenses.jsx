import React, { useEffect, useMemo, useState } from "react";
import { Loader2, Plus, Trash2, Download, Search, X, Paperclip, FileText, Receipt, Wallet, Repeat, Power, Upload, Play, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { api } from "../../lib/api";
import { apiErr } from "../../lib/apiErr";
import { rp, num } from "./PlatformDashboard";

const todayISO = () => new Date().toISOString().slice(0, 10);
const fmtDate = (d) => (d ? new Date(d + "T00:00:00").toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" }) : "-");
const PPN_RATE = 0.11;

export default function PlatformExpenses() {
  const [cats, setCats] = useState([]);
  const [items, setItems] = useState(null);
  const [total, setTotal] = useState({});
  const [refreshing, setRefreshing] = useState(false);

  // filters
  const [q, setQ] = useState(""); const [dq, setDq] = useState("");
  const [fcat, setFcat] = useState(""); const [start, setStart] = useState(""); const [end, setEnd] = useState("");

  // form
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(todayISO());
  const [category, setCategory] = useState("ai_provider");
  const [vendor, setVendor] = useState("");
  const [amount, setAmount] = useState("");
  const [taxable, setTaxable] = useState(false);
  const [efaktur, setEfaktur] = useState("");
  const [desc, setDesc] = useState("");
  const [file, setFile] = useState(null);
  const [saving, setSaving] = useState(false);
  const [viewing, setViewing] = useState(null);

  // recurring subscriptions
  const [showRecur, setShowRecur] = useState(false);
  const [recur, setRecur] = useState([]);
  const emptyRform = { category: "hosting_prod", vendor: "", amount_idr: "", taxable: false, day_of_month: 1, active: true };
  const [rform, setRform] = useState(emptyRform);
  const [rbusy, setRbusy] = useState(false);
  const [uploadFor, setUploadFor] = useState(null);
  const fileRef = React.useRef(null);

  const loadRecur = () => api.get("/platform/expenses/recurring").then((r) => setRecur(r.data.items || [])).catch(() => setRecur([]));
  useEffect(() => { loadRecur(); }, []);

  const addRecur = async (e) => {
    e.preventDefault(); setRbusy(true);
    try {
      await api.post("/platform/expenses/recurring", { ...rform, amount_idr: Math.round(Number(rform.amount_idr) || 0) });
      toast.success("Langganan ditambahkan"); setRform(emptyRform); loadRecur();
    } catch (err) { toast.error(apiErr(err, "Gagal menambah langganan")); } finally { setRbusy(false); }
  };
  const toggleRecur = async (r) => {
    try { await api.put(`/platform/expenses/recurring/${r.id}`, { category: r.category, vendor: r.vendor, amount_idr: r.amount_idr, taxable: r.taxable, description: r.description || "", day_of_month: r.day_of_month, active: !r.active }); loadRecur(); }
    catch (e) { toast.error("Gagal memperbarui"); }
  };
  const delRecur = async (r) => { if (!window.confirm(`Hapus langganan "${r.vendor}"?`)) return; try { await api.delete(`/platform/expenses/recurring/${r.id}`); loadRecur(); } catch (e) { toast.error("Gagal menghapus"); } };
  const runRecur = async () => { try { const res = await api.post("/platform/expenses/recurring/run"); toast.success(`${res.data.created} pengeluaran dibuat untuk ${res.data.month}`); loadRecur(); load(); loadBudget(); } catch (e) { toast.error("Gagal menjalankan"); } };

  const pickUpload = (e) => { setUploadFor(e.id); fileRef.current?.click(); };
  const onUpload = async (ev) => {
    const f = ev.target.files?.[0]; ev.target.value = ""; if (!f || !uploadFor) return;
    const fd = new FormData(); fd.append("file", f);
    try { await api.put(`/platform/expenses/${uploadFor}/efaktur`, fd); toast.success("e-Faktur terunggah"); load(); }
    catch (err) { toast.error(apiErr(err, "Gagal unggah e-faktur")); } finally { setUploadFor(null); }
  };

  // monthly budget threshold (overall + per category)
  const [budget, setBudget] = useState(null);
  const [bEdit, setBEdit] = useState(false);
  const [bForm, setBForm] = useState({ monthly: "", cats: {} });
  const loadBudget = () => api.get("/platform/expenses/budget").then((r) => setBudget(r.data)).catch(() => {});
  useEffect(() => { loadBudget(); }, []);
  const startEdit = () => { const cats = {}; (budget?.categories || []).forEach((c) => { if (c.budget_idr) cats[c.category] = String(c.budget_idr); }); setBForm({ monthly: String(budget?.monthly_idr || ""), cats }); setBEdit(true); };
  const saveBudget = async () => {
    const categories = {}; Object.entries(bForm.cats).forEach(([k, v]) => { const n = Math.round(Number(v) || 0); if (n > 0) categories[k] = n; });
    try { await api.put("/platform/expenses/budget", { monthly_idr: Math.round(Number(bForm.monthly) || 0), categories }); toast.success("Anggaran disimpan"); setBEdit(false); loadBudget(); } catch (e) { toast.error("Gagal menyimpan anggaran"); }
  };

  useEffect(() => { const t = setTimeout(() => setDq(q.trim()), 350); return () => clearTimeout(t); }, [q]);

  const params = useMemo(() => {
    const p = {}; if (dq) p.q = dq; if (fcat) p.category = fcat; if (start) p.start = start; if (end) p.end = end; return p;
  }, [dq, fcat, start, end]);

  const load = () => {
    setRefreshing(true);
    api.get("/platform/expenses", { params })
      .then((r) => { setItems(r.data.items); setTotal(r.data.total || {}); setCats(r.data.categories || []); })
      .catch((e) => { setItems([]); if (e?.response?.status === 400) toast.error(apiErr(e, "Format tidak valid")); })
      .finally(() => setRefreshing(false));
  };
  useEffect(load, [params]);

  const catLabel = (id) => (cats.find((c) => c.id === id) || {}).label || id;

  const amt = Number(amount) || 0;
  const previewDpp = taxable ? Math.round(amt / (1 + PPN_RATE)) : amt;
  const previewPpn = taxable ? amt - previewDpp : 0;

  const resetForm = () => { setDate(todayISO()); setCategory("ai_provider"); setVendor(""); setAmount(""); setTaxable(false); setEfaktur(""); setDesc(""); setFile(null); };

  const submit = async (e) => {
    e.preventDefault();
    if (taxable && !file) { toast.error("Lampiran e-faktur wajib untuk pengeluaran kena PPN"); return; }
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append("date", date); fd.append("category", category); fd.append("vendor", vendor);
      fd.append("amount_idr", String(Math.round(amt))); fd.append("description", desc);
      fd.append("taxable", taxable ? "true" : "false"); fd.append("efaktur_no", efaktur);
      if (file) fd.append("file", file);
      await api.post("/platform/expenses", fd);
      toast.success("Pengeluaran tersimpan");
      resetForm(); setOpen(false); load(); loadBudget();
    } catch (err) { toast.error(apiErr(err, "Gagal menyimpan")); } finally { setSaving(false); }
  };

  const remove = async (e) => {
    if (!window.confirm(`Hapus pengeluaran "${e.vendor}" (${rp(e.amount_idr)})?`)) return;
    try { await api.delete(`/platform/expenses/${e.id}`); toast.success("Dihapus"); load(); loadBudget(); }
    catch (err) { toast.error(apiErr(err, "Gagal menghapus")); }
  };

  const viewFile = async (e) => {
    setViewing(e.id);
    try {
      const r = await api.get(`/platform/expenses/${e.id}/file`, { responseType: "blob" });
      const url = URL.createObjectURL(r.data); window.open(url, "_blank"); setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) { toast.error("Gagal membuka lampiran"); } finally { setViewing(null); }
  };

  const download = async () => {
    try {
      const r = await api.get("/platform/expenses/export.csv", { params, responseType: "blob" });
      const url = URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = url; a.download = `oryntix-pengeluaran-${start || "awal"}-${end || "kini"}.csv`; a.click(); URL.revokeObjectURL(url);
    } catch (e) { toast.error("Gagal mengunduh CSV"); }
  };

  const hasFilter = q || fcat || start || end;

  return (
    <div data-testid="platform-expenses">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-black text-slate-900"><Wallet size={22} className="text-[#2F6BFF]" /> Pengeluaran</h1>
          <p className="text-sm text-slate-500">Catat beban operasional (provider AI, hosting, database, dll). Nilai = total dibayar; PPN 11% dipecah otomatis untuk yang kena pajak.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowRecur((v) => !v)} className="inline-flex items-center gap-1.5 rounded-xl border border-[#E7ECF3] bg-white px-3 py-2 text-xs font-bold text-slate-600 hover:border-[#2F6BFF]" data-testid="exp-toggle-recur"><Repeat size={14} /> Langganan{recur.length ? ` (${recur.length})` : ""}</button>
          <button onClick={download} className="inline-flex items-center gap-1.5 rounded-xl border border-[#E7ECF3] bg-white px-3 py-2 text-xs font-bold text-slate-600 hover:border-[#2F6BFF]" data-testid="exp-download"><Download size={14} /> Unduh CSV</button>
          <button onClick={() => setOpen((v) => !v)} className="btn-grad inline-flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-bold" data-testid="exp-toggle-form"><Plus size={14} /> Pengeluaran baru</button>
        </div>
      </div>

      <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={onUpload} className="hidden" data-testid="exp-efaktur-upload-input" />

      {items && items.filter((e) => e.needs_efaktur && !e.attachment).length > 0 && (
        <div className="mt-4 flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4" data-testid="exp-efaktur-banner">
          <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-600" />
          <div className="text-sm">
            <p className="font-bold text-amber-800">{items.filter((e) => e.needs_efaktur && !e.attachment).length} pengeluaran kena PPN menunggu e-faktur</p>
            <p className="text-amber-700">Unggah e-faktur agar PPN masukan sah dikreditkan. Pengingat email dikirim otomatis ke Finance tiap akhir bulan (tgl 28).</p>
          </div>
        </div>
      )}

      {showRecur && (
        <div className="mt-5 aivora-card p-5" data-testid="exp-recurring">
          <div className="flex items-center justify-between">
            <div><p className="flex items-center gap-2 text-sm font-bold text-slate-900"><Repeat size={15} className="text-[#2F6BFF]" /> Langganan bulanan</p><p className="text-xs text-slate-500">Dibuat otomatis tiap awal bulan (cron). Item kena PPN akan menunggu lampiran e-faktur.</p></div>
            <button onClick={runRecur} className="inline-flex items-center gap-1.5 rounded-xl bg-slate-900 px-3 py-2 text-xs font-bold text-white hover:bg-slate-700" data-testid="exp-recur-run"><Play size={13} /> Jalankan sekarang</button>
          </div>
          <form onSubmit={addRecur} className="mt-4 grid items-end gap-3 md:grid-cols-6" data-testid="exp-recur-form">
            <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 md:col-span-1">Kategori<select value={rform.category} onChange={(e) => setRform({ ...rform, category: e.target.value })} data-testid="recur-category" className="mt-1 block w-full rounded-xl border border-[#E7ECF3] bg-white px-2 py-2 text-sm outline-none">{cats.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</select></label>
            <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 md:col-span-2">Vendor<input value={rform.vendor} onChange={(e) => setRform({ ...rform, vendor: e.target.value })} required placeholder="mis. MongoDB Atlas" data-testid="recur-vendor" className="mt-1 block w-full rounded-xl border border-[#E7ECF3] px-3 py-2 text-sm outline-none" /></label>
            <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Nominal/bln<input type="number" min="1" value={rform.amount_idr} onChange={(e) => setRform({ ...rform, amount_idr: e.target.value })} required placeholder="IDR" data-testid="recur-amount" className="mt-1 block w-full rounded-xl border border-[#E7ECF3] px-3 py-2 text-sm outline-none" /></label>
            <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Tgl tagih<input type="number" min="1" max="28" value={rform.day_of_month} onChange={(e) => setRform({ ...rform, day_of_month: Number(e.target.value) })} data-testid="recur-day" className="mt-1 block w-full rounded-xl border border-[#E7ECF3] px-3 py-2 text-sm outline-none" /></label>
            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1.5 text-xs font-semibold text-slate-600"><input type="checkbox" checked={rform.taxable} onChange={(e) => setRform({ ...rform, taxable: e.target.checked })} data-testid="recur-taxable" className="h-4 w-4" /> PPN</label>
              <button disabled={rbusy} className="btn-grad inline-flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold disabled:opacity-50" data-testid="recur-add">{rbusy ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}</button>
            </div>
          </form>
          <div className="mt-4 divide-y divide-slate-100" data-testid="recur-list">
            {recur.length === 0 && <p className="py-3 text-xs text-slate-400">Belum ada langganan.</p>}
            {recur.map((r) => (
              <div key={r.id} className="flex items-center gap-3 py-2.5 text-sm" data-testid={`recur-row-${r.id}`}>
                <span className={`h-2 w-2 rounded-full ${r.active ? "bg-emerald-500" : "bg-slate-300"}`} />
                <span className="rounded-full bg-[#EEF3FF] px-2 py-0.5 text-[11px] font-bold text-[#2F6BFF]">{catLabel(r.category)}</span>
                <span className="font-semibold text-slate-800">{r.vendor}</span>
                <span className="text-slate-500">{rp(r.amount_idr)}/bln · tgl {r.day_of_month}{r.taxable ? " · PPN" : ""}</span>
                <span className="ml-auto text-[11px] text-slate-400">{r.last_generated ? `terakhir ${r.last_generated}` : "belum dibuat"}</span>
                <button onClick={() => toggleRecur(r)} title={r.active ? "Nonaktifkan" : "Aktifkan"} className={`rounded-lg px-2 py-1.5 ${r.active ? "bg-amber-50 text-amber-600" : "bg-emerald-50 text-emerald-600"}`} data-testid={`recur-toggle-${r.id}`}><Power size={13} /></button>
                <button onClick={() => delRecur(r)} className="rounded-lg bg-rose-50 px-2 py-1.5 text-rose-600" data-testid={`recur-delete-${r.id}`}><Trash2 size={13} /></button>
              </div>
            ))}
          </div>
        </div>
      )}

      {open && (
        <form onSubmit={submit} className="mt-5 aivora-card p-5" data-testid="exp-form">
          <div className="grid gap-4 md:grid-cols-3">
            <label className="text-xs font-semibold text-slate-500">Tanggal<input type="date" value={date} max={todayISO()} onChange={(e) => setDate(e.target.value)} required data-testid="exp-date" className="mt-1 block w-full rounded-xl border border-[#E7ECF3] px-3 py-2 text-sm text-slate-900 outline-none focus:border-[#2F6BFF]" /></label>
            <label className="text-xs font-semibold text-slate-500">Kategori<select value={category} onChange={(e) => setCategory(e.target.value)} data-testid="exp-category" className="mt-1 block w-full rounded-xl border border-[#E7ECF3] bg-white px-3 py-2 text-sm outline-none focus:border-[#2F6BFF]">{cats.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</select></label>
            <label className="text-xs font-semibold text-slate-500">Vendor / Penyedia<input value={vendor} onChange={(e) => setVendor(e.target.value)} required placeholder="mis. OpenAI, Emergent, MongoDB Atlas" data-testid="exp-vendor" className="mt-1 block w-full rounded-xl border border-[#E7ECF3] px-3 py-2 text-sm outline-none focus:border-[#2F6BFF]" /></label>
            <label className="text-xs font-semibold text-slate-500">Total dibayar (IDR)<input type="number" min="1" value={amount} onChange={(e) => setAmount(e.target.value)} required placeholder="0" data-testid="exp-amount" className="mt-1 block w-full rounded-xl border border-[#E7ECF3] px-3 py-2 text-sm outline-none focus:border-[#2F6BFF]" /></label>
            <label className="text-xs font-semibold text-slate-500 md:col-span-2">Keterangan<input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Opsional" data-testid="exp-desc" className="mt-1 block w-full rounded-xl border border-[#E7ECF3] px-3 py-2 text-sm outline-none focus:border-[#2F6BFF]" /></label>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-4 rounded-xl bg-slate-50 p-3">
            <label className="flex cursor-pointer items-center gap-2 text-sm font-semibold text-slate-700" data-testid="exp-taxable-label">
              <input type="checkbox" checked={taxable} onChange={(e) => setTaxable(e.target.checked)} data-testid="exp-taxable" className="h-4 w-4 rounded border-slate-300" /> Kena PPN 11%
            </label>
            {taxable && (
              <>
                <span className="text-xs text-slate-500" data-testid="exp-ppn-preview">DPP <b>{rp(previewDpp)}</b> · PPN <b className="text-[#2F6BFF]">{rp(previewPpn)}</b></span>
                <input value={efaktur} onChange={(e) => setEfaktur(e.target.value)} placeholder="No. e-faktur (opsional)" data-testid="exp-efaktur-no" className="ml-auto w-56 rounded-xl border border-[#E7ECF3] px-3 py-1.5 text-sm outline-none focus:border-[#2F6BFF]" />
              </>
            )}
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-sm text-slate-600" data-testid="exp-file-label">
              <span className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-dashed border-[#C7D2E5] px-3 py-2 text-xs font-bold text-slate-600 hover:border-[#2F6BFF]"><Paperclip size={14} /> {file ? file.name : "Lampirkan e-faktur (PDF/JPG/PNG)"}
                <input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="exp-file" className="hidden" /></span>
              {taxable && <span className="text-[11px] font-semibold text-rose-500">wajib untuk kena PPN</span>}
            </label>
            <div className="flex gap-2">
              <button type="button" onClick={() => { resetForm(); setOpen(false); }} className="rounded-xl bg-slate-100 px-4 py-2 text-xs font-bold text-slate-600" data-testid="exp-cancel">Batal</button>
              <button disabled={saving} className="btn-grad inline-flex items-center gap-1.5 rounded-xl px-5 py-2 text-xs font-bold disabled:opacity-50" data-testid="exp-save">{saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Simpan</button>
            </div>
          </div>
        </form>
      )}

      <div className="mt-4 aivora-card p-4" data-testid="exp-budget">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Anggaran bulan ini{budget?.month ? ` (${budget.month})` : ""}</p>
            {!bEdit && <p className="mt-1 text-lg font-black text-slate-900">{budget?.monthly_idr ? rp(budget.monthly_idr) : "Belum diatur"}<button onClick={startEdit} className="ml-2 text-xs font-bold text-[#2F6BFF] hover:underline" data-testid="budget-edit">{budget?.monthly_idr || budget?.categories?.some((c) => c.budget_idr) ? "Ubah" : "Atur target"}</button></p>}
          </div>
          {!bEdit && <div className="text-right"><p className="text-xs text-slate-500">Terpakai</p><p className={`text-lg font-black ${budget?.over ? "text-rose-600" : "text-slate-900"}`} data-testid="budget-spent">{rp(budget?.spent_idr)}{budget?.monthly_idr ? ` · ${budget?.pct}%` : ""}</p></div>}
        </div>

        {bEdit ? (
          <div className="mt-3" data-testid="budget-editor">
            <label className="block text-[11px] font-semibold uppercase tracking-wider text-slate-500">Anggaran total/bulan (IDR)
              <input type="number" min="0" value={bForm.monthly} onChange={(e) => setBForm({ ...bForm, monthly: e.target.value })} placeholder="mis. 5000000" data-testid="budget-input" className="mt-1 block w-56 rounded-lg border border-[#E7ECF3] px-3 py-1.5 text-sm outline-none focus:border-[#2F6BFF]" />
            </label>
            <p className="mt-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Anggaran per kategori (opsional)</p>
            <div className="mt-1 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              {(budget?.categories || []).map((c) => (
                <label key={c.category} className="flex items-center gap-2 text-xs text-slate-600">
                  <span className="w-32 shrink-0">{c.label}</span>
                  <input type="number" min="0" value={bForm.cats[c.category] || ""} onChange={(e) => setBForm({ ...bForm, cats: { ...bForm.cats, [c.category]: e.target.value } })} placeholder="0" data-testid={`budget-cat-${c.category}`} className="w-full rounded-lg border border-[#E7ECF3] px-2 py-1.5 text-sm outline-none focus:border-[#2F6BFF]" />
                </label>
              ))}
            </div>
            <div className="mt-3 flex gap-2">
              <button onClick={saveBudget} className="btn-grad rounded-lg px-4 py-1.5 text-xs font-bold" data-testid="budget-save">Simpan</button>
              <button onClick={() => setBEdit(false)} className="rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-600" data-testid="budget-cancel">Batal</button>
            </div>
          </div>
        ) : (
          <>
            {budget?.monthly_idr > 0 && (
              <div className="mt-3">
                <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full transition-all ${budget.over ? "bg-rose-500" : budget.pct >= 80 ? "bg-amber-500" : "bg-emerald-500"}`} style={{ width: `${Math.min(budget.pct, 100)}%` }} data-testid="budget-bar" /></div>
                {budget.over ? <p className="mt-2 flex items-center gap-1.5 text-xs font-bold text-rose-600" data-testid="budget-over"><AlertTriangle size={13} /> Melebihi anggaran sebesar {rp(budget.spent_idr - budget.monthly_idr)}! Email peringatan dikirim ke Finance.</p> : budget.pct >= 80 ? <p className="mt-2 text-xs font-semibold text-amber-600" data-testid="budget-warn">Mendekati batas anggaran ({budget.pct}%). Sisa {rp(budget.remaining_idr)}.</p> : <p className="mt-2 text-xs text-slate-500">Sisa anggaran {rp(budget.remaining_idr)}.</p>}
              </div>
            )}
            {(budget?.categories || []).some((c) => c.budget_idr > 0) && (
              <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="budget-cats">
                {budget.categories.filter((c) => c.budget_idr > 0).map((c) => (
                  <div key={c.category} data-testid={`budget-cat-row-${c.category}`}>
                    <div className="flex items-center justify-between text-[11px]"><span className="font-semibold text-slate-600">{c.label}</span><span className={c.over ? "font-bold text-rose-600" : "text-slate-500"}>{rp(c.spent_idr)} / {rp(c.budget_idr)}</span></div>
                    <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100"><div className={`h-full rounded-full ${c.over ? "bg-rose-500" : c.pct >= 80 ? "bg-amber-500" : "bg-emerald-500"}`} style={{ width: `${Math.min(c.pct, 100)}%` }} /></div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* totals */}
      <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[["Total pengeluaran", rp(total.amount), `${num(total.count || 0)} transaksi`, "exp-total"], ["DPP (tanpa PPN)", rp(total.dpp), "dasar pengenaan pajak", "exp-total-dpp"], ["PPN Masukan (11%)", rp(total.ppn), "dapat dikreditkan", "exp-total-ppn"], ["Rata-rata / transaksi", rp(total.count ? Math.round(total.amount / total.count) : 0), "per pengeluaran", "exp-total-avg"]].map(([l, v, s, id]) => (
          <div key={id} className="aivora-card p-5" data-testid={id}><p className="text-xs font-semibold uppercase tracking-wider text-slate-500">{l}</p><p className="mt-2 text-2xl font-black text-slate-900">{v}</p><p className="text-xs text-slate-500">{s}</p></div>))}
      </div>

      {/* filters */}
      <div className="mt-6 aivora-card flex flex-wrap items-end gap-3 p-4" data-testid="exp-filterbar">
        <label className="min-w-[200px] flex-1 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Cari vendor/keterangan
          <div className="relative mt-1"><Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><input value={q} onChange={(e) => setQ(e.target.value)} data-testid="exp-search" placeholder="mis. OpenAI" className="w-full rounded-xl border border-[#E7ECF3] py-2 pl-9 pr-3 text-sm outline-none focus:border-[#2F6BFF]" /></div>
        </label>
        <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Kategori<select value={fcat} onChange={(e) => setFcat(e.target.value)} data-testid="exp-filter-cat" className="mt-1 block rounded-xl border border-[#E7ECF3] bg-white px-3 py-2 text-sm outline-none"><option value="">Semua</option>{cats.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</select></label>
        <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Dari<input type="date" value={start} max={end || undefined} onChange={(e) => setStart(e.target.value)} data-testid="exp-filter-start" className="mt-1 block rounded-xl border border-[#E7ECF3] bg-white px-3 py-2 text-sm outline-none" /></label>
        <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Sampai<input type="date" value={end} min={start || undefined} onChange={(e) => setEnd(e.target.value)} data-testid="exp-filter-end" className="mt-1 block rounded-xl border border-[#E7ECF3] bg-white px-3 py-2 text-sm outline-none" /></label>
        {hasFilter && <button onClick={() => { setQ(""); setDq(""); setFcat(""); setStart(""); setEnd(""); }} className="inline-flex items-center gap-1 rounded-xl bg-slate-100 px-3 py-2 text-xs font-bold text-slate-600 hover:bg-slate-200" data-testid="exp-clear"><X size={13} /> Reset</button>}
      </div>

      {/* table */}
      <div className="mt-4 aivora-card overflow-hidden" data-testid="exp-list">
        {items === null ? <p className="flex items-center gap-2 p-6 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p> : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500"><tr><th className="px-4 py-2.5 text-left">Tanggal</th><th className="px-3 py-2.5 text-left">Kategori</th><th className="px-3 py-2.5 text-left">Vendor</th><th className="px-3 py-2.5 text-right">Total</th><th className="px-3 py-2.5 text-right">DPP</th><th className="px-3 py-2.5 text-right">PPN</th><th className="px-3 py-2.5 text-center">e-Faktur</th><th className="px-4 py-2.5 text-right">Aksi</th></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {items.length === 0 && <tr><td colSpan={8} className="p-6 text-center text-sm text-slate-500" data-testid="exp-empty">Belum ada pengeluaran yang cocok.</td></tr>}
              {items.map((e) => (
                <tr key={e.id} data-testid={`exp-row-${e.id}`}>
                  <td className="px-4 py-2.5 text-slate-700">{fmtDate(e.date)}</td>
                  <td className="px-3 py-2.5"><span className="rounded-full bg-[#EEF3FF] px-2 py-0.5 text-[11px] font-bold text-[#2F6BFF]">{catLabel(e.category)}</span></td>
                  <td className="px-3 py-2.5"><p className="flex items-center gap-1.5 font-semibold text-slate-800">{e.vendor}{e.from_recurring && <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-slate-500" title="Dari langganan">langganan</span>}</p>{e.description && <p className="text-[11px] text-slate-400">{e.description}</p>}</td>
                  <td className="px-3 py-2.5 text-right font-bold text-slate-900">{rp(e.amount_idr)}</td>
                  <td className="px-3 py-2.5 text-right text-slate-600">{rp(e.dpp_idr)}</td>
                  <td className="px-3 py-2.5 text-right">{e.taxable ? <span className="font-semibold text-[#2F6BFF]">{rp(e.ppn_idr)}</span> : <span className="text-slate-300">–</span>}</td>
                  <td className="px-3 py-2.5 text-center">{e.attachment ? <button onClick={() => viewFile(e)} disabled={viewing === e.id} className="inline-flex items-center gap-1 text-xs font-bold text-[#2F6BFF] hover:underline" data-testid={`exp-view-${e.id}`}>{viewing === e.id ? <Loader2 size={13} className="animate-spin" /> : <FileText size={13} />} Lihat</button> : e.needs_efaktur ? <button onClick={() => pickUpload(e)} className="inline-flex items-center gap-1 rounded-lg bg-amber-50 px-2 py-1 text-[11px] font-bold text-amber-700 hover:bg-amber-100" data-testid={`exp-upload-${e.id}`}><AlertTriangle size={12} /> Unggah</button> : <span className="text-[11px] text-slate-300">—</span>}</td>
                  <td className="px-4 py-2.5 text-right"><button onClick={() => remove(e)} className="inline-flex items-center gap-1 rounded-lg bg-rose-50 px-2.5 py-1.5 text-xs font-bold text-rose-600" data-testid={`exp-delete-${e.id}`}><Trash2 size={13} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
