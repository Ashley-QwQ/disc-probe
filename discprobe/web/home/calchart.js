/**
 * Calibration engineering drawings: measured offsets, ±sigma bars, bounded fit
 * and hatched uncertainty. Follows the designer's review, 标定页 §5, and
 * mockups/标定 · 测几何（重画示例）-html.zip, CalMeasure.dc.html (right paper).
 */
const LEFT = 64, RIGHT = 544, TOP = 28, BOTTOM = 174;
const MID = (TOP + BOTTOM) / 2, HALF = (BOTTOM - TOP) / 2;
const RADII = [24, 30, 40, 50, 58];
const X = r => LEFT + (r - 24) / 34 * (RIGHT - LEFT);
const n = value => String(Number(value.toFixed(4)));
// Only fragment names vary between renders; no DOM, clock or input mutation.
let nextId = 0;

function validPoint(p) {
  return p && [p.r, p.d, p.s].every(Number.isFinite) && p.s >= 0 &&
    Number.isFinite(Math.abs(p.d) + p.s);
}

function niceRange(points) {
  const extent = points.reduce((v, p) => Math.max(v, Math.abs(p.d) + p.s), .3);
  const raw = Math.min(Number.MAX_VALUE, extent / (1 / 1.15));
  const step = 10 ** Math.floor(Math.log10(raw)) / 10;
  return Math.min(Number.MAX_VALUE, Math.ceil(raw / step - 1e-10) * step);
}

function fit(points, range) {
  if (points.length < 2 || points[0].r === points.at(-1).r) return null;
  // Centre and scale both coordinates to keep the least-squares sums stable.
  // Normalising all 1/s² weights by the same factor preserves the solution.
  const floor = Math.min(...points.map(p => Math.max(.01, p.s)));
  const rows = points.map(p => ({
    x: (p.r - 24) / 34, y: p.d / range,
    w: (floor / Math.max(.01, p.s)) ** 2,
  }));
  const sum = rows.reduce((s, p) => s + p.w, 0);
  const mx = rows.reduce((s, p) => s + p.w * p.x, 0) / sum;
  const my = rows.reduce((s, p) => s + p.w * p.y, 0) / sum;
  const variance = rows.reduce((s, p) => s + p.w * (p.x - mx) ** 2, 0);
  if (!(variance > 0)) return null;
  const slope = rows.reduce((s, p) => s + p.w * (p.x - mx) * (p.y - my), 0) / variance;
  const at = r => my + slope * ((r - 24) / 34 - mx);
  const rms = Math.sqrt(rows.reduce((s, p) => s + p.w *
    (p.y - my - slope * (p.x - mx)) ** 2, 0) / sum);
  const sigmas = points.map(p => p.s / range).sort((a, b) => a - b);
  const mid = Math.floor(sigmas.length / 2);
  const median = sigmas.length % 2 ? sigmas[mid] : (sigmas[mid - 1] + sigmas[mid]) / 2;
  const band = Math.max(rms, median);
  return [at(points[0].r), at(points.at(-1).r), band].every(Number.isFinite)
    ? { at, band } : null;
}

