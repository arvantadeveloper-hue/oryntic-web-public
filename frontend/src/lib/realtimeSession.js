import { API_BASE, getToken, api } from "./api";

export const reportUsage = (callId, ev) => { if (ev?.type === "response.done" && ev.response?.usage) api.post(`/realtime/calls/${callId}/usage`, { usage: ev.response.usage }).catch(() => {}); };

// Same semantic-VAD mapping as backend `vad_config`; interruption is confirmed client-side (see MicPipeline.openFor).
export const vadUpdate = (sensitivity, createResponse) => ({
  type: "session.update",
  session: { type: "realtime", audio: { input: { turn_detection: { type: "semantic_vad", eagerness: ({ low: "low", medium: "low", high: "medium" })[sensitivity] || "low", create_response: createResponse, interrupt_response: false } } } },
});

// Replaces old audio turns with ONE compact text item, so every new response re-reads far fewer (and cheaper, text) input tokens.
export class ContextPruner {
  constructor(session, { keep = 6, threshold = 14, maxChars = 2400 } = {}) {
    this.s = session; this.keep = keep; this.threshold = threshold; this.maxChars = maxChars;
    this.items = []; this.summaryId = null; this.summary = ""; this.pruned = 0;
  }

  onEvent(ev) {
    switch (ev.type) {
      case "conversation.item.added":
      case "conversation.item.created": {
        const it = ev.item;
        if (!it?.id || it.id === this.summaryId || this.items.some((x) => x.id === it.id)) return;
        const text = (it.content || []).map((c) => c.text || c.transcript || "").join(" ").trim()
          || (it.type === "function_call" ? `(handed over: ${it.arguments || ""})` : it.type === "function_call_output" ? `(result: ${(it.output || "").slice(0, 300)})` : "");
        this.items.push({ id: it.id, role: it.role || it.type, text });
        return;
      }
      case "conversation.item.input_audio_transcription.completed": this._set(ev.item_id, ev.transcript); return;
      case "response.output_audio_transcript.done": this._set(ev.item_id, ev.transcript); return;
      default:
    }
  }

  _set(id, text) { const it = this.items.find((x) => x.id === id); if (it && text) it.text = text; }

  // Call between turns only (never while a response is in flight).
  prune() {
    if (this.items.length < this.threshold) return false;
    const old = this.items.splice(0, this.items.length - this.keep);
    const lines = old.filter((i) => i.text).map((i) => `${i.role === "user" ? "User" : i.role === "assistant" ? "Assistant" : "Note"}: ${i.text}`);
    this.summary = `${this.summary}\n${lines.join("\n")}`.trim().slice(-this.maxChars);
    old.forEach((i) => this.s.send({ type: "conversation.item.delete", item_id: i.id }));
    if (this.summaryId) this.s.send({ type: "conversation.item.delete", item_id: this.summaryId });
    this.summaryId = `ctx_${Date.now().toString(36)}`;
    this.s.send({ type: "conversation.item.create", previous_item_id: "root", item: { id: this.summaryId, type: "message", role: "user", content: [{ type: "input_text", text: `[Earlier in this call — condensed transcript, for context only]\n${this.summary}` }] } });
    this.pruned += old.length;
    return true;
  }
}

// One OpenAI Realtime WebRTC session (negotiated via our backend). sendAudio=false → receive-only (panelists get the user's words as text).
export class RealtimeSession {
  constructor({ callId, persona, primary, role, stream, onEvent, onError, sensitivity = "medium", createResponse = false, sendAudio = true }) {
    this.callId = callId; this.persona = persona; this.primary = primary; this.role = role; this.stream = stream;
    this.onEvent = onEvent; this.onError = onError; this.sensitivity = sensitivity; this.createResponse = createResponse; this.sendAudio = sendAudio;
    this.pc = null; this.dc = null; this.audioEl = null; this.ac = null; this.analyser = null; this.buf = null;
    this.level = 0; this.closed = false;
    this.pruner = new ContextPruner(this);
  }

