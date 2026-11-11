"""Terminal help for people typing commands: hints, colours and a progress line.

All of it is off unless stdout is a real terminal, so pipes, redirects and agents get the
plain output they always had (DISCPROBE_PLAIN=1 turns it off in a terminal too). 7-bit ASCII is
the default, because a UTF-8 encoding says nothing about the font; DISCPROBE_UNICODE=1 asks for
finer glyphs. Terminals that draw box and block characters themselves get those without asking.
Colour needs ANSI, and the progress line needs nothing but a carriage return. Animation is a
function of the clock, never of how often something was drawn, because reads come at an uneven
pace; each animated thing has a still form for --no-animation.
"""

from __future__ import annotations

import atexit
import collections
import contextlib
import functools
import math
import json
import uuid
import os
import re
import shutil
import sys
import threading
import time

from . import i18n, iso9660, snake
from .i18n import display_width, tr

SPINNER_ASCII = ("(|)", "(/)", "(-)", "(\\)")
SPINNER_UNICODE = ("◐", "◓", "◑", "◒")     # a disc turning
SPINNER_BLOCKS = ("▘", "▝", "▗", "▖")      # the same turn, in the range these terminals draw themselves
SPINNER_FRAME_S = 0.12
BAR_ASCII = ("=", ">", ".")
BAR_UNICODE = ("━", "╸", "─")
SPARK = "▁▂▃▄▅▆▇█"
SPARK_CELLS = 12
GLINT_EVERY_S = 4.0
GLINT_SWEEP_S = 1.2
GLINT_REACH = 2.0
TASKBAR_REFRESH_S = 5.0     # Ghostty drops a progress state it has not heard about for 15 s
SYNC_START, SYNC_END = "\x1b[?2026h", "\x1b[?2026l"
BURN_WARNING = "Careful: burning a DVD+R, DVD-R or CD-R cannot be undone; only RW discs can be erased. Check the image and the disc first."
WARNING_FLASHES = 4
WARNING_FLASH_S = 0.5       # one flash a second, slow enough to read and well under what can trouble people sensitive to flashing
STYLES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33", "cyan": "36", "flash": "1;36", "warning": "1;31"}
DVD_ACCENT_HUE = 0.9        # the middle of the DVD title's colours
PERCENT_FLASH_S = 0.4
BAR_WIDTH = 20
ANIMATED_FPS = 8.0
PLAIN_FPS = 1.0
# Drawing outside the random pause delays the next command, so keep it rare there.
OUTSIDE_PAUSE_INTERVAL_S = 1.0
SWEEP_S = 1.7
SWEEP_REACH = 4.0
BAR_COLOUR_CELLS = 4        # the bar's rainbow changes in steps, which keeps each frame small
# The measured lines, at a terminal, with every value in its own column. Rounding drops trailing
# zeros, so they come back at the precision it kept. Scripts never pass through here.
_COLUMNS = ((re.compile(r"Zone (\S+) \(LBA (\d+)\): T = (\S+) ms \((\S+) rpm\), jitter (\S+) us = (\S+) deg, coherence (\S+)"),
             "Zone {0:.2f} (LBA {1:7.0f}): T = {2:.5f} ms ({3:7.2f} rpm), jitter {4:6.2f} us = {5:6.3f} deg, coherence {6:.4f}"),
            (re.compile(r"Target (\S+) \(LBA (\d+)\): phase (\S+) deg \+/- (\S+) \(single-shot std (\S+), n=(\d+)\), ref jitter (\S+) deg"),
             "Target {0:.2f} (LBA {1:7.0f}): phase {2:7.3f} deg +/- {3:5.3f} (single-shot std {4:6.3f}, n={5:2.0f}), ref jitter {6:6.3f} deg"))


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
        original = mode.value
        if original & 0x0004:
            return True
        if not k32.SetConsoleMode(handle, original | 0x0004):
            return False

        def restore():      # the shell gets its console back as it was
            stream.flush()
            k32.SetConsoleMode(handle, original)
        atexit.register(restore)
        return True
    except (OSError, ValueError, AttributeError, ImportError):
        return False


def _isatty(stream) -> bool:
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


_media = "cd"


def use_media(media: str) -> str:
    """Which disc the commands and highlights are coloured for: a CD cyan, a DVD violet. Says what it was before."""
    global _media
    before, _media = _media, media
    return before


