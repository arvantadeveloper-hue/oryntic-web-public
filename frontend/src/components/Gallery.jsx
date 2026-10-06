import React, { useCallback, useEffect, useRef, useState } from "react";
import { HardDrive, FileText, Image as ImageIcon, Video, Download, ExternalLink, Loader2, Check, Users, Share2, Search, Send, MessageSquare, Wand2 } from "lucide-react";
import { api, API_BASE, getToken } from "../lib/api";
import { fileUrl, downloadUrl, openPublish, mediaSrc, Lightbox } from "./MessageExtras";

export const GALLERY_FILTERS = [
  { v: "all", label: "Semua" },
  { v: "document", label: "Dokumen" },
  { v: "image", label: "Gambar" },
  { v: "video", label: "Video" },
];

// Cursor-paginated gallery feed (newest first) with infinite scrolling.
export function useGallery(type = "all", limit = 24, q = "") {
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
      const r = await api.get(`/gallery?type=${type}&limit=${limit}${q ? `&q=${encodeURIComponent(q)}` : ""}${before}`);
      setItems((prev) => (reset ? r.data.items : [...prev, ...r.data.items]));
      setHasMore(!!r.data.has_more); cursor.current = r.data.next_before;
    } catch (e) { setHasMore(false); } finally { busy.current = false; setLoading(false); }
  }, [type, limit, q]);

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
const KIND_ICON = { document: FileText, image: ImageIcon, video: Video, drive: HardDrive };

export function GalleryCard({ item, selectable = false, selected = false, onSelect, onOpen, onShare }) {
  const Icon = KIND_ICON[item.kind] || FileText;
  const date = new Date(item.created_at).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });
  const [zoom, setZoom] = useState(false);
  const click = selectable ? () => onSelect(item) : onOpen ? () => onOpen(item) : item.kind === "image" ? () => setZoom(true) : undefined;
  return (
    <div onClick={click} data-testid={`gallery-item-${item.kind}`} className={`group relative flex flex-col overflow-hidden rounded-2xl border bg-white transition ${selectable || onOpen || item.kind === "image" ? "cursor-pointer" : ""} ${selected ? "border-[#2F6BFF] ring-2 ring-[#2F6BFF]/30" : "border-[#E7ECF3] hover:shadow-md"}`}>
      {zoom && <Lightbox media={{ type: "image", path: item.path, name: item.name, request: item.title }} onClose={() => setZoom(false)} />}
      {selectable && <span className={`absolute right-2 top-2 z-10 flex h-6 w-6 items-center justify-center rounded-md border bg-white ${selected ? "btn-grad border-transparent" : "border-slate-300"}`} data-testid="gallery-select-mark">{selected && <Check size={13} />}</span>}
      <div className="flex h-36 items-center justify-center overflow-hidden bg-slate-50">
        {item.kind === "image" ? <img src={fileUrl(item.path)} alt={item.name} loading="lazy" className="h-full w-full object-cover" />
          : item.kind === "video" ? <video src={mediaSrc(item)} preload="metadata" muted className="h-full w-full object-cover" />
          : <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#EEF3FF] text-[#2F6BFF]"><Icon size={26} /></span>}
      </div>
      <div className="flex flex-1 flex-col p-3">
        <p className="truncate text-sm font-semibold text-slate-900" title={item.title || item.name} data-testid="gallery-item-title">{item.edited && <Wand2 size={11} className="mr-1 inline text-[#2F6BFF]" />}{item.title || item.name}</p>
        <p className="mt-0.5 flex items-center gap-1 truncate text-[11px] text-slate-400">{item.team && <Users size={11} />}{item.persona_name || "Asisten"} · {date}{item.version > 1 ? ` · v${item.version}` : ""}</p>
        {!selectable && (
          <div className="mt-2 flex flex-wrap gap-1.5" onClick={(e) => e.stopPropagation()}>
            {item.kind === "drive" ? (
              <a href={item.link} target="_blank" rel="noreferrer" className="flex items-center gap-1 rounded-lg bg-[#EEF3FF] px-2 py-1 text-[11px] font-semibold text-[#2F6BFF] hover:bg-[#E0E8FF]" data-testid="gallery-open-drive"><ExternalLink size={11} /> Buka di Google Drive</a>
            ) : item.kind === "document" ? (<>
              <a href={`${window.location.origin}/workspace/${item.task_id}`} target="_blank" rel="noreferrer" className="flex items-center gap-1 rounded-lg bg-[#EEF3FF] px-2 py-1 text-[11px] font-semibold text-[#2F6BFF] hover:bg-[#E0E9FF]" data-testid="gallery-open"><ExternalLink size={11} /> Buka</a>
              <a href={exportUrl(item.task_id, "docx")} download className="flex items-center gap-1 rounded-lg bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-200" data-testid="gallery-dl-docx"><Download size={11} /> Word</a>
              <a href={exportUrl(item.task_id, "pdf")} download className="flex items-center gap-1 rounded-lg bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-200" data-testid="gallery-dl-pdf"><Download size={11} /> PDF</a>
            </>) : item.drive_id ? (<>
              <a href={item.link} target="_blank" rel="noreferrer" className="flex items-center gap-1 rounded-lg bg-[#EEF3FF] px-2 py-1 text-[11px] font-semibold text-[#2F6BFF] hover:bg-[#E0E9FF]" data-testid="gallery-open-drive"><HardDrive size={11} /> Buka di Google Drive</a>
              {item.conversation_id && <a href={`/chat/${item.conversation_id}`} className="flex items-center gap-1 rounded-lg bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-200" data-testid="gallery-open-chat"><MessageSquare size={11} /> Chat</a>}
              <button onClick={() => openPublish({ type: item.kind, drive_id: item.drive_id, name: item.name }, item.title || "")} className="flex items-center gap-1 rounded-lg bg-[#2F6BFF] px-2 py-1 text-[11px] font-semibold text-white hover:bg-[#2558d6]" data-testid="gallery-publish"><Send size={11} /> Publikasikan</button>
            </>) : (<>
              <a href={fileUrl(item.path)} target="_blank" rel="noreferrer" className="flex items-center gap-1 rounded-lg bg-[#EEF3FF] px-2 py-1 text-[11px] font-semibold text-[#2F6BFF] hover:bg-[#E0E9FF]" data-testid="gallery-open"><ExternalLink size={11} /> Buka</a>
              <a href={downloadUrl(item.path)} download={item.name} className="flex items-center gap-1 rounded-lg bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-200" data-testid="gallery-dl-file"><Download size={11} /> Unduh</a>
              {item.conversation_id && <a href={`/chat/${item.conversation_id}`} className="flex items-center gap-1 rounded-lg bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-200" data-testid="gallery-open-chat"><MessageSquare size={11} /> Chat</a>}
              <button onClick={() => openPublish({ type: item.kind, path: item.path, name: item.name }, item.title || "")} className="flex items-center gap-1 rounded-lg bg-[#2F6BFF] px-2 py-1 text-[11px] font-semibold text-white hover:bg-[#2558d6]" data-testid="gallery-publish"><Send size={11} /> Publikasikan</button>
            </>)}
            {onShare && item.kind !== "drive" && <button onClick={() => onShare(item)} className="flex items-center gap-1 rounded-lg bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-200" data-testid="gallery-share"><Share2 size={11} /> Bagikan</button>}
          </div>
        )}
      </div>
    </div>
  );
}

