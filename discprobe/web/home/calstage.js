import { flipWatch } from "./kit/flipnum.js";
// The calibration page's stage: the burner seen straight down with its top shell see-through (caltop/,
// rendered by caltop/render_caltop.py), the disc as the main character. The page draws on the disc what is
// happening: the rainbow growing out from the inner edge as the head reads (hue by radius, as everywhere a
// disc is read or written), a thin pointer from the centre to the head with its radius, a copper band where
// reading stopped, a dashed place when there is no disc. A big percent and the time left sit lower left.
//
//   const st = await stage(api); st.show(true); st.set({ disc, read, head, headKnown, band, percent, left, busy });
//     disc: "in" | "none" | "blank"     read: [r0, r1] mm already covered (rainbow), or null
//     head: mm of the head (pointer), or null; headKnown false: the pointer without a number
//     band: [r0, r1] mm where it stopped (copper), or null        busy: the drive is working (shell a touch darker)
//     percent: 0..100 or null; left: words for the time left
// Nothing here talks to the drive; it only draws what the page tells it.

const ORDER = ["shadow", "bg", "sled", "mid", "disc", "glow", "over", "occluders", "lid"];
const BASE = new URL("./caltop/", import.meta.url);
let meta = null, el = null, state = {}, api = null;

// the colour of the radius the head is at: the same OKLCH rainbow as the rest of the page (calibrate.js, ui.py)
function oklch(l, c, hDeg) {
  const h = (hDeg * Math.PI) / 180, a = c * Math.cos(h), b = c * Math.sin(h);
  const L = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3, M = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3, S = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const lin = [4.0767416621 * L - 3.3077115913 * M + 0.2309699292 * S, -1.2684380046 * L + 2.6097574011 * M - 0.3413193965 * S, -0.0041960863 * L - 0.7034186147 * M + 1.707614701 * S];
  return "#" + lin.map((v) => Math.round(Math.min(1, v <= 0 ? 0 : v < 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055) * 255).toString(16).padStart(2, "0")).join("");
}
const rainbowAt = (mm) => oklch(0.72, 0.12, 262 - Math.min(1, Math.max(0, (mm - 24) / 34)) * 237);
function theme() { return document.documentElement.dataset.theme === "dark" ? "dark" : "paper"; }

function build() {
  el = document.createElement("div");
  el.className = "cal-stage";
  el.hidden = true;
  const [W, H] = meta.image_size;
  // the picture has room for the shadow on its left and below: centre the drive itself, the shadow spills over
  const [bx0, by0, bx1, by1] = meta.body_px || [0, 0, W, H];
  const shift = `translate:${((W / 2 - (bx0 + bx1) / 2) / W * 100).toFixed(2)}% ${((H / 2 - (by0 + by1) / 2) / H * 100).toFixed(2)}%`;
  el.innerHTML = `<div class="cs-art" style="aspect-ratio:${W}/${H};${shift}">` +
    ORDER.map((k) => k === "over" ? `<canvas class="cs-over" width="${W}" height="${H}"></canvas>` : `<img class="cs-${k}" alt="" draggable="false">`).join("") +
    // the disc turning while the drive works: one grey arc near the rim going round (designer: "光驱正忙")
    `<svg class="cs-spin" viewBox="0 0 ${W} ${H}" aria-hidden="true" style="--spin-o:${(meta.disc.centre_px[0] / W * 100).toFixed(2)}% ${(meta.disc.centre_px[1] / H * 100).toFixed(2)}%"><path d="${spinArc()}"/></svg>` +
    `<span class="cs-label" hidden></span></div>` +
    `<p class="cs-big" hidden><b></b><span></span></p>`;
  document.body.append(el);
  for (const n of el.querySelectorAll(".cs-big b, .cs-big span")) flipWatch(n, {lang:api.lang()});
  addEventListener("dp-theme", paintArt);
  new MutationObserver(paintArt).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  paintArt();
}
function spinArc() {
  const [cx, cy] = meta.disc.centre_px, r = 56.5 * meta.scale.px_per_mm, a0 = -Math.PI / 2, a1 = a0 + Math.PI * 40 / 180;
  const pt = (a) => `${(cx + r * Math.cos(a)).toFixed(1)} ${(cy + r * Math.sin(a)).toFixed(1)}`;
  return `M ${pt(a0)} A ${r.toFixed(1)} ${r.toFixed(1)} 0 0 1 ${pt(a1)}`;
}
function paintArt() {
  if (!el) return;
  const v = theme();
  for (const k of ORDER) {
    if (k === "over") continue;
    const img = el.querySelector(`.cs-${k}`), src = new URL(`${k}_${v}.webp`, BASE).href;
    if (img.dataset.src !== src) { img.src = src; img.dataset.src = src; }
  }
  draw();
}

