import React, { useEffect, useState, useRef } from "react";
import { Phone, PhoneOff, X } from "lucide-react";
import { api } from "../lib/api";
import { AIVORA_MARK } from "./Logo";
import { useAuth } from "../context/AuthContext";

export function IncomingCall() {
  const { user, refreshUser } = useAuth();
  const [call, setCall] = useState(null);
  const [answered, setAnswered] = useState(null);
  const [busy, setBusy] = useState(false);
  const dismissed = useRef(new Set());

  useEffect(() => {
    if (!user) return;
    let active = true;
    const poll = async () => {
      try {
        const r = await api.get("/reminders/incoming");
        const next = (r.data || []).find((x) => !dismissed.current.has(x.id));
        if (active && next && !answered) setCall((c) => c || next);
      } catch (e) {}
    };
    poll();
    const iv = setInterval(poll, 12000);
    return () => { active = false; clearInterval(iv); };
  }, [user, answered]);

  if (!call) return null;

  const persona = call.persona;
  const avatar = persona?.portrait || AIVORA_MARK;
  const name = persona?.name || "Aivora";

  const decline = async () => {
    dismissed.current.add(call.id);
    try { await api.post(`/reminders/${call.id}/respond`, { action: "decline" }); } catch (e) {}
    setCall(null);
  };

  const accept = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/reminders/${call.id}/respond`, { action: "accept" });
      dismissed.current.add(call.id);
      setAnswered({ ...r.data, name });
      refreshUser();
    } catch (e) {} finally { setBusy(false); }
  };

  const closeAnswered = () => { setAnswered(null); setCall(null); };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4" data-testid="incoming-call-overlay">
      <div className="absolute inset-0 glass" />
      <div className="relative w-full max-w-sm rounded-3xl border border-[rgba(0,209,255,0.3)] bg-[#111C3A] p-8 text-center fade-up"
        style={{ boxShadow: "0 24px 80px rgba(0,209,255,0.2)" }}>
        {!answered ? (
          <>
            <p className="mb-6 text-xs font-semibold uppercase tracking-widest text-[#00D1FF]">Panggilan masuk</p>
            <div className="mx-auto mb-5 h-28 w-28 overflow-hidden rounded-full glow-ring"
              style={{ border: "3px solid rgba(0,209,255,.5)" }}>
              <img src={avatar} alt={name} className="h-full w-full object-cover" />
            </div>
            <h2 className="text-2xl font-bold text-white" data-testid="call-persona-name">{name}</h2>
            <p className="mt-1 text-sm text-slate-400">Asisten AI Anda · Pengingat Jadwal</p>
            <p className="mt-4 rounded-xl bg-[#0e1830] px-4 py-3 text-sm text-slate-300">"{name} menelepon terkait: {call.title}"</p>
            <div className="mt-8 flex items-center justify-center gap-10">
              <button onClick={decline} data-testid="call-decline-btn"
                className="flex h-16 w-16 items-center justify-center rounded-full bg-[#EF4444] text-white transition hover:scale-105">
                <PhoneOff size={26} />
              </button>
              <button onClick={accept} disabled={busy} data-testid="call-accept-btn"
                className="flex h-16 w-16 items-center justify-center rounded-full bg-[#10B981] text-white transition hover:scale-105 disabled:opacity-50">
                <Phone size={26} />
              </button>
            </div>
          </>
        ) : (
          <>
            <button onClick={closeAnswered} className="absolute right-4 top-4 text-slate-400"><X size={18} /></button>
            <div className="mx-auto mb-4 h-20 w-20 overflow-hidden rounded-full" style={{ border: "2px solid rgba(0,209,255,.5)" }}>
              <img src={avatar} alt={name} className="h-full w-full object-cover" />
            </div>
            <h3 className="text-lg font-bold text-white">{name}</h3>
            <p className="mt-3 text-left text-sm leading-relaxed text-slate-200" data-testid="call-message">{answered.message}</p>
            <button onClick={closeAnswered} data-testid="call-end-btn" className="btn-grad mt-6 w-full rounded-xl py-3">Akhiri</button>
          </>
        )}
      </div>
    </div>
  );
}
