import assert from "node:assert/strict";
import { test } from "node:test";
import { calibratedBatch, discDisplayKind, localDay } from "../discprobe/web/home/batches.mjs";
import { geoChoice } from "../discprobe/web/home/design/export-rules.mjs";
import { lastDiscCheck, lobbyStatus } from "../discprobe/web/home/lobby-state.js";
import { paintStopButton } from "../discprobe/web/home/burn-stop.js";
import { photoSaveWords } from "../discprobe/web/home/guidance.mjs";
import { dateText, filterWorks, isMeasurementWork } from "../discprobe/web/home/pastworks/works.mjs";

test("a measured maker code wins over a stale or draft batch on the same media", () => {
  const bad = { id: "old", mid: "RITEKF1", s: "stopped_early" };
  const other = { id: "other", mid: "MCC 004", s: "good", geo: "results/other" };
  const measured = { id: "saved", mid: " ritekf1 ", s: "usable", geo: "results/our-batch" };
  const entries = [bad, other, measured];
  const draft = { id: "new:work", kind: "new", name: "Named draft batch", readMid: "RITEKF1" };
  assert.equal(calibratedBatch(entries, draft, { mid: "MCC 004" }), measured);
  assert.equal(calibratedBatch(entries, bad), measured);
  assert.equal(calibratedBatch(entries, { id: "saved" }), measured);
  assert.equal(calibratedBatch(entries, { mid: "different" }, { mid: "RITEKF1" }), undefined);
  assert.equal(geoChoice({ item: draft }, entries).path, measured.geo);
});

test("the lobby attributes observations to a check and still reports a busy drive", () => {
  const disc = { present: true, blank: false, kind: "DVD-ROM", read_at: 120 };
  const state = { drives: [{ id: "X:", disc }], selectedDrive: "X:" };
  assert.equal(lastDiscCheck(state, "en", 305000), "Last checked 3 min ago");
  assert.equal(lastDiscCheck(state, "zh", 305000), "上次检测：3 分钟前");
  assert.match(lobbyStatus(state, "en"), /Recorded disc.*DVD-ROM/);
  assert.match(lobbyStatus({ ...state, checking: true }, "en"), /^Checking/);
  assert.match(lobbyStatus({ ...state, checkFailed: true }, "en"), /^Could not check/);
  assert.match(lobbyStatus({ ...state, checking: true, jobs: [{ drive: "X:", exit: null }] }, "en"), /busy/);
  assert.equal(discDisplayKind({ ...disc, blank: null }, "en"), "DVD-ROM");
});

test("calibration offers a plain stop for read-only phases and a burn stop for writing", () => {
  const button = { classList: { remove() {} }, setAttribute(key, value) { this[key] = value; } };
  for (const [lang, stop, burn, erase] of [["en", "Stop", "Stop burn", "Stop erasing"], ["zh", "停止", "停止刻录", "停止擦除"]]) {
    paintStopButton(button, false, lang);
    assert.equal(button.textContent, stop);
    assert.equal(button["aria-label"], stop);
    paintStopButton(button, true, lang);
    assert.equal(button.textContent, burn);
    paintStopButton(button, false, lang, true);
    assert.equal(button.textContent, erase);
  }
});

test("old generated measurement records are hidden, CLI burn reports and designed work stay visible", () => {
  const name = "dvd-measurement-1795147334128";
  const record = { type: "burn", iso_path: `C:\\iso\\${name}.iso` };
  const old = { name, source_design_missing: true, discs: [record] };
  const designed = { ...old, source_design_missing: false };
  const cli = { ...old, name: "Archive CLI work" };
  assert.equal(isMeasurementWork(old), true);
  assert.deepEqual(filterWorks([old, designed, cli]), [designed, cli]);
});

test("names and rendered dates agree near midnight local time", () => {
  const tz = process.env.TZ;
  try {
    process.env.TZ = "America/Toronto";
    const date = new Date("2026-11-20T04:10:43.031787+00:00");
    assert.deepEqual(localDay(date), [2026, 11, 19]);
    assert.match(dateText(+date, "en"), /Nov 19, 2026.*23:10/);
    assert.match(dateText(+date, "zh"), /19日.*23:10/);
    assert.match(dateText(+new Date("2026-11-20T05:10:00Z"), "en"), /Nov 20, 2026.*00:10/);
  } finally {
    if (tz === undefined) delete process.env.TZ; else process.env.TZ = tz;
  }
});

test("an unreadable preset is described separately from photo correction", () => {
  assert.equal(photoSaveWords({ written: false, reason: "invalid_preset" }).en,
    "The preset file could not be read. Save the preset again.");
  assert.match(photoSaveWords({ written: false, reason: "no_photo" }).en, /No photo result/);
});
