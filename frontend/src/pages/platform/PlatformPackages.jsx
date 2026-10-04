import React from "react";
import { Loader2, Plus, Trash2, ArrowUp, ArrowDown, Star } from "lucide-react";
import { usePricingDraft, NumField, SaveBar } from "./pricingDraft";
import { rp, num } from "./PlatformDashboard";

const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "paket";

export default function PlatformPackages() {
  const { draft, preview, update, save, reset, busy, dirty } = usePricingDraft();
  if (!draft || !preview) return <p className="flex items-center gap-2 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat…</p>;
  const tiers = draft.packages || [];
  const setTiers = (fn) => update((d) => ({ ...d, packages: fn([...(d.packages || [])]) }));
  const setTier = (i, patch) => setTiers((t) => { t[i] = { ...t[i], ...patch }; return t; });
  const move = (i, dir) => setTiers((t) => { const j = i + dir; if (j < 0 || j >= t.length) return t; [t[i], t[j]] = [t[j], t[i]]; return t; });
  const add = () => setTiers((t) => [...t, { id: `paket-${t.length + 1}`, name: `Paket ${t.length + 1}`, usd: 10, discount_pct: 0, best_value: false }]);
  const priceOf = (id) => preview.packages.find((p) => p.id === id);
  return (
    <div data-testid="platform-packages">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-black text-slate-900">Paket Kredit</h1><p className="text-sm text-slate-500">Harga Rp = USD × (1 + margin paket − diskon) × (1 + PPN) × kurs, dibulatkan. Kredit = USD ÷ nilai 1 kredit.</p></div>
        <SaveBar dirty={dirty} busy={busy} onSave={save} onReset={reset} testid="pkg" />
      </div>
      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        <NumField label="Margin paket" value={draft.package_margin_pct} onChange={(v) => update({ package_margin_pct: v })} suffix="%" step={0.5} testid="pkg-margin" />
        <NumField label="Pembulatan harga" value={draft.package_round_idr} onChange={(v) => update({ package_round_idr: v })} suffix="Rp" step={100} min={1} testid="pkg-round" />
        <div className="aivora-card flex items-center justify-between p-4 text-xs text-slate-600"><span>PPN {draft.tax_pct}% · Kurs {rp(draft.usd_to_idr)}</span><span className="text-slate-400">ubah di Tarif & Margin</span></div>
      </div>
      <div className="mt-6 space-y-3">
        {tiers.map((t, i) => { const p = priceOf(t.id); return (
          <div key={i} className="aivora-card grid items-end gap-3 p-4 md:grid-cols-[1fr_1.4fr_1fr_1fr_auto_auto]" data-testid={`pkg-tier-${t.id}`}>
            <label className="block"><span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">ID</span><input value={t.id} onChange={(e) => setTier(i, { id: slug(e.target.value) })} data-testid={`pkg-id-${i}`} className="mt-1 w-full rounded-xl border border-[#E7ECF3] px-3 py-2 text-sm outline-none focus:border-[#2F6BFF]" /></label>
            <label className="block"><span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Nama</span><input value={t.name} onChange={(e) => setTier(i, { name: e.target.value })} data-testid={`pkg-name-${i}`} className="mt-1 w-full rounded-xl border border-[#E7ECF3] px-3 py-2 text-sm outline-none focus:border-[#2F6BFF]" /></label>
            <NumField label="Nilai (USD)" value={t.usd} onChange={(v) => setTier(i, { usd: v })} step={1} min={1} testid={`pkg-usd-${i}`} />
            <NumField label="Diskon" value={t.discount_pct} onChange={(v) => setTier(i, { discount_pct: v })} suffix="%" step={1} testid={`pkg-disc-${i}`} />
            <div className="text-right"><p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Hasil</p><p className="text-base font-black text-slate-900" data-testid={`pkg-price-${i}`}>{p ? rp(p.price_idr) : "…"}</p><p className="text-[11px] text-slate-400">{p ? `${num(p.credits)} kredit` : ""}</p></div>
            <div className="flex items-center gap-1">
              <button onClick={() => setTiers((x) => x.map((y, k) => ({ ...y, best_value: k === i ? !y.best_value : false })))} title="Tandai Hemat / terpopuler" data-testid={`pkg-best-${i}`} className={`rounded-lg p-2 ${t.best_value ? "bg-amber-100 text-amber-600" : "text-slate-400 hover:bg-slate-100"}`}><Star size={15} /></button>
              <button onClick={() => move(i, -1)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100" data-testid={`pkg-up-${i}`}><ArrowUp size={15} /></button>
              <button onClick={() => move(i, 1)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100" data-testid={`pkg-down-${i}`}><ArrowDown size={15} /></button>
              <button onClick={() => setTiers((x) => x.filter((_, k) => k !== i))} disabled={tiers.length <= 1} className="rounded-lg p-2 text-rose-400 hover:bg-rose-50 disabled:opacity-30" data-testid={`pkg-del-${i}`}><Trash2 size={15} /></button>
            </div>
          </div>); })}
        <button onClick={add} disabled={tiers.length >= 12} className="flex items-center gap-2 rounded-xl border border-dashed border-[#CBD5E1] px-4 py-2.5 text-sm font-semibold text-slate-600 hover:border-[#2F6BFF] hover:text-[#2F6BFF] disabled:opacity-40" data-testid="pkg-add"><Plus size={15} /> Tambah tier</button>
      </div>
    </div>
  );
}
