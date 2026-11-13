// A stand-in for the core's works library: the /api/works routes of docs/goals/pastworks/SPEC.md,
// kept in memory, answering through a fetch-shaped function. For tests, file previews and ?mock demos
// only; the real store is the core's (works/<id>/ beside the results). Its "zip" is a JSON bundle
// with a mock marker, which only this mock reads back.
const MARK = "DP-MOCK-WORKS-ZIP\n";
const iso = (ms) => {
  const d = new Date(ms), off = -d.getTimezoneOffset(), sign = off >= 0 ? "+" : "-", a = Math.abs(off);
  const p = (n, w = 2) => String(n).padStart(w, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}${sign}${p(Math.floor(a / 60))}:${p(a % 60)}`;
};
const idFor = (ms, n) => {
  const d = new Date(ms), p = (v) => String(v).padStart(2, "0");
  return `w-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}-${(n * 2654435761 >>> 0).toString(16).slice(-4).padStart(4, "0")}`;
};
async function dataURL(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let s = ""; for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return `data:${blob.type || "image/png"};base64,${btoa(s)}`;
}
const asText = async (body) => body == null ? "" : typeof body === "string" ? body : await new Response(body).text();

export function createMockWorks({ now = () => Date.now(), works: seed = [], latency = 0 } = {}) {
  const works = new Map(), trash = new Map(), designs = new Map(), thumbs = new Map(), history = new Map();
  let serial = 0, last = 0;
  // every write gets a strictly later stamp, so If-Match always tells two saves apart
  const tick = () => { last = Math.max(now(), last + 1); return last; };
  // events as the core writes them (works.py _event): {type, time, ...}; renames and marks carry `changes`, ISOs and burns `record`
  const log = (id, e) => { const time = iso(tick()); (history.get(id) ?? history.set(id, []).get(id)).push({ type: e.type, time, ...e }); return time; };
  // eslint-disable-next-line no-unused-vars
  function make({ name, media = "dvd", disc_type = "-R", id: _i, created_at: _c, updated_at: _u, opened_at: _o, thumb_url: _t, history: _h, ...rest }) {
    const t = tick(), id = idFor(t, ++serial), at = iso(t);
    const w = { id, name: String(name || "未命名作品"), created_at: at, updated_at: at, opened_at: at, media, disc_type,
      batch: null, geo_run: null, photo_l: null, cell_um: 20, status: "draft", discs: [], source_file: null, ...rest };
    works.set(id, w); history.set(id, []);
    return w;
  }
  for (const s of seed) {
    const { design, history: h, ...fields } = s, w = make(fields);
    for (const k of ["created_at", "updated_at", "opened_at"]) if (s[k]) w[k] = s[k];      // samples carry their own dates
    if (design != null) designs.set(w.id, typeof design === "string" ? design : JSON.stringify(design));
    if (h) history.set(w.id, h.map((e) => ({ ...e })));
  }
  const view = (w) => ({ ...w, discs: w.discs.map((d) => ({ ...d })), thumb_url: thumbs.has(w.id) ? `/api/works/${w.id}/thumb?v=${encodeURIComponent(w.updated_at)}` : null });
  const reply = (status, data, headers = {}) => new Response(data === undefined ? null : typeof data === "string" || data instanceof Blob ? data : JSON.stringify(data),
    { status, headers: { "Content-Type": typeof data === "string" ? "text/plain; charset=utf-8" : "application/json", ...headers } });
  const fail = (status, error) => reply(status, { error });
  function copyOf(w, name) {
    const c = make({ ...w, name, id: undefined, created_at: undefined, discs: [], status: "draft" });
    if (designs.has(w.id)) designs.set(c.id, designs.get(w.id));
    if (thumbs.has(w.id)) thumbs.set(c.id, thumbs.get(w.id));
    log(c.id, { type: "duplicated", source: w.id });
    return c;
  }

  async function route(url, init = {}) {
    const u = new URL(url, "http://mock.invalid"), method = (init.method ?? "GET").toUpperCase();
    const h = new Headers(init.headers ?? {});
    const parts = u.pathname.split("/").filter(Boolean).map(decodeURIComponent);   // api works <id> <tail>
    if (parts[0] !== "api" || parts[1] !== "works") return fail(404, "not found");
    const [, , id, tail] = parts;
    if (!id) {
      if (method === "GET") {
        let list = [...works.values()];
        const status = u.searchParams.get("status"), media = u.searchParams.get("media");
        if (status) list = list.filter((w) => w.status === status);
        if (media) list = list.filter((w) => w.media === media);
        list.sort(u.searchParams.get("sort") === "name" ? (a, b) => a.name.localeCompare(b.name, "zh") : (a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
        return reply(200, { works: list.map(view) });
      }
      if (method === "POST") {
        const b = JSON.parse(await asText(init.body) || "{}");
        if (!b.name || typeof b.name !== "string") return fail(400, "name required");
        if (b.media && !["cd", "dvd", "bd"].includes(b.media)) return fail(400, "bad media");
        const w = make({ name: b.name.slice(0, 200), media: b.media || "dvd" });
        log(w.id, { type: "created" });
        return reply(201, view(w));
      }
      return fail(405, "method");
    }
    if (id === "import" && method === "POST") {
      const text = await asText(init.body), file = decodeURIComponent(h.get("X-Filename") ?? "");
      if (text.startsWith(MARK)) {
        const b = JSON.parse(text.slice(MARK.length));
        // as the core: a zip keeps its id, metadata and record; an id already here (or in the bin) is a conflict
        if (works.has(b.work.id) || trash.has(b.work.id)) return fail(409, "work id already exists");
        const w = { ...b.work, discs: (b.work.discs ?? []).map((d) => ({ ...d })) };
        works.set(w.id, w);
        if (b.design != null) designs.set(w.id, b.design);
        if (b.thumb) thumbs.set(w.id, await (await fetch(b.thumb)).blob());
        history.set(w.id, [...(b.history ?? [])]);
        return reply(200, view(w));
      }
      let d; try { d = JSON.parse(text); } catch { return fail(400, "not a .zip or .discdesign"); }
      if (d?.format !== "disc-probe design" || !Array.isArray(d.layers)) return fail(400, "not a .discdesign");
      const w = make({ name: file.replace(/\.(discdesign|json)$/i, "") || "导入的作品", media: ["cd", "dvd", "bd"].includes(d.media) ? d.media : "dvd",
        cell_um: d.cell ? Math.round(d.cell * 1000) : 20, geo_run: typeof d.geo === "string" ? d.geo : null, source_file: file || null });
      designs.set(w.id, text);
      log(w.id, { type: "imported", source: file });
      return reply(201, view(w));
    }
    const w = works.get(id);
    if (tail === "restore" && method === "POST") {
      const t = trash.get(id);
      if (!t) return fail(404, "not in the bin");
      trash.delete(id); works.set(id, t); log(id, { type: "restored" });
      return reply(200, view(t));
    }
    if (!w) return fail(404, "no such work");
    if (!tail) {
      if (method === "GET") {
        w.opened_at = iso(tick());
        return reply(200, { work: view(w), history: (history.get(id) ?? []).slice(-50) });
      }
      if (method === "PATCH") {
        const b = JSON.parse(await asText(init.body) || "{}");
        if ("status" in b && !["draft", "iso_ready", "burned", "done", "failed"].includes(b.status)) return fail(400, "bad status");
        if (b.status === "failed" && !String(b.note ?? "").trim()) return fail(400, "a failed work needs a reason");
        if ("name" in b) {
          const name = String(b.name).trim();
          if (!name) return fail(400, "name required");
          w.name = name.slice(0, 200);
        }
        if ("geo_run" in b && b.geo_run != null && (/[:\\]/.test(b.geo_run) || b.geo_run.startsWith("/") || b.geo_run.split("/").includes(".."))) return fail(400, "geo run must be relative to the data directory");
        if ("status" in b) w.status = b.status;
        if ("note" in b) w.note = b.note;
        for (const k of ["disc_type", "batch", "geo_run", "photo_l", "cell_um"]) if (k in b) w[k] = b[k];
        w.updated_at = log(id, { type: Object.keys(b).join() === "name" ? "renamed" : "marked", changes: b });
        return reply(200, view(w));
      }
      if (method === "DELETE") { works.delete(id); trash.set(id, w); return reply(200, { ok: true, id }); }
      return fail(405, "method");
    }
    if (tail === "design") {
      if (method === "GET") return designs.has(id) ? reply(200, designs.get(id), { "Content-Type": "application/json" }) : fail(404, "no design yet");
      if (method === "PUT") {
        const match = h.get("If-Match");
        if (match && match !== w.updated_at) return reply(409, { error: "changed elsewhere", work: view(w) });
        const text = await asText(init.body);
        if (text.length > 64 * 1024 * 1024) return fail(413, "too big");
        let d; try { d = JSON.parse(text); } catch { return fail(400, "not JSON"); }
        if (d?.format !== "disc-probe design") return fail(400, "not a .discdesign");
        designs.set(id, text);
        if (["cd", "dvd", "bd"].includes(d.media)) w.media = d.media;
        if (d.cell) w.cell_um = Math.round(d.cell * 1000);
        if (typeof d.geo === "string") w.geo_run = d.geo;
        w.updated_at = log(id, { type: "saved" });
        return reply(200, view(w));
      }
    }
    if (tail === "thumb") {
      if (method === "GET") return thumbs.has(id) ? new Response(thumbs.get(id), { status: 200, headers: { "Content-Type": "image/png" } }) : fail(404, "no thumbnail");
      if (method === "PUT") {
        const body = init.body instanceof Blob ? init.body : new Blob([init.body ?? ""], { type: "image/png" });
        thumbs.set(id, body);                     // as in the core, a picture moves updated_at too
        w.updated_at = log(id, { type: "thumb" });
        return reply(200, view(w));
      }
    }
    if (tail === "duplicate" && method === "POST") {
      const b = JSON.parse(await asText(init.body) || "{}");
      return reply(201, view(copyOf(w, b.name || `${w.name} 副本`)));
    }
    if (tail === "export" && method === "GET") {
      const t = thumbs.get(id);
      const bundle = { work: w, design: designs.get(id) ?? null, history: history.get(id) ?? [], thumb: t ? await dataURL(t) : null };
      return new Response(MARK + JSON.stringify(bundle), { status: 200, headers: { "Content-Type": "application/zip",
        "Content-Disposition": `attachment; filename="${w.id}.zip"` } });
    }
    return fail(404, "not found");
  }
  const calls = [];
  return {
    calls, works, trash, designs, thumbs, history,
    async fetch(url, init) {
      calls.push({ url: String(url), method: (init?.method ?? "GET").toUpperCase(), headers: Object.fromEntries(new Headers(init?.headers ?? {})) });
      if (latency) await new Promise((r) => setTimeout(r, latency));
      return route(String(url), init);
    },
    // what another window would do: save the design behind this page's back
    touch(id) { const w = works.get(id); w.updated_at = log(id, { type: "saved" }); return w.updated_at; },
    // what `image --work` / `burn --work` append (works.py link): a discs[] record and its history event
    link(id, { type = "burn", ...fields }) {
      const w = works.get(id), record = { type, time: iso(tick()), result: "completed", ...fields };
      w.discs.push(record); w.status = type === "burn" ? "burned" : "iso_ready";
      w.updated_at = log(id, { type, record });
      return record;
    },
  };
}
