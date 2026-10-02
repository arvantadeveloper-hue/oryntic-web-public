// Adaptive noise gate: passes only audio clearly above the room's noise floor (= the person near the mic).
const PROFILES = {
  low: { margin: 18, attack: 120, hold: 500, floorMin: 0.04 },
  medium: { margin: 12, attack: 80, hold: 400, floorMin: 0.028 },
  high: { margin: 6, attack: 50, hold: 350, floorMin: 0.018 },
};

class OryntixGate extends AudioWorkletProcessor {
  constructor() {
    super();
    this.cfg = PROFILES.medium; this.enabled = true;
    this.floor = 0.005; this.open = false; this.above = 0; this.below = 0; this.gain = 0; this.lastPost = 0;
    this.delay = new Float32Array(Math.ceil(sampleRate * 0.13)); this.wi = 0;
    this.port.onmessage = (e) => {
      const d = e.data || {};
      if (d.sensitivity && PROFILES[d.sensitivity]) this.cfg = PROFILES[d.sensitivity];
      if (typeof d.enabled === "boolean") this.enabled = d.enabled;
    };
  }

  process(inputs, outputs) {
    const inp = inputs[0] && inputs[0][0];
    const out = outputs[0] && outputs[0][0];
    if (!inp || !out) return true;
    let s = 0;
    for (let i = 0; i < inp.length; i++) s += inp[i] * inp[i];
    const rms = Math.sqrt(s / inp.length);
    const ms = (inp.length / sampleRate) * 1000;

    // noise floor: adapts down quickly, up slowly (slower still while the gate is open = user talking)
    if (rms < this.floor) this.floor += (rms - this.floor) * 0.05;
    else this.floor += (rms - this.floor) * (this.open ? 0.00002 : 0.0002);
    this.floor = Math.max(this.floor, 0.0005);
    const thr = Math.max(this.floor * Math.pow(10, this.cfg.margin / 20), this.cfg.floorMin);

    if (rms > thr) { this.above += ms; this.below = 0; if (!this.open && this.above >= this.cfg.attack) this.open = true; }
    else { this.below += ms; this.above = 0; if (this.open && this.below >= this.cfg.hold) this.open = false; }

    const target = (!this.enabled || this.open) ? 1 : 0;
    const dl = Math.round((this.cfg.attack / 1000) * sampleRate); // look-ahead so the first syllable is kept
    const L = this.delay.length;
    for (let i = 0; i < inp.length; i++) {
      this.delay[this.wi] = inp[i];
      const ri = (this.wi - dl + L) % L;
      this.gain += (target - this.gain) * 0.002;
      out[i] = this.delay[ri] * this.gain;
      this.wi = (this.wi + 1) % L;
    }
    if (currentTime - this.lastPost > 0.05) {
      this.lastPost = currentTime;
      this.port.postMessage({ level: rms, floor: this.floor, threshold: thr, open: this.open });
    }
    return true;
  }
}

registerProcessor("oryntix-gate", OryntixGate);
