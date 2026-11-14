// Disc Lab desk page: a translator between a person and `python -m disclab ... --json`.
//
// Everything shown comes from the server's /api/status (that is `disclab status --json`) and from the
// replies of the commands a button starts (/api/run -> one `disclab <command> --lab LAB --json` process).
// Nothing is remembered here except per-viewer conveniences (theme, language) in localStorage.
//
// The desk has three things (art: disc-probe's lobby desk, art/desk + build_lab.py):
//   the basket of discs   the lab's virtual discs: what each holds, which is in the tray, a new basket
//   the burner            the virtual drive: reader, tray, faults; and the practice steps, in disc-probe's order
//   the phone             renders photos of a burned disc, reads L from them, says how far L is from the truth
// plus disc-probe's floor lamp (light / dark).

const $ = (id) => document.getElementById(id);
const root = document.documentElement;
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
let lang = "zh";
try { lang = localStorage.getItem("disclab-lang") || "zh"; } catch {}
const tr = (zh, en) => (lang === "en" ? en : zh);
let reduce = root.dataset.motion === "off";

// ------------------------------------------------------------------ words
const W = {
  basket: ["光盘箩", "Disc basket"], burner: ["刻录机", "Burner"], phone: ["手机", "Phone"],
  lamp_on: ["开灯", "Lights on"], lamp_off: ["关灯", "Lights off"],
  state: { blank: ["空白", "blank"], burned: ["已刻", "written"], open: ["未封口", "open session"], partial: ["刻了一半", "partly written"] },
  used: { measure_burn: ["测量盘", "measurement disc"], check_burn: ["检查盘", "check disc"], final_burn: ["成品", "final disc"] },
  readers: { gh70n: ["GH70N 类（恒定角速度，稳）", "GH70N-like (CAV, steady)"], "slim-clv": ["超薄光驱（恒定线速度）", "slim drive (CLV)"],
    nofua: ["不认 FUA 的光驱", "ignores FUA"], noisy: ["读数抖动大的光驱", "noisy timing"] },
  faults: { read_error: ["读错误（划痕）", "read error (scratch)"], spindle_unsteady: ["转速不稳", "unsteady spindle"],
    capacity_misreport: ["容量报错", "misreported capacity"], burn_interrupt: ["刻录中断", "burn interrupted"] },
  styles: { flash: ["闪光灯，盘放桌上", "flash, disc on a table"], handheld: ["手拿着，室内灯下", "handheld under a room lamp"] },
};
const w = (pair) => (pair ? tr(pair[0], pair[1]) : "");
// Lab messages are written "中文 / English": show the half in the page's language
const pick = (t) => { t = String(t ?? ""); const i = t.indexOf(" / "); return i < 0 ? t : lang === "en" ? t.slice(i + 3) : t.slice(0, i); };
// the reader's reasons, in the words disc-probe's phone page uses (web/home/guidance.mjs photoReasons)
const REASONS = {
  ok: ["照片可以用。", "The photo is usable."],
  no_rim: ["把整张盘拍进画面，四周留一点边。", "Keep the whole disc in frame with a little space around it."],
  too_few_votes: ["转动盘，移动灯光，让条纹更清楚。", "Turn the disc and move the light to make the pattern clearer."],
  few_inliers: ["转动盘，再拍一张清楚的条纹。", "Turn the disc and take another clear photo of the pattern."],
  rings_not_found: ["把整张盘拍进画面，移动灯光让圆环清楚。", "Keep the whole disc in frame and move the light to show the rings."],
  weak_peak: ["条纹太弱。移动灯光，轻点盘面使相机对焦。", "The pattern is faint. Move the light and tap the disc to focus."],
  two_peaks: ["有两个可能的位置。转动盘，换个角度重拍。", "Two positions look possible. Turn the disc and retake from another angle."],
  poor_angle_coverage: ["转动盘，让更多方向的条纹出现在画面里。", "Turn the disc to show the pattern in more directions."],
  poor_radius_coverage: ["把整张盘拍进画面，让内圈和外圈都清楚。", "Keep the whole disc in frame so both inner and outer rings are clear."],
  large_residual: ["条纹位置对不上。把盘放平，拍全盘。", "The pattern does not fit. Lay the disc flat and photograph the whole disc."],
  unstable_L: ["这张照片的位置读数不稳定。转动盘重拍。", "The position reading varies within this photo. Turn the disc and retake."],
  shape_not_1_over_r: ["内外圈的读数对不上。拍全盘，移动灯光后重拍。", "Inner and outer readings disagree. Keep the whole disc in frame and move the light."],
  duplicate_photo: ["这张照片重复了。转动盘，拍一张不同角度的。", "This photo is a duplicate. Turn the disc and take a different view."],
};
// which steps need what in the tray
const NEEDS_BLANK = new Set(["blank", "measure_image", "measure_burn", "check_burn", "final_burn"]);
const NEEDS_MEASURED = new Set(["timing", "geo"]);
const BURNS = new Set(["measure_burn", "check_burn", "final_burn"]);
// burner page art: disc-probe's burner (web/home/burner.json): the tray slides by tray_slide_px * t (t 1 = closed)
const BURNER = { size: [1600, 1062], slide: [438.666, -253.264],
  // the render's slot clip, its slanted top edge extended (as disc-probe does) so the closed tray's front stays
  clip: [[876.84, 706.17], [-4384.2, -2331.27], [-4384.2, 4248], [876.84, 4248]] };

// ------------------------------------------------------------------ state
let S = null;            // outputs.status of `disclab status --json`
let LAB = "";            // the lab folder (the reply's `lab`)
let SCORES = {};
let mode = "";           // "" lobby, "basket", "burner", "phone"
let job = null;          // the running command, as /api/job reports it
let picture = null;      // a picture chosen on the burner page for 放进图片 / 生成成品 (a step argument)
let shoot = { n: 3, style: "flash", disc: null };
let M = null, L = {};    // lobby art: lobby.json and the built nodes

async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
async function refresh() {
  const r = await api("/api/status");
  if (r.status !== "ok") { toast((r.errors || []).map((e) => e.message).join(" ")); return; }
  S = r.outputs.status; LAB = r.lab; SCORES = r.scores || {};
  if (r.busy && !job && r.busy.id !== lastJob) watch(r.busy.id);
  paint();
}
function file(path, wpx) { return `/api/file?path=${encodeURIComponent(path)}${wpx ? `&w=${wpx}` : ""}`; }

// run one disclab command; long ones become a job the footer shows
let pending = false;      // a quick command is on its way: the next button waits for its reply
async function run(argv, { quiet = false } = {}) {
  pending = true; paintNext();
  try {
    const r = await api("/api/run", { argv });
    if (r.job) { watch(r.job); return; }
    if (r.status !== "ok") toast(errText(r));
    else if (!quiet) toast(tr("好了。", "Done."));
    await refresh();
    return r;
  } catch (e) { toast(e.message); }
  finally { pending = false; paintNext(); }
}
function errText(r) { return (r?.errors || []).map((e) => pick(e.message)).filter(Boolean).join(" ") || tr("没有成功。", "It did not work."); }
let lastJob = null;
function watch(id) {
  lastJob = id;
  job = { id, state: "running", argv: [], log: "", t0: Date.now() / 1000 };
  paintJob();
  const tick = async () => {
    try { job = await api(`/api/job/${id}`); } catch { setTimeout(tick, 1500); return; }
    paintJob();
    if (job.state === "running") { setTimeout(tick, 700); return; }
    const done = job;
    if (done.state === "failed") toast(errText(done.result));
    else if (done.argv[0] === "box") toast(tr("新的一箩建好了，第一张已经放进光驱。", "New basket made; its first disc is in the drive."));
    // read the new state before the next button comes back, or it would offer the step just run again
    await refresh().catch(() => {});
    job = null; paintJob(); paint();
  };
  setTimeout(tick, 400);
}

