# Task card: calibration charts as engineering drawings (disc-probe web page)

You are working in the git worktree `D:/disc-probe/.claude/worktrees/web-walkthrough`. Do NOT commit, push, switch
branches, stash or reset. Do NOT start servers. Do NOT edit any existing file: create only the two new files below.

## Goal

Write `discprobe/web/home/calchart.js`: an ES module with two pure functions that return SVG markup strings for the
calibration page. They replace two quick charts in `discprobe/web/home/calibrate.js` (`liveChart` and `realChart`,
read them, do not edit them). The calibration page will import your module; the wiring is done by someone else.

```js
export function liveChart(points, { head = null, zh = true } = {})
//   points: [{ r: radius_mm, d: offset_deg, s: sigma_deg }, ...] measured so far, any order, may be empty
//   head:   radius in mm the optical head is at now (number) or null
export function resultChart(measurement, { zh = true } = {})
//   measurement: { points: [{ lba, residual_deg, sigma_deg }, ...], span_mm: [r_lo, r_hi] | null, stopped: bool }
//   returns "" when there are no points
```

## The look (follow the reference, it is the designer's drawing)

Reference mockup: `D:/disc-probe/docs/goals/art-brief/review/mockups/标定 · 测几何（重画示例）-html.zip` (unzip it into a NEW
empty folder outside the repo, read `CalMeasure.dc.html`; the chart is the SVG on the right "paper"). A screenshot
of it: `C:/Users/ADMINI~1/AppData/Local/Temp/claude/0fa2f3b7e932577a/3cb97cf6-4528-48e8-a950-a898c53a3f9c/scratchpad/mock_geo/shot.png`.
The designer's rules (from the review, section 标定页 5):
- engineering drawing: thin axes; measured points as small open circles with vertical error bars (±sigma);
  the fit as a solid line; the confidence band as 45° thin hatching (NOT a filled block);
- where nothing was measured yet: leave it blank, a dashed vertical line at the head, the words
  "还没读到" / "not read yet" centred in the blank part. Never extend the fit line past the last measured radius;
- no red, no green, no fills of colour. Ink only (copper is reserved for "the person must decide", not used here).
Line widths (the site's illustration spec, at 1440 px wide): outlines/data 1.5 px ink 100 %; axes and fit line
1 px ink at 70 %; ticks, error bars, hatching 0.75 px ink at 40 %. Numbers and units in the monospace font.

## Details

- x axis: radius in mm, fixed 24 to 58, ticks and labels at 24, 30, 40, 50, 58; label "半径 mm" / "radius mm".
- y axis: offset in degrees, symmetric about 0, range = max(0.3, max(|d|+s)) * 1.15, rounded nicely; three labels
  (+range, 0, -range) like "+0.4°"; label "转角偏差" / "turn offset" at the top left.
- fit: weighted least squares straight line d = a + b·r with weights 1/s² (s floored at 0.01), drawn only from the
  first to the last measured radius, needs >= 2 points; band = fit ± (weighted RMS of residuals about the fit,
  at least the median s), drawn as a clipped polygon filled with an SVG <pattern> of 45° lines.
- liveChart: dashed vertical line at `head` (or at the largest r when head is null) when it is < 57; the blank text
  in the middle of the unmeasured part.
- resultChart: points have LBA, not radius. Convert with r(lba) = sqrt(A + B·lba), fitted so that the smallest LBA
  maps to span_mm[0] and the largest to span_mm[1] (constant linear density); if span_mm is missing, map LBA
  linearly onto 24..58 and label the axis "位置（扇区）" / "position (sectors)" instead of mm. When `stopped` is true,
  the region after the last point gets the "还没读到 / not read" treatment too.
- SVG: `viewBox="0 0 560 220"`, `class="chart"`, `role="img"` with an `aria-label` in the chosen language,
  `width="100%"`. Put a `<style>` inside the SVG using the page's CSS variables so both themes work:
  `--ink` (text and lines), `--ink-3` (secondary text), `--mono` (font). Do not hard-code theme colours.
  Pattern ids must be unique per call (two charts can be on one page).
- Escape nothing user-controlled? All inputs are numbers; still guard against NaN/Infinity (skip such points).

## Tests

Create `tests/test_calchart.mjs` (run with `node tests/test_calchart.mjs`, plain `node:assert`, no packages):
empty input; one point (no fit line); many points (fit line present, its x2 equals the last point's x, never
beyond); head at 40 mm gives the dashed line and the blank words; head null and last r 57.5 gives no blank words;
resultChart with span_mm maps the first/last LBA to the span ends (check the circles' cx); resultChart without
span_mm uses the sector label; two calls give different pattern ids; NaN points are skipped; zh=false gives English.
Also run the existing `node tests/test_geo_progress.mjs` and `node tests/test_web_guidance.mjs` (must still pass).

## Done means

Both files exist, all the tests above pass, and a short note at the top of calchart.js says what it draws and
cites the designer's rules. Report the test output.
