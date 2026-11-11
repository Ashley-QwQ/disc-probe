// The core's terminal look in the page: its colour codes (SGR) as spans, and its progress line
// (ui.Progress: a turning disc, the stage with a band of the rainbow crossing it, a bar in the disc's
// rainbow with a glint now and then, the percentage whose changed digit flashes, the time left).
// Used by the terminal page (terminal.js) and by the log lying on the floor by the drive (floor-log.js).

// The 16 terminal colours, per look (Campbell for PowerShell, Tango for bash and for the floor).
export const PALETTE = {
  win: ["#0c0c0c", "#c50f1f", "#13a10e", "#c19c00", "#0037da", "#881798", "#3a96dd", "#cccccc",
        "#767676", "#e74856", "#16c60c", "#f9f1a5", "#3b78ff", "#b4009e", "#61d6d6", "#f2f2f2"],
  bash: ["#2e3436", "#cc0000", "#4e9a06", "#c4a000", "#3465a4", "#75507b", "#06989a", "#d3d7cf",
         "#555753", "#ef2929", "#8ae234", "#fce94f", "#729fcf", "#ad7fa8", "#34e2e2", "#eeeeec"],
};

// a line with SGR codes to spans: bold, dim, the 16 colours and 24-bit colour (the core's rainbow)
export function painted(ansi, pal = PALETTE.bash) {
  const frag = document.createDocumentFragment();
  let fg = null, bold = false, dim = false;
  const re = /\x1b\[([0-9;]*)m/g;
  let at = 0, m;
  const put = (text) => {
    if (!text) return;
    const span = document.createElement("span");
    span.textContent = text;
    if (fg) span.style.color = fg;
    if (bold) span.style.fontWeight = "700";
    if (dim) span.style.opacity = ".62";
    frag.append(span);
  };
  while ((m = re.exec(ansi))) {
    put(ansi.slice(at, m.index));
    at = re.lastIndex;
    const c = (m[1] || "0").split(";").map(Number);
    for (let i = 0; i < c.length; i++) {
      const n = c[i];
      if (n === 0) { fg = null; bold = dim = false; }
      else if (n === 1) bold = true;
      else if (n === 2) dim = true;
      else if (n === 22) bold = dim = false;
      else if (n === 39) fg = null;
      else if (n >= 30 && n <= 37) fg = pal[n - 30];
      else if (n >= 90 && n <= 97) fg = pal[n - 82];
      else if (n === 38 && c[i + 1] === 2) { fg = `rgb(${c[i + 2]}, ${c[i + 3]}, ${c[i + 4]})`; i += 4; }
      else if (n === 38 && c[i + 1] === 5) { const k = c[i + 2]; fg = k < 16 ? pal[k] : null; i += 2; }
    }
  }
  put(ansi.slice(at));
  return frag;
}

// The core's colours (ui.py): OKLCH, its rainbow in 48 hue steps (ui._tone), its timings.
export function oklch(l, c, h) {
  const a = c * Math.cos(2 * Math.PI * h), b = c * Math.sin(2 * Math.PI * h);
  const L = (l + .3963377774 * a + .2158037573 * b) ** 3, M = (l - .1055613458 * a - .0638541728 * b) ** 3, S = (l - .0894841775 * a - 1.291485548 * b) ** 3;
  return [4.0767416621 * L - 3.3077115913 * M + .2309699292 * S, -1.2684380046 * L + 2.6097574011 * M - .3413193965 * S, -.0041960863 * L - .7034186147 * M + 1.707614701 * S]
    .map((v) => Math.round(255 * Math.min(1, v <= 0 ? 0 : v < .0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - .055)));
}
export const tone = (pos, lift = 0) => { const h = Math.round((((pos % 1) + 1) % 1) * 48) % 48, lv = 3, lf = Math.round(lift * 2) / 2;
  const [r, g, b] = oklch(.68 + .1 * lf, (.05 + .025 * lv) * (1 - .3 * lf), .08 + h / 48); return `rgb(${r}, ${g}, ${b})`; };
const BAR = 20, CELLS = 4, SPIN = ["◐", "◓", "◑", "◒"], SPIN_S = .12, GLINT_EVERY = 4, GLINT_SWEEP = 1.2, GLINT_REACH = 2,
  SWEEP_S = 1.7, SWEEP_REACH = 4, FLASH_S = .4;

// One progress line drawn into `line`, as the core draws it at a terminal. update(e) takes a progress event
// ({fraction, stage, eta_s}); while `alive()` holds and motion is on, it keeps turning between events.
// reduce(): motion is off (nothing turns or flashes); pal(): the 16 colours (100 % is their green).
export function progressLine(line, { reduce = () => false, alive = () => true, pal = () => PALETTE.bash } = {}) {
  const state = { line, started: performance.now() / 1000, pct: null, changed: -1, lit: new Set(), e: {}, timer: 0 };
  function draw() {
    const { e } = state, now = performance.now() / 1000, still = reduce();
    const f = Math.max(0, Math.min(1, e.fraction ?? 0)), halves = Math.floor(f * BAR * 2), filled = Math.floor(halves / 2);
    const parts = [];
    const put = (text, color, extra = {}) => parts.push({ text, color, ...extra });
    if (!still) put(SPIN[Math.floor((now - state.started) / SPIN_S) % 4] + " ", tone(now * .1));
    // the stage, with a band of the rainbow crossing it now and then
    const label = String(e.stage ?? "");
    const cols = label.length, at = ((now % SWEEP_S) / SWEEP_S) * (cols + 2 * SWEEP_REACH) - SWEEP_REACH;
    [...label].forEach((ch, i) => { const d = Math.abs(i - at) / SWEEP_REACH; put(ch, !still && d < 1 ? tone(.08 + i / Math.max(cols, 1) * .5, 1 - d) : null); });
    put("  ");
    // the bar: the rainbow in steps of four cells, a glint down the done part every few seconds
    const glintAt = Math.min((now % GLINT_EVERY) / GLINT_SWEEP, 1) * (filled + 2 * GLINT_REACH) - GLINT_REACH;
    for (let i = 0; i < filled; i++) {
      const d = Math.min(Math.abs(i - glintAt) / GLINT_REACH, 1), lift = still ? 0 : .5 * (1 + Math.cos(Math.PI * d));
      put("━", tone(Math.floor(i / CELLS) * CELLS / BAR * .75, lift));
    }
    const tip = filled < BAR && halves % 2 ? "╸" : "";
    if (tip) put(tip, tone(Math.floor(filled / CELLS) * CELLS / BAR * .75, 1));
    put("─".repeat(BAR - filled - tip.length), null, { dim: true });
    put(" ");
    // the percentage: a digit that just changed flashes; 100 % is green
    const flash = !still && now - state.changed < FLASH_S, pct = state.pct ?? "";
    [...pct].forEach((ch, i) => put(ch, pct.trim() === "100%" ? pal()[10] : flash && state.lit.has(i) ? tone(.75) : null, { bold: flash && state.lit.has(i) }));
    if (Number.isFinite(e.eta_s) && e.eta_s > 0) put(`  ${Math.floor(e.eta_s / 60)}:${String(Math.round(e.eta_s % 60)).padStart(2, "0")}`, null, { dim: true });
    line.replaceChildren(...parts.map((p) => { const s = document.createElement("span"); s.textContent = p.text; if (p.color) s.style.color = p.color; if (p.dim) s.style.opacity = ".55"; if (p.bold) s.style.fontWeight = "700"; return s; }));
  }
  function update(e) {
    const now = performance.now() / 1000;
    const pct = `${Math.floor(Math.max(0, Math.min(1, e.fraction ?? 0)) * 100 + 1e-9)}%`.padStart(4);
    if (state.pct !== null && pct !== state.pct) {
      state.lit = new Set([...pct].map((ch, i) => (ch !== state.pct[i] ? i : -1)).filter((i) => i >= 0));
      state.changed = now;
    }
    state.pct = pct; state.e = e;
    draw();
    if (!reduce() && !state.timer) {
      const tick = () => { if (!line.isConnected || !alive()) { state.timer = 0; return; } draw(); state.timer = setTimeout(tick, 70); };
      state.timer = setTimeout(tick, 70);
    }
  }
  return { line, update, stop() { clearTimeout(state.timer); state.timer = 0; } };
}
