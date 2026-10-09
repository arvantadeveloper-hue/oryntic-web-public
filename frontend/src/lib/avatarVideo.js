import { Room, RoomEvent, Track } from "livekit-client";
import { secureWsUrl } from "./api";

// Bridges our OpenAI Realtime audio to a LiveAvatar LITE session: PCM16 24 kHz chunks go over the LiveAvatar WebSocket
// (agent.speak / speak_end / interrupt) and the lip-synced avatar video+audio arrive through LiveKit.
const b64 = (i16) => { const u8 = new Uint8Array(i16.buffer, i16.byteOffset, i16.byteLength); let s = ""; for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000)); return btoa(s); };
const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);

export class AvatarBridge {
  constructor({ onState, onError, onVideoTrack, onAudioTrack, onConnection }) {
    this.onState = onState; this.onError = onError; this.onVideoTrack = onVideoTrack; this.onAudioTrack = onAudioTrack; this.onConnection = onConnection;
    this.ws = null; this.room = null; this.ac = null; this.proc = null; this.src = null;
    this.ready = false; this.forwarding = false; this.utterance = null; this.pending = []; this.keep = null; this.closed = false;
  }

  async start({ ws_url, livekit_url, livekit_client_token, livekit_agent_token }, remoteStream) {
    await Promise.all([this._openWs(ws_url), this._joinRoom(livekit_url, livekit_client_token), this._joinAsAgent(livekit_url, livekit_agent_token)]);
    if (remoteStream) this.attachAudio(remoteStream);
    this.keep = setInterval(() => this._send({ type: "session.keep_alive" }), 45000);
  }

  _openWs(url) {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(secureWsUrl(url)); this.ws = ws; // LiveAvatar session socket, forced to wss
      const timer = setTimeout(() => reject(new Error("LiveAvatar WebSocket timeout")), 15000);
      ws.onmessage = (e) => {
        let ev = {}; try { ev = JSON.parse(e.data); } catch (err) { return; }
        if (ev.type === "session.state_updated") {
          if (ev.state === "connected") { this.ready = true; clearTimeout(timer); resolve(); }
          if (ev.state === "disconnected" && !this.closed) this.onError?.("Koneksi avatar terputus");
        } else if (ev.type === "agent.state_updated") this.onState?.(ev.new_state);
        else if (ev.type === "error") this.onError?.(ev.error?.message || "LiveAvatar error");
      };
      ws.onerror = () => { clearTimeout(timer); reject(new Error("LiveAvatar WebSocket gagal")); };
      ws.onclose = () => { this.ready = false; };
    });
  }

  async _joinRoom(url, token) {
    const room = new Room({ adaptiveStream: false, dynacast: false }); this.room = room;
    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === Track.Kind.Video) this.onVideoTrack?.(track);
      if (track.kind === Track.Kind.Audio) this.onAudioTrack?.(track);
    });
    // connection lifecycle → the hook pauses the countdown/billing while the room is not connected
    room.on(RoomEvent.Reconnecting, () => this.onConnection?.("reconnecting"));
    room.on(RoomEvent.Reconnected, () => this.onConnection?.("connected"));
    room.on(RoomEvent.Disconnected, (reason) => { this.onConnection?.("disconnected", reason); if (!this.closed) this.onError?.("Ruang video avatar terputus"); });
    await room.connect(url, token, { autoSubscribe: true });
    this.onConnection?.("connected");
    room.remoteParticipants.forEach((p) => p.trackPublications.forEach((pub) => { if (pub.track) { if (pub.track.kind === Track.Kind.Video) this.onVideoTrack?.(pub.track); if (pub.track.kind === Track.Kind.Audio) this.onAudioTrack?.(pub.track); } }));
  }

  // LiveAvatar starts rendering once an "agent" participant is present in the room — we hold that seat from the browser.
  async _joinAsAgent(url, token) {
    if (!token) return;
    try { const r = new Room({ adaptiveStream: false, dynacast: false }); this.agentRoom = r; await r.connect(url, token, { autoSubscribe: false }); } catch (e) { console.warn("[avatar] agent seat failed", e?.message); }
  }

  // Capture the assistant's WebRTC audio as PCM16 @ 24 kHz; chunks are only forwarded between speakStart() and speakEnd().
  attachAudio(stream) {
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      this.ac = new AC({ sampleRate: 24000 });
      this.src = this.ac.createMediaStreamSource(stream);
      this.proc = this.ac.createScriptProcessor(4096, 1, 1);
      this.proc.onaudioprocess = (e) => {
        if (!this.forwarding) return;
        const f32 = e.inputBuffer.getChannelData(0);
        const i16 = new Int16Array(f32.length);
        for (let i = 0; i < f32.length; i++) { const v = Math.max(-1, Math.min(1, f32[i])); i16[i] = v < 0 ? v * 0x8000 : v * 0x7fff; }
        this.pending.push(i16);
        if (this.pending.reduce((n, c) => n + c.length, 0) >= 12000) this._flush(); // ~0.5 s chunks
      };
      this.src.connect(this.proc); this.proc.connect(this.ac.destination); // destination keeps the node alive; gain is silent on our side
      if (this.ac.state === "suspended") this.ac.resume().catch(() => {});
    } catch (e) { this.onError?.("Tidak bisa menangkap audio asisten untuk avatar"); }
  }

  _flush() {
    if (!this.pending.length) return;
    const total = this.pending.reduce((n, c) => n + c.length, 0);
    const out = new Int16Array(total); let o = 0; this.pending.forEach((c) => { out.set(c, o); o += c.length; }); this.pending = [];
    if (!this.utterance) this.utterance = uuid();
    this._send({ type: "agent.speak", event_id: this.utterance, audio: b64(out) });
  }

  speakStart() { this.pending = []; this.utterance = null; this.forwarding = true; }
  speakEnd() { this.forwarding = false; this._flush(); if (this.utterance) this._send({ type: "agent.speak_end" }); this.utterance = null; }
  interrupt() { this.forwarding = false; this.pending = []; this.utterance = null; this._send({ type: "agent.interrupt" }); }
  listening(on) { this._send({ type: on ? "agent.start_listening" : "agent.stop_listening" }); }
  _send(ev) { try { if (this.ready && this.ws?.readyState === 1) this.ws.send(JSON.stringify(ev)); } catch (e) {} }

  stop() {
    this.closed = true; this.forwarding = false;
    if (this.keep) clearInterval(this.keep);
    try { this.proc?.disconnect(); this.src?.disconnect(); this.ac?.close(); } catch (e) {}
    try { this.ws?.close(); } catch (e) {}
    try { this.room?.disconnect(); } catch (e) {}
    try { this.agentRoom?.disconnect(); } catch (e) {}
  }
}
