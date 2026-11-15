// The lamp view's scheduling (design/editor-lamp.mjs) with a fake worker and clock: one render at a time, only the
// newest pose, quick frames while moving and a still frame once settled, stale revisions dropped, errors and retry.
// Also the pose controls' height scale (design/lamp-pose.mjs). Run: node tests/test_editor_lamp.mjs
import assert from "node:assert/strict";
import { LampPreview, target, DRAG_SIZE } from "../discprobe/web/home/design/editor-lamp.mjs";
import { zOfCm, cmOfZ, snapCm, lampPose, DESIGN_Z_MM } from "../discprobe/web/home/design/lamp-pose.mjs";

let clock = 0;
const sent = [], worker = { postMessage: m => sent.push(m), terminate() { this.dead = true; } };
const changes = [];
const lamp = new LampPreview({ worker: () => worker, bitmap: async image => ({ ...image, close() { this.closed = true; } }), settle: 100, now: () => clock });
lamp.onChange = () => changes.push(lamp.phase);
const doc = { calls: 0 }, document = () => (doc.calls++, { layers: [] });
const pose = y => ({ camera: [0, y, 330], flash: [-43.66, y + 19.79, 330], rotate: 0 });
const renders = () => sent.filter(m => m.type === "render");
const answer = async (m, extra = {}) => { await lamp.message({ type: "frame", id: m.id, rev: m.rev, pose: m.pose, size: m.size, k: m.k, n: m.n, paper: m.paper, exposure: m.exposure, fine: m.fine, image: { w: m.size }, ms: 5, ...extra }); };

// first view: the work goes over once, then a quick frame (nothing is up yet)
assert.equal(lamp.view({ rev: 1, document, pose: pose(70), screen: 900 }), null);
assert.equal(doc.calls, 1);
assert.deepEqual(sent.map(m => m.type), ["doc", "render"]);
assert.equal(renders()[0].size, DRAG_SIZE); assert.equal(renders()[0].fine, false);
assert.equal(lamp.phase, "waiting");
lamp.view({ rev: 1, document, pose: pose(70), screen: 900 });
assert.equal(renders().length, 1, "same request is not sent twice");

// the hand moves while the quick frame is being made: only the newest pose waits, nothing piles up
for (let y = 71; y < 80; y++) { clock += 8; lamp.view({ rev: 1, document, pose: pose(y), screen: 900 }); }
assert.equal(renders().length, 1, "one render in the worker at a time");
await answer(renders()[0]);
assert.equal(renders().length, 2); assert.equal(renders()[1].pose.camera[1], 79, "then only the newest pose");
assert(lamp.shown, "a frame is up"); assert.equal(lamp.phase, "waiting");
await answer(renders()[1]);
assert.equal(lamp.view({ rev: 1, document, pose: pose(79), screen: 900 }).w, DRAG_SIZE);
assert.equal(lamp.phase, "refining");

// still for `settle` ms: the still frame at screen size, k from FINE_SAMPLES
clock += 150;
lamp.view({ rev: 1, document, pose: pose(79), screen: 900 });
const fine = renders().at(-1);
assert.deepEqual([fine.size, fine.k, fine.fine], [900, target(900, false).k, true]);
await answer(fine);
assert.equal(lamp.view({ rev: 1, document, pose: pose(79), screen: 900 }).w, 900);
assert.equal(lamp.phase, "ready");
assert.equal(renders().length, 3, "a still frame is cached");

// moving away during a still frame does not wait for it: the worker drops it at its next band
clock += 10; lamp.view({ rev: 1, document, pose: pose(90), screen: 900 }); await answer(renders().at(-1)); clock += 200;
lamp.view({ rev: 1, document, pose: pose(90), screen: 900 });
const slow = renders().at(-1); assert(slow.fine);
clock += 5; lamp.view({ rev: 1, document, pose: pose(91), screen: 900 });
assert.equal(renders().at(-1).pose.camera[1], 91, "sent at once, the still frame is superseded");
await lamp.message({ type: "dropped", id: slow.id, rev: 1 });
await answer(renders().at(-1));
// back to a pose seen still: shown at once, from the cache
clock += 500;
assert.equal(lamp.view({ rev: 1, document, pose: pose(79), screen: 900 }).w, 900); assert.equal(lamp.phase, "ready");

