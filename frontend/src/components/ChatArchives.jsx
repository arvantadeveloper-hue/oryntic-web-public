import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Archive, Loader2, X } from "lucide-react";
import { api } from "../lib/api";
import { ArchiveCard } from "../pages/Archives";
import { Sentinel } from "./Gallery";

const PAGE = 15;

// Archives of ONE chat, same cards as the Arsip menu (restore / reminder / contents). Newest at the bottom;
// scrolling UP loads older pages while keeping the viewport anchored.
export function ChatArchivesModal({ cid, onClose, onRestored }) {
  const [items, setItems] = useState(null); // ascending (oldest → newest)
  const [next, setNext] = useState(null);
  const [busy, setBusy] = useState(false);
  const boxRef = useRef(null);
  const anchorRef = useRef(null); // {height, top} to restore after prepending

  const load = useCallback(async (before) => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await api.get("/archives", { params: { conversation_id: cid, limit: PAGE, before } });
      const older = [...r.data.items].reverse();
      if (before && boxRef.current) anchorRef.current = { height: boxRef.current.scrollHeight, top: boxRef.current.scrollTop };
      setItems((x) => (before ? [...older, ...(x || [])] : older));
      setNext(r.data.has_more ? r.data.next_before : null);
    } catch (e) { setItems((x) => x || []); } finally { setBusy(false); }
  }, [cid, busy]);

  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useLayoutEffect(() => {
    const el = boxRef.current; if (!el || !items) return;
    if (anchorRef.current) { el.scrollTop = el.scrollHeight - anchorRef.current.height + anchorRef.current.top; anchorRef.current = null; }
    else el.scrollTop = el.scrollHeight; // first page: start at the newest archive
  }, [items]);

  const restored = (a, r) => { setItems((x) => x.map((i) => (i.id === a.id ? { ...i, restored: true } : i))); onRestored && onRestored(a, r); };

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/50 p-4" data-testid="chat-archives-modal">
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center gap-2 border-b border-[#E7ECF3] px-5 py-3">
          <Archive size={16} className="text-slate-500" /><p className="font-bold text-slate-900">Arsip percakapan ini</p>
          <span className="text-xs text-slate-400" data-testid="chat-archives-count">{items ? `${items.length} arsip${next ? "+" : ""}` : "…"}</span>
          <button onClick={onClose} data-testid="archive-close" className="ml-auto rounded-lg p-1.5 text-slate-500 hover:bg-slate-100"><X size={16} /></button>
        </div>
        <div ref={boxRef} className="flex-1 space-y-3 overflow-y-auto bg-[#F8FAFC] p-4" data-testid="chat-archives-list">
          {items === null ? <Loader2 className="mx-auto animate-spin text-slate-400" /> : items.length === 0 ? <p className="py-8 text-center text-sm text-slate-500" data-testid="chat-archives-empty">Belum ada arsip untuk chat ini.</p> : (
            <>
              {busy && <p className="flex items-center justify-center gap-2 text-xs text-slate-400" data-testid="chat-archives-loading"><Loader2 size={12} className="animate-spin" /> Memuat arsip sebelumnya…</p>}
              {next && !busy && <Sentinel onVisible={() => load(next)} root={boxRef} />}
              {!next && items.length >= PAGE && <p className="text-center text-[10px] text-slate-400" data-testid="chat-archives-start">Awal riwayat arsip</p>}
              {items.map((a) => <ArchiveCard key={a.id} a={a} compact inChat onRestored={restored} />)}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
