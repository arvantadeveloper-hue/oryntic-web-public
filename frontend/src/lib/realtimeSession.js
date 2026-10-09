import { API_BASE, getToken, api } from "./api";
import { LiveBridge, isLiveModel } from "./liveBridge";

export const reportUsage = (callId, ev) => {
  if (!callId) return;
  if (ev?.type === "response.done" && ev.response?.usage) api.post(`/realtime/calls/${callId}/usage`, { usage: ev.response.usage }).catch(() => {});
  else if (ev?.type === "live.backend_usage" && ev.usage) api.post(`/realtime/calls/${callId}/usage`, { usage: ev.usage, kind: "backend" }).catch(() => {}); // GPT-Live: delegated brain-model tokens
};

// Same semantic-VAD mapping as backend `vad_config`; interruption is confirmed client-side (see MicPipeline.openFor).
// Platform-wide Conversation Behaviour (set in the back-office): turn detection, eagerness, barge-in threshold, backchannel tolerance.
export const BEHAVIOUR = { turn_detection: "semantic_vad", eagerness: "low", interrupt_response: false, threshold: 0.5, prefix_padding_ms: 300, silence_duration_ms: 500, barge_confirm_ms: 1300, backchannel_resume: true, backchannel_window_ms: 8000 };
export async function loadBehaviour() {
  try { const r = await api.get("/realtime/behaviour"); Object.assign(BEHAVIOUR, r.data || {}); } catch (e) {}
  return BEHAVIOUR;
}
export const bargeMs = () => BEHAVIOUR.barge_confirm_ms || 1300;
export const vadUpdate = (_sensitivity, createResponse) => {
  const b = BEHAVIOUR;
  const td = b.turn_detection === "server_vad"
    ? { type: "server_vad", threshold: b.threshold, prefix_padding_ms: b.prefix_padding_ms, silence_duration_ms: b.silence_duration_ms }
    : { type: "semantic_vad", eagerness: b.eagerness || "low" };
  return { type: "session.update", session: { type: "realtime", audio: { input: { turn_detection: { ...td, create_response: createResponse, interrupt_response: !!b.interrupt_response } } } } };
};

// Safety net: no call UI is mounted → no <audio> element created by a call may keep playing.
export function removeAllCallAudio() {
  document.querySelectorAll("body > audio").forEach((el) => { try { el.pause(); el.srcObject = null; el.remove(); } catch (e) {} });
}

