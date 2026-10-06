import React, { useState } from "react";
import { Github, Gitlab, Link2, Unplug, Loader2, CheckCircle2, KeyRound, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

const PROV = {
  github: { Icon: Github, bg: "bg-[#0B132B]", tokenUrl: () => "https://github.com/settings/personal-access-tokens/new", placeholder: "github_pat_…",
    perms: <>Gunakan <b>fine-grained Personal Access Token</b> yang hanya mengakses repo yang Anda pilih, dengan izin <code>Contents: Read & write</code>, <code>Pull requests: Read & write</code>, <code>Issues: Read</code>, <code>Metadata: Read</code>.</>,
    examples: '"tampilkan repo github saya", "jelaskan file src/app.py di repo budi/toko", "buat PR di repo budi/toko: tambahkan validasi email di form registrasi".' },
  gitlab: { Icon: Gitlab, bg: "bg-[#FC6D26]", tokenUrl: (base) => `${base || "https://gitlab.com"}/-/user_settings/personal_access_tokens`, placeholder: "glpat-…",
    perms: <>Gunakan <b>Personal Access Token</b> dengan scope <code>api</code> (atau <code>read_api</code> + <code>write_repository</code>). Mendukung gitlab.com maupun <b>instance self-hosted</b> — isi URL instance Anda.</>,
    examples: '"tampilkan proyek gitlab saya", "jelaskan file src/app.py di proyek tim/toko", "buat merge request di proyek tim/toko: perbaiki validasi email".' },
};

// GitHub / GitLab Connect (Level 1) — the user pastes a Personal Access Token (GitLab: + instance URL for self-hosted).
export function GitHubCard({ item, onChange, provider = "github" }) {
  const P = PROV[provider];
  const [token, setToken] = useState("");
  const [baseUrl, setBaseUrl] = useState("https://gitlab.com");
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);
  if (!item) return null;
  const connect = async () => {
    if (token.trim().length < 10) { toast.error(`Tempel token ${item.name} yang valid`); return; }
    setBusy(true);
    try {
      const r = await api.post(`/integrations/${provider}`, provider === "gitlab" ? { token: token.trim(), base_url: baseUrl.trim() } : { token: token.trim() });
      toast.success(`${item.name} terhubung sebagai ${r.data.login}`); setToken(""); setShowForm(false); onChange();
    } catch (e) { toast.error(e?.response?.data?.detail || `Gagal menghubungkan ${item.name}`); }
    finally { setBusy(false); }
  };
  const disconnect = async () => {
    if (!window.confirm(`Putuskan ${item.name}? Token akan dihapus dari Oryntix.`)) return;
    await api.delete(`/integrations/${provider}`); toast.success(`${item.name} diputus`); onChange();
  };
  return (
    <div className="mt-4 aivora-card p-5" data-testid={`integration-${provider}`}>
      <div className="flex flex-wrap items-start gap-4">
        <span className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl ${P.bg} text-white`}><P.Icon size={22} /></span>
        <div className="min-w-0 flex-1">
          <p className="text-base font-bold text-slate-900">{item.name} <span className="ml-1 rounded-full bg-[#EEF3FF] px-2 py-0.5 text-[10px] font-bold text-[#2F6BFF]">Level 1</span></p>
          {item.connected
            ? <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-emerald-700" data-testid={`${provider}-status`}><CheckCircle2 size={13} /> Terhubung sebagai {item.account_picture && <img src={item.account_picture} alt="" className="h-4 w-4 rounded-full" />}<b>@{item.account_login}</b>{item.account_name ? ` (${item.account_name})` : ""}{item.base_url && <span className="text-slate-500">· {item.base_url.replace(/^https?:\/\//, "")}</span>}</p>
            : <p className="mt-0.5 text-xs text-slate-500" data-testid={`${provider}-status`}>Belum terhubung</p>}
          <ul className="mt-3 grid gap-1 text-xs text-slate-600 sm:grid-cols-2">{item.capabilities.map((c) => <li key={c} className="flex items-center gap-1.5"><Link2 size={11} className="text-[#2F6BFF]" /> {c}</li>)}</ul>
          <p className="mt-3 text-[11px] text-slate-400">{P.perms} Token disimpan terenkripsi dan bisa dicabut kapan saja.</p>
          <p className="mt-2 text-[11px] text-slate-400">Contoh perintah ke asisten: {P.examples}</p>
          {!item.connected && showForm && (
            <div className="mt-4 space-y-2" data-testid={`${provider}-token-form`}>
              {provider === "gitlab" && <input type="url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://gitlab.com atau https://gitlab.perusahaan.com" className="input-dark w-full py-2.5 text-sm" data-testid="gitlab-url-input" />}
              <div className="flex flex-col gap-2 sm:flex-row">
                <input type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder={P.placeholder} className="input-dark flex-1 py-2.5 text-sm" data-testid={`${provider}-token-input`} autoComplete="off" />
                <button onClick={connect} disabled={busy} className="btn-grad flex items-center justify-center gap-1.5 rounded-xl px-4 py-2 text-xs font-bold disabled:opacity-50" data-testid={`${provider}-token-submit`}>{busy ? <Loader2 size={14} className="animate-spin" /> : <KeyRound size={14} />} Simpan & uji token</button>
              </div>
              <a href={P.tokenUrl(baseUrl)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#2F6BFF] hover:underline" data-testid={`${provider}-token-help`}>Buat token di {item.name} <ExternalLink size={10} /></a>
            </div>
          )}
        </div>
        {item.connected ? <button onClick={disconnect} className="flex items-center gap-1.5 rounded-xl border border-rose-200 px-3 py-2 text-xs font-bold text-rose-600 hover:bg-rose-50" data-testid={`${provider}-disconnect`}><Unplug size={14} /> Putuskan</button>
          : !showForm && <button onClick={() => setShowForm(true)} className="btn-grad flex items-center gap-1.5 rounded-xl px-4 py-2 text-xs font-bold" data-testid={`${provider}-connect`}><P.Icon size={14} /> Hubungkan {item.name}</button>}
      </div>
    </div>
  );
}
