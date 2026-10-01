import { useEffect, useState } from "react";
import { api } from "../lib/api";

let cached = null;

// Whether speech-to-speech Realtime calls are enabled on the backend (OPENAI_API_KEY configured).
export function useRealtimeStatus() {
  const [status, setStatus] = useState(cached);
  useEffect(() => {
    if (cached) return;
    api.get("/realtime/status").then((r) => { cached = r.data; setStatus(r.data); }).catch(() => setStatus({ enabled: false }));
  }, []);
  return status || { enabled: false };
}
