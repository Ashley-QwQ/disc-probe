"""Terminal help for people typing commands: hints, colours and a progress line.

All of it is off unless stdout is a real terminal, so pipes, redirects and agents get the
plain output they always had (DISCPROBE_PLAIN=1 turns it off in a terminal too). Only 7-bit
ASCII is drawn, so no code page can break it; colour needs ANSI, and the progress line needs
nothing but a carriage return.
"""

from __future__ import annotations

import atexit
import os
import re
import shutil
import sys
import time

SPINNER = ("(|)", "(/)", "(-)", "(\\)")
STYLES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33", "cyan": "36"}
BAR_WIDTH = 24
ANIMATED_FPS = 8.0
PLAIN_FPS = 1.0
# Drawing outside the random pause delays the next command, so keep it rare there.
OUTSIDE_PAUSE_INTERVAL_S = 1.0


def _windows_ansi(stream) -> bool:
    """Turn on VT escape processing; False on consoles too old to have it."""
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        handle = msvcrt.get_osfhandle(stream.fileno())
        mode = wintypes.DWORD()
        if not k32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(k32.SetConsoleMode(handle, mode.value | 0x0004))
    except (OSError, ValueError, AttributeError, ImportError):
        return False


def _isatty(stream) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


class Term:
    """What this output stream can do. `interactive` gates every extra line we print."""

    def __init__(self, stream=None, env=None, platform=None):
        self.stream = stream if stream is not None else sys.stdout
        env = os.environ if env is None else env
        platform = platform or sys.platform
        self.interactive = _isatty(self.stream) and not env.get("DISCPROBE_PLAIN") and env.get("TERM") != "dumb"
        if not self.interactive:
            self.ansi = False
        elif platform == "win32":
            self.ansi = _windows_ansi(self.stream)
        else:
            self.ansi = bool(env.get("TERM"))
        self.color = self.ansi and not env.get("NO_COLOR")
        self.animate = self.color and not env.get("CI")
        self.truecolor = self.color and (env.get("COLORTERM", "") in ("truecolor", "24bit") or bool(env.get("WT_SESSION")))

    def style(self, text: str, name: str) -> str:
        return f"\x1b[{STYLES[name]}m{text}\x1b[0m" if self.color else text

    def can_prompt(self) -> bool:
        return self.interactive and _isatty(sys.stdin)


_term = None


def term() -> Term:
    global _term
    if _term is None:
        _term = Term()
    return _term


