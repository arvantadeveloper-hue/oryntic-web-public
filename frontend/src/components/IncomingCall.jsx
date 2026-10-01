import React, { useEffect, useState, useRef } from "react";
import { Phone, PhoneOff, X } from "lucide-react";
import { api } from "../lib/api";
import { Mark } from "./Logo";
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
  const portrait = persona?.portrait;
  const name = persona?.name || "Asisten";

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
      <div className="absolute inset-0 bg-slate-900/50 backdrop-blur-sm" />
      <div className="relative w-full max-w-sm rounded-3xl border border-[#E7ECF3] bg-white p-8 text-center shadow-2xl fade-up">
        {!answered ? (
          <>
            <p className="mb-6 text-xs font-semibold uppercase tracking-widest text-[#2F6BFF]">Panggilan masuk</p>
            <div className="mx-auto mb-5 flex h-28 w-28 items-center justify-center overflow-hidden rounded-full glow-ring bg-[#EEF3FF]" style={{ border: "3px solid #2F6BFF" }}>
              {portrait ? <img src={portrait} alt={name} className="h-full w-full object-cover" /> : <Mark size={60} />}
            </div>
            <h2 className="text-2xl font-bold text-slate-900" data-testid="call-persona-name">{name}</h2>
            <p className="mt-1 text-sm text-slate-500">Asisten AI Anda · Pengingat Jadwal</p>
            <p className="mt-4 rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">"{name} menelepon terkait: {call.title}"</p>
            <div className="mt-8 flex items-center justify-center gap-10">
              <button onClick={decline} data-testid="call-decline-btn" className="flex h-16 w-16 items-center justify-center rounded-full bg-[#EF4444] text-white transition hover:scale-105"><PhoneOff size={26} /></button>
              <button onClick={accept} disabled={busy} data-testid="call-accept-btn" className="flex h-16 w-16 items-center justify-center rounded-full bg-[#10B981] text-white transition hover:scale-105 disabled:opacity-50"><Phone size={26} /></button>
            </div>
          </>
        ) : (
          <>
            <button onClick={closeAnswered} className="absolute right-4 top-4 text-slate-400"><X size={18} /></button>
            <div className="mx-auto mb-4 flex h-20 w-20 items-center justify-center overflow-hidden rounded-full bg-[#EEF3FF]" style={{ border: "2px solid #2F6BFF" }}>
              {portrait ? <img src={portrait} alt={name} className="h-full w-full object-cover" /> : <Mark size={44} />}
            </div>
            <h3 className="text-lg font-bold text-slate-900">{name}</h3>
            <p className="mt-3 text-left text-sm leading-relaxed text-slate-600" data-testid="call-message">{answered.message}</p>
            <button onClick={closeAnswered} data-testid="call-end-btn" className="btn-grad mt-6 w-full rounded-xl py-3">Akhiri</button>
          </>
        )}
      </div>
    </div>
  );
}