// a new revision: its document goes over once; frames of the old one are thrown away; the old frame stays up meanwhile
const before = lamp.shown;
lamp.view({ rev: 2, document, pose: pose(79), screen: 900 });
assert.equal(doc.calls, 2); assert.equal(sent.filter(m => m.type === "doc").length, 2);
assert.equal(lamp.shown, before, "the old frame stays up until the new work's first");
const quick2 = renders().at(-1); assert.equal(quick2.rev, 2); assert.equal(quick2.fine, false);
await lamp.message({ type: "frame", id: quick2.id - 1, rev: 1, pose: pose(1), size: 10, k: 1, n: 512, image: { w: 10 }, ms: 1 });
assert.equal(lamp.shown, before, "an old revision's frame is dropped");
await answer(quick2); assert.equal(lamp.shown.rev, 2);

// leaving the view cancels the waiting request; errors stop it until retry
lamp.pause(); assert.equal(lamp.phase, "paused"); assert.equal(lamp.queued, null);
lamp.view({ rev: 2, document, pose: pose(79), screen: 900 });
await lamp.message({ type: "error", rev: 2, error: "lamp table" });
assert.equal(lamp.phase, "error"); assert.equal(lamp.error, "lamp table"); assert(worker.dead);
const n = sent.length; lamp.view({ rev: 2, document, pose: pose(79), screen: 900 }); assert.equal(sent.length, n, "nothing sent after an error");
worker.dead = false; lamp.retry(); lamp.view({ rev: 2, document, pose: pose(79), screen: 900 });
assert.deepEqual(sent.slice(n).map(m => m.type), ["doc", "render"], "retry starts over");

// targets: quick frames are small; still frames average about FINE_SAMPLES across, within the sample budget
assert.deepEqual(target(300, true), { size: 300, k: 1, n: 512 });
assert.equal(target(2000, false).k, 1); assert.equal(target(2000, false).n, 2048);
assert(target(473, false).k * target(473, false).size >= 2000);

// the height scale: 21 cm is the design height; marks round trip; the lever snaps onto marks
assert.equal(zOfCm(21), DESIGN_Z_MM); assert.equal(Math.round(zOfCm(30) * 10) / 10, 298.7); assert.equal(Math.round(zOfCm(70) * 10) / 10, 698.7);
for (const cm of [12, 21, 25.5, 30, 44, 70, 80]) assert(Math.abs(cmOfZ(zOfCm(cm)) - cm) < 1e-9);
assert.equal(snapCm(21.6), 21); assert.equal(snapCm(25.3), 25.5); assert.equal(snapCm(200), 80);
// the pose: the scene's phone, the lever's height (the flash rides with the phone), the dial's turn
const scene = { cam: [0, -70, 330], follows: true };
const r6 = o => JSON.parse(JSON.stringify(o, (k, v) => typeof v === "number" ? Math.round(v * 1e6) / 1e6 : v));
assert.deepEqual(r6(lampPose({ scene, lookY: 70 })), { camera: [0, 70, 330], flash: [-43.66, 89.79, 330], rotate: 0 });
const p = lampPose({ scene, lookY: 70, lamp: { rotate: -30, z: DESIGN_Z_MM } });
assert.deepEqual(p.camera, [0, 70, DESIGN_Z_MM]); assert.equal(p.flash[2], DESIGN_Z_MM); assert.equal(p.rotate, 330);
const desk = lampPose({ scene: { cam: [0, -70, 330], follows: false, lamp: [-260, -220, 420] }, lookY: 70, lamp: { z: 250 } });
assert.equal(desk.camera[2], 250); assert.equal(desk.flash[2], 420, "a desk lamp stays where it is");
assert.equal(lampPose({ pose: { camera: [0, 28.45, 206.5], flash: [0, 76.35, 206.5], delta_scale: .93 } }).delta_scale, .93);
console.log("editor lamp: one render at a time, newest pose only, quick then still frames, cache, revisions, errors/retry; lamp pose and height scale");
