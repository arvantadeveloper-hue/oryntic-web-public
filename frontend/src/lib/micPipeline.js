import { RnnoiseWorkletNode, loadRnnoise } from "@sapphi-red/web-noise-suppressor";
import { api } from "./api";

export const SENSITIVITIES = ["low", "medium", "high"];
export const SENS_LABEL = { low: "Rendah", medium: "Sedang", high: "Tinggi" };
export const SENS_HINT = {
  low: "Disarankan — tahan bising, asisten tidak terpotong oleh suara latar.",
  medium: "Seimbang — suara Anda lolos, obrolan orang jauh diabaikan.",
  high: "Peka — untuk ruangan sunyi atau suara pelan.",
};
export const BARGE_CONFIRM_MS = 700; // sustained voice needed before we treat it as a real interruption
const PREF_KEY = "aivora_mic_prefs";

export function loadMicPrefs(user) {
  try { const l = JSON.parse(localStorage.getItem(PREF_KEY) || "null"); if (l?.sensitivity) return l; } catch (e) {}
  const s = user?.settings || {};
  return { sensitivity: s.mic_sensitivity || "low", noise: s.noise_suppression !== false };
}

export function saveMicPrefs(p) {
  localStorage.setItem(PREF_KEY, JSON.stringify(p));
  api.put("/auth/settings", { mic_sensitivity: p.sensitivity, noise_suppression: p.noise }).catch(() => {});
}

// mic → [RNNoise] → adaptive gate → processed MediaStream (what we send to the assistant)
export class MicPipeline {
  constructor(prefs) {
    this.prefs = { ...prefs };
    this.meter = { level: 0, floor: 0, threshold: 0, open: false };
    this.openedAt = 0; this.raw = null; this.stream = null; this.ctx = null; this.src = null; this.rnn = null; this.gate = null; this.dest = null;
    this.listeners = new Set(); this.ready = false;
  }

  async start() {
    this.raw = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } });
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      this.ctx = new AC({ sampleRate: 48000 });
      await this.ctx.resume();
      if (!this.ctx.audioWorklet) throw new Error("no worklet");
      this.src = this.ctx.createMediaStreamSource(this.raw);
      await this.ctx.audioWorklet.addModule("/audio/gate-worklet.js");
      this.gate = new AudioWorkletNode(this.ctx, "oryntix-gate", { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1] });
      this.gate.port.onmessage = (e) => {
        const m = e.data;
        if (m.open && !this.meter.open) this.openedAt = Date.now();
        this.meter = m;
        this.listeners.forEach((f) => f(m));
      };
      this.gate.port.postMessage({ sensitivity: this.prefs.sensitivity });
      try {
        const [wasm] = await Promise.all([
          loadRnnoise({ url: "/audio/rnnoise.wasm", simdUrl: "/audio/rnnoise_simd.wasm" }),
          this.ctx.audioWorklet.addModule("/audio/rnnoise-worklet.js"),
        ]);
        this.rnn = new RnnoiseWorkletNode(this.ctx, { wasmBinary: wasm, maxChannels: 1 });
      } catch (e) { this.rnn = null; }
      this.dest = this.ctx.createMediaStreamDestination();
      this.gate.connect(this.dest);
      this._wire();
      this.stream = this.dest.stream;
      this.ready = true;
    } catch (e) {
      this.stream = this.raw; // old browser: plain mic
    }
    return this.stream;
  }

  _wire() {
    try { this.src.disconnect(); } catch (e) {}
    try { this.rnn?.disconnect(); } catch (e) {}
    if (this.rnn && this.prefs.noise) { this.src.connect(this.rnn); this.rnn.connect(this.gate); }
    else this.src.connect(this.gate);
  }

  get hasNoise() { return !!this.rnn; }
  setSensitivity(s) { this.prefs.sensitivity = s; this.gate?.port.postMessage({ sensitivity: s }); }
  setNoise(b) { this.prefs.noise = b; if (this.src && this.gate) this._wire(); }
  setMuted(b) { (this.stream || this.raw)?.getAudioTracks().forEach((t) => { t.enabled = !b; }); }
  // how long the gate has been continuously open (ms); Infinity when the gate is unavailable
  openFor() { if (!this.ready) return Infinity; return this.meter.open ? Date.now() - this.openedAt : 0; }
  isOpen() { return !this.ready || this.meter.open; }
  onMeter(f) { this.listeners.add(f); return () => this.listeners.delete(f); }

  stop() {
    this.listeners.clear();
    try { this.raw?.getTracks().forEach((t) => t.stop()); } catch (e) {}
    try { this.rnn?.destroy?.(); } catch (e) {}
    try { this.ctx?.close(); } catch (e) {}
  }
}