export function GalleryGrid({ type, q = "", selectable = false, selectedIds = [], onSelect, onOpen, onShare, scrollRoot, emptyText = "Belum ada berkas. Minta asisten membuat dokumen, gambar, atau video dari chat." }) {
  const g = useGallery(type, 24, q);
  return (
    <div data-testid="gallery-grid">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {g.items.map((it) => <GalleryCard key={it.id} item={it} selectable={selectable} selected={selectedIds.includes(it.id)} onSelect={onSelect} onOpen={onOpen} onShare={onShare} />)}
      </div>
      {g.loading && <p className="flex items-center justify-center gap-2 py-6 text-sm text-slate-400" data-testid="gallery-loading"><Loader2 size={16} className="animate-spin" /> Memuat berkas…</p>}
      {!g.loading && g.items.length === 0 && <p className="py-12 text-center text-sm text-slate-400" data-testid="gallery-empty">{q ? `Tidak ada berkas yang cocok dengan «${q}».` : emptyText}</p>}
      {!g.loading && g.hasMore && <Sentinel onVisible={g.loadMore} root={scrollRoot} />}
      {!g.loading && !g.hasMore && g.items.length > 0 && <p className="py-4 text-center text-[11px] text-slate-300">Semua berkas sudah ditampilkan</p>}
    </div>
  );
}

export function GallerySearch({ value, onChange }) {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => onChange(v.trim()), 350); return () => clearTimeout(t); }, [v]); // eslint-disable-line
  return (
    <div className="relative w-full sm:w-72"><Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
      <input className="input-dark py-2 pl-10" placeholder="Cari prompt gambar/video, judul, atau isi dokumen…" value={v} onChange={(e) => setV(e.target.value)} data-testid="gallery-search" /></div>
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