def clock(seconds: float) -> str:
    seconds = int(max(seconds, 0))
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}" if seconds >= 3600 \
        else f"{seconds // 60}:{seconds % 60:02d}"


def say(text: str = "", style: str | None = None) -> None:
    """A line only people at a terminal see."""
    t = term()
    if t.interactive:
        print(t.style(text, style) if style else text, flush=True)


def ask(question: str, default: bool = True) -> bool:
    """Yes or no at the terminal; the default wherever nobody can answer."""
    if not term().can_prompt():
        return default
    try:
        answer = input(f"{question} [{'Y/n' if default else 'y/N'}] ").strip().lower()
    except EOFError:
        return default
    return answer.startswith("y") if answer else default


class Progress:
    """One line that overwrites itself; `status` returns (fraction or None, label, seconds left or None)."""

    def __init__(self, status, t: Term | None = None):
        self.t = t or term()
        self.status = status
        self.started = time.monotonic()
        self.last_draw = 0.0
        self.width_shown = 0
        self.frame = 0
        self.interval = 1 / (ANIMATED_FPS if self.t.animate else PLAIN_FPS)
        self.closed = False
        if self.t.ansi:
            self.t.stream.write("\x1b[?25l")
            atexit.register(self.close)

    def _segments(self) -> list[tuple[str, str | None]]:
        fraction, label, left = self.status()
        seg: list[tuple[str, str | None]] = []
        if self.t.animate:
            self.frame += 1
            seg.append((SPINNER[self.frame % len(SPINNER)] + " ", "cyan"))
        if fraction is not None:
            fraction = max(0.0, min(1.0, fraction))
            filled = int(fraction * BAR_WIDTH)
            head = ">" if filled < BAR_WIDTH else ""
            seg += [("[", None), ("=" * filled + head, "cyan"), ("." * (BAR_WIDTH - filled - len(head)), "dim"),
                    (f"] {fraction * 100:3.0f}%  ", None)]
        seg.append((label, None))
        seg.append((f"  elapsed {clock(time.monotonic() - self.started)}", "dim"))
        if left is not None:
            seg.append((f"  about {clock(left)} left", None))
        return seg

    def _render(self) -> tuple[str, int]:
        room = max(10, shutil.get_terminal_size((80, 24)).columns - 1)  # never wrap: \r only reaches one row
        out, used = [], 0
        for text, style in self._segments():
            text = text[:room - used]
            used += len(text)
            out.append(self.t.style(text, style) if style and text else text)
        return "".join(out), used

    def tick(self, force: bool = False, interval: float | None = None) -> None:
        if self.closed:
            return
        now = time.monotonic()
        if not force and now - self.last_draw < (interval if interval is not None else self.interval):
            return
        self.last_draw = now
        line, width = self._render()
        self.t.stream.write("\r" + line + " " * max(0, self.width_shown - width))
        self.t.stream.flush()
        self.width_shown = width

    def _wipe(self) -> None:
        if self.width_shown:
            self.t.stream.write("\r" + " " * self.width_shown + "\r")
            self.width_shown = 0

    def log(self, *parts) -> None:
        """Print a line above the progress line."""
        self._wipe()
        print(*parts, file=self.t.stream, flush=True)
        self.tick(force=True)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._wipe()
        if self.t.ansi:
            self.t.stream.write("\x1b[?25h")
        self.t.stream.flush()


class ProgressDevice:
    """A drive wrapper that draws the progress line from the measuring thread, between reads.

    There is no animation thread on purpose. ctypes drops the GIL during the ioctl, and a thread
    holding it when the read returns delays the completion timestamp by up to the 5 ms switch
    interval, far above the tens of microseconds being measured. Drawing happens in the random
    pause before each timed read instead: that wait is arbitrary by design and the time spent
    drawing is taken off it. Outside it (setup, cache test) it draws at most once a second.
    """

    def __init__(self, dev):
        self._dev = dev
        self.progress: Progress | None = None
        self.pauses = 0     # one per timed read

    def __getattr__(self, name):
        return getattr(self._dev, name)

    def execute(self, *args, **kwargs):
        res = self._dev.execute(*args, **kwargs)
        if self.progress:
            self.progress.tick(interval=OUTSIDE_PAUSE_INTERVAL_S)
        return res

    def idle(self, seconds: float) -> None:
        start = time.perf_counter()
        self.pauses += 1
        if self.progress:
            self.progress.tick()
        if hasattr(self._dev, "idle"):      # the simulator's clock is virtual
            self._dev.idle(seconds)
            return
        rest = seconds - (time.perf_counter() - start)
        if rest > 0:
            time.sleep(rest)


class _Rate:
    """Seconds left from planned work, once enough of it has been timed."""

    MIN_DONE = 8

    def __init__(self):
        self.start = None
        self.done_at_start = 0.0

    def left(self, done: float, total: float) -> float | None:
        now = time.monotonic()
        if self.start is None:
            self.start, self.done_at_start = now, done
            return None
        finished = done - self.done_at_start
        return (now - self.start) / finished * (total - done) if finished >= self.MIN_DONE else None


def timing_status(probe, dev: ProgressDevice):
    """Progress of `timing`. Spin-up has no known length, so the bar counts the timed reads after it."""
    planned = 3 * probe.period_reads + 2 * probe.reps * len(probe.targets)
    names = {"": "starting", "setup": "reading the disc", "warmup": "warming up", "cache": "cache test",
             "settle": "waiting for a steady spindle"}
    marks: dict[str, int] = {}
    rate = _Rate()

    def status():
        stage = probe._experiment
        marks.setdefault(stage, dev.pauses)
        if stage not in ("period", "phase"):
            return None, names.get(stage, stage), None
        period_done = (marks["phase"] if "phase" in marks else dev.pauses) - marks["period"]
        phase_done = dev.pauses - marks["phase"] if "phase" in marks else 0
        done = period_done + phase_done
        if stage == "period":
            label = f"rotation test, zone {min(period_done // max(probe.period_reads, 1) + 1, 3)}/3"
        else:
            per_target = max(2 * probe.reps, 1)
            label = f"phase test, target {min(phase_done // per_target + 1, len(probe.targets))}/{len(probe.targets)}"
        return done / planned, label, rate.left(done, planned)
    return status


def geo_status(ladder, dev: ProgressDevice):
    """Progress of `geo`, in rungs of the ladder. A retried rung takes longer, so the time left is a guess."""
    per_rung = max(2 * ladder.reps, 1)
    rate = _Rate()
    state = {"rungs": -1, "mark": 0}

    def status():
        rungs = len(ladder.targets)
        if getattr(ladder, "T", None) is None:
            stage = "cache test" if not hasattr(ladder, "ref") else "waiting for a steady spindle"
            done = rungs / max(ladder.max_targets, 1)
            return (done if rungs else None), f"rung {rungs}/{ladder.max_targets}: {stage}" if rungs else stage, None
        if rungs != state["rungs"]:
            state.update(rungs=rungs, mark=dev.pauses)
        current = min((dev.pauses - state["mark"]) / per_rung, 1.0)
        done = (rungs + current) * per_rung
        total = ladder.max_targets * per_rung
        label = f"rung {min(rungs + 1, ladder.max_targets)}/{ladder.max_targets}"
        return done / total, label, rate.left(done, total)
    return status


def percent_log():
    """`log` for the ISO writers: their percentage lines, plus the time left at a terminal."""
    if not term().interactive:
        return print
    start = time.monotonic()

    def log(message):
        match = re.search(r"([\d.]+) %", message)
        spent = time.monotonic() - start
        if match and 0 < float(match.group(1)) < 100 and spent > 1:
            share = float(match.group(1)) / 100
            message += f"   about {clock(spent * (1 - share) / share)} left"
        print(message, flush=True)
    return log