function draw(input, { zh, head = null, unread = false, sectors = null }) {
  const points = input.filter(validPoint).sort((a, b) => a.r - b.r);
  const id = `calchart-${++nextId}`, pattern = `${id}-hatch`, clip = `${id}-clip`, markers = `${id}-markers`;
  const range = niceRange(points), Y = ratio => MID - ratio * HALF;
  const label = zh ? '转角偏差' : 'turn offset';
  const unit = sectors ? (zh ? '位置（扇区）' : 'position (sectors)') : (zh ? '半径 mm' : 'radius mm');
  const description = zh ? '各处转角偏差、正负一倍标准差误差棒与测量范围内的拟合和斜线置信带'
    : 'Turn offsets, plus or minus one sigma error bars, fitted line and hatched uncertainty within the measured span';
  const digits = Math.max(1, -Math.floor(Math.log10(range)) + 1);
  const magnitude = range < 1e6 ? range.toFixed(digits) : range.toExponential(1);
  let svg = `<svg xmlns="http://www.w3.org/2000/svg" class="chart calchart" viewBox="0 0 560 220" width="100%" role="img" aria-label="${description}">
<style>
svg.chart.calchart { display: block; height: auto; color: var(--ink); }
svg.chart.calchart text { fill: var(--ink-3); font-size: 12px; }
svg.chart.calchart .cc-number, svg.chart.calchart .cc-unit { font-family: var(--mono); font-variant-numeric: tabular-nums; }
svg.chart.calchart .cc-axis, svg.chart.calchart .cc-fit, svg.chart.calchart .cc-head { stroke: var(--ink); stroke-width: 1; stroke-opacity: .7; fill: none; }
svg.chart.calchart .cc-tick, svg.chart.calchart .cc-error, svg.chart.calchart .cc-hatch { stroke: var(--ink); stroke-width: .75; stroke-opacity: .4; fill: none; }
svg.chart.calchart .cc-point { stroke: var(--ink); stroke-width: 1.5; fill: none; }
svg.chart.calchart .cc-unread { font-family: inherit; font-size: 14px; }
</style>
<defs><pattern id="${pattern}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><path class="cc-hatch" d="M0 0 V6"/></pattern>
<clipPath id="${clip}"><rect x="${LEFT}" y="${TOP}" width="${RIGHT - LEFT}" height="${BOTTOM - TOP}"/></clipPath>
<clipPath id="${markers}"><rect x="${LEFT - 4}" y="${TOP - 4}" width="${RIGHT - LEFT + 8}" height="${BOTTOM - TOP + 8}"/></clipPath></defs>
<path class="cc-axis" d="M${LEFT} ${TOP} V${BOTTOM} H${RIGHT}"/>
<line class="cc-tick" x1="${LEFT}" x2="${RIGHT}" y1="${MID}" y2="${MID}"/>`;
  for (const [ratio, text] of [[1, `+${magnitude}°`], [0, '0'], [-1, `−${magnitude}°`]]) {
    const y = Y(ratio);
    svg += `<path class="cc-tick" d="M${LEFT - 5} ${n(y)} h5"/><text class="cc-number" x="${LEFT - 9}" y="${n(y + 4)}" text-anchor="end">${text}</text>`;
  }
  for (const r of RADII) {
    const value = sectors ? Math.round(sectors[0] + (sectors[1] - sectors[0]) * (r - 24) / 34) : r;
    svg += `<path class="cc-tick" d="M${n(X(r))} ${BOTTOM} v5"/><text class="cc-number" x="${n(X(r))}" y="194" text-anchor="middle">${value}</text>`;
  }
  svg += `<text x="${LEFT}" y="16">${label}</text><text class="cc-unit" x="${RIGHT}" y="214" text-anchor="end">${unit}</text><g clip-path="url(#${clip})">`;
  const fitted = fit(points, range);
  if (fitted) {
    const first = points[0].r, last = points.at(-1).r;
    const x1 = n(X(first)), x2 = n(X(last));
    const a = fitted.at(first), b = fitted.at(last), band = fitted.band;
    svg += `<polygon class="cc-band" points="${x1},${n(Y(a + band))} ${x2},${n(Y(b + band))} ${x2},${n(Y(b - band))} ${x1},${n(Y(a - band))}" fill="url(#${pattern})"/>
<line class="cc-fit" x1="${x1}" x2="${x2}" y1="${n(Y(a))}" y2="${n(Y(b))}"/>`;
  }
  // The band is plot-clipped; endpoint circles and caps need their full width.
  svg += `</g><g clip-path="url(#${markers})">`;
  for (const p of points) {
    const x = X(p.r), y = Y(p.d / range);
    const top = Y((p.d + p.s) / range), bottom = Y((p.d - p.s) / range);
    // Leave the open marker's centre clear, even where the bars cross the fit.
    const stem = bottom - top > 6 ? `M${n(x)} ${n(top)} V${n(y - 3)} M${n(x)} ${n(y + 3)} V${n(bottom)} ` : '';
    svg += `<path class="cc-error" d="${stem}M${n(x - 3)} ${n(top)} h6 M${n(x - 3)} ${n(bottom)} h6"/><circle class="cc-point" cx="${n(x)}" cy="${n(y)}" r="3"/>`;
  }
  svg += '</g>';
  if (unread && Number.isFinite(head)) {
    const x = X(Math.max(24, Math.min(58, head)));
    // the words only where they fit; a sliver at the edge keeps just the dashed line
    const words = RIGHT - x >= 90 ? `<text class="cc-unread" x="${n((x + RIGHT) / 2)}" y="${MID + 4}" text-anchor="middle">${zh ? '还没读到' : 'not read yet'}</text>` : "";
    svg += `<line class="cc-head" x1="${n(x)}" x2="${n(x)}" y1="${TOP}" y2="${BOTTOM}" stroke-dasharray="3 4"/>${words}`;
  }
  return svg + '</svg>';
}

export function liveChart(points, { head = null, zh = true } = {}) {
  const valid = (Array.isArray(points) ? points : []).filter(validPoint);
  const last = valid.reduce((r, p) => Math.max(r, p.r), 24);
  const at = Number.isFinite(head) ? head : last;
  return draw(valid, { zh, head: at, unread: at < 57 });
}

export function resultChart(measurement, { zh = true } = {}) {
  const points = (Array.isArray(measurement?.points) ? measurement.points : []).filter(p =>
    p && Number.isFinite(p.lba) && validPoint({ r: p.lba, d: p.residual_deg, s: p.sigma_deg }));
  if (!points.length) return '';
  const lbas = points.map(p => p.lba), lo = Math.min(...lbas), hi = Math.max(...lbas);
  const span = measurement.span_mm;
  const hasSpan = Array.isArray(span) && span.length === 2 && span.every(Number.isFinite) &&
    span[0] >= 24 && span[0] <= span[1] && span[1] <= 58;
  const [rlo, rhi] = hasSpan ? span : [24, 58];
  const mapped = points.map(p => {
    const t = hi === lo ? 0 : (p.lba - lo) / (hi - lo);
    // r² = A + B·lba, with the measured LBA endpoints at the span endpoints.
    const r = hasSpan ? Math.sqrt(rlo ** 2 + t * (rhi ** 2 - rlo ** 2)) : 24 + 34 * t;
    return { r, d: p.residual_deg, s: p.sigma_deg };
  });
  const last = Math.max(...mapped.map(p => p.r));
  return draw(mapped, { zh, head: last, unread: Boolean(measurement.stopped) && last < 58,
    sectors: hasSpan ? null : [lo, hi] });
}
