// node tests/lamp_runner.mjs job.json out.bin: renders the lamp view with design/lamp-optics.mjs.
// job: { labels: base64 of n*n uint8 (row 0 at the top), n, share?: base64 of n*n float32 (NaN = not dithered),
//        materials, pose, size, k, annulus } -> out: size*size*4 RGBA bytes; prints {level, ms} as JSON.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { loadTables, coverageFrom, render } from "../discprobe/web/home/design/lamp-optics.mjs";

const design = new URL("../discprobe/web/home/design/", import.meta.url);
const T = loadTables(JSON.parse(readFileSync(fileURLToPath(new URL("lamp-a3v3.json", design)), "utf8")),
  readFileSync(fileURLToPath(new URL("lamp-a3v3.bin", design))).buffer.slice(0));
const job = JSON.parse(readFileSync(process.argv[2], "utf8"));
const labels = new Uint8Array(Buffer.from(job.labels, "base64"));
const share = job.share ? new Float32Array(new Uint8Array(Buffer.from(job.share, "base64")).buffer) : null;
const cov = coverageFrom(labels, share, job.n, job.materials);
const t = performance.now();
const { rgba, level, unknown } = render(T, cov, job.materials, job.pose, { size: job.size, k: job.k, annulus: job.annulus });
const ms = performance.now() - t;
writeFileSync(process.argv[3], rgba);
console.log(JSON.stringify({ level, ms, unknown }));
