// The terminal: what opens when the monitor in the lobby is clicked. The screen lights up (a baked layer,
// lobby.js), then a console slides down from the top, dressed as the shell of the machine the core runs
// on (PowerShell on Windows, bash elsewhere), with an optional worn-screen look.
//
// It is not a shell. A typed line is read as a disc-probe command and sent to the same job runner the
// pages use (/api/run): the same whitelist of actions and options, checked by the server, so nothing
// can be run here that a page could not run. The core's output comes back line by line (log events),
// its progress on one updating line, and its questions are answered by typing y or n. Burning stays on
// the burn page, where it is confirmed by holding the button.

const STR = {
  zh: {
    title: { win: "PowerShell · disc-probe", bash: "bash · disc-probe" }, close: "关闭", real: "旧屏幕质感",
    hello: "disc-probe 终端。输入 help 看能用的命令；命令和页面上的按钮走同一条路，只是用打字代替点击。",
    help: ["读光驱里的盘（只读）", "测转速", "测几何", "等你换一张盘（只读）", "做随机数据盘的镜像", "做刻录镜像", "导出 DIS 预设",
      "CD 探测", "光驱和正在跑的任务", "清屏", "关掉终端"],
    helpNote: "光驱默认是页面上选中的那台（--drive 可改），盘种默认 DVD（--media 可改）。",
    noBurn: "刻录请到刻录页：在那里按住按钮确认，更不容易误刻。",
    unknown: (c) => `没有这个命令：${c}。输入 help 看能用的命令。`,
    busy: "上一条命令还在跑。等它结束，或按 Ctrl+C 停下。",
    ask: "（y 继续 / n 取消）",
    stopped: "已停下。", done: "完成。", failed: (c) => `没有完成（退出码 ${c}）。`,
    demo: "演示模式：命令不会真的运行。", refused: (m) => `服务器没有接受这条命令：${m}。输入 help 看能用的写法。`,
    drives: (d) => `光驱：${d || "没找到"}`, jobs: (n) => `正在跑的任务：${n}`,
  },
  en: {
    title: { win: "PowerShell · disc-probe", bash: "bash · disc-probe" }, close: "Close", real: "Old screen look",
    hello: "disc-probe terminal. Type help for the commands; they take the same path as the buttons on the pages, typed instead of clicked.",
    help: ["read the disc in the drive (read-only)", "measure the rotation", "measure the geometry", "wait while you change discs (read-only)",
      "make a random-data disc image", "make a burn image", "export a DIS preset", "CD probe", "drives and running jobs",
      "clear the screen", "close the terminal"],
    helpNote: "The drive is the one chosen on the pages (--drive to change); the disc kind is DVD (--media to change).",
    noBurn: "Burn from the burn page: holding its button to confirm makes a mistaken burn less likely.",
    unknown: (c) => `No such command: ${c}. Type help for the commands.`,
    busy: "The last command is still running. Wait for it, or press Ctrl+C to stop it.",
    ask: "(y to continue / n to decline)",
    stopped: "Stopped.", done: "Done.", failed: (c) => `Did not finish (exit code ${c}).`,
    demo: "Demo mode: commands are not really run.", refused: (m) => `The server did not accept this command: ${m}. Type help for what works.`,
    drives: (d) => `Drives: ${d || "none found"}`, jobs: (n) => `Running jobs: ${n}`,
  },
};
const ACTIONS = ["info", "timing", "geo", "swap", "random", "image", "disexport", "cdprobe"];
// the help's left column (ASCII, so the columns line up in a monospaced face), in the order of STR.help
const USAGE = ["info", "timing [--speed 8x]", "geo [--speed 8x] [--media cd]", "swap [--minutes 5]", "random --sectors N",
  "image --geo latest --picture PATH", "disexport --geo latest --sectors N", "cdprobe --sectors N", "status", "clear", "exit"];
let api, $, W = null, onClose = null, job = null, ask = null, history = [], back = 0;
const T = () => STR[api.lang() === "en" ? "en" : "zh"];
const kind = () => (/^win/i.test(api.platform?.() ?? "") ? "win" : "bash");
const prompt = () => (kind() === "win" ? "PS disc-probe> " : "disc-probe:~$ ");