// ------------------------------------------------------------------ the flow
const stepBy = (k) => S?.flow.find((s) => s.key === k);
const current = () => S?.flow.find((s) => s.current) || null;
const drive = () => { const [name, d] = Object.entries(S?.drives || {})[0] || []; return name ? { name, ...d } : null; };
const discRow = (id) => S?.box.discs.find((d) => d.id === id);
const measureDisc = () => S?.box.discs.find((d) => d.used_for === "measure_burn")?.id;
const discName = (id) => {
  const d = discRow(id); if (!d) return id || "";
  const used = d.used_for ? `${w(W.used[d.used_for])}，` : "";
  return `${id}（${used}${w(W.state[d.state])}）`;
};
function stepArgs(key) {
  const a = ["step", key];
  if ((key === "picture" || key === "final") && picture) a.push("--picture", picture);
  if (key === "photos") a.push("--photos", String(shoot.n), "--style", shoot.style);
  return a;
}
// What "next" does from here: disc-probe's fixed corner. Its words say the action, its why says what blocks it.
function nextAction() {
  if (!S) return { label: "…", disabled: true };
  if (pending && !job) return { label: tr("稍等…", "One moment…"), disabled: true };
  if (job) return { label: tr("正在", "Running: ") + jobName(job), disabled: true, why: tr("可以关掉网页，命令在电脑上继续。", "You can close the page; the command keeps running.") };
  const c = current();
  if (!c) {
    if (mode !== "basket") return { label: tr("看和真值差多少", "See how far from the truth"), go: "basket" };
    return { label: tr("建一箩新的再练", "Make a new basket"), act: () => document.querySelector("#newbox")?.scrollIntoView({ behavior: "smooth" }) };
  }
  const place = c.place;
  if (mode === "" || mode !== place) {
    const where = w(W[place]);
    return { label: `${tr("下一步：", "Next: ")}${tr(c.zh, c.en)}`, go: place, why: mode ? tr(`在${where}上做`, `On the ${where.toLowerCase()}`) : "" };
  }
  const d = drive();
  if (NEEDS_BLANK.has(c.key)) {
    if (!d?.tray || d.open || d.tray_state !== "blank") {
      return { label: tr("换一张空白盘", "Swap in a blank"), act: () => run(["swap"], { quiet: true }),
        why: d?.tray ? tr(`${d.tray} 已经刻过了，先换一张这批的空白盘`, `${d.tray} is written; swap in a blank from this batch`) : tr("托盘是空的", "The tray is empty") };
    }
  }
  if (NEEDS_MEASURED.has(c.key)) {
    const m = measureDisc();
    if (m && d?.tray !== m) return { label: tr("放回测量盘", "Put the measurement disc back"), act: () => run(["tray", "--disc", m], { quiet: true }) };
  }
  if (BURNS.has(c.key)) return { label: tr(`按住刻录：${c.zh}`, `Hold to burn: ${c.en}`), hold: () => run(stepArgs(c.key)),
    why: tr(`刻到 ${d.tray}，刻录不能撤销`, `Onto ${d.tray}; a burn cannot be undone`) };
  if (c.key === "photos" && S.photo && S.photo.offset_mm == null)      // the last reading gave no L: more photos, they add up
    return { label: tr(`再拍 ${shoot.n} 张`, `Take ${shoot.n} more`), act: () => run(stepArgs(c.key)),
      why: tr("换个角度，新照片和之前的一起读", "From other angles; read together with the earlier ones") };
  return { label: tr(c.zh, c.en), act: () => run(stepArgs(c.key)) };
}
function jobName(j) {
  const a = j.argv || [];
  if (a[0] === "step") return (stepBy(a[1]) ? tr(stepBy(a[1]).zh, stepBy(a[1]).en) : a[1]) + "…";
  if (a[0] === "photos") return tr("拍摄光盘…", "photographing…");
  if (a[0] === "box") return tr("建新的一箩…", "making a basket…");
  return a.join(" ") + "…";
}

