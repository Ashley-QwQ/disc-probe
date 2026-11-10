// Only design extraction and canvas presentation run on the UI thread.
export class SimView {
  constructor(project, changed) {
    this.changed = changed;
    this.project = project;
    this.canvas = document.createElement('canvas');
    this.worker = new Worker(new URL('./worker.mjs', import.meta.url), { type: 'module' });
    this.id = 0; this.key = ''; this.status = 'loading';
    this.worker.onerror = () => { this.status = 'error'; changed(); };
    this.worker.onmessage = ({ data: m }) => {
      if (m.loaded) { this.loaded = true; this.key = ''; this.request(this.pose); return; }
      if (m.id !== this.id) return;
      if (m.error) { this.status = 'error'; changed(); return; }
      this.canvas.width = this.canvas.height = m.size;
      this.canvas.getContext('2d').putImageData(new ImageData(new Uint8ClampedArray(m.buffer), m.size, m.size), 0, 0);
      this.status = m.fine ? 'ready' : 'refining';
      this.ms = m.ms;
      changed();
    };
  }
  request(pose) {
    const key = JSON.stringify(pose);
    if (this.key === key) return;
    this.key = key; this.pose = { ...pose }; this.id++;
    clearTimeout(this.timer);
    if (!this.loaded) {
      if (!this.loading) {
        this.loading = true;
        // ctx.render is synchronous and belongs to the design page. Let the
        // loading label paint first; bitmap readback and classification are in
        // the worker. Honor whatever resolution the project actually returns.
        this.loadTimer = setTimeout(async () => {
          try {
            const bitmap = await createImageBitmap(this.project.render(50));
            if (this.stopped) { bitmap.close(); return; }
            this.worker.postMessage({ type: 'design', bitmap }, [bitmap]);
          } catch { if (!this.stopped) { this.status = 'error'; this.changed(); } }
        }, 30);
      }
      return;
    }
    this.status = 'refining';
    // Coalesce pointer/range events to one request per animation frame.
    if (!this.raf) this.raf = requestAnimationFrame(() => {
      this.raf = 0;
      this.worker.postMessage({ id: this.id, pose: this.pose, size: 160, fine: false });
    });
    this.timer = setTimeout(() => this.worker.postMessage({ id: this.id, pose: this.pose, size: 500, fine: true }), 180);
  }
  stop() { this.stopped = true; clearTimeout(this.loadTimer); clearTimeout(this.timer); cancelAnimationFrame(this.raf); this.worker.terminate(); }
}