function build() {
  const css = document.createElement("link");
  css.rel = "stylesheet"; css.href = new URL("./terminal.css", import.meta.url).href;
  const ready = new Promise((ok) => { css.onload = ok; css.onerror = ok; });
  document.head.append(css);
  W = document.createElement("section");
  W.className = "term"; W.hidden = true; W.setAttribute("role", "dialog");
  W.innerHTML = `
    <div class="term-bezel">
      <div class="term-bar"><span class="term-title"></span>
        <label class="term-real"><input type="checkbox"><span></span></label>
        <button type="button" class="term-close"></button></div>
      <div class="term-screen">
        <div class="term-out" role="log" aria-live="polite"></div>
        <label class="term-line"><span class="term-ps"></span><input class="term-in" spellcheck="false" autocomplete="off" autocapitalize="off"></label>
      </div>
      <div class="term-fx" aria-hidden="true"></div>
    </div>`;
  document.body.append(W);
  const q = (s) => W.querySelector(s);
  Object.assign(W, { out: q(".term-out"), input: q(".term-in"), screen: q(".term-screen"), real: q(".term-real input") });
  try { W.real.checked = localStorage.getItem("dp-term-real") === "1"; } catch {}
  W.classList.toggle("real", W.real.checked);
  W.real.addEventListener("change", () => {
    W.classList.toggle("real", W.real.checked);
    try { localStorage.setItem("dp-term-real", W.real.checked ? "1" : "0"); } catch {}
  });
  q(".term-close").addEventListener("click", close);
  W.screen.addEventListener("click", () => { if (!getSelection()?.toString()) W.input.focus({ preventScroll: true }); });
  W.input.addEventListener("keydown", key);
  addEventListener("keydown", (e) => { if (e.key === "Escape" && isOpen()) { e.preventDefault(); close(); } });
  return ready;
}
function words() {
  const t = T();
  W.dataset.shell = kind();
  W.setAttribute("aria-label", t.title[kind()]);
  W.querySelector(".term-title").textContent = t.title[kind()];
  W.querySelector(".term-real span").textContent = t.real;
  W.querySelector(".term-close").textContent = t.close;
  W.querySelector(".term-ps").textContent = ask ? `${ask.question} ${t.ask} ` : prompt();
}

