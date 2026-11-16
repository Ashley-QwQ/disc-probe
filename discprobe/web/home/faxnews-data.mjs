// The news fax's data: read, check and lay out one day's paper. No DOM, no network: faxnews.js asks the core,
// this file decides what the bytes mean. Format: docs/fax-news.md ("dp-fax-news", version 1).
//
// Download only. Paper and asset requests stay on the local API; the Python core checks and downloads sources.

export const FORMAT = "dp-fax-news", FORMAT_VERSION = 1, SKIN_FORMAT = "dp-skin";
export const DEFAULT_SOURCE = "/api/news";
const MAX_ITEMS = 40, MAX_TEXT = 600;

// A text is a plain string or {zh, en}; either language may be missing (the other stands in).
export function pick(text, lang) {
  if (typeof text === "string") return text;
  if (!text || typeof text !== "object") return "";
  return String(text[lang] ?? text.zh ?? text.en ?? "");
}
const isText = (t) => (typeof t === "string" && t.length <= MAX_TEXT) ||
  (!!t && typeof t === "object" && !Array.isArray(t) && ["zh", "en"].some((k) => typeof t[k] === "string") &&
    Object.values(t).every((v) => typeof v === "string" && v.length <= MAX_TEXT));
const isDate = (d) => typeof d === "string" && /^\d{4}-\d{2}-\d{2}$/.test(d) && !Number.isNaN(Date.parse(d));
const isColour = (c) => typeof c === "string" && /^#[0-9a-f]{6}$/i.test(c);
// a relative path or an http(s) address; nothing that runs (javascript:, data: html) or leaves the web
export function safeRef(ref) {
  if (typeof ref !== "string" || !ref || ref.length > 400) return false;
  if (/^[a-z][a-z0-9+.-]*:/i.test(ref)) return /^https?:\/\//i.test(ref);
  return !ref.startsWith("//");
}

// "v1.0.0.0-alpha" -> {nums: [1, 0, 0, 0], pre: "alpha"}; null if it is not a version
export function parseVersion(v) {
  const m = /^v?(\d+(?:\.\d+){0,3})(?:-([0-9a-z.]+))?$/i.exec(String(v ?? "").trim());
  if (!m) return null;
  return { nums: m[1].split(".").map(Number), pre: m[2] ?? "" };
}
// < 0: a is older. Missing parts count as 0; a prerelease comes before its release (1.0.0.0-alpha < 1.0.0.0);
// prereleases compare part by part, numbers as numbers (alpha.2 < alpha.10).
export function compareVersions(a, b) {
  const x = parseVersion(a), y = parseVersion(b);
  if (!x || !y) return NaN;
  for (let i = 0; i < 4; i++) {
    const d = (x.nums[i] ?? 0) - (y.nums[i] ?? 0);
    if (d) return Math.sign(d);
  }
  if (x.pre === y.pre) return 0;
  if (!x.pre) return 1;
  if (!y.pre) return -1;
  const p = x.pre.split("."), q = y.pre.split(".");
  for (let i = 0; i < Math.max(p.length, q.length); i++) {
    if (p[i] === undefined) return -1;
    if (q[i] === undefined) return 1;
    const n = /^\d+$/.test(p[i]), m = /^\d+$/.test(q[i]);
    if (n && m && +p[i] !== +q[i]) return Math.sign(+p[i] - +q[i]);
    if (n !== m) return n ? -1 : 1;
    if (p[i] !== q[i]) return p[i] < q[i] ? -1 : 1;
  }
  return 0;
}

// Why a paper was refused, for the slip the fax prints instead. Each problem names its field.
export class PaperError extends Error {
  constructor(problems) { super(problems.join("; ")); this.problems = problems; this.name = "PaperError"; }
}

