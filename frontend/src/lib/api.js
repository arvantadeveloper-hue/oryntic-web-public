import { toast } from "sonner";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API_BASE });

export function setAuthToken(token) {
  if (token) {
    api.defaults.headers.common["Authorization"] = `Bearer ${token}`;
    localStorage.setItem("aivora_token", token);
  } else {
    delete api.defaults.headers.common["Authorization"];
    localStorage.removeItem("aivora_token");
  }
}

const saved = localStorage.getItem("aivora_token");
if (saved) api.defaults.headers.common["Authorization"] = `Bearer ${saved}`;

export function getToken() {
  return localStorage.getItem("aivora_token");
}

// WebSockets are ALWAYS encrypted (wss) so realtime traffic (chat events, user events, call audio) never travels in clear text —
// even when REACT_APP_BACKEND_URL is given as http. REACT_APP_WS_SCHEME=ws is the only (local-dev) opt-out.
const WS_SCHEME = process.env.REACT_APP_WS_SCHEME === "ws" ? "ws" : "wss";
export const WS_BASE = API_BASE.replace(/^https?/, WS_SCHEME);
export const secureWsUrl = (url) => (WS_SCHEME === "wss" && typeof url === "string" ? url.replace(/^ws:\/\//i, "wss://") : url);

// Conversation WebSocket with keepalive pings (proxies drop idle sockets) and auto-reconnect with backoff.
// Returns a handle: { send(obj), close(), get socket(), onReconnect } — `onReconnect` fires after a re-established connection so callers can resync.
export function openConvSocket(cid, onEvent, onReconnect) {
  let ws = null, stopped = false, delay = 1000, timer = null, ping = null, wasOpen = false;
  const open = () => {
    if (stopped) return;
    ws = new WebSocket(`${WS_BASE}/ws/${cid}?token=${getToken()}`);
    ws.onopen = () => { delay = 1000; if (wasOpen) onReconnect?.(); wasOpen = true; clearInterval(ping); ping = setInterval(() => { try { ws.readyState === 1 && ws.send(JSON.stringify({ type: "ping" })); } catch (_) {} }, 25000); };
    ws.onmessage = (e) => { try { onEvent(JSON.parse(e.data)); } catch (_) {} };
    ws.onclose = (ev) => { clearInterval(ping); if (stopped || ev.code === 4401 || ev.code === 4403) return; timer = setTimeout(open, delay); delay = Math.min(delay * 2, 30000); };
  };
  open();
  return {
    get socket() { return ws; },
    get readyState() { return ws ? ws.readyState : 3; },
    send(obj) { try { ws && ws.readyState === 1 && ws.send(typeof obj === "string" ? obj : JSON.stringify(obj)); } catch (_) {} },
    close() { stopped = true; clearTimeout(timer); clearInterval(ping); try { ws && ws.close(); } catch (_) {} },
  };
}

// Generic SSE POST stream. `signal` (AbortSignal) lets the caller cancel mid-stream (barge-in).
export async function streamSSE(path, body, onEvent, signal) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const err = new Error("stream failed"); err.status = res.status;
    err.retryAfter = Number(res.headers.get("Retry-After")) || 0;
    try { err.detail = (await res.json()).detail; } catch (e) {}
    throw err;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop();
    for (const ev of events) {
      const line = ev.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const data = line.slice(6);
      if (data === "[DONE]") continue;
      try { onEvent(JSON.parse(data)); } catch (e) {}
    }
  }
}

// Streaming chat with attachments + optional extra body fields (e.g. {moderator:false}).
export function streamChatWithAtt(cid, content, attachments, onEvent, extra = {}, signal) {
  return streamSSE(`/conversations/${cid}/send`, { content, attachments, ...extra }, onEvent, signal);
}

api.interceptors.response.use((r) => r, (err) => {
  if (err?.response?.status === 429) toast.error(err.response.data?.detail || "Terlalu banyak permintaan, coba lagi sebentar.");
  return Promise.reject(err);
});