// ---------------------------------------------------------------- output
// The 16 terminal colours, per look (Campbell for PowerShell, Tango for bash), for the core's plain codes.
const PALETTE = {
  win: ["#0c0c0c", "#c50f1f", "#13a10e", "#c19c00", "#0037da", "#881798", "#3a96dd", "#cccccc",
        "#767676", "#e74856", "#16c60c", "#f9f1a5", "#3b78ff", "#b4009e", "#61d6d6", "#f2f2f2"],
  bash: ["#2e3436", "#cc0000", "#4e9a06", "#c4a000", "#3465a4", "#75507b", "#06989a", "#d3d7cf",
         "#555753", "#ef2929", "#8ae234", "#fce94f", "#729fcf", "#ad7fa8", "#34e2e2", "#eeeeec"],
};
// a line with SGR codes to spans: bold, dim, the 16 colours and 24-bit colour (the core's rainbow)
function painted(ansi) {
  const frag = document.createDocumentFragment(), pal = PALETTE[kind()];
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
function print(text, cls = "", ansi = null) {
  const line = document.createElement("div");
  line.className = "term-row" + (cls ? " " + cls : "");
  if (ansi) line.append(painted(ansi)); else line.textContent = text;
  W.out.append(line);
  while (W.out.childElementCount > 2000) W.out.firstElementChild.remove();
  W.screen.scrollTop = W.screen.scrollHeight;
  return line;
}
// The core's colours (ui.py): OKLCH, its rainbow in 48 hue steps (ui._tone), its timings.
function oklch(l, c, h) {
  const a = c * Math.cos(2 * Math.PI * h), b = c * Math.sin(2 * Math.PI * h);
  const L = (l + .3963377774 * a + .2158037573 * b) ** 3, M = (l - .1055613458 * a - .0638541728 * b) ** 3, S = (l - .0894841775 * a - 1.291485548 * b) ** 3;
  return [4.0767416621 * L - 3.3077115913 * M + .2309699292 * S, -1.2684380046 * L + 2.6097574011 * M - .3413193965 * S, -.0041960863 * L - .7034186147 * M + 1.707614701 * S]
    .map((v) => Math.round(255 * Math.min(1, v <= 0 ? 0 : v < .0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - .055)));
}
const tone = (pos, lift = 0) => { const h = Math.round((((pos % 1) + 1) % 1) * 48) % 48, lv = 3, lf = Math.round(lift * 2) / 2;
  const [r, g, b] = oklch(.68 + .1 * lf, (.05 + .025 * lv) * (1 - .3 * lf), .08 + h / 48); return `rgb(${r}, ${g}, ${b})`; };
const BAR = 20, CELLS = 4, SPIN = ["◐", "◓", "◑", "◒"], SPIN_S = .12, GLINT_EVERY = 4, GLINT_SWEEP = 1.2, GLINT_REACH = 2,
  SWEEP_S = 1.7, SWEEP_REACH = 4, FLASH_S = .4;
let prog = null;          // the last progress event and the state of its drawing
function progress(e) {
  const now = performance.now() / 1000;
  const pct = `${Math.floor(Math.max(0, Math.min(1, e.fraction ?? 0)) * 100 + 1e-9)}%`.padStart(4);
  if (!prog || !prog.line.isConnected) {
    prog = { line: print("", "progress"), started: now, pct, changed: -1, lit: new Set() };
    prog.raf = 0;
  }
  if (pct !== prog.pct) {
    prog.lit = new Set([...pct].map((ch, i) => (ch !== prog.pct[i] ? i : -1)).filter((i) => i >= 0));
    prog.pct = pct; prog.changed = now;
  }
  prog.e = e;
  drawProgress();
  if (!api.reduce && !prog.raf) { const tick = () => { if (!prog?.line.isConnected || !job) { if (prog) prog.raf = 0; return; } drawProgress(); prog.raf = setTimeout(tick, 70); }; prog.raf = setTimeout(tick, 70); }
}
function drawProgress() {
  const { e, line } = prog, now = performance.now() / 1000, still = api.reduce;
  const f = Math.max(0, Math.min(1, e.fraction ?? 0)), halves = Math.floor(f * BAR * 2), filled = Math.floor(halves / 2);
  const parts = [];
  const put = (text, color, extra = {}) => parts.push({ text, color, ...extra });
  if (!still) put(SPIN[Math.floor((now - prog.started) / SPIN_S) % 4] + " ", tone(now * .1));
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
  const flash = !still && now - prog.changed < FLASH_S;
  [...prog.pct].forEach((ch, i) => put(ch, prog.pct.trim() === "100%" ? PALETTE[kind()][10] : flash && prog.lit.has(i) ? tone(.75) : null, { bold: flash && prog.lit.has(i) }));
  if (Number.isFinite(e.eta_s) && e.eta_s > 0) put(`  ${Math.floor(e.eta_s / 60)}:${String(Math.round(e.eta_s % 60)).padStart(2, "0")}`, null, { dim: true });
  line.replaceChildren(...parts.map((p) => { const s = document.createElement("span"); s.textContent = p.text; if (p.color) s.style.color = p.color; if (p.dim) s.style.opacity = ".55"; if (p.bold) s.style.fontWeight = "700"; return s; }));
}

// ---------------------------------------------------------------- input
function key(e) {
  if (e.key === "Enter") { e.preventDefault(); const line = W.input.value; W.input.value = ""; enter(line); return; }
  if (e.key === "ArrowUp" || e.key === "ArrowDown") {
    if (!history.length) return;
    e.preventDefault();
    back = Math.max(0, Math.min(history.length, back + (e.key === "ArrowUp" ? 1 : -1)));
    W.input.value = back ? history[history.length - back] : "";
    return;
  }
  if ((e.key === "c" || e.key === "C") && e.ctrlKey && !W.input.selectionEnd) {
    e.preventDefault();
    if (job) { print("^C"); stop(); }
  }
}
// "a b --x 'c d'" to words, quotes kept together
function split(line) {
  const out = []; let cur = "", q = null, any = false;
  for (const ch of line) {
    if (q) { if (ch === q) q = null; else cur += ch; continue; }
    if (ch === '"' || ch === "'") { q = ch; any = true; continue; }
    if (/\s/.test(ch)) { if (cur || any) out.push(cur); cur = ""; any = false; continue; }
    cur += ch;
  }
  if (cur || any) out.push(cur);
  return out;
}
async function enter(line) {
  const t = T();
  if (ask) {                                 // answering the core's question
    const yes = /^\s*y(es)?\s*$/i.test(line) || (!line.trim() && ask.default === true);
    print(`${ask.question} ${t.ask} ${line}`, "echo");
    const a = ask; ask = null; words();
    try { await api.backend.answer(a.job, a.id, yes); } catch (err) { print(api.backend.errorText(err, api.lang()), "error"); }
    return;
  }
  print(prompt() + line, "echo");
  const w = split(line.trim());
  if (!w.length) return;
  history.push(line.trim()); back = 0;
  // "discprobe info", "python -m discprobe info" and "info" are the same command
  while (w.length && /^(python3?|py|-m|-P|discprobe|disc-probe)$/i.test(w[0])) w.shift();
  const [cmd, ...rest] = w;
  if (!cmd) return;
  if (/^(help|\?|-h|--help)$/i.test(cmd)) {
    const pad = Math.max(...USAGE.map((u) => u.length)) + 3;
    USAGE.forEach((u, i) => print(u.padEnd(pad) + t.help[i], "dim"));
    print(t.helpNote, "dim");
    return;
  }
  if (/^(clear|cls)$/i.test(cmd)) { W.out.replaceChildren(); return; }
  if (/^(exit|quit)$/i.test(cmd)) { close(); return; }
  if (/^status$/i.test(cmd)) { await status(); return; }
  if (/^burn$/i.test(cmd)) { print(t.noBurn, "warn"); return; }
  if (!ACTIONS.includes(cmd)) { print(t.unknown(cmd), "error"); return; }
  if (job) { print(t.busy, "warn"); return; }
  const payload = { action: cmd, media: "dvd", args: {} };
  for (let i = 0; i < rest.length; i++) {
    const m = /^--([a-z][a-z0-9-]*)(?:=(.*))?$/i.exec(rest[i]);
    if (!m) { print(`? ${rest[i]}`, "error"); return; }
    const name = m[1].toLowerCase().replace(/-/g, "_");
    let value = m[2] ?? rest[++i];
    if (value === undefined) { print(`--${m[1]} ?`, "error"); return; }
    if (/^-?\d+(\.\d+)?$/.test(value)) value = Number(value);
    if (name === "drive") payload.drive = String(value);
    else if (name === "media") payload.media = String(value).toLowerCase();
    else payload.args[name] = value;
  }
  if (["info", "timing", "geo", "swap"].includes(cmd)) payload.drive ??= api.selectedDrive?.();
  await run(payload);
}
async function status() {
  const t = T();
  if (api.backend.mock) { print(t.demo, "dim"); print(t.drives("H: HL-DT-ST GH70N")); print(t.jobs(0)); return; }
  try {
    const s = await api.backend.state();
    print(t.drives((s.drives ?? []).map((d) => (d.name && d.name !== d.id ? `${d.id} ${d.name}` : d.id)).join(", ")));
    print(t.jobs((s.jobs ?? []).filter((j) => j.exit === null).length));
  } catch (err) { print(api.backend.errorText(err, api.lang()), "error"); }
}
async function run(payload) {
  const t = T();
  if (api.backend.mock) {                    // the mock has no core behind it
    print(t.demo, "dim");
    if (payload.action === "info") ["Drive: HL-DT-ST GH70N  (H:)", "Disc: DVD-R, blank", "MID: MCC 004 (Verbatim)", "Sectors: 2,295,104"].forEach((l) => print(l));
    else if (["timing", "geo", "random", "image"].includes(payload.action)) {
      job = { id: "demo" }; prog = null;
      const t0 = performance.now();
      await new Promise((done) => {
        const step = () => {
          const f = Math.min(1, (performance.now() - t0) / 6000);
          progress({ fraction: f, stage: payload.action === "geo" ? "measuring the geometry" : "reading", eta_s: (1 - f) * 6 });
          if (f < 1) setTimeout(step, 250); else done();
        };
        step();
      });
      job = null;
      print("", "", "\x1b[32mDone.\x1b[0m \x1b[2m(demo)\x1b[0m");
    }
    return;
  }
  job = { id: null };
  prog = null;
  try {
    await api.backend.job(payload, (e) => {
      if (e.type === "started") job.id = e.job;
      else if (e.type === "log") print(e.text, e.level === "error" ? "error" : e.level === "warn" || e.level === "warning" ? "warn" : "", e.ansi);
      else if (e.type === "progress") progress(e);
      else if (e.type === "ask") { ask = { job: e.job, id: e.id, question: e.question, default: e.default }; words(); }
      else if (e.type === "stopped") print(t.stopped, "warn");
    });
    print(t.done, "ok");
  } catch (err) {
    // 400: the server's whitelist said no (an action or option it does not take); 422: the command ran and failed
    print(err.status === 400 ? t.refused(err.message) : err.status === 422 ? t.failed(String(err.message).match(/\((-?\d+)\)/)?.[1] ?? "?")
      : api.backend.errorText(err, api.lang()), "error");
  } finally {
    job = null; ask = null; words();
  }
}
async function stop() {
  if (!job?.id) return;
  try { await api.backend.cancel(job.id); } catch (err) { print(api.backend.errorText(err, api.lang()), "error"); }
}

// ---------------------------------------------------------------- in and out
export async function open(homeApi, { closed = null } = {}) {
  api = homeApi; $ = api.$; onClose = closed;
  if (!W) { await build(); print(T().hello, "dim"); }
  words();
  W.hidden = false;
  if (!api.reduce) W.animate([{ transform: "translateY(calc(-100% - 140px))" }, { transform: "none" }], { duration: 560, easing: "cubic-bezier(.2, .8, .2, 1)" });
  setTimeout(() => W.input.focus({ preventScroll: true }), api.reduce ? 0 : 420);
}
export async function close() {
  if (!isOpen()) return;
  if (!api.reduce) await W.animate([{ transform: "none" }, { transform: "translateY(calc(-100% - 140px))" }], { duration: 380, easing: "cubic-bezier(.5, 0, .9, .5)" }).finished;
  W.hidden = true;
  onClose?.();
}
export const isOpen = () => !!W && !W.hidden;