const PATTERNS = ["diamond", "dots", "stripes"];
// Checks a parsed paper and returns a clean copy (unknown fields dropped, lists capped). Throws PaperError.
export function readPaper(data) {
  const bad = [];
  const need = (ok, what) => { if (!ok) bad.push(what); return !!ok; };
  if (!need(data && typeof data === "object" && !Array.isArray(data), "not an object")) throw new PaperError(bad);
  need(data.format === FORMAT, `format is not "${FORMAT}"`);
  need(data.version === FORMAT_VERSION, `version is not ${FORMAT_VERSION}`);
  if (bad.length) throw new PaperError(bad);
  need(isDate(data.date), "date");
  const list = (key, check) => {
    const v = data[key] ?? [];
    if (!need(Array.isArray(v), key)) return [];
    const out = [];
    v.slice(0, MAX_ITEMS).forEach((item, i) => { const r = check(item, `${key}[${i}]`); if (r) out.push(r); });
    return out;
  };
  const obj = (x, where) => need(x && typeof x === "object" && !Array.isArray(x), where);
  let release = null;
  if (data.release != null && obj(data.release, "release")) {
    const r = data.release;
    const ok = need(parseVersion(r.version), "release.version") & need(isDate(r.date), "release.date") &
      need(isText(r.headline), "release.headline") & need(r.url == null || safeRef(r.url), "release.url") &
      need(r.summary == null || isText(r.summary), "release.summary");
    if (ok) release = { version: r.version, date: r.date, headline: r.headline, summary: r.summary ?? "", url: r.url ?? "" };
  }
  const changelog = list("changelog", (c, w) => obj(c, w) && need(parseVersion(c.version), `${w}.version`) &&
    need(isDate(c.date), `${w}.date`) && need(isText(c.title), `${w}.title`) && need(isText(c.story), `${w}.story`)
    ? { version: c.version, date: c.date, title: c.title, story: c.story } : null);
  const skins = list("skins", (s, w) => obj(s, w) && need(typeof s.id === "string" && /^[a-z0-9-]{1,40}$/.test(s.id), `${w}.id`) &&
    need(isText(s.name), `${w}.name`) && need(isText(s.pitch), `${w}.pitch`) && need(safeRef(s.package), `${w}.package`) &&
    need(Array.isArray(s.swatches) && s.swatches.length >= 2 && s.swatches.length <= 6 && s.swatches.every(isColour), `${w}.swatches`) &&
    need(s.price == null || isText(s.price), `${w}.price`) && need(s.size_kb == null || (Number.isFinite(s.size_kb) && s.size_kb >= 0), `${w}.size_kb`)
    ? { id: s.id, name: s.name, pitch: s.pitch, price: s.price ?? "", swatches: s.swatches, package: s.package, size_kb: s.size_kb ?? null } : null);
  const backgrounds = list("backgrounds", (b, w) => {
    if (!(obj(b, w) && need(isText(b.name), `${w}.name`) && need(obj(b.pattern, `${w}.pattern`), `${w}.pattern`))) return null;
    const p = b.pattern;
    const ok = need(PATTERNS.includes(p.pattern), `${w}.pattern.pattern`) && need(["cartesian", "polar"].includes(p.coordinates ?? "cartesian"), `${w}.pattern.coordinates`) &&
      need(Number.isFinite(p.pitch_mm) && p.pitch_mm >= 0.5 && p.pitch_mm <= 20, `${w}.pattern.pitch_mm`) &&
      need(Number.isFinite(p.size_mm) && p.size_mm > 0 && p.size_mm <= p.pitch_mm / 2, `${w}.pattern.size_mm`) &&
      need(p.angle_deg == null || (Number.isFinite(p.angle_deg) && Math.abs(p.angle_deg) <= 360), `${w}.pattern.angle_deg`);
    return ok ? { name: b.name, note: isText(b.note) ? b.note : "", pattern: { pattern: p.pattern, coordinates: p.coordinates ?? "cartesian",
      pitch_mm: p.pitch_mm, size_mm: p.size_mm, angle_deg: p.angle_deg ?? 0 } } : null;
  });
  const artworks = list("artworks", (a, w) => obj(a, w) && need(isText(a.title), `${w}.title`) && need(safeRef(a.image), `${w}.image`) &&
    need(a.by == null || isText(a.by), `${w}.by`) && need(a.disc == null || isText(a.disc), `${w}.disc`)
    ? { title: a.title, image: a.image, by: a.by ?? "", disc: a.disc ?? "", caption: isText(a.caption) ? a.caption : "" } : null);
  const jokes = list("jokes", (j, w) => need(isText(j), w) ? j : null);
  const coming = list("coming", (c, w) => obj(c, w) && need(isText(c.title), `${w}.title`) && need(c.note == null || isText(c.note), `${w}.note`)
    ? { title: c.title, note: c.note ?? "" } : null);
  if (bad.length) throw new PaperError(bad);
  if (!release && !changelog.length && !skins.length && !backgrounds.length && !artworks.length && !jokes.length && !coming.length)
    throw new PaperError(["nothing to print"]);
  return { date: data.date, sample: data.sample === true, release, changelog, skins, backgrounds, artworks, jokes, coming };
}

// A skin parcel (what "订购" downloads): {format: "dp-skin", version: 1, id, name, tokens: {paper: {...}, dark: {...}}}
export function readSkin(data, id) {
  const ok = data && typeof data === "object" && data.format === SKIN_FORMAT && data.version === 1 && data.id === id &&
    isText(data.name) && data.tokens && ["paper", "dark"].every((t) => data.tokens[t] && typeof data.tokens[t] === "object" &&
      Object.entries(data.tokens[t]).every(([k, v]) => /^[a-z0-9-]{1,30}$/.test(k) && isColour(v)));
  if (!ok) throw new PaperError(["not a skin parcel for " + id]);
  return { id, name: data.name, tokens: data.tokens };
}

// The day's choice: the same paper on the same day, another one tomorrow (no randomness that needs a seed
// stored anywhere). day = "YYYY-MM-DD" in local time.
export function dayNumber(day) { return Math.floor(Date.parse(day + "T00:00:00Z") / 864e5); }
const pickOf = (list, n, day) => list.length ? list[((n % list.length) + list.length) % list.length] : null;
export function layOut(paper, { local = "", day = "" } = {}) {
  const n = Number.isFinite(dayNumber(day)) ? dayNumber(day) : 0;
  const newer = paper.release && local ? compareVersions(paper.release.version, local) > 0 : false;
  // the changelog as stories, newest first; with no newer release the newest story leads instead
  const stories = [...paper.changelog].sort((a, b) => compareVersions(b.version, a.version) || (a.date < b.date ? 1 : -1));
  return {
    date: paper.date,
    sample: paper.sample,
    lead: newer ? { kind: "release", ...paper.release } : stories[0] ? { kind: "story", ...stories[0] } : null,
    upToDate: !!paper.release && !!local && !newer && Number.isFinite(compareVersions(paper.release.version, local)),
    local,
    stories: newer ? stories.slice(0, 3) : stories.slice(1, 4),
    skins: paper.skins.slice(0, 2),
    background: pickOf(paper.backgrounds, n, day),
    artwork: pickOf(paper.artworks, n + 1, day),
    joke: pickOf(paper.jokes, n, day),
    coming: paper.coming.slice(0, 3),
  };
}
// References go through the core, which confines assets to the paper's directory prefix.
export function resolveRef(ref, source, base) {
  if (!safeRef(ref)) return "";
  const query = new URLSearchParams({ path: ref });
  if (source && source !== DEFAULT_SOURCE) query.set("source", source);
  return "/api/news/asset?" + query;
}
