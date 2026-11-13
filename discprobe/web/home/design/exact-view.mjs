// The burn cells themselves, for the part of the disc on screen once the canvas shows a cell as a pixel or more.
// Computed by exact-worker.mjs with the composer the core uses, so what shows is what `compose` writes: picture
// dither included. Older requests are dropped; one worker, one request at a time.
export class ExactView {
  constructor(onChange = () => {}) { this.onChange = onChange; this.phase = "off"; this.key = ""; this.image = null; this.seq = 0; }
  // window: { side, rows: [r0, r1], cols: [c0, c1] } of the burn grid; materials: the document's, for colours
  // document: the work, or a function that makes it (only called when the window or the work changed)
  request(key, document, window, paint) {
    if (key === this.key) return this.image;
    if (typeof document === "function") document = document();
    this.key = key; this.image = null; this.phase = "computing"; this.onChange();
    clearTimeout(this.timer);
    const id = ++this.seq;
    this.timer = setTimeout(() => {
      if (this.busy) { this.worker?.terminate(); this.worker = null; }   // a stale window: drop it, don't queue
      this.busy = true;
      this.worker ??= new Worker(new URL("./exact-worker.mjs", import.meta.url), { type: "module" });
      this.worker.onmessage = ({ data }) => {
        if (data.id !== this.seq) return;
        this.busy = false;
        if (data.error) { this.phase = "error"; this.error = data.error; this.onChange(); return; }
        this.image = { ...window, canvas: paint(data.labels, data.w, data.h) };
        this.phase = "ready"; this.onChange();
      };
      this.worker.postMessage({ id, document, ...window });
    }, 250);
    return null;
  }
  off() {
    if (this.phase === "off") return;
    clearTimeout(this.timer); this.seq++; this.key = ""; this.image = null; this.phase = "off"; this.busy = false;
    this.worker?.terminate(); this.worker = null;            // a 5 µm window can take a while: stop it, not wait
  }
}
