import React, { useEffect, useState } from "react";
import { X, HardDrive, Search, Paperclip, Loader2, FileText, Image as ImageIcon, Table2, Presentation, File, Check } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

export const driveIcon = (mime = "") => {
  if (mime.includes("spreadsheet") || mime.includes("csv")) return <Table2 size={16} />;
  if (mime.includes("presentation")) return <Presentation size={16} />;
  if (mime.startsWith("image/")) return <ImageIcon size={16} />;
  if (mime.includes("document") || mime.includes("pdf") || mime.startsWith("text/") || mime.includes("word")) return <FileText size={16} />;
  return <File size={16} />;
};

const mimeLabel = (mime = "") => mime.includes("apps.document") ? "Google Docs" : mime.includes("apps.spreadsheet") ? "Google Sheets" : mime.includes("apps.presentation") ? "Google Slides"
  : mime.includes("pdf") ? "PDF" : mime.includes("word") ? "Word" : mime.startsWith("image/") ? "Gambar" : mime.startsWith("text/") ? "Teks" : (mime.split("/")[1] || "Berkas");

const loadPickerApi = () => new Promise((resolve, reject) => {
  const ready = () => window.gapi.load("picker", { callback: resolve, onerror: reject });
  if (window.gapi?.load) return ready();
  const s = document.createElement("script"); s.src = "https://apis.google.com/js/api.js"; s.async = true; s.onload = ready; s.onerror = reject; document.head.appendChild(s);
});

// Google Picker (official UI): with the least-privilege drive.file scope only the files the user picks here become readable by Oryntix.
export async function openGooglePicker({ max = 5, docsOnly = false }) {
  const { data } = await api.get("/integrations/google/picker-token");
  await loadPickerApi();
  return new Promise((resolve) => {
    const g = window.google.picker;
    const view = new g.DocsView(g.ViewId.DOCS).setIncludeFolders(true).setSelectFolderEnabled(false).setOwnedByMe(false);
    if (docsOnly) view.setMimeTypes("application/vnd.google-apps.document,application/vnd.google-apps.spreadsheet,application/vnd.google-apps.presentation,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown,text/csv,text/html");
    const b = new g.PickerBuilder().setOAuthToken(data.access_token).setDeveloperKey(data.api_key).setAppId(data.app_id).setLocale("id").addView(view).addView(new g.DocsView(g.ViewId.DOCS).setEnableDrives(true).setIncludeFolders(true)).setTitle("Pilih file Google Drive")
      .setCallback((r) => { if (r.action === g.Action.PICKED) resolve((r.docs || []).slice(0, max).map((d) => ({ type: "drive", drive_id: d.id, name: d.name, mime: d.mimeType, link: d.url, kind: (d.mimeType || "").startsWith("image/") ? "image" : "document" }))); else if (r.action === g.Action.CANCEL) resolve([]); });
    if (max > 1) b.enableFeature(g.Feature.MULTISELECT_ENABLED);
    b.build().setVisible(true);
  });
}

