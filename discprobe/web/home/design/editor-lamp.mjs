// The lamp view's scheduling, on the page's side; the light itself is lamp-optics.mjs, run in lamp-worker.mjs.
// As the design tool DIS does it (docs/goals/dis-editor-study/REPORT.md 2.5): the work's coverage is computed once
// per revision in the worker; while the pose moves, quick frames (a few hundred pixels, one sample each) follow the
// hand; once it has stood still for `settle` ms, one fine frame at screen size replaces them. Only the newest request
// counts: the worker drops a render that a newer one supersedes, and frames of an older revision are thrown away.
// Until the first frame of a pose arrives the last frame stays up, so the disc never goes blank while dragging.
export const DRAG_SIZE = 384;            // px of a frame while the pose moves
export const FINE_SAMPLES = 2000;        // samples across the disc a still frame averages (simulate.FINE_SAMPLES)
export const MAX_SAMPLES = 6e6;          // per frame: about a third of a second in the worker

export function target(screen, interacting) {
  screen = Math.max(200, Math.min(2048, Math.round(screen)));
  if (interacting) return { size: Math.min(screen, DRAG_SIZE), k: 1, n: 512 };
  const k = Math.max(1, Math.min(Math.ceil(FINE_SAMPLES / screen), Math.floor(Math.sqrt(MAX_SAMPLES) / screen)));
  return { size: screen, k, n: screen > 1100 ? 2048 : 1024 };
}

export class LampPreview {
  constructor({ onChange = () => {}, worker = () => new Worker(new URL("./lamp-worker.mjs", import.meta.url), { type: "module" }),
    bitmap = image => createImageBitmap(image), settle = 160, now = () => performance.now() } = {}) {
    Object.assign(this, { onChange, makeWorker: worker, bitmap, settle, now });
    this.phase = "idle"; this.cache = new Map(); this.id = 0; this.shown = null; this.stats = [];
  }
  start() {
    if (this.worker) return;
    this.worker = this.makeWorker();
    this.worker.onmessage = ({ data }) => this.message(data);
    this.worker.onerror = event => this.fail(event.message || "Lamp worker failed");
  }
  // rev: the work's revision; document(): the work (called once per revision); pose: { camera, flash, rotate,
  // delta_scale }; screen: px across the disc on screen. Returns the frame to draw (an ImageBitmap of the whole
  // 120 mm square) or null while there is none yet.
  view({ rev, document, pose, screen, paper = false, exposure = 0 }) {
    if (this.phase === "error") return this.shown?.image ?? null;
    this.start();
    const now = this.now();
    if (rev !== this.rev) {
      this.rev = rev; this.docSent = null; this.sentKey = null;
      for (const f of this.cache.values()) if (f !== this.shown) f.image.close?.();
      this.cache.clear();      // the last frame stays up until the new work's first one arrives
      this.post({ type: "doc", rev, document: document(), n: 0 });
    }
    const poseKey = JSON.stringify(pose), moveKey = poseKey + exposure;
    if (moveKey !== this.moveKey) { this.moveKey = moveKey; this.moved = now; }
    const interacting = now - (this.moved ?? -1e9) < this.settle;
    const quick = interacting || !this.shown || this.shown.rev !== rev, t = target(screen, quick), key = JSON.stringify([rev, poseKey, t.size, t.k, t.n, paper, exposure]);
    // a still frame of this very pose, even mid-drag (back to where the hand was), beats any quick one
    const still = target(screen, false), done = this.cache.get(key) ?? this.cache.get(JSON.stringify([rev, poseKey, still.size, still.k, still.n, paper, exposure]));
    if (done) { this.cache.delete(done.key); this.cache.set(done.key, done); this.shown = done; this.phase = "ready"; this.sentKey = null; return done.image; }
    if (key !== this.sentKey) {
      this.sentKey = key;
      this.request({ type: "render", id: ++this.id, rev, pose, paper, exposure, ...t, fine: !quick });
    }
    clearTimeout(this.timer);
    if (interacting) this.timer = setTimeout(() => this.onChange(), this.settle - (now - this.moved) + 5);
    this.phase = this.shown ? "refining" : "waiting";
    return this.shown?.image ?? null;
  }
  // One render in the worker at a time, so it never works through a backlog of poses already left behind: the
  // newest request waits for the one in progress, replacing any request that was waiting. A still frame in progress
  // is not waited for: the worker stops it at its next band when a newer request arrives.
  request(message) {
    if (this.inflight && !this.inflight.fine) { this.queued = message; return; }
    this.queued = null; this.inflight = message;
    this.worker.postMessage(message);
  }
  post(message) { this.worker.postMessage(message); }
  settled(id) {
    if (this.inflight && id >= this.inflight.id) this.inflight = null;
    if (!this.inflight && this.queued && this.worker) this.request(this.queued);
  }
  async message(data) {
    if (data.type === "error") { if (data.rev === this.rev || data.rev === undefined) this.fail(data.error); return; }
    if (data.type === "doc") { this.composeMs = data.ms; return; }
    if (data.type === "dropped") { this.settled(data.id); return; }
    if (data.type !== "frame") return;
    this.settled(data.id);
    if (data.rev !== this.rev) return;
    const key = JSON.stringify([data.rev, JSON.stringify(data.pose), data.size, data.k, data.n, data.paper ?? false, data.exposure ?? 0]);
    const image = await this.bitmap(data.image);
    if (data.rev !== this.rev) { image.close?.(); return; }
    const frame = { image, key, rev: data.rev, size: data.size, k: data.k, ms: data.ms };
    this.stats.push({ rev: data.rev, size: data.size, k: data.k, fine: data.fine, ms: Math.round(data.ms), at: Math.round(this.now()) });
    if (this.stats.length > 200) this.stats.shift();
    // a newer frame is already up: keep it (frames can only arrive in order, but a bitmap decode may not)
    if (this.shown && this.shown.id > data.id) { image.close?.(); return; }
    frame.id = data.id;
    const old = this.shown;
    this.shown = frame;
    if (old && ![...this.cache.values()].includes(old)) old.image.close?.();
    if (data.fine) {                      // only still frames are kept: coming back to a pose shows it at once
      this.cache.set(key, frame);
      while (this.cache.size > 6) { const [k0, old] = this.cache.entries().next().value; this.cache.delete(k0); if (old !== this.shown) old.image.close?.(); }
    }
    this.onChange();
  }
  fail(error) { this.phase = "error"; this.error = String(error); this.worker?.terminate(); this.worker = null; this.inflight = this.queued = null; this.onChange(); }
  // leaving the lamp view: nothing more is rendered; the cache stays for coming back
  pause() { clearTimeout(this.timer); this.sentKey = null; this.queued = null; if (this.phase !== "error") this.phase = "paused"; }
  retry() { this.worker?.terminate(); this.worker = null; this.inflight = this.queued = null; this.error = null; this.phase = "idle"; this.rev = undefined; this.onChange(); }
  dispose() { this.pause(); this.worker?.terminate(); this.worker = null; this.inflight = null; for (const f of this.cache.values()) f.image.close?.(); this.cache.clear(); this.shown = null; this.rev = undefined; }
}
