// The job's command-line output, lying on the floor beside the drive.
//
// The lines are the ones disc-probe prints in a terminal (the backend passes the job's stdout through
// as log events), so the page never words them itself. They lie along the drive's side, the way the
// floor runs in the picture: the newest line is the one furthest from the drive, the older ones move
// toward the drive and fade, and under them a meter line like the terminal's progress line.
//
// Placed in the render's own pixels (burner.json: 1600 × 1062, true isometric), in whatever box shows
// that picture unmirrored at the moment: the drive picture on the home page, or the big cutaway.
//
// The lines keep the core's colours (log events carry its SGR codes), and the meter is the core's own
// progress line (core-render.js, the same renderer as the terminal page). The step's title lies on the
// floor in front of the drive, turned 45° anticlockwise in the floor's plane, so it reads across the
// picture like a word painted on the ground.

import { painted, progressLine } from "./core-render.js";

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

// the title (shown only while a job runs, when the tray is shut): centred this far along the side, in front of the closed tray, and
// this far in from it (the middle of the front face, the drive being about 148 mm wide); letters this tall
const TITLE_AT = [300, -74], TITLE_MM = 36;
const reduce = () => document.documentElement.dataset.motion !== "on";

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
  const title = document.createElement("div");
  title.className = "fl-title";
  title.setAttribute("aria-hidden", "true");
  const [tl, tt] = at(...TITLE_AT);
  Object.assign(title.style, { left: `${tl}%`, top: `${tt}%` });
  for (const [k, v] of Object.entries({ "--mm": `${MM}cqw`, "--fl-title": TITLE_MM })) title.style.setProperty(k, v);
  let host = null, meterLine = null;

  function push(text, level = "info", ansi = null) {
    const row = document.createElement("div");
    row.className = `fl-line ${level}`;
    if (ansi) row.append(painted(ansi)); else row.textContent = text;
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
      box.append(el, title);
    },
    start(command) {
      lines.replaceChildren();
      meterLine?.stop(); meterLine = null; bar.replaceChildren();
      el.classList.add("on");
      push(command, "command");
    },
    log(text, level, ansi) { if (text) push(text, level, ansi); },
    progress(fraction, stage, eta) {
      meterLine ??= progressLine(bar, { reduce, alive: () => el.classList.contains("on") });
      meterLine.update({ fraction, stage, eta_s: eta });
    },
    end() { meterLine?.stop(); meterLine = null; bar.replaceChildren(); },
    // the step's name on the floor in front of the drive; empty takes it away
    title(text) {
      if (text) title.textContent = text;
      title.classList.toggle("on", !!text);
    },
    hide() { el.classList.remove("on"); title.classList.remove("on"); },
  };
}