// Short listener sounds ("hmm", "iya", "oke"...) are backchannels, not turns — see REALTIME AVATAR CONVERSATION BEHAVIOR in the persona prompt.
const BACKCHANNEL_WORD = "(h+m+|he+m+|e+m+|m+|he-?e[hm]|ya+|iya+|yoi|oh+|oke+|okey|ok|okay|sip+|hehe+|he+|gitu|baik|betul|bener)";
export const isBackchannel = (t) => { const w = (t || "").toLowerCase().replace(/[^\p{L}\s-]/gu, " ").trim().split(/\s+/).filter(Boolean); return w.length > 0 && w.length <= 3 && w.every((x) => new RegExp(`^${BACKCHANNEL_WORD}$`, "u").test(x)); };
export const RESUME_AFTER_BACKCHANNEL = (t) => `The user only made a short listening sound ("${t}") — it was NOT an interruption. Continue your previous answer exactly from where you stopped, without repeating what you already said and without commenting on the interruption.`;

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
  constructor({ callId, persona, primary, role, stream, onEvent, onError, onStatus, onTrack, sensitivity = "medium", createResponse = false, sendAudio = true, model = "" }) {
    this.callId = callId; this.persona = persona; this.primary = primary; this.role = role; this.stream = stream; this.onTrack = onTrack;
    this.live = isLiveModel(model); this.bridge = null;
    this.onEvent = onEvent; this.onError = onError; this.onStatus = onStatus; this.sensitivity = sensitivity; this.createResponse = createResponse; this.sendAudio = sendAudio;
    this.reconnecting = false; this.reconnectAttempts = 0; this.reconnectTimer = null;
    this.pc = null; this.dc = null; this.audioEl = null; this.ac = null; this.analyser = null; this.buf = null;
    this.level = 0; this.closed = false;
    this.pruner = new ContextPruner(this);
  }

  async connect() {
    await this._openPeer(false);
  }

  _teardownPeer() {
    try { this.ac?.close(); } catch (e) {}
    try { if (this.dc) { this.dc.onmessage = null; this.dc.onopen = null; this.dc.close(); } } catch (e) {}
    try { if (this.pc) { this.pc.onconnectionstatechange = null; this.pc.ontrack = null; this.pc.close(); } } catch (e) {}
    try { if (this.audioEl) { this.audioEl.srcObject = null; this.audioEl.remove(); this.audioEl = null; } } catch (e) {}
    this.analyser = null;
  }

  async _openPeer(resume) {
    const pc = new RTCPeerConnection(); this.pc = pc;
    const audioEl = document.createElement("audio"); audioEl.autoplay = true; document.body.appendChild(audioEl); this.audioEl = audioEl;
    pc.ontrack = (e) => { audioEl.srcObject = e.streams[0]; this._monitor(e.streams[0]); this.onTrack?.(e.streams[0]); };
    if (this.sendAudio && this.stream) this.stream.getTracks().forEach((t) => pc.addTrack(t, this.stream));
    else pc.addTransceiver("audio", { direction: "recvonly" });
    const dc = pc.createDataChannel("oai-events"); this.dc = dc;
    const handle = (ev) => { reportUsage(this.callId, ev); this.pruner.onEvent(ev); this._track(ev); this.onEvent(this, ev); };
    if (this.live) this.bridge = new LiveBridge({ send: (ev) => this._rawSend(ev), emit: handle });
    dc.onmessage = (e) => { try { const ev = JSON.parse(e.data); if (this.bridge) this.bridge.onMessage(ev); else handle(ev); } catch (err) {} };
    pc.onconnectionstatechange = () => { if (this.pc === pc && ["failed", "disconnected", "closed"].includes(pc.connectionState) && !this.closed) this._scheduleReconnect(); };
    const opened = new Promise((resolve) => { dc.onopen = resolve; });
    const offer = await pc.createOffer(); await pc.setLocalDescription(offer);
    const res = await fetch(`${API_BASE}/realtime/calls/${this.callId}/negotiate?sensitivity=${this.sensitivity}`, { method: "POST", headers: { "Content-Type": "application/sdp", Authorization: `Bearer ${getToken()}` }, body: offer.sdp });
    if (!res.ok) { let d = "Negosiasi gagal"; try { d = (await res.json()).detail || d; } catch (e) {} throw new Error(d); }
    const answer = await res.text();
    if (this.closed) return;
    await pc.setRemoteDescription({ type: "answer", sdp: answer });
    await Promise.race([opened, new Promise((_, rej) => setTimeout(() => rej(new Error("timeout data channel")), 15000))]);
    if (resume && !this.closed) {
      this.reconnecting = false; this.reconnectAttempts = 0;
      this.onStatus?.(this, "connected");
      this.send({ type: "conversation.item.create", item: { type: "message", role: "user", content: [{ type: "input_text", text: "[System: the call connection dropped briefly and is now restored. Continue naturally where you left off; do not restart the conversation.]" }] } });
    }
  }

  // Connection dropped → keep the session alive, report "reconnecting", retry with backoff; give up (onError) after ~8 attempts.
  _scheduleReconnect(delay = 1500) {
    if (this.closed || this.reconnectTimer) return;
    if (!this.reconnecting) { this.reconnecting = true; this.reconnectAttempts = 0; this.onStatus?.(this, "reconnecting"); }
    this.reconnectTimer = setTimeout(async () => {
      this.reconnectTimer = null;
      if (this.closed) return;
      if (!navigator.onLine) { this._scheduleReconnect(2000); return; }
      this.reconnectAttempts += 1;
      if (this.reconnectAttempts > 8) { this.reconnecting = false; this.onError?.(this, new Error("connection lost")); return; }
      this._teardownPeer();
      try { await this._openPeer(true); }
      catch (e) { this._scheduleReconnect(Math.min(15000, 1500 * this.reconnectAttempts)); }
    }, delay);
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

  _rawSend(ev) { try { if (this.dc?.readyState === "open") this.dc.send(JSON.stringify(ev)); } catch (e) {} }
  send(ev) { if (this.bridge) this.bridge.send(ev); else this._rawSend(ev); }

  // OpenAI allows one active response per session: queue response.create while one is running, flush on response.done.
  _track(ev) {
    if (ev.type === "response.created") this.active = true;
    else if (ev.type === "response.done") { this.active = false; this._flush(); }
    else if (ev.type === "error" && ev.error?.code === "conversation_already_has_active_response") { this.active = true; if (this._last) this.pending = [this._last, ...(this.pending || [])]; }
  }
  _flush() {
    const next = (this.pending || []).shift();
    if (next) { this._last = next; this.send(next); }
  }
  respond(instructions) {
    const ev = { type: "response.create", ...(instructions ? { response: { instructions } } : {}) };
    if (this.active) { (this.pending = this.pending || []).push(ev); return; }
    this._last = ev; this.send(ev);
  }

  cancel() { this.pending = []; this.send({ type: "response.cancel" }); this.send({ type: "output_audio_buffer.clear" }); }

  inject(text) { this.send({ type: "conversation.item.create", item: { type: "message", role: "user", content: [{ type: "input_text", text }] } }); }

  toolOutput(callId, output) { this.send({ type: "conversation.item.create", item: { type: "function_call_output", call_id: callId, output: typeof output === "string" ? output : JSON.stringify(output) } }); }

  updateVad(sensitivity) {
    this.sensitivity = sensitivity;
    if (this.sendAudio) this.send(vadUpdate(sensitivity, this.createResponse));
  }

  close() {
    if (this.reconnectTimer) { clearTimeout(this.reconnectTimer); this.reconnectTimer = null; }
    this.closed = true;
    if (this.bridge && this.dc?.readyState === "open") { // GPT-Live: ask for a graceful close, tear down shortly after
      this.bridge.close(); const dc = this.dc, pc = this.pc, el = this.audioEl;
      try { this.ac?.close(); } catch (e) {}
      setTimeout(() => { try { dc.close(); } catch (e) {} try { pc?.close(); } catch (e) {} try { if (el) { el.srcObject = null; el.remove(); } } catch (e) {} }, 1500);
      return;
    }
    try { this.ac?.close(); } catch (e) {}
    try { this.dc?.close(); } catch (e) {}
    try { this.pc?.close(); } catch (e) {}
    try { if (this.audioEl) { this.audioEl.srcObject = null; this.audioEl.remove(); } } catch (e) {}
  }
}