def _code(name: str, t: "Term") -> str:
    """A style's colour code. Plain magenta is too dark on some themes, so a DVD without true colour gets the bright one."""
    if _media == "dvd" and name in ("cyan", "flash"):
        bold = "1;" if name == "flash" else ""
        if t.truecolor:
            r, g, b = oklch(0.74, 0.15, DVD_ACCENT_HUE)
            return f"{bold}38;2;{r};{g};{b}"
        return f"{bold}95"
    return STYLES[name]


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
        self.animate = self.ansi and not env.get("CI") and not env.get("DISCPROBE_NO_ANIMATION")
        self.truecolor = self.color and (env.get("COLORTERM", "") in ("truecolor", "24bit") or bool(env.get("WT_SESSION")))
        # Few terminals say what is behind the text. Told it is dark, use bright green; otherwise
        # the theme's own green, which its author made readable on that theme.
        background = env.get("COLORFGBG", "").rpartition(";")[2]
        self.green = "92" if background.isdigit() and int(background) not in (7, 15) else "32"
        utf8 = (getattr(self.stream, "encoding", None) or "").lower().replace("-", "") == "utf8"
        self.unicode = self.ansi and utf8 and bool(env.get("DISCPROBE_UNICODE"))
        # These terminals say who they are and draw U+2500-259F themselves, whatever the font has.
        modern = bool(env.get("WT_SESSION")) or env.get("TERM_PROGRAM") in ("ghostty", "WezTerm", "claude-desktop") or env.get("TERM") == "xterm-kitty"
        self.blocks = self.unicode or (self.ansi and utf8 and modern)
        self.sync = self.ansi and modern
        self.taskbar = self.ansi and (modern or env.get("ConEmuANSI") == "ON")

    def style(self, text: str, name: str) -> str:
        return f"\x1b[{_code(name, self)}m{text}\x1b[0m" if self.color else text

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
        text = tr(text)
        print(t.style(text, style) if style else text, flush=True)


_event_lock = threading.Lock()


def event(event_type: str, **fields) -> None:
    """Optional JSONL outlet. The terminal path does no I/O when it is disabled."""
    path = os.environ.get("DISCPROBE_EVENTS")
    if path:
        record = dict(type=event_type, job=os.environ.get("DISCPROBE_JOB"), **fields)
        with _event_lock, open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")


def result_event(step: str, path: str, stopped=None) -> None:
    event("result", step=step, path=os.path.abspath(path),
          verdict="stopped_early" if stopped else "unknown", summary={})
    if stopped:
        event("stopped", reason=stopped)
    event("state")


def ask(question: str, default: bool = True, *, kind: str = "confirm") -> bool:
    """Yes or no at the terminal; the default wherever nobody can answer."""
    if os.environ.get("DISCPROBE_EVENTS"):
        ident = uuid.uuid4().hex
        event("ask", id=ident, question=tr(question), default=default, kind=kind)
        answer_path = os.environ.get("DISCPROBE_ANSWERS", os.environ["DISCPROBE_EVENTS"] + ".answers")
        deadline = time.monotonic() + float(os.environ.get("DISCPROBE_ASK_TIMEOUT", "30"))
        answer = default
        while time.monotonic() < deadline:
            try:
                with open(answer_path, encoding="utf-8") as stream:
                    for line in stream:
                        try:
                            reply = json.loads(line)
                        except ValueError:
                            continue
                        if reply.get("id") == ident and type(reply.get("yes")) is bool:
                            answer = reply["yes"]
                            event("answer", id=ident, yes=answer)
                            return answer
            except FileNotFoundError:
                pass
            time.sleep(0.05)
        event("answer", id=ident, yes=answer, timeout=True)
        return answer
    if not term().can_prompt():
        return default
    try:
        answer = input(f"{tr(question)} [{'Y/n' if default else 'y/N'}] ").strip().lower()
    except EOFError:
        return default
    return answer.startswith("y") if answer else default


def oklch(light: float, chroma: float, hue: float) -> tuple[int, int, int]:
    """OKLCH to sRGB bytes, `hue` in turns. Equal `light` looks equally bright, unlike HSV, whose blue is dim and yellow glares."""
    a, b = chroma * math.cos(math.tau * hue), chroma * math.sin(math.tau * hue)
    long = (light + 0.3963377774 * a + 0.2158037573 * b) ** 3
    mid = (light - 0.1055613458 * a - 0.0638541728 * b) ** 3
    short = (light - 0.0894841775 * a - 1.2914855480 * b) ** 3
    linear = (4.0767416621 * long - 3.3077115913 * mid + 0.2309699292 * short,
              -1.2684380046 * long + 2.6097574011 * mid - 0.3413193965 * short,
              -0.0041960863 * long - 0.7034186147 * mid + 1.7076147010 * short)
    return tuple(round(255 * min(1.0, 12.92 * v if v < 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055)) if v > 0 else 0 for v in linear)


