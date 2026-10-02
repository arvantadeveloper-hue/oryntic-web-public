import { API_BASE, getToken, api } from "./api";

export const reportUsage = (callId, ev) => { if (ev?.type === "response.done" && ev.response?.usage) api.post(`/realtime/calls/${callId}/usage`, { usage: ev.response.usage }).catch(() => {}); };

// Same semantic-VAD mapping as backend `vad_config`; interruption is confirmed client-side (see MicPipeline.openFor).
export const vadUpdate = (sensitivity, createResponse) => ({
  type: "session.update",
  session: { type: "realtime", audio: { input: { turn_detection: { type: "semantic_vad", eagerness: sensitivity, create_response: createResponse, interrupt_response: false } } } },
});

// One OpenAI Realtime WebRTC session (negotiated via our backend) sharing the user's mic stream.
export class RealtimeSession {
  constructor({ callId, persona, primary, stream, onEvent, onError, sensitivity = "medium", createResponse = false }) {
    this.callId = callId; this.persona = persona; this.primary = primary; this.stream = stream;
    this.onEvent = onEvent; this.onError = onError; this.sensitivity = sensitivity; this.createResponse = createResponse;
    this.pc = null; this.dc = null; this.audioEl = null; this.ac = null; this.analyser = null; this.buf = null;
    this.level = 0; this.closed = false;
  }

  async connect() {
    const pc = new RTCPeerConnection(); this.pc = pc;
    const audioEl = document.createElement("audio"); audioEl.autoplay = true; document.body.appendChild(audioEl); this.audioEl = audioEl;
    pc.ontrack = (e) => { audioEl.srcObject = e.streams[0]; this._monitor(e.streams[0]); };
    this.stream.getTracks().forEach((t) => pc.addTrack(t, this.stream));
    const dc = pc.createDataChannel("oai-events"); this.dc = dc;
    dc.onmessage = (e) => { try { reportUsage(this.callId, ev); this.onEvent(this, JSON.parse(e.data)); } catch (err) {} };
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

  updateVad(sensitivity) {
    this.sensitivity = sensitivity;
    this.send(vadUpdate(sensitivity, this.createResponse));
  }

  close() {
    this.closed = true;
    try { this.ac?.close(); } catch (e) {}
    try { this.dc?.close(); } catch (e) {}
    try { this.pc?.close(); } catch (e) {}
    try { if (this.audioEl) { this.audioEl.srcObject = null; this.audioEl.remove(); } } catch (e) {}
  }
}
