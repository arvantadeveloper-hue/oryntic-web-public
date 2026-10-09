import React, { useEffect, useMemo, useState } from "react";
import { Loader2, Save, Plus, Trash2, DownloadCloud, Calculator, ChevronRight, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

const N = (v) => (Number.isFinite(+v) ? +v : 0);
const usd = (v) => `$${N(v) < 0.01 ? N(v).toFixed(6) : N(v).toFixed(4)}`;
const IN = "input-dark w-full py-1.5 text-xs";

// margin/PPN: komponen → layanan → provider → global
const pct = (field, c, s, p, g) => {
  for (const src of [c, s, p]) if (src?.[field] !== null && src?.[field] !== undefined && src?.[field] !== "") return N(src[field]);
  return N(g[field]);
};
// biaya 1 satuan: harga ÷ qty dasar (gambar = flat per gambar karena qty dasar 1)
const calc = (c, s, p, g) => {
  const base = N(c.usd) / Math.max(N(c.qty_basis) || 1, 1e-9);
  const m = pct("margin_pct", c, s, p, g), t = pct("tax_pct", c, s, p, g);
  const total = base * (1 + m / 100) * (1 + t / 100);
  return { base, m, t, total, credits: total / Math.max(N(g.usd_per_credit) || 0.001, 1e-9) };
};

const ComponentRow = ({ c, s, p, g, onChange, onDelete }) => {
  const k = calc(c, s, p, g);
  return (
    <tr className="border-t border-[#EEF1F6] text-xs" data-testid={`pc-comp-${s.id}-${c.id}`}>
      <td className="py-2 pr-2">
        <p className="font-semibold text-slate-800">{c.label}</p>
        <p className="font-mono text-[10px] text-slate-400">{c.id} · {c.modality}/{c.direction}</p>
      </td>
      <td className="px-1"><input value={c.usd} onChange={(e) => onChange({ usd: e.target.value })} className={`${IN} w-20`} data-testid={`pc-usd-${s.id}-${c.id}`} /></td>
      <td className="px-1"><input value={c.qty_basis} onChange={(e) => onChange({ qty_basis: e.target.value })} className={`${IN} w-20`} data-testid={`pc-basis-${s.id}-${c.id}`} /></td>
      <td className="px-1"><input value={c.unit} onChange={(e) => onChange({ unit: e.target.value })} className={`${IN} w-20`} data-testid={`pc-unit-${s.id}-${c.id}`} /></td>
      <td className="px-1"><input value={c.margin_pct ?? ""} placeholder={`${pct("margin_pct", {}, s, p, g)}`} onChange={(e) => onChange({ margin_pct: e.target.value === "" ? null : e.target.value })} className={`${IN} w-16`} data-testid={`pc-margin-${s.id}-${c.id}`} /></td>
      <td className="px-1"><input value={c.tax_pct ?? ""} placeholder={`${pct("tax_pct", {}, s, p, g)}`} onChange={(e) => onChange({ tax_pct: e.target.value === "" ? null : e.target.value })} className={`${IN} w-16`} data-testid={`pc-tax-${s.id}-${c.id}`} /></td>
      <td className="px-2 text-right text-slate-500" title="biaya provider per 1 satuan">{usd(k.base)}</td>
      <td className="px-2 text-right text-slate-500" title="setelah margin & PPN">{usd(k.total)}</td>
      <td className="px-2 text-right font-bold text-[#2F6BFF]" data-testid={`pc-credits-${s.id}-${c.id}`}>{k.credits < 1 ? k.credits.toFixed(3) : Math.ceil(k.credits)}</td>
      <td className="px-1 text-right">
        <label className="mr-2 text-[10px] text-slate-500"><input type="checkbox" checked={c.enabled !== false} onChange={(e) => onChange({ enabled: e.target.checked })} /> aktif</label>
        <button onClick={onDelete} className="text-slate-300 hover:text-red-500" data-testid={`pc-del-${s.id}-${c.id}`}><Trash2 size={12} /></button>
      </td>
    </tr>
  );
};

export const PricingCatalogCard = () => {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState({});
  const [busy, setBusy] = useState(false);
  const [diff, setDiff] = useState(null);
  const [sim, setSim] = useState({ service_id: "gpt-luna", component_id: "text_out", qty: 1000, result: null });

  const load = () => api.get("/admin/pricing-catalog").then((r) => setData(r.data)).catch((e) => toast.error(e?.response?.data?.detail || "Gagal memuat katalog harga"));
  useEffect(() => { load(); }, []);

  const g = data?.globals || { margin_pct: 30, tax_pct: 11, usd_per_credit: 0.001 };
  const flat = useMemo(() => {
    const rows = [];
    (data?.catalog?.providers || []).forEach((p) => p.services.forEach((s) => s.components.forEach((c) => rows.push({ id: `${s.id}|${c.id}`, label: `${s.label} — ${c.label}`, s, c }))));
    return rows;
  }, [data]);

  if (!data) return <p className="flex items-center gap-2 text-sm text-slate-400" data-testid="pc-loading"><Loader2 size={14} className="animate-spin" /> Memuat katalog harga…</p>;

  const mutate = (pid, sid, cid, patch) => setData((d) => ({
    ...d,
    catalog: {
      ...d.catalog,
      providers: d.catalog.providers.map((p) => p.id !== pid ? p : {
        ...p,
        services: sid === null ? p.services : p.services.map((s) => s.id !== sid ? s : {
          ...s,
          components: cid === null ? s.components : s.components.map((c) => (c.id !== cid ? c : { ...c, ...patch })),
          ...(cid === null ? patch : {}),
        }),
        ...(sid === null ? patch : {}),
      }),
    },
  }));

  const addComponent = (pid, sid) => mutate(pid, sid, null, {
    components: [...(data.catalog.providers.find((p) => p.id === pid).services.find((s) => s.id === sid).components),
      { id: `komponen_${Date.now().toString(36)}`, label: "Komponen baru", unit: "token", qty_basis: 1000000, usd: 0, modality: "text", direction: "input", margin_pct: null, tax_pct: null, enabled: true, note: "" }],
  });
  const delComponent = (pid, sid, cid) => mutate(pid, sid, null, {
    components: data.catalog.providers.find((p) => p.id === pid).services.find((s) => s.id === sid).components.filter((c) => c.id !== cid),
  });

  const save = async () => {
    setBusy(true);
    try {
      const body = { version: data.catalog.version || 2, providers: data.catalog.providers };
      const r = await api.put("/admin/pricing-catalog", body);
      setData((d) => ({ ...d, catalog: r.data.catalog, table: r.data.table }));
      toast.success("Katalog harga disimpan — tarif baru langsung dipakai untuk penagihan");
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan"); } finally { setBusy(false); }
  };

  const runImport = async (pid) => {
    setBusy(true);
    try {
      const r = await api.post(`/admin/pricing-catalog/import?provider_id=${pid}`);
      setDiff(r.data);
      if (!r.data.rows?.length) toast.error("Tidak ada angka yang bisa dibaca dari halaman itu — edit manual saja");
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal impor"); } finally { setBusy(false); }
  };
  const applyImport = async () => {
    setBusy(true);
    try {
      const rows = diff.rows.filter((r) => r.changed);
      const r = await api.post("/admin/pricing-catalog/import/apply", { provider_id: diff.provider, rows });
      setData((d) => ({ ...d, catalog: r.data.catalog, table: r.data.table }));
      setDiff(null);
      toast.success(`${rows.length} harga diperbarui dari docs`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal menerapkan"); } finally { setBusy(false); }
  };

  const runQuote = async () => {
    try {
      const r = await api.post("/admin/pricing-catalog/quote", { service_id: sim.service_id, component_id: sim.component_id, qty: sim.qty === "" ? null : N(sim.qty) });
      setSim({ ...sim, result: r.data });
    } catch (e) { toast.error(e?.response?.data?.detail || "Komponen tidak ditemukan"); }
  };

  return (
    <div data-testid="pricing-catalog">
      <p className="text-sm text-slate-500">
        Provider → layanan/model → komponen harga → satuan. Rumus satu pintu: <b>biaya = harga × qty ÷ satuan dasar</b>, lalu <b>× (1+margin) × (1+PPN) ÷ nilai kredit</b>.
        Margin/PPN kosong = ikut induknya (layanan → provider → global {g.margin_pct}% / {g.tax_pct}%). <b>Katalog ini satu-satunya sumber tarif</b> — chat, panggilan, gambar (flat per gambar), video, STT/TTS, dan tool semuanya menagih dari sini.
      </p>

      <div className="mt-4 space-y-3">
        {data.catalog.providers.map((p) => (
          <div key={p.id} className="aivora-card overflow-hidden p-0" data-testid={`pc-provider-${p.id}`}>
            <div className="flex flex-wrap items-center gap-3 px-5 py-3">
              <button onClick={() => setOpen((o) => ({ ...o, [p.id]: !o[p.id] }))} className="flex items-center gap-2 text-left" data-testid={`pc-toggle-${p.id}`}>
                <ChevronRight size={16} className={`text-slate-400 transition-transform ${open[p.id] ? "rotate-90" : ""}`} />
                <span className="text-sm font-bold text-slate-900">{p.label}</span>
                <span className="text-[11px] text-slate-400">{p.services.length} layanan</span>
              </button>
              {p.docs_url && <a href={p.docs_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-[11px] text-[#2F6BFF] hover:underline">docs <ExternalLink size={10} /></a>}
              <div className="ml-auto flex items-center gap-2 text-xs">
                <label className="flex items-center gap-1 text-slate-500">margin <input value={p.margin_pct ?? ""} placeholder={`${g.margin_pct}`} onChange={(e) => mutate(p.id, null, null, { margin_pct: e.target.value === "" ? null : e.target.value })} className="input-dark w-14 py-1 text-xs" data-testid={`pc-pmargin-${p.id}`} />%</label>
                <label className="flex items-center gap-1 text-slate-500">PPN <input value={p.tax_pct ?? ""} placeholder={`${g.tax_pct}`} onChange={(e) => mutate(p.id, null, null, { tax_pct: e.target.value === "" ? null : e.target.value })} className="input-dark w-14 py-1 text-xs" />%</label>
                {p.docs_url && <button onClick={() => runImport(p.id)} disabled={busy} className="flex items-center gap-1 rounded-lg bg-slate-100 px-2.5 py-1.5 font-semibold text-slate-700 hover:bg-slate-200" data-testid={`pc-import-${p.id}`}><DownloadCloud size={12} /> Impor dari docs</button>}
              </div>
            </div>
            {open[p.id] && (
              <div className="border-t border-[#EEF1F6] bg-[#FAFBFE] px-5 py-4">
                {p.services.map((s) => (
                  <div key={s.id} className="mb-5 last:mb-0" data-testid={`pc-service-${s.id}`}>
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-semibold text-slate-800">{s.label}</p>
                      <span className="rounded-full bg-[#EEF3FF] px-2 py-0.5 text-[10px] font-bold text-[#2F6BFF]">{s.kind}</span>
                      <span className="font-mono text-[10px] text-slate-400">{s.id}</span>
                      {s.note && <span className="text-[10px] text-amber-600">{s.note}</span>}
                      <button onClick={() => addComponent(p.id, s.id)} className="ml-auto flex items-center gap-1 text-[11px] font-semibold text-[#2F6BFF]" data-testid={`pc-add-${s.id}`}><Plus size={11} /> Komponen</button>
                    </div>
                    <div className="mt-2 overflow-x-auto">
                      <table className="w-full min-w-[820px] text-left">
                        <thead><tr className="text-[10px] uppercase tracking-wide text-slate-400">
                          <th className="pb-1">Komponen</th><th className="px-1 pb-1">Harga USD</th><th className="px-1 pb-1">Per (qty dasar)</th><th className="px-1 pb-1">Satuan</th>
                          <th className="px-1 pb-1">Margin</th><th className="px-1 pb-1">PPN</th>
                          <th className="px-2 pb-1 text-right">Biaya / satuan</th><th className="px-2 pb-1 text-right">Total / satuan</th><th className="px-2 pb-1 text-right">Kredit / satuan</th><th /></tr></thead>
                        <tbody>
                          {s.components.map((c) => (
                            <ComponentRow key={c.id} c={c} s={s} p={p} g={g}
                              onChange={(patch) => mutate(p.id, s.id, c.id, patch)}
                              onDelete={() => delComponent(p.id, s.id, c.id)} />
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="mt-4 aivora-card p-5" data-testid="pc-simulator">
        <p className="flex items-center gap-2 text-sm font-bold text-slate-900"><Calculator size={16} className="text-[#2F6BFF]" /> Simulator harga</p>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="text-xs"><span className="mb-1 block font-semibold text-slate-700">Komponen</span>
            <select value={`${sim.service_id}|${sim.component_id}`} onChange={(e) => { const [s, c] = e.target.value.split("|"); setSim({ ...sim, service_id: s, component_id: c, result: null }); }} className="input-dark w-80 py-1.5 text-xs" data-testid="pc-sim-select">
              {flat.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select></label>
          <label className="text-xs"><span className="mb-1 block font-semibold text-slate-700">Jumlah (satuan komponen)</span>
            <input value={sim.qty} onChange={(e) => setSim({ ...sim, qty: e.target.value })} className="input-dark w-40 py-1.5 text-xs" data-testid="pc-sim-qty" /></label>
          <button onClick={runQuote} className="btn-primary py-1.5 text-xs" data-testid="pc-sim-run">Hitung</button>
          {sim.result && (
            <div className="rounded-xl bg-[#F6F8FD] px-4 py-2 text-xs" data-testid="pc-sim-result">
              <p className="text-slate-500">{sim.result.qty} {sim.result.unit} · {usd(sim.result.unit_usd)} per {sim.result.qty_basis} {sim.result.unit}</p>
              <p className="text-slate-700">biaya {usd(sim.result.base_usd)} + margin {sim.result.margin_pct}% ({usd(sim.result.margin_usd)}) + PPN {sim.result.tax_pct}% ({usd(sim.result.tax_usd)}) = <b>{usd(sim.result.total_usd)}</b></p>
              <p className="font-bold text-[#2F6BFF]">{sim.result.credits_exact.toFixed(3)} kredit (dibulatkan {sim.result.credits})</p>
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 flex items-center justify-end gap-3">
        {data.catalog.updated_at && <span className="text-[11px] text-slate-400" data-testid="pc-updated">Terakhir disimpan: {new Date(data.catalog.updated_at).toLocaleString("id-ID")}</span>}
        <button onClick={save} disabled={busy} className="btn-primary py-2" data-testid="pc-save">{busy ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Simpan katalog</button>
      </div>

      {diff && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" data-testid="pc-diff-modal">
          <div className="max-h-[80vh] w-full max-w-2xl overflow-auto rounded-2xl bg-white p-6">
            <p className="text-base font-bold text-slate-900">Impor harga {diff.provider}</p>
            <p className="mt-1 text-xs text-slate-500">Sumber: {diff.docs_url}</p>
            {!!diff.unmatched?.length && <p className="mt-2 text-[11px] text-amber-600">Tidak terbaca otomatis: {diff.unmatched.join(", ")} — edit manual.</p>}
            <table className="mt-3 w-full text-left text-xs">
              <thead><tr className="text-[10px] uppercase text-slate-400"><th className="pb-1">Komponen</th><th className="pb-1 text-right">Sekarang</th><th className="pb-1 text-right">Docs</th></tr></thead>
              <tbody>
                {diff.rows.map((r) => (
                  <tr key={r.path} className={`border-t border-[#EEF1F6] ${r.changed ? "bg-amber-50" : ""}`}>
                    <td className="py-1.5">{r.service} — {r.component}</td>
                    <td className="text-right text-slate-500">${r.current_usd}</td>
                    <td className={`text-right font-bold ${r.changed ? "text-amber-700" : "text-slate-400"}`}>${r.doc_usd}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setDiff(null)} className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-700" data-testid="pc-diff-cancel">Tutup</button>
              <button onClick={applyImport} disabled={busy || !diff.rows.some((r) => r.changed)} className="btn-primary py-2 text-sm" data-testid="pc-diff-apply">Terapkan {diff.rows.filter((r) => r.changed).length} perubahan</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
