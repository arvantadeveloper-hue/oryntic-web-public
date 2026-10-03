import { api, WS_BASE, getToken } from "./api";

// Human ↔ human audio: WebRTC mesh signaled over the conversation WebSocket (server relays {type:"rtc"} frames).
// ICE servers come from GET /api/rtc/ice-servers (Metered TURN when configured, STUN otherwise).
export class PeerMesh {
  constructor({ cid, myId, localStream, onPeers, onRemoteStream, onStatus }) {
    this.cid = cid; this.myId = myId; this.localStream = localStream;
    this.onPeers = onPeers || (() => {}); this.onRemoteStream = onRemoteStream || (() => {}); this.onStatus = onStatus || (() => {});
    this.peers = {}; // id -> { pc, name, stream, state }
    this.ws = null; this.ice = [{ urls: "stun:stun.l.google.com:19302" }]; this.closed = false; this.turn = false;
  }

  async start() {
    try { const r = await api.get("/rtc/ice-servers"); this.ice = r.data.iceServers || this.ice; this.turn = !!r.data.turn; } catch (e) {}
    this.ws = new WebSocket(`${WS_BASE}/ws/${this.cid}?token=${getToken()}`);
    this.ws.onopen = () => this._send({ kind: "join" });
    this.ws.onmessage = (e) => { try { const m = JSON.parse(e.data); if (m.type === "rtc" && m.from && m.from !== this.myId) this._handle(m); } catch (err) {} };
    this.ws.onclose = () => { if (!this.closed) this.onStatus("signaling-closed"); };
    return this;
  }

  _send(m) { if (this.ws?.readyState === 1) this.ws.send(JSON.stringify({ type: "rtc", ...m })); }

  _emit() { this.onPeers(Object.entries(this.peers).map(([id, p]) => ({ id, name: p.name, state: p.state }))); }

  _peer(id, name) {
    if (this.peers[id]) { if (name) this.peers[id].name = name; return this.peers[id]; }
    const pc = new RTCPeerConnection({ iceServers: this.ice });
    const p = { pc, name: name || "Peserta", stream: null, state: "connecting" }; this.peers[id] = p;
    this.localStream?.getAudioTracks().forEach((t) => pc.addTrack(t, this.localStream));
    pc.onicecandidate = (e) => { if (e.candidate) this._send({ kind: "ice", to: id, candidate: e.candidate }); };
    pc.ontrack = (e) => { p.stream = e.streams[0]; this.onRemoteStream(id, e.streams[0], p.name); };
    pc.onconnectionstatechange = () => { p.state = pc.connectionState; this._emit(); if (["failed", "closed"].includes(pc.connectionState)) this._drop(id); };
    this._emit();
    return p;
  }

  async _handle(m) {
    if (m.to && m.to !== this.myId) return;
    if (m.kind === "join") { // newcomer: existing participants send the offer
      const p = this._peer(m.from, m.from_name);
      const offer = await p.pc.createOffer(); await p.pc.setLocalDescription(offer);
      this._send({ kind: "offer", to: m.from, sdp: p.pc.localDescription });
    } else if (m.kind === "offer") {
      const p = this._peer(m.from, m.from_name);
      await p.pc.setRemoteDescription(m.sdp);
      const ans = await p.pc.createAnswer(); await p.pc.setLocalDescription(ans);
      this._send({ kind: "answer", to: m.from, sdp: p.pc.localDescription });
    } else if (m.kind === "answer") {
      const p = this.peers[m.from]; if (p) await p.pc.setRemoteDescription(m.sdp);
    } else if (m.kind === "ice") {
      const p = this.peers[m.from]; if (p && m.candidate) { try { await p.pc.addIceCandidate(m.candidate); } catch (e) {} }
    } else if (m.kind === "leave") { this._drop(m.from); }
  }

  _drop(id) { const p = this.peers[id]; if (!p) return; try { p.pc.close(); } catch (e) {} delete this.peers[id]; this.onRemoteStream(id, null, p.name); this._emit(); }

  replaceLocalTrack(track) {
    Object.values(this.peers).forEach((p) => p.pc.getSenders().filter((s) => s.track?.kind === "audio").forEach((s) => s.replaceTrack(track)));
  }

  close() {
    this.closed = true; this._send({ kind: "leave" });
    Object.keys(this.peers).forEach((id) => this._drop(id));
    try { this.ws?.close(); } catch (e) {}
  }
}

// Mixes several MediaStreams into one (for feeding the assistant / the peers). Returns { stream, add(stream), remove(stream), close() }.
export function createMixer(ac) {
  const dest = ac.createMediaStreamDestination(); const nodes = new Map();
  return {
    stream: dest.stream,
    add(stream) { if (!stream || nodes.has(stream)) return; const src = ac.createMediaStreamSource(stream); src.connect(dest); nodes.set(stream, src); },
    remove(stream) { const n = nodes.get(stream); if (n) { try { n.disconnect(); } catch (e) {} nodes.delete(stream); } },
    close() { nodes.forEach((n) => { try { n.disconnect(); } catch (e) {} }); nodes.clear(); },
  };
}
