# Task card: the designer review's open items on the library (盘库) and the new-work page (新作品)

Worktree: `D:/disc-probe/.claude/worktrees/review-fixes`, branch `web/review-fixes-20261112` (from release/1.0.0-alpha +
the spotlight work).
- Do NOT commit, push, stash, reset or switch branches.
- No drives: never load the real pages against a drive, and never burn.
- Don't start servers outside tests; never touch ports 8772, 8795, 8798, 8812, 8841, 8863.
- Edit only `discprobe/web/home/index.html`, `newplan.js`, `newplan.css`, `design.js` (header only, item N7),
  `guidance.mjs` (words) and tests.
- Do NOT edit the lobby, pastworks*, presetio*, calibrate*, photocal*, kit/, any Python, or any picture.
- Clean up your temp files.

Read first:
- the review: `C:/Users/Administrator/Downloads/评审意见.txt` (sections 盘库 and 新作品与装袋过场, the priority table rows 7 and 8,
  插画规范);
- the audit of what is open:
  `C:/Users/Administrator/AppData/Local/Claude-Data/claude_pzs8sxrjxfjjc/side-session-notes/local_2cfb5b01-cd5a-41c5-9159-c871a79e44e1/design-review-audit-20261112.md`
  (rows P7, P8, K1-K7, I4, I7, N2-N7, O2, O5, with file:line evidence; its screenshots are in
  `C:/Users/ADMINI~1/AppData/Local/Temp/claude/0fa2f3b7e932577a/3cb97cf6-4528-48e8-a950-a898c53a3f9c/scratchpad/audit-shots/`);
- `DESIGN.md` at the repo root.

## The house rules that still hold (they beat the review where they differ)
- **Colour:** only the disc has colour. Copper (`--copper`) marks only what needs the person, and at most one copper thing
  per screen.
- **Shadows** fall lower-left (light from the upper right). The review says upper-left; ignore that.
- **Motion:** `document.documentElement.dataset.motion === "off"` means instant. The person forces motion on while their
  system has reduced motion, so don't rely only on prefers-reduced-motion.
- **Words:** zh first with en. No dead ends: no control that does nothing.

## Library (盘库)
1. **P7 / K7 / I4.** The background shelves are line art behind the page. Keep the right-hand text column clear of them:
   mask the shelf art out under the text column, or drop the background line opacity to ≤ 6 % there. Background
   objects are outline only, ≤ 8 % ink, no fill.
2. **P8.** Model names never break at a hyphen ("Verbatim DVD-" / "RW 2x").
   - Use U+2011 in the displayed name, or `white-space: nowrap` per token.
   - When a name does not fit, narrow it by stepping `font-stretch` from 118 % (or the current value) down to 100 %
     before wrapping at spaces.
   - This also applies after the rolling-number animation fills the text back in (audit row P8 names the line).
3. **K1.** Split the bottom-left corner.
   - The position counter "01 / 08" stays on the slanted line, printed on the front edge of the current shelf.
   - The kinds DVD / CD / BD become one horizontal row above the bottom-left status line. The current kind gets a
     background in its disc tone (`--dvd` / `--cd` / `--bd`; this is the disc's colour, allowed).
4. **K2.** "光驱" (drives) is not a disc kind.
   - Move it out of that row to the header beside "盘库" as its own entry.
   - Or make the library top a two-tab switch "盘 / 光驱".
   - Pick the one that needs less churn and keeps keyboard order sane; explain the choice.
5. **K3.** The right column has three layers: name / one status sentence with its consequence / the numbers.
   - In the numbers, "还剩 N / M 张" comes first and larger.
   - Sector count becomes small monospace (for experts).
   - The other facts stay as they are.
6. **K4.** "就是光驱里这张": the disc on the shelf that is the drive's current disc is pulled forward out of the shelf by a
   short way (transform on that disc's element, eased). This is in addition to the copper line, not instead of it. Make
   sure there is then only one copper thing (I7): if the selected-disc highlight is also copper, make it ink.
7. **K5.** The single rainbow disc on a shelf: find in the code what it stands for.
   - If it marks something (the measurement disc, the drive's disc …), name it in the right column with the same word.
   - If it means nothing, remove the rainbow from it.
8. **K6.** "画廊" with the triangle is a dead button (the click returns early). Remove it from the library.
9. The library header has an extra "预设导入导出 / Presets" button that drops below the toolbar row and has hard-coded
   text.
   - Put it in the header row like its neighbours, and give it i18n like the rest.
   - Hide it when the core does not offer presets-io (that check exists: commit 28887c7).

## New work (新作品)
10. **N2.** The half-disc picker is closed by default: a small round stamp "DVD-R · 自动认出 / auto".
    - Clicking the stamp opens the existing half-disc (unchanged look). It also opens by itself when the disc was not
      recognised.
    - The stamp is not cut by the paper's top edge.
11. **N3.** The stamp handles only the kind; the batch dropdown handles only which batch. Place them next to each other
    on the paper.
12. **N4.** Replace the native batch `<select>` with a drawn control: a 4 px radius frame and a line-art arrow, keyboard
    accessible (listbox pattern or a styled select with `appearance: none` plus a drawn arrow, whichever is more robust).
    Ink and paper colours in both themes.
13. **N5 / O2.** When the chosen batch is not calibrated:
    - the paper says so plainly first: "这批盘第一次用，要先测一次，约 30–60 分钟，会用掉 1–2 张盘". Use the numbers the
      page already uses; keep them consistent.
    - The Next button text becomes "下一步：先标定" and leads to calibration.
    - When calibrated, it stays "下一步：放进图片".
14. **O5.** Beside the disc / batch name on the new-work paper, add a small link "去盘库看这批盘" that opens the library
    on that batch, the way the design header already does (design.js).
15. **N6.** The bagging animation plays in full only the first time in a session (1 s, as now).
    - After that it is shortened to about 0.4 s total.
    - Enter or a click skips it at any time.
    - Motion off → instant.
16. **N7.** In the design page header, put a very small bag icon left of the work name.
    - Use a small crop of `newplan/envelope_front_<theme>.webp`, or draw it as an inline SVG line icon in ink (preferred:
      crisp).
    - Its tooltip says "作品存在往期作品里 / Saved in past works".
    - The lobby file box part of this item is out of scope (baked picture).

**Not in this card:** N1 (turning the drive round so it enters from the bottom) is an art change and is done separately.

## Tests and proof
- Extend the existing node tests for these pages (search `tests/` for the library and newplan tests) and add new ones
  for: hyphen no-break, stamp collapsed/expanded, Next text when uncalibrated vs calibrated, bagging duration first vs
  repeat and skip, kinds row vs drives entry, the right-column order.
- Use mocks or the existing fake data; never a real drive.
- Run `python -m pytest -q tests` and every `node tests/*.mjs` / `*.cjs`. All must pass.
- Save screenshots (mock data, file URLs or the tests' own harness) to `.impeccable/review-fixes/`:
  - library at 1440×900, paper and dark, on a DVD shelf with a long hyphenated name;
  - new work at 1440×900, paper and dark: stamp closed, stamp open, and uncalibrated batch.

## Done means
Tests pass and the screenshots are saved. Report per item what changed (file:line) and every judgement call (K2 choice,
K5 meaning).
