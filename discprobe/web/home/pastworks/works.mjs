// The works library as the page sees it: a client for the core's /api/works routes
// (docs/goals/pastworks/SPEC.md) and the pure helpers the past-works page and the design page share.
// No DOM at import time, so plain Node can test it against the mock (mock-works.mjs).

export const STATUSES = Object.freeze(["draft", "iso_ready", "burned", "done", "failed"]);
export const MEDIA = Object.freeze(["cd", "dvd", "bd"]);
const WORDS = {
  zh: {
    draft: "草稿", iso_ready: "已出 ISO", burned: "已刻", done: "成品", failed: "失败", unsaved: "未存进库",
    discs: (n) => `刻过 ${n} 张`, noDiscs: "还没刻", unknownDate: "日期未知",
    created: "创建", saved: "保存", iso: "出 ISO", burnedOn: (d) => `刻进 ${d}`, burnedEvent: "刻录", photo: "照片结果",
    renamed: (n) => `改名为“${n}”`, duplicated: (n) => n ? `从“${n}”复制` : "复制", imported: (n) => n ? `导入自 ${n}` : "导入",
    markedDone: "标成成品", markedFailed: "标成失败", restored: "从回收站恢复", deleted: "移到回收站", thumb: "更新缩略图", changed: "改了作品信息", geoNoted: "记下所用几何",
  },
  en: {
    draft: "Draft", iso_ready: "ISO ready", burned: "Burned", done: "Finished", failed: "Failed", unsaved: "Not in the library",
    discs: (n) => `${n} disc${n === 1 ? "" : "s"} burned`, noDiscs: "Not burned yet", unknownDate: "Date unknown",
    created: "Created", saved: "Saved", iso: "ISO written", burnedOn: (d) => `Burned onto ${d}`, burnedEvent: "Burned", photo: "Photo result",
    renamed: (n) => `Renamed to “${n}”`, duplicated: (n) => n ? `Copied from “${n}”` : "Copied", imported: (n) => n ? `Imported from ${n}` : "Imported",
    markedDone: "Marked finished", markedFailed: "Marked failed", restored: "Restored from the bin", deleted: "Moved to the bin", thumb: "Picture updated", changed: "Details changed", geoNoted: "Geometry noted",
  },
};
export const words = (lang) => WORDS[lang === "en" ? "en" : "zh"];
export const statusWord = (status, lang) => words(lang)[status] ?? String(status ?? "");

// "DVD-R", "CD-RW", "BD-R": the kind and its type, as printed on the disc
export function mediaLabel(work) {
  const m = String(work?.media ?? "").toUpperCase();
  if (!m) return "";
  const t = String(work?.disc_type ?? "").trim();
  return t ? m + (/^[-+]/.test(t) ? t : "-" + t) : m;
}
// discs[] holds ISOs written ({type: "iso"}) and discs burned ({type: "burn"}); only burns are discs
export const burnedDiscs = (work) => (Array.isArray(work?.discs) ? work.discs : []).filter((d) => (d?.type ?? "burn") === "burn");
export const discCount = (work) => Array.isArray(work?.discs) ? burnedDiscs(work).length : Number(work?.disc_count) || 0;
export const discCode = (d) => d?.disc_code ?? d?.code ?? (typeof d?.disc === "string" ? d.disc : d?.disc?.code) ?? d?.label ?? null;
export const discTime = (d) => d?.time ?? d?.burned_at ?? d?.at ?? null;
export const discISO = (d) => d?.iso_path ?? d?.iso ?? null;

const stamp = (v) => {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : Date.parse(v);
  return Number.isFinite(n) ? n : null;
};
export const workTime = (w) => stamp(w?.updated_at) ?? stamp(w?.opened_at) ?? stamp(w?.created_at);
const collator = new Intl.Collator("zh-u-co-pinyin", { numeric: true, sensitivity: "base" });
const han = /\p{Script=Han}/u;
export function sortWorks(works, order = "time") {
  return works.map((work, index) => ({ work, index })).sort((a, b) => {
    if (order === "name") {
      const an = String(a.work.name ?? ""), bn = String(b.work.name ?? "");
      return Number(!han.test(an[0])) - Number(!han.test(bn[0])) || collator.compare(an, bn) || a.index - b.index;
    }
    return (workTime(b.work) ?? -Infinity) - (workTime(a.work) ?? -Infinity) || a.index - b.index;
  }).map(({ work }) => work);
}
// Search is by name, ignoring case and width (full-width Latin typed with a Chinese IME still matches).
const fold = (s) => String(s ?? "").normalize("NFKC").toLocaleLowerCase();
export function filterWorks(works, { status = "", media = "", q = "" } = {}) {
  const needle = fold(q).trim();
  return works.filter((w) => (!status || w.status === status) && (!media || w.media === media)
    && (!needle || fold(w.name).includes(needle)));
}
export function countBy(works, key) {
  const out = {};
  for (const w of works) out[w[key]] = (out[w[key]] ?? 0) + 1;
  return out;
}

