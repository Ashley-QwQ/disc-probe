// The terminal: what opens when the monitor in the lobby is clicked. The screen lights up (a baked layer,
// lobby.js), then a console slides down from the top, dressed as the shell of the machine the core runs
// on (PowerShell on Windows, bash elsewhere), with an optional worn-screen look.
//
// It is not a shell. A typed line is read as a disc-probe command and sent to the same job runner the
// pages use (/api/run): the same whitelist of actions and options, checked by the server, so nothing
// can be run here that a page could not run. The core's output comes back line by line (log events),
// its progress on one updating line, and its questions are answered by typing y or n. Burning stays on
// the burn page, where it is confirmed by holding the button.

import { PALETTE, painted, progressLine } from "./core-render.js";

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
// the core's colours and its progress line (core-render.js), in this machine's shell palette
function print(text, cls = "", ansi = null) {
  const line = document.createElement("div");
  line.className = "term-row" + (cls ? " " + cls : "");
  if (ansi) line.append(painted(ansi, PALETTE[kind()])); else line.textContent = text;
  W.out.append(line);
  while (W.out.childElementCount > 2000) W.out.firstElementChild.remove();
  W.screen.scrollTop = W.screen.scrollHeight;
  return line;
}
let prog = null;          // the job's progress line
function progress(e) {
  if (!prog || !prog.line.isConnected)
    prog = progressLine(print("", "progress"), { reduce: () => api.reduce, alive: () => !!job, pal: () => PALETTE[kind()] });
  prog.update(e);
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
