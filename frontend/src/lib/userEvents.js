import { useEffect } from "react";
import { toast } from "sonner";
import { WS_BASE, getToken } from "./api";
import { listenForegroundPush } from "./firebase";

const EVENT = "oryntix:event";
export const emitUserEvent = (detail) => window.dispatchEvent(new CustomEvent(EVENT, { detail }));

// Subscribe to per-user realtime events (reminder_due, incoming_call, task_update, message_new, push). Returns unsubscribe.
export function onUserEvent(types, cb) {
  const set = types ? new Set([].concat(types)) : null;
  const h = (e) => { if (!set || set.has(e.detail?.type)) cb(e.detail); };
  window.addEventListener(EVENT, h);
  return () => window.removeEventListener(EVENT, h);
}

// Opens /api/ws/user while signed in (auto-reconnect with backoff) and re-emits events; foreground FCM messages become events too.
export function useUserEvents(active) {
  useEffect(() => {
    if (!active || !getToken()) return;
    let ws, stopped = false, delay = 1000, timer;
    const open = () => {
      ws = new WebSocket(`${WS_BASE}/ws/user?token=${getToken()}`);
      ws.onopen = () => { delay = 1000; };
      ws.onmessage = (ev) => { try { emitUserEvent(JSON.parse(ev.data)); } catch (e) {} };
      ws.onclose = (ev) => { if (ev.code === 4401) return;  /* invalid token: wait for a new sign-in */ if (!stopped) { timer = setTimeout(open, delay); delay = Math.min(delay * 2, 30000); } };
    };
    open();
    let unsubPush = () => {};
    listenForegroundPush((d) => { emitUserEvent({ type: "push", ...d }); if (d.title) toast(d.title, { description: d.body }); }).then((u) => { unsubPush = u || (() => {}); }).catch(() => {});
    return () => { stopped = true; clearTimeout(timer); try { ws && ws.close(); } catch (e) {} unsubPush(); };
  }, [active]);
}