// ------------------------------------------------------------------ painting
function paint() {
  if (!S) return;
  paintChrome();
  paintLobby();
  if (mode) paintPage();
  paintNext();
}
function paintChrome() {
  $("lang").textContent = lang === "en" ? "中文" : "EN";
  $("lang").setAttribute("aria-label", tr("Switch to English", "切换到中文"));
  $("theme").setAttribute("aria-label", tr("切换纸色 / 墨色", "Switch paper / ink"));
  $("back").setAttribute("aria-label", tr("回到桌面", "Back to the desk"));
  $("back").hidden = !mode;
  root.lang = lang === "en" ? "en" : "zh-CN";
  const d = drive();
  $("drive").innerHTML = d ? `<b>${esc(d.name)}</b> · ${d.tray ? esc(discName(d.tray)) : tr("托盘空着", "tray empty")}${d.open ? tr(" · 托盘开着", " · tray open") : ""}` : "";
}
function paintJob() {
  const on = !!job;
  $("job").hidden = !on;
  if (on) {
    const s = Math.max(0, Math.round((job.t1 || Date.now() / 1000) - job.t0));
    $("job-t").textContent = `${jobName(job)} ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    $("job-log").textContent = tr("看日志", "Log");
    const pre = document.querySelector("#log pre"); if (pre) { pre.textContent = job.log || ""; pre.scrollTop = pre.scrollHeight; }
  }
  paintNext();
}
let holdT = null;
function paintNext() {
  const n = nextAction(), b = $("next");
  b.disabled = !!n.disabled;
  b.innerHTML = (n.hold ? `<span class="hold-ring" aria-hidden="true"></span>` : "") + `<span>${esc(n.label)}</span>` +
    (n.hold || n.disabled ? "" : `<svg class="icon i-chev"><use href="#i-chev"/></svg>`);
  $("why").textContent = n.why || "";
  b.onclick = null; b.onpointerdown = b.onpointerup = b.onpointerleave = b.onkeydown = b.onkeyup = null;
  if (n.disabled) return;
  if (n.hold) {
    const ring = b.querySelector(".hold-ring");
    // a timer, not animation frames: frames stop in a background tab, and the hold must still end
    const start = () => {
      if (holdT) return;
      const t0 = performance.now();
      holdT = setInterval(() => {
        const p = Math.min(1, (performance.now() - t0) / 1000);
        ring.style.setProperty("--p", p.toFixed(3));
        if (p >= 1) { clearInterval(holdT); holdT = null; ring.style.setProperty("--p", 0); n.hold(); }
      }, 16);
    };
    const stop = () => { if (holdT) clearInterval(holdT); holdT = null; ring.style.setProperty("--p", 0); };
    b.onpointerdown = start; b.onpointerup = stop; b.onpointerleave = stop;
    b.onkeydown = (e) => { if ((e.key === "Enter" || e.key === " ") && !e.repeat) { e.preventDefault(); start(); } };
    b.onkeyup = (e) => { if (e.key === "Enter" || e.key === " ") stop(); };
    b.onclick = () => { if (!holdT) toast(tr("按住约 1 秒，等彩虹转满一圈。", "Hold for about a second, until the rainbow goes round.")); };
    return;
  }
  b.onclick = () => (n.go !== undefined ? go(n.go) : n.act?.());
}

// ------------------------------------------------------------------ lobby (as disc-probe's lobby.js)
function quadMatrix(wd, h, [[x0, y0], [x1, y1], [x2, y2], [x3, y3]]) {
  const dx1 = x1 - x2, dx2 = x3 - x2, dx3 = x0 - x1 + x2 - x3, dy1 = y1 - y2, dy2 = y3 - y2, dy3 = y0 - y1 + y2 - y3;
  let g = 0, k = 0;
  if (Math.abs(dx3) > 1e-9 || Math.abs(dy3) > 1e-9) { const den = dx1 * dy2 - dx2 * dy1; g = (dx3 * dy2 - dx2 * dy3) / den; k = (dx1 * dy3 - dx3 * dy1) / den; }
  const a = x1 - x0 + g * x1, b = x3 - x0 + k * x3, d = y1 - y0 + g * y1, e = y3 - y0 + k * y3;
  return `matrix3d(${[a / wd, d / wd, 0, g / wd, b / h, e / h, 0, k / h, 0, 0, 1, 0, x0, y0, 0, 1].map((v) => +v.toFixed(8)).join(",")})`;
}
const dist = ([ax, ay], [bx, by]) => Math.hypot(bx - ax, by - ay);
const theme = () => (root.dataset.theme === "dark" ? "dark" : "paper");

async function buildLobby() {
  M = await (await fetch("lobby/lobby.json")).json();
  const [Wd, H] = M.size;
  const world = document.createElement("div");
  world.className = "lb-world"; world.style.width = `${Wd}px`; world.style.height = `${H}px`;
  const ds = M.layers.map((l) => l.depth ?? 0), dn = Math.min(...ds), df = Math.max(...ds);
  const reach = (d) => (df > dn ? 1 - (2 / 3) * ((d - dn) / (df - dn)) : 1 / 3);
  L.layer = {};
  for (const l of M.layers) {
    const g = document.createElement("div");
    g.className = "lb-layer"; g.dataset.name = l.name; g.style.setProperty("--reach", reach(l.depth ?? 0).toFixed(3));
    const img = document.createElement("img");
    img.alt = ""; img.draggable = false; img.decoding = "async";
    const [x0, y0, x1, y1] = l.box;
    Object.assign(img.style, { left: `${x0}px`, top: `${y0}px`, width: `${x1 - x0}px`, height: `${y1 - y0}px` });
    g.append(img); world.append(g); L.layer[l.name] = g;
  }
  const svgNS = "http://www.w3.org/2000/svg";
  for (const [key, t] of Object.entries(M.targets)) {
    const home = L.layer[t.layer] || L.layer.base;
    const g = document.createElement("div");
    g.className = "lb-layer"; g.style.setProperty("--reach", home.style.getPropertyValue("--reach"));
    const pts = t.hotspot, xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const [bx, by, bw, bh] = [Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)];
    const btn = document.createElement("button");
    btn.type = "button"; btn.className = "lb-hit"; btn.dataset.target = key;
    Object.assign(btn.style, { left: `${bx}px`, top: `${by}px`, width: `${bw}px`, height: `${bh}px`,
      clipPath: `polygon(${pts.map(([x, y]) => `${(x - bx).toFixed(1)}px ${(y - by).toFixed(1)}px`).join(",")})` });
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("class", "lb-outline"); svg.setAttribute("viewBox", `${bx} ${by} ${bw} ${bh}`);
    Object.assign(svg.style, { left: `${bx}px`, top: `${by}px`, width: `${bw}px`, height: `${bh}px` });
    const poly = document.createElementNS(svgNS, "polygon"); poly.setAttribute("points", pts.map((p) => p.join(",")).join(" "));
    svg.append(poly);
    g.append(btn, svg);
    if (t.screen) {        // the phone's screen shows the newest rendered photo
      const q = t.screen, sw = dist(q[0], q[1]), sh = dist(q[0], q[3]);
      const s = document.createElement("div");
      s.className = "lb-screen"; s.dataset.target = key;
      Object.assign(s.style, { width: `${sw}px`, height: `${sh}px`, transform: quadMatrix(sw, sh, q) });
      s.append(Object.assign(document.createElement("img"), { alt: "" }));
      g.append(s); L.screen = s;
    }
    if (t.label) {
      const q = t.label.quad, lw = dist(q[0], q[1]), lh = dist(q[0], q[3]);
      const lab = document.createElement("span");
      lab.className = "lb-label"; lab.dataset.target = key; lab.setAttribute("aria-hidden", "true");
      Object.assign(lab.style, { width: `${lw}px`, height: `${lh}px`, transform: quadMatrix(lw, lh, q) });
      lab.style.setProperty("--h", `${lh}px`);
      lab.append(document.createElement("i"));
      g.append(lab);
    }
    if (key === "lamp") {
      const hint = document.createElement("span");
      hint.className = "lb-lamp-hint"; const [x, y] = M.lamp.bulb;
      Object.assign(hint.style, { left: `${x + 66}px`, top: `${y - 35}px` });
      g.append(hint); L.lampHint = hint;
    }
    world.append(g);
    const hot = (on) => {
      if (t.layer !== "base") L.layer[t.layer]?.classList.toggle("lift", on);
      if (key === "lamp") $("lobby").classList.toggle("lamp-hot", on);
      world.querySelectorAll(`.lb-label[data-target="${key}"], .lb-screen[data-target="${key}"]`).forEach((n) => n.classList.toggle("hot", on));
    };
    btn.addEventListener("pointerenter", () => hot(true)); btn.addEventListener("pointerleave", () => hot(false));
    btn.addEventListener("focus", () => hot(true)); btn.addEventListener("blur", () => hot(false));
    btn.addEventListener("click", () => (key === "lamp" ? toggleTheme() : go(key)));
  }
  $("lobby-art").replaceChildren(world);
  L.world = world;
  paintTheme(); fit(); paintLobby();
  if (matchMedia("(pointer: fine)").matches) {
    addEventListener("pointermove", (e) => {
      if (reduce || mode) return;
      const dx = (e.clientX / innerWidth - 0.5) * 2, dy = (e.clientY / innerHeight - 0.5) * 2;
      for (const g of world.children) { const r = +g.style.getPropertyValue("--reach") || 0.33; g.style.transform = `translate(${(-dx * 7 * r).toFixed(2)}px, ${(-dy * 5 * r).toFixed(2)}px)`; }
    });
  }
}
function fit() {
  if (!M || !L.world) return;
  const [Wd, H] = M.size, vw = innerWidth, vh = innerHeight;
  const k = Math.min(vw / Wd, vh / H) * (vw < 720 ? 1.25 : 1);
  L.k = k; L.ox = (vw - Wd * k) / 2; L.oy = (vh - H * k) / 2;
  L.world.style.transform = `translate(${L.ox.toFixed(1)}px, ${L.oy.toFixed(1)}px) scale(${k.toFixed(5)})`;
}
function paintTheme() {
  if (!M) return;
  for (const l of M.layers) L.layer[l.name].querySelector("img").src = `lobby/${l.name}_${theme()}.webp`;
  if (L.lampHint) L.lampHint.textContent = w(theme() === "dark" ? W.lamp_on : W.lamp_off);
  if (mode) paintHero();
}
function paintLobby() {
  if (!M || !L.world) return;
  for (const n of L.world.querySelectorAll(".lb-label[data-target]")) {
    const k = n.dataset.target; n.firstElementChild.textContent = W[k] ? w(W[k]) : "";
    const i = n.firstElementChild; i.style.fontSize = "";
    const kk = Math.min(1, (n.offsetWidth * 0.86) / (i.offsetWidth || 1), (n.offsetHeight * 0.92) / (i.offsetHeight || 1));
    if (kk < 1) i.style.fontSize = `${kk.toFixed(3)}em`;
  }
  for (const b of L.world.querySelectorAll(".lb-hit")) b.setAttribute("aria-label", b.dataset.target === "lamp" ? w(theme() === "dark" ? W.lamp_on : W.lamp_off) : w(W[b.dataset.target]));
  const shot = latestShots()[0];
  if (L.screen) { const img = L.screen.querySelector("img"); img.hidden = !shot; if (shot) img.src = file(shot, 360); }
  if (!S) return;
  const c = current();
  $("hello").textContent = c ? tr(`现在到这里：${c.zh}`, `You are here: ${c.en}`) : tr("这一轮练完了。去光盘箩看看和真值差多少。", "This round is done. See how far it was from the truth at the basket.");
  const d = drive();
  const bits = [d?.tray ? tr(`托盘里是 ${discName(d.tray)}`, `In the tray: ${d.tray} (${w(W.state[d.tray_state])})`) : tr("托盘空着", "The tray is empty"),
    tr(`箩里还有 ${S.box.blanks} 张空白盘`, `${S.box.blanks} blank discs left in the basket`)];
  if (d?.faults?.length) bits.push(tr(`注入了 ${d.faults.length} 个故障`, `${d.faults.length} fault(s) injected`));
  if (S.quick) bits.push(tr("快练（只测内圈）", "quick practice (inner band only)"));
  $("where").textContent = bits.join(" · ");
}
function latestShots() { const set = S?.photos?.[S.photos.length - 1]; return set ? set.paths.filter((p) => /\.(jpe?g|png)$/i.test(p)) : []; }

// ------------------------------------------------------------------ pages
// ---- transitions, after disc-probe's lobby (lobby.js pushLobby, newplan.js): the camera pushes in on the
// object, the page fades in from close and settles; back plays it in reverse. Page to page pans: next to the
// right, back to the left (DESIGN.md, the Fixed Corners Rule). Off with reduced motion; any click finishes it.
const EASE_IN = "cubic-bezier(.5, 0, .6, 1)", EASE = "cubic-bezier(.2, .8, .2, 1)";
let flight = null;
const PAGE_ORDER = ["basket", "burner", "phone"];
function objectOnScreen(key) {
  const t = M?.targets[key]; if (!t || !L.k) return null;
  const xs = t.hotspot.map((p) => p[0]), ys = t.hotspot.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  return { x: L.ox + (x0 + x1) / 2 * L.k, y: L.oy + (y0 + y1) / 2 * L.k, w: (x1 - x0) * L.k };
}
function finishFlight() { if (flight) { flight.anims.forEach((a) => { try { a.finish(); } catch {} }); } }
function show(m) {
  mode = m || "";
  if (mode) root.dataset.mode = mode; else delete root.dataset.mode;
  $("lobby").hidden = !!mode; $("page").hidden = !mode;
  if (mode) { paintHero(); paintPage(); $("sheet").scrollTop = 0; }
  paint();
  try { history.replaceState(null, "", mode ? `#${mode}` : location.pathname); } catch {}
}
async function go(m) {
  m = m || "";
  if (m === mode) return;
  finishFlight();
  const from = mode, art = $("lobby-art"), page = $("page"), greet = document.querySelector(".lobby-greet");
  if (reduce || !M) { show(m); return; }
  const anims = [], fl = flight = { anims };
  const done = () => Promise.all(anims.map((a) => a.finished)).catch(() => {});
  if (!from && m) {                         // lobby -> page: push in on the object, the page comes up from close
    const obj = objectOnScreen(m);
    show(m);
    const stage = $("hero").querySelector(".stage")?.getBoundingClientRect();
    $("lobby").hidden = false;              // stays drawn under the page until the flight ends
    $("lobby").style.zIndex = "0"; page.style.zIndex = "1";
    if (obj && stage) {
      const hx = stage.left + stage.width / 2, hy = stage.top + stage.height / 2, k = Math.min(4, stage.width / obj.w);
      art.style.transformOrigin = `${obj.x}px ${obj.y}px`;
      anims.push(art.animate([{ transform: "none" }, { transform: `translate(${hx - obj.x}px, ${hy - obj.y}px) scale(${k})` }],
        { duration: 600, easing: EASE_IN, fill: "forwards" }));
      page.style.transformOrigin = `${hx}px ${hy}px`;
      anims.push(page.animate([{ transform: `scale(${1 / Math.max(1.6, k * 0.6)})`, opacity: 0 }, { opacity: 0, offset: .25 },
        { transform: "none", opacity: 1 }], { duration: 820, easing: EASE, fill: "backwards" }));
      anims.push($("sheet").animate([{ translate: "48px 0", opacity: 0 }, { opacity: 0, offset: .35 }, { translate: "0 0", opacity: 1 }],
        { duration: 820, easing: EASE, fill: "backwards" }));
    }
    if (greet) anims.push(greet.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, fill: "forwards" }));
    await done();
    if (flight !== fl) return;
    anims.forEach((a) => a.cancel()); art.style.transformOrigin = page.style.transformOrigin = "";
    $("lobby").hidden = true; $("lobby").style.zIndex = page.style.zIndex = "";
  } else if (from && !m) {                  // page -> lobby: the page lifts off, the camera pulls back out
    const obj = (() => { show(""); fit(); const o = objectOnScreen(from); $("page").hidden = false; return o; })();
    const stage = $("hero").querySelector(".stage")?.getBoundingClientRect();
    page.style.zIndex = "1";
    if (obj && stage) {
      const hx = stage.left + stage.width / 2, hy = stage.top + stage.height / 2, k = Math.min(4, stage.width / obj.w);
      art.style.transformOrigin = `${obj.x}px ${obj.y}px`;
      anims.push(art.animate([{ transform: `translate(${hx - obj.x}px, ${hy - obj.y}px) scale(${k})` }, { transform: "none" }],
        { duration: 600, easing: EASE, fill: "backwards" }));
      page.style.transformOrigin = `${hx}px ${hy}px`;
      anims.push(page.animate([{ transform: "none", opacity: 1 }, { opacity: 0, offset: .6 }, { transform: `scale(${1 / Math.max(1.6, k * 0.6)})`, opacity: 0 }],
        { duration: 520, easing: EASE_IN, fill: "forwards" }));
    }
    if (greet) anims.push(greet.animate([{ opacity: 0 }, { opacity: 0, offset: .4 }, { opacity: 1 }], { duration: 520, fill: "backwards" }));
    await done();
    if (flight !== fl) return;
    anims.forEach((a) => a.cancel()); art.style.transformOrigin = page.style.transformOrigin = "";
    page.hidden = true; page.style.zIndex = "";
  } else {                                  // page -> page: pan; forward along basket, burner, phone goes right
    const dir = PAGE_ORDER.indexOf(m) > PAGE_ORDER.indexOf(from) ? 1 : -1;
    const out = page.animate([{ translate: "0 0", opacity: 1 }, { translate: `${-dir * 6}vw 0`, opacity: 0 }],
      { duration: 200, easing: EASE_IN, fill: "forwards" });
    anims.push(out);
    await out.finished.catch(() => {});
    if (flight !== fl) return;
    show(m);
    out.cancel();
    anims.push(page.animate([{ translate: `${dir * 6}vw 0`, opacity: 0 }, { translate: "0 0", opacity: 1 }],
      { duration: 360, easing: EASE, fill: "backwards" }));
    await done();
  }
  if (flight === fl) flight = null;
}
addEventListener("pointerdown", () => finishFlight(), true);
function paintHero() {
  const h = $("hero"), th = theme();
  if (mode === "burner") {
    // disc-probe's burner (web/home index.html): the body, and the tray sliding along the drive's axis,
    // clipped to the outside of the slot; the tray is out only while the virtual drive's tray is open
    const d = drive(), t = d?.open ? 0 : 1, [bw, bh] = BURNER.size;
    const pct = ([x, y]) => `${(x / bw * 100).toFixed(2)}% ${(y / bh * 100).toFixed(2)}%`;
    const slide = `translate(${(BURNER.slide[0] * t / bw * 100).toFixed(3)}%, ${(BURNER.slide[1] * t / bh * 100).toFixed(3)}%)`;
    const tray = d?.tray ? "traydisc" : "tray";
    h.innerHTML = `<div class="stage" style="--ar:${bw / bh}"><img src="burner/burner_body_${th}.webp" alt="">` +
      `<div style="position:absolute;inset:0;clip-path:polygon(${BURNER.clip.map(pct).join(",")})">` +
      `<img src="burner/burner_${tray}_${th}.webp" alt="" style="transform:${slide}"></div></div>`;
    return;
  }
  const lay = M?.layers.find((l) => l.name === mode);
  if (!lay) { h.innerHTML = ""; return; }
  const [x0, y0, x1, y1] = lay.box, lw = x1 - x0, lh = y1 - y0;
  let extra = "";
  const t = M.targets[mode];
  if (mode === "phone" && t?.screen) {
    const shot = latestShots()[0];
    if (shot) {
      const q = t.screen.map(([x, y]) => [x - x0, y - y0]), sw = dist(q[0], q[1]), sh = dist(q[0], q[3]);
      extra = `<div class="shot" data-w="${sw}" data-h="${sh}" data-q='${JSON.stringify(q)}'><img src="${file(shot, 480)}" alt=""></div>`;
    }
  }
  h.innerHTML = `<div class="stage" style="--ar:${lw / lh};width:min(${mode === "phone" ? 26 : 30}vw, ${mode === "phone" ? 380 : 440}px)"><img src="lobby/${mode}_${th}.webp" alt="">${extra}</div>`;
  const s = h.querySelector(".shot");
  if (s) {
    const stage = h.querySelector(".stage");
    const place = () => { const kk = stage.clientWidth / lw, q = JSON.parse(s.dataset.q).map(([x, y]) => [x * kk, y * kk]); const sw = dist(q[0], q[1]), sh = dist(q[0], q[3]);
      Object.assign(s.style, { width: `${sw}px`, height: `${sh}px`, transform: quadMatrix(sw, sh, q) }); };
    place(); new ResizeObserver(place).observe(stage);
  }
}
function paintPage() {
  const sh = $("sheet");
  const keepLog = sh.querySelector("#log")?.open;
  sh.innerHTML = mode === "burner" ? burnerSheet() : mode === "phone" ? phoneSheet() : basketSheet();
  if (keepLog) sh.querySelector("#log")?.setAttribute("open", "");
  const pre = sh.querySelector("#log pre"); if (pre && job) pre.textContent = job.log || "";
}