@functools.lru_cache(maxsize=None)
def _tone(hue: int, level: int, lift: int) -> str:
    """Steps of hue, of colourfulness and of lift towards white, so a frame only looks colours up."""
    r, g, b = oklch(0.68 + 0.1 * lift, (0.05 + 0.025 * level) * (1 - 0.3 * lift), 0.08 + hue / 48)
    return f"38;2;{r};{g};{b}"


def iso_ready(path: str) -> None:
    """Where the image went, on a line of its own, since the line that first said so has scrolled away by now."""
    say("ISO ready! It is here:", "green")
    say(os.path.abspath(path))


def burn_warning(t: Term | None = None, pause=time.sleep) -> None:
    """After an image is ready to burn: flash, then leave the warning standing. Only people at a terminal see it.

    Drawn by the clock, as terminals differ on whether they blink. The flash is skipped by Ctrl+C or --no-animation.
    """
    event("log", text=tr(BURN_WARNING), level="warning")
    t = t or term()
    if not t.interactive:
        return
    text = tr(BURN_WARNING)
    if t.animate:
        lit, unlit = ("1;97;41", "1;31") if t.color else ("7", "1")
        shown = i18n.fit(text, shutil.get_terminal_size((80, 24)).columns - 1)
        t.stream.write("\x1b[?25l")
        try:
            for flash in range(WARNING_FLASHES * 2):
                t.stream.write(f"\r\x1b[{unlit if flash % 2 else lit}m{shown}\x1b[0m\x1b[K")
                t.stream.flush()
                pause(WARNING_FLASH_S)
        except KeyboardInterrupt:
            pass
        finally:
            t.stream.write("\r\x1b[K\x1b[?25h")
            t.stream.flush()
    print(t.style(text, "warning"), file=t.stream, flush=True)


def _rainbow(position: float, saturation: float = 0.8, lift: float = 0.0) -> str:
    return _tone(round(position % 1.0 * 48) % 48, round(saturation * 4), round(lift * 2))


def _paint_runs(cells: list[tuple[str, str]]) -> str:
    """(code, text) cells to one string, one escape per run of equal codes.

    A true colour replaces one of the same shape outright, so no reset goes between them.
    """
    out, run_code, run = [], "", []
    for code, text in cells + [("", "")]:
        if code != run_code:
            joined = "".join(run)
            replaced = code.startswith("38;2;") and code.count(";") == run_code.count(";")
            out.append(f"\x1b[{run_code}m{joined}{'' if replaced else chr(27) + '[0m'}" if run_code else joined)
            run_code, run = code, []
        run.append(text)
    out.append("".join(run))
    return "".join(out)


