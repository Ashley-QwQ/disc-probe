"""Self-test of the terminal layer: when it switches on, that it leaves measurements alone, and its advice."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile

from . import guide, timing, ui
from .sim import SimDrive


class FakeTty(io.StringIO):
    def isatty(self):
        return True

    def fileno(self):
        raise ValueError("not a real console")


def _term_matrix(c) -> None:
    pipe = ui.Term(io.StringIO(), env={"TERM": "xterm"}, platform="linux")
    c.check(not (pipe.interactive or pipe.ansi or pipe.color or pipe.animate), "a pipe gets nothing extra")
    tty = ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux")
    c.check(tty.interactive and tty.ansi and tty.color and tty.animate, "a terminal gets colour and animation")
    no_color = ui.Term(FakeTty(), env={"TERM": "xterm", "NO_COLOR": "1"}, platform="linux")
    c.check(no_color.interactive and not no_color.color and not no_color.animate, "NO_COLOR keeps hints, drops colour and animation")
    c.check(not ui.Term(FakeTty(), env={"TERM": "dumb"}, platform="linux").interactive, "TERM=dumb counts as a pipe")
    c.check(not ui.Term(FakeTty(), env={"TERM": "xterm", "DISCPROBE_PLAIN": "1"}, platform="linux").interactive,
            "DISCPROBE_PLAIN=1 counts as a pipe")
    old = ui.Term(FakeTty(), env={}, platform="win32")      # GetConsoleMode cannot work on this stream
    c.check(old.interactive and not old.ansi and not old.color and not old.animate, "a console without ANSI falls back to plain text")


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
        c.check("rung 6/22" in text and "0:40 left" in text and "a line\n" in text, f"{name}: progress line and log line")
        c.check(("\x1b[3" in text) == (wants_escape and wants_spinner) and any(f in text for f in ui.SPINNER) == wants_spinner,
                f"{name}: colour and spinner {'on' if wants_spinner else 'off'}")
        c.check(not wants_escape or text.endswith("\x1b[?25h"), f"{name}: the cursor comes back")
    s = FakeTty()
    p = ui.Progress(status, ui.Term(s, env={}, platform="win32"))
    p.tick(force=True)
    p.close()
    c.check("\x1b" not in s.getvalue() and "rung 6/22" in s.getvalue() and s.getvalue().isascii(),
            "no ANSI: plain ASCII with carriage returns only")


def _reader_changes_nothing(c) -> None:
    def run(wrap):
        sim = SimDrive(mode="cav", seed=7)
        dev = sim
        if wrap:
            dev = ui.ProgressDevice(sim)
        probe = timing.TimingProbe(dev, log=lambda *_: None, reps=8, period_reads=20)
        if wrap:
            dev.progress = ui.Progress(ui.timing_status(probe, dev), ui.Term(FakeTty(), env={"TERM": "xterm"}, platform="linux"))
        s = probe.run()
        if wrap:
            dev.progress.close()
        return s, probe.events_as_rows()
    plain, wrapped = run(False), run(True)
    c.check(plain == wrapped, "the progress wrapper leaves summary and events identical (same seed)")

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
    import re
    from . import banner
    ansi = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
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
    moved = modes["16 colours"]
    frames = []
    banner.show(moved, pause=frames.append)
    text = moved.stream.getvalue()
    if frames:   # a narrow console cannot fit the animation
        c.check(len(frames) == banner.FRAMES and text.endswith("\x1b[?25h\n\n"), "the animation runs and gives the cursor back")
    still = modes["NO_COLOR"]
    frames = []
    banner.show(still, pause=frames.append)
    c.check(not frames and "\x1b" not in still.stream.getvalue(), "NO_COLOR: one still frame, no escapes")
    pipe = ui.Term(io.StringIO(), env={"TERM": "xterm"}, platform="linux")
    banner.show(pipe)
    c.check(pipe.stream.getvalue() == "", "a pipe gets no banner")


def run(c) -> None:
    print("terminal layer: capabilities, progress line, advice, opening screen")
    _preflight(c)
    _banner(c)
    _term_matrix(c)
    _progress_line(c)
    _reader_changes_nothing(c)
    _status_counts(c)
    _results(c)
    _advice(c)
    _command_line(c)
    _missing_package(c)
