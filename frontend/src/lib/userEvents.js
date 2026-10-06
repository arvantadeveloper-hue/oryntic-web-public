import { useEffect, useState } from "react";
import { toast } from "sonner";
import { WS_BASE, getToken } from "./api";
import { listenForegroundPush } from "./firebase";

const EVENT = "oryntix:event";
export const emitUserEvent = (detail) => window.dispatchEvent(new CustomEvent(EVENT, { detail }));

// Connection state of the user WebSocket: when it is up, everything arrives as push and GET polling is suspended.
let wsConnected = false;
export const isWsConnected = () => wsConnected;
const setWsConnected = (v) => { if (wsConnected !== v) { wsConnected = v; emitUserEvent({ type: "ws_state", connected: v }); } };
export function useWsConnected() {
  const [c, setC] = useState(wsConnected);
  useEffect(() => onUserEvent(["ws_state"], (e) => setC(!!e.connected)), []);
  return c;
}

// Run `fn` on mount, then: on every listed push event; on a GET interval ONLY while the WebSocket is down;
// once when the socket reconnects and once when the tab becomes visible again (resync after background).
export function useLiveSync(fn, events, intervalMs, deps = []) {
  useEffect(() => {
    let timer = null, alive = true;
    const run = (...a) => { if (alive) fn(...a); };
    const arm = () => { clearInterval(timer); timer = null; if (!wsConnected && intervalMs) timer = setInterval(run, intervalMs); };
    run(); arm();
    const offEv = events && events.length ? onUserEvent(events, run) : () => {};
    const offWs = onUserEvent(["ws_state"], (e) => { arm(); if (e.connected) run(); });
    const onVis = () => { if (document.visibilityState === "visible") run(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { alive = false; clearInterval(timer); offEv(); offWs(); document.removeEventListener("visibilitychange", onVis); };
    /* eslint-disable-next-line */
  }, deps);
}

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
    let ws, stopped = false, delay = 1000, timer, ping;
    const open = () => {
      ws = new WebSocket(`${WS_BASE}/ws/user?token=${getToken()}`);
      ws.onopen = () => { delay = 1000; setWsConnected(true); clearInterval(ping); ping = setInterval(() => { try { ws.readyState === 1 && ws.send("ping"); } catch (e) {} }, 25000); };
      ws.onmessage = (ev) => { try { emitUserEvent(JSON.parse(ev.data)); } catch (e) {} };
      ws.onclose = (ev) => { setWsConnected(false); clearInterval(ping); if (ev.code === 4401) return;  /* invalid token: wait for a new sign-in */ if (!stopped) { timer = setTimeout(open, delay); delay = Math.min(delay * 2, 30000); } };
    };
    open();
    let unsubPush = () => {};
    listenForegroundPush((d) => { emitUserEvent({ type: "push", ...d }); if (d.title) toast(d.title, { description: d.body }); }).then((u) => { unsubPush = u || (() => {}); }).catch(() => {});
    return () => { stopped = true; clearTimeout(timer); clearInterval(ping); setWsConnected(false); try { ws && ws.close(); } catch (e) {} unsubPush(); };
  }, [active]);
}