function stepList(filter) {
  let html = "", stage = null;
  for (const s of S.flow) {
    if (filter && !filter(s)) continue;
    if (s.stage !== stage) { stage = s.stage; const st = S.stages[stage]; html += `<li class="stage-h">${esc(tr(st.zh, st.en))}</li>`; }
    const cls = s.done ? "done" : s.current ? "here" : s.skip ? "skip" : "";
    const place = s.place !== mode ? `<span class="place">${esc(w(W[s.place]))}</span>` : `<span class="cmd">${esc(s.runs)}</span>`;
    const detail = s.skip ? tr(s.skip.zh, s.skip.en) : s.current ? tr(s.why.zh, s.why.en) + (s.detail ? ` · ${pick(s.detail)}` : "") : pick(s.detail);
    html += `<li class="step ${cls}"><span class="mk"></span><span class="nm">${esc(tr(s.zh, s.en))}${s.current ? ` <span class="note">← ${tr("现在到这里", "you are here")}</span>` : ""}</span>${place}` +
      `<span class="dt">${esc(detail || "")}</span>${s.error ? `<span class="err">${esc(tr("上次没成功：", "Last try failed: ") + pick(s.error))}</span>` : ""}</li>`;
  }
  return `<ul class="steps">${html}</ul>`;
}
function logBlock() {
  return `<details class="log" id="log"><summary>${tr("日志（命令的原始输出）", "Log (the commands' own output)")}</summary><pre>${esc(job?.log || "")}</pre></details>`;
}

