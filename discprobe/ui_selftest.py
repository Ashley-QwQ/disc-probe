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

from . import guide, i18n, snake, timing, ui
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
                c.check(i18n.tr("Ctrl+C to stop") in wide and i18n.tr("g: snake") in wide, f"{lang}: a wide line offers stop and snake")
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
    frame_bytes = len(ui.Progress(status, tty)._render(100)[0].encode())
    c.check(frame_bytes < 420, f"a true-colour frame stays small ({frame_bytes} bytes)")


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
    c.check(g.over and g.best == 1, "a wall ends the game and keeps the best score")
    g.reset()
    c.check(not g.over and g.score == 0 and g.best == 1, "a new game starts clean")
    g = snake.Snake(10, 6)
    g.body = [(5, 2), (4, 2), (4, 3), (5, 3), (6, 3), (6, 2)]
    g.heading = (0, 1)
    g.step()
    c.check(g.over, "biting itself ends the game")
    c.check(shared_random.getstate() == before, "the game leaves the shared random generator alone")
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
    plain, wrapped = run(False), run(True)
    c.check(plain == wrapped, "the progress wrapper leaves summary and events identical (same seed)")
    saved = {k: os.environ.get(k) for k in ("COLUMNS", "LINES")}
    os.environ.update(COLUMNS="80", LINES="24")
    try:
        playing = run(True, Keys(["g"], ["w"], [], ["a"], [], ["s"], ["d"], ["r"]))
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    c.check(plain == playing, "playing snake leaves summary and events identical (same seed)")

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
    del report["atip"]
    c.check(guide.sectors_from_info(report)[0] == 101, "--sectors from the last LBA")
    c.check(guide.sectors_from_info({}) is None, "--sectors unknown says nothing")


def _advice(c) -> None:
    from argparse import Namespace
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
    stop = "\n".join(guide.after_geo_stop(args, "the spindle speed never settled; is the read speed fixed (--speed)?"))
    c.check("timing" in stop and "--speed" in stop, "a geo that never settled gets a next step")
    hint = guide.parser_hint("argument <command>: invalid choice: 'timming' (choose from a)", ["timming"], ["timing", "geo"])
    c.check("timing" in (hint or ""), "a mistyped command gets a suggestion")
    hint = guide.parser_hint("the following arguments are required: --geo", ["image"], ["image"])
    c.check(hint == f"Use your last measurement: {guide.PROG} image --geo latest", "a missing --geo offers latest")
    c.check(all(line.isascii() for line in guide.guide_lines("dvd", "no such folder")), "guide text is ASCII")


def _command_line(c) -> None:
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
            c.check("no disc" in str(e.code), "an empty tray is reported")
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


def run(c) -> None:
    print("terminal layer: capabilities, progress line, snake, advice, opening screen, Chinese")
    _preflight(c)
    _banner(c)
    _term_matrix(c)
    _progress_line(c)
    _layout(c)
    _snake(c)
    _reader_changes_nothing(c)
    _status_counts(c)
    _results(c)
    _advice(c)
    _command_line(c)
    _missing_package(c)
    _chinese(c)
