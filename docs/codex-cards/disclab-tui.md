# Task card: Disc Lab TUI, practice mode and structured output

Worktree: `D:/disc-probe/.claude/worktrees/disclab-tui`, branch `dev/disclab-tui-20261113` (from Disc Lab 2ec80ce).
Another Codex works in parallel on scenario files, fault injection and fault scoring in a sibling branch; it owns `disclab/box.py`, `disclab/drive.py`, new `disclab/faults.py`, `disclab/scenario.py`, `disclab/SCENARIO.md`. **Do not edit those files.** You both add subcommands to `disclab/__main__.py`: keep your edits there small and self-contained (one block registering your subcommands) so the merge is easy.

## Hard rules (keep unchanged)
- Do NOT commit, push, stash, reset or switch branches.
- Do not edit anything under `discprobe/`.
- No real drives, no burns, no network beyond the local web server that `disclab web` already starts (only in tests and your own checks, on a free port). Never use ports 8772, 8795, 8798, 8812, 8813, 8841, 8863, 8877, 8879.
- Standard library only for the TUI (no curses-only features that break on Windows; plain prompts, numbered menus, ANSI colour only when the terminal supports it, and a `--plain` mode).
- At most 4 CPU-heavy processes. Do not use any word starting with "blin" in commands or paths (a hook blocks it).
- Existing commands, scores and all 30 tests stay as they are.

## Why
The user wants Disc Lab command line and TUI first, a practice mode so a new user can walk the whole disc-probe flow on a virtual drive before burning real discs, and every capability reachable as structured data, so a web GUI shell can be added later as a pure translator (the same principle as disc-probe).

## What to do
1. **`--json` on every disclab command**: a single JSON object on stdout (status, lab, outputs, scores, errors), human text going to stderr in that mode. Put the shared helper in a new `disclab/jsonout.py`. Document the shape per command in `disclab/API.md` (Chinese and English).
2. **Lab state**: `LAB/state.json` (exists) gains a `steps` record of what has been done (box made, which discs burned with what, geo runs, photos, L, pictures, scores) with timestamps and paths, written by each command, so any front end can show progress without parsing text. Keep existing keys.
3. **TUI** `python -m disclab tui [--lab LAB] [--plain]` (new `disclab/tui.py`): menus for
   - choose or create a box (media, count, seed, reader profile);
   - walk the flow on one disc: put it in the tray → burn the measurement disc → `timing` → `geo` → make a picture ISO from a bundled sample picture → virtual burn → photos (the lab's own simplified two-texture target; say plainly that the `checkdisc` target cannot be rendered yet) → photo L → picture with L;
   - see scores: each step's result next to the truth (geo error, L error, placement error), from the JSON the commands write.
   Every action calls the same functions/commands the CLI uses; the TUI holds no state of its own beyond `state.json`.
4. **Practice mode** `python -m disclab practice [--media dvd-r] [--lab LAB] [--port N] [--lan]` (new `disclab/practice.py`): make a small practice box (2–3 discs of the chosen media, default reader), start disc-probe's web page on the virtual drive (reuse `disclab web`), print the address and a short Chinese/English guide of what to try, and on exit print where the practice results are. No discs are used up; say so.
5. README (both languages): sections for the TUI, practice mode and `--json`; a "next steps" list: rewritable discs and erase, more faults (timeouts, whole-turn aliasing, photo pose/exposure), rendering multi-byte textures so the check disc can be photographed in practice, a web shell over the JSON API.
6. Tests: `--json` shape for each command (on tiny labs), `state.json` steps, TUI driven by scripted input (`--plain`, stdin) through a short flow, practice command start/stop on a free port.

## Acceptance
- `python -m pytest disclab/tests -q` all pass (report counts).
- A scripted TUI run on this machine through box → geo → picture → score, with its transcript, in `disclab/TUI_REPORT.md` (Chinese).
