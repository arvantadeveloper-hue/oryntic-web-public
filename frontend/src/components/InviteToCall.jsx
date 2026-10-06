import React, { useEffect, useState } from "react";
import { UserPlus, X, Loader2, Check, Bot, Users } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

// Round control-bar button that opens the invite dialog (host only).
export function InviteButton({ onClick, disabled }) {
  return (
    <button onClick={onClick} disabled={disabled} data-testid="call-invite-btn" title="Undang teman atau asisten lain ke panggilan ini" className="flex h-14 w-14 items-center justify-center rounded-full bg-white/15 text-white transition hover:bg-white/25 disabled:opacity-50"><UserPlus size={22} /></button>
  );
}

function Row({ item, on, onClick, testid, fallbackIcon }) {
  const img = item.portrait || item.avatar;
  return (
    <button onClick={onClick} data-testid={testid} className={`flex w-full items-center gap-3 rounded-xl border p-2.5 text-left transition ${on ? "border-emerald-400/70 bg-emerald-400/10" : "border-white/10 hover:bg-white/5"}`}>
      {img ? <img src={img} alt="" className="h-9 w-9 shrink-0 rounded-full object-cover" /> : <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#2F6BFF]/40 text-white">{fallbackIcon}</span>}
      <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold text-white">{item.name}</span>{item.email && <span className="block truncate text-[11px] text-white/50">{item.email}</span>}</span>
      <span className={`flex h-6 w-6 items-center justify-center rounded-full border ${on ? "border-emerald-400 bg-emerald-400 text-slate-900" : "border-white/20 text-transparent"}`}><Check size={14} /></span>
    </button>
  );
}

// Pick friends + assistants who are not yet in the conversation → POST /conversations/{cid}/members.
export function InviteDialog({ conv, onClose, onInvited }) {
  const [friends, setFriends] = useState([]);
  const [personas, setPersonas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [pf, setPf] = useState([]);
  const [pp, setPp] = useState([]);
  useEffect(() => {
    Promise.all([api.get("/friends"), api.get("/personas")])
      .then(([f, p]) => { setFriends(f.data.friends || []); setPersonas(p.data || []); })
      .catch(() => toast.error("Gagal memuat daftar teman/asisten")).finally(() => setLoading(false));
  }, []);
  const inP = new Set((conv.persona_ids || []).concat((conv.members || []).map((m) => m.id)));
  const inH = new Set(conv.participants || []);
  const fOpts = friends.filter((f) => !inH.has(f.id));
  const pOpts = personas.filter((p) => !inP.has(p.id));
  const toggle = (set) => (id) => set((a) => (a.includes(id) ? a.filter((x) => x !== id) : [...a, id]));
  const submit = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/conversations/${conv.id}/members`, { friend_ids: pf, persona_ids: pp });
      toast.success(pf.length ? "Undangan terkirim — teman akan berdering" : "Asisten ditambahkan ke panggilan");
      onInvited(r.data); onClose();
    } catch (e) { toast.error(e?.response?.data?.detail || "Gagal mengundang"); } finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-[110] flex items-end justify-center bg-black/60 p-4 backdrop-blur-sm sm:items-center" data-testid="invite-dialog" onClick={onClose}>
      <div className="w-full max-w-md rounded-3xl border border-white/10 bg-[#0f172a] p-5 text-white shadow-2xl fade-up" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2">
          <UserPlus size={18} className="text-[#8FB0FF]" />
          <h3 className="flex-1 text-base font-bold">Undang ke panggilan</h3>
          <button onClick={onClose} data-testid="invite-close" className="flex h-8 w-8 items-center justify-center rounded-full bg-white/10 hover:bg-white/20"><X size={16} /></button>
        </div>
        <p className="mt-1 text-xs text-white/55">Teman yang diundang akan berdering dan bisa langsung bergabung. Ruang panggilan tersambung ulang sebentar setelah mengundang.</p>
        <div className="mt-4 max-h-[50vh] space-y-4 overflow-y-auto pr-1">
          {loading && <p className="flex items-center gap-2 text-sm text-white/60"><Loader2 size={14} className="animate-spin" /> Memuat...</p>}
          {!loading && (
            <>
              <section>
                <p className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-white/45"><Users size={12} /> Teman</p>
                {fOpts.length === 0 && <p className="text-xs text-white/45" data-testid="invite-no-friends">{friends.length === 0 ? "Belum ada teman. Tambahkan lewat halaman Teman." : "Semua teman sudah ada di percakapan ini."}</p>}
                <div className="space-y-2">{fOpts.map((f) => <Row key={f.id} item={f} on={pf.includes(f.id)} onClick={() => toggle(setPf)(f.id)} testid={`invite-friend-${f.id}`} fallbackIcon={<Users size={16} />} />)}</div>
              </section>
              <section>
                <p className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-white/45"><Bot size={12} /> Asisten</p>
                {pOpts.length === 0 && <p className="text-xs text-white/45" data-testid="invite-no-personas">Semua asisten sudah ada di percakapan ini.</p>}
                <div className="space-y-2">{pOpts.map((p) => <Row key={p.id} item={p} on={pp.includes(p.id)} onClick={() => toggle(setPp)(p.id)} testid={`invite-persona-${p.id}`} fallbackIcon={<Bot size={16} />} />)}</div>
              </section>
            </>
          )}
        </div>
        <button onClick={submit} disabled={busy || (pf.length === 0 && pp.length === 0)} data-testid="invite-submit" className="btn-grad mt-4 flex h-11 w-full items-center justify-center gap-2 rounded-xl text-sm font-bold disabled:opacity-50">
          {busy ? <Loader2 size={16} className="animate-spin" /> : <UserPlus size={16} />} Undang {pf.length + pp.length > 0 ? `(${pf.length + pp.length})` : ""}
        </button>
      </div>
    </div>
  );
}
