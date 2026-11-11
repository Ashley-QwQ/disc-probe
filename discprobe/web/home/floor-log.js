// The job's command-line output, lying on the floor beside the drive.
//
// The lines are the ones disc-probe prints in a terminal (the backend passes the job's stdout through
// as log events), so the page never words them itself. They lie along the drive's side, the way the
// floor runs in the picture: the newest line is the one furthest from the drive, the older ones move
// toward the drive and fade, and under them a meter line like the terminal's progress line.
//
// Placed in the render's own pixels (burner.json: 1600 × 1062, true isometric), in whatever box shows
// that picture unmirrored at the moment: the drive picture on the home page, or the big cutaway.

const W = 1600, H = 1062;
const PX_PER_MM = 3.61806;                    // along each world axis, render px
const MM = (PX_PER_MM / W) * 100;             // one millimetre in cqw of a box W px wide
// The drive's +X side (the one with the screw holes; on the left in the mirrored picture): its
// floor edge runs from the rear corner to the front corner.
const REAR = [1580.77, 565.11], FRONT = [922.46, 945.19], EDGE_MM = 210.1;
const ALONG = [(FRONT[0] - REAR[0]) / EDGE_MM, (FRONT[1] - REAR[1]) / EDGE_MM];   // px per mm, rear → front
const OUT = [-ALONG[0], ALONG[1]];                                                 // px per mm, away from the side
// Type larger than life: true to the drive it would be a few pixels high. The lines run on past the
// front corner, beside where the tray comes out (they lie further out than the tray).
const LINES = 5, PITCH_MM = 22, FONT_MM = 15, LENGTH_MM = 600;

// a point on the floor, `a` mm from the rear corner along the side and `o` mm out from it, as a
// share of the mirrored picture
function at(a, o) {
  const x = REAR[0] + ALONG[0] * a + OUT[0] * o, y = REAR[1] + ALONG[1] * a + OUT[1] * o;
  return [((W - x) / W) * 100, (y / H) * 100];
}

const clock = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const BAR = 24;
function meter(fraction, stage, eta) {
  const parts = [];
  if (Number.isFinite(fraction)) {
    const f = Math.max(0, Math.min(1, fraction)), n = Math.round(f * BAR);
    parts.push(`[${"#".repeat(n)}${"-".repeat(BAR - n)}]`, `${String(Math.floor(f * 100)).padStart(3)}%`);
  }
  if (stage) parts.push(stage);
  if (Number.isFinite(eta)) parts.push(`about ${clock(eta)} left`);
  return parts.join("  ");
}

export function floorLog() {
  const el = document.createElement("div");
  el.className = "floor-log";
  el.setAttribute("aria-hidden", "true");          // the job bar and the panel carry the words for screen readers
  el.innerHTML = `<div class="fl-lines"></div><div class="fl-meter"></div>`;
  const [left, top] = at(4, 8);
  Object.assign(el.style, { left: `${left}%`, top: `${top}%`, width: `${LENGTH_MM * MM}cqw` });
  for (const [k, v] of Object.entries({ "--mm": `${MM}cqw`, "--fl-pitch": PITCH_MM, "--fl-font": FONT_MM, "--fl-lines": LINES }))
    el.style.setProperty(k, v);
  const lines = el.firstChild, bar = el.lastChild;
  let host = null;

  function push(text, level = "info") {
    const row = document.createElement("div");
    row.className = `fl-line ${level}`;
    row.textContent = text;
    lines.append(row);
    while (lines.children.length > LINES + 1) lines.firstChild.remove();
    // the column moves one line toward the drive; the newest line rises into the free place
    lines.style.transition = "none";
    lines.style.transform = `translateY(calc(var(--mm) * ${PITCH_MM}))`;
    void lines.offsetWidth;
    lines.style.transition = "";
    lines.style.transform = "";
  }
  return {
    // put the log into the box that now shows the drive picture unmirrored (container-type: inline-size)
    mount(box) {
      if (!box || host === box) return;
      host = box;
      box.append(el);
    },
    start(command) {
      lines.replaceChildren();
      bar.textContent = "";
      el.classList.add("on");
      push(command, "command");
    },
    log(text, level) { if (text) push(text, level); },
    progress(fraction, stage, eta) { bar.textContent = meter(fraction, stage, eta); },
    end() { bar.textContent = ""; },
    hide() { el.classList.remove("on"); },
  };
}