function burnerSheet() {
  const d = drive(), c = current();
  const readers = S.readers.map((r) => `<option value="${r}" ${d.reader === r ? "selected" : ""}>${esc(w(W.readers[r]) || r)}</option>`).join("");
  const faults = (d.faults || []).map((f) => `<li><span class="k">${esc(w(W.faults[f.kind]) || f.kind)}</span><span class="p">${esc(JSON.stringify(f.params))}</span>` +
    `<button class="x" data-a="unfault" data-id="${esc(f.id)}" aria-label="${tr("去掉", "Remove")}"><svg class="icon"><use href="#i-x"/></svg></button></li>`).join("");
  const pic = (c && (c.key === "picture" || c.key === "final")) ? `<h3>${tr("用哪张图", "Which picture")}</h3>
    <div class="row"><span>${picture ? esc(picture.split(/[\\/]/).pop()) : tr("Lab 自带的示例图（帆船）", "the Lab's sample (a sailing boat)")}</span>
    <label class="sbtn quiet" style="display:inline-flex;align-items:center">${tr("换一张图片…", "Choose a picture…")}<input type="file" accept="image/*" data-a="pick" hidden></label>
    ${picture ? `<button class="sbtn quiet" data-a="nopick">${tr("用示例图", "Use the sample")}</button>` : ""}</div>` : "";
  const previews = (S.pictures || []).map((p) => ({ key: p.key, png: (p.paths || []).find((x) => /preview\.png$/i.test(x)) })).filter((p) => p.png);
  const prev = previews.length ? `<h3>${tr("预览", "Preview")}</h3><div class="gallery">${previews.map((p) =>
    `<figure><img src="${file(p.png)}" alt="" data-a="zoom" data-src="${esc(file(p.png))}" style="aspect-ratio:1;object-fit:contain"><figcaption>${p.key === "final" ? tr("成品（带 L）", "Final (with L)") : tr("放进图片", "Picture")}</figcaption></figure>`).join("")}</div>` : "";
  return `<h2>${esc(w(W.burner))}</h2>
  <p class="sub">${esc(d.name)} · ${esc(w(W.readers[d.reader]) || d.reader)} · ${d.tray ? esc(tr(`托盘里：${discName(d.tray)}`, `In the tray: ${d.tray}`)) : tr("托盘空着", "Tray empty")}</p>
  <div class="rule"></div>
  ${stepList((s) => s.place === "burner" || s.place === "phone")}
  ${pic}
  ${prev}
  <h3>${tr("托盘", "Tray")}</h3>
  <div class="row">
    <button class="sbtn quiet" data-a="swap">${tr("换一张空白盘", "Swap in a blank")}</button>
    ${d.open ? `<button class="sbtn quiet" data-a="close">${tr("推上托盘", "Close the tray")}</button>` : `<button class="sbtn quiet" data-a="eject">${tr("弹出托盘", "Open the tray")}</button>`}
    ${measureDisc() && d.tray !== measureDisc() ? `<button class="sbtn quiet" data-a="measured">${tr("放回测量盘", "Put the measurement disc back")}</button>` : ""}
  </div>
  <h3>${tr("读盘配置", "Reader")}</h3>
  <div class="row"><select data-a="reader" aria-label="${tr("读盘配置", "Reader")}">${readers}</select></div>
  <p class="note">${tr("换一台“光驱”：转速方式、读数抖动、是否认 FUA 都跟着变。真光驱换了要重拍检查盘。", "A different 'drive': rotation, timing noise and FUA change with it. A changed real drive needs new check-disc photos.")}</p>
  <h3>${tr("注入故障", "Injected faults")}</h3>
  ${faults ? `<ul class="faults">${faults}</ul>` : `<p class="note">${tr("没有。这台光驱现在一切正常。", "None. The drive behaves normally.")}</p>`}
  <div class="row">
    <select data-a="fkind" aria-label="${tr("故障种类", "Fault kind")}">${Object.keys(W.faults).map((k) => `<option value="${k}">${esc(w(W.faults[k]))}</option>`).join("")}</select>
    <span id="fparams">${faultParams("read_error")}</span>
    <button class="sbtn" data-a="fault">${tr("加上", "Add")}</button>
  </div>
  <p class="note">${tr("故障对所有命令一起生效；disc-probe 应该停下来说清原因，而不是给出错的结果。", "Faults act on every command; disc-probe should stop and say why, not give a wrong result.")}</p>
  ${logBlock()}`;
}
function faultParams(kind) {
  const n = (k, v, step, unit) => `<label class="field"><span>${k}</span><input type="number" data-p="${k}" value="${v}" step="${step}" aria-label="${k}">${unit ? "" : ""}</label>`;
  if (kind === "read_error") return `<span class="row" style="margin:0">${n("r_lo", 40, 0.5)}${n("r_hi", 41, 0.5)}<span class="note">mm</span></span>`;
  if (kind === "spindle_unsteady") return `<span class="row" style="margin:0">${n("amplitude", 0.15, 0.05)}${n("rate_hz", 1, 0.5)}</span>`;
  if (kind === "capacity_misreport") return `<span class="row" style="margin:0">${n("offset", -20000, 1000)}<span class="note">${tr("扇区", "sectors")}</span></span>`;
  return `<span class="row" style="margin:0">${n("fraction", 0.5, 0.1)}</span>`;
}
function faultArg() {
  const kind = document.querySelector('[data-a="fkind"]').value, v = (k) => +document.querySelector(`[data-p="${k}"]`).value;
  const p = kind === "read_error" ? { r_mm: [v("r_lo"), v("r_hi")] } : kind === "spindle_unsteady" ? { amplitude: v("amplitude"), rate_hz: v("rate_hz") }
    : kind === "capacity_misreport" ? { offset: Math.round(v("offset")) } : { fraction: v("fraction") };
  return `${kind}:${JSON.stringify(p)}`;
}

