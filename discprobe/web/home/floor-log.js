// The job's command-line output, lying on the floor in front of the drive.
//
// The lines are the ones disc-probe prints in a terminal (the backend passes the job's stdout through as
// log events, with the core's colours), so the page never words them itself. They lie on the floor in
// front of the drive the way the percentage and the time left lie inside it (.inside-type): in the floor's
// plane, lines running down to the right along the drive's side, stacking down to the left.
//
// The block keeps its own size on the screen (the drive picture grows a lot when the cutaway opens; the
// words don't), lies beside the drive, and never leaves the window, slides under the footer row or
// over the panel on the right: slanted, it takes .87 x (width + height) across and .5 x (width + height)
// down, so in a small window it gets narrower first (lines end in "…") and then smaller. Newest line at the
// bottom in full ink, the older ones fading upwards, the core's progress line (core-render.js) under them.

import { painted, progressLine } from "./core-render.js";

const W = 1600, H = 1062;                     // burner.json's render, whose pixels the host box shows unmirrored
const PX_PER_MM = 3.61806;
const REAR = [1580.77, 565.11], FRONT = [922.46, 945.19], EDGE_MM = 210.1;
const ALONG = [(FRONT[0] - REAR[0]) / EDGE_MM, (FRONT[1] - REAR[1]) / EDGE_MM];
const OUT = [-ALONG[0], ALONG[1]];
const LINES = 7;
const FLOOR = [.866, .5];                     // the floor's plane: matrix(.866, .5, -.866, .5), as .inside-type
const WIDTHS = [600, 520, 440, 380, 320];     // block widths to try, widest first (unslanted px)
const MIN_SCALE = .8;                         // narrower before smaller than this
const SHOW_MIN = .7;                          // smaller than this and the block isn't shown at all
const GAP_MM = 14;                            // clear of the drive's side
const reduce = () => document.documentElement.dataset.motion !== "on";
const px = (n) => `${Math.round(n)}px`;

// a point on the floor, a mm along the side and o mm out from it, as a share (0..1) of the mirrored picture
function at(a, o) {
  const x = REAR[0] + ALONG[0] * a + OUT[0] * o, y = REAR[1] + ALONG[1] * a + OUT[1] * o;
  return [(W - x) / W, y / H];
}

