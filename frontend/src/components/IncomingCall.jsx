import React, { useEffect, useState, useRef } from "react";
import { onUserEvent, coalesce } from "../lib/userEvents";
import { Phone, PhoneOff, X, Volume2, AlarmClock } from "lucide-react";
import { toast } from "sonner";
import { api, API_BASE, getToken } from "../lib/api";
import { Mark } from "./Logo";
import { useAuth } from "../context/AuthContext";
import { isMuted } from "./SoundToggle";
import { VideoRoom } from "./VideoRoom";
import { RealtimeCall } from "./RealtimeCall";
import { useRealtimeStatus } from "../hooks/useRealtimeStatus";

export function IncomingCall() {
  const { user, refreshUser } = useAuth();
  const rt = useRealtimeStatus();
  const [call, setCall] = useState(null);
  const [answered, setAnswered] = useState(null);
  const [busy, setBusy] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [inCall, setInCall] = useState(null); // {conv, cid}
  const dismissed = useRef(new Set());
  const audioRef = useRef(null);

  useEffect(() => {
    if (!user) return;
    let active = true;
    const poll = async () => {
      try {
        const r = await api.get("/reminders/incoming");
        const next = (r.data || []).find((x) => !dismissed.current.has(x.id));
        if (active && next && !answered && !inCall) setCall((c) => c || next);
      } catch (e) {}
    };
    poll();
    const off = onUserEvent(["reminder_due", "incoming_call", "push", "ws_state"], () => coalesce("reminder-due", poll)); // trigger → GET
    return () => { active = false; off(); };
  }, [user, answered, inCall]);

  if (inCall) {
    const close = () => { setInCall(null); setAnswered(null); setCall(null); };
    if (inCall.realtime) return <RealtimeCall conv={inCall.conv} cid={inCall.cid} opening={inCall.opening} onClose={close} onRefresh={() => refreshUser()} />;
    return <VideoRoom conv={inCall.conv} cid={inCall.cid} isPrivate onClose={close} onRefresh={() => refreshUser()} />;
  }
  if (!call) return null;
  const persona = call.persona;
  const portrait = persona?.portrait;
  const name = persona?.name || "Asisten";

  const decline = async () => {
    dismissed.current.add(call.id);
    try { await api.post(`/reminders/${call.id}/respond`, { action: "decline" }); } catch (e) {}
    setCall(null);
  };
  const snooze = async (minutes = 10) => {
    dismissed.current.add(call.id);
    try { await api.post(`/reminders/${call.id}/snooze`, { minutes }); toast.success(`Oke, ${name} akan mengingatkan lagi ${minutes} menit lagi`); } catch (e) { toast.error("Gagal menunda"); }
    setCall(null);
  };

  const speakAndContinue = async (data) => {
    // play the reminder aloud in the persona's voice, then continue as a normal call
    if (data.persona && data.message && !isMuted(user)) {
      setSpeaking(true);
      try {
        const res = await fetch(`${API_BASE}/voice/tts`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` }, body: JSON.stringify({ text: data.message.slice(0, 1200), voice: data.persona.voice || "nova" }) });
        const ab = await res.blob();
        const a = new Audio(URL.createObjectURL(ab)); audioRef.current = a;
        await new Promise((resolve) => { a.onended = resolve; a.onerror = resolve; a.play().catch(resolve); });
      } catch (e) {}
      setSpeaking(false);
    }
    if (data.conversation) {
      setInCall({ conv: data.conversation, cid: data.conversation.id });
    }
  };

  const accept = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/reminders/${call.id}/respond`, { action: "accept", realtime: !!rt.enabled });
      dismissed.current.add(call.id);
      refreshUser();
      if (rt.enabled && r.data.conversation) {
        // the assistant opens the realtime call by speaking the reminder itself
        setInCall({ conv: r.data.conversation, cid: r.data.conversation.id, realtime: true, opening: r.data.opening });
        return;
      }
      setAnswered({ ...r.data, name });
      speakAndContinue(r.data);
    } catch (e) {} finally { setBusy(false); }
  };
  const closeAnswered = () => { try { audioRef.current?.pause(); } catch (e) {} setAnswered(null); setCall(null); setInCall(null); };

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
            <button onClick={() => snooze(10)} data-testid="call-snooze-btn" className="mt-5 inline-flex items-center gap-1.5 rounded-full border border-[#E7ECF3] px-4 py-2 text-xs font-semibold text-slate-600 transition hover:bg-slate-50"><AlarmClock size={14} /> Ingatkan lagi 10 menit</button>
          </>
        ) : (
          <>
            <button onClick={closeAnswered} className="absolute right-4 top-4 text-slate-400"><X size={18} /></button>
            <div className={`mx-auto mb-4 flex h-20 w-20 items-center justify-center overflow-hidden rounded-full bg-[#EEF3FF] ${speaking ? "glow-ring" : ""}`} style={{ border: "2px solid #2F6BFF" }}>
              {portrait ? <img src={portrait} alt={name} className="h-full w-full object-cover" /> : <Mark size={44} />}
            </div>
            <h3 className="text-lg font-bold text-slate-900">{name}</h3>
            <p className="mt-1 flex items-center justify-center gap-1.5 text-xs font-semibold text-[#10B981]">{speaking ? <><Volume2 size={13} /> Sedang berbicara...</> : "Pengingat"}</p>
            <p className="mt-3 text-left text-sm leading-relaxed text-slate-600" data-testid="call-message">{answered.message}</p>
            {answered.conversation ? (
              <button onClick={() => setInCall({ conv: answered.conversation, cid: answered.conversation.id })} data-testid="call-continue-btn" className="btn-grad mt-6 w-full rounded-xl py-3">Lanjutkan Panggilan</button>
            ) : (
              <button onClick={closeAnswered} data-testid="call-end-btn" className="btn-grad mt-6 w-full rounded-xl py-3">Akhiri</button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