function phoneSheet() {
  const c = current(), r = S.photo, shots = latestShots(), set = S.photos[S.photos.length - 1];
  const burned = S.box.discs.filter((d) => d.state !== "blank");
  const check = S.box.discs.find((d) => d.used_for === "check_burn")?.id;
  const target = shoot.disc || check || burned[0]?.id;
  const verdictBy = {};
  // the reading covers every photo of the disc so far; the newest set is its last entries
  if (r && set && r.disc === set.disc) { const all = r.photos || [], off = all.length - shots.length; shots.forEach((_, i) => { if (all[off + i]) verdictBy[i] = all[off + i]; }); }
  const gal = shots.map((p, i) => {
    const v = verdictBy[i];
    const cap = v ? (v.verdict === "ok" ? `<b class="good">${tr("可以用", "Usable")}</b>${v.L_mm != null ? ` · L ${fmt(v.L_mm)}` : ""}` : `<b>${tr("重拍", "Retake")}</b>：${esc(w(REASONS[v.status]) || v.reason || "")}`) : esc(p.split(/[\\/]/).pop());
    return `<figure><img src="${file(p, 360)}" alt="" data-a="zoom" data-src="${esc(file(p))}" loading="lazy"><figcaption>${cap}</figcaption></figure>`;
  }).join("");
  const opts = burned.map((d) => `<option value="${esc(d.id)}" ${d.id === target ? "selected" : ""}>${esc(discName(d.id))}</option>`).join("");
  let result = "";
  if (r) {
    const ok = r.verdict === "ok" && r.offset_mm != null, t = r.truth;
    result = `<h3>${tr("照片读出的沿轨常数", "Along-track constant from the photos")}</h3>
    <div class="facts"><div><dt>${tr("读出", "Read")}</dt><dd>${ok ? fmt(r.offset_mm) : tr("没有", "none")}</dd></div>
    <div><dt>${tr("可用照片", "Usable photos")}</dt><dd>${(r.photos || []).filter((p) => p.verdict === "ok").length} / ${(r.photos || []).length}</dd></div>
    <div><dt>${tr("盘", "Disc")}</dt><dd style="font-size:17px">${esc(r.disc)}</dd></div></div>
    ${ok ? "" : `<p class="warn">${tr("还读不出可信的 L。再拍几张不同角度的，会和之前的照片一起读。", "No reliable L yet. Take a few more from other angles; they are read together with the earlier ones.")}</p>`}
    ${t && t.L_mm != null ? `<div class="labonly"><div class="h">${tr("只在 Lab 里有：真值", "Lab only: the truth")}</div>
      <div class="facts" style="margin:0"><div><dt>${tr("真值 L", "True L")}</dt><dd>${fmt(t.L_mm)}</dd></div>
      <div><dt>${tr("差", "Off by")}</dt><dd>${t.error_mm != null ? fmt(t.error_mm) : "—"}</dd></div>
      <div><dt>${tr("判定", "Verdict")}</dt><dd style="font-size:17px">${t.error_mm == null ? "—" : Math.abs(t.error_mm) <= 0.1 ? `<span class="good">${tr("在 0.1 mm 内", "within 0.1 mm")}</span>` : `<span class="warn">${tr("超过 0.1 mm", "over 0.1 mm")}</span>`}</dd></div></div></div>` : ""}`;
  }
  return `<h2>${esc(w(W.phone))}</h2>
  <p class="sub">${tr("虚拟手机照着真值把盘拍下来：反光、彩虹、对焦、手抖都按物理算。", "A virtual phone photographs the disc from its truth: glare, rainbow, focus and shake are computed.")}</p>
  <div class="rule"></div>
  ${stepList((s) => s.stage === "photo" || s.stage === "check")}
  <h3>${tr("拍哪张盘", "Which disc")}</h3>
  ${burned.length ? `<div class="row"><select data-a="target" aria-label="${tr("拍哪张盘", "Which disc")}">${opts}</select></div>` : `<p class="note">${tr("还没有刻过的盘。先在刻录机上刻一张。", "No written disc yet. Burn one at the burner first.")}</p>`}
  <div class="row"><span class="choice" role="group" aria-label="${tr("张数", "How many")}">${[3, 6].map((n) => `<button data-a="n" data-v="${n}" aria-pressed="${shoot.n === n}">${tr(`${n} 张`, `${n} photos`)}</button>`).join("")}</span>
  <span class="choice" role="group" aria-label="${tr("怎么拍", "How")}">${Object.keys(W.styles).map((k) => `<button data-a="style" data-v="${k}" aria-pressed="${shoot.style === k}">${esc(w(W.styles[k]))}</button>`).join("")}</span></div>
  ${c?.key === "photos" && target === check ? "" : burned.length ? `<div class="row"><button class="sbtn quiet" data-a="shoot" ${job ? "disabled" : ""}>${tr("给这张盘拍几张", "Photograph this disc")}</button><span class="note">${tr("只拍照，不读 L、不算进练手流程", "photos only: no L, outside the practice steps")}</span></div>` : ""}
  ${gal ? `<h3>${tr("最近一组照片", "Latest photos")} <span class="note">${esc(set.disc || "")}</span></h3><div class="gallery">${gal}</div>` : ""}
  ${result}
  ${logBlock()}`;
}
const sgn = (v, n) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(n)}`;
const fmt = (v) => `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(3)} mm`;

function basketSheet() {
  const b = S.box, d = drive();
  const rows = b.discs.map((x) => `<tr class="${x.drive ? "in" : ""}"><td class="id"><span class="discdot ${x.state === "blank" ? "blank" : ""}"></span>${esc(x.id)}</td>
    <td><span class="chip ${x.state}">${esc(w(W.state[x.state]))}</span></td><td>${esc(x.used_for ? w(W.used[x.used_for]) : "")}</td>
    <td>${x.drive ? `${tr("在光驱", "in")} ${esc(x.drive)}` : `<button class="sbtn quiet" data-a="insert" data-id="${esc(x.id)}" ${job ? "disabled" : ""}>${tr("放进光驱", "Put in the drive")}</button>`}</td></tr>`).join("");
  const tui = SCORES.tui, sc = scoreBlock(tui);
  const media = S.media.map((m) => `<option value="${m}" ${m === b.media ? "selected" : ""}>${m.toUpperCase()}</option>`).join("");
  return `<h2>${esc(w(W.basket))}</h2>
  <p class="sub">${esc(b.media.toUpperCase())} · ${esc(b.mid)} · ${tr(`批次 ${b.batch}`, `batch ${b.batch}`)} · ${tr(`${b.count} 张，空白 ${b.blanks} 张`, `${b.count} discs, ${b.blanks} blank`)}</p>
  <div class="rule"></div>
  <p class="note">${tr("每张盘的几何、偏心、翘曲都不一样，真值藏在实验目录的 answers.json 里，disc-probe 看不到。", "Every disc differs in geometry, eccentricity and warp. The truth is in the lab's answers.json, which disc-probe never sees.")}</p>
  <table class="discs"><thead><tr><th>${tr("盘号", "Disc")}</th><th>${tr("状态", "State")}</th><th>${tr("用作", "Used as")}</th><th></th></tr></thead><tbody>${rows}</tbody></table>
  <h3>${tr("对照真值", "Compared with the truth")}</h3>
  ${sc || `<p class="note">${tr("测完几何以后，这里会写测量和照片差了多少。", "After the geometry is measured, this says how far the measurement and photos were off.")}</p>`}
  ${stepBy("score")?.done || !stepBy("geo")?.done ? "" : `<div class="row"><button class="sbtn" data-a="score" ${job ? "disabled" : ""}>${tr("对照真值", "Compare with the truth")}</button></div>`}
  <h3 id="newbox">${tr("新的一箩", "A new basket")}</h3>
  <p class="note">${tr("建在实验目录旁边的新文件夹里；这一箩的结果都留着。", "Made in a new folder next to this lab; this basket's results stay.")}</p>
  <div class="row">
    <label class="field"><span>${tr("盘种", "Media")}</span><select id="nb-media">${media}</select></label>
    <label class="field"><span>${tr("张数", "Discs")}</span><input type="number" id="nb-count" value="3" min="1" max="24"></label>
    <label class="field"><span>${tr("批次", "Batch")}</span><input type="number" id="nb-batch" value="${b.batch + 1}" min="1"></label>
    <label class="field"><span>${tr("随机种子", "Seed")}</span><input type="number" id="nb-seed" value="${Math.floor(Math.random() * 1000)}" min="0"></label>
  </div>
  <div class="row">
    <label class="field"><span>${tr("偏心 µm（空着随机）", "Eccentricity µm (blank: random)")}</span><input type="number" id="nb-ecc" step="5" placeholder="${tr("随机", "random")}"></label>
    <label class="field"><span>${tr("碟形翘曲 mm", "Dish warp mm")}</span><input type="number" id="nb-dish" step="0.05" placeholder="${tr("随机", "random")}"></label>
    <label class="field"><span>${tr("起始半径 mm", "Start radius mm")}</span><input type="number" id="nb-r0" step="0.05" placeholder="${tr("随机", "random")}"></label>
  </div>
  <div class="row">
    <label class="field"><span>${tr("划痕（读不出的弧）", "Scratch (unreadable arc)")}</span><select id="nb-scratch"><option value="">${tr("没有", "none")}</option><option value="40">${tr("40–41 mm，一小段", "40–41 mm, short")}</option><option value="52">${tr("52–54 mm，长一些", "52–54 mm, longer")}</option></select></label>
    <label class="field"><span>${tr("第一张盘", "First disc")}</span><select id="nb-state"><option value="blank">${tr("空白", "blank")}</option><option value="partial">${tr("刻了一半", "partly written")}</option><option value="open">${tr("刻完没封口", "written, open")}</option><option value="burned">${tr("已刻好", "written")}</option></select></label>
    <label class="field"><span>${tr("读盘配置", "Reader")}</span><select id="nb-reader">${S.readers.map((r) => `<option value="${r}" ${r === d?.reader ? "selected" : ""}>${esc(w(W.readers[r]) || r)}</option>`).join("")}</select></label>
  </div>
  <div class="row"><button class="sbtn" data-a="newbox" ${job ? "disabled" : ""}>${tr("建这一箩", "Make this basket")}</button>
    <button class="sbtn quiet" data-a="labs">${tr("换一箩已有的…", "Open another basket…")}</button></div>
  <div id="labs"></div>
  ${logBlock()}`;
}
function scoreBlock(tui) {
  if (!tui?.geo) return "";
  const g = tui.geo, p = (tui.photos || []).slice(-1)[0];
  return `<div class="facts"><div><dt>${tr("几何 u 差", "Geometry u off")}</dt><dd>${sgn(g.du_bits ?? 0, 3)} bit</dd></div>
    <div><dt>${tr("几何 v 差（相对）", "Geometry v off (rel.)")}</dt><dd>${sgn((g.dv_rel ?? 0) * 1e6, 2)} ppm</dd></div>
    <div><dt>${tr("照片 L 差", "Photo L off")}</dt><dd>${p?.error_mm != null ? fmt(p.error_mm) : "—"}</dd></div></div>
    <p class="note">${tr(`测量盘 ${g.disc}；几何在实测范围内与真值比较。`, `Measurement disc ${g.disc}; geometry compared with the truth within the measured span.`)}</p>`;
}
function newBoxArgv() {
  const v = (id) => document.getElementById(id).value, num = (id) => (v(id) === "" ? null : +v(id));
  const count = Math.max(1, Math.round(num("nb-count") || 3));
  const discs = { media: v("nb-media"), count, batch: Math.max(1, Math.round(num("nb-batch") || 1)), seed: Math.max(0, Math.round(num("nb-seed") || 0)) };
  const par = {};
  if (num("nb-ecc") != null) par.ecc_um = num("nb-ecc");
  if (num("nb-dish") != null) par.dish_mm = num("nb-dish");
  if (num("nb-r0") != null) par.start_radius_mm = num("nb-r0");
  if (Object.keys(par).length) discs.parameters = par;
  const sc = v("nb-scratch");
  if (sc) discs.defect_arcs = sc === "40" ? [{ r_mm: [40, 41], deg: [20, 60] }] : [{ r_mm: [52, 54], deg: [200, 300] }];
  const st = v("nb-state");
  if (st !== "blank") discs.initial_state = [st === "partial" ? { state: "partial", random: true, sectors: 4096, fraction: 0.5 } : { state: st, random: true, sectors: 4096 }, ...Array(count - 1).fill("blank")];
  const scenario = { version: 1, discs, drive: { profile: v("nb-reader") } };
  return ["box", "--scenario-json", JSON.stringify(scenario)];
}

// ------------------------------------------------------------------ events
document.addEventListener("click", async (e) => {
  const el = e.target.closest("[data-a]"); if (!el || el.tagName === "SELECT" || el.tagName === "INPUT") return;
  const a = el.dataset.a, d = drive();
  if (a === "swap") run(["swap"], { quiet: true });
  else if (a === "eject") run(["tray", "--drive", d.name, "--open"], { quiet: true });
  else if (a === "close") run(["tray", "--drive", d.name, "--disc", d.tray || ""].filter(Boolean), { quiet: true });
  else if (a === "measured") run(["tray", "--disc", measureDisc()], { quiet: true });
  else if (a === "insert") run(["tray", "--disc", el.dataset.id], { quiet: true });
  else if (a === "unfault") run(["drive", "--clear", el.dataset.id], { quiet: true });
  else if (a === "fault") run(["drive", "--fault", faultArg()], { quiet: true });
  else if (a === "nopick") { picture = null; paintPage(); }
  else if (a === "score") run(["step", "score"]);
  else if (a === "n") { shoot.n = +el.dataset.v; paintPage(); }
  else if (a === "style") { shoot.style = el.dataset.v; paintPage(); }
  else if (a === "shoot") {
    const disc = document.querySelector('[data-a="target"]')?.value; if (!disc) return;
    run(["photos", "--disc", disc, "-n", String(shoot.n), "--style", shoot.style, "--out", `${LAB}/photos/${disc.replace(/ /g, "_")}/manual-${Date.now()}`]);
  }
  else if (a === "zoom") { const z = $("zoom"); z.querySelector("img").src = el.dataset.src; z.hidden = false; }
  else if (a === "newbox") run(newBoxArgv());
  else if (a === "labs") {
    const r = await api("/api/labs");
    $("labs").innerHTML = `<div class="row">${r.labs.map((n) => `<button class="sbtn ${n === r.current ? "" : "quiet"}" data-a="openlab" data-n="${esc(n)}">${esc(n)}</button>`).join("")}</div>`;
  }
  else if (a === "openlab") { await api("/api/lab", { name: el.dataset.n }); await refresh(); }
});
document.addEventListener("change", async (e) => {
  const el = e.target, a = el.dataset?.a;
  if (a === "reader") run(["drive", "--reader", el.value], { quiet: true });
  else if (a === "fkind") $("fparams").innerHTML = faultParams(el.value);
  else if (a === "target") { shoot.disc = el.value; paintPage(); }
  else if (a === "pick" && el.files?.[0]) {
    const f = el.files[0];
    try {
      const r = await fetch("/api/picture", { method: "POST", headers: { "X-Filename": encodeURIComponent(f.name).replace(/%/g, "_") || "picture.png" }, body: f });
      const j = await r.json(); if (!r.ok) throw new Error(j.error); picture = j.path; paintPage(); toast(tr("图片放好了。", "Picture ready."));
    } catch (err) { toast(err.message); }
  }
});
$("zoom").addEventListener("click", () => { $("zoom").hidden = true; });
$("back").addEventListener("click", () => go(""));
$("job-log").addEventListener("click", () => { if (!mode) go(job?.argv?.[0] === "photos" || job?.argv?.[1]?.startsWith("photo") ? "phone" : "burner"); setTimeout(() => { const l = $("log"); if (l) { l.open = true; l.scrollIntoView({ behavior: "smooth" }); } }, 50); });
$("lang").addEventListener("click", () => { lang = lang === "en" ? "zh" : "en"; try { localStorage.setItem("disclab-lang", lang); } catch {} paint(); if (mode) paintPage(); });
function toggleTheme() {
  root.dataset.theme = theme() === "dark" ? "paper" : "dark";
  try { localStorage.setItem("disclab-theme", root.dataset.theme); } catch {}
  paintTheme(); paintLobby();
}
$("theme").addEventListener("click", toggleTheme);
// ---- settings: animation follows the system, or on / off for this page (disc-probe's Settings; Windows
// users often keep the system's animations off, and the page then stands still)
const sysReduce = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const motionChoice = () => { try { return localStorage.getItem("disclab-motion") || "auto"; } catch { return "auto"; } };
function paintSettings() {
  const c = motionChoice();
  $("set-motion-label").textContent = tr("动画", "Animation");
  for (const b of $("set-menu").querySelectorAll("[data-motion]")) {
    b.textContent = { auto: tr("跟随系统", "As system"), on: tr("开", "On"), off: tr("关", "Off") }[b.dataset.motion];
    b.setAttribute("aria-checked", String(b.dataset.motion === c));
  }
  $("set-motion-note").textContent = sysReduce()
    ? tr("系统设置了减弱动效，所以“跟随系统”时页面不动；选“开”只对这个页面生效。", "The system asks for reduced motion, so the page stands still when following it; On applies to this page only.")
    : tr("系统允许动效。", "The system allows motion.");
  $("settings").setAttribute("aria-label", tr("设置", "Settings"));
}
function setMotion(c) {
  try { c === "auto" ? localStorage.removeItem("disclab-motion") : localStorage.setItem("disclab-motion", c); } catch {}
  const on = c === "on" || (c === "auto" && !sysReduce());
  root.dataset.motion = on ? "on" : "off"; reduce = !on;
  paintSettings();
}
$("settings").addEventListener("click", (e) => { e.stopPropagation(); const open = $("set-menu").hidden; $("set-menu").hidden = !open; $("settings").setAttribute("aria-expanded", String(open)); paintSettings(); });
$("set-menu").addEventListener("click", (e) => { e.stopPropagation(); const b = e.target.closest("[data-motion]"); if (b) setMotion(b.dataset.motion); });
document.addEventListener("click", () => { if (!$("set-menu").hidden) { $("set-menu").hidden = true; $("settings").setAttribute("aria-expanded", "false"); } });
addEventListener("keydown", (e) => { if (e.key === "Escape" && mode) { if (!$("zoom").hidden) $("zoom").hidden = true; else go(""); } });
addEventListener("resize", fit);
let toastT;
function toast(text) { const t = $("toast"); t.textContent = text; t.classList.add("on"); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("on"), 4200); }

// ------------------------------------------------------------------ start
(async () => {
  await buildLobby().catch((e) => console.error("lobby art", e));
  await refresh().catch((e) => toast(e.message));
  const m = location.hash.slice(1);
  if (["basket", "burner", "phone"].includes(m)) go(m);
  // another tab or the terminal may change the lab: look again now and then (cheap: one status call)
  setInterval(() => { if (!job && document.visibilityState === "visible") refresh().catch(() => {}); }, 8000);
})();