export function floorLog() {
  const el = document.createElement("div");
  el.className = "floor-log";
  el.setAttribute("aria-hidden", "true");          // the job bar and the panel carry the words for screen readers
  el.innerHTML = `<div class="fl-title"></div><div class="fl-lines"></div><div class="fl-meter"></div>`;
  const [titleEl, lines, bar] = el.children;
  let host = null, meterLine = null, timer = 0;

  // Where the block goes: on the floor beside the drive's left side (the floor the picture shows most of),
  // lines running along the side, and inside the free part of the window (its margins, above the footer
  // row, left of the panel). Of the spots tried, the one that lets the block be largest; at MIN_SCALE or
  // more, the widest block. If none leaves even SHOW_MIN, the window is too small for it: the block isn't
  // shown (the panel on the right is what matters), and the panel shows the step's title itself (fl-off).
  function place() {
    if (!host || !el.classList.contains("on")) return;
    const box = host.getBoundingClientRect();
    if (!box.width) return;
    const css = getComputedStyle(document.documentElement);
    const edge = parseFloat(css.getPropertyValue("--edge")) || 32;
    const foot = edge + (parseFloat(css.getPropertyValue("--row")) || 52);
    const panel = [...document.querySelectorAll("#cal:not([hidden]), .burn-panel, .detail")].map((n) => n.getBoundingClientRect()).find((r) => r.width);
    const right = panel ? panel.left - 32 : innerWidth - edge;
    const top0 = edge + 70, bottom = innerHeight - foot - 20;
    const point = (a, o) => { const [fx, fy] = at(a, o); return [box.left + fx * box.width, box.top + fy * box.height]; };
    const [e1, e2] = [[FLOOR[0], FLOOR[1]], [-FLOOR[0], FLOOR[1]]];     // the text's across and down, on screen
    // the largest scale (<= 1) at which a w x h block with its top-left corner at O stays in the free part
    function fit([ox, oy], w, h) {
      if (ox < edge || ox > right || oy < top0 || oy > bottom) return 0;
      let k = 1;
      for (const [dx, dy] of [[e1[0] * w, e1[1] * w], [e2[0] * h, e2[1] * h], [e1[0] * w + e2[0] * h, e1[1] * w + e2[1] * h]]) {
        if (dx > 0) k = Math.min(k, (right - ox) / dx); else if (dx < 0) k = Math.min(k, (edge - ox) / dx);
        if (dy > 0) k = Math.min(k, (bottom - oy) / dy); else if (dy < 0) k = Math.min(k, (top0 - oy) / dy);
      }
      return Math.max(0, k);
    }
    const spots = [];
    for (let a = 0; a <= EDGE_MM - 40; a += 15) spots.push(point(a, GAP_MM));               // beside the left side
    let best = null;
    for (const width of WIDTHS) {
      el.style.width = px(width);
      const h = el.offsetHeight;
      for (const O of spots) {
        const k = fit(O, width, h);
        const better = !best || (k >= MIN_SCALE ? best.k < MIN_SCALE || width > best.w || (width === best.w && k > best.k) : k > best.k);
        if (better) best = { O, w: width, h, k };
      }
    }
    const { O: [ox, oy], w, k } = best;
    const cramped = k < SHOW_MIN;
    el.classList.toggle("cramped", cramped);
    document.documentElement.classList.toggle("fl-off", cramped);
    if (cramped) return;
    el.style.width = px(w);
    el.style.transform = `matrix(${e1[0] * k}, ${e1[1] * k}, ${e2[0] * k}, ${e2[1] * k}, 0, 0)`;
    el.style.left = px(ox);
    el.style.top = px(oy);
  }
  // the cutaway grows and moves for most of a second: follow it while the block shows
  function follow() {
    clearInterval(timer);
    timer = setInterval(() => (el.classList.contains("on") ? place() : clearInterval(timer)), 200);
    place();
  }
  addEventListener("resize", place);

  function push(text, level = "info", ansi = null) {
    const row = document.createElement("div");
    row.className = `fl-line ${level}`;
    if (ansi) row.append(painted(ansi)); else row.textContent = text;
    lines.append(row);
    while (lines.children.length > LINES) lines.firstChild.remove();
    [...lines.children].forEach((n, i, all) => n.style.setProperty("--age", String(all.length - 1 - i)));
    if (!reduce()) row.animate([{ opacity: 0, translate: "0 6px" }, { opacity: 1, translate: "0 0" }], { duration: 260, easing: "ease-out" });
  }
  return {
    // the box that now shows the drive picture unmirrored: the block hangs in front of the drive in it
    mount(box) {
      if (!box) return;
      host = box;
      if (!el.isConnected) document.body.append(el);
      follow();
    },
    start(command) {
      lines.replaceChildren();
      meterLine?.stop(); meterLine = null; bar.replaceChildren();
      el.classList.add("on");
      push(command, "command");
      follow();
    },
    log(text, level, ansi) { if (text) push(text, level, ansi); },
    progress(fraction, stage, eta) {
      meterLine ??= progressLine(bar, { reduce, alive: () => el.classList.contains("on") });
      meterLine.update({ fraction, stage, eta_s: eta });
    },
    end() { meterLine?.stop(); meterLine = null; bar.replaceChildren(); },
    // the step's name, the block's first line, large; empty takes it away
    title(text) {
      titleEl.textContent = text || "";
      titleEl.hidden = !text;
      if (text) { el.classList.add("on"); follow(); }
      place();
    },
    hide() { el.classList.remove("on"); document.documentElement.classList.remove("fl-off"); clearInterval(timer); },
  };
}
