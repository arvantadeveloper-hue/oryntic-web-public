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

// Streaming chat with attachments + optional extra body fields (e.g. {moderator:false}).
export async function streamChatWithAtt(cid, content, attachments, onEvent, extra = {}) {
  const res = await fetch(`${API_BASE}/conversations/${cid}/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ content, attachments, ...extra }),
  });
  if (!res.ok || !res.body) throw new Error("stream failed");
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
