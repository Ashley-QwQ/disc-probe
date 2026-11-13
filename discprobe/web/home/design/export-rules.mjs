// What the design page burns, decided in one place: which measured geometry, which textures, which grid.
// The page, the preview's checklist and the tests all ask here, so what the checklist says is what is made.
// Pure functions: no DOM, no fetch.

// The two textures of a black-and-white burn, per disc kind (the core's own defaults: `image --dark/--light`,
// cdimage 0D/AA). Background (slot 0) is light; every other material is dark.
export const TEXTURES = { dvd: { light: "B9", dark: "A5" }, cd: { light: "AA", dark: "0D" }, bd: { light: "B9", dark: "A5" } };

// The grids the core accepts (imagedisc.CELL_SIDES): µm → cells across the 120 mm disc.
export const CELLS = { 20: 6000, 10: 12000, 5: 24000 };
export const DEFAULT_CELL_UM = 20;

// Measured 2026-11-12 on a shared i5-12400F (12 threads, 32 GB, other jobs running): a work of three 2048 px
// photos (one turned 30°, one at 60 % opacity) and a pattern ring, `compose` + `image` for a full DVD.
//   20 µm: 25 s + 60 s, peak 0.55 GB   10 µm: 82 s + 53 s, peak 1.2 GB   5 µm: 277 s + 88 s, peak 4.4 GB
// (the peak is `image` loading the whole label array and copying it). Rounded up, so the page never promises less.
export const COST = {
  20: { minutes: 2, gb: 1 },
  10: { minutes: 4, gb: 2 },
  5: { minutes: 8, gb: 5 },
};

const good = (x) => ["good", "usable"].includes(x?.s) || x?.image_compatible === true;
const same = (a, b) => !!a && !!b && String(a).replace(/\\/g, "/").replace(/\/summary\.json$/, "").endsWith(String(b).replace(/\\/g, "/").replace(/\/summary\.json$/, ""));

// Whether a plan names a disc batch. "Decide later" plans (kind "unset") and plans without an id or maker code
// don't; a batch picked in the form but not measured yet ("new") does.
export function hasBatch(item) {
  return !!item && item.kind !== "unset" && !!(item.id || item.mid || item.imported);
}

// Which measured geometry the burn file is made from, and why. Never another batch's newest record unless the
// plan has no batch at all, and then the record is named.
//   catalogue: the library's entries for this disc kind; latest: the newest finished geo run's path (or null).
// Returns { path, source, name }: source is batch | imported | imported_corrected | saved | latest | none.
export function geoChoice(plan, catalogue = [], latest = null) {
  const item = plan?.item;
  const known = catalogue.filter(good);
  if (item?.imported) {
    const ok = item.image_compatible === true && known.some((x) => x.geo === item.geo);
    return ok ? { path: item.geo, source: item.correction_required ? "imported_corrected" : "imported", name: item.name ?? "" }
      : { path: null, source: "none", name: item.name ?? "" };
  }
  if (hasBatch(item)) {
    // the batch's own measurement, and nothing else: a geometry kept in the plan from before counts only if it is
    // this batch's
    if (good(item) && item.geo) return { path: item.geo, source: "batch", name: item.name ?? item.mid ?? "" };
    const entry = known.find((x) => (item.id && x.id === item.id) || (item.mid && x.mid === item.mid));
    if (entry?.geo) return { path: entry.geo, source: "batch", name: entry.name ?? entry.mid ?? "" };
    return { path: null, source: "none", name: item.name ?? item.mid ?? "" };
  }
  // no batch: the plan's own earlier geometry, else the newest finished one, said by name
  const saved = plan?.geo && known.find((x) => x.geo === plan.geo);
  if (saved) return { path: saved.geo, source: "saved", name: saved.name ?? saved.mid ?? "", when: saved.last ?? "" };
  if (latest) {
    const entry = catalogue.find((x) => same(latest, x.geo));
    return { path: latest, source: "latest", name: entry?.name ?? entry?.mid ?? "", when: entry?.last ?? "" };
  }
  return { path: null, source: "none", name: "" };
}

// The texture specs a document may put on the disc, from the label slots in use (slot → materials[slot].spec).
export function specsUsed(doc, slots) {
  const out = new Set();
  for (const s of slots) { const m = doc.materials?.[s]; if (m?.spec) out.add(String(m.spec).toUpperCase()); }
  return [...out];
}

// Colour, pattern-of-colour and effect content: anything that would burn a texture other than the disc kind's
// black-and-white pair. `slots`: label slots seen in a composed preview; effects are counted whether or not the
// preview grid caught them (they pick a texture by period at every cell).
export function experimentalContent(doc, media, slots = []) {
  const tx = TEXTURES[media] ?? TEXTURES.dvd, plain = new Set([tx.light, tx.dark, TEXTURES.dvd.light, TEXTURES.dvd.dark]);
  const colours = specsUsed(doc, slots).filter((s) => !plain.has(s));
  const shown = new Set((doc.layers ?? []).filter((l) => l.visible !== false).map((l) => l.id));
  const effects = (doc.assignments ?? []).filter((a) => a.effect && (a.layer === undefined || shown.has(a.layer))).length +
    (doc.layers ?? []).filter((l) => l.kind === "fx" && l.visible !== false).length;
  return { colours, effects, any: colours.length > 0 || effects > 0 };
}

// The document as it is burned. "bw": every material but the background becomes the disc kind's dark texture and
// the background its light one, so colours, colour patterns and effects burn as plain dark areas (their shapes
// stay). "experimental": the materials' own textures (DVD only), as the model chose them. Label slots are not
// touched either way, so the composed array is the same; only the texture list differs.
export function burnDocument(doc, media, mode = "bw") {
  const tx = TEXTURES[media] ?? TEXTURES.dvd;
  if (mode === "experimental" && media === "dvd") return { doc, mode, textures: doc.materials.map((m) => m.spec) };
  const materials = doc.materials.map((m, i) => ({ ...m, spec: i === 0 || m.id === "background" ? tx.light : tx.dark }));
  return { doc: { ...doc, materials }, mode: "bw", textures: materials.map((m) => m.spec) };
}

// The burn file may only carry what the mode allows: in black and white, the light and dark textures only.
export function checkTextures(used, media, mode) {
  const tx = TEXTURES[media] ?? TEXTURES.dvd;
  const extra = (used ?? []).map((s) => String(s).toUpperCase()).filter((s) => s !== tx.light && s !== tx.dark);
  return mode === "bw" && extra.length ? extra : [];
}

// How finely the pictures themselves are sampled: µm of disc per source pixel, finest visible picture layer.
// The export samples the working copy (≤ 2048 px a side), never the original file.
export function pictureSampling(layers = []) {
  let finest = Infinity;
  for (const l of layers) {
    if (l.kind !== "image" || l.visible === false || !l.w || l.shape) continue;
    finest = Math.min(finest, (l.width * 1000) / l.w);
  }
  return Number.isFinite(finest) ? finest : null;
}
