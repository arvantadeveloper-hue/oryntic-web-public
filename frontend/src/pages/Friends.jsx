import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { UserPlus, Users, MessageSquare, Phone, Check, X, Mail, Loader2, Search, UserMinus, Clock } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

const Avatar = ({ name }) => <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#0B132B] text-sm font-bold text-white">{(name || "?")[0].toUpperCase()}</span>;

export default function Friends() {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [email, setEmail] = useState("");
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState("");
  const load = () => api.get("/friends").then((r) => setData(r.data)).catch(() => setData({ friends: [], incoming: [], outgoing: [], email_invites: [] }));
  useEffect(() => { load(); }, []);

  const invite = async (e) => {
    e.preventDefault();
    setBusy("invite");
    try {
      const r = await api.post("/friends/invite", { email: email.trim(), app_url: window.location.origin });
      toast.success(r.data.status === "emailed" ? `Email ajakan dikirim ke ${email}. Permintaan pertemanan otomatis muncul setelah ia mendaftar.` : r.data.status === "accepted" ? "Kalian sekarang berteman" : "Permintaan pertemanan dikirim — menunggu persetujuan");
      setEmail(""); load();
    } catch (err) { toast.error(err?.response?.data?.detail || "Gagal mengirim undangan"); } finally { setBusy(""); }
  };
  const act = async (path, msg) => { try { await api.post(path); toast.success(msg); load(); } catch (e) { toast.error("Gagal"); } };
  const unfriend = async (f) => { if (!window.confirm(`Hapus ${f.name} dari daftar teman?`)) return; await api.delete(`/friends/${f.id}`); load(); };
  const openChat = async (f, call) => {
    setBusy(f.id);
    try { const r = await api.post(`/friends/${f.id}/chat`); if (call) toast.message("Panggilan suara antar-teman hadir di pembaruan berikutnya — chat dibuka dulu."); nav(`/chat/${r.data.id}`); }
    catch (e) { toast.error("Gagal membuka chat"); } finally { setBusy(""); }
  };
  const ql = q.trim().toLowerCase();
  const friends = (data?.friends || []).filter((f) => !ql || f.name.toLowerCase().includes(ql) || (f.email || "").toLowerCase().includes(ql));

  return (
    <div className="mx-auto max-w-4xl p-5 sm:p-8 fade-up" data-testid="friends-page">
      <h1 className="flex items-center gap-2 text-2xl font-bold text-slate-900 sm:text-3xl"><Users size={26} className="text-[#2F6BFF]" /> Teman</h1>
      <p className="mt-1 text-sm text-slate-500">Undang teman lewat email. Setelah disetujui, kalian bisa chat langsung atau membuat grup bersama asisten AI.</p>

      <form onSubmit={invite} className="mt-5 flex flex-col gap-2 sm:flex-row" data-testid="friend-invite-form">
        <div className="relative flex-1"><Mail size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input type="email" required className="input-dark pl-10" placeholder="Email teman" value={email} onChange={(e) => setEmail(e.target.value)} data-testid="friend-invite-email" /></div>
        <button disabled={busy === "invite"} className="btn-grad flex items-center justify-center gap-2 rounded-xl px-5 py-3 text-sm" data-testid="friend-invite-submit">{busy === "invite" ? <Loader2 size={15} className="animate-spin" /> : <UserPlus size={15} />} Undang</button>
      </form>

      {!data && <p className="flex items-center gap-2 py-10 text-sm text-slate-400"><Loader2 size={15} className="animate-spin" /> Memuat…</p>}

      {data?.incoming?.length > 0 && (
        <section className="mt-6" data-testid="friend-incoming">
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">Permintaan masuk ({data.incoming.length})</h2>
          <div className="mt-2 space-y-2">{data.incoming.map((r) => (
            <div key={r.request_id} className="aivora-card flex items-center gap-3 p-3" data-testid={`friend-request-${r.request_id}`}>
              <Avatar name={r.name} /><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-slate-900">{r.name}</p><p className="truncate text-xs text-slate-400">{r.email}</p></div>
              <button onClick={() => act(`/friends/${r.request_id}/accept`, `${r.name} sekarang teman Anda`)} className="flex items-center gap-1 rounded-lg bg-[#10B981] px-3 py-1.5 text-xs font-bold text-white" data-testid="friend-accept"><Check size={13} /> Terima</button>
              <button onClick={() => act(`/friends/${r.request_id}/reject`, "Permintaan ditolak")} className="flex items-center gap-1 rounded-lg border border-[#E7ECF3] px-3 py-1.5 text-xs font-semibold text-slate-600" data-testid="friend-reject"><X size={13} /> Tolak</button>
            </div>
          ))}</div>
        </section>
      )}

      {data && (
        <section className="mt-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">Teman ({data.friends.length})</h2>
            <div className="relative w-full sm:w-64"><Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><input className="input-dark py-2 pl-9" placeholder="Cari teman" value={q} onChange={(e) => setQ(e.target.value)} data-testid="friend-search" /></div>
          </div>
          {friends.length === 0 ? <p className="mt-3 text-sm text-slate-400" data-testid="friends-empty">{ql ? "Tidak ada teman yang cocok." : "Belum ada teman. Undang lewat email di atas."}</p> : (
            <div className="mt-2 grid gap-2 sm:grid-cols-2">{friends.map((f) => (
              <div key={f.id} className="aivora-card flex items-center gap-3 p-3" data-testid={`friend-card-${f.id}`}>
                <Avatar name={f.name} /><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-slate-900">{f.name}</p><p className="truncate text-xs text-slate-400">{f.email}</p></div>
                <button onClick={() => openChat(f, false)} disabled={busy === f.id} title="Chat" className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#EEF3FF] text-[#2F6BFF]" data-testid="friend-chat"><MessageSquare size={16} /></button>
                <button onClick={() => openChat(f, true)} disabled={busy === f.id} title="Panggilan" className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-50 text-[#10B981]" data-testid="friend-call"><Phone size={16} /></button>
                <button onClick={() => unfriend(f)} title="Hapus teman" className="text-slate-300 hover:text-[#EF4444]" data-testid="friend-remove"><UserMinus size={15} /></button>
              </div>
            ))}</div>
          )}
        </section>
      )}

      {(data?.outgoing?.length > 0 || data?.email_invites?.length > 0) && (
        <section className="mt-6" data-testid="friend-pending">
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">Menunggu</h2>
          <div className="mt-2 space-y-1">
            {data.outgoing.map((r) => <p key={r.request_id} className="flex items-center gap-2 text-xs text-slate-500"><Clock size={12} /> {r.name} ({r.email}) — menunggu persetujuan</p>)}
            {data.email_invites.map((e) => <p key={e.email} className="flex items-center gap-2 text-xs text-slate-500"><Mail size={12} /> {e.email} — email ajakan terkirim, belum mendaftar</p>)}
          </div>
        </section>
      )}
    </div>
  );
}
