import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Download, FileText, Loader2, Link2Off, Clock } from "lucide-react";
import { API_BASE } from "../lib/api";
import { Logo } from "../components/Logo";
import { Markdown } from "../components/Markdown";

export default function SharePage() {
  const { code } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    fetch(`${API_BASE}/public/share/${code}`).then(async (r) => { if (!r.ok) throw new Error((await r.json()).detail || "Tautan tidak valid"); setData(await r.json()); }).catch((e) => setError(e.message));
  }, [code]);
  const file = `${API_BASE}/public/share/${code}/file`;
  const btn = "flex items-center gap-1.5 rounded-xl px-4 py-2.5 text-sm font-bold";
  return (
    <div className="min-h-screen bg-[#F8FAFC]" data-testid="share-page">
      <header className="flex items-center justify-between border-b border-[#E7ECF3] bg-white px-6 py-4"><Logo size={32} /><a href="/" className="text-xs font-semibold text-[#2F6BFF]">Coba Oryntix</a></header>
      <main className="mx-auto max-w-3xl p-5 sm:p-8">
        {error && <div className="aivora-card p-10 text-center fade-up" data-testid="share-error"><Link2Off size={36} className="mx-auto text-[#EF4444]" /><h1 className="mt-4 text-xl font-bold text-slate-900">Tautan tidak tersedia</h1><p className="mt-1 text-sm text-slate-500">{error}</p></div>}
        {!data && !error && <p className="flex items-center justify-center gap-2 py-20 text-sm text-slate-400"><Loader2 size={16} className="animate-spin" /> Memuat…</p>}
        {data && (
          <div className="fade-up">
            <p className="text-xs text-slate-400">Dibagikan oleh <b className="text-slate-600">{data.shared_by}</b> · <Clock size={11} className="inline" /> berlaku sampai {new Date(data.expires_at).toLocaleString("id-ID", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</p>
            <h1 className="mt-1 text-2xl font-bold text-slate-900 sm:text-3xl" data-testid="share-title">{data.title || data.name}</h1>
            <div className="mt-4 flex flex-wrap gap-2">
              {data.kind === "document" ? (<>
                <a href={`${API_BASE}/public/share/${code}/export/docx`} className={`${btn} bg-[#0B132B] text-white`} data-testid="share-dl-docx"><Download size={15} /> Word</a>
                <a href={`${API_BASE}/public/share/${code}/export/pdf`} className={`${btn} bg-slate-200 text-slate-800`} data-testid="share-dl-pdf"><Download size={15} /> PDF</a>
                {data.has_tables && <a href={`${API_BASE}/public/share/${code}/export/xlsx`} className={`${btn} bg-slate-200 text-slate-800`}><Download size={15} /> Excel</a>}
              </>) : <a href={`${file}?download=1`} className={`${btn} bg-[#0B132B] text-white`} data-testid="share-dl-file"><Download size={15} /> Unduh {data.name}</a>}
            </div>
            <div className="mt-6 aivora-card overflow-hidden p-5" data-testid="share-body">
              {data.kind === "document" && <Markdown content={data.content || "_Dokumen kosong._"} />}
              {data.kind === "image" && <img src={file} alt={data.name} className="mx-auto max-h-[70vh] rounded-xl" />}
              {data.kind === "video" && <video src={file} controls className="w-full rounded-xl" />}
              {data.kind === "file" && <p className="flex items-center gap-2 text-sm text-slate-600"><FileText size={16} /> {data.name}</p>}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
