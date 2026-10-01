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

export const WS_BASE = API_BASE.replace(/^http/, "ws");

// Open a realtime WebSocket for a conversation. Returns the WebSocket (auto-closes handled by caller).
export function openConvSocket(cid, onEvent) {
  const ws = new WebSocket(`${WS_BASE}/ws/${cid}?token=${getToken()}`);
  ws.onmessage = (e) => { try { onEvent(JSON.parse(e.data)); } catch (_) {} };
  return ws;
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
