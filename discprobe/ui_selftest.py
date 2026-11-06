"""Self-test of the terminal layer: when it switches on, that it leaves measurements alone, and its advice."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile

from . import filldisc, guide, i18n, snake, timing, ui
from .sim import SimDrive


class FakeTty(io.StringIO):
    def isatty(self):
        return True

    def fileno(self):
        raise ValueError("not a real console")


class Utf8Tty(FakeTty):
    encoding = "utf-8"


class Keys:
    """Pressed keys for the game, one list per poll."""

    def __init__(self, *polls):
        self.polls = list(polls)
        self.closed = False

    def read(self):
        return self.polls.pop(0) if self.polls else []

    def close(self):
        self.closed = True


ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
LONG_ENGLISH = re.compile(r"[A-Za-z]{3,}(?: [A-Za-z]{2,}){3,}")


def _term_matrix(c) -> None:
    pipe = ui.Term(io.StringIO(), env={"TERM": "xterm"}, platform="linux")
    c.check(not (pipe.interactive or pipe.ansi or pipe.color or pipe.animate), "a pipe gets nothing extra")
    tty = ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux")
    c.check(tty.interactive and tty.ansi and tty.color and tty.animate, "a terminal gets colour and animation")
    no_color = ui.Term(FakeTty(), env={"TERM": "xterm", "NO_COLOR": "1"}, platform="linux")
    c.check(no_color.interactive and not no_color.color and no_color.animate, "NO_COLOR drops colour only")
    c.check(not ui.Term(FakeTty(), env={"TERM": "dumb"}, platform="linux").interactive, "TERM=dumb counts as a pipe")
    c.check(not ui.Term(FakeTty(), env={"TERM": "xterm", "DISCPROBE_PLAIN": "1"}, platform="linux").interactive,
            "DISCPROBE_PLAIN=1 counts as a pipe")
    old = ui.Term(FakeTty(), env={}, platform="win32")      # GetConsoleMode cannot work on this stream
    c.check(old.interactive and not old.ansi and not old.color and not old.animate, "a console without ANSI falls back to plain text")
    still = ui.Term(FakeTty(), env={"TERM": "xterm", "DISCPROBE_NO_ANIMATION": "1"}, platform="linux")
    c.check(still.color and not still.animate, "DISCPROBE_NO_ANIMATION=1 keeps colour, drops motion")
    c.check(not ui.Term(Utf8Tty(), env={"TERM": "xterm"}, platform="linux").unicode, "ASCII by default, even on UTF-8")
    c.check(ui.Term(Utf8Tty(), env={"TERM": "xterm", "DISCPROBE_UNICODE": "1"}, platform="linux").unicode, "DISCPROBE_UNICODE=1 asks for finer glyphs")
    c.check(not ui.Term(FakeTty(), env={"TERM": "xterm", "DISCPROBE_UNICODE": "1"}, platform="linux").unicode, "finer glyphs need UTF-8")


def _progress_line(c) -> None:
    status = lambda: (0.25, "rung 6/22", 40.0)
    for name, env, wants_escape, wants_spinner in (
            ("colour", {"TERM": "xterm"}, True, True), ("NO_COLOR", {"TERM": "xterm", "NO_COLOR": "1"}, True, False)):
        s = FakeTty()
        p = ui.Progress(status, ui.Term(s, env=env, platform="linux"))
        p.tick(force=True)
        p.log("a line")
        p.close()
        text = s.getvalue()
        shown = ANSI.sub("", text)
        c.check("rung 6/22" in shown and "0:40 left" in shown and "a line\n" in shown, f"{name}: progress line and log line")
        c.check(("\x1b[36m" in text) == wants_spinner, f"{name}: colour {'on' if wants_spinner else 'off'}")
        c.check(any(f in shown for f in ui.SPINNER_ASCII), f"{name}: the spinner turns")
        c.check(not wants_escape or text.endswith("\x1b[?25h"), f"{name}: the cursor comes back")
    s = FakeTty()
    p = ui.Progress(status, ui.Term(s, env={}, platform="win32"))
    p.tick(force=True)
    p.close()
    c.check("\x1b" not in s.getvalue() and "rung 6/22" in s.getvalue() and s.getvalue().isascii(),
            "no ANSI: plain ASCII with carriage returns only")


def _layout(c) -> None:
    status = lambda: (0.25, "rotation test, zone 2/3", 40.0)
    tty = ui.Term(FakeTty(), env={"TERM": "xterm", "COLORTERM": "truecolor"}, platform="linux")
    plain = ui.Term(FakeTty(), env={"TERM": "xterm", "NO_COLOR": "1"}, platform="linux")
    for lang in ("en", "zh"):
        i18n.use(lang)
        try:
            for t in (tty, plain):
                p = ui.Progress(status, t, keys=Keys())
                for columns in (200, 100, 80, 60, 40, 24, 12):
                    line, width = p._render(columns)
                    shown = ANSI.sub("", line)
                    c.check(i18n.display_width(shown) == width <= max(10, columns - 1), f"{lang}, {columns} columns: the line fits ({width})")
                wide, narrow = ANSI.sub("", p._render(200)[0]), ANSI.sub("", p._render(40)[0])
                c.check(i18n.tr("Ctrl+C to stop") in wide and i18n.tr("g: game") in wide, f"{lang}: a wide line offers stop and the games")
                c.check("[" not in narrow and "25%" in narrow, f"{lang}: a narrow line drops the bar, keeps the percentage")
                p.keys = None
                p.close()
        finally:
            i18n.use("en")
    p = ui.Progress(status, tty)
    p.started = 100.0
    c.check(p._spinner(100.13) == p._spinner(100.13) == ui.SPINNER_ASCII[1], "the spinner follows the clock, not the draws")
    p.close()
    painted = ui.sweep("reading the disc", 0.8, tty)
    c.check("38;2;" in painted and ANSI.sub("", painted) == "reading the disc", "the light sweep only adds colour")
    sixteen = ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux")
    c.check("1;36" in ui.sweep("reading the disc", 0.8, sixteen), "16 colours: the sweep is a bold band")
    c.check(ui.sweep("reading the disc", 0.8, plain) == "reading the disc", "no colour: plain text")
    still = ui.Term(FakeTty(), env={"TERM": "xterm", "DISCPROBE_NO_ANIMATION": "1"}, platform="linux")
    c.check(ui.sweep("reading the disc", 0.8, still) == "reading the disc", "no motion: still text")
    p = ui.Progress(status, still)
    c.check(not any(f in ANSI.sub("", p._render(100)[0]) for f in ui.SPINNER_ASCII), "no motion: no spinner, the numbers stay")
    s = FakeTty()
    p = ui.Progress(lambda: (0.5, "same", None), ui.Term(s, env={"TERM": "xterm", "DISCPROBE_NO_ANIMATION": "1"}, platform="linux"))
    p.tick(force=True)
    size = len(s.getvalue())
    p.tick(force=True)
    c.check(len(s.getvalue()) == size, "an unchanged frame is not written again")
    p.close()
    level = [0.25]
    for term_used, flashes, name in ((sixteen, True, "colour"), (plain, False, "NO_COLOR"), (still, False, "no motion")):
        level[0] = 0.25
        p = ui.Progress(lambda: (level[0], "rung 3/22", None), term_used)
        c.check("\x1b[" not in p._percent(0.25, 1000.0)[1], f"{name}: the first percentage does not flash")
        level[0] = 0.26
        c.check((" 2\x1b[1;36m6\x1b[0m%" in p._render(100)[0]) == flashes, f"{name}: {'only the digit that changed flashes' if flashes else 'a new digit stays plain'}")
        p.percent_changed -= ui.PERCENT_FLASH_S
        c.check(" 26%" in p._render(100)[0], f"{name}: it goes back to the terminal's colour")
        level[0] = 0.30
        c.check(("\x1b[1;36m30\x1b[0m%" in p._render(100)[0]) == flashes, f"{name}: two digits that change both flash")
        level[0] = 0.996
        c.check(" 99%" in ANSI.sub("", p._render(100)[0]), f"{name}: 99.6% does not read as done")
        level[0] = 1.0
        full = p._render(100)[0]
        c.check(("\x1b[32m100%\x1b[0m" in full) == (term_used is not plain), f"{name}: 100% is green where there is colour")
        p.percent_changed -= ui.PERCENT_FLASH_S
        c.check(("\x1b[32m100%" in p._render(100)[0]) == (term_used is not plain), f"{name}: and stays green")
        p.close()
    for env, wanted in (({}, "32"), ({"COLORFGBG": "15;0"}, "92"), ({"COLORFGBG": "0;15"}, "32"), ({"COLORFGBG": "0;default;7"}, "32"), ({"COLORFGBG": "bad"}, "32")):
        c.check(ui.Term(FakeTty(), env={"TERM": "xterm", **env}, platform="linux").green == wanted, f"green for {env}: {wanted}")
    frame_bytes = len(ui.Progress(status, tty)._render(100)[0].encode())
    c.check(frame_bytes < 420, f"a true-colour frame stays small ({frame_bytes} bytes)")


def _modern_terminal(c) -> None:
    env = {"TERM": "xterm", "WT_SESSION": "x"}
    wt = ui.Term(Utf8Tty(), env=env, platform="linux")
    c.check(wt.blocks and wt.sync and wt.taskbar and not wt.unicode, "Windows Terminal draws blocks itself, and takes taskbar progress and synchronized frames")
    c.check(ui.Term(Utf8Tty(), env={"TERM": "xterm-256color", "TERM_PROGRAM": "claude-desktop"}, platform="linux").blocks, "so does the desktop app's terminal panel")
    c.check(not ui.Term(FakeTty(), env=env, platform="linux").blocks, "no blocks without UTF-8")
    other = ui.Term(Utf8Tty(), env={"TERM": "xterm"}, platform="linux")
    c.check(not (other.blocks or other.sync or other.taskbar), "a terminal that does not say who it is gets none of this")
    conemu = ui.Term(Utf8Tty(), env={"TERM": "xterm", "ConEmuANSI": "ON"}, platform="linux")
    c.check(conemu.taskbar and not conemu.blocks, "ConEmu takes taskbar progress only")
    c.check(ui.oklch(1, 0, 0) == (255, 255, 255) and ui.oklch(0, 0, 0) == (0, 0, 0), "OKLCH: white and black are themselves")

    level = [0.25]
    s = Utf8Tty()
    p = ui.Progress(lambda: (level[0], "same", None), ui.Term(s, env=env, platform="linux"))
    p.tick(force=True)
    c.check("\x1b]9;4;1;25\x07" in s.getvalue(), "the taskbar shows the percentage")
    p.tick(force=True)
    c.check(s.getvalue().count("\x1b]9;4;") == 1, "and hears it only when it changes")
    p.taskbar_at -= ui.TASKBAR_REFRESH_S
    p.tick(force=True)
    c.check(s.getvalue().count("\x1b]9;4;") == 2, "or now and then, for terminals that forget")
    level[0] = None
    p.tick(force=True)
    c.check("\x1b]9;4;3;0\x07" in s.getvalue(), "work of unknown length is indeterminate")
    p.close()
    c.check("\x1b]9;4;0;0\x07" in s.getvalue(), "closing clears the taskbar")
    s = Utf8Tty()
    p = ui.Progress(lambda: (0.25, "same", None), ui.Term(s, env={"TERM": "xterm"}, platform="linux"))
    p.tick(force=True)
    p.close()
    c.check("\x1b]" not in s.getvalue(), "other terminals are sent no taskbar sequence")

    p = ui.Progress(lambda: (0.25, "rotation test, zone 2/3", 40.0), ui.Term(Utf8Tty(), env=env, platform="linux"), pulse=[100.0, 900.0, 500.0])
    for fraction, shown in ((0.0, "─" * 20), (0.025, "╸" + "─" * 19), (0.05, "━" + "─" * 19), (0.5, "━" * 10 + "─" * 10), (0.999, "━" * 19 + "╸"), (1.0, "━" * 20)):
        c.check(p._bar(fraction, 0.0)[0] == shown, f"the bar at {fraction} moves in half cells")
        c.check(ANSI.sub("", p._bar(fraction, 0.0)[1]) == shown, f"and paint only adds colour at {fraction}")
    c.check(ui.SPARK[0] in p._spark()[0][0] and ui.SPARK[-1] in p._spark()[0][0] and len(p._spark()[0][0]) == ui.SPARK_CELLS, "read times fill a fixed width, lowest to highest")
    for columns in (200, 120, 100, 80, 60, 40, 24, 12):
        line, width = p._render(columns)
        c.check(i18n.display_width(ANSI.sub("", line)) == width <= max(10, columns - 1), f"with read times, {columns} columns: the line fits ({width})")
    c.check(ui.SPARK[-1] in ANSI.sub("", p._render(120)[0]) and ui.SPARK[-1] not in ANSI.sub("", p._render(80)[0]), "read times are the first thing a narrow line loses")
    frame_bytes = len(p._render(120)[0].encode())
    c.check(frame_bytes < 420, f"a full frame with bar and read times stays small ({frame_bytes} bytes)")
    p.close()

    class Timed:
        ok = True
        duration_us = 123.0

    class Device:
        def execute(self):
            return Timed()

        def idle(self, seconds):
            pass
    reader = ui.ProgressDevice(Device())
    reader.idle(0)
    c.check(not reader.read_times, "no read yet, nothing to show")
    reader.execute()
    c.check(not reader.read_times, "a read is noted in the pause after it, not while it is timed")
    reader.idle(0)
    c.check(list(reader.read_times) == [123.0], "the pause notes it")

    colour = ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux")
    plain = ui.Term(FakeTty(), env={"TERM": "xterm", "NO_COLOR": "1"}, platform="linux")
    line = "  python -m discprobe geo --drive H: --speed 8x"
    c.check(ANSI.sub("", ui.command(line, colour)) == line and "\x1b[1;36m geo\x1b[0m" in ui.command(line, colour), "a command to copy: the subcommand stands out, the text is untouched")
    c.check(ui.command(line, plain) == line, "no colour: as written")
    c.check(ui.command("  python -m pip install numpy", colour) == "\x1b[36m  python -m pip install numpy\x1b[0m", "another command: all one colour")
    lines = [f"Where you are, for DVD (CD: {guide.PROG} guide --media cd):", "", "  [x] Python packages        numpy", "  [ ] Geometry (geo)         not run yet", "Next:", "  Make it:", line, "All commands: x"]
    for text in lines:
        c.check(ANSI.sub("", ui.guide_line(text, colour)) == text and ui.guide_line(text, plain) == text, f"guide only adds colour: {text.strip()[:24]}")
    c.check("\x1b[32m[x]" in ui.guide_line(lines[2], colour) and "\x1b[2m[ ]" in ui.guide_line(lines[3], colour), "done is green, the rest steps back")
    i18n.use("zh")
    try:
        c.check(i18n.tr("Next:") in ANSI.sub("", ui.guide_line("Next:", colour)) and i18n.tr("Next:") != "Next:", "guide is translated before it is painted")
    finally:
        i18n.use("en")
    text = "usage: python -m discprobe x\n\nStart here:\n  guide       show\n\noptions:\n  -h, --help  show\n  --drive D   the drive\n  python -m discprobe random --output a\n"
    c.check(ANSI.sub("", ui.help_text(text, colour)) == text, "help only adds colour")
    c.check(ui.help_text(text, plain) == text, "no colour: help as argparse wrote it")
    c.check("\x1b[36m-h, --help\x1b[0m" in ui.help_text(text, colour) and "\x1b[36mguide\x1b[0m" in ui.help_text(text, colour) and "\x1b[1mStart here:\x1b[0m" in ui.help_text(text, colour),
            "headings and names stand out")


def _fill_disc(c) -> None:
    import random

    def game(shape):
        g = filldisc.FillDisc(12, 8, rng=random.Random(1))
        g.shape = shape
        g.x, g.y = g.cols - 1 - max(x for x, _ in shape), 2
        return g
    bar = filldisc.SHAPES[3]
    g = game(bar)
    x = g.x
    g.step()
    c.check(g.x == x - 1 and not g.burned, "a block moves left at each step")
    g.turn("up")
    g.turn("up")
    g.turn("up")
    c.check(g.y == 0, "up moves it, and the edge stops it")
    g.turn("right")
    c.check({(x, y) for x, y in g.shape} == {(i, 0) for i in range(4)}, "right spins it")
    g = game(bar)
    g.turn("right")
    c.check(g._fits(g._cells()) and g.x + 3 == g.cols - 1, "a block spun at the edge is nudged back inside")
    g = game(bar)
    while not g.burned:
        g.turn("left")
    c.check({(0, y) for y in range(2, 6)} == set(g.burned) and g.x >= g.cols - 2, "at the left it lands, and the next block comes in on the right")
    g = game(bar)
    g.burned = dict.fromkeys([(0, 0), (0, 1), (0, 6), (0, 7), (1, 0)], "block1") | {(3, 0): "block2"}
    while not g.score:
        g.turn("left")
    c.check(g.score == 1 and g.best == 1 and g.burned == {(0, 0): "block1", (2, 0): "block2"}, "a full column clears, scores, and what was right of it moves left, colours and all")
    g = game(bar)
    g.burned = dict.fromkeys([(g.cols - 2, y) for y in range(7)], "block0")
    g.best = 4
    g.step()
    c.check(g.over and g.best == 4, "a stack that reaches the right edge ends the game")
    best = g.best
    c.check(g.step() == [] and g.turn("left") == [], "a finished game does not move")
    c.check(sum(g.cell(x, y) != "field" for x in range(g.cols) for y in range(8)) == len(g.burned), "a finished game shows only what landed")
    g.reset()
    c.check(not g.over and g.score == 0 and g.best == best and not g.burned, "a new game starts clean and keeps the best score")
    g = filldisc.FillDisc(14, 8, rng=random.Random(3))
    kinds = [g.kind]
    for _ in range(40):
        kind = g.kind
        while g.kind == kind:
            g.turn("left")
        g.burned.clear()
        kinds.append(g.kind)
    c.check(all(a != b for a, b in zip(kinds, kinds[1:])) and set(kinds) == set(filldisc.BLOCK_KINDS), "every block gets a colour, never the same as the last one")
    c.check(all(k in ui.GAME_CELLS and k in ui.GAME_GLYPHS for k in filldisc.BLOCK_KINDS), "every colour can be drawn, with and without colour")
    g = filldisc.FillDisc(14, 8, rng=random.Random(7))
    moves = random.Random(9)
    drawn = {(x, y): g.cell(x, y) for x in range(14) for y in range(8)}
    played = 0
    while not g.over and played < 4000:
        changed = g.turn(moves.choice(("up", "down", "left", "right"))) if played % 3 else g.step()
        drawn.update({(x, y): kind for x, y, kind in changed})
        played += 1
        if drawn != {(x, y): g.cell(x, y) for x in range(14) for y in range(8)}:
            break
    c.check(drawn == {(x, y): g.cell(x, y) for x in range(14) for y in range(8)} and played > 50, "drawing only the changed cells always gives the true board")
    c.check(filldisc.FillDisc().step_s == filldisc.SLOWEST_STEP_S, "the first blocks are slow")
    fast = filldisc.FillDisc()
    fast.score = 1000
    c.check(fast.step_s == filldisc.FASTEST_STEP_S, "it speeds up with the score, to a limit")


def _snake(c) -> None:
    import random as shared_random
    before = shared_random.getstate()
    g = snake.Snake(10, 6)
    g.food = (5, g.body[0][1])
    head, length = g.body[0], len(g.body)
    g.step()
    c.check(g.body[0] == (head[0] + 1, head[1]) and len(g.body) == length and not g.over, "the snake moves")
    g.turn("left")
    c.check(not g.queued, "the snake cannot reverse into itself")
    g.step()
    c.check(g.score == 1 and len(g.body) == length + 1 and g.food not in g.body, "eating grows it and places new food")
    g.turn("up")
    g.turn("left")
    g.step()
    g.step()
    c.check(g.heading == (-1, 0), "two quick turns are both kept")
    for _ in range(20):
        g.step()
    best = g.score      # it may have eaten again on the way to the wall
    c.check(g.over and best >= 1 and g.best == best, "a wall ends the game and keeps the best score")
    g.reset()
    c.check(not g.over and g.score == 0 and g.best == best, "a new game starts clean")
    g = snake.Snake(10, 6)
    g.body = [(5, 2), (4, 2), (4, 3), (5, 3), (6, 3), (6, 2)]
    g.heading = (0, 1)
    g.step()
    c.check(g.over, "biting itself ends the game")
    _fill_disc(c)
    c.check(shared_random.getstate() == before, "the games leave the shared random generator alone")
    c.check(snake.parse_posix("\x1b[Ag\x1bOB") == ["up", "g", "down"], "arrow keys from a POSIX terminal")

    saved = {k: os.environ.get(k) for k in ("COLUMNS", "LINES")}
    os.environ.update(COLUMNS="80", LINES="24")
    try:
        s = FakeTty()
        keys = Keys(["x"], ["g"], ["d"], [], ["q"], ["g"])
        p = ui.Progress(lambda: (0.5, "rung 3/22", None), ui.Term(s, env={"TERM": "xterm"}, platform="linux"), keys=keys)
        p.play()
        c.check(not p.playing, "no game until g is pressed")
        p.play()
        c.check(p.playing and "best 0" in s.getvalue(), "g opens the game below the progress line")
        p.last_step = 0.0
        p.play()
        c.check(p.game.heading == (1, 0) and p.game.body[0][0] == 4, "the game steps during a pause")
        p.log("a measured line")
        text = s.getvalue()
        c.check("a measured line\n" in text and text.rindex("a measured line") < text.rindex("best 0"),
                "a log line prints above the game, and the game is redrawn under it")
        p.play()
        p.play()
        c.check(not p.playing, "q closes the game")
        p.play()
        c.check(p.playing, "g opens it again")
        p.close()
        tail = s.getvalue()
        c.check(keys.closed and tail.endswith("\x1b[?25h") or tail.rstrip().endswith("\x1b[?25h"), "closing restores keys and cursor")
        s = FakeTty()
        keys = Keys(["g"], [])
        p = ui.Progress(lambda: (0.5, "rung 3/22", None), ui.Term(s, env={"TERM": "xterm"}, platform="linux"), keys=keys)
        p.play()
        os.environ.update(COLUMNS="44")
        p.play()
        c.check(p.playing and p.game.cols == 20, "a resized window redraws the game to fit")
        os.environ.update(COLUMNS="20")
        keys.polls = [[]]
        p.play()
        c.check(not p.playing and "too small" in s.getvalue(), "a window too small after resizing closes the game")
        p.close()
        os.environ.update(COLUMNS="80")
        s = FakeTty()
        p = ui.Progress(lambda: (0.5, "rung 3/22", None), ui.Term(s, env={"TERM": "xterm", "NO_COLOR": "1"}, platform="linux"), keys=Keys(["g"]))
        p.play()
        c.check(p.playing and "##" in s.getvalue() and not re.search(r"\x1b\[[0-9;]*m", s.getvalue()), "NO_COLOR: the game is drawn with glyphs")
        p.close()
        os.environ.update(LINES="6")
        s = FakeTty()
        p = ui.Progress(lambda: (0.5, "rung 3/22", None), ui.Term(s, env={"TERM": "xterm"}, platform="linux"), keys=Keys(["g"]))
        p.play()
        c.check(not p.playing and "too small" in s.getvalue(), "a low window says so instead of drawing over text")
        p.close()
        os.environ.update(LINES="24")
        s = FakeTty()
        keys = Keys(["g"], ["n"], ["up"], ["n"], ["n"])
        p = ui.Progress(lambda: (0.5, "rung 3/22", None), ui.Term(s, env={"TERM": "xterm"}, platform="linux"), keys=keys)
        p.play()
        snake_game = p.game
        snake_game.best = 7
        p.play()
        c.check(p.playing and isinstance(p.game, filldisc.FillDisc) and "Fill the Disc 0" in s.getvalue(), "n changes to the other game")
        y = p.game.y
        before = s.getvalue()
        p.play()
        c.check(p.game.y == y - 1 and len(s.getvalue()) > len(before), "a key moves the block at once, not at the next step")
        filled = p.game
        filled.best = 3
        p.play()
        c.check(p.game is snake_game, "n changes back, and each game keeps its board")
        p.play()
        c.check(p.game is filled, "and again")
        p.close()
        c.check("Snake: best score 7" in s.getvalue() and "Fill the Disc: best score 3" in s.getvalue(), "both best scores are printed at the end, for the log")
        s = FakeTty()
        p = ui.Progress(lambda: (0.5, "rung 3/22", None), ui.Term(s, env={"TERM": "xterm", "NO_COLOR": "1"}, platform="linux"), keys=Keys(["g"], ["n"]))
        p.play()
        p.play()
        c.check(ui.GAME_GLYPHS[p.game.kind] in s.getvalue() and not re.search(r"\x1b\[[0-9;]*m", s.getvalue()), "NO_COLOR: Fill the Disc is drawn with glyphs")
        p.close()
        os.environ.update(COLUMNS="30")
        s = FakeTty()
        p = ui.Progress(lambda: (0.5, "rung 3/22", None), ui.Term(s, env={"TERM": "xterm"}, platform="linux"), keys=Keys(["g"]))
        p.play()
        c.check(p.playing and "closes" not in s.getvalue() and "Snake 0" in s.getvalue(), "a narrow window cuts the hint and never wraps it")
        p.close()
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _chinese(c) -> None:
    from . import __main__ as cli, zh
    yes, no = (lambda: True), (lambda: False)
    term_env = {"TERM": "xterm"}
    for flag, tty, env, encodable, system, wanted, name in (
            ("zh", False, {}, True, no, "zh", "--lang zh works in a pipe"),
            ("en", True, {"DISCPROBE_LANG": "zh"}, True, yes, "en", "--lang en beats everything"),
            (None, False, {"DISCPROBE_LANG": "zh"}, True, yes, "en", "a pipe ignores DISCPROBE_LANG and the system"),
            (None, True, {"DISCPROBE_LANG": "zh"}, True, no, "zh", "DISCPROBE_LANG=zh at a terminal"),
            (None, True, {"DISCPROBE_LANG": "en"}, True, yes, "en", "DISCPROBE_LANG=en at a terminal"),
            (None, True, term_env, True, yes, "zh", "a Chinese system gets Chinese"),
            (None, True, term_env, True, no, "en", "other systems get English"),
            (None, True, term_env, False, yes, "en", "a code page without Chinese gets English"),
            (None, True, {"TERM": "linux"}, True, yes, "en", "the Linux console has no Chinese font")):
        c.check(i18n.decide(flag, tty, env, encodable, system) == wanted, name)
    for env, wanted in (({"LANG": "zh_CN.UTF-8"}, True), ({"LANG": "zh_TW.UTF-8"}, True), ({"LANG": "en_US.UTF-8"}, False),
                        ({"LANG": "C"}, False), ({"LC_ALL": "en_GB.UTF-8", "LANG": "zh_CN.UTF-8"}, False)):
        c.check(i18n.system_is_chinese(env, "linux") == wanted, f"system language from {env}")
    c.check(i18n.take_flag(["timing", "--lang", "zh", "--sim", "cav"]) == ("zh", ["timing", "--sim", "cav"]), "--lang can sit anywhere")
    c.check(i18n.take_flag(["--lang=EN", "list"]) == ("en", ["list"]) and i18n.take_flag(["list"]) == (None, ["list"]), "--lang=en, and none")
    try:
        i18n.take_flag(["--lang", "fr"])
        c.check(False, "an unknown language is refused")
    except ValueError as e:
        c.check("zh or en" in str(e), "an unknown language is refused")

    placeholder = re.compile(r"\{(\w+)\}")
    bad = [k for k, v in zh.TEXT.items() if not set(placeholder.findall(v)) <= set(placeholder.findall(k))]
    c.check(not bad, f"every Chinese placeholder exists in its English key {bad[:2]}")
    loose = [k for k in zh.TEXT if "{" in k and len(placeholder.sub("", k).strip()) < 3]
    c.check(not loose, f"no key is so loose that it matches anything {loose[:2]}")
    c.check(i18n.tr("Rotation: CAV") == "Rotation: CAV", "English: lookups do nothing")
    c.check(sys.stdout.__class__.__name__ != "_Lines", "English: the output streams are untouched")
    i18n.use("zh")
    try:
        c.check(i18n.tr("Rotation: CAV") == "转速方式：恒定转速 (CAV)", "values are looked up again")
        c.check(i18n.tr("  rung  3: LBA   123456 (+1.0 turns) phase   12.345 +/- 0.123 deg").startswith("  测量点  3："), "indents and padding survive")
        c.check(i18n.tr("something new on /some/path") == "something new on /some/path", "a line with no entry stays English")
        for words in ("python -m discprobe geo --drive E:", "C:\\results\\geo-E-20260101-100000", "12.5 %"):
            c.check(i18n.tr(words) == words, f"left alone: {words}")
        stream = io.StringIO()
        lines = i18n._Lines(stream)
        lines.write("Next:")
        lines.write("\nRotation: C")
        lines.write("LV\npartial")
        lines.flush()
        c.check(stream.getvalue() == "下一步：\n转速方式：恒定线速度 (CLV)\npartial", "lines are translated whole, however they were written")
        c.check(all(i18n.display_width(x) <= 20 for x in i18n.wrap("每次计时读之前随机等待 0 到 N 毫秒，避免 repeated reads 都跨过相同圈数", 20)), "Chinese help wraps by columns")
        c.check(i18n.display_width("光盘a") == 5 and i18n.display_width(i18n.fit("光盘光盘光盘", 7)) <= 7, "width and cutting count columns")

        p, sub, _ = cli._build_parser()
        untranslated = [a.help for parser in [p, *sub.choices.values()] for a in parser._actions
                        if a.help and a.help != "==SUPPRESS==" and not re.search("[\u4e00-\u9fff]", a.help)]
        c.check(not untranslated, f"every option's help has Chinese (add it to zh.py): {untranslated[:2]}")
        c.check(all(re.search("[\u4e00-\u9fff]", x.description or "") for x in sub.choices.values()), "every command's description has Chinese")
    finally:
        i18n.use("en")
    command = re.compile(r"python -m discprobe [^`\n]*?(?=  |`|$)", re.M)
    pairs = [("workflow", cli.WORKFLOW)] + list(cli.EXAMPLES.items())
    drifted = [name for name, english in pairs if name not in zh.BLOCKS
               or {x.strip() for x in command.findall(english)} != {x.strip() for x in command.findall(zh.BLOCKS[name])}]
    c.check(not drifted, f"Chinese help paragraphs show the same commands as the English {drifted}")

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def run(*argv, **env):
        full = {k: v for k, v in os.environ.items() if k not in ("DISCPROBE_LANG", "DISCPROBE_PLAIN")}
        full.update(env)
        done = subprocess.run([sys.executable, "-m", "discprobe", *argv], capture_output=True, cwd=root, env=full)
        return done.returncode, done.stdout.decode("utf-8", "replace") + done.stderr.decode("utf-8", "replace")

    with tempfile.TemporaryDirectory() as d:
        en_dir, zh_dir, env_dir = (os.path.join(d, x) for x in ("en", "zh", "env"))
        quick = ("--sim", "cav", "--reps", "4", "--period-reads", "20")
        code_en, text_en = run("timing", *quick, "--out", en_dir)
        code_zh, text_zh = run("timing", *quick, "--out", zh_dir, "--lang", "zh")
        code_env, text_env = run("timing", *quick, "--out", env_dir, DISCPROBE_LANG="zh", LANG="zh_CN.UTF-8")
        c.check(code_en == code_zh == code_env == 0, "timing runs in both languages")
        c.check("Rotation: CAV" in text_en and "恒定转速" not in text_en, "the default in a pipe is English")
        c.check("Rotation: CAV" in text_env and "恒定转速" not in text_env, "DISCPROBE_LANG does not reach a pipe")
        c.check("转速方式：恒定转速 (CAV)" in text_zh, "--lang zh translates measuring output")
        left = [x for x in text_zh.splitlines() if LONG_ENGLISH.search(x) and "python -m" not in x]
        c.check(not left, f"timing has no English sentence left in Chinese {left[:2]}")

        def summary(folder):
            with open(os.path.join(guide.scan(folder)[0].path, "summary.json"), encoding="utf-8") as f:
                data = json.load(f)
            data["args"].pop("out")
            return data
        c.check(summary(en_dir) == summary(zh_dir), "the language never reaches summary.json")
        for argv in (["-h"], ["timing", "-h"], ["guide"], ["results", "--out", zh_dir], ["image"], ["timming"], ["info", "--sim", "cav", "--out", zh_dir]):
            code, text = run(*argv, "--lang", "zh")
            left = [x for x in text.splitlines() if LONG_ENGLISH.search(x) and "python -m" not in x and "docs/" not in x]
            c.check(re.search("[\u4e00-\u9fff]", text) and not left, f"Chinese: {' '.join(argv)} {left[:2]}")
        no_motion = os.path.join(d, "still")
        code, text = run("timing", *quick, "--no-animation", "--out", no_motion)
        c.check(code == 0 and "no_animation" not in json.dumps(summary(no_motion)), "--no-animation never reaches summary.json")
        code, text = run("-h")
        c.check(code == 0 and "--lang" not in text and "Start here" in text, "piped help stays as it was")
        code, text = run("-h", DISCPROBE_PLAIN="1", DISCPROBE_LANG="zh", LANG="zh_CN.UTF-8")
        c.check("Start here" in text and "--lang" not in text, "DISCPROBE_PLAIN=1 stays English")


def _completion(c) -> None:
    import shutil
    from . import __main__ as cli, completion
    rows = completion.table(cli._build_parser)
    p, sub, _ = cli._build_parser()
    c.check(set(sub.choices) <= {e[0] for e in rows[""]} and "completion" in {e[0] for e in rows[""]}, "completion knows every command")
    missing = [f for name, parser in sub.choices.items() for a in parser._actions for f in a.option_strings
               if f not in {e[0] for e in rows[name]}]
    c.check(not missing, f"completion knows every option {missing[:3]}")
    speed = next(e for e in rows["timing"] if e[0] == "--speed")
    media = next(e for e in rows["timing"] if e[0] == "--media")
    cav = next(e for e in rows["timing"] if e[0] == "--cav")
    out_flag = next(e for e in rows["timing"] if e[0] == "--out")
    c.check(speed[1] == "v" and speed[3] == "kB/s or 4x" and media[2] == ("dvd", "cd") and cav[1] == "f" and out_flag[1] == "p", "options say what their value is")
    scripts = {shell: completion.script(shell, cli._build_parser) for shell in completion.SHELLS}
    c.check(all("--along-track-frames" in text for text in scripts.values()), "every script holds the options")
    c.check("discprobe.__main__" not in "".join(scripts.values()) and not any(
        re.search(r"(?m)^[^#'\n]*\bpython -m discprobe\b", text) for text in scripts.values()), "a script never starts Python")
    i18n.use("zh")
    try:
        chinese = completion.script("powershell", cli._build_parser)
    finally:
        i18n.use("en")
    c.check(chinese.isascii() and "\\u8bfb" in chinese, "the PowerShell script is ASCII whatever the language")
    code, text = _run_cli("completion", "nope")
    c.check(code == 2 and "powershell" in text, "an unknown shell shows the usage")
    code, text = _run_cli("completion", "bash", "--lang", "zh")
    c.check(code == 0 and "_discprobe_complete" in text and "\r" not in text, "bash script: LF line ends, --lang accepted")

    with tempfile.TemporaryDirectory() as d:
        if sys.platform == "win32" and shutil.which("powershell"):
            path = os.path.join(d, "c.ps1")
            with open(path, "w", encoding="ascii") as f:
                f.write(scripts["powershell"])
            checks = (("python -m discprobe timing --sp", "--speed"), ("python -m discprobe ti", "timing tiles tilescan"),
                      ("python -m discprobe timing --media ", "dvd cd"), ("python -m discprobe --lang zh geo --ref", "--ref-lba"),
                      ("python C:\\Windows\\win.in", "C:\\Windows\\win.ini"), ("python -m d", "discprobe"), ("python -m ", "discprobe"),
                      ("python -m discprobe xyz", "xyz"), ("python -m discprobe timing --xyz", "--xyz"), ("python -m discprobe timing --reps 1", "1"))
            probe = ". '" + path + "'\n" + "".join(
                f"(TabExpansion2 -inputScript '{line}' -cursorColumn {len(line)}).CompletionMatches.CompletionText -join ' '\n" for line, _ in checks)
            done = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", probe], capture_output=True, text=True)
            got = done.stdout.splitlines()
            c.check(len(got) == len(checks) and all(g == want for g, (_, want) in zip(got, checks)), f"PowerShell: Tab completes as intended {got}")
        elif sys.platform != "win32" and shutil.which("bash"):
            path = os.path.join(d, "c.bash")
            with open(path, "w", encoding="utf-8") as f:
                f.write(scripts["bash"])
            checks = (("python -m discprobe timing --sp", "--speed"), ("python -m discprobe ti", "timing tiles tilescan"),
                      ("python -m discprobe timing --media ''", "dvd cd"), ("python -m discprobe --lang zh geo --ref", "--ref-lba"),
                      ("python script.py ''", ""), ("python -m d", "discprobe"), ("python -", "-m"))
            probe = "source " + path + "\n" + "".join(
                f"COMP_WORDS=({line}); COMP_CWORD=$((${{#COMP_WORDS[@]}} - 1)); _discprobe_complete; echo \"${{COMPREPLY[*]}}\"\n" for line, _ in checks)
            done = subprocess.run(["bash", "--norc", "-c", probe], capture_output=True, text=True)
            got = done.stdout.split("\n")[:len(checks)]
            c.check(all(g == want for g, (_, want) in zip(got, checks)) and len(got) == len(checks), f"bash: Tab completes as intended {got}")


def _install(c) -> None:
    from . import __main__ as cli, completion
    with tempfile.TemporaryDirectory() as home:
        startup = os.path.join(home, "sub", "profile.ps1")
        lines = completion.install("powershell", cli._build_parser, home, [(startup, "RemoteSigned")])
        script = completion.script_path("powershell", home)
        with open(startup, encoding="utf-8") as f:
            text = f.read()
        c.check(os.path.exists(script) and completion.load_line("powershell") in text and completion.installed(home), "install writes the script and one startup line")
        c.check(any("press Tab" in x for x in lines) and any("does not have it yet" in x for x in lines), "install says this window needs a step, and how to try it")
        completion.install("powershell", cli._build_parser, home, [(startup, "RemoteSigned")])
        with open(startup, encoding="utf-8") as f:
            c.check(f.read() == text, "installing twice adds nothing")
        with open(startup, "wb") as f:
            f.write("# mine\n".encode("utf-16"))
        completion.add_to_startup(startup, "line")
        with open(startup, "rb") as f:
            c.check(f.read().decode("utf-16") == f"# mine\n{completion.MARKER}\nline\n", "a UTF-16 startup file stays UTF-16")
        with open(startup, "w", encoding="utf-8") as f:
            f.write(f"{completion.MARKER}\n")
        c.check(completion.add_to_startup(startup, "line"), "a marker with its line gone is not called installed")
        with open(startup, encoding="utf-8") as f:
            c.check(f.read() == f"{completion.MARKER}\nline\n", "the line comes back without a second marker")
        with open(startup, "wb") as f:
            f.write(b"# \xd6\xd0\xce\xc4 keep\n")
        completion.add_to_startup(startup, completion.load_line("powershell"))
        completion.uninstall("powershell", home, [(startup, "")])
        with open(startup, "rb") as f:
            c.check(f.read() == b"# \xd6\xd0\xce\xc4 keep\n", "uninstall restores other people's bytes exactly")
        c.check(not os.path.exists(script) and not completion.installed(home), "uninstall deletes the script")
        c.check(completion.uninstall("powershell", home, [(startup, "")]) == ["Tab completion was not installed."], "uninstalling twice is harmless")
        untouched = os.path.join(home, "other.ps1")
        lines = completion.install("powershell", cli._build_parser, home, [(untouched, "Restricted")])
        c.check(not os.path.exists(untouched) and any("Set-ExecutionPolicy" in x for x in lines), "a blocking policy is reported, never changed")
    for env, platform, wanted in (({}, "win32", "powershell"), ({"MSYSTEM": "MINGW64", "SHELL": "/usr/bin/bash"}, "win32", "bash"),
                                  ({"SHELL": "/bin/zsh"}, "darwin", "zsh"), ({"SHELL": "/usr/bin/fish"}, "linux", None)):
        c.check(completion.default_shell(env, platform) == wanted, f"default shell for {platform} {env}: {wanted}")


def _writing(c) -> None:
    real_term = ui._term
    try:
        ui._term = ui.Term(io.StringIO(), env={})
        with ui.writing("x", 10) as log:
            c.check(log is print, "a pipe gets the writers' lines as before")
        with ui.busy("x"):
            pass
        c.check(ui._term.stream.getvalue() == "", "a pipe sees nothing of the busy line")
        s = FakeTty()
        ui._term = ui.Term(s, env={"TERM": "xterm"}, platform="linux")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.iso")
            with open(path, "wb") as f:
                f.write(bytes(512 * 2048))
            with contextlib.redirect_stdout(io.StringIO()) as printed, ui.writing(path, 1024) as log:
                ui.time.sleep(0.3)
                halfway = ANSI.sub("", s.getvalue())
                c.check(" 50%" in halfway, "between reports the bar follows the file's size")
                log("  20.0 %")
                log("a note")
                with open(path, "wb") as f:
                    f.write(bytes(2048 * 1024))
                ui.time.sleep(0.3)
                c.check(" 99%" in ANSI.sub("", s.getvalue()) and "100%" not in ANSI.sub("", s.getvalue()), "only a report can say 100%")
                log("  100.0 %")
                ui.time.sleep(0.3)
            text = ANSI.sub("", s.getvalue())
            c.check("100%" in text and "a note\n" in text and "20.0 %" not in text and "Finished in" in printed.getvalue(), "percentage lines become the bar; other lines still print")
            c.check("\x1b[?25h" in s.getvalue(), "the cursor comes back")
        try:
            with ui.writing("no such file", 10):
                raise ValueError("stop")
        except ValueError:
            c.check(s.getvalue().count("\x1b[?25l") == s.getvalue().count("\x1b[?25h"), "an error mid-write still restores the cursor")
    finally:
        ui._term = real_term


def _run_cli(*argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    done = subprocess.run([sys.executable, "-m", "discprobe", *argv], capture_output=True, cwd=root)
    return done.returncode, done.stdout.decode("utf-8", "replace") + done.stderr.decode("utf-8", "replace")


def _reader_changes_nothing(c) -> None:
    def run(wrap, keys=None):
        sim = SimDrive(mode="cav", seed=7)
        dev = sim
        if wrap:
            dev = ui.ProgressDevice(sim)
        probe = timing.TimingProbe(dev, log=lambda *_: None, reps=8, period_reads=20)
        if wrap:
            dev.progress = ui.Progress(ui.timing_status(probe, dev), ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux"), keys=keys)
        s = probe.run()
        if wrap:
            dev.progress.close()
        return s, probe.events_as_rows()
    from argparse import Namespace
    skipped = Namespace(_experiment="period", period_reads=10, reps=4, targets=[1, 2])
    pauses = Namespace(pauses=100)
    status = ui.timing_status(skipped, pauses)
    skipped._experiment = "phase"
    c.check(abs(status()[0] - 30 / 46) < 1e-9, "a rotation test the progress line never saw is counted as done, not a crash")
    plain, wrapped = run(False), run(True)
    c.check(plain == wrapped, "the progress wrapper leaves summary and events identical (same seed)")
    saved = {k: os.environ.get(k) for k in ("COLUMNS", "LINES")}
    os.environ.update(COLUMNS="80", LINES="24")
    try:
        playing = run(True, Keys(["g"], ["w"], [], ["a"], [], ["s"], ["d"], ["r"], ["n"], ["w"], [], ["a"], ["d"], ["s"], ["r"]))
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    c.check(plain == playing, "playing both games leaves summary and events identical (same seed)")

    class NoIdle:
        """A real drive has no idle(): the wrapper must sleep the pause itself, minus drawing."""
        name = "X:"
        slept: list[float] = []

    dev = ui.ProgressDevice(NoIdle())
    real_sleep = ui.time.sleep
    ui.time.sleep = NoIdle.slept.append
    try:
        dev.idle(0.02)
    finally:
        ui.time.sleep = real_sleep
    c.check(len(NoIdle.slept) == 1 and 0 < NoIdle.slept[0] <= 0.02 and dev.pauses == 1, "a real drive still waits out the pause")


def _status_counts(c) -> None:
    dev = ui.ProgressDevice(SimDrive(mode="cav", seed=7))
    probe = timing.TimingProbe(dev, log=lambda *_: None, reps=8, period_reads=20)
    seen = []
    dev.progress = ui.Progress(lambda: seen.append(status()) or (None, "", None), ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux"))
    dev.progress.interval = 0.0
    status = ui.timing_status(probe, dev)
    probe.run()
    dev.progress.close()
    fractions = [f for f, _, _ in seen if f is not None]
    labels = {label.split(",")[0] for _, label, _ in seen}
    c.check(fractions == sorted(fractions) and 0.9 < fractions[-1] <= 1.0, f"timing progress rises to the end ({fractions[-1]:.3f})")
    c.check({"rotation test", "phase test"} <= labels, "timing progress names its stages")


def _results(c) -> None:
    from .__main__ import main
    with tempfile.TemporaryDirectory() as d:
        def geo(name, rungs, chi2=1.0, media=None):
            folder = os.path.join(d, name)
            os.makedirs(folder)
            fit = {"u": 180000.0, "v": 5.5, "bit_nm_assumed": 133.3, "chi2_per_dof": chi2, "residual_rms_deg": 0.1,
                   "measured_span_mm": [26.0, 54.0]}
            if media:
                fit["media"] = media
            with open(os.path.join(folder, "summary.json"), "w", encoding="utf-8") as f:
                json.dump({"fit": fit, "setup": {"last_lba": 2295103}}, f)
            with open(os.path.join(folder, "targets.csv"), "w", encoding="utf-8") as f:
                f.write("header\n" + "row\n" * rungs)
            return folder
        good = geo("geo-H-20260101-100000", 22)
        cd_run = geo("geo-H-20260101-110000", 36, media="cd")
        geo("geo-H-20260101-120000", 3)                     # stopped early
        geo("geo-H-20260101-130000", 20, chi2=300.0)        # stopped by the whole-turn check
        geo("geo-SIM-cav-20260101-140000", 22)              # never burn from a simulation
        os.makedirs(os.path.join(d, "not a result"))
        c.check(guide.latest_geo("dvd", d).path == good, "latest skips stopped, simulated and other-media runs")
        c.check(guide.latest_geo("cd", d).path == cd_run, "latest honours the media")
        c.check(guide.resolve_geo("latest", "dvd", d) == os.path.join(good, "summary.json"), "--geo latest")
        c.check(guide.resolve_geo(good) == os.path.join(good, "summary.json"), "--geo accepts a result folder")
        c.check(guide.resolve_geo("x/summary.json") == "x/summary.json", "--geo keeps a file path as it is")
        empty = os.path.join(d, "none")
        try:
            guide.resolve_geo("latest", None, empty)
            c.check(False, "--geo latest with no results is refused")
        except ValueError as e:
            c.check("no geo result yet" in str(e), "--geo latest with no results is refused")
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            main(["results", "geo", "--latest", "--out", d])
        c.check(printed.getvalue().strip() == cd_run, "results --latest prints the newest complete real folder")
    report = {"track_1": {"parsed": {"blank": True, "track_start": 0, "free_blocks": 2298496}},
              "atip": {"parsed": {"last_leadout_start_lba": 359849}}, "capacity": {"parsed": {"last_lba": 100}}}
    c.check(guide.sectors_from_info(report)[0] == 2298496, "--sectors from a blank DVD's free space")
    del report["track_1"]
    c.check(guide.sectors_from_info(report)[0] == 359849, "--sectors from a CD's ATIP")
    c.check("closer count" in guide.sectors_from_info(report)[1], "the ATIP count says a blank disc gives a closer one")
    del report["atip"]
    c.check(guide.sectors_from_info(report)[0] == 101, "--sectors from the last LBA")
    c.check(guide.sectors_from_info({}) is None, "--sectors unknown says nothing")


def _advice(c) -> None:
    from argparse import Namespace
    from . import __main__ as cli
    parsers = cli._build_parser()[1].choices
    args = Namespace(drive="H:", sim=None, media="dvd", speed=None, sectors=1, transport="auto", out="results")
    def timed(mode, jitter):
        return {"period": {"rotation": {"mode": mode}, "zones": [{"jitter_deg": j} for j in jitter]}}
    good = "\n".join(guide.after_timing(args, timed("CAV", [0.4, 0.6])))
    c.check("usable" in good and f"{guide.PROG} geo --drive H:" in good, "a good drive is sent on to geo")
    clv = "\n".join(guide.after_timing(args, timed("CLV", [0.4])))
    c.check("not CAV" in clv and "--speed" in clv and " geo " not in clv, "a CLV drive is sent back with another speed")
    noisy = "\n".join(guide.after_timing(args, timed("CAV", [9.0])))
    c.check("too high" in noisy, "very high jitter is called out")
    cd_args = Namespace(**{**vars(args), "media": "cd", "speed": 1411})
    c.check("--media cd" in guide.after_timing(cd_args, timed("CAV", [0.4]))[-1], "next commands keep --media cd")
    c.check("--speed 1411" not in guide.after_timing(cd_args, timed("CAV", [0.4]))[-1], "next commands leave out the default speed")
    fit = {"chi2_per_dof": 5.2, "measured_span_mm": [25.8, 54.4], "residual_rms_deg": 0.9, "angle_sigma_measured_span_deg": 0.33}
    geo_args = Namespace(**{**vars(args), "speed": 5540})
    real_compare = guide.compare_pitch
    try:
        guide.compare_pitch = lambda out: (5.2, 5.6)
        noisy_fit = "\n".join(guide.after_geo(geo_args, fit, os.path.join("results", "geo-H-20260101-100000")))
        c.check("does not fit better" in noisy_fit and "--speed 3324" in noisy_fit and "--correction" not in noisy_fit,
                "no gain from a varying pitch: geo says carry on, no correction")
        guide.compare_pitch = lambda out: (20.0, 1.5)
        pitch_fit = guide.after_geo(geo_args, fit, os.path.join("results", "geo-H-20260101-100000"))
        c.check(any("--write-correction" in x for x in pitch_fit) and all("--correction correction.json" in x for x in pitch_fit if f"{guide.PROG} image" in x or f"{guide.PROG} disexport" in x),
                "a clear gain: geo writes the correction into the next commands")
        guide.compare_pitch = lambda out: None
        c.check(any("geo_polyfit" in x for x in guide.after_geo(geo_args, fit, "x")), "no comparison possible: geo says how to run it")
    finally:
        guide.compare_pitch = real_compare
    c.check(guide.compare_pitch("no such folder") is None, "a comparison that cannot run is not an error")
    c.check("0.33 deg" in guide.geo_summary(fit, 22) and "22 points" in guide.geo_summary(fit, 22), "geo opens with a plain summary")
    clean = {**fit, "chi2_per_dof": 1.62, "angle_sigma_measured_span_deg": 0.152}
    verdict = guide.after_geo(geo_args, clean, os.path.join("results", "geo-H-20260101-100000"))
    c.check(verdict[0].startswith("Verdict: good") and "0.15 deg" in verdict[0] and "0.13 mm" in verdict[0], "a clean geo gets a verdict in plain terms")
    i18n.use("zh")
    try:
        c.check(i18n.tr(verdict[0]).startswith("结论"), "the verdict has Chinese")
    finally:
        i18n.use("en")
    real_compare = guide.compare_pitch
    try:
        for ratio, word in (((20.0, 1.5), "good once corrected"), ((5.2, 5.6), "usable, but noisy"), (None, "not settled")):
            guide.compare_pitch = lambda out, ratio=ratio: ratio
            c.check(word in guide.after_geo(geo_args, fit, os.path.join("results", "geo-H-20260101-100000"))[0], f"a noisy geo: {word}")
    finally:
        guide.compare_pitch = real_compare
    geo_out = os.path.join("results", "geo-H-20260101-100000")
    def verdict_on(sigma, chi2=1.0):
        return guide.after_geo(geo_args, {**fit, "chi2_per_dof": chi2, "angle_sigma_measured_span_deg": sigma}, geo_out)
    c.check(verdict_on(0.25)[0].startswith("Verdict: good"), "the limit itself is still good")
    noisy_run = verdict_on(0.4)
    c.check("usable, but noisy" in noisy_run[0] and "good" not in noisy_run[0] and "0.35 mm" in noisy_run[0]
            and any("--speed 3324" in x for x in noisy_run), "wide error bars with a clean fit are not called good, and geo says what to try")
    bad_run = verdict_on(3.0)
    c.check("too noisy" in bad_run[0] and "2.62 mm" in bad_run[0] and "another drive" in bad_run[1], "very wide error bars are called out")
    real_compare = guide.compare_pitch
    i18n.use("zh")
    try:
        c.check(all(i18n.tr(x) != x for x in (noisy_run[0], noisy_run[1], bad_run[0])), "the noisy verdicts have Chinese")
        try:
            guide.compare_pitch = lambda out: (30.0, 10.0)
            helps = verdict_on(2.0, 30.0)
            c.check("a correction helps" in helps[0] and "good" not in helps[0] and "1.15 deg" in helps[0] and i18n.tr(helps[0]) != helps[0]
                    and any("--write-correction" in x for x in helps) and any("--speed 3324" in x for x in helps),
                    "a correction that leaves wide error bars is not called good")
            guide.compare_pitch = lambda out: (5.0, 5.2)
            lost = verdict_on(2.0, 5.0)
            c.check("too noisy" in lost[0] and not any("You can carry on" in x for x in lost) and any(i18n.tr(x) != x and "does not fit better" in x for x in lost),
                    "read noise this large does not say carry on")
        finally:
            guide.compare_pitch = real_compare
    finally:
        i18n.use("en")
    measured = {"setup": {"last_lba": 359751}, "fit": {"media": "cd"}}
    c.check("how much was burned" in guide._sectors_for(measured, "no such folder")[1], "--sectors from the measured disc says it may be less than a blank holds")
    def blank(profile, count):
        return {"configuration": {"parsed": {"current_profile": profile}}, "track_1": {"parsed": {"blank": True, "track_start": 0, "free_blocks": count}}}
    c.check("--sectors 699648" in guide._random_for_blank(blank(0x11, 713936))[1], "a miniDVD gets a random disc that fits, with room to close")
    usual_size = guide._random_for_blank(blank(0x11, 2295104))
    c.check("--sectors" not in usual_size[1] and "would not fit" not in usual_size[0], "a 2295104-sector DVD keeps the usual size, which has burned many times")
    c.check("--sectors" not in guide._random_for_blank(blank(0x11, 2298496))[1], "a 2298496-sector DVD keeps the usual size")
    full_cd = guide._random_for_blank(blank(0x09, 359847))[1]
    c.check("--sectors" not in full_cd and "--media cd" in full_cd, "a blank CD is told --media cd")
    i18n.use("zh")
    try:
        said = [guide.sectors_hint("no such file"), "Enter the same number in DiscImageStudio. A blank disc's `info` is the count to go by: one user found read-from-disc there too high."]
        c.check(all(i18n.tr(x) != x for x in said) and "`info`" in said[0], "the --sectors advice goes by `info` on a blank disc, in both languages")
    finally:
        i18n.use("en")
    helps = [a.help for name in ("timing", "geo", "random", "disexport") for a in parsers[name]._actions if "--sectors" in a.option_strings]
    c.check(len(helps) == 4 and all("not " in x for x in helps), "each --sectors help says what it is not")
    whole = Namespace(**{**vars(args), "sectors": 16})
    c.check(any("geo" in x and "--sectors 16" in x for x in guide.after_timing(whole, timed("CAV", [0.5]))), "timing with --sectors 16 carries it to the geo command")
    c.check("--media cd --sectors 326336" in guide._random_for_blank(blank(0x09, 333000))[1], "a 74-minute CD gets a random disc that fits")
    c.check("--media cd" in "".join(guide.after_info(Namespace(**vars(args)), blank(0x09, 359847))), "info on a blank CD offers the CD command")
    bd = {"setup": {"family": "bd"}, **timed("mixed", [0.4])}
    bd_lines = guide.after_timing(args, bd)
    c.check("constant linear speed" in bd_lines[1] and "8990" in bd_lines[2] and "3324" not in "".join(bd_lines), "on Blu-ray a non-CAV result does not promise another speed helps, and offers a BD speed")
    bd_good = guide.after_timing(args, {"setup": {"family": "bd"}, **timed("CAV", [9.0])})
    c.check(any("8990" in x for x in bd_good) and not any("--sectors 16" in x or " geo " in x for x in bd_good), "a noisy Blu-ray stays with BD speeds and is not sent on to geo")
    i18n.use("zh")
    try:
        c.check(all(i18n.tr(x) != x for x in (bd_lines[1], bd_good[-1], *guide.after_random(Namespace(**vars(args)))[:3], *guide.after_disexport(True))), "the new advice has Chinese")
    finally:
        i18n.use("en")
    c.check(len(guide.after_disexport(True)) == 3 and len(guide.after_disexport()) == 2, "a CD preset without the constant says the route settles it")
    cd_next = guide.after_geo(cd_args, clean, os.path.join("results", "geo-H-20260101-100000"))
    c.check(any("disexport" in x for x in cd_next[:6]) and "README.md" in "".join(cd_next) and
            next(i for i, x in enumerate(cd_next) if "disexport" in x) < next(i for i, x in enumerate(cd_next) if " image" in x),
            "a CD geo offers the preset before a picture ISO")
    with tempfile.TemporaryDirectory() as d:
        for name, profile, last in (("info-H-20260101-100000", 0x11, 2295103), ("info-H-20260102-100000", 0x09, 359847)):
            os.makedirs(os.path.join(d, name))
            with open(os.path.join(d, name, "info.json"), "w", encoding="utf-8") as f:
                json.dump({"configuration": {"parsed": {"current_profile": profile}}, "capacity": {"parsed": {"last_lba": last}}}, f)
        c.check(guide._sectors_for({"fit": {}}, d)[0] == "2295104" and guide._sectors_for({"fit": {"media": "cd"}}, d)[0] == "359848",
                "the --sectors suggestion comes from an `info` of the same kind of disc")
    stop = "\n".join(guide.after_geo_stop(args, "the spindle speed never settled; is the read speed fixed (--speed)?"))
    c.check("timing" in stop and "--speed" in stop, "a geo that never settled gets a next step")

    def retry_at(speed, media="dvd"):
        at = Namespace(**{**vars(args), "speed": speed, "media": media})
        lines = guide.after_geo_stop(at, "a whole-turn count went wrong") + guide.after_geo_stop(at, "the spindle speed never settled")
        return lines + guide.after_geo(at, {**fit, "chi2_per_dof": 1.0}, os.path.join("results", "geo-H-20260101-100000"))
    lowest, usual, cd = (retry_at(3324), retry_at(5540), retry_at(1411, "cd"))
    c.check(not any("lower speed" in x for x in lowest) and sum("a different speed" in x for x in lowest) == 3 and any("--speed 5540" in x for x in lowest),
            "already at the lowest speed: geo does not call the next one lower")
    c.check(any("--ranges" in x for x in lowest), "already at the lowest speed: geo still offers --ranges")
    c.check(sum("a lower speed" in x for x in usual) == 3 and any("--speed 3324" in x for x in usual), "with a lower speed to try, geo says lower")
    c.check(not any("lower speed" in x for x in cd) and any("--speed 2822" in x for x in cd), "CD at its default speed: the next one is not called lower")
    i18n.use("zh")
    try:
        said = [i18n.tr(x) for x in lowest + usual]
        c.check(not any(x.isascii() for x in said if "peed" in x and "--speed" not in x) and any("换一个速度" in x for x in said) and any("降速" in x for x in said),
                "the retry advice is in both languages")
    finally:
        i18n.use("en")
    hint = guide.parser_hint("argument <command>: invalid choice: 'timming' (choose from a)", ["timming"], ["timing", "geo"])
    c.check("timing" in (hint or ""), "a mistyped command gets a suggestion")
    hint = guide.parser_hint("the following arguments are required: --geo", ["image"], ["image"])
    c.check(hint == f"Use your last measurement: {guide.PROG} image --geo latest", "a missing --geo offers latest")
    c.check(all(line.isascii() for line in guide.guide_lines("dvd", "no such folder")), "guide text is ASCII")
    finished = guide.after_image("iso/p.iso", "iso/p.preview.png", os.path.join("results", "geo-H-20260101-100000", "summary.json"))
    c.check("preview" in finished[0] and any("burn" in x and "p.iso" in x for x in finished), "a finished picture says: check the preview, then burn")
    fake = guide.after_image("iso/p.iso", "iso/p.preview.png", os.path.join("results", "geo-SIM-cav-20260101-100000", "summary.json"))
    c.check(any("do not burn" in x for x in fake) and not any("If it looks right" in x for x in fake), "a picture from a simulated run must not be burned")
    sim_args = Namespace(**{**vars(args), "sim": "cav", "drive": None})
    c.check("simulated drive" in guide.after_timing(sim_args, timed("CAV", [0.4]))[0] and "simulated drive" in guide.after_timing(sim_args, timed("CLV", [0.4]))[0],
            "a verdict on the simulated drive says so")
    c.check(not any("simulated" in x for x in guide.after_timing(args, timed("CAV", [0.4]))), "a real drive's verdict does not")
    real_missing = guide.missing_packages
    try:
        guide.missing_packages = lambda: ["numpy", "scipy"]
        c.check("numpy, scipy" in guide.after_selftest()[0] and guide.INSTALL in guide.after_selftest()[1], "a self-test that skipped checks says so")
        guide.missing_packages = lambda: []
        c.check("guide" in guide.after_selftest()[0], "a complete self-test points to guide")
    finally:
        guide.missing_packages = real_missing
    with tempfile.TemporaryDirectory() as d:
        here = os.getcwd()
        os.chdir(d)
        try:
            os.makedirs("iso")
            with open(os.path.join("iso", "random.iso"), "wb"):
                pass
            piped, shown = guide.guide_lines("dvd"), guide.guide_lines("dvd", notes=True)
            c.check(any(x.startswith("  [x] Random-data disc") for x in piped), "a script keeps the tick it always saw")
            c.check(any(x.startswith("  [ ] Random-data disc") for x in shown), "at a terminal a written file is not yet a disc")
        finally:
            os.chdir(here)
    plain, noted = guide.guide_lines("dvd", "no such folder"), guide.guide_lines("dvd", "no such folder", notes=True)
    # The ticked row depends on the folder this runs in, and has its own check above.
    plain, noted = [x for x in plain if "Random-data disc" not in x], [x for x in noted if "Random-data disc" not in x]
    c.check(len(noted) == len(plain) + 1 and set(plain) < set(noted), "at a terminal the next command says what it does; a pipe gets the same lines as before")
    i18n.use("zh")
    try:
        untranslated = [x for x in set(noted) - set(plain) if i18n.tr(x) == x]
    finally:
        i18n.use("en")
    c.check(not untranslated, f"the note has Chinese {untranslated}")


def _command_line(c) -> None:
    import shutil
    from . import __main__ as cli

    def code_and_stderr(*argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            try:
                cli.main(list(argv))
                return 0, ""
            except SystemExit as e:
                text = err.getvalue() + (e.code if isinstance(e.code, str) else "")
                return (e.code if isinstance(e.code, int) else 1), text
    real_term = ui._term
    ui._term = ui.Term(io.StringIO(), env={})   # what a script sees, also when the self-test runs at a terminal
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "r")
        code, _ = code_and_stderr("timing", "--sim", "cav", "--speed", "4x", "--reps", "4", "--period-reads", "20", "--out", out)
        run = guide.scan(out)[0]
        c.check(code == 0 and run.summary["args"]["speed"] == 5540, "--speed 4x is 5540 kB/s on DVD")
        code, text = code_and_stderr("geo", "--sim", "cav", "--speed", "fast")
        c.check(code == 2 and "not a speed" in text, "a bad --speed is an argument error")
        code, _ = code_and_stderr()
        c.check(code == 2, "no command in a pipe is still an argument error")
        if importlib.util.find_spec("numpy") is None or importlib.util.find_spec("scipy") is None:
            print("--geo and --ranges error checks skipped (need numpy and scipy)")
        else:
            code, _ = code_and_stderr("timing", "--sim", "cav", "--media", "cd", "--speed", "8x", "--reps", "4", "--period-reads", "20", "--out", out)
            speeds = sorted(r.summary["args"]["speed"] for r in guide.scan(out))
            c.check(code == 0 and speeds == [1411, 5540], "--speed 8x is 1411 kB/s on CD")
            for given, wanted, name in ((["--sp", "4x"], 706, "--sp 4x"), (["--speed=8x"], 1411, "--speed=8x"), ([], 1411, "no --speed")):
                shortened = os.path.join(d, "short")
                shutil.rmtree(shortened, ignore_errors=True)
                code, _ = code_and_stderr("timing", "--sim", "cav", "--media", "cd", *given, "--reps", "4", "--period-reads", "20", "--out", shortened)
                c.check(code == 0 and guide.scan(shortened)[0].summary["args"]["speed"] == wanted, f"with --media cd: {name} gives {wanted} kB/s")
            code, text = code_and_stderr("geo", "--sim", "cav", "--ranges", "5-1")
            c.check(code == 1 and "start-end" in text, "a backwards --ranges says how to write it")
            code, text = code_and_stderr("image", "--geo", os.path.join(d, "missing.json"))
            c.check(code == 1 and "no such geo result" in text, "a missing --geo file is a plain error")
            geo_cd = os.path.join(d, "cd.json")
            with open(geo_cd, "w", encoding="utf-8") as f:
                json.dump({"fit": {"u": 150000.0, "v": 9.0, "bit_nm_assumed": 277.0, "media": "cd"}}, f)
            code, text = code_and_stderr("disexport", "--geo", geo_cd, "--media", "dvd", "--output", os.path.join(d, "p.json"))
            c.check(code == 1 and "does not match" in text, "disexport --media checks the fit")
            code, text = code_and_stderr("disexport", "--geo", geo_cd, "--output", os.path.join(d, "p.json"))
            c.check(code == 1 and "needs --sectors" in text, "a CD preset without --sectors is refused")
            geo_dvd = os.path.join(d, "dvd.json")
            with open(geo_dvd, "w", encoding="utf-8") as f:
                json.dump({"fit": {"u": 120000.0, "v": 3.0, "bit_nm_assumed": 133.3}}, f)
            code, text = code_and_stderr("disexport", "--geo", geo_dvd, "--output", os.path.join(d, "p.json"))
            c.check(code == 1 and "needs --sectors" in text and not os.path.exists(os.path.join(d, "p.json")),
                    "a DVD preset without --sectors is refused too, with no file written")
            not_geo = os.path.join(d, "t.json")
            with open(not_geo, "w", encoding="utf-8") as f:
                json.dump({"cache": {}}, f)
            code, text = code_and_stderr("disexport", "--geo", not_geo)
            c.check(code == 1 and "not the summary.json" in text, "a summary without a fit is a plain error")

    class Stopped:
        name = "SIM"

        def __init__(self):
            self.sim = SimDrive(mode="cav", seed=7)
            self.left = 50

        def execute(self, *a, **k):
            self.left -= 1
            if self.left <= 0:
                raise KeyboardInterrupt
            return self.sim.execute(*a, **k)

        def __getattr__(self, name):
            return getattr(self.sim, name)
    real_open = cli._open
    cli._open = lambda args: Stopped()
    try:
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "r")
            code, text = code_and_stderr("timing", "--sim", "cav", "--out", out)
            kept = os.path.exists(os.path.join(guide.scan(out)[0].path, "summary.json"))
            c.check(code == 130 and "Ctrl+C" in text and kept, "Ctrl+C says so and keeps the partial results")
    finally:
        cli._open = real_open
        cli._Parser.last_out = None
        ui._term = real_term


def _blu_ray(c) -> None:
    from argparse import Namespace
    from . import __main__ as cli
    from .scsi import ScsiResult

    class Disc:
        def __init__(self, profile):
            self.profile, self.commands = profile, 0

        def execute(self, cdb, data_len=0, direction=1, timeout_s=30):
            self.commands += 1
            return ScsiResult(0, bytes([0, 0, 0, 4, 0, 0, 0, self.profile]), None, 0, 1000)

    def run(profile, speed, sim=None):
        args = Namespace(speed=speed, sim=sim)
        disc = Disc(profile)
        with contextlib.redirect_stdout(io.StringIO()):
            cli._blu_ray_speed(disc, args)
        return args.speed, disc.commands
    eight = cli._SpeedKbs(11080)
    eight.multiple = 8.0
    c.check(run(0x41, eight)[0] == 35960, "8x on a Blu-ray disc is 35960 kB/s")
    c.check(run(0x11, eight)[0] == 11080, "8x on a DVD stays 11080 kB/s")
    c.check(run(0x41, 5540) == (5540, 0), "a speed in kB/s is left alone and asks the drive nothing")
    c.check(run(0x41, eight, sim="cav") == (eight, 0), "the simulated drive is not asked")
    c.check(json.loads(json.dumps({"speed": eight}))["speed"] == 11080, "the speed still saves as a plain number")


def _no_disc(c) -> None:
    from argparse import Namespace
    from . import __main__ as cli, info, mmc
    from .scsi import ScsiResult, Sense

    class Empty:
        """A drive that answers everything with the same Not Ready sense."""
        name = "SIM"

        def __init__(self, asc):
            self.sense = Sense(2, asc, 2 if asc == 0x3A else 1)

        def execute(self, cdb, data_len=0, direction=1, timeout_s=30):
            return ScsiResult(2, b"", self.sense, 0, 1000)

    c.check(mmc.not_ready(Sense(2, 0x3A, 2)) == mmc.NO_DISC and mmc.not_ready("2/3A/01") == mmc.NO_DISC, "sense 3A means no disc")
    c.check(mmc.not_ready(Sense(2, 0x04, 1)) == mmc.LOADING, "sense 04 means still loading")
    c.check(mmc.not_ready(None) is None and mmc.not_ready(Sense(2, 0x30, 0)) is None and mmc.not_ready(Sense(3, 0x3A, 0)) is None,
            "other answers are not taken for an empty tray")
    report = info.collect(Empty(0x3A))
    shown = info.summarize(report)
    c.check(mmc.NO_DISC in shown and not any("unknown" in x or "3A" in x for x in shown), "info says there is no disc, once")
    args = Namespace(drive="H:", sim=None, media="cd", speed=1411, transport="auto", out="results")
    c.check(guide.after_info(args, report) == [], "info does not send an empty drive off to burn a disc")
    c.check(guide.after_geo_stop(args, mmc.NO_DISC) == [] and guide.after_timing_stop(args, mmc.NO_DISC) == [], "no other advice on top of it")
    i18n.use("zh")
    try:
        c.check(i18n.tr(mmc.NO_DISC) != mmc.NO_DISC and i18n.tr(mmc.LOADING) != mmc.LOADING, "both messages have Chinese")
    finally:
        i18n.use("en")

    def run(*argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            try:
                cli.main(list(argv))
                code = 0
            except SystemExit as e:
                err.write(e.code if isinstance(e.code, str) else "")
                code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue() + err.getvalue()
    real_term, real_open = ui._term, cli._open
    ui._term = ui.Term(io.StringIO(), env={})   # what a script sees: the tester's pipe got the misleading text
    try:
        with tempfile.TemporaryDirectory() as d:
            cli._open = lambda args: Empty(0x3A)
            code, text = run("timing", "--sim", "cav", "--out", d)
            c.check(code == 1 and mmc.NO_DISC in text and "burn a test disc" not in text, "timing on an open tray says so")
            if importlib.util.find_spec("numpy") is None or importlib.util.find_spec("scipy") is None:
                print("CD and geo open-tray checks skipped (need numpy and scipy)")
            else:
                code, text = run("timing", "--sim", "cav", "--media", "cd", "--out", d)
                c.check(code == 1 and mmc.NO_DISC in text and "Mode 1" not in text, "timing --media cd on an open tray says so")
                for media in ("cd", "dvd"):
                    code, text = run("geo", "--sim", "cav", "--media", media, "--out", d)
                    c.check(mmc.NO_DISC in text and "how noisy" not in text, f"geo --media {media} on an open tray says so")
            cli._open = lambda args: Empty(0x04)
            code, text = run("timing", "--sim", "cav", "--out", d)
            c.check(code == 1 and mmc.LOADING in text, "timing while the disc is loading says to wait")
    finally:
        ui._term, cli._open = real_term, real_open
        cli._Parser.last_out = None


def _greetings(c) -> None:
    import datetime
    from . import __main__ as cli, greetings
    week = [entry for day in greetings.WEEK for entry in day]
    every = list(greetings.FIRST_TIME) + week
    c.check(len(greetings.WEEK) == 7 and all(len(day) == 5 for day in greetings.WEEK), "a line for every day and time of day")
    c.check(len({en for en, _ in every}) == len(every) and len({zh for _, zh in every}) == len(every), "no line is used twice")
    c.check(all(en.isascii() and re.search("[\u4e00-\u9fff]", zh) and i18n.display_width(zh) < 50 and len(en) < 60 for en, zh in every),
            "every greeting has both languages and fits a narrow window")
    claims = re.compile(r"steady|settled|ready to|\d+ ?rpm|\u7a33\u5b9a|\u5df2\u5c31\u7eea", re.I)
    c.check(not any(claims.search(en + zh) for en, zh in every), "no greeting reads like a measurement")
    monday = datetime.date(2026, 11, 2)     # a Monday

    def at(day, hour):
        return greetings.pick(now=datetime.datetime(monday.year, monday.month, monday.day + day, hour, 30))
    for hour, slot in ((0, 0), (4, 0), (5, 1), (8, 1), (9, 2), (11, 2), (12, 3), (17, 3), (18, 4), (21, 4), (22, 0), (23, 0)):
        c.check(at(0, hour) == greetings.WEEK[0][slot][0], f"{hour}:30 falls in the right part of the day")
    c.check(at(4, 19) == greetings.WEEK[4][4][0] and at(6, 10) == greetings.WEEK[6][2][0], "each day has its own lines")
    c.check(greetings.pick(True) in [en for en, _ in greetings.FIRST_TIME], "a first run is welcomed")
    i18n.use("zh")
    try:
        c.check(at(0, 10) == greetings.WEEK[0][2][1] and greetings.pick(True) in [zh for _, zh in greetings.FIRST_TIME], "the greeting follows the language")
    finally:
        i18n.use("en")
    real_term = ui._term
    try:
        ui._term = ui.Term(io.StringIO(), env={})
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            cli.cmd_guide(type("Args", (), {"guide_media": "dvd"})())
        c.check(not any(en in printed.getvalue() for en, _ in every), "a pipe gets no greeting")
    finally:
        ui._term = real_term


def _priority(c) -> None:
    """In a process of its own, so the rest of the self-test keeps its normal priority."""
    if sys.platform != "win32":
        return
    code = ("import ctypes; from ctypes import wintypes; from discprobe import spti; ok = spti.raise_priority(); "
            "k = spti._kernel32; k.GetPriorityClass.argtypes = [wintypes.HANDLE]; k.GetThreadPriority.argtypes = [wintypes.HANDLE]; "
            "print(ok, k.GetPriorityClass(spti._GetCurrentProcess()), k.GetThreadPriority(spti._GetCurrentThread()))")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=root)
    c.check(done.stdout.split() == ["True", "128", "2"], f"measuring really runs at high priority {done.stdout.split()}")


def _plain_errors(c) -> None:
    from . import __main__ as cli
    missing = FileNotFoundError(2, "No such file or directory", "nope.png")
    stopped = OSError(5, "The system cannot locate the file specified.")
    chinese = OSError(2, "\u7cfb\u7edf\u627e\u4e0d\u5230\u6307\u5b9a\u7684\u6587\u4ef6\u3002")
    real_term = ui._term
    try:
        ui._term = ui.Term(io.StringIO(), env={})
        c.check(cli._os_error(missing) == f"error: {missing}" and cli._reason(stopped) == stopped.strerror, "a script sees system errors as it always did")
        ui._term = ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux")
        c.check(cli._os_error(missing) == "no such file: nope.png", "at a terminal a missing file is said plainly")
        c.check(cli._os_error(stopped) == f"error: {stopped}", "other system errors keep their text")
        c.check(cli._reason(stopped) == "The system cannot locate the file specified" and not cli._reason(chinese).endswith("\u3002"), "no doubled full stop")
    finally:
        ui._term = real_term


def _missing_package(c) -> None:
    import subprocess
    import sys
    code = ("import sys; sys.modules['scipy'] = None; from discprobe.__main__ import main; "
            "main(['disexport', '--geo', sys.argv[1]])")
    with tempfile.TemporaryDirectory() as d:
        geo = os.path.join(d, "s.json")
        with open(geo, "w", encoding="utf-8") as f:
            json.dump({"fit": {"u": 180000.0, "v": 5.5, "bit_nm_assumed": 133.3}}, f)
        done = subprocess.run([sys.executable, "-c", code, geo], capture_output=True, text=True,
                              cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    c.check(done.returncode == 1 and "pip install" in done.stderr and "Traceback" not in done.stderr,
            "a missing package says what to install")


def _preflight(c) -> None:
    from argparse import Namespace
    from . import __main__ as cli
    from .scsi import ScsiResult, Sense

    class Drive:
        name = "X:"

        def __init__(self, profile=None, tray_empty=False):
            self.profile, self.tray_empty = profile, tray_empty

        def execute(self, cdb, data_len=0, direction=1, timeout_s=30):
            if cdb[0] == 0x00:      # TEST UNIT READY
                return ScsiResult(2, b"", Sense(2, 0x3A, 0), 0, 1) if self.tray_empty else ScsiResult(0, b"", None, 0, 1)
            data = bytes(6) + self.profile.to_bytes(2, "big") + bytes(4)
            return ScsiResult(0, data, None, 0, 1)

    args = Namespace(media="dvd", func=cli.cmd_geo, drive=None, sim=None)
    real_term, real_ask, real_drives, real_platform = ui._term, ui.ask, guide.optical_drives, cli.sys.platform
    ui._term = ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux")
    try:
        ui.ask = lambda *a, **k: True
        try:
            cli._check_disc(Drive(profile=0x09), args)
            c.check(False, "a CD with DVD settings offers --media cd")
        except cli._Rerun as again:
            c.check(again.extra == ["--media", "cd"], "a CD with DVD settings offers --media cd")
        ui.ask = lambda *a, **k: False
        cli._check_disc(Drive(profile=0x09), args)
        c.check(True, "declining keeps the command as typed")
        cli._check_disc(Drive(profile=0x11), args)
        c.check(True, "a DVD with DVD settings passes")
        try:
            cli._check_disc(Drive(tray_empty=True), args)
            c.check(False, "an empty tray is reported")
        except SystemExit as e:
            c.check(str(e.code) == cli.mmc.NO_DISC, "an empty tray is reported")
        cli.sys.platform = "win32"
        guide.optical_drives = lambda: ["H:"]
        with contextlib.redirect_stdout(io.StringIO()):
            cli._choose_drive(args)
        c.check(args.drive == "H:", "the only drive is used when --drive is left out")
        guide.optical_drives = lambda: []
        args.drive = None
        try:
            cli._choose_drive(args)
            c.check(False, "no drive at all is reported")
        except SystemExit as e:
            c.check("--sim" in str(e.code), "no drive at all is reported")
    finally:
        ui._term, ui.ask, guide.optical_drives, cli.sys.platform = real_term, real_ask, real_drives, real_platform


def _banner(c) -> None:
    from . import banner
    ansi = ANSI
    modes = {"true colour": ui.Term(FakeTty(), env={"TERM": "xterm", "COLORTERM": "truecolor"}, platform="linux"),
             "16 colours": ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux"),
             "NO_COLOR": ui.Term(FakeTty(), env={"TERM": "xterm", "NO_COLOR": "1"}, platform="linux"),
             "no ANSI": ui.Term(FakeTty(), env={}, platform="win32")}
    for name, t in modes.items():
        for columns in (120, 60, 20):
            rows = banner.frame(1.0, t, columns)
            plain = [ansi.sub("", r) for r in rows]
            c.check(all(p.isascii() for p in plain) and all(len(p) < columns for p in plain),
                    f"{name}, {columns} columns: ASCII and fits")
            c.check(("\x1b" in "".join(rows)) == t.color, f"{name}, {columns} columns: escapes only with colour")
    colour = "".join(banner.frame(1.0, modes["true colour"], 120))
    c.check("\x1b[48;2;" in colour and any(g in ansi.sub("", colour) for g in "/\\"), "the disc is coloured spaces with slashes on top")
    c.check("\x1b[4" in "".join(banner.frame(1.0, modes["16 colours"], 120)), "16 colours: the disc uses background colours")
    i18n.use("zh")
    try:
        for columns in (120, 60, 20):
            plain = [ansi.sub("", r) for r in banner.frame(1.0, modes["NO_COLOR"], columns)]
            c.check(all(i18n.display_width(p) < columns for p in plain), f"Chinese, {columns} columns: the screen fits")
    finally:
        i18n.use("en")
    saved = {k: os.environ.get(k) for k in ("COLUMNS", "LINES")}
    os.environ.update(COLUMNS="100", LINES="30")
    try:
        moved = modes["16 colours"]
        clock = [0.0]
        waits = []

        def wait(seconds):
            waits.append(seconds)
            clock[0] += seconds
        banner.show(moved, pause=wait, now=lambda: clock[0])
        text = moved.stream.getvalue()
        c.check(0 < len(waits) <= banner.SHOW_S / banner.FRAME_S + 1 and text.endswith("\x1b[?25h\n\n"), "the animation runs and gives the cursor back")
        clock[0], waits = 0.0, []

        def slow(seconds):
            waits.append(seconds)
            clock[0] += 0.5
        banner.show(ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux"), pause=slow, now=lambda: clock[0])
        c.check(len(waits) == 2, "a slow terminal skips frames and takes no longer")
        turning = modes["NO_COLOR"]
        waits = []
        banner.show(turning, pause=wait, now=lambda: clock[0])
        c.check(waits and not re.search(r"\x1b\[[0-9;]*m", turning.stream.getvalue()), "NO_COLOR: the disc still turns, without colour")
        still = ui.Term(FakeTty(), env={"TERM": "xterm", "NO_COLOR": "1", "DISCPROBE_NO_ANIMATION": "1"}, platform="linux")
        waits = []
        banner.show(still, pause=wait, now=lambda: clock[0])
        c.check(not waits and "\x1b" not in still.stream.getvalue(), "no colour, no motion: one still frame, no escapes")
        os.environ.update(LINES="8")
        low = ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux")
        waits = []
        banner.show(low, pause=wait, now=lambda: clock[0])
        c.check(not waits and "| |__" in low.stream.getvalue() and "\x1b[48" not in low.stream.getvalue(), "a low window gets the title alone")
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    pipe = ui.Term(io.StringIO(), env={"TERM": "xterm"}, platform="linux")
    banner.show(pipe)
    c.check(pipe.stream.getvalue() == "", "a pipe gets no banner")

    fine = ui.Term(Utf8Tty(), env={"TERM": "xterm", "WT_SESSION": "x"}, platform="linux")
    rows = banner.disc_rows(1.0, fine)
    c.check(len(rows) == banner.DISC_H and all(len(ansi.sub("", r)) == banner.DISC_W for r in rows), "half blocks: the disc keeps its size")
    c.check("▀" in rows[6] and "48;2;" in rows[6] and ansi.sub("", rows[0]).startswith(" "), "half blocks: two colours a cell, and round")
    c.check(banner._pixels(0.0)[banner.DISC_H * banner.DISC_W + banner.DISC_W // 2] is None, "half blocks: the hole shows through")
    c.check(banner.disc_rows(1.0, fine, 1.0) != rows, "steps done dye the track")
    c.check(banner.disc_cells(1.0, 0.401) == banner.disc_cells(1.0, 0.4), "and a small difference in steps is not a new disc")
    seen = {}
    first = banner._next_frame(1.0, fine, 120, seen, None, 0.0)
    again = banner._next_frame(1.0, fine, 120, seen, None, 0.0)
    moved = banner._next_frame(1.1, fine, 120, seen, None, 0.0)
    c.check(not again.replace("\n", "") and 0 < len(moved) < len(first) * 0.8, f"only changed cells go out ({len(first)}, then {len(moved)} bytes)")
    grid = [[" "] * 120 for _ in range(banner.DISC_H)]
    position = re.compile(r"\x1b\[(\d+)G([^\x1b]*)|\x1b\[[0-9;]*m([^\x1b]*)")
    painted = banner._next_frame(1.1, fine, 120, {}, None, 0.0).split("\n")
    whole = [ansi.sub("", r).rstrip() for r in banner.frame(1.1, fine, 120)]
    for y, row in enumerate(painted):
        column = 0
        for match in position.finditer(row):
            column = int(match[1]) - 1 if match[1] else column
            for ch in match[2] or match[3] or "":
                grid[y][column] = ch
                column += 1
    c.check(["".join(g).rstrip() for g in grid] == whole, "sent from nothing, the changes add up to the whole frame")
    os.environ.update(COLUMNS="100", LINES="30")
    try:
        clock = [0.0]

        def wait(seconds):
            clock[0] += seconds
        banner.show(fine, pause=wait, now=lambda: clock[0], burned=0.4)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    text = fine.stream.getvalue()
    c.check(text.count(ui.SYNC_START) == text.count(ui.SYNC_END) > 1 and text.endswith("\x1b[?25h\n\n"), "each frame is sent whole, and the cursor comes back")
    still = ui.Term(Utf8Tty(), env={"TERM": "xterm", "WT_SESSION": "x", "DISCPROBE_NO_ANIMATION": "1"}, platform="linux")
    banner.show(still, pause=wait, now=lambda: clock[0])
    c.check("▀" in still.stream.getvalue() and ui.SYNC_START not in still.stream.getvalue(), "no motion: one still frame of the same disc")


def run(c) -> None:
    print("terminal layer: capabilities, progress line, games, advice, opening screen, Chinese")
    _preflight(c)
    _banner(c)
    _term_matrix(c)
    _modern_terminal(c)
    _progress_line(c)
    _layout(c)
    _snake(c)
    _reader_changes_nothing(c)
    _status_counts(c)
    _results(c)
    _advice(c)
    _command_line(c)
    _missing_package(c)
    _plain_errors(c)
    _no_disc(c)
    _blu_ray(c)
    _priority(c)
    _greetings(c)
    _chinese(c)
    _completion(c)
    _install(c)
    _writing(c)