// Pick files from the user's Google Drive: files Oryntix created (listed here) or any other file via the Google Picker. Read via the Drive API — nothing is uploaded to the platform.
export function DrivePicker({ onClose, onPick, max = 5, title = "Lampirkan dari Google Drive", hint, confirmLabel = "Lampirkan", docsOnly = false }) {
  const [q, setQ] = useState("");
  const [files, setFiles] = useState(null);
  const [sel, setSel] = useState([]);
  const [pickerOn, setPickerOn] = useState(false);
  const [opening, setOpening] = useState(false);
  useEffect(() => { api.get("/integrations/google/status").then((r) => setPickerOn(!!r.data.picker)).catch(() => {}); }, []);
  const fromGoogle = async () => {
    setOpening(true);
    try { const items = await openGooglePicker({ max, docsOnly }); if (items.length) { onPick(items); onClose(); } }
    catch (e) { toast.error(e?.response?.data?.detail || "Google Picker gagal dibuka"); } finally { setOpening(false); }
  };
  useEffect(() => {
    let alive = true;
    setFiles(null);
    const t = setTimeout(() => api.get("/integrations/google/files", { params: { q: q.trim(), limit: 25 } }).then((r) => alive && setFiles(r.data.files || []))
      .catch((e) => { if (alive) { setFiles([]); toast.error(e?.response?.data?.detail || "Gagal memuat Drive"); } }), q ? 350 : 0);
    return () => { alive = false; clearTimeout(t); };
  }, [q]);
  const list = (files || []).filter((f) => !docsOnly || !(f.mimeType || "").startsWith("image/"));
  const toggle = (f) => setSel((s) => (s.some((x) => x.id === f.id) ? s.filter((x) => x.id !== f.id) : max === 1 ? [f] : s.length >= max ? s : [...s, f]));
  const confirm = () => { onPick(sel.map((f) => ({ type: "drive", drive_id: f.id, name: f.name, mime: f.mimeType, link: f.webViewLink, kind: (f.mimeType || "").startsWith("image/") ? "image" : "document" }))); onClose(); };
  return (
    <div className="fixed inset-0 z-[93] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} />
      <div className="relative flex max-h-[85vh] w-full max-w-2xl flex-col rounded-3xl border border-[#E7ECF3] bg-white shadow-2xl fade-up" data-testid="drive-picker">
        <div className="flex items-start justify-between gap-3 border-b border-[#E7ECF3] p-5">
          <div>
            <h3 className="flex items-center gap-2 text-lg font-bold text-slate-900"><HardDrive size={18} className="text-[#2F6BFF]" /> {title}</h3>
            <p className="mt-0.5 text-xs text-slate-500">{hint || `Pilih hingga ${max} berkas. Isinya dibaca langsung dari Drive Anda — tidak memakai penyimpanan platform.`}</p>
          </div>
          <button onClick={onClose} className="text-slate-400" data-testid="drive-picker-close"><X size={18} /></button>
        </div>
        <div className="px-5 pt-4">
          {pickerOn && <button onClick={fromGoogle} disabled={opening} className="mb-3 flex w-full items-center justify-center gap-2 rounded-xl border border-[#2F6BFF] bg-[#EEF3FF] px-3 py-2.5 text-sm font-bold text-[#2F6BFF] hover:bg-[#E0E9FF] disabled:opacity-50" data-testid="drive-picker-google">{opening ? <Loader2 size={15} className="animate-spin" /> : <HardDrive size={15} />} Pilih file lain dari Google Drive (Google Picker)</button>}
          <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-400">File buatan Oryntix di Drive Anda</p>
          <div className="flex items-center gap-2 rounded-xl border border-[#E7ECF3] px-3 py-2"><Search size={14} className="text-slate-400" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari nama file di Drive…" className="w-full bg-transparent text-sm outline-none" data-testid="drive-picker-search" /></div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          {files === null ? <p className="flex items-center gap-2 text-sm text-slate-400"><Loader2 size={14} className="animate-spin" /> Memuat file Drive…</p>
            : list.length === 0 ? <p className="text-sm text-slate-400" data-testid="drive-picker-empty">{q ? "Tidak ada file yang cocok." : pickerOn ? "Belum ada file buatan Oryntix. Gunakan tombol Google Picker di atas untuk memilih file lain." : "Belum ada file buatan Oryntix di Drive Anda. Minta asisten menyimpan dokumen ke Drive dulu."}</p>
              : <ul className="space-y-1.5" data-testid="drive-picker-list">{list.map((f) => { const on = sel.some((x) => x.id === f.id); return (
                <li key={f.id}><button onClick={() => toggle(f)} className={`flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors ${on ? "border-[#2F6BFF] bg-[#EEF3FF]" : "border-[#E7ECF3] hover:bg-slate-50"}`} data-testid={`drive-file-${f.id}`}>
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white text-[#2F6BFF] shadow-sm">{driveIcon(f.mimeType)}</span>
                  <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold text-slate-900">{f.name}</span><span className="block text-[11px] text-slate-400">{mimeLabel(f.mimeType)} · {f.modifiedTime ? new Date(f.modifiedTime).toLocaleDateString("id-ID") : ""}</span></span>
                  {on && <Check size={16} className="text-[#2F6BFF]" />}
                </button></li>); })}</ul>}
        </div>
        <div className="flex items-center justify-between border-t border-[#E7ECF3] p-4">
          <span className="text-xs font-semibold text-slate-500" data-testid="drive-picker-count">{sel.length ? `${sel.length} dipilih` : "Belum ada yang dipilih"}</span>
          <button onClick={confirm} disabled={!sel.length} className="btn-grad flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm disabled:opacity-50" data-testid="drive-picker-attach"><Paperclip size={15} /> {confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}