// Posts a text card (markdown with links) from the assistant into the call chat panel — so links the user hears about are also clickable.
const postCard = (callId, content) => (callId ? api.post(`/realtime/calls/${callId}/transcript`, { role: "assistant", content, via: "meeting_chat" }).catch(() => {}) : Promise.resolve());

// Voice tools shared by solo calls and meetings: the model asks, we call our API, the result goes back as function_call_output.
export async function runVoiceTool(name, args, cid, callId = null) {
  try {
    if (name === "assign_task") {
      const r = await api.post(`/conversations/${cid}/tasks`, { title: args.title, brief: args.brief, scheduled_at: args.scheduled_at || null, persona_id: args.persona_id || null, team: !!args.team, assignments: Array.isArray(args.assignments) ? args.assignments : null });
      if (r.data?.task_id || r.data?.id) await postCard(callId, `Tugas dibuat: **${args.title}** — [buka di Ruang Kerja](${window.location.origin}/workspace/${r.data.task_id || r.data.id})`);
      return { ok: true, ...r.data, note: "the workspace link was posted to the chat panel" };
    }
    if (name === "search_archive") { const r = await api.post(`/conversations/${cid}/archive-search`, { query: args.query }); return { ok: true, ...r.data, note: "results were posted to the chat panel; ask before restoring" }; }
    if (name === "restore_archive") { const r = await api.post(`/conversations/${cid}/archive-restore`, { archive_id: args.archive_id, confirmed: !!args.confirmed }); return r.data; }
    if (name === "drive_save") {
      const r = await api.post("/integrations/google/save", { title: args.title, content: args.content || undefined, kind: args.kind || "doc", conversation_id: cid });
      await postCard(callId, `Tersimpan di Google Drive: **${r.data.name}** — [buka di Drive](${r.data.link})`);
      return { ok: true, name: r.data.name, link: r.data.link, note: "saved to the user's Google Drive; the clickable link was posted to the chat panel (no need to read the URL aloud)" };
    }
    if (name === "drive_update") {
      const r = await api.post("/integrations/google/update", { file: args.file, text: args.text, mode: args.mode || "append" });
      await postCard(callId, `Dokumen diperbarui: **${r.data.name}** — [buka di Drive](${r.data.webViewLink})`);
      return { ok: true, name: r.data.name, link: r.data.webViewLink, note: "the link was posted to the chat panel" };
    }
    if (name === "drive_link") {
      const r = await api.post("/integrations/google/link", { file: args.file, share: !!args.share });
      await postCard(callId, `Tautan Drive: **${r.data.name}** — [buka di Drive](${r.data.webViewLink})${r.data.shared ? " · dapat dibuka siapa pun yang punya tautan" : ""}`);
      return { ok: true, name: r.data.name, link: r.data.webViewLink, shared: r.data.shared, note: "the clickable link was posted to the chat panel (no need to read the URL aloud)" };
    }
    if (name === "generate_image") {
      const r = await api.post(`/conversations/${cid}/voice-image`, { prompt: args.prompt, edit_previous: !!args.edit_previous, aspect_ratio: args.aspect_ratio || "1:1", quality: args.quality || "standar", request: args.request || "" });
      return { ok: true, credits: r.data.credits, edited: r.data.edited, note: "the image is now visible in the chat panel; tell the user it's there and ask if they want changes" };
    }
    if (name === "generate_video") {
      const r = await api.post(`/conversations/${cid}/voice-video`, { prompt: args.prompt, duration: args.duration || 5, aspect_ratio: args.aspect_ratio || "16:9", from_image: !!args.from_image, request: args.request || "" });
      return { ok: true, needs_choice: r.data.needs_choice, options: r.data.options, summary: r.data.summary, note: r.data.needs_choice ? "a card to pick Seedance 2.0 or 2.5 was posted to the chat panel — tell the user the prices briefly and ask them to tap one" : "a notice was posted to the chat panel — explain it briefly" };
    }
    if (name === "search_workspace") { const r = await api.post(`/conversations/${cid}/workspace-search`, { query: args.query }); return { ok: true, ...r.data, note: "links were posted to the chat panel" }; }
    if (name === "web_search") {
      const r = await api.post(`/realtime/calls/${callId}/web-search`, { query: args.query });
      return { ok: true, answer: r.data.answer, sources: (r.data.sources || []).map((s) => s.title), note: "answer briefly in speech and say the source name(s) aloud; the clickable links are already in the chat panel" };
    }
    if (name === "run_code") {
      const r = await api.post(`/realtime/calls/${callId}/run-code`, { task: args.task });
      return { ok: true, result: r.data.answer, note: "read the result back naturally in speech (round long decimals), mention you calculated it; the full result card is already in the chat panel" };
    }
    if (name === "add_calendar_event") {
      const mode = args.remind_mode === "none" ? null : (args.remind_mode || "call");
      const offsets = mode ? ((args.remind_offsets || []).filter((n) => n > 0).length ? args.remind_offsets.filter((n) => n > 0) : [30]) : [];
      const r = await api.post("/events", { title: args.title, start_at: args.start_at, notes: args.notes || "", remind_mode: mode, remind_offsets: offsets, repeat: ["daily", "weekly", "monthly"].includes(args.repeat) ? args.repeat : "none", conversation_id: cid });
      return { ok: true, event: { title: r.data.title, start_at: r.data.start_at, remind: r.data.remind }, note: "confirm briefly: title, day & time, and how/when they will be reminded; the card is already in the chat panel" };
    }
    const gitProv = name.startsWith("gitlab_") ? "gitlab" : "github";
    const gitLabel = gitProv === "gitlab" ? "GitLab" : "GitHub";
    if (name === "github_repos" || name === "gitlab_repos") {
      const r = await api.get(`/integrations/${gitProv}/repos`, { params: { q: args.query || "" } });
      const items = r.data.items || [];
      if (items.length) await postCard(callId, `Repositori ${gitLabel}:\n` + items.slice(0, 15).map((x) => `- [${x.full_name}](${x.url})${x.private ? " 🔒" : ""}`).join("\n"));
      return { ok: true, count: items.length, repos: items.slice(0, 30).map((x) => ({ full_name: x.full_name, description: x.description, default_branch: x.default_branch, language: x.language })), note: "links were posted to the chat panel" };
    }
    if (name === "github_read" || name === "gitlab_read") {
      const r = await api.post(args.path ? `/integrations/${gitProv}/read` : `/integrations/${gitProv}/tree`, { repo: args.repo, path: args.path || "" });
      return { ok: true, ...r.data };
    }
    if (name === "github_issues" || name === "gitlab_issues") { const r = await api.post(`/integrations/${gitProv}/issues`, { repo: args.repo, state: args.state || "open" }); return { ok: true, ...r.data }; }
    if (name === "social_publish") {
      const r = await api.post(`/conversations/${cid}/social-publish`, { providers: args.providers || [], caption: args.caption || "", kind: args.kind || "image", app_url: window.location.origin });
      return { ok: true, results: r.data.results.map((x) => ({ provider: x.provider, status: x.status, error: x.error })), note: "a result card with links was posted to the chat panel" };
    }
    if (name === "github_review" || name === "gitlab_review") {
      const r = await api.post(`/conversations/${cid}/git-review`, { provider: gitProv, repo: args.repo, number: args.number || null });
      return { ok: true, number: r.data.number, title: r.data.title, summary: r.data.summary, note: "the full written review was posted to the chat panel — speak only the key points" };
    }
    if (name === "github_pr" || name === "gitlab_pr") {
      const r = await api.post(`/integrations/${gitProv}/pr`, { repo: args.repo, title: args.title, body: args.body || "", changes: args.changes || [] });
      await postCard(callId, `${gitProv === "gitlab" ? "Merge request" : "Pull request"} dibuka: **!${r.data.number} ${r.data.title}** di ${r.data.repo} — [lihat di ${gitLabel}](${r.data.url})`);
      return { ok: true, number: r.data.number, url: r.data.url, branch: r.data.branch, note: "the PR link was posted to the chat panel (no need to read the URL aloud)" };
    }
    if (name === "github_commit" || name === "gitlab_commit") {
      const r = await api.post(`/integrations/${gitProv}/commit`, { repo: args.repo, title: args.title, changes: args.changes || [], branch: args.branch });
      await postCard(callId, `Commit **${r.data.title}** masuk ke branch \`${r.data.branch}\` di ${r.data.repo}${r.data.created_branch ? " (branch baru)" : ""} — [lihat di ${gitLabel}](${r.data.url})`);
      return { ok: true, branch: r.data.branch, files: r.data.files, created_branch: r.data.created_branch, note: "the commit link was posted to the chat panel" };
    }
    if (name === "update_task") {
      const c = await api.get(`/conversations/${cid}/messages?limit=1`);
      const tid = c.data?.conversation?.task_id;
      if (!tid) return { ok: false, error: "no task linked to this conversation" };
      const r = await api.post(`/tasks/${tid}/revise`, { instruction: args.instruction });
      await postCard(callId, `Dokumen direvisi (versi ${r.data.version}) — [buka di Ruang Kerja](${window.location.origin}/workspace/${tid})`);
      return { ok: true, version: r.data.version, summary: r.data.summary };
    }
    return { ok: false, error: `unknown tool ${name}` };
  } catch (e) { return { ok: false, error: e?.response?.data?.detail || e.message }; }
}
