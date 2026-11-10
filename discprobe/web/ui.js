// disc-probe UI helpers: the radius rainbow, ghost completion, hold-to-confirm. No dependencies.

// OKLCH to sRGB hex, same maths as discprobe/ui.py `oklch`.
export function oklch(light, chroma, hueDeg) {
  const h = (hueDeg * Math.PI) / 180, a = chroma * Math.cos(h), b = chroma * Math.sin(h);
  const l = (light + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (light - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (light - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const lin = [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s];
  return "#" + lin.map((v) => {
    const c = v <= 0 ? 0 : v < 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055;
    return Math.round(Math.min(1, c) * 255).toString(16).padStart(2, "0");
  }).join("");
}

// The signature: colour follows the radius the optical head is at, inner (blue) to outer (red),
// the order a disc shows its diffraction colours under one lamp.
export const R_INNER = 22, R_OUTER = 58.5;
export function hueAt(radiusMm) {
  const t = Math.min(1, Math.max(0, (radiusMm - R_INNER) / (R_OUTER - R_INNER)));
  return 262 - t * 237;
}
export function rainbowAt(radiusMm) { return oklch(0.74, 0.11, hueAt(radiusMm)); }
export function rainbowGradient(r0 = R_INNER, r1 = R_OUTER, stops = 12) {
  const parts = [];
  for (let i = 0; i <= stops; i++) {
    const r = r0 + ((r1 - r0) * i) / stops;
    parts.push(`${rainbowAt(r)} ${((i / stops) * 100).toFixed(1)}%`);
  }
  return `linear-gradient(90deg, ${parts.join(", ")})`;
}

// A progress bar. For a disc job pass radiusMm: the filled part shows the colours from the inner
// edge up to where the head is now. Without a radius the bar stays in the primary colour.
export function setProgress(bar, fraction, radiusMm) {
  const fill = bar.querySelector(".bar-fill");
  fill.style.width = `${(Math.max(0, Math.min(1, fraction)) * 100).toFixed(2)}%`;
  if (radiusMm == null) { bar.removeAttribute("data-disc"); return; }
  bar.setAttribute("data-disc", "");
  const r1 = Math.max(R_INNER + 0.5, radiusMm);
  fill.style.setProperty("--rainbow", rainbowGradient(R_INNER, r1));
  fill.style.backgroundSize = "100% 100%";
}

// Ghost completion: a faint suggestion after what was typed; Tab or → at the end accepts it.
export function ghostInput(input, ghost, suggestions) {
  const show = () => {
    const v = input.value;
    const hit = v ? suggestions.find((s) => s.toLowerCase().startsWith(v.toLowerCase()) && s.length > v.length) : suggestions[0];
    ghost.innerHTML = "";
    if (!hit) return;
    const typed = document.createElement("span");
    typed.className = "typed";
    typed.textContent = v;
    ghost.append(typed, document.createTextNode(hit.slice(v.length)));
    ghost.dataset.hit = hit;
  };
  input.addEventListener("input", show);
  input.addEventListener("keydown", (e) => {
    const atEnd = input.selectionStart === input.value.length;
    if ((e.key === "Tab" || (e.key === "ArrowRight" && atEnd)) && ghost.dataset.hit && ghost.textContent.length > input.value.length) {
      e.preventDefault();
      input.value = ghost.dataset.hit;
      show();
    }
  });
  show();
}

// Hold to confirm: the ring fills along the circumference; letting go early cancels.
export function holdToConfirm(button, { ms = 1000, onConfirm, label } = {}) {
  const ring = button.querySelector(".hold-ring");
  const stops = Array.from({ length: 13 }, (_, i) => `${rainbowAt(R_INNER + ((R_OUTER - R_INNER) * i) / 12)} ${(i * 30).toFixed(0)}deg`);
  ring.style.setProperty("--ring", `conic-gradient(${stops.join(", ")})`);
  let start = 0, raf = 0, done = false;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const draw = (t) => ring.style.setProperty("--deg", `${(t * 360).toFixed(1)}deg`);
  const stop = () => { cancelAnimationFrame(raf); if (!done) draw(0); start = 0; };
  const tick = (now) => {
    const t = Math.min(1, (now - start) / ms);
    draw(reduce ? (t < 1 ? 0 : 1) : t);
    if (t < 1) { raf = requestAnimationFrame(tick); return; }
    done = true;
    onConfirm?.();
  };
  const begin = (e) => {
    if (done || start) return;
    e.preventDefault();
    start = performance.now();
    raf = requestAnimationFrame(tick);
  };
  button.addEventListener("pointerdown", begin);
  for (const ev of ["pointerup", "pointerleave", "pointercancel"]) button.addEventListener(ev, stop);
  button.addEventListener("keydown", (e) => { if ((e.key === " " || e.key === "Enter") && !e.repeat) begin(e); });
  button.addEventListener("keyup", (e) => { if (e.key === " " || e.key === "Enter") stop(); });
  button.addEventListener("click", (e) => e.preventDefault());
  if (label) button.setAttribute("aria-label", label);
  return { reset() { done = false; draw(0); } };
}
