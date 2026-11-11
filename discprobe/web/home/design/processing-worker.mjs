import { processRGBA, renderOutput, renderExportCells } from "./processing.mjs";

// A whole-disc export one band of rows at a time (any cell size): begin, then each band top to bottom
// (every band but the last with one row more, the next band's first), then end for the packed bits.
let band = null;
function exportBand(job) {
  if (job.kind === "export-begin") {
    const { side, r0, rMax, adjustments, output } = job;
    band = { side, ppm: side / 120, lo: r0 * r0, hi: rMax * rMax, rMax, adjustments, output,
      bits: new Uint8Array(side * side / 8), dark: 0, strip: { y0: 0, more: false, carry: null } };
    return { ok: true };
  }
  if (!band) throw new Error("export-begin first");
  if (job.kind === "export-end") {
    const { bits, dark, lo, hi, ppm, rMax } = band;
    band = null;
    return { bits, rMax: Math.round(rMax * 10) / 10, darkShare: dark / (Math.PI * (hi - lo) * ppm * ppm) };
  }
  const { image, y0, rows } = job, { side, ppm, lo, hi, bits, strip } = band;
  if (y0 !== strip.y0 || image.width !== side) throw new Error("bands must come in order, full width");
  strip.more = image.height > rows;
  // Keep the tone pass's byte quantization, but no export needs its histogram or
  // a second RGBA copy of the dithered cells. round(clamp(v)*255) < 128 iff v < .5;
  // NaN (a transparent cell) stays light, just as renderOutput's white pixel did.
  const { values } = renderExportCells(image, band.adjustments, band.output, strip);
  for (let y = 0; y < rows; y++) {
    const yy = (y0 + y + 0.5) / ppm - 60, row = (y0 + y) * side;
    for (let x = 0; x < side; x++) {
      const xx = (x + 0.5) / ppm - 60, r2 = xx * xx + yy * yy, i = y * side + x;
      if (r2 < lo || r2 > hi || !(values[i] < 0.5)) continue;
      const k = row + x;
      bits[k >> 3] |= 0x80 >> (k & 7);
      band.dark++;
    }
  }
  strip.y0 = y0 + rows;
  return { done: strip.y0 };
}

self.onmessage = ({ data: job }) => {
  try {
    if (job.kind?.startsWith("export-")) {
      const result = exportBand(job);
      self.postMessage(result, result.bits ? [result.bits.buffer] : []);
      return;
    }
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
