// The canvas's exact view: compose rows of the burn grid off the page's thread (editor-ops.compose, the same code
// as the core's compose). Message: { id, document, side, rows: [r0, r1], cols: [c0, c1] } -> { id, labels, w, h }.
import { compose, grid } from "./editor-ops.mjs";

self.onmessage = ({ data }) => {
  const { id, document, side, rows, cols } = data;
  try {
    const g = grid(side), full = compose(document, g, { rows }), w = cols[1] - cols[0], h = rows[1] - rows[0];
    const labels = new Uint8Array(w * h);
    for (let j = 0; j < h; j++) labels.set(full.subarray(j * side + cols[0], j * side + cols[1]), j * w);
    self.postMessage({ id, labels, w, h }, [labels.buffer]);
  } catch (error) {
    self.postMessage({ id, error: String(error?.message ?? error) });
  }
};