export function dateText(t, lang, { time = true } = {}) {
  if (t == null) return words(lang).unknownDate;
  const opts = { year: "numeric", month: "short", day: "numeric", ...(time ? { hour: "2-digit", minute: "2-digit", hour12: false } : {}) };
  return new Intl.DateTimeFormat(lang === "en" ? "en-CA" : "zh-CN", opts).format(t);
}

// The record of one work, oldest first: history events ({type, time, changes | record, ...}: the core's
// history.jsonl), with discs[] filling in ISOs and burns a short history no longer carries. Each line:
// { at, kind, text, detail }. Picture uploads are left out: every save makes one.
const base = (p) => String(p ?? "").split(/[\\/]/).pop();
const where = (r) => [r?.drive, r?.speed != null && r.speed !== "" ? (/x$/i.test(String(r.speed)) ? r.speed : `${r.speed}x`) : "", r?.result && r.result !== "completed" ? r.result : ""].filter(Boolean).join(" · ");
export function timeline(work, lang = "zh") {
  const t = words(lang), out = [], seen = new Set();
  const history = Array.isArray(work?.history) ? work.history : [];
  const linked = (r, kind) => {
    const code = discCode(r) ?? "";
    return kind === "iso" ? { text: t.iso, detail: [base(discISO(r)), code].filter(Boolean).join(" · ") }
      : { text: code ? t.burnedOn(code) : t.burnedEvent, detail: where(r) };
  };
  for (const e of history) {
    const kind = String(e.type ?? e.event ?? e.kind ?? ""), c = e.changes ?? {}, r = e.record ?? e;
    const at = stamp(e.time ?? e.at ?? e.ts);
    let text = kind, detail = "";
    switch (kind) {
      case "create": case "created": case "new": text = t.created; break;
      case "save": case "saved": text = t.saved; break;
      case "iso": case "iso_ready": case "image": case "burn": case "burned": {
        const iso = /^iso|^image/.test(kind);
        if (e.record) seen.add(discTime(e.record) ?? "");
        ({ text, detail } = linked(r, iso ? "iso" : "burn")); break;
      }
      case "photo": text = t.photo; detail = [e.result, e.L != null ? `L ${e.L}` : "", e.source ?? ""].filter(Boolean).join(" · "); break;
      case "rename": case "renamed": text = t.renamed(c.name ?? e.name ?? e.to ?? ""); break;
      case "duplicate": case "duplicated": text = t.duplicated(e.from_name ?? ""); break;
      case "import": case "imported": text = t.imported(base(e.source ?? e.file ?? "")); break;
      case "mark": case "marked": case "status": {
        const st = c.status ?? e.status;
        const geoOnly = !st && c.geo_run && Object.keys(c).length === 1;
        text = st === "failed" ? t.markedFailed : st === "done" ? t.markedDone : st ? statusWord(st, lang) : geoOnly ? t.geoNoted : t.changed;
        detail = geoOnly ? c.geo_run : c.note ?? e.note ?? ""; break;
      }
      case "restore": case "restored": text = t.restored; break;
      case "delete": case "deleted": text = t.deleted; break;
      case "thumb": case "thumbnail": continue;
    }
    out.push({ at, kind, text, detail });
  }
  for (const d of Array.isArray(work?.discs) ? work.discs : []) {
    if (seen.has(discTime(d) ?? "") && discTime(d)) continue;
    const kind = d.type === "iso" ? "iso" : "burned";
    out.push({ at: stamp(discTime(d)), kind, ...linked(d, kind === "iso" ? "iso" : "burn") });
  }
  return out.map((e, i) => ({ e, i })).sort((a, b) => (a.e.at ?? Infinity) - (b.e.at ?? Infinity) || a.i - b.i).map(({ e }) => e);
}

// ---------------------------------------------------------------- the client
// Responses are read leniently where the contract leaves the envelope open ({works:[...]} or a bare
// list; {work, history} or the work itself), and strictly where it fixes a field.
export const unwrapWork = (d) => d && typeof d === "object" ? (d.work && typeof d.work === "object"
  ? { ...d.work, ...(Array.isArray(d.history) ? { history: d.history } : {}) } : d) : null;
const unwrapList = (d) => Array.isArray(d) ? d : Array.isArray(d?.works) ? d.works : Array.isArray(d?.items) ? d.items : [];

export class WorksError extends Error {
  constructor(message, status, body) { super(message); this.status = status; this.body = body; }
}

