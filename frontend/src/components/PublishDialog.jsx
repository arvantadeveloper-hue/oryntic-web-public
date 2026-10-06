import React, { useEffect, useState } from "react";
import { X, Share2, Loader2, Sparkles, CheckCircle2, XCircle, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { fileUrl } from "./MessageExtras";

// Listens for `oryntix:publish` (fired by the "Publikasikan" button on any media) and walks the user through account → caption → send.
export function PublishHost() {
  const [job, setJob] = useState(null);
  useEffect(() => { const h = (e) => setJob(e.detail); window.addEventListener("oryntix:publish", h); return () => window.removeEventListener("oryntix:publish", h); }, []);
  if (!job) return null;
  return <PublishDialog media={job.media} context={job.context} onClose={() => setJob(null)} />;
}

export function PublishDialog({ media, context = "", onClose }) {
  const kind = media ? (media.type === "video" ? "video" : "image") : "text";
  const [accounts, setAccounts] = useState(null);
  const [picked, setPicked] = useState([]);
  const [caption, setCaption] = useState("");
  const [busy, setBusy] = useState("");
  const [results, setResults] = useState(null);
  useEffect(() => {
    api.get("/social/accounts").then((r) => {
      const ok = r.data.items.filter((a) => a.connected && a.kinds.includes(kind));
      setAccounts(r.data.items); setPicked(ok.slice(0, 1).map((a) => a.id));
    }).catch(() => setAccounts([]));
  }, [kind]);
  const genCaption = async () => {
    setBusy("caption");
    try { const r = await api.post("/social/caption", { context: context || "", providers: picked, kind, media_path: media?.path || null }); setCaption(r.data.caption); }
    catch (e) { toast.error("Gagal membuat caption"); } finally { setBusy(""); }
  };
  const send = async () => {
    if (!picked.length) { toast.error("Pilih minimal satu akun"); return; }
    setBusy("send");
    try {
      const r = await api.post("/social/publish", { providers: picked, kind, text: caption, title: media?.name || "", media_path: media?.path || null, app_url: window.location.origin });
      setResults(r.data.results);
      if (r.data.results.every((x) => x.status === "sent")) toast.success("Terkirim ke media sosial");
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal memposting"); } finally { setBusy(""); }
  };
  const eligible = (accounts || []).filter((a) => a.kinds.includes(kind));
  return (
    <div className="fixed inset-0 z-[96] flex items-center justify-center p-4" data-testid="publish-dialog">
      <div className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg overflow-hidden rounded-3xl border border-[#E7ECF3] bg-white shadow-2xl fade-up">
        <div className="flex items-center justify-between border-b border-[#E7ECF3] px-5 py-4">
          <p className="flex items-center gap-2 text-sm font-bold text-slate-900"><Share2 size={16} className="text-[#2F6BFF]" /> Publikasikan ke media sosial</p>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700" data-testid="publish-close"><X size={18} /></button>
        </div>
        <div className="space-y-4 p-5">
          {media && (media.type === "video" ? <video src={fileUrl(media.path)} className="max-h-40 w-full rounded-xl bg-black" controls /> : <img src={fileUrl(media.path)} alt="" className="max-h-40 w-full rounded-xl object-cover" />)}
          <div>
            <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400">Akun tujuan</p>
            {accounts === null ? <Loader2 size={14} className="animate-spin text-slate-400" /> : eligible.length === 0 ? <p className="text-xs text-slate-500">Belum ada akun yang mendukung {kind}. <a href="/social" className="font-semibold text-[#2F6BFF]">Hubungkan di menu Social Media →</a></p> : (
              <div className="flex flex-wrap gap-2">{eligible.map((a) => (
                <button key={a.id} type="button" disabled={!a.connected} onClick={() => setPicked((p) => p.includes(a.id) ? p.filter((x) => x !== a.id) : [...p, a.id])} data-testid={`publish-acc-${a.id}`}
                  className={`rounded-full border px-3 py-1.5 text-xs font-semibold transition disabled:opacity-40 ${picked.includes(a.id) ? "border-[#2F6BFF] bg-[#EEF3FF] text-[#2F6BFF]" : "border-[#E7ECF3] text-slate-600"}`}>{a.label}{a.account_name ? ` · ${a.account_name}` : a.connected ? "" : " (belum terhubung)"}</button>
              ))}</div>
            )}
          </div>
          <div>
            <div className="mb-1.5 flex items-center justify-between"><p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Caption</p><button onClick={genCaption} disabled={!!busy} className="flex items-center gap-1 text-xs font-semibold text-[#2F6BFF]" data-testid="publish-gen-caption">{busy === "caption" ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />} Tulis otomatis oleh asisten</button></div>
            <textarea value={caption} onChange={(e) => setCaption(e.target.value)} rows={4} placeholder="Tulis caption, atau minta asisten menulisnya…" className="input-dark w-full resize-none py-2.5 text-sm" data-testid="publish-caption" />
          </div>
          {results && (
            <div className="space-y-1.5 rounded-xl border border-[#E7ECF3] p-3 text-xs" data-testid="publish-results">
              {results.map((r) => <p key={r.id} className="flex items-center gap-2">{r.status === "sent" ? <CheckCircle2 size={13} className="text-emerald-600" /> : <XCircle size={13} className="text-rose-600" />}<b>{r.provider}</b>{r.status === "sent" ? <a href={r.post_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-[#2F6BFF]">lihat post <ExternalLink size={10} /></a> : <span className="text-rose-600">{r.error}</span>}</p>)}
            </div>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-[#E7ECF3] px-5 py-3">
          <button onClick={onClose} className="rounded-xl px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100" data-testid="publish-cancel">{results ? "Tutup" : "Batal"}</button>
          {!results && <button onClick={send} disabled={!!busy || !picked.length} className="btn-grad flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-bold disabled:opacity-50" data-testid="publish-send">{busy === "send" ? <Loader2 size={13} className="animate-spin" /> : <Share2 size={13} />} Publikasikan</button>}
        </div>
      </div>
    </div>
  );
}
