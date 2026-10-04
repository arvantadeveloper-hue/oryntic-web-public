import React, { useEffect, useRef, useState } from "react";
import { BookOpen, Upload, Bold, Italic, List, Heading2, Trash2, Loader2, FileText, PenLine, Eye } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

// Reference knowledge for an assistant: uploaded documents or text written in a small WYSIWYG editor.
// Not "priority" memory — only the chunks relevant to a message are shown to the assistant.
export function KnowledgeTab({ personaId }) {
  const [docs, setDocs] = useState(null);
  const [mode, setMode] = useState("upload"); // upload | editor
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);
  const edRef = useRef(null);
  const fileRef = useRef(null);
  const load = () => api.get(`/personas/${personaId}/knowledge`).then((r) => setDocs(r.data)).catch(() => setDocs([]));
  useEffect(() => { load(); }, [personaId]); // eslint-disable-line

  const upload = async (file) => {
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) { toast.error("Maksimal 8 MB"); return; }
    setBusy(true);
    try {
      const data = await new Promise((res, rej) => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.onerror = rej; fr.readAsDataURL(file); });
      const r = await api.post(`/personas/${personaId}/knowledge`, { title: title.trim() || file.name, file_name: file.name, file_data: data });
      toast.success(`"${r.data.title}" ditambahkan (${r.data.chunk_count} bagian)`); setTitle(""); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengunggah"); } finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  };
  const saveEditor = async () => {
    const html = edRef.current?.innerHTML || "";
    if (!title.trim()) { toast.error("Isi judul dokumen"); return; }
    setBusy(true);
    try { const r = await api.post(`/personas/${personaId}/knowledge`, { title: title.trim(), html }); toast.success(`"${r.data.title}" disimpan (${r.data.chunk_count} bagian)`); setTitle(""); if (edRef.current) edRef.current.innerHTML = ""; load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menyimpan"); } finally { setBusy(false); }
  };
  const cmd = (c, v) => { edRef.current?.focus(); document.execCommand(c, false, v); };
  const toggle = async (d) => { await api.put(`/personas/${personaId}/knowledge/${d.id}`, { enabled: !d.enabled }); load(); };
  const remove = async (d) => { if (!window.confirm(`Hapus "${d.title}"?`)) return; await api.delete(`/personas/${personaId}/knowledge/${d.id}`); load(); };
  const openPreview = async (d) => { try { setPreview((await api.get(`/personas/${personaId}/knowledge/${d.id}`)).data); } catch (e) {} };
  const tb = "flex h-8 w-8 items-center justify-center rounded-lg border border-[#E7ECF3] text-slate-600 hover:bg-slate-50";

  return (
    <div data-testid="knowledge-tab">
      <p className="text-xs text-slate-500">Dokumen referensi asisten. Berbeda dengan memori prioritas: isi dokumen <b>hanya</b> dikirim ke asisten saat relevan dengan pesan Anda (maks 3 bagian), jadi hemat token.</p>
      <div className="mt-4 flex gap-2">
        <button onClick={() => setMode("upload")} data-testid="kn-mode-upload" className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-semibold ${mode === "upload" ? "btn-grad" : "border border-[#E7ECF3] text-slate-600"}`}><Upload size={13} /> Unggah dokumen</button>
        <button onClick={() => setMode("editor")} data-testid="kn-mode-editor" className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-semibold ${mode === "editor" ? "btn-grad" : "border border-[#E7ECF3] text-slate-600"}`}><PenLine size={13} /> Tulis sendiri</button>
      </div>
      <input className="input-dark mt-3 py-2.5" placeholder={mode === "upload" ? "Judul (opsional, default nama berkas)" : "Judul dokumen"} value={title} onChange={(e) => setTitle(e.target.value)} data-testid="kn-title" />
      {mode === "upload" ? (
        <label className="mt-3 flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-[#E7ECF3] p-6 text-center hover:bg-slate-50" data-testid="kn-dropzone">
          {busy ? <Loader2 size={22} className="animate-spin text-[#2F6BFF]" /> : <Upload size={22} className="text-[#2F6BFF]" />}
          <span className="mt-2 text-sm font-semibold text-slate-700">Pilih berkas PDF, Word, TXT, atau Markdown</span>
          <span className="text-xs text-slate-400">Maks 8 MB · ±200 ribu karakter</span>
          <input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.md,.markdown,.csv,.json,.html" className="hidden" onChange={(e) => upload(e.target.files?.[0])} data-testid="kn-file-input" />
        </label>
      ) : (
        <div className="mt-3">
          <div className="flex gap-1.5">
            <button onClick={() => cmd("bold")} className={tb} title="Tebal" data-testid="kn-ed-bold"><Bold size={14} /></button>
            <button onClick={() => cmd("italic")} className={tb} title="Miring" data-testid="kn-ed-italic"><Italic size={14} /></button>
            <button onClick={() => cmd("formatBlock", "h2")} className={tb} title="Judul" data-testid="kn-ed-h2"><Heading2 size={14} /></button>
            <button onClick={() => cmd("insertUnorderedList")} className={tb} title="Daftar" data-testid="kn-ed-list"><List size={14} /></button>
          </div>
          <div ref={edRef} contentEditable suppressContentEditableWarning className="md-body mt-2 min-h-[180px] rounded-2xl border border-[#E7ECF3] bg-white p-4 text-sm text-slate-800 outline-none focus:border-[#2F6BFF]" data-testid="kn-editor" data-placeholder="Tulis pengetahuan untuk asisten…" />
          <button onClick={saveEditor} disabled={busy} className="btn-grad mt-3 rounded-xl px-5 py-2.5 text-sm disabled:opacity-50" data-testid="kn-save-editor">{busy ? "..." : "Simpan sebagai pengetahuan"}</button>
        </div>
      )}

      <div className="mt-6 space-y-2">
        <p className="text-[11px] font-bold uppercase tracking-wider text-slate-400">Dokumen ({docs?.length ?? 0})</p>
        {docs === null && <p className="flex items-center gap-2 text-xs text-slate-400"><Loader2 size={13} className="animate-spin" /> Memuat…</p>}
        {docs?.length === 0 && <p className="text-sm text-slate-400" data-testid="kn-empty">Belum ada dokumen pengetahuan.</p>}
        {(docs || []).map((d) => (
          <div key={d.id} className={`flex items-center gap-3 rounded-2xl border border-[#E7ECF3] bg-white p-3 ${d.enabled ? "" : "opacity-60"}`} data-testid={`kn-doc-${d.id}`}>
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#EEF3FF] text-[#2F6BFF]">{d.source === "upload" ? <FileText size={16} /> : <BookOpen size={16} />}</span>
            <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold text-slate-900">{d.title}</span><span className="block text-[11px] text-slate-400">{d.source === "upload" ? d.file_name : "editor"} · {d.chars.toLocaleString("id-ID")} karakter · {d.chunk_count} bagian</span></span>
            <button onClick={() => openPreview(d)} className="text-slate-400 hover:text-[#2F6BFF]" title="Lihat" data-testid="kn-view"><Eye size={15} /></button>
            <button onClick={() => toggle(d)} className="text-xs font-semibold text-[#2F6BFF]" data-testid="kn-toggle">{d.enabled ? "Nonaktif" : "Aktif"}</button>
            <button onClick={() => remove(d)} className="text-slate-300 hover:text-[#EF4444]" data-testid="kn-delete"><Trash2 size={15} /></button>
          </div>
        ))}
      </div>
      {preview && (
        <div className="fixed inset-0 z-[95] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-slate-900/40" onClick={() => setPreview(null)} />
          <div className="relative max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-3xl border border-[#E7ECF3] bg-white p-6 shadow-2xl" data-testid="kn-preview">
            <h3 className="text-lg font-bold text-slate-900">{preview.title}</h3>
            <pre className="mt-3 whitespace-pre-wrap text-xs text-slate-700">{preview.text}</pre>
            <button onClick={() => setPreview(null)} className="btn-grad mt-4 rounded-xl px-4 py-2 text-sm">Tutup</button>
          </div>
        </div>
      )}
    </div>
  );
}
