import React, { useEffect, useRef, useState } from "react";
import { onUserEvent, isWsConnected } from "../lib/userEvents";
import { useLocation, useNavigate } from "react-router-dom";
import { Phone, PhoneOff, Users } from "lucide-react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { isMuted } from "./SoundToggle";

// Simple synthesized ringtone (no asset needed): two-tone pulse every 2s.
function startRing() {
  try {
    const ac = new (window.AudioContext || window.webkitAudioContext)();
    const gain = ac.createGain(); gain.gain.value = 0.0001; gain.connect(ac.destination);
    const o1 = ac.createOscillator(); o1.frequency.value = 880; o1.connect(gain);
    const o2 = ac.createOscillator(); o2.frequency.value = 660; o2.connect(gain);
    o1.start(); o2.start();
    const pulse = () => { const t = ac.currentTime; gain.gain.cancelScheduledValues(t); gain.gain.setValueAtTime(0.0001, t); gain.gain.exponentialRampToValueAtTime(0.12, t + 0.05); gain.gain.setValueAtTime(0.12, t + 0.8); gain.gain.exponentialRampToValueAtTime(0.0001, t + 1.0); };
    pulse(); const iv = setInterval(() => { pulse(); if (navigator.vibrate) navigator.vibrate([300, 200, 300]); }, 2000);
    return () => { clearInterval(iv); try { o1.stop(); o2.stop(); ac.close(); } catch (e) {} };
  } catch (e) { return () => {}; }
}

// Rings when a friend is inside a group/DM call that I'm part of but haven't joined.
export function FriendCallRing() {
  const { user } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [call, setCall] = useState(null);
  const dismissed = useRef(new Set()); // conversation ids declined (reset when that call ends)
  const stopRef = useRef(null);

  useEffect(() => {
    if (!user) return;
    let alive = true;
    const poll = async () => {
      try {
        const r = await api.get("/calls/incoming");
        const liveIds = new Set((r.data || []).map((x) => x.conversation_id));
        dismissed.current.forEach((id) => { if (!liveIds.has(id)) dismissed.current.delete(id); });
        const inRoom = loc.pathname.startsWith("/chat/") && window.__oryntixInCall;
        const next = (r.data || []).find((x) => !dismissed.current.has(x.conversation_id) && !(inRoom && loc.pathname.endsWith(x.conversation_id)));
        if (alive) setCall(next || null);
      } catch (e) {}
    };
    poll();
    const iv = setInterval(() => { if (!isWsConnected()) poll(); }, 30000); const off = onUserEvent(["incoming_call", "push", "ws_state"], poll);
    return () => { alive = false; clearInterval(iv); off(); };
  }, [user?.id, loc.pathname]); // eslint-disable-line

  const muted = isMuted(user);
  useEffect(() => {
    if (call && !muted && !stopRef.current) stopRef.current = startRing();
    if ((!call || muted) && stopRef.current) { stopRef.current(); stopRef.current = null; }
  }, [call, muted]);
  useEffect(() => () => { if (stopRef.current) { stopRef.current(); stopRef.current = null; } }, []); // unmount: never leave the ringtone playing

  if (!call) return null;
  const decline = () => { dismissed.current.add(call.conversation_id); setCall(null); };
  const accept = () => { dismissed.current.add(call.conversation_id); setCall(null); nav(`/chat/${call.conversation_id}`, { state: { openMeeting: true } }); };
  return (
    <div className="fixed inset-x-0 top-4 z-[101] flex justify-center px-4" data-testid="friend-call-ring">
      <div className="flex w-full max-w-md items-center gap-3 rounded-2xl border border-[#E7ECF3] bg-white p-3 shadow-2xl fade-up">
        <span className="glow-ring flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[#10B981] text-white"><Users size={20} /></span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-bold text-slate-900" data-testid="friend-call-title">{call.callers.join(", ")} memulai panggilan</p>
          <p className="truncate text-xs text-slate-500">{call.title}{call.assistants?.length ? ` · asisten: ${call.assistants.join(", ")}` : ""}</p>
        </div>
        <button onClick={decline} data-testid="friend-call-decline" title="Tolak" className="flex h-11 w-11 items-center justify-center rounded-full bg-[#EF4444] text-white"><PhoneOff size={18} /></button>
        <button onClick={accept} data-testid="friend-call-accept" title="Angkat" className="flex h-11 items-center gap-2 rounded-full bg-[#10B981] px-4 text-sm font-bold text-white"><Phone size={18} /> Angkat</button>
      </div>
    </div>
  );
}
