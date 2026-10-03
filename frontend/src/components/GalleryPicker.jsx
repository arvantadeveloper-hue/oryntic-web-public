import React, { useRef, useState } from "react";
import { X, Images, Paperclip } from "lucide-react";
import { GalleryGrid, GalleryFilterBar } from "./Gallery";

// Pick existing gallery files to attach to a chat message (attached by reference — no re-upload).
export function GalleryPicker({ onClose, onPick, max = 5 }) {
  const [type, setType] = useState("all");
  const [sel, setSel] = useState([]);
  const scrollRef = useRef(null);
  const toggle = (it) => setSel((s) => (s.some((x) => x.id === it.id) ? s.filter((x) => x.id !== it.id) : s.length >= max ? s : [...s, it]));
  const confirm = () => {
    onPick(sel.map((it) => ({ type: "gallery", kind: it.kind, name: it.name, path: it.path, task_id: it.kind === "document" ? it.task_id : undefined, format: it.format })));
    onClose();
  };
  return (
    <div className="fixed inset-0 z-[93] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} />
      <div className="relative flex max-h-[85vh] w-full max-w-3xl flex-col rounded-3xl border border-[#E7ECF3] bg-white shadow-2xl fade-up" data-testid="gallery-picker">
        <div className="flex items-start justify-between gap-3 border-b border-[#E7ECF3] p-5">
          <div>
            <h3 className="flex items-center gap-2 text-lg font-bold text-slate-900"><Images size={18} className="text-[#2F6BFF]" /> Lampirkan dari Galeri</h3>
            <p className="mt-0.5 text-xs text-slate-500">Pilih hingga {max} berkas. Asisten membaca isinya langsung dari penyimpanan — tanpa upload ulang.</p>
          </div>
          <button onClick={onClose} className="text-slate-400" data-testid="gallery-picker-close"><X size={18} /></button>
        </div>
        <div className="px-5 pt-4"><GalleryFilterBar value={type} onChange={setType} /></div>
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto p-5">
          <GalleryGrid type={type} selectable selectedIds={sel.map((x) => x.id)} onSelect={toggle} scrollRoot={scrollRef} emptyText="Belum ada berkas di Galeri." />
        </div>
        <div className="flex items-center justify-between border-t border-[#E7ECF3] p-4">
          <span className="text-xs font-semibold text-slate-500" data-testid="gallery-picker-count">{sel.length ? `${sel.length} dipilih` : "Belum ada yang dipilih"}</span>
          <button onClick={confirm} disabled={!sel.length} className="btn-grad flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm disabled:opacity-50" data-testid="gallery-picker-attach"><Paperclip size={15} /> Lampirkan</button>
        </div>
      </div>
    </div>
  );
}
