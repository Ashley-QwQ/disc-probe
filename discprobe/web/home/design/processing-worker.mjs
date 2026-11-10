import { processRGBA, renderOutput } from "./processing.mjs";

self.onmessage = ({ data: job }) => {
  try {
    const { adjustments, output } = job;
    if (job.kind === "preview") {
      const out = renderOutput(processRGBA(job.image, adjustments, job.context), output);
      self.postMessage({ image: out }, [out.data.buffer]);
      return;
    }
    const GRID = 6000, GRID_MM = 120, ppm = GRID / GRID_MM;
    const out = renderOutput(processRGBA(job.image, adjustments, { previewScale: 1 }), output);
    const { r0, rMax } = job, lo = r0 * r0, hi = rMax * rMax;
    const d = out.data, bits = new Uint8Array(GRID * GRID / 8);
    let dark = 0;
    for (let y = 0; y < GRID; y++) {
      const yy = (y + 0.5) / ppm - GRID_MM / 2;
      for (let x = 0; x < GRID; x++) {
        const xx = (x + 0.5) / ppm - GRID_MM / 2, r2 = xx * xx + yy * yy, i = y * GRID + x;
        if (r2 < lo || r2 > hi || d[i * 4] >= 128) continue;
        bits[i >> 3] |= 0x80 >> (i & 7);
        dark++;
      }
    }
    self.postMessage({ bits, rMax: Math.round(rMax * 10) / 10, darkShare: dark / (Math.PI * (hi - lo) * ppm * ppm) }, [bits.buffer]);
  } catch (error) {
    self.postMessage({ error: { name: error.name, message: error.message } });
  }
};
