# Task card: the new-work page's disc field, rebuilt (kind dial always on, batch as a suggested free-text field)

Worktree: `D:/disc-probe/.claude/worktrees/review-fixes`, branch `web/review-fixes-20261112` (head aa1bf6a).
- Do NOT commit, push, stash, reset or switch branches.
- No drives. Port 8813 serves this folder for the person: do not stop or restart it, and don't start other servers
  outside tests.
- Edit only `discprobe/web/home/newplan.js`, `newplan.css`, `guidance.mjs` (words) and tests. If a catalogue or
  design file truly must change, stop and say why in the report instead.
- Another session is changing the design page on another branch: don't touch `design.js` or `design/`.

Read first:
- `C:/Users/Administrator/AppData/Local/Claude-Data/claude_pzs8sxrjxfjjc/side-session-notes/local_2cfb5b01-cd5a-41c5-9159-c871a79e44e1/persona-walkthroughs-20261112.md`,
  frictions 1, 2, 7 and 10 and design decision B;
- `newplan.js`: `fillBatches`, `chosen`, `calibrated`, `needsCalibration`, `calibrationNotice`, `readDrive`, `.np-choice`,
  `chooseKind`, `expandDial`, the dial, `unlisted`, `next()`, and what the plan saves as its `item`;
- `design/export-rules.mjs` (`hasBatch`, `geoChoice`, read only).

## The person's design
1. **The kind dial is always visible**, hanging from the sheet's top-right edge (where it is now, without the slide).
   It starts on the kind of the disc in the drive; with no disc, on the last kind used. If it's wrong, the person
   turns it right there. Remove the two "自动认出 / 手动选择" choices and `chooseKind`; a quiet line under the field
   can say "光驱里认出的是 DVD-R" when it was recognised. Keyboard and wheel on the dial stay as they are.
2. **"所使用的光盘" becomes a suggested text field, like 作品名.**
   - Label: "盘类型 / Disc type". The field shows the suggestion in grey; Tab accepts it; typing replaces it; there is
     the same `Tab` key cap as the name field.
   - The suggestion comes from what the drive read, in order:
     - (a) the batch in the library that matches the drive disc's maker code (MID) and kind; if several match, the
       most recently used;
     - (b) otherwise a new name made from what was read: maker and type when known, plus the MID, e.g.
       "RITEK DVD-R（RITEKF1）". Use what the drive reports; don't invent a brand from a MID.
     - (c) with no disc, the last batch used of this kind;
     - (d) else empty, with the help "例如：Verbatim DVD-R 16x".
   - While typing, a small list under the field shows the library's batches of this kind that match. Click or arrows +
     Enter picks one. Matching is case-insensitive, on name and MID.
   - Typing a name that matches no batch means a NEW batch. Keep the typed name, plus everything the drive read (MID,
     kind/type, sectors) when the drive disc is of this kind. It becomes a batch when it is calibrated or parameters
     are imported. Until then the plan's `item` is a "new" batch with its name/MID, so `hasBatch` is true and
     `geoChoice` returns "none" (no borrowed geometry).
   - **Remove "先不填 / Decide later".** A plan never silently uses another batch's geometry. If the person leaves the
     field empty, the plan has no batch; the line under the field says plainly "没选盘：画好后要刻时再选". That stays
     the page's existing no-batch behaviour downstream; do not change export-rules.
3. **The line under the field is one honest sentence for the state:**
   - measured: "已标定 · 2026-11-07";
   - imported from DIS: "参数来自 DIS（未经 DP 实测）";
   - new or unmeasured: "这批还没有参数：可以先画；要刻之前标定一次，或者带上已有参数". The links "标定这批" and
     "从 DIS 导入 · 手动填写" sit on that same line. Use "标定" (to calibrate) as the link, not "先去标定".
   - CD keeps "沿轨常数未知" where it applies.
   - Remove the separate budget paragraph from the paper; the disc budget belongs to the calibration page. Next stays
     "下一步：放进图片" in every state.
4. **The library link** ("去盘库看这批盘") shows only when the field names a library batch.
5. **"还剩 N / M 张"** shows when the batch has counts.

## Tests
Rewrite the affected parts of `tests/test_review_library_newwork.mjs` for:
- the dial always visible and starting from the drive;
- the suggestion order (a)-(d);
- Tab accepts;
- typing filters the list; Enter picks;
- a new name gives a "new" item with the MID and no borrowed geometry;
- the empty field gives no batch and the plain sentence;
- the status sentences per state;
- Next is always "放进图片".

Keep the bring-your-own-parameters tests passing. Run `python -m pytest -q tests` and every `node tests/*.mjs` / `*.cjs`
(skip the helper `tests/editor_runner.mjs`). Screenshots at 1440×900, paper and dark, to `.impeccable/disc-field/`:
recognised library batch, new batch typed, empty field, the suggestion list open.

## Done means
Tests pass, screenshots saved. Report the changes (file:line) and anything you couldn't do inside the boundary.

## Revision (after the first run stopped at export-rules.mjs:48)
Do not change `design/export-rules.mjs`. Solve it in `newplan.js`:
- A NEW batch's plan `item` gets its own id, `id: "new:" + a random id`, so `hasBatch` is true.
- It does NOT carry `mid`. Put what the drive read under different keys (`readMid`, `readKind`, `readSectors`), so
  `geoChoice`'s maker-code match (`item.mid && x.mid === item.mid`) never pulls another batch's geometry.
- A library batch picked from the list keeps its own `id`/`mid` as today.

Show anywhere the page names the new batch's maker code from `readMid`. Add a test that a new batch typed while a
measured batch with the same MID exists gets `geoChoice(...).source === "none"`; import export-rules read-only in
the test. Then do the whole card.
