// GPT-Live (/v1/live/sessions) speaks a different data-channel protocol than the Realtime API the call UIs were built on.
// This bridge translates both ways so RealtimeCall/RealtimeMeeting keep working unchanged:
//   out: Realtime client events  → Live commands (append context/instructions, backend tool results, session.close)
//   in : Live server events      → Realtime-like events (transcripts grouped into turns, speaking state, function calls)
export const isLiveModel = (m) => (m || "").startsWith("gpt-live");

const MAX_APPEND = 1800; // ≈ the 500-token limit of one *.append

export class LiveBridge {
  constructor({ send, emit }) {
    this.raw = send; this.emit = emit;
    this.ready = false; this.queue = []; this.n = 0;
    this.inBuf = ""; this.outBuf = ""; this.inTimer = null; this.outTimer = null;
    this.userSpeaking = false; this.speaking = false; this.closed = false; this.lastToolAt = 0;
  }

  _id(p) { return `${p}_${++this.n}_${Date.now().toString(36)}`; }
  _raw(ev) { if (this.ready) this.raw(ev); else this.queue.push(ev); }
  _append(type, content) { this._raw({ type, event_id: this._id("ctx"), delegation_id: null, content: content.slice(0, MAX_APPEND) }); }

  // ---------- outgoing ----------
  send(ev) {
    switch (ev.type) {
      case "conversation.item.create": {
        const it = ev.item || {};
        if (it.type === "function_call_output") {
          this._raw({ type: "response.item.create", event_id: this._id("tool"), item: { type: "function_call_output", call_id: it.call_id, output: it.output } });
          this._raw({ type: "response.create", event_id: this._id("cont") }); // the backend continues and the voice relays its result
          this.lastToolAt = Date.now();
          return;
        }
        if (it.type !== "message") return;
        const parts = it.content || [];
        if (parts.some((c) => c.type === "input_image")) { // vision goes to the delegated backend model
          this._raw({ type: "response.item.create", event_id: this._id("img"), item: { type: "message", role: "user", content: parts.map((c) => (c.type === "input_image" ? { type: "input_image", image_url: c.image_url, detail: c.detail || "low" } : { type: "input_text", text: c.text || "" })) } });
          this._raw({ type: "response.create", event_id: this._id("cont") });
          return;
        }
        const text = parts.map((c) => c.text || "").join(" ").trim();
        if (text) this._append(/^\[System/i.test(text) ? "session.instructions.append" : "session.thinking.append", text);
        return;
      }
      case "response.create": {
        if (Date.now() - this.lastToolAt < 600) return; // follow-up to a tool result: the backend continuation already makes the voice speak
        const ins = ev.response?.instructions;
        // GPT-Live only speaks unprompted when told so explicitly ("Immediately ...")
        this._append("session.instructions.append", ins ? `Immediately speak now. ${ins}` : "Immediately speak now, before the caller says anything: deliver the opening described in your instructions in 2-3 short spoken sentences, then pause and listen.");
        return;
      }
      case "response.cancel": case "output_audio_buffer.clear": case "conversation.item.delete": case "session.update":
        return; // full duplex + managed context: nothing to do
      default:
        this._raw(ev);
    }
  }

  close() { if (!this.closed) { this.closed = true; this.raw({ type: "session.close" }); } }

  // ---------- incoming ----------
  onMessage(ev) {
    switch (ev.type) {
      case "session.started":
        this.ready = true; this.queue.splice(0).forEach((q) => this.raw(q));
        this.emit({ type: "session.created", session: ev.session });
        return;
      case "session.input_transcript.delta":
        if (!this.userSpeaking) { this.userSpeaking = true; this.emit({ type: "input_audio_buffer.speech_started" }); }
        this.inBuf += ev.delta || "";
        clearTimeout(this.inTimer); this.inTimer = setTimeout(() => this._flushIn(), 900);
        return;
      case "session.output_transcript.delta":
        if (!this.speaking) { this.speaking = true; this.emit({ type: "response.created", response: {} }); this.emit({ type: "output_audio_buffer.started" }); }
        this.outBuf += ev.delta || "";
        this.emit({ type: "response.output_audio_transcript.delta", delta: ev.delta || "" });
        clearTimeout(this.outTimer); this.outTimer = setTimeout(() => this._flushOut(), 1800);
        return;
      case "response.event": {
        const e = ev.event || {};
        if (e.type === "response.output_item.done" && e.item?.type === "function_call") this.emit({ type: "response.function_call_arguments.done", name: e.item.name, call_id: e.item.call_id, arguments: e.item.arguments || "{}", delegation_id: ev.delegation_id });
        else if (e.type === "response.completed" && e.response?.usage) this.emit({ type: "live.backend_usage", usage: e.response.usage });
        return;
      }
      case "session.closed":
        this._flushIn(); this._flushOut(); this.closed = true;
        this.emit({ type: "live.closed", reason: ev.reason, usage: ev.usage });
        return;
      case "error":
        this.emit(ev);
        return;
      default: // acks (*.appended, session.updated), session.usage.updated, session.delegation.created
    }
  }

  _flushIn() {
    clearTimeout(this.inTimer); this.inTimer = null;
    if (!this.userSpeaking) return;
    this.userSpeaking = false;
    const t = this.inBuf.trim(); this.inBuf = "";
    this.emit({ type: "input_audio_buffer.speech_stopped" });
    if (t) this.emit({ type: "conversation.item.input_audio_transcription.completed", transcript: t });
  }

  _flushOut() {
    clearTimeout(this.outTimer); this.outTimer = null;
    if (!this.speaking) return;
    this.speaking = false;
    const t = this.outBuf.trim(); this.outBuf = "";
    this.emit({ type: "response.output_audio_transcript.done", transcript: t });
    this.emit({ type: "output_audio_buffer.stopped" });
    this.emit({ type: "response.done", response: {} });
  }
}