function draw() {
  if (!el || !meta) return;
  const s = state, [W, H] = meta.image_size, g = el.querySelector(".cs-over").getContext("2d");
  const [cx, cy] = meta.disc.centre_px, pxmm = meta.scale.px_per_mm, R = (mm) => mm * pxmm;
  const art = el.querySelector(".cs-art");
  art.dataset.disc = s.disc || "in";
  art.classList.toggle("busy", !!s.busy);
  art.classList.toggle("spinning", !!s.busy && s.disc !== "none");
  g.clearRect(0, 0, W, H);
  // the head: the sled slides along its travel; the laser spot with it while it reads
  const [rIn, rOut] = meta.sled.radius_mm, travel = rOut - rIn;
  const head = Number.isFinite(s.head) ? Math.max(rIn, Math.min(rOut, s.head)) : rIn;
  const t = (head - rIn) / travel, [ox, oy] = meta.sled.offset_px;
  const move = `translate(${(ox * t / W * 100).toFixed(3)}%, ${(oy * t / H * 100).toFixed(3)}%)`;
  el.querySelector(".cs-sled").style.transform = move;
  const glow = el.querySelector(".cs-glow");
  glow.style.transform = move; glow.hidden = !s.busy || s.disc !== "in";
  if (s.disc === "none") {                 // the empty place where the disc goes
    g.save(); g.setLineDash([R(2.4), R(1.8)]); g.strokeStyle = cssVar("--copper"); g.lineWidth = R(0.5);
    g.beginPath(); g.arc(cx, cy, R(60), 0, Math.PI * 2); g.stroke(); g.restore();
  }
  if (s.disc !== "none" && s.read) {       // what has been read or written: rings coloured by radius (a blank being burned too)
    const [a, b] = s.read, step = 0.5;
    g.save(); g.globalAlpha = 0.85;
    for (let mm = a; mm < b; mm += step) {
      g.fillStyle = rainbowAt(mm + step / 2);
      g.beginPath(); g.arc(cx, cy, R(Math.min(b, mm + step)), 0, Math.PI * 2); g.arc(cx, cy, R(mm), 0, Math.PI * 2, true); g.fill();
    }
    g.restore();
  }
  if (s.band) {                            // where reading stopped: a copper band, the one thing to look at
    g.save(); g.fillStyle = cssVar("--copper"); g.globalAlpha = 0.55;
    g.beginPath(); g.arc(cx, cy, R(s.band[1]), 0, Math.PI * 2); g.arc(cx, cy, R(s.band[0]), 0, Math.PI * 2, true); g.fill();
    g.restore();
  }
  // the pointer: from the centre along the head's travel to the head, a small ring at the head
  const label = el.querySelector(".cs-label");
  if (s.disc === "in" && Number.isFinite(s.head)) {
    const [ux, uy] = unit(meta.sled.px_per_mm), hx = cx + ux * R(head), hy = cy + uy * R(head);
    g.save(); g.strokeStyle = cssVar("--ink"); g.lineWidth = Math.max(1.5, R(0.25));
    g.beginPath(); g.moveTo(cx, cy); g.lineTo(hx, hy); g.stroke();
    g.fillStyle = cssVar("--paper"); g.beginPath(); g.arc(hx, hy, R(1.4), 0, Math.PI * 2); g.fill(); g.stroke();
    g.restore();
    const zh = api?.lang() === "zh";
    label.textContent = s.headKnown === false ? (zh ? "光头在读" : "Head reading") : (zh ? `光头在 ${head.toFixed(1)} mm` : `Head at ${head.toFixed(1)} mm`);
    label.style.left = `${(hx / W * 100).toFixed(2)}%`; label.style.top = `${(hy / H * 100).toFixed(2)}%`;
    label.hidden = false;
  } else label.hidden = true;
  const big = el.querySelector(".cs-big");
  big.hidden = !Number.isFinite(s.percent);
  if (!big.hidden) { big.querySelector("b").textContent = `${Math.round(s.percent)}%`; big.querySelector("span").textContent = s.left || ""; }
}
// the scene's scale for the glass shadows (index.html --mm): the stage picture's px per mm on screen
function scale() {
  const art = el?.querySelector(".cs-art");
  if (!art || el.hidden) return;
  const w = art.getBoundingClientRect().width;
  if (w) document.documentElement.style.setProperty("--mm", `${(w / meta.image_size[0] * meta.scale.px_per_mm).toFixed(3)}px`);
}
addEventListener("resize", () => scale());
const unit = ([x, y]) => { const n = Math.hypot(x, y) || 1; return [x / n, y / n]; };
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

export async function stage(homeApi) {
  api = homeApi;
  if (!meta) meta = await fetch(new URL("caltop.json", BASE)).then((r) => r.json());
  if (!el) build();
  return {
    show(on) { el.hidden = !on; if (on) { draw(); scale(); } },
    art: () => el.querySelector(".cs-art"),          // the picture's box: the grid loaddisc.js lines up with
    hold(on) { el.style.visibility = on ? "hidden" : ""; },   // laid out but unseen while the disc goes in
    set(next) { state = { ...next }; draw(); },
  };
}
