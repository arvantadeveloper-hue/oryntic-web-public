import React, { useState } from "react";
import { Github, Link2, Unplug, Loader2, CheckCircle2, KeyRound, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

// GitHub Connect (Level 1) — the user pastes a fine-grained Personal Access Token.
export function GitHubCard({ item, onChange }) {
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);
  if (!item) return null;
  const connect = async () => {
    if (token.trim().length < 20) { toast.error("Tempel token GitHub yang valid"); return; }
    setBusy(true);
    try { const r = await api.post("/integrations/github", { token: token.trim() }); toast.success(`GitHub terhubung sebagai ${r.data.login}`); setToken(""); setShowForm(false); onChange(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Gagal menghubungkan GitHub"); }
    finally { setBusy(false); }
  };
  const disconnect = async () => {
    if (!window.confirm("Putuskan GitHub? Token akan dihapus dari Oryntix.")) return;
    await api.delete("/integrations/github"); toast.success("GitHub diputus"); onChange();
  };
  return (
    <div className="mt-4 aivora-card p-5" data-testid="integration-github">
      <div className="flex flex-wrap items-start gap-4">
        <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#0B132B] text-white"><Github size={22} /></span>
        <div className="min-w-0 flex-1">
          <p className="text-base font-bold text-slate-900">{item.name} <span className="ml-1 rounded-full bg-[#EEF3FF] px-2 py-0.5 text-[10px] font-bold text-[#2F6BFF]">Level 1</span></p>
          {item.connected
            ? <p className="mt-0.5 flex items-center gap-1.5 text-xs text-emerald-700" data-testid="github-status"><CheckCircle2 size={13} /> Terhubung sebagai {item.account_picture && <img src={item.account_picture} alt="" className="h-4 w-4 rounded-full" />}<b>@{item.account_login}</b>{item.account_name ? ` (${item.account_name})` : ""}</p>
            : <p className="mt-0.5 text-xs text-slate-500" data-testid="github-status">Belum terhubung</p>}
          <ul className="mt-3 grid gap-1 text-xs text-slate-600 sm:grid-cols-2">{item.capabilities.map((c) => <li key={c} className="flex items-center gap-1.5"><Link2 size={11} className="text-[#2F6BFF]" /> {c}</li>)}</ul>
          <p className="mt-3 text-[11px] text-slate-400">Gunakan <b>fine-grained Personal Access Token</b> yang hanya mengakses repo yang Anda pilih, dengan izin <code>Contents: Read & write</code>, <code>Pull requests: Read & write</code>, <code>Issues: Read</code>, <code>Metadata: Read</code>. Token disimpan terenkripsi dan bisa dicabut kapan saja dari GitHub.</p>
          <p className="mt-2 text-[11px] text-slate-400">Contoh perintah ke asisten: "tampilkan repo github saya", "jelaskan file src/app.py di repo budi/toko", "buat PR di repo budi/toko: tambahkan validasi email di form registrasi".</p>
          {!item.connected && showForm && (
            <div className="mt-4 flex flex-col gap-2 sm:flex-row" data-testid="github-token-form">
              <input type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="github_pat_…" className="input-dark flex-1 py-2.5 text-sm" data-testid="github-token-input" autoComplete="off" />
              <button onClick={connect} disabled={busy} className="btn-grad flex items-center justify-center gap-1.5 rounded-xl px-4 py-2 text-xs font-bold disabled:opacity-50" data-testid="github-token-submit">{busy ? <Loader2 size={14} className="animate-spin" /> : <KeyRound size={14} />} Simpan & uji token</button>
            </div>
          )}
          {!item.connected && showForm && <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-[#2F6BFF] hover:underline" data-testid="github-token-help">Buat token di GitHub <ExternalLink size={10} /></a>}
        </div>
        {item.connected ? <button onClick={disconnect} className="flex items-center gap-1.5 rounded-xl border border-rose-200 px-3 py-2 text-xs font-bold text-rose-600 hover:bg-rose-50" data-testid="github-disconnect"><Unplug size={14} /> Putuskan</button>
          : !showForm && <button onClick={() => setShowForm(true)} className="btn-grad flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-bold" data-testid="github-connect"><Github size={14} /> Hubungkan GitHub</button>}
      </div>
    </div>
  );
}
