// Pieces of the drive scene shared by the calibration flow (calibrate.js) and the burn page (burn.js).
//
// - cutaway(api, opts): while it burns, the drive opens into a cutaway that grows from the drive
//   picture to fill the left of the window. The pickup moves with the head's radius, so the pickup is
//   the progress bar; the percentage lies on the disc and the time left on the tray floor.
// - flyer(api, opts): a disc printed with its name, hovering over the open tray with an arrow, that
//   drops into the tray.
//
// The home page's drive picture is shown mirrored. `mirrored: false` is for a page that flips the
// drive back (the burn page, so its tray faces the other way); positions follow either way.

const R0 = 22, R1 = 58.5;               // data area, mm: the radius the head sweeps while burning
const radiusAt = (p) => Math.sqrt(R0 * R0 + (R1 * R1 - R0 * R0) * p);   // constant linear velocity
const CROP = [10, 25, 1180, 920];       // what of the 1600 × 1062 canvas is drive (mirrored px)

const rigRect = (api) =>
  [...api.burnerLayer.querySelectorAll(".rig")].find((n) => n.getBoundingClientRect().width > 0)?.getBoundingClientRect();

export function cutaway(api, { mirrored = true, textLeft = () => innerWidth * 0.56 } = {}) {
  let inside = null;
  const X = (x) => mirrored ? 1 - x / 1600 : x / 1600;     // canvas px across, as a share of the picture
  async function build() {
    if (inside) return inside;
    const info = await fetch(new URL("./interior/interior.json", import.meta.url)).then((r) => r.json());
    const stage = document.createElement("div");
    stage.className = `cutaway live${mirrored ? "" : " unmirrored"}`;
    stage.innerHTML = `<div class="cutaway-in"></div>`;
    const box = stage.firstChild, sets = {};
    for (const theme of ["dark", "paper"]) {
      const set = document.createElement("div");
      set.className = `inside ${theme === "dark" ? "dark" : "light"}`;
      const disc = theme === "dark" ? "disc" : "disc_cut";          // dark: see-through disc; paper: cut away
      const img = (name, cls) => `<img class="${cls}" alt="" decoding="async" data-src="${new URL(`./interior/${name}_${theme}.webp`, import.meta.url).href}">`;
      set.innerHTML = img("bg", "bg") + img("sled", "sled") + img("mid", "mid") + img(disc, "disc") + img("glow", "glow") + img("occluders", "occ");
      box.append(set);
      sets[theme] = set;
    }
    // flat type, placed in canvas px (the picture may be mirrored, the type never is)
    const at = (el, x, y) => { el.style.left = `${X(x) * 100}%`; el.style.top = `${(y / 1062) * 100}%`; };
    const pct = document.createElement("div"), clock = document.createElement("div");
    pct.className = "inside-type big"; clock.className = "inside-type";
    const d = info.disc.centre_px_top_face, m = info.disc.plane_matrix_px_per_mm;
    at(pct, d[0] + m.a * 37 + m.c * 17, d[1] + m.b * 37 + m.d * 17);   // the open part of the disc, below the clamp bridge
    at(clock, 705, 468);                         // the flat floor of the closed tray, beside the pickup
    box.append(pct, clock);
    document.body.append(stage);
    inside = { info, stage, box, sets, pct, clock, on: false };
    addEventListener("resize", () => { if (inside.on) place(); });
    new MutationObserver(() => { if (inside.on) load(theme()); }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return inside;
  }
  const theme = () => document.documentElement.dataset.theme === "dark" ? "dark" : "paper";
  function load(t) { for (const im of inside.sets[t].querySelectorAll("img[data-src]")) { im.src = im.dataset.src; im.removeAttribute("data-src"); } }
  // the big place: the left of the window, up to the text column, between the top row and the bar
  function place() {
    const W = innerWidth, H = innerHeight;
    const x0 = 12, x1 = Math.min((textLeft() || W * 0.56) - 56, W * 0.6), y0 = 76, y1 = (document.getElementById("next")?.getBoundingClientRect().top ?? H - 80) - 8;   // above the footer row
    const [cx0, cy, cw, ch] = CROP, cx = mirrored ? cx0 : 1600 - cx0 - cw;
    const k = Math.min((x1 - x0) / cw, (y1 - y0) / ch);
    const L = x0 + (x1 - x0 - cw * k) / 2 - cx * k, T0 = y0 + (y1 - y0 - ch * k) / 2 - cy * k;
    Object.assign(inside.box.style, { left: `${L}px`, top: `${T0}px`, width: `${1600 * k}px`, height: `${1062 * k}px` });
    return { L, T: T0, w: 1600 * k };
  }
  // the transform that puts the big cutaway back onto the drive picture
  function fromRig(to) {
    const r = rigRect(api);
    return r ? `translate(${r.left - to.L}px, ${r.top - to.T}px) scale(${r.width / to.w})` : "none";
  }
  async function show(on) {
    const root = document.documentElement;
    if (!on) {
      if (!inside?.on) return;
      inside.on = false;
      const to = { L: parseFloat(inside.box.style.left), T: parseFloat(inside.box.style.top), w: parseFloat(inside.box.style.width) };
      inside.box.style.transform = fromRig(to);          // shrink back into the drive
      inside.stage.classList.remove("on");
      root.classList.remove("burning");
      api.burnerLayer.classList.remove("inside-on");
      return;
    }
    const s0 = await build();
    if (s0.on) { place(); return; }
    s0.on = true;
    load(theme());
    const to = place();
    s0.box.style.transition = "none";
    s0.box.style.transform = fromRig(to);               // start exactly on the drive picture
    void s0.box.offsetWidth;
    s0.box.style.transition = "";
    s0.stage.classList.add("on");
    api.burnerLayer.classList.add("inside-on");
    root.classList.add("burning");
    setTimeout(() => { if (s0.on) s0.box.style.transform = "none"; }, 30);   // then grow into place
  }
  function update(p, leftS) {
    if (!inside) return;
    const sl = inside.info.sled, size = inside.info.image_size;
    const r = Math.min(sl.radius_mm[1], Math.max(sl.radius_mm[0], radiusAt(p) * (sl.radius_mm[1] / R1)));
    const t = (r - sl.radius_mm[0]) / sl.travel_mm;
    const tx = `${((sl.offset_px[0] * t) / size[0]) * 100}%`, ty = `${((sl.offset_px[1] * t) / size[1]) * 100}%`;
    inside.box.style.setProperty("--sled", `${tx}, ${ty}`);
    inside.pct.textContent = `${Math.floor(p * 100)}%`;
    if (Number.isFinite(leftS)) {
      const m = Math.floor(leftS / 60), sec = Math.floor(leftS % 60);
      inside.clock.textContent = `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
    } else inside.clock.textContent = "";
  }
  // box: the cutaway's picture, unmirrored, in render px (a container for cqw sizes)
  return { show, update, get on() { return !!inside?.on; }, get box() { return inside?.box; } };
}

// A disc hovering over the open tray. Positions are worked out from the rig's box (which does not
// move with the tray): burner.json's disc centre plus the extra 60 mm the page opens the tray by.
export function flyer(api, { mirrored = true } = {}) {
  const pct = (x, y) => [`${(x / api.meta.width) * 100}%`, `${(y / api.meta.height) * 100}%`];
  function trayPoint() {
    const r = rigRect(api), cam = api.cam.getBoundingClientRect(), k = cam.width / api.meta.width;
    if (!r) return [api.meta.burnerAnchor.x, api.meta.burnerAnchor.y];
    const extra = [(60 / 140) * 438.666, (-60 / 140) * -253.264];
    const xm = (1600 - 659.34 + extra[0]) / 1600, x = mirrored ? xm : 1 - xm, y = (608.19 + extra[1]) / 1062;
    return [(r.left + x * r.width - cam.left) / k, (r.top + y * r.height - cam.top) / k];
  }
  const hoverPoint = () => { const [x, y] = trayPoint(); return [x, y - 115]; };
  const el = document.createElement("div");
  el.className = "flyer";
  el.style.width = `${(120 * api.meta.axisPx / api.meta.width) * 100}%`;
  el.innerHTML = `<div class="floor"><div class="face"><svg class="print" viewBox="0 0 100 100" aria-hidden="true">` +
    `<defs><path id="fly-arc-burn" d="M50,50 m-35.5,0 a35.5,35.5 0 1,1 71,0 a35.5,35.5 0 1,1 -71,0"/></defs>` +
    `<text><textPath href="#fly-arc-burn" startOffset="25%" text-anchor="middle"></textPath></text></svg></div></div>` +
    `<svg class="arrow" viewBox="0 0 24 40" aria-hidden="true"><path d="M12 2v32M4 26l8 9 8-9"/></svg>`;
  api.cam.append(el);
  const wait = (ms) => new Promise((r) => setTimeout(r, api.reduce ? 0 : ms));
  return {
    // come down from above and hover, breathing, the arrow pointing at the tray
    async hover(name) {
      el.querySelector(".print textPath").textContent = name ?? "";
      el.classList.remove("drop", "up");
      const [x, y] = pct(...hoverPoint());
      el.style.transition = "none";
      el.style.left = x; el.style.top = "-30%";
      el.classList.add("on");
      void el.offsetWidth;
      el.style.transition = "";
      el.style.top = y;
      await wait(1400);
      if (el.classList.contains("on") && !el.classList.contains("drop")) el.classList.add("hover");
    },
    // fall into the tray; the caller then puts the disc in the tray picture and closes it
    async drop() {
      el.classList.remove("hover");
      const [x, y] = pct(...trayPoint());
      el.classList.add("drop");
      el.style.left = x; el.style.top = y;
      await wait(950);
      el.classList.remove("on", "drop");
    },
    // the disc in the tray rises out of it and hovers, the arrow pointing up (as on the calibration page)
    async lift(name) {
      el.querySelector(".print textPath").textContent = name ?? "";
      el.classList.remove("drop", "hover");
      const [tx, ty] = pct(...trayPoint());
      el.style.transition = "none";
      el.style.left = tx; el.style.top = ty;
      el.classList.add("on", "up");
      api.placeDisc(false);
      void el.offsetWidth;
      el.style.transition = "";
      const [hx, hy] = pct(...hoverPoint());
      el.style.left = hx; el.style.top = hy;
      await wait(1400);
      if (el.classList.contains("up") && el.classList.contains("on")) el.classList.add("hover");
    },
    // taken away: up and out of the picture
    async away() {
      el.classList.remove("hover");
      el.style.top = "-30%";
      await wait(1300);
      el.classList.remove("on", "up");
    },
    hide() { el.classList.remove("on", "hover", "drop", "up"); },
  };
}
