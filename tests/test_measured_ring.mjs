// The picture stays inside the measured part of the disc: the core refuses radii outside it
// (coverage.range_warning), so the page's ring, the editor's annulus and the burn file use the same cut.
import assert from "node:assert/strict";
import { geoChoice, measuredRing } from "../discprobe/web/home/design/export-rules.mjs";

assert.deepEqual(measuredRing(null, [24, 58]), null);
const [lo, hi] = measuredRing([25.724, 54.045], [24, 58]);
assert.ok(Math.abs(lo - 25.774) < 1e-9 && Math.abs(hi - 53.995) < 1e-9);
assert.deepEqual(measuredRing([20, 60], [24, 58]), [24, 58]);          // measured wider than the disc: the disc
assert.equal(measuredRing([30, 30.05], [24, 58]), null);                 // nothing left inside

const entry = { id: "a", mid: "RITEKF1", geo: "results/geo-H-1", s: "good", measured_mm: [25.724, 54.045] };
assert.deepEqual(geoChoice({ item: { id: "a", mid: "RITEKF1", s: "good", geo: "results/geo-H-1", measured_mm: [25.724, 54.045] } }, [entry]).measured, [25.724, 54.045]);
assert.deepEqual(geoChoice({ item: { id: "a", mid: "RITEKF1", s: "none" } }, [entry]).measured, [25.724, 54.045]);
assert.deepEqual(geoChoice({ item: { kind: "unset" } }, [entry], "results/geo-H-1").measured, [25.724, 54.045]);
assert.equal(geoChoice({ item: { kind: "unset" } }, [], null).measured, undefined);
console.log("measured ring: cut to the measurement, carried by every geometry choice");