export function createWorksClient({ fetch: fetcher = globalThis.fetch?.bind(globalThis), token = null } = {}) {
  const headers = (extra = {}) => ({ ...(token ? { "X-Discprobe-Token": token } : {}), ...extra });
  const path = (id, tail = "") => `/api/works/${encodeURIComponent(id)}${tail}`;
  async function call(url, { method = "GET", body, type, extra, as = "json" } = {}) {
    const init = { method, headers: headers({ ...(type ? { "Content-Type": type } : {}), ...extra }), cache: "no-store" };
    if (body !== undefined) init.body = body;
    const r = await fetcher(url, init);
    if (!r.ok) {
      let data = null; try { data = await r.json(); } catch {}
      throw new WorksError(data?.error || r.statusText || `HTTP ${r.status}`, r.status, data);
    }
    if (as === "blob") return r.blob();
    if (as === "text") return r.text();
    if (as === "response") return r;
    const text = await r.text();
    return text ? JSON.parse(text) : null;
  }
  const json = (v) => JSON.stringify(v);
  const thumbs = new Map();                  // id -> { key, url }
  return {
    async list({ sort = "time", status = "", media = "" } = {}) {
      const q = new URLSearchParams({ sort, status, media });
      return unwrapList(await call(`/api/works?${q}`));
    },
    async get(id) { return unwrapWork(await call(path(id))); },
    design: (id) => call(path(id, "/design"), { as: "text" }),
    async create({ name, media, from } = {}) {
      return unwrapWork(await call("/api/works", { method: "POST", type: "application/json", body: json({ name, media, ...(from ? { from } : {}) }) }));
    },
    // ifMatch: the updated_at this page last saw; a newer one on disk answers 409
    async saveDesign(id, text, ifMatch) {
      return unwrapWork(await call(path(id, "/design"), { method: "PUT", type: "application/json", body: text,
        extra: ifMatch ? { "If-Match": ifMatch } : {} }));
    },
    async putThumb(id, blob) { return unwrapWork(await call(path(id, "/thumb"), { method: "PUT", type: "image/png", body: blob })); },
    async patch(id, fields) { return unwrapWork(await call(path(id), { method: "PATCH", type: "application/json", body: json(fields) })); },
    rename(id, name) { return this.patch(id, { name }); },
    mark(id, status, note) { return this.patch(id, note ? { status, note } : { status }); },
    async duplicate(id, name) {
      return unwrapWork(await call(path(id, "/duplicate"), { method: "POST", type: "application/json", body: json(name ? { name } : {}) }));
    },
    async remove(id) { await call(path(id), { method: "DELETE" }); },
    async restore(id) { return unwrapWork(await call(path(id, "/restore"), { method: "POST", type: "application/json", body: "{}" })); },
    // the zip, and the name the core gives it (Content-Disposition), else the work's name
    async exportZip(id, fallbackName = id) {
      const r = await call(path(id, "/export"), { as: "response" });
      const cd = r.headers.get("Content-Disposition") ?? "";
      const m = /filename\*=UTF-8''([^;]+)/i.exec(cd) ?? /filename="?([^";]+)"?/i.exec(cd);
      let name = m ? m[1] : `${id}.zip`;
      try { name = decodeURIComponent(name); } catch {}
      // the core names the zip after the id; the person knows the work by its name
      if (fallbackName && fallbackName !== id) name = `${String(fallbackName).replace(/[\\/:*?"<>|\u0000-\u001f]+/g, "_").trim() || id}.zip`;
      return { blob: await r.blob(), name };
    },
    // A zip goes to /import as it is (it keeps its own name and record). A .discdesign is made as a new work
    // named after the file, then saved: a Chinese file name cannot travel in a header (X-Filename is Latin-1).
    async importFile(file) {
      if (/\.zip$/i.test(file.name)) {
        return unwrapWork(await call("/api/works/import", { method: "POST", body: file, type: "application/zip",
          extra: { "X-Filename": encodeURIComponent(file.name) } }));
      }
      const text = await file.text();
      let doc; try { doc = JSON.parse(text); } catch { doc = null; }
      if (doc?.format !== "disc-probe design" || !Array.isArray(doc.layers)) throw new WorksError(`${file.name}: not a .discdesign`, 400, null);
      const made = await this.create({ name: file.name.replace(/\.(discdesign|json)$/i, "") || file.name, media: MEDIA.includes(doc.media) ? doc.media : "dvd" });
      try { return await this.saveDesign(made.id, text, made.updated_at); }
      catch (e) { await this.remove(made.id).catch(() => {}); throw e; }
    },
    // The thumbnail as an object URL (an <img> cannot send the token header). Cached per save.
    async thumbURL(work) {
      const key = `${work.updated_at ?? ""}|${work.thumb_url ?? ""}`, hit = thumbs.get(work.id);
      if (hit?.key === key) return hit.url;
      const blob = await call(work.thumb_url || path(work.id, "/thumb"), { as: "blob" });
      if (hit) URL.revokeObjectURL?.(hit.url);
      const url = URL.createObjectURL(blob);
      thumbs.set(work.id, { key, url });
      return url;
    },
  };
}

// The library for this page, or null when the core has none (then the page keeps its in-memory list).
// Demo pages (?mock) and file previews get the in-browser mock; it says so on the page.
let shared = null;
export async function worksFor(api, { capable = true } = {}) {
  if (shared) return shared;
  const local = api?.backend?.mock || (typeof location !== "undefined" && location.protocol === "file:");
  if (local) {
    const { createMockWorks } = await import("./mock-works.mjs");
    const mock = createMockWorks();
    shared = Object.assign(createWorksClient({ fetch: mock.fetch }), { mock });
    return shared;
  }
  if (!capable) return null;
  const token = typeof location !== "undefined" ? new URLSearchParams(location.search).get("token") : null;
  shared = createWorksClient({ token });
  return shared;
}
export const setWorksForTest = (client) => { shared = client; };
