// node tests/lamp_runner.mjs [--document] job.json out.bin: renders the lamp view with design/lamp-optics.mjs.
// job: { labels: base64 of n*n uint8 (row 0 at the top), n, share?: base64 of n*n float32 (NaN = not dithered),
//        materials, pose, size, k, annulus } -> out: size*size*4 RGBA bytes; prints {level, ms} as JSON.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { loadTables, coverageFrom, render } from "../discprobe/web/home/design/lamp-optics.mjs";
import { compose, grid } from "../discprobe/web/home/design/editor-ops.mjs";

const design = new URL("../discprobe/web/home/design/", import.meta.url);
// --document job.json: { document, n, pose, size, k }: the work composed here as the lamp worker does it
const byDocument = process.argv[2] === "--document", args = process.argv.slice(byDocument ? 3 : 2);
const job = JSON.parse(readFileSync(args[0], "utf8"));
const T = job.table
  ? loadTables(job.table.meta, Uint8Array.from(Buffer.from(job.table.xyz, "base64")).buffer)
  : loadTables(JSON.parse(readFileSync(fileURLToPath(new URL("lamp-a3v3.json", design)), "utf8")),
    readFileSync(fileURLToPath(new URL("lamp-a3v3.bin", design))).buffer.slice(0));
let cov;
if (byDocument) {
  const share = new Float32Array(job.n * job.n).fill(NaN);
  const labels = compose(job.document, grid(job.n), { share });
  job.materials = job.document.materials; job.annulus = job.document.annulus_mm;
  cov = coverageFrom(labels, share, job.n, job.materials);
} else {
  const labels = new Uint8Array(Buffer.from(job.labels, "base64"));
  const share = job.share ? new Float32Array(new Uint8Array(Buffer.from(job.share, "base64")).buffer) : null;
  cov = coverageFrom(labels, share, job.n, job.materials);
}
const t = performance.now();
const { rgba, level, unknown, delta } = render(T, cov, job.materials, job.pose, {
  size: job.size, k: job.k, annulus: job.annulus, diffractionOnly: job.diffractionOnly, traceDelta: !!args[2],
});
const ms = performance.now() - t;
writeFileSync(args[1], rgba);
if (delta) writeFileSync(args[2], new Uint8Array(delta.buffer));
console.log(JSON.stringify({ level, ms, unknown }));
