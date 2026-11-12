// The page's keys, one set everywhere, so they become habit:
//
//   Esc        back one step (the Back button), or close what is open on top
//   Enter      next (the Next button); burning uses the slider's Right / End gesture
//   W A S D    the arrow keys: move the choice
//   O          the settings menu
//   T          light / dark
//   L          the language
//   M          sound on / off
//   ?          this list
//
// The buttons show their keys (a small cap under Back, the language, the theme and settings; Next ends in
// the Enter key), so the keys are learnt by looking, not from this list: a button's cap while the pointer
// is on it, all of them while the keyboard is in use (keyboard mode, below).
//
// Each page keeps its own handling of the arrow keys (the library's columns, the new-plan dial, the
// preview); W A S D only stand in for them. The lobby has no arrow handling of its own: there the arrows
// (and W A S D) move the focus between the desk's objects by where they stand, and Enter opens the one in
// focus. Tab is left alone: it moves the focus from control to control, which keyboard and screen-reader
// users rely on.
//
// Nothing here while typing (inputs, the terminal, an input method composing; Esc still means back), with
// Ctrl/Alt/Cmd held, or in the design view, which has its own keys (W is its wand, Esc clears the
// selection first); ?, O, T and L work there too (it doesn't use them).

const WASD = { w: "ArrowUp", a: "ArrowLeft", s: "ArrowDown", d: "ArrowRight" };
const STEP = { ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0] };

const WORDS = {
  en: { title: "Keys", close: "Close", rows: [
    ["Esc", "Back one step"], ["Enter", "Next"], ["→ / End", "Focus the burn slider and hold for 1 second"],
    ["W A S D", "Move the choice (as the arrow keys)"], ["O", "Settings"], ["T", "Light or dark"], ["L", "中文"], ["M", "Sound on or off"],
    ["?", "This list"],
    ["Tab", "Move between buttons"]],
    note: "In the design view: V move, W wand, H pan, 0 fit, Space drag the view." },
  zh: { title: "快捷键", close: "关闭", rows: [
    ["Esc", "返回上一步"], ["Enter", "下一步"], ["→ / End", "聚焦刻录滑块，按住 1 秒确认"],
    ["W A S D", "移动选择（同方向键）"], ["O", "设置"], ["T", "浅色或深色"], ["L", "English"], ["M", "声音开或关"],
    ["?", "打开这张表"],
    ["Tab", "在按钮之间移动"]],
    note: "设计页另有一套：V 移动、W 魔棒、H 拖动、0 适配画面、按住空格拖动视图。" },
};

const root = document.documentElement;
const typing = (t) => t instanceof Element && !!t.closest("input, textarea, select, [contenteditable=''], [contenteditable='true']");
const shown = (n) => !!n && !n.hidden && n.getClientRects().length > 0;

let help = null;

function buildHelp() {
  help = document.createElement("div");
  help.className = "keys-help";
  help.id = "keys-help";
  help.hidden = true;
  help.setAttribute("role", "dialog");
  help.setAttribute("aria-modal", "true");
  help.setAttribute("aria-labelledby", "keys-help-title");
  help.addEventListener("click", (e) => { if (e.target === help || e.target.closest(".keys-close")) showHelp(false); });
  document.body.append(help);
  addEventListener("dp-lang", () => { if (!help.hidden) paintHelp(); });
}

function paintHelp() {
  const t = WORDS[root.dataset.lang === "zh" ? "zh" : "en"];
  const card = document.createElement("div");
  card.className = "keys-card";
  const h = document.createElement("h2");
  h.id = "keys-help-title"; h.textContent = t.title;
  const list = document.createElement("dl");
  for (const [k, what] of t.rows) {
    const dt = document.createElement("dt");
    for (const part of k.split(" ")) { const kbd = document.createElement("kbd"); kbd.textContent = part; dt.append(kbd); }
    const dd = document.createElement("dd"); dd.textContent = what;
    list.append(dt, dd);
  }
  const note = document.createElement("p");
  note.textContent = t.note;
  const close = document.createElement("button");
  close.type = "button"; close.className = "btn keys-close"; close.textContent = t.close;
  card.append(h, list, note, close);
  help.replaceChildren(card);
}

let before = null;
function showHelp(open) {
  if (!help) buildHelp();
  if (open === !help.hidden) return;
  if (open) { before = document.activeElement; paintHelp(); help.hidden = false; help.querySelector(".keys-close").focus(); }
  else { help.hidden = true; before?.focus?.(); before = null; }
}

