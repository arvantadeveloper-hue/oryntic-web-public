import React, { useCallback, useEffect, useRef, useState } from "react";
import { FileText, Image as ImageIcon, Video, Download, ExternalLink, Loader2, Check, Users } from "lucide-react";
import { api, API_BASE, getToken } from "../lib/api";
import { fileUrl, downloadUrl } from "./MessageExtras";

export const GALLERY_FILTERS = [
  { v: "all", label: "Semua" },
  { v: "document", label: "Dokumen" },
  { v: "image", label: "Gambar" },
  { v: "video", label: "Video" },
];

// Cursor-paginated gallery feed (newest first) with infinite scrolling.
export function useGallery(type = "all", limit = 24) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [hasMore, setHasMore] = useState(false);
  const cursor = useRef(null);
  const busy = useRef(false);

  const fetchPage = useCallback(async (reset) => {
    if (busy.current) return;
    busy.current = true; setLoading(true);
    try {
      const before = reset ? "" : cursor.current ? `&before=${encodeURIComponent(cursor.current)}` : "";
      const r = await api.get(`/gallery?type=${type}&limit=${limit}${before}`);
      setItems((prev) => (reset ? r.data.items : [...prev, ...r.data.items]));
      setHasMore(!!r.data.has_more); cursor.current = r.data.next_before;
    } catch (e) { setHasMore(false); } finally { busy.current = false; setLoading(false); }
  }, [type, limit]);

  useEffect(() => { cursor.current = null; setItems([]); fetchPage(true); }, [fetchPage]);
  const loadMore = () => { if (hasMore && !busy.current) fetchPage(false); };
  return { items, loading, hasMore, loadMore, reload: () => fetchPage(true) };
}

// Fires onVisible whenever the sentinel scrolls into view.
export function Sentinel({ onVisible, root }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const io = new IntersectionObserver((es) => { if (es[0].isIntersecting) onVisible(); }, { root: root?.current || null, rootMargin: "200px" });
    io.observe(el); return () => io.disconnect();
  }, [onVisible, root]);
  return <div ref={ref} className="h-1 w-full" data-testid="gallery-sentinel" />;
}

const exportUrl = (taskId, fmt) => `${API_BASE}/tasks/${taskId}/export/${fmt}?auth=${getToken()}`;
const KIND_ICON = { document: FileText, image: ImageIcon, video: Video };

export function GalleryCard({ item, selectable = false, selected = false, onSelect }) {
  const Icon = KIND_ICON[item.kind] || FileText;
  const date = new Date(item.created_at).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });
  const click = selectable ? () => onSelect(item) : undefined;
  return (
    <div onClick={click} data-testid={`gallery-item-${item.kind}`} className={`group relative flex flex-col overflow-hidden rounded-2xl border bg-white transition ${selectable ? "cursor-pointer" : ""} ${selected ? "border-[#2F6BFF] ring-2 ring-[#2F6BFF]/30" : "border-[#E7ECF3] hover:shadow-md"}`}>
      {selectable && <span className={`absolute right-2 top-2 z-10 flex h-6 w-6 items-center justify-center rounded-md border bg-white ${selected ? "btn-grad border-transparent" : "border-slate-300"}`} data-testid="gallery-select-mark">{selected && <Check size={13} />}</span>}
      <div className="flex h-36 items-center justify-center overflow-hidden bg-slate-50">
        {item.kind === "image" ? <img src={fileUrl(item.path)} alt={item.name} loading="lazy" className="h-full w-full object-cover" />
          : item.kind === "video" ? <video src={fileUrl(item.path)} preload="metadata" muted className="h-full w-full object-cover" />
          : <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#EEF3FF] text-[#2F6BFF]"><Icon size={26} /></span>}
      </div>
      <div className="flex flex-1 flex-col p-3">
        <p className="truncate text-sm font-semibold text-slate-900" title={item.name}>{item.name}</p>
        <p className="mt-0.5 flex items-center gap-1 truncate text-[11px] text-slate-400">{item.team && <Users size={11} />}{item.persona_name || "Asisten"} · {date}{item.version > 1 ? ` · v${item.version}` : ""}</p>
        {!selectable && (
          <div className="mt-2 flex flex-wrap gap-1.5" onClick={(e) => e.stopPropagation()}>
            {item.kind === "document" ? (<>
              <a href={`${window.location.origin}/workspace/${item.task_id}`} target="_blank" rel="noreferrer" className="flex items-center gap-1 rounded-lg bg-[#EEF3FF] px-2 py-1 text-[11px] font-semibold text-[#2F6BFF] hover:bg-[#E0E9FF]" data-testid="gallery-open"><ExternalLink size={11} /> Buka</a>
              <a href={exportUrl(item.task_id, "docx")} download className="flex items-center gap-1 rounded-lg bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-200" data-testid="gallery-dl-docx"><Download size={11} /> Word</a>
              <a href={exportUrl(item.task_id, "pdf")} download className="flex items-center gap-1 rounded-lg bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-200" data-testid="gallery-dl-pdf"><Download size={11} /> PDF</a>
            </>) : (<>
              <a href={fileUrl(item.path)} target="_blank" rel="noreferrer" className="flex items-center gap-1 rounded-lg bg-[#EEF3FF] px-2 py-1 text-[11px] font-semibold text-[#2F6BFF] hover:bg-[#E0E9FF]" data-testid="gallery-open"><ExternalLink size={11} /> Buka</a>
              <a href={downloadUrl(item.path)} download={item.name} className="flex items-center gap-1 rounded-lg bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-200" data-testid="gallery-dl-file"><Download size={11} /> Unduh</a>
            </>)}
          </div>
        )}
      </div>
    </div>
  );
}

export function GalleryGrid({ type, selectable = false, selectedIds = [], onSelect, scrollRoot, emptyText = "Belum ada berkas. Minta asisten membuat dokumen, gambar, atau video dari chat." }) {
  const g = useGallery(type);
  return (
    <div data-testid="gallery-grid">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {g.items.map((it) => <GalleryCard key={it.id} item={it} selectable={selectable} selected={selectedIds.includes(it.id)} onSelect={onSelect} />)}
      </div>
      {g.loading && <p className="flex items-center justify-center gap-2 py-6 text-sm text-slate-400" data-testid="gallery-loading"><Loader2 size={16} className="animate-spin" /> Memuat berkas…</p>}
      {!g.loading && g.items.length === 0 && <p className="py-12 text-center text-sm text-slate-400" data-testid="gallery-empty">{emptyText}</p>}
      {!g.loading && g.hasMore && <Sentinel onVisible={g.loadMore} root={scrollRoot} />}
      {!g.loading && !g.hasMore && g.items.length > 0 && <p className="py-4 text-center text-[11px] text-slate-300">Semua berkas sudah ditampilkan</p>}
    </div>
  );
}

export function GalleryFilterBar({ value, onChange, counts }) {
  return (
    <div className="flex flex-wrap gap-2" data-testid="gallery-filters">
      {GALLERY_FILTERS.map((f) => (
        <button key={f.v} onClick={() => onChange(f.v)} data-testid={`gallery-filter-${f.v}`} className={`rounded-full px-3.5 py-1.5 text-xs font-semibold transition ${value === f.v ? "btn-grad" : "border border-[#E7ECF3] bg-white text-slate-600 hover:bg-slate-50"}`}>{f.label}</button>
      ))}
    </div>
  );
}
