// The start guide's four-scene diagram, also shown as a still in the reading guide.
const TRACKS = Array.from({ length: 49 }, (_, i) => `M${120 + i * 8} 168v12`).join("");
const RAY_COLOURS = ["#c04a6a", "#d08a3e", "#b9a52f", "#4fa174", "#4a7fd0"];
const esc = value => value.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

export function lightingDiagram(label, picture) {
  const rays = RAY_COLOURS.map((colour, i) => {
    const angle = [52, 42, 32, 22, 12][i] * Math.PI / 180;
    return `<line class="sg-ray" data-i="${i}" x1="378" y1="168" x2="${(378 + 200 * Math.cos(angle)).toFixed(1)}" y2="${(168 - 200 * Math.sin(angle)).toFixed(1)}" stroke="${colour}"/>`;
  }).join("");
  return `<svg class="sg-fig" viewBox="0 0 640 224" role="img" aria-label="${esc(label)}">
    <path class="sg-tracks" d="${TRACKS}"/><path class="sg-surface" d="M112 168H512"/>
    <g class="sg-beamg"><circle class="sg-lamp" cx="64" cy="28" r="9"/><line class="sg-beam" x1="72" y1="34" x2="378" y2="166"/></g>
    <g class="sg-raysg">${rays}</g>
    <g class="sg-eyeg"><path class="sg-eye" d="M572 93q30-26 60 0q-30 26-60 0z"/><circle class="sg-pupil" cx="602" cy="93" r="6"/></g>
    <g class="sg-pic"><rect x="344" y="160" width="68" height="28" rx="2"/><text x="378" y="214" text-anchor="middle">${esc(picture)}</text></g>
  </svg>`;
}