// The lobby: the focus moves to the nearest object on that side, nearer to the line of the key counting
// more than distance along it.
function lobbyMove(key) {
  const items = [...document.querySelectorAll(".lb-hit, #lobby-recent button")].filter(shown);
  if (!items.length) return false;
  const centre = (n) => { const r = n.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; };
  const from = items.includes(document.activeElement) ? document.activeElement : null;
  if (!from) { items[0].focus(); return true; }
  const [fx, fy] = centre(from), [dx, dy] = STEP[key];
  let best = null, score = Infinity;
  for (const n of items) {
    if (n === from) continue;
    const [x, y] = centre(n), along = (x - fx) * dx + (y - fy) * dy, across = Math.abs((x - fx) * dy - (y - fy) * dx);
    if (along <= 4) continue;
    const s = along + 2 * across;
    if (s < score) { score = s; best = n; }
  }
  best?.focus();
  return true;
}

// Next, by keyboard: a click, or for a hold button the same hold its own key handling does (it was given
// the focus, so the release reaches it).
function pressNext(next, e) {
  if (!shown(next) || next.disabled) return false;
  if (next.dataset.hold || next.classList.contains("burn-primary")) {
    next.focus();
    next.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true, repeat: e.repeat }));
  } else if (!e.repeat) next.click();
  return true;
}

// Keyboard mode: the buttons show their keys while the keyboard is in use. Any key turns it on (not
// typing in a field, not a modifier alone); the mouse moving a little or a click turns it off a moment later.
function keyboardMode() {
  let off = 0, moved = 0, last = null;
  const leave = () => { clearTimeout(off); off = setTimeout(() => root.classList.remove("kbd-mode"), 1200); };
  addEventListener("keydown", (e) => {
    if (["Shift", "Control", "Alt", "Meta", "CapsLock"].includes(e.key)) return;
    if (typing(e.target) && e.key.length === 1) return;
    clearTimeout(off); moved = 0; last = null;
    root.classList.add("kbd-mode");
  }, true);
  addEventListener("pointermove", (e) => {
    if (!root.classList.contains("kbd-mode") || e.pointerType !== "mouse") return;
    if (last) moved += Math.hypot(e.clientX - last[0], e.clientY - last[1]);
    last = [e.clientX, e.clientY];
    if (moved > 12) { moved = 0; leave(); }
  }, { passive: true });
  addEventListener("pointerdown", () => { if (root.classList.contains("kbd-mode")) leave(); }, { passive: true });
}

export function install({ $ }) {
  keyboardMode();
  addEventListener("keydown", (e) => {
    if (e.defaultPrevented || e.isComposing || e.ctrlKey || e.metaKey || e.altKey) return;
    if (document.querySelector(".term:not([hidden])")) return;
    const k = e.key;
    if (help && !help.hidden) {
      if (k === "Escape" || k === "?") { e.preventDefault(); showHelp(false); }
      return;
    }
    if (!typing(e.target)) {
      const tool = { o: "settings", t: "theme", l: "lang", m: "sound" }[k.toLowerCase()];
      if (tool && !e.shiftKey) { e.preventDefault(); $(tool).click(); return; }
      if (k === "?") { e.preventDefault(); showHelp(true); return; }
    }
    if (root.dataset.mode === "design") return;
    // Esc types nothing, so it means back even from a text field (fields with an Esc of their own, like a
    // rename, keep it to themselves)
    if (k === "Escape") {
      const back = $("back");
      if (shown(back) && !back.disabled) { e.preventDefault(); back.click(); }
      return;
    }
    if (typing(e.target)) return;
    if (k === "Enter") {
      // a focused button or link answers Enter itself
      if (e.target instanceof Element && e.target.closest("button, a[href], summary, [role=button]")) return;
      if (pressNext($("next"), e)) e.preventDefault();
      return;
    }
    const arrow = e.shiftKey ? null : WASD[k] ?? (STEP[k] ? k : null);
    if (!arrow) return;
    if (root.dataset.home === "lobby" && !root.dataset.mode) {
      if (lobbyMove(arrow)) e.preventDefault();
      return;
    }
    if (WASD[k]) {
      e.preventDefault();
      (document.activeElement ?? document.body).dispatchEvent(new KeyboardEvent("keydown", { key: arrow, bubbles: true, cancelable: true, repeat: e.repeat }));
    }
  });
  // the release of a held Enter that began here, if the focus was not on Next when it went down
  addEventListener("keyup", (e) => {
    const next = $("next");
    if (e.key === "Enter" && document.activeElement !== next && (next?.dataset.hold || next?.classList.contains("burn-primary")))
      next.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", bubbles: true, cancelable: true }));
  });
}
