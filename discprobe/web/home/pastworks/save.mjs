// Saving a design into the works library (Ctrl+S on the design page). The design page hands over the
// .discdesign text and a way to draw the 512 px disc picture; this files it under the plan's work,
// making the work on the first save. A 409 means another window saved the same work since this page
// last loaded or saved it: the person chooses to overwrite it or to keep both.

const SAY = {
  zh: {
    title: "另一个窗口改过这件作品", body: (n) => `“${n}”在这一页上次保存之后，又在别处保存过。`,
    overwrite: "用这一页覆盖", copy: "另存为新作品", cancel: "先不保存",
    saved: (n) => `已存进作品库：${n}`, copied: (n) => `已另存为新作品：${n}`, copyName: (n) => `${n}（另存）`,
    failed: "没能存进作品库：", thumb: "作品已保存，缩略图没有传上去。",
  },
  en: {
    title: "Another window changed this work", body: (n) => `“${n}” was saved somewhere else after this page last saved it.`,
    overwrite: "Overwrite with this page", copy: "Save as a new work", cancel: "Don't save yet",
    saved: (n) => `Saved to the library: ${n}`, copied: (n) => `Saved as a new work: ${n}`, copyName: (n) => `${n} (copy)`,
    failed: "Could not save to the library: ", thumb: "Saved; the picture did not upload.",
  },
};
export const sayings = (lang) => SAY[lang === "en" ? "en" : "zh"];

// plan.work: { id, updated_at } once the plan lives in the library.
// Returns { work, note } after a save, or null when the person cancelled a conflict.
export async function saveToLibrary({ client, plan, text, thumb, name, lang = "zh", ask = askConflict }) {
  const s = sayings(lang);
  let note = s.saved(name), work;
  const fresh = async (n = name) => client.create({ name: n, media: plan.media });
  let target = plan.work?.id ? plan.work : null, ifMatch = target?.updated_at ?? null;
  if (!target) { work = await fresh(); target = work; ifMatch = work.updated_at; }
  try {
    work = await client.saveDesign(target.id, text, ifMatch);
  } catch (e) {
    if (e.status === 404) {                       // moved to the bin elsewhere: keep this as a new work
      work = await fresh(); work = await client.saveDesign(work.id, text, work.updated_at);
    } else if (e.status === 409) {
      const choice = await ask({ name, lang });
      if (choice === "overwrite") {
        const now = await client.get(target.id);
        work = await client.saveDesign(target.id, text, now.updated_at);
      } else if (choice === "copy") {
        work = await fresh(s.copyName(name));
        work = await client.saveDesign(work.id, text, work.updated_at);
        note = s.copied(work.name);
      } else return null;
    } else throw e;
  }
  plan.work = { id: work.id, updated_at: work.updated_at };
  try {
    const blob = await thumb?.();
    if (blob) {
      const after = await client.putThumb(work.id, blob);
      // the contract does not say whether a picture moves updated_at; follow it if it does
      if (after?.updated_at) plan.work.updated_at = after.updated_at;
    }
  } catch { note += " " + s.thumb; }
  return { work: { ...work, updated_at: plan.work.updated_at }, note };
}

// The overwrite-or-copy question, as a modal dialog on the glass. Esc or the backdrop cancels.
let styled = false;
export function askConflict({ name, lang = "zh", doc = document } = {}) {
  const s = sayings(lang);
  if (!styled) {
    styled = true;
    const css = doc.createElement("style");
    css.textContent = `.pw-conflict{max-width:min(460px,calc(100vw - 32px));padding:22px 24px;border:0;border-radius:8px;
  background:var(--paper);color:var(--ink);box-shadow:var(--glass-edge),var(--glass-desk);font:16px/1.55 var(--font)}
.pw-conflict::backdrop{background:rgb(0 0 0 / .32)}
.pw-conflict h2{margin:0 0 6px;font-size:20px;font-weight:800;font-stretch:110%}.pw-conflict p{margin:0 0 18px;color:var(--ink-2)}
.pw-conflict div{display:flex;flex-wrap:wrap;gap:10px}
.pw-conflict button{min-height:44px;padding:0 16px;border:1px solid var(--rule-strong);border-radius:4px;background:none;color:var(--ink);font:600 15px var(--font);cursor:pointer}
.pw-conflict button:hover{border-color:var(--copper);color:var(--copper)}
.pw-conflict button:focus-visible{outline:2px solid var(--copper);outline-offset:2px}
.pw-conflict button.primary{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.pw-conflict button.primary:hover{background:var(--copper);border-color:var(--copper);color:var(--paper)}`;
    doc.head.append(css);
  }
  const d = doc.createElement("dialog");
  d.className = "pw-conflict"; d.setAttribute("aria-labelledby", "pw-conflict-title");
  const h = doc.createElement("h2"), p = doc.createElement("p"), row = doc.createElement("div");
  h.id = "pw-conflict-title"; h.textContent = s.title; p.textContent = s.body(name);
  const button = (label, value, primary = false) => {
    const b = doc.createElement("button"); b.type = "button"; b.textContent = label; b.value = value;
    if (primary) b.className = "primary";
    b.addEventListener("click", () => d.close(value)); return b;
  };
  // keeping both is the safe choice and comes first; overwriting loses the other window's save
  row.append(button(s.copy, "copy", true), button(s.overwrite, "overwrite"), button(s.cancel, ""));
  d.append(h, p, row); doc.body.append(d);
  return new Promise((resolve) => {
    d.addEventListener("close", () => { resolve(d.returnValue || null); d.remove(); }, { once: true });
    d.addEventListener("click", (e) => { if (e.target === d) d.close(""); });
    d.showModal(); row.firstElementChild.focus();
  });
}
