import React, { useMemo } from "react";
import { diffWordsWithSpace } from "diff";

// Word-level diff of two markdown sources: additions green, removals red strikethrough.
export function VersionDiff({ oldText = "", newText = "", oldLabel, newLabel }) {
  const parts = useMemo(() => diffWordsWithSpace(oldText || "", newText || ""), [oldText, newText]);
  const added = parts.filter((p) => p.added).reduce((n, p) => n + p.value.split(/\s+/).filter(Boolean).length, 0);
  const removed = parts.filter((p) => p.removed).reduce((n, p) => n + p.value.split(/\s+/).filter(Boolean).length, 0);
  return (
    <div className="aivora-card overflow-hidden" data-testid="version-diff">
      <div className="flex flex-wrap items-center gap-3 border-b border-[#E7ECF3] bg-slate-50 px-4 py-2.5 text-xs">
        <span className="font-semibold text-slate-700">Perubahan {oldLabel} → {newLabel}</span>
        <span className="rounded-full bg-emerald-100 px-2 py-0.5 font-bold text-emerald-700" data-testid="diff-added">+{added} kata</span>
        <span className="rounded-full bg-rose-100 px-2 py-0.5 font-bold text-rose-700" data-testid="diff-removed">−{removed} kata</span>
        {added === 0 && removed === 0 && <span className="text-slate-500">Tidak ada perbedaan teks.</span>}
      </div>
      <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap break-words p-5 font-sans text-sm leading-relaxed text-slate-700">
        {parts.map((p, i) => p.added
          ? <ins key={i} className="rounded bg-emerald-100 px-0.5 text-emerald-900 no-underline" data-testid="diff-ins">{p.value}</ins>
          : p.removed
          ? <del key={i} className="rounded bg-rose-100 px-0.5 text-rose-800" data-testid="diff-del">{p.value}</del>
          : <span key={i}>{p.value}</span>)}
      </pre>
    </div>
  );
}
