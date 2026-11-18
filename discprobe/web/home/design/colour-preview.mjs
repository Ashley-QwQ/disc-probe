// Only the newest pending view goes to the core. An in-flight composition may finish and be cached there.
export class ColourPreview {
  constructor(onChange) {
    this.onChange = onChange;
    this.phase = 'idle';
  }
  view({rev, document, pose, view = 'lamp', screen, exposure = 0}) {
    const size = Math.max(200, Math.min(800, Math.round(screen / 100) * 100));
    const key = JSON.stringify([rev, pose, view, size, exposure]);
    if (this.key !== key) {
      this.key = key;
      this.next = {key, rev, document, pose, view, size, exposure};
      this.phase = 'waiting';
      clearTimeout(this.timer);
      this.timer = setTimeout(() => this.run(), 180);
    }
    return this.frame?.rev === rev && this.frame.view === view ? this.frame.image : null;
  }
  async run() {
    if (this.running || !this.next) return;
    const {key, rev, document, pose, view, size, exposure} = this.next;
    this.next = null;
    this.running = true;
    try {
      const response = await fetch('/api/editor-preview', {method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({document:document(), pose, view, size, exposure, quality:'draft'})});
      if (!response.ok) throw Error((await response.json().catch(() => ({}))).error ?? response.statusText);
      const image = await createImageBitmap(await response.blob());
      if (key === this.key) {
        this.frame?.image.close();
        this.frame = {image, rev, view};
        this.phase = 'ready';
      } else image.close();
    } catch (error) {
      if (key === this.key) {
        this.error = String(error.message ?? error);
        this.phase = 'error';
      }
    } finally {
      this.running = false;
      this.onChange();
      if (this.next) this.run();
    }
  }
  retry() { if (this.phase === 'error') this.key = null; }
  pause() {
    if (this.phase === 'waiting') this.key = null;
    clearTimeout(this.timer);
    this.next = null;
  }
  dispose() {
    this.pause();this.key=null;this.frame?.image.close();this.frame=null;
  }
}
