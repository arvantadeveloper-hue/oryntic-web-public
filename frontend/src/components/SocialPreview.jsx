import React, { useEffect, useState } from "react";
import { ThumbsUp, MessageCircle, Share2, Heart, Send, Bookmark, Play, AlertTriangle, CalendarClock } from "lucide-react";
import { api, API_BASE, getToken } from "../lib/api";

const fileUrl = (path) => `${API_BASE}/files/${path}?auth=${getToken()}`;

// Mock-ups of how the post will look on each platform, shown on the confirmation card before publishing/scheduling.
const PROVIDER_META = {
  linkedin: { label: "LinkedIn", color: "#0A66C2", kinds: ["text", "image", "video"] },
  meta: { label: "Facebook · Instagram", color: "#1877F2", kinds: ["image", "video"] },
  youtube: { label: "YouTube", color: "#FF0000", kinds: ["video"] },
};

let accCache = null;
const useAccounts = () => {
  const [acc, setAcc] = useState(accCache || {});
  useEffect(() => {
    if (accCache) return;
    api.get("/social/accounts").then((r) => { accCache = Object.fromEntries((r.data.items || []).map((a) => [a.id, a])); setAcc(accCache); }).catch(() => {});
  }, []);
  return acc;
};

function Media({ pt, tall = false }) {
  if (!pt.media_path) return pt.content_kind === "text" ? null : <div className={`flex ${tall ? "h-40" : "h-28"} items-center justify-center rounded-lg bg-slate-100 text-[11px] text-slate-400`}>media dari Drive</div>;
  const src = fileUrl(pt.media_path);
  if (pt.content_kind === "video") {
    return (
      <div className={`relative overflow-hidden rounded-lg bg-black ${tall ? "h-44" : "h-32"}`}>
        <video src={src} muted playsInline preload="metadata" className="h-full w-full object-cover opacity-90" />
        <span className="absolute inset-0 flex items-center justify-center"><span className="flex h-10 w-10 items-center justify-center rounded-full bg-white/90 text-slate-900"><Play size={16} className="ml-0.5" /></span></span>
      </div>
    );
  }
  return <img src={src} alt="" className={`w-full rounded-lg object-cover ${tall ? "max-h-56" : "max-h-40"}`} />;
}

function Head({ name, picture, sub, color }) {
  return (
    <div className="flex items-center gap-2">
      {picture ? <img src={picture} alt="" className="h-8 w-8 rounded-full object-cover" /> : <span className="flex h-8 w-8 items-center justify-center rounded-full text-[11px] font-bold text-white" style={{ background: color }}>{(name || "O").slice(0, 1).toUpperCase()}</span>}
      <span className="min-w-0"><span className="block truncate text-xs font-bold text-slate-900">{name || "Akun Anda"}</span><span className="block truncate text-[10px] text-slate-500">{sub}</span></span>
    </div>
  );
}

function LinkedInPost({ pt, acc, when }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 text-slate-900 shadow-sm" data-testid="social-preview-linkedin">
      <Head name={acc?.account_name} picture={acc?.account_picture} sub={when} color="#0A66C2" />
      <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed">{pt.caption}</p>
      <div className="mt-2"><Media pt={pt} /></div>
      <div className="mt-2 flex justify-around border-t border-slate-100 pt-2 text-[10px] font-semibold text-slate-500">
        <span className="flex items-center gap-1"><ThumbsUp size={11} /> Suka</span><span className="flex items-center gap-1"><MessageCircle size={11} /> Komentar</span><span className="flex items-center gap-1"><Share2 size={11} /> Bagikan</span>
      </div>
    </div>
  );
}