def sweep(text: str, now: float, t: Term, base: str | None = None) -> str:
    """Text with a band of the disc's rainbow crossing it; the band is the only thing that moves.

    Between sweeps the text keeps the terminal's own colour, so it stays readable on any theme.
    """
    if not (t.animate and t.color) or not text:
        return t.style(text, base) if base else text
    columns = display_width(text)
    position = (now % SWEEP_S) / SWEEP_S * (columns + 2 * SWEEP_REACH) - SWEEP_REACH
    rest = _code(base, t) if base else ""
    cells, column = [], 0
    for ch in text:
        light = max(0.0, 1 - abs(column - position) / SWEEP_REACH)
        if light <= 0:
            code = rest
        elif t.truecolor:
            code = _rainbow((column // 2) * 2 / max(columns, 1) * 0.7 + now * 0.08, 0.45 + 0.45 * round(light * 2) / 2)
        else:
            code = _code("flash", t) if light > 0.45 else rest
        cells.append((code, ch))
        column += display_width(ch)
    return _paint_runs(cells)


def aligned(line: str) -> str:
    for pattern, form in _COLUMNS:
        match = pattern.fullmatch(line)
        if match:
            try:
                return form.format(*map(float, match.groups()))
            except ValueError:      # a value that is not a number stays as it was
                return line
    return line


def command(line: str, t: Term | None = None) -> str:
    """A line to copy: the part that differs stands out. Only colour is added, so it pastes as written."""
    t = t or term()
    if not t.color:
        return line
    match = re.fullmatch(r"(\s*python -m discprobe)( \S+)?(.*)", line)
    if not match:
        return t.style(line, "cyan")
    head, name, rest = match.groups()
    return t.style(head, "dim") + (t.style(name, "flash") if name else "") + re.sub(r"--[\w-]+", lambda m: t.style(m[0], "cyan"), rest)


def guide_line(line: str, t: Term | None = None) -> str:
    """A line of `guide`: what is done is green, what only explains itself steps back. Translated here, as paint hides it from `i18n`."""
    t = t or term()
    if line.lstrip().startswith("python "):
        return command(line, t)
    line = tr(line)
    if not t.color or not line:
        return line
    step = re.fullmatch(r"(  )\[(x| )\]( .+? {2,})(.*)", line)
    if step:
        indent, tick, name, detail = step.groups()
        box = f"\x1b[{t.green}m[x]\x1b[0m" if tick == "x" else t.style("[ ]", "dim")
        return indent + box + name + t.style(detail, "dim")
    if line.startswith(" "):
        return line
    return t.style(line, "bold" if line.endswith((":", "：")) else "dim")


def help_text(text: str, t: Term | None = None) -> str:
    """`--help` at a terminal: headings and the names to type stand out, and the columns stay as argparse set them."""
    t = t or term()
    if not t.color:
        return text
    lines = []
    for line in text.split("\n"):
        line = tr(line)
        if line.lstrip().startswith("python -m discprobe"):
            line = command(line, t)
        elif line.startswith("usage: "):
            line = t.style("usage:", "bold") + line[6:]
        elif line and not line.startswith(" ") and line.endswith((":", "：")):
            line = t.style(line, "bold")
        else:
            line = re.sub(r"^( {2})(-[^ ]*(?: [^ ]+)*?|[a-z]\w*)(?= {2,}|$)", lambda m: m[1] + t.style(m[2], "cyan"), line)
        lines.append(line)
    return "\n".join(lines)


class Progress:
    """One line that overwrites itself; `status` returns (fraction or None, label, seconds left or None).

    A narrow terminal loses whole parts, least useful first, and never gets a wrapped line.
    With `keys` given, a game can be opened under it; with `pulse`, recent read times show beside it.
    `wait_s` is how long this kind of run usually takes, for choosing a puzzle before an estimate exists.
    """

    def __init__(self, status, t: Term | None = None, keys=None, pulse=None, wait_s: float | None = None):
        self.t = t or term()
        self.status = status
        self.pulse = pulse
        self.wait_s = wait_s
        self.left = None
        self.puzzle = None
        self.taskbar_shown = None
        self.taskbar_at = 0.0
        self.fraction = None
        self.started = time.monotonic()
        self.last_draw = 0.0
        self.width_shown = 0
        self.line_shown = None
        self.percent_shown = None
        self.percent_lit = set()
        self.percent_changed = 0.0
        self.interval = 1 / (ANIMATED_FPS if self.t.animate else PLAIN_FPS)
        self.closed = False
        self.event_at = None
        self.location = getattr(status, "location", None)
        self.keys = keys
        self.game = None        # the one on show; `games` keeps each one's board and best score
        self.games = {}
        self.game_kind = 0
        self.playing = False
        self.last_step = 0.0
        self.game_size = None
        if self.t.ansi:
            self.t.stream.write("\x1b[?25l")
        if self.t.ansi or keys:
            atexit.register(self.close)

    def _spinner(self, now: float) -> str:
        frames = SPINNER_UNICODE if self.t.unicode else SPINNER_BLOCKS if self.t.blocks else SPINNER_ASCII
        return frames[int((now - self.started) / SPINNER_FRAME_S) % len(frames)]

    def _glint(self, cell: int, filled: int, now: float) -> float:
        """A band of light down the finished part of the bar now and then; the idea is Codex's shimmer."""
        if not self.t.animate:
            return 0.0
        position = min((now % GLINT_EVERY_S) / GLINT_SWEEP_S, 1.0) * (filled + 2 * GLINT_REACH) - GLINT_REACH
        distance = min(abs(cell - position) / GLINT_REACH, 1.0)
        return 0.5 * (1 + math.cos(math.pi * distance))

    def _bar(self, fraction: float, now: float) -> tuple[str, str]:
        """The bar as plain text and as painted text. Line glyphs need no brackets and move in half cells."""
        blocks = self.t.blocks
        fill, head, rest = BAR_UNICODE if blocks else BAR_ASCII
        halves = int(fraction * BAR_WIDTH * 2)
        filled = halves // 2
        tip = head if filled < BAR_WIDTH and (halves % 2 or not blocks) else ""
        tail = rest * (BAR_WIDTH - filled - len(tip))
        left, right = ("", "") if blocks else ("[", "]")
        plain = f"{left}{fill * filled}{tip}{tail}{right}"
        if not self.t.color:
            return plain, plain
        if self.t.truecolor:
            hue = lambda i: (i // BAR_COLOUR_CELLS) * BAR_COLOUR_CELLS / BAR_WIDTH * 0.75
            done = _paint_runs([(_rainbow(hue(i), lift=self._glint(i, filled, now)), fill) for i in range(filled)])
            tip_painted = f"\x1b[{_rainbow(hue(filled), lift=1.0)}m{tip}\x1b[0m" if tip else ""
        else:
            done = self.t.style(fill * filled, "cyan")
            tip_painted = self.t.style(tip, "cyan") if tip else ""
        return plain, left + done + tip_painted + (self.t.style(tail, "dim") if tail else "") + right

    def _spark(self) -> list[tuple[str, str]]:
        """The last read times, tallest for the slowest of them, so a noisy drive shows as it happens."""
        if not self.pulse or not self.t.blocks:
            return []
        low, span = min(self.pulse), max(max(self.pulse) - min(self.pulse), 1.0)
        text = "".join(SPARK[int((v - low) / span * 7.99)] for v in self.pulse).rjust(SPARK_CELLS)
        return [(text, self.t.style(text, "dim"))]

    def _taskbar(self, now: float) -> str:
        """The tab and the taskbar button fill too, so a long run can be left in the background."""
        if not self.t.taskbar:
            return ""
        state = "3;0" if self.fraction is None else f"1;{int(self.fraction * 100 + 1e-9)}"
        if state == self.taskbar_shown and now - self.taskbar_at < TASKBAR_REFRESH_S:
            return ""
        self.taskbar_shown, self.taskbar_at = state, now
        return f"\x1b]9;4;{state}\x07"

    def _percent(self, fraction: float, now: float) -> tuple[str, str]:
        """The percentage as plain and painted text: a digit that just changed flashes, and 100% stays green.

        Rounded down, so it only reads 100% when the work is done.
        """
        text = f"{int(fraction * 100 + 1e-9):3d}%"
        if text != self.percent_shown:
            old = self.percent_shown or text    # the first value is news to nobody
            self.percent_lit = {i for i, (a, b) in enumerate(zip(old, text)) if a != b}
            self.percent_changed = now
            self.percent_shown = text
        if not self.t.color:
            return text, text
        if text == "100%":
            return text, f"\x1b[{self.t.green}m{text}\x1b[0m"
        if self.t.animate and now - self.percent_changed < PERCENT_FLASH_S:
            return text, _paint_runs([(STYLES["flash"] if i in self.percent_lit else "", ch) for i, ch in enumerate(text)])
        return text, text

    def _render(self, columns: int | None = None) -> tuple[str, int]:
        columns = columns if columns is not None else shutil.get_terminal_size((80, 24)).columns
        room = max(10, columns - 1)
        now = time.monotonic()
        fraction, label, left = self.status()
        self.fraction = None if fraction is None else max(0.0, min(1.0, fraction))
        self.left = left
        label = tr(label)
        glyph = self._spinner(now)
        spin = [(glyph, f"\x1b[{_rainbow(now * 0.1)}m{glyph}\x1b[0m" if self.t.truecolor else self.t.style(glyph, "cyan"))] if self.t.animate else []
        meter = []
        if fraction is not None:
            fraction = max(0.0, min(1.0, fraction))
            meter = [self._bar(fraction, now), self._percent(fraction, now)]
        percent = meter[1:]
        title = [(label, sweep(label, now, self.t))]
        elapsed = clock(now - self.started)
        spent = [(elapsed, self.t.style(elapsed, "dim"))]
        due = []
        if left is not None:
            text = tr(f"about {clock(left)} left")
            due = [(text, text)]
        stop = tr("Ctrl+C to stop")
        stop_part = [(stop, self.t.style(stop, "dim"))]
        game_part = []
        if self.keys and not self.playing:
            text = tr("g: game")
            game_part = [(text, self.t.style(text, "dim"))]
        spark = self._spark()
        for parts in (spin + meter + title + spark + spent + due + stop_part + game_part,
                      spin + meter + title + spent + due + stop_part + game_part,
                      spin + meter + title + spent + due + game_part,
                      spin + meter + title + spent + due,
                      spin + meter + title + due,
                      spin + percent + title + due,
                      spin + percent + title,
                      spin + title):
            width = sum(display_width(p[0]) for p in parts) + 2 * (len(parts) - 1)
            if width <= room:
                return "  ".join(p[1] for p in parts), width
        cut = i18n.fit(label, room)
        return cut, display_width(cut)

    def tick(self, force: bool = False, interval: float | None = None) -> None:
        if self.closed:
            return
        now = time.monotonic()
        if os.environ.get("DISCPROBE_EVENTS"):
            if self.event_at is None or now - self.event_at >= 0.25:
                fraction, stage, eta = self.status()
                event("progress", fraction=fraction, stage=stage, eta_s=eta,
                      **(self.location() if self.location else {}))
                self.event_at = now
            if not self.t.interactive:
                return
        if not force and now - self.last_draw < (interval if interval is not None else self.interval):
            return
        self.last_draw = now
        line, width = self._render()
        taskbar = self._taskbar(now)
        if line == self.line_shown:
            if taskbar:
                self.t.stream.write(taskbar)
                self.t.stream.flush()
            return
        self.line_shown = line
        if self.t.ansi:     # with wrapping off a miscounted glyph is clipped, not pushed to a new row
            self.t.stream.write(f"{taskbar}{self._unwrap()}\r\x1b[?7l{line}\x1b[K\x1b[?7h")
        else:
            self.t.stream.write("\r" + line + " " * max(0, self.width_shown - width))
        self.t.stream.flush()
        self.width_shown = width

    def _unwrap(self) -> str:
        """After the window narrows, the terminal folds the line already shown onto more rows, and only the
        last would be cleared. Go up and clear them all. Only where the terminal is known to fold it: elsewhere
        going up would erase a measured line, and a leftover is the lesser harm. Rounds down, for the same reason."""
        if not self.t.sync or not self.width_shown:
            return ""
        columns = shutil.get_terminal_size((80, 24)).columns
        if self.width_shown <= columns:
            return ""
        rows = (self.width_shown - 1) // columns
        self.width_shown = 0
        return f"\r\x1b[{rows}A\x1b[J"

    def _wipe(self) -> None:
        self.line_shown = None
        if self.t.ansi:
            self.t.stream.write(self._unwrap())
        if self.playing:
            self.t.stream.write("\r\x1b[J")
        elif self.t.ansi:
            self.t.stream.write("\r\x1b[K")
        elif self.width_shown:
            self.t.stream.write("\r" + " " * self.width_shown + "\r")
        self.width_shown = 0

    def log(self, *parts) -> None:
        """Print a line above the progress line."""
        event("log", text=tr(" ".join(str(p) for p in parts)), level="info")
        self._wipe()
        print(tr(aligned(" ".join(str(p) for p in parts))), file=self.t.stream, flush=True)
        if self.playing:
            self._draw_game()
        self.tick(force=True)

    def close(self) -> None:
        if self.closed:
            return
        if os.environ.get("DISCPROBE_EVENTS"):
            self.event_at = None
            self.tick(force=True)
        self.closed = True
        self._wipe()
        self.playing = False
        if self.keys:
            self.keys.close()
        if self.taskbar_shown:
            self.t.stream.write("\x1b]9;4;0;0\x07")
        if self.t.ansi:
            self.t.stream.write("\x1b[?25h")
        for game in self.games.values():
            if game.best:
                print(tr(f"{game.name}: best score {game.best}"), file=self.t.stream)
            if hasattr(game, "save"):       # the measuring is over, so a file may take its time
                game.save()
        self.t.stream.flush()

    # The game below is reached only from `play`, inside the pause before a timed read.

    def play(self) -> None:
        if not self.keys or self.closed:
            return
        for key in self.keys.read():
            self._press(snake.key_name(key))
        if self.playing and shutil.get_terminal_size((80, 24)) != self.game_size:
            self._wipe()        # a resize moves everything: draw it afresh, or close if it no longer fits
            self.playing = False
            self._open_game()
        now = time.monotonic()
        if self.playing and not self.game.over and now - self.last_step >= self.game.step_s:
            self.last_step = now
            self._advance(self.game.step)

    def _advance(self, move) -> None:
        score = self.game.score
        self._draw_cells(move() or [])
        if self.game.score != score or self.game.over:
            self._draw_hint()
        self.t.stream.flush()

    def _press(self, key: str) -> None:
        if not self.playing:
            if key in ("g", "G"):
                self._open_game()
            return
        if key in ("q", "Q"):
            self._wipe()
            self.playing = False
            self.tick(force=True)
        elif key in ("n", "N"):
            self.game_kind += 1
            self._wipe()
            self.playing = False
            self._open_game()
        elif key in ("r", "R") and self.game.over:
            self.game.reset()
            self._draw_game()
        elif key in snake.DIRECTIONS or key in getattr(self.game, "keys", ()):
            self._advance(lambda: self.game.turn(key))

    def _kinds(self) -> list:
        """The games on offer. A puzzle is chosen once, by the wait left when it first comes up."""
        from . import filldisc, sectors, sudoku
        if self.puzzle is None:
            left = self.left if self.left is not None else (self.wait_s - (time.monotonic() - self.started) if self.wait_s else None)
            self.puzzle = sudoku.for_wait(left)
        return [snake.Snake, filldisc.FillDisc, sectors.Sectors] + ([self.puzzle] if self.puzzle else [])

    def _open_game(self) -> None:
        size = shutil.get_terminal_size((80, 24))
        kinds = self._kinds()
        for skipped in range(len(kinds)):       # a game too wide for the window is passed over, so the others stay in reach
            kind = kinds[(self.game_kind + skipped) % len(kinds)]
            cols = min(kind.max_cols, (size.columns - 4) // kind.cell_w)
            if cols >= kind.min_cols and size.lines >= snake.ROWS + 4:
                self.game_kind += skipped
                break
        else:
            self.log("The window is too small for the game")
            return
        kept = self.games.get(kind)
        if kept is None or kept.cols != cols:
            self.games[kind] = kind(cols)
            self.games[kind].best = max(kept.best if kept else 0, self.games[kind].best)
        self.game = self.games[kind]
        self.playing = True
        self.game_size = size
        self.last_step = time.monotonic()
        self._draw_game()
        self.tick(force=True)

    def _below(self, rows: int, text: str) -> str:
        return f"\x1b[{rows}B{text}\x1b[{rows}A\r"

    def _draw_hint(self) -> None:
        text = i18n.fit(tr(self.game.hint()), self.game_size.columns - 3)
        self.t.stream.write(self._below(1, f"\r\x1b[K  {self.t.style(text, 'dim')}"))

    def _board_top(self) -> int:
        """Rows from the progress line to the board, which sits in the middle of the space kept for it."""
        return 2 + (snake.ROWS - self.game.rows * self.game.cell_h) // 2

    def _draw_cells(self, changed) -> None:
        from . import gameart
        g = self.game
        top = self._board_top()
        for x, y, kind in changed:
            for r, row in enumerate(gameart.paint_kind(kind, x, y, g, self.t)):
                self.t.stream.write(self._below(top + y * g.cell_h + r, f"\x1b[{3 + g.cell_w * x}G{row}"))

    def _draw_game(self) -> None:
        """Make room below the progress line (scrolling if at the bottom), then draw all of it."""
        from . import gameart
        below = snake.ROWS + 1
        self.t.stream.write("\n" * below + f"\x1b[{below}A\r")
        self._draw_hint()
        g = self.game
        top = self._board_top()
        for y in range(g.rows):
            cells = [gameart.paint(g, x, y, self.t) for x in range(g.cols)]
            for r in range(g.cell_h):
                self.t.stream.write(self._below(top + y * g.cell_h + r, f"\r  {''.join(c[r] for c in cells)}\x1b[K"))
        self.t.stream.flush()


def open_keys(t: Term | None = None):
    """Keys for the game, where it can be played: it needs motion and someone at the keyboard."""
    t = t or term()
    return snake.open_keys() if t.animate and t.can_prompt() else None


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
        self.last = None
        self.read_times = collections.deque(maxlen=SPARK_CELLS)     # read only inside the pause, like everything drawn

    def __getattr__(self, name):
        return getattr(self._dev, name)

    def execute(self, *args, **kwargs):
        cdb = args[0] if args else kwargs.get("cdb", b"")
        if os.environ.get("DISCPROBE_EVENTS") and cdb and cdb[0] in (0x28, 0xA8, 0xBE):
            self.event_lba = int.from_bytes(cdb[2:6], "big")
        res = self.last = self._dev.execute(*args, **kwargs)
        if self.progress:
            self.progress.tick(interval=OUTSIDE_PAUSE_INTERVAL_S)
        return res

    def idle(self, seconds: float) -> None:
        start = time.perf_counter()
        self.pauses += 1
        if self.last is not None and self.last.ok:      # what ran before a pause is the timed read
            self.read_times.append(self.last.duration_us)
        if self.progress:
            self.progress.play()
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
        if stage == "phase":    # no line may have been drawn during the rotation test
            marks.setdefault("period", marks["phase"] - 3 * probe.period_reads)
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
    def location():
        lba = getattr(dev, "event_lba", None)
        if lba is None:
            return {}
        values = dict(lba=lba)
        # The initial prior is not a measured geometry. Wait for fitted targets.
        if getattr(ladder, "cov", None) is not None:
            b = ladder.prior.bit_nm * 1e-6
            values["radius_mm"] = b * math.sqrt(ladder.u ** 2 + ladder.v * ladder._n_end(lba) / math.pi)
        return values
    status.location = location
    return status


@contextlib.contextmanager
def _animated(status):
    """A progress line with its own drawing thread, for work where no timing is being measured."""
    t = term()
    progress = Progress(status, t)
    lock = threading.Lock()
    stop = threading.Event()

    def draw():
        while not stop.wait(progress.interval):
            with lock:
                progress.tick()
    thread = threading.Thread(target=draw, daemon=True)
    thread.start()
    with lock:
        progress.tick(force=True)

    def log(*parts):
        with lock:
            progress.log(*parts)
    try:
        yield log, progress
    finally:
        stop.set()
        thread.join(1.0)
        progress.close()


def _file_stamp(path: str):
    try:
        status = os.stat(path)
        return status.st_size, status.st_mtime_ns
    except OSError:
        return None


def _remove(path: str) -> bool:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        return False
    return True


@contextlib.contextmanager
def _whole_or_gone(path: str):
    """An image cut short must not pass for a finished one, since it may get burned.

    If the write fails or is stopped, what it left goes. A file it never touched stays: a check can fail before
    the writer opens anything. A killed process or closed window cleans up nothing, so a marker beside the
    image says it isn't whole, for `guide` and for the next write.
    """
    marker = path + iso9660.UNFINISHED
    if os.path.exists(marker) and _remove(path):
        _remove(marker)
    before = _file_stamp(path)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(marker, "w", encoding="utf-8"):
            pass
    except OSError:
        pass        # the writer will say what is wrong with this folder
    try:
        yield
    except BaseException:
        if _file_stamp(path) == before:
            _remove(marker)
        elif _remove(path):     # if it can't be removed, the marker stays and still says so
            _remove(marker)
            say("The unfinished image was removed.")
        raise
    _remove(marker)


@contextlib.contextmanager
def writing(path: str, sectors: int):
    """`log` for the ISO writers. At a terminal their percentage lines become a progress line.

    The writers report only every 10 or 20 %, so between reports the bar follows the file's real
    size. Only a report can say 100 %. Pipes get the writers' lines as they always did.
    """
    with _whole_or_gone(path):
        if not term().interactive:
            yield _report_lines() if os.environ.get("DISCPROBE_EVENTS") else print
            return
        with _writing_line(path, sectors) as log:
            yield log


def _report_lines():
    """The writers' log for the web UI: each percentage report (asked for every 1 %) is a progress event; the
    printed lines stay as a pipe always had them, one per 20 %."""
    shown = [-1.0]

    def log(message):
        match = re.search(r"([\d.]+) %", message)
        if not match:
            print(message, flush=True)
            return
        fraction = float(match.group(1)) / 100
        event("progress", fraction=round(fraction, 4), stage="writing the image")
        if fraction >= 0.999 or fraction - shown[0] >= 0.2 - 1e-9 or shown[0] < 0:
            shown[0] = fraction
            print(message, flush=True)
    log.every = 0.01
    return log


@contextlib.contextmanager
def _writing_line(path: str, sectors: int):
    total = max(sectors * 2048, 1)
    reported = [0.0]
    rate = _Rate()

    def status():
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        fraction = max(reported[0], min(size / total, 0.99))
        return fraction, "writing the image", rate.left(fraction * 1000, 1000)
    with _animated(status) as (show, progress):
        def log(message):
            match = re.search(r"([\d.]+) %", message)
            if match:
                reported[0] = float(match.group(1)) / 100
            else:
                show(message)
        log.every = 0.01        # the bar moves with each 1 % the writer reports
        yield log
    say(f"Finished in {clock(time.monotonic() - progress.started)}", "dim")


@contextlib.contextmanager
def busy(label: str):
    """A turning disc and a label for work of unknown length. Pipes see nothing."""
    if not term().interactive:
        yield
        return
    with _animated(lambda: (None, label, None)):
        yield
