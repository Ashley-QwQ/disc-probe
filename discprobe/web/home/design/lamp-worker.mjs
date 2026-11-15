// The lamp view's worker: the work's coverage once per revision (editor-ops.compose at a coarse grid, off the
// page's thread), then any number of renders of it (lamp-optics.mjs) as the pose changes. Messages:
//   { type: "doc", rev, document, n }            -> { type: "doc", rev, n, ms } | { type: "error", rev, error }
//   { type: "render", id, rev, pose, size, k, paper } -> { type: "frame", id, rev, n, size, k, image, level, ms }
// A render is done in bands of rows; between bands the worker reads its messages, and a newer render request makes
// the one in progress stop (its result would be stale). One coverage is kept per grid size, for the latest revision.
import { compose, grid } from "./editor-ops.mjs";
import { loadTables, coverageFrom, LampFrame } from "./lamp-optics.mjs";

let tables = null, doc = null, newest = 0;
const covers = new Map();                 // n -> coverage of doc
const queue = [];
let running = false;

async function load() {
  if (tables) return tables;
  const [meta, bin] = await Promise.all([
    fetch(new URL("./lamp-a3v3.json", import.meta.url)).then(r => { if (!r.ok) throw Error("lamp table"); return r.json(); }),
    fetch(new URL("./lamp-a3v3.bin", import.meta.url)).then(r => { if (!r.ok) throw Error("lamp table"); return r.arrayBuffer(); }),
  ]);
  return (tables = loadTables(meta, bin));
}

function coverage(n) {
  if (!covers.has(n)) {
    const share = new Float32Array(n * n).fill(NaN);
    const labels = compose(doc.document, grid(n), { share });
    covers.set(n, coverageFrom(labels, share, n, doc.document.materials));
  }
  return covers.get(n);
}

// read pending messages between bands; a MessageChannel, since nested setTimeout(0) waits 4 ms each
const channel = new MessageChannel(), waiting = [];
channel.port1.onmessage = () => waiting.shift()?.();
const dropped = job => self.postMessage({ type: "dropped", id: job.id, rev: job.rev });
const yieldNow = () => new Promise(r => { waiting.push(r); channel.port2.postMessage(0); });

async function render(job) {
  const T = await load();
  if (!doc || job.rev !== doc.rev) return dropped(job);     // a newer work is on its way
  const t0 = performance.now(), d = doc.document;
  const cov = coverage(job.n);
  const f = new LampFrame(T, cov, d.materials, job.pose, { size: job.size, k: job.k, annulus: d.annulus_mm, paper: job.paper });
  const band = Math.max(8, Math.floor(160000 / (job.size * job.k * job.k)));
  for (let y = 0; y < job.size; y += band) {
    f.rows(y, Math.min(job.size, y + band));
    if (y + band < job.size && job.k * job.size > 500) { await yieldNow(); if (newest > job.id || queue.some(j => j.type === "doc")) return dropped(job); }
  }
  const rgba = f.finish();
  const image = new ImageData(rgba, job.size, job.size);
  self.postMessage({ type: "frame", id: job.id, rev: job.rev, n: job.n, size: job.size, k: job.k, pose: job.pose, paper: job.paper ?? false, fine: !!job.fine, image,
    level: f.level, unknown: f.unknown, ms: performance.now() - t0 }, [rgba.buffer]);
}

async function pump() {
  if (running) return;
  running = true;
  try {
    while (queue.length) {
      const job = queue.shift();
      try {
        if (job.type === "doc") {
          const t0 = performance.now();
          doc = { rev: job.rev, document: job.document }; covers.clear();
          await load();
          if (job.n) coverage(job.n);
          self.postMessage({ type: "doc", rev: job.rev, n: job.n, ms: performance.now() - t0 });
        } else if (job.type === "render") {
          if (job.id < newest) { dropped(job); continue; }   // superseded while waiting
          await render(job);
        }
      } catch (error) {
        self.postMessage({ type: "error", id: job.id, rev: job.rev, error: String(error?.message ?? error) });
        if (job.type === "render") dropped(job);
      }
    }
  } finally { running = false; }
}

self.onmessage = ({ data }) => {
  if (data.type === "render") newest = Math.max(newest, data.id);
  if (data.type === "doc") for (let i = queue.length - 1; i >= 0; i--) if (queue[i].type === "doc") queue.splice(i, 1);
  queue.push(data);
  pump();
};