function MetaPost({ pt, acc, when }) {
  const page = acc?.pages?.[0];
  return (
    <div className="grid gap-2 sm:grid-cols-2" data-testid="social-preview-meta">
      <div className="rounded-xl border border-slate-200 bg-white p-3 text-slate-900 shadow-sm">
        <Head name={page?.name || acc?.account_name} picture={acc?.account_picture} sub={`${when} · Facebook`} color="#1877F2" />
        <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed">{pt.caption}</p>
        <div className="mt-2"><Media pt={pt} /></div>
        <div className="mt-2 flex justify-around border-t border-slate-100 pt-2 text-[10px] font-semibold text-slate-500">
          <span className="flex items-center gap-1"><ThumbsUp size={11} /> Suka</span><span className="flex items-center gap-1"><MessageCircle size={11} /> Komentar</span><span className="flex items-center gap-1"><Share2 size={11} /> Bagikan</span>
        </div>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-3 text-slate-900 shadow-sm">
        <Head name={page?.ig_username || page?.name || acc?.account_name} picture={acc?.account_picture} sub="Instagram" color="#E1306C" />
        <div className="mt-2"><Media pt={pt} tall /></div>
        <div className="mt-2 flex items-center gap-3 text-slate-700"><Heart size={14} /><MessageCircle size={14} /><Send size={14} /><Bookmark size={14} className="ml-auto" /></div>
        <p className="mt-1 line-clamp-3 text-xs"><b>{page?.ig_username || page?.name || acc?.account_name || "akun"}</b> {pt.caption}</p>
        {!page?.ig_id && <p className="mt-1 text-[10px] text-amber-700" data-testid="social-preview-ig-note">Instagram diposting hanya bila halaman Facebook terhubung ke akun bisnis Instagram.</p>}
      </div>
    </div>
  );
}

function YouTubePost({ pt, acc, when }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 text-slate-900 shadow-sm" data-testid="social-preview-youtube">
      <Media pt={pt} tall />
      <div className="mt-2 flex gap-2">
        {acc?.account_picture ? <img src={acc.account_picture} alt="" className="h-8 w-8 rounded-full object-cover" /> : <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#FF0000] text-[11px] font-bold text-white">{(acc?.account_name || "Y").slice(0, 1)}</span>}
        <span className="min-w-0">
          <span className="line-clamp-2 text-xs font-bold">{pt.media_name || pt.caption?.split("\n")[0] || "Video"}</span>
          <span className="block text-[10px] text-slate-500">{acc?.account_name || "Channel Anda"} · {when}</span>
          <span className="mt-1 line-clamp-2 block text-[10px] text-slate-600">{pt.caption}</span>
        </span>
      </div>
    </div>
  );
}

const VIEW = { linkedin: LinkedInPost, meta: MetaPost, youtube: YouTubePost };

export function SocialPreview({ pt, dark = false }) {
  const accounts = useAccounts();
  const when = pt.schedule_label ? pt.schedule_label.replace(/\s*\(.*\)$/, "") : "Baru saja";
  const kindLabel = { text: "teks", image: "gambar", video: "video" }[pt.content_kind] || pt.content_kind;
  return (
    <div className="mt-2 w-full space-y-3" data-testid="social-preview">
      <p className={`flex items-center gap-1 text-[11px] font-semibold ${dark ? "text-white/70" : "text-slate-600"}`}>
        {pt.schedule_at ? <CalendarClock size={12} /> : null} Pratinjau {kindLabel}{pt.schedule_label ? ` · tayang ${pt.schedule_label}` : ""}
      </p>
      {(pt.providers || []).map((p) => {
        const meta = PROVIDER_META[p] || { label: p, color: "#64748B", kinds: [] };
        const View = VIEW[p];
        const ok = meta.kinds.includes(pt.content_kind);
        return (
          <div key={p} data-testid={`social-preview-${p}-wrap`}>
            <p className="mb-1 flex items-center gap-1.5 text-[11px] font-bold" style={{ color: dark ? "#fff" : meta.color }}><span className="h-2 w-2 rounded-full" style={{ background: meta.color }} /> {meta.label}</p>
            {ok && View ? <View pt={pt} acc={accounts[p]} when={when} /> : (
              <p className="flex items-center gap-1 rounded-lg bg-rose-50 px-2 py-1.5 text-[11px] text-rose-700" data-testid={`social-preview-${p}-unsupported`}><AlertTriangle size={12} /> {meta.label} tidak menerima {kindLabel} — hanya {meta.kinds.join("/")}.</p>
            )}
          </div>
        );
      })}
    </div>
  );
}