  async connect() {
    const pc = new RTCPeerConnection(); this.pc = pc;
    const audioEl = document.createElement("audio"); audioEl.autoplay = true; document.body.appendChild(audioEl); this.audioEl = audioEl;
    pc.ontrack = (e) => { audioEl.srcObject = e.streams[0]; this._monitor(e.streams[0]); };
    if (this.sendAudio && this.stream) this.stream.getTracks().forEach((t) => pc.addTrack(t, this.stream));
    else pc.addTransceiver("audio", { direction: "recvonly" });
    const dc = pc.createDataChannel("oai-events"); this.dc = dc;
    dc.onmessage = (e) => { try { const ev = JSON.parse(e.data); reportUsage(this.callId, ev); this.pruner.onEvent(ev); this.onEvent(this, ev); } catch (err) {} };
    pc.onconnectionstatechange = () => { if (["failed", "disconnected", "closed"].includes(pc.connectionState) && !this.closed) this.onError?.(this, new Error("connection lost")); };
    const opened = new Promise((resolve) => { dc.onopen = resolve; });
    const offer = await pc.createOffer(); await pc.setLocalDescription(offer);
    const res = await fetch(`${API_BASE}/realtime/calls/${this.callId}/negotiate?sensitivity=${this.sensitivity}`, { method: "POST", headers: { "Content-Type": "application/sdp", Authorization: `Bearer ${getToken()}` }, body: offer.sdp });
    if (!res.ok) { let d = "Negosiasi gagal"; try { d = (await res.json()).detail || d; } catch (e) {} throw new Error(d); }
    const answer = await res.text();
    if (this.closed) return;
    await pc.setRemoteDescription({ type: "answer", sdp: answer });
    await Promise.race([opened, new Promise((_, rej) => setTimeout(() => rej(new Error("timeout data channel")), 15000))]);
  }

  _monitor(stream) {
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      this.ac = new AC(); this.analyser = this.ac.createAnalyser(); this.analyser.fftSize = 512;
      this.ac.createMediaStreamSource(stream).connect(this.analyser);
      this.buf = new Uint8Array(this.analyser.fftSize);
    } catch (e) {}
  }

  readLevel() {
    if (!this.analyser) return 0;
    this.analyser.getByteTimeDomainData(this.buf);
    let s = 0; for (let i = 0; i < this.buf.length; i++) { const d = (this.buf[i] - 128) / 128; s += d * d; }
    this.level = Math.min(1, Math.sqrt(s / this.buf.length) * 4);
    return this.level;
  }

  send(ev) { try { if (this.dc?.readyState === "open") this.dc.send(JSON.stringify(ev)); } catch (e) {} }

  respond(instructions) { this.send({ type: "response.create", ...(instructions ? { response: { instructions } } : {}) }); }

  cancel() { this.send({ type: "response.cancel" }); this.send({ type: "output_audio_buffer.clear" }); }

  inject(text) { this.send({ type: "conversation.item.create", item: { type: "message", role: "user", content: [{ type: "input_text", text }] } }); }

  toolOutput(callId, output) { this.send({ type: "conversation.item.create", item: { type: "function_call_output", call_id: callId, output: typeof output === "string" ? output : JSON.stringify(output) } }); }

  updateVad(sensitivity) {
    this.sensitivity = sensitivity;
    if (this.sendAudio) this.send(vadUpdate(sensitivity, this.createResponse));
  }

  close() {
    this.closed = true;
    try { this.ac?.close(); } catch (e) {}
    try { this.dc?.close(); } catch (e) {}
    try { this.pc?.close(); } catch (e) {}
    try { if (this.audioEl) { this.audioEl.srcObject = null; this.audioEl.remove(); } } catch (e) {}
  }
}

// Voice tools shared by solo calls and meetings: the model asks, we call our API, the result goes back as function_call_output.
export async function runVoiceTool(name, args, cid) {
  try {
    if (name === "assign_task") { const r = await api.post(`/conversations/${cid}/tasks`, { title: args.title, brief: args.brief, scheduled_at: args.scheduled_at || null, persona_id: args.persona_id || null, team: !!args.team, assignments: Array.isArray(args.assignments) ? args.assignments : null }); return { ok: true, ...r.data }; }
    if (name === "search_workspace") { const r = await api.post(`/conversations/${cid}/workspace-search`, { query: args.query }); return { ok: true, ...r.data, note: "links were posted to the chat panel" }; }
    if (name === "update_task") {
      const c = await api.get(`/conversations/${cid}/messages?limit=1`);
      const tid = c.data?.conversation?.task_id;
      if (!tid) return { ok: false, error: "no task linked to this conversation" };
      const r = await api.post(`/tasks/${tid}/revise`, { instruction: args.instruction });
      return { ok: true, version: r.data.version, summary: r.data.summary };
    }
    return { ok: false, error: `unknown tool ${name}` };
  } catch (e) { return { ok: false, error: e?.response?.data?.detail || e.message }; }
}
