"""The guided console: the whole workflow, every command and the picture form on one screen.

`guide` prints the same steps as plain lines, which is what scripts and pipes get. This is the
version for a person in a terminal: arrow keys, a filterable list of every command, a form for
`image`, and each step run in place. It is built from escape sequences and the standard library,
so the program keeps its promise of no dependency beyond numpy, Pillow and scipy -- and the
offline Windows package keeps working.

The state machine (`Console.handle` / `Console.text`) never reads a terminal, so the checks can
drive it with keys and look at the lines it would draw.
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import banner, guide, i18n, ui
from .i18n import tr

PROG = guide.PROG
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff")

FOOTER_HOME = "Up/Down move   Enter open   r run   : commands   ? keys   q quit"
FOOTER_STEP = "Enter/r run   e edit   c copy   Esc back"
FOOTER_FORM_STEP = "Enter/r open the picture form   Esc back"
FOOTER_BACK = "Esc back"
FOOTER_PALETTE = "Up/Down move   Enter help   r run   c copy   Esc back"
FOOTER_HELP = "r run   e edit   c copy   Up/Down scroll   Esc back"
FOOTER_EDIT = "Enter run   Esc back"
FOOTER_FORM = "Tab complete or next   Enter next or run   Esc cancel"
FOOTER_KEYS = "Esc or Enter back"

WIN_ARROWS = {"H": "up", "P": "down", "K": "left", "M": "right",
              "G": "home", "O": "end", "I": "pgup", "Q": "pgdn",
              "S": "delete", "R": "insert"}
CSI_KEYS = {"A": "up", "B": "down", "C": "right", "D": "left",
            "H": "home", "F": "end", "Z": "shift-tab"}
TILDE_KEYS = {"1": "home", "2": "insert", "3": "delete", "4": "end",
              "5": "pgup", "6": "pgdn", "7": "home", "8": "end"}
CONTROL = {0x00: "ctrl-space", 0x08: "backspace", 0x09: "tab", 0x0A: "enter", 0x0D: "enter",
           0x7F: "backspace"}
for _code in range(1, 27):
    CONTROL.setdefault(_code, "ctrl-" + chr(_code + 96))
del _code


# --- keys ---------------------------------------------------------------------------------------

def parse_keys(data: bytes) -> tuple[list[str], bytes]:
    """Decode one read of terminal input into key names, and return bytes of an unfinished sequence.

    The console only needs a small keyboard, but a terminal may send a whole buffer: several keys,
    an arrow sequence, a bracketed paste or a mouse event. Everything unfinished stays in the
    caller's buffer for the next read, so a sequence split across reads still arrives whole.
    """
    keys: list[str] = []
    index, total = 0, len(data)
    while index < total:
        byte = data[index]
        if byte == 0x1B:
            rest = data[index:]
            if len(rest) == 1:
                return keys, rest
            if rest[1:2] == b"[":
                match = re.match(rb"\x1b\[([0-9;?<=>]*)([@-~])", rest)
                if match is None:
                    if len(rest) < 24:
                        return keys, rest
                    index += 1
                    continue
                params = match.group(1).decode("ascii", "replace")
                final = chr(match.group(2)[0])
                end = match.end()
                if params == "200" and final == "~":
                    close = rest.find(b"\x1b[201~", end)
                    if close < 0:
                        return keys, rest
                    text = rest[end:close].decode("utf-8", "replace")
                    keys.append("paste:" + text.replace("\r\n", "\n").replace("\r", "\n"))
                    index += close + 6
                    continue
                if params.startswith("<") and final in "Mm":
                    try:
                        bits, x, y = (int(part) for part in params[1:].split(";"))
                    except ValueError:
                        keys.append("")
                    else:
                        keys.append("mouse:%d:%d:%d:%s" % (bits, x, y, final))
                elif final in CSI_KEYS:
                    keys.append(CSI_KEYS[final])
                elif final == "~":
                    keys.append(TILDE_KEYS.get(params.split(";")[0], ""))
                index += end
                continue
            if rest[1:2] == b"O":
                if len(rest) < 3:
                    return keys, rest
                keys.append({"A": "up", "B": "down", "C": "right", "D": "left",
                             "H": "home", "F": "end"}.get(chr(rest[2]), ""))
                index += 3
                continue
            char, used = _next_char(rest[1:])
            if char is None:
                return keys, rest
            keys.append("alt-" + char)
            index += 1 + used
            continue
        if byte < 0x20 or byte == 0x7F:
            key = CONTROL.get(byte)
            if key:
                keys.append(key)
            index += 1
            continue
        char, used = _next_char(data[index:])
        if char is None:
            return keys, data[index:]
        keys.append(char)
        index += used
    return keys, b""


def _next_char(buf: bytes) -> tuple[str | None, int]:
    """One UTF-8 character, and how many bytes it took; None when the buffer holds only part of it."""
    if not buf:
        return "", 0
    first = buf[0]
    if first < 0x80:
        return chr(first), 1
    if 0xC2 <= first <= 0xDF:
        size = 2
    elif 0xE0 <= first <= 0xEF:
        size = 3
    elif 0xF0 <= first <= 0xF4:
        size = 4
    else:
        return "\ufffd", 1
    if len(buf) < size:
        return None, 0
    try:
        return buf[:size].decode("utf-8"), size
    except UnicodeDecodeError:
        return "\ufffd", size


def _char_keys(char: str) -> list[str]:
    if char in ("\r", "\n"):
        return ["enter"]
    if char == "\t":
        return ["tab"]
    if char in ("\x08", "\x7f"):
        return ["backspace"]
    if char == "\x1b":
        return ["esc"]
    if len(char) == 1 and ord(char) < 0x20:
        return [CONTROL.get(ord(char), "")]
    return [char] if char else []


def _open_keys():
    """A key reader for this terminal, or None when stdin is not one."""
    try:
        if sys.platform == "win32":
            if os.environ.get("WT_SESSION"):
                try:
                    keys = _WindowsVtKeys()
                    keys.resume()
                    keys.pause()
                    return keys
                except (ImportError, OSError, AttributeError, ValueError):
                    pass
            try:
                keys = _WindowsConsoleKeys()
                keys.resume()
                keys.pause()
                return keys
            except (ImportError, OSError, AttributeError, ValueError):
                pass
            try:
                keys = _WindowsVtKeys()
                keys.resume()
                keys.pause()
                return keys
            except (ImportError, OSError, AttributeError, ValueError):
                return _WindowsKeys()
        if not (sys.stdin and sys.stdin.isatty()):
            return None
        return _PosixKeys()
    except (ImportError, OSError, ValueError, AttributeError):
        return None


class _WindowsKeys:
    """msvcrt gives characters one at a time; arrows arrive as a NUL prefix and a scan code."""

    def __init__(self):
        import msvcrt
        self.msvcrt = msvcrt

    def resume(self) -> None:
        return None

    def pause(self) -> None:
        return None

    def close(self) -> None:
        return None

    def read(self, timeout: float = 0.25) -> list[str]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.msvcrt.kbhit():
                char = self.msvcrt.getwch()
                if char in ("\x00", "\xe0"):
                    # The second half of a function key: the arrow keys this console needs.
                    scan = self.msvcrt.getwch()
                    key = WIN_ARROWS.get(scan)
                    if key:
                        return [key]
                    continue
                keys = _char_keys(char)
                if keys:
                    return keys
            else:
                time.sleep(0.01)
        return []


class _WindowsVtKeys:
    """Read Windows Terminal's VT input, including SGR mouse reports.

    conhost reports the mouse only through ReadConsoleInput, which msvcrt does not expose. Windows
    Terminal (and other VT terminals on Windows) instead sends keys and mouse reports as the same
    escape sequences the POSIX reader gets, once the input handle has ENABLE_VIRTUAL_TERMINAL_INPUT.
    """

    ENABLE_MOUSE_INPUT = 0x0010
    ENABLE_QUICK_EDIT_MODE = 0x0040
    ENABLE_EXTENDED_FLAGS = 0x0080
    ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200

    def __init__(self):
        import ctypes
        import msvcrt
        self.ctypes = ctypes
        self.msvcrt = msvcrt
        self.buf = ""
        self.raw = False
        self.mouse = bool(os.environ.get("WT_SESSION"))
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
        self.kernel32.GetConsoleMode.restype = ctypes.c_int
        self.kernel32.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.kernel32.SetConsoleMode.restype = ctypes.c_int
        self.handle = msvcrt.get_osfhandle(sys.stdin.fileno())
        self.saved = ctypes.c_uint()
        if not self.kernel32.GetConsoleMode(self.handle, ctypes.byref(self.saved)):
            raise OSError(ctypes.get_last_error(), "stdin is not a console")

    def resume(self) -> None:
        if self.raw:
            return
        mode = (self.saved.value | self.ENABLE_MOUSE_INPUT | self.ENABLE_EXTENDED_FLAGS
                | self.ENABLE_VIRTUAL_TERMINAL_INPUT) & ~self.ENABLE_QUICK_EDIT_MODE
        if not self.kernel32.SetConsoleMode(self.handle, mode):
            raise OSError(self.ctypes.get_last_error(), "could not enable VT input")
        self.raw = True

    def pause(self) -> None:
        if self.raw:
            self.kernel32.SetConsoleMode(self.handle, self.saved.value)
            self.raw = False

    def close(self) -> None:
        self.pause()

    def read(self, timeout: float = 0.25) -> list[str]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.msvcrt.kbhit():
                char = self.msvcrt.getwch()
                if char in ("\x00", "\xe0"):
                    scan = self.msvcrt.getwch()
                    key = WIN_ARROWS.get(scan)
                    if key:
                        return [key]
                    continue
                self.buf += char
                keys, rest = parse_keys(self.buf.encode("utf-8", "replace"))
                if keys:
                    self.buf = rest.decode("utf-8", "replace")
                    return keys
            else:
                time.sleep(0.01)
        if self.buf == "\x1b":
            self.buf = ""
            return ["esc"]
        return []


class _WindowsConsoleKeys:
    """Read conhost input records, so cmd.exe gets the same clicks as Windows Terminal.

    Windows Terminal is asked for VT input (and SGR mouse reports) separately; this reader uses
    ReadConsoleInput, which is the only mouse source in the classic console host.
    """

    ENABLE_MOUSE_INPUT = 0x0010
    ENABLE_QUICK_EDIT_MODE = 0x0040
    ENABLE_EXTENDED_FLAGS = 0x0080
    ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200
    KEY_EVENT = 0x0001
    MOUSE_EVENT = 0x0002
    MOUSE_WHEELED = 0x0004
    SCAN = {0x48: "up", 0x50: "down", 0x4B: "left", 0x4D: "right",
            0x47: "home", 0x4F: "end", 0x49: "pgup", 0x51: "pgdn",
            0x52: "insert", 0x53: "delete"}

    def __init__(self):
        import ctypes
        import msvcrt
        from ctypes import wintypes

        class Coord(ctypes.Structure):
            _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

        class KeyEvent(ctypes.Structure):
            _fields_ = [("bKeyDown", wintypes.BOOL),
                        ("wRepeatCount", wintypes.WORD),
                        ("wVirtualKeyCode", wintypes.WORD),
                        ("wVirtualScanCode", wintypes.WORD),
                        ("uChar", wintypes.WCHAR),
                        ("dwControlKeyState", wintypes.DWORD)]

        class MouseEvent(ctypes.Structure):
            _fields_ = [("dwMousePosition", Coord),
                        ("dwButtonState", wintypes.DWORD),
                        ("dwControlKeyState", wintypes.DWORD),
                        ("dwEventFlags", wintypes.DWORD)]

        class Event(ctypes.Union):
            _fields_ = [("KeyEvent", KeyEvent), ("MouseEvent", MouseEvent)]

        class InputRecord(ctypes.Structure):
            _fields_ = [("EventType", wintypes.WORD), ("Event", Event)]

        class SmallRect(ctypes.Structure):
            _fields_ = [("Left", wintypes.SHORT), ("Top", wintypes.SHORT),
                        ("Right", wintypes.SHORT), ("Bottom", wintypes.SHORT)]

        class ScreenBufferInfo(ctypes.Structure):
            _fields_ = [("dwSize", Coord), ("dwCursorPosition", Coord),
                        ("wAttributes", wintypes.WORD), ("srWindow", SmallRect),
                        ("dwMaximumWindowSize", Coord)]

        self.ctypes = ctypes
        self.ScreenBufferInfo = ScreenBufferInfo
        self.msvcrt = msvcrt
        self.Coord, self.KeyEvent, self.MouseEvent = Coord, KeyEvent, MouseEvent
        self.Event, self.InputRecord = Event, InputRecord
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
        self.kernel32.GetConsoleMode.restype = ctypes.c_int
        self.kernel32.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.kernel32.SetConsoleMode.restype = ctypes.c_int
        self.kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.kernel32.WaitForSingleObject.restype = ctypes.c_uint
        self.kernel32.ReadConsoleInputW.argtypes = [ctypes.c_void_p, ctypes.POINTER(InputRecord),
                                                     ctypes.c_uint, ctypes.POINTER(ctypes.c_uint)]
        self.kernel32.ReadConsoleInputW.restype = ctypes.c_int
        self.kernel32.GetConsoleScreenBufferInfo.argtypes = [ctypes.c_void_p,
                                                             ctypes.POINTER(ScreenBufferInfo)]
        self.kernel32.GetConsoleScreenBufferInfo.restype = ctypes.c_int
        self.handle = msvcrt.get_osfhandle(sys.stdin.fileno())
        self.info = ScreenBufferInfo()
        self.saved = ctypes.c_uint()
        if not self.kernel32.GetConsoleMode(self.handle, ctypes.byref(self.saved)):
            raise OSError(ctypes.get_last_error(), "stdin is not a console")
        self.raw = False
        self.mouse = True
        self.vt_mouse = False
        self.left = False

    def resume(self) -> None:
        if self.raw:
            return
        mode = (self.saved.value | self.ENABLE_MOUSE_INPUT | self.ENABLE_EXTENDED_FLAGS)
        mode &= ~(self.ENABLE_QUICK_EDIT_MODE | self.ENABLE_VIRTUAL_TERMINAL_INPUT)
        if not self.kernel32.SetConsoleMode(self.handle, mode):
            raise OSError(self.ctypes.get_last_error(), "could not enable console mouse input")
        self.raw = True

    def pause(self) -> None:
        if self.raw:
            self.kernel32.SetConsoleMode(self.handle, self.saved.value)
            self.raw = False

    def close(self) -> None:
        self.pause()

    def read(self, timeout: float = 0.25) -> list[str]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            wait = max(1, min(50, int((deadline - time.monotonic()) * 1000)))
            if self.kernel32.WaitForSingleObject(self.handle, wait) != 0:
                continue
            record = self.InputRecord()
            count = self.ctypes.c_uint()
            if not self.kernel32.ReadConsoleInputW(self.handle, self.ctypes.byref(record), 1,
                                                   self.ctypes.byref(count)):
                return []
            if count.value:
                keys = self._record(record)
                if keys:
                    return keys
        return []

    def _record(self, record) -> list[str]:
        if record.EventType == self.KEY_EVENT:
            event = record.Event.KeyEvent
            if not event.bKeyDown:
                return []
            if event.uChar:
                return [key for key in _char_keys(event.uChar) if key]
            key = self.SCAN.get(event.wVirtualScanCode)
            return [key] if key else []
        if record.EventType != self.MOUSE_EVENT:
            return []
        event = record.Event.MouseEvent
        x, y = event.dwMousePosition.X + 1, event.dwMousePosition.Y + 1
        if self.kernel32.GetConsoleScreenBufferInfo(self.handle, self.ctypes.byref(self.info)):
            # dwMousePosition is a buffer coordinate; the screen shows only the window rectangle.
            x -= self.info.srWindow.Left
            y -= self.info.srWindow.Top
        x, y = max(1, x), max(1, y)
        if event.dwEventFlags == 0:
            pressed = bool(event.dwButtonState & 0x0001)
            if pressed and not self.left:
                self.left = True
                return ["mouse:0:%d:%d:M" % (x, y)]
            if not pressed:
                self.left = False
            return []
        if event.dwEventFlags & self.MOUSE_WHEELED:
            delta = self.ctypes.c_short((event.dwButtonState >> 16) & 0xFFFF).value
            bits = 64 if delta > 0 else 65
            return ["mouse:%d:%d:%d:M" % (bits, x, y)]
        return []


class _PosixKeys:
    """cbreak stdin, read in groups, so the console gets keys without waiting for Enter."""

    def __init__(self):
        import termios
        import tty
        self.termios, self.tty = termios, tty
        self.fd = sys.stdin.fileno()
        self.saved = termios.tcgetattr(self.fd)
        self.raw = False
        self.buf = b""

    def resume(self) -> None:
        if not self.raw:
            self.tty.setcbreak(self.fd)
            self.raw = True

    def pause(self) -> None:
        if self.raw:
            self.termios.tcsetattr(self.fd, self.termios.TCSADRAIN, self.saved)
            self.raw = False

    def close(self) -> None:
        self.pause()

    def read(self, timeout: float = 0.25) -> list[str]:
        import select
        ready = select.select([self.fd], [], [], timeout)[0]
        if not ready:
            if self.buf == b"\x1b":
                self.buf = b""
                return ["esc"]
            return []
        chunk = os.read(self.fd, 4096)
        if not chunk:
            return ["ctrl-d"]
        self.buf += chunk
        keys, rest = parse_keys(self.buf)
        if rest[:1] == b"\x1b" and len(rest) > 1:
            # A split sequence: give the rest of it a moment to arrive.
            more = select.select([self.fd], [], [], 0.02)[0]
            if more:
                self.buf = rest + os.read(self.fd, 4096)
                extra, rest = parse_keys(self.buf)
                keys += extra
        if rest == b"\x1b":
            keys.append("esc")
            rest = b""
        self.buf = rest
        return keys


class _Screen:
    """The alternate screen, the hidden cursor and the mouse modes, restored on the way out."""

    def __init__(self, t, keys, mouse: bool):
        self.t, self.keys, self.mouse = t, keys, mouse
        # conhost delivers mouse records through ReadConsoleInput; only VT terminals need the modes.
        self.vt_mouse = bool(mouse and getattr(keys, "vt_mouse", True))

    def __enter__(self):
        self.keys.resume()
        write = self.t.stream.write
        write("\x1b[?1049h\x1b[?25l")
        if self.vt_mouse:
            write("\x1b[?1000h\x1b[?1006h\x1b[?2004h")
        self.t.stream.flush()
        return self

    def __exit__(self, *exc):
        write = self.t.stream.write
        if self.vt_mouse:
            write("\x1b[?1006l\x1b[?1000l\x1b[?2004l")
        write("\x1b[?25h\x1b[?1049l")
        self.t.stream.flush()
        self.keys.pause()
        return False


# --- text helpers -------------------------------------------------------------------------------

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
# OSC 8 hyperlinks (and any other OSC string) are invisible to width and to the screen itself.
OSC_RE = re.compile(r"\x1b\](?:[^\x07\x1b]|\x1b(?!\\))*(?:\x07|\x1b\\)")
KEYCAP_RE = re.compile(r"(?<![A-Za-z0-9])(Up/Down|Enter/r|Enter|Esc|Tab|PgUp|PgDn|r|e|c|m|l|o|q|\?|:)(?![A-Za-z0-9])")


def visible(text: str) -> str:
    return ANSI_RE.sub("", OSC_RE.sub("", text))


def width_of(text: str) -> int:
    return i18n.display_width(visible(text))


def fit_line(text: str, width: int) -> str:
    if width_of(text) <= width:
        return text
    return i18n.fit(visible(text), width)


def path_url(path: str) -> str:
    """A file:// URL for a path, or "" when the platform cannot make one."""
    try:
        return Path(os.path.abspath(path)).as_uri()
    except (OSError, ValueError):
        return ""


def manual_path() -> str:
    name = "MANUAL.md" if i18n.active() == "zh" else "MANUAL.en.md"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "docs", name)


def hyperlink(text: str, url: str, t, underline: bool = True) -> str:
    """OSC 8: a clickable link in terminals that support it, plain text everywhere else.

    The sequence is invisible, so it must be stripped before any width calculation (see `visible`).
    """
    if not (url and getattr(t, "ansi", False)):
        return text
    url = url.replace("\x07", "").replace("\x1b", "")
    shown = ("\x1b[4m" + text + "\x1b[24m") if underline else text
    return f"\x1b]8;;{url}\x1b\\{shown}\x1b]8;;\x1b\\"


def filled(text: str, t, media: str, danger: bool = False, neutral: bool = False) -> str:
    """Text on a background: a dark tint with true colour, reverse video everywhere else.

    A background bar is what makes the selected row and the key names readable at a glance;
    reverse video keeps that cue on terminals that do not do 24-bit colour.
    """
    if not getattr(t, "color", False):
        return text
    if getattr(t, "truecolor", False):
        if danger:
            bg, fg = ui.oklch(0.32, 0.10, 0.03), (255, 255, 255)
        elif neutral:
            bg, fg = ui.oklch(0.30, 0.02, 0.62), (255, 255, 255)
        else:
            hue = ui.DVD_ACCENT_HUE if media == "dvd" else 0.52
            bg, fg = ui.oklch(0.30, 0.055, hue), ui.oklch(0.97, 0.01, hue)
        return "\x1b[1;38;2;%d;%d;%d;48;2;%d;%d;%dm%s\x1b[0m" % (*fg, *bg, text)
    return "\x1b[1;7m" + text + "\x1b[0m"


def clean_path(text: str) -> str:
    """A path as typed or dropped into a terminal: quotes and file:// around it are not part of it."""
    text = (text or "").strip()
    changed = True
    while changed:
        changed = False
        if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
            text = text[1:-1].strip()
            changed = True
        for prefix in ("file:///", "file://"):
            if text.lower().startswith(prefix):
                text = text[len(prefix):]
                changed = True
                break
    if os.name == "nt" and re.match(r"^/[A-Za-z]:", text):
        text = text[1:]
    return os.path.expanduser(text.strip())


def split_args(text: str) -> list[str]:
    """Split a command line the way a person means it on both Windows and POSIX.

    Backslashes stay as they are (a Windows path is not an escape), quotes group a word, and
    `--option=value` becomes two arguments so the in-process parser sees it as usual.
    """
    args: list[str] = []
    current: list[str] = []
    quote = None
    started = False
    for char in text:
        if quote:
            if char == quote:
                quote = None
            else:
                current.append(char)
        elif char in "\"'" and (not current or current[-1] == "="):
            quote = char
            started = True
        elif char.isspace():
            if current or started:
                args.append("".join(current))
                current = []
                started = False
        else:
            current.append(char)
            started = True
    if quote:
        raise ValueError(tr("A quote is not closed."))
    if current or started:
        args.append("".join(current))
    out: list[str] = []
    for arg in args:
        if arg.startswith("--") and "=" in arg:
            key, _, value = arg.partition("=")
            out.extend([key, value])
        else:
            out.append(arg)
    return out


def command_text(argv: list[str]) -> str:
    return PROG + " " + " ".join(guide.quote(part) if " " in part else part for part in argv)


def fuzzy_score(query: str, text: str) -> int | None:
    """A rank for a command name, or None when the letters are not there in order."""
    if not query:
        return 0
    if text.startswith(query):
        return 1000 - len(text)
    found = text.find(query)
    if found >= 0:
        return 700 - found
    index = -1
    score = 300
    for char in query:
        found = text.find(char, index + 1)
        if found < 0:
            return None
        if index >= 0:
            score -= found - index - 1
        index = found
    return max(50, score - len(text))


# --- commands -----------------------------------------------------------------------------------

def _parser_of(result):
    return result[0] if isinstance(result, tuple) else result


def _groups_of(result):
    if isinstance(result, tuple) and len(result) > 1 and isinstance(result[1], (list, tuple)):
        return result[1]
    return ()


def _subparsers(parser):
    for action in getattr(parser, "_actions", ()):
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _command_rows(parser, groups=()) -> list[tuple[str, str]]:
    sub = _subparsers(parser)
    if sub is None:
        return []
    order: list[str] = []
    for _, names in groups:
        order += [name for name in names if name in sub.choices]
    order += [name for name in sub.choices if name not in order]
    rows = []
    for name in order:
        if name == "menu":
            continue
        description = getattr(sub.choices[name], "description", None) or ""
        rows.append((name, description))
    return rows


def _default_builder():
    from . import __main__ as cli
    parser, _sub, _defaults = cli._build_parser()
    return parser, cli.COMMAND_GROUPS


# --- the console --------------------------------------------------------------------------------

class Console:
    """Screens, keys and what Enter does. It draws nothing itself; `text` is the whole picture."""

    def __init__(self, plan, commands=(), t=None, builder=None, out=None, mouse=False):
        self.plan = plan
        self.commands = list(commands)
        self.t = t or ui.term()
        self.builder = builder
        self.out = out or plan.out
        self.mouse = mouse
        self.width, self.height = 100, 30
        self.screen = "home"
        self.row = 0
        self.scroll = 0
        self.message = ""
        self.query = ""
        self.query_pos = 0
        self.form = None
        self.edit_text = ""
        self.edit_pos = 0
        self.help_name = ""
        self.help_lines: list[str] = []
        self._previous = "home"
        self._hits: dict[int, int] = {}
        self._zones: list[tuple[int, int, int, str]] = []
        self._pending_zones: list[tuple[int, int, int, str]] = []
        current = plan.current()
        for index, task in enumerate(plan.tasks):
            if task is current:
                self.row = index
                break

    # -- state -----------------------------------------------------------------------------------

    def task(self):
        return self.plan.tasks[self.row]

    def refresh(self) -> None:
        key = self.task().key
        self.plan = guide.workflow(self.plan.media, self.out, notes=True)
        self.out = self.plan.out
        self.row = next((index for index, task in enumerate(self.plan.tasks) if task.key == key), 0)
        self.screen = "home"
        self.scroll = 0
        self.message = ""
        self.form = None

    def set_media(self, media: str) -> None:
        key = self.task().key
        self.plan = guide.workflow(media, self.out, notes=True)
        ui.use_media(media)
        self.out = self.plan.out
        self.row = next((index for index, task in enumerate(self.plan.tasks) if task.key == key), 0)
        self.screen = "home"
        self.scroll = 0
        self.message = tr("Now showing the {media} steps.").format(media=media.upper())

    def toggle_language(self) -> None:
        lang = "en" if i18n.active() == "zh" else "zh"
        i18n.use(lang)
        os.environ["DISCPROBE_LANG"] = lang
        self.message = tr("Language: {name}").format(name="中文" if lang == "zh" else "English")
        self._reload_commands()
        if self.screen == "command":
            self.help_lines = self._command_help(self.help_name)

    def _reload_commands(self) -> None:
        if not self.builder:
            return
        try:
            result = self.builder()
            rows = _command_rows(_parser_of(result), _groups_of(result))
        except Exception:
            return
        if rows:
            self.commands = rows

    def copy(self, text: str) -> None:
        if console_copy(text, self.t):
            self.message = tr("Copied. Paste it with Ctrl+V (Cmd+V on macOS).")
        else:
            self.message = tr("Could not reach the clipboard; select the text and copy it by hand.")

    # -- keys ------------------------------------------------------------------------------------

    def handle(self, key: str):
        if key == "ctrl-c":
            return ("quit", None)
        if key == "ctrl-d":
            return ("quit", None)
        if self.screen in ("home", "step", "command", "keys"):
            if key == "?":
                self._open_keys_screen()
                return None
            if key == ":" and self.screen in ("home", "step"):
                self._open_palette()
                return None
            if key == "l":
                self.toggle_language()
                return None
            if key == "m" and self.screen in ("home", "step"):
                order = ("dvd", "cd", "bd")
                other = order[(order.index(self.plan.media) + 1) % len(order)]
                self.set_media(other)
                return None
            if key == "o":
                return ("open", os.path.abspath(self.out))
        if key.startswith("mouse:"):
            return self._mouse(key)
        if key.startswith("paste:"):
            return self._paste(key[len("paste:"):])
        if self.screen == "home":
            return self._home_key(key)
        if self.screen == "step":
            return self._step_key(key)
        if self.screen == "palette":
            return self._palette_key(key)
        if self.screen == "command":
            return self._command_key(key)
        if self.screen == "edit":
            return self._edit_key(key)
        if self.screen == "form":
            return self._form_key(key)
        if self.screen == "keys":
            return self._keys_key(key)
        return None

    def _home_key(self, key):
        count = len(self.plan.tasks)
        if key in ("up", "k"):
            self.row = max(0, self.row - 1)
            self.message = ""
        elif key in ("down", "j"):
            self.row = min(count - 1, self.row + 1)
            self.message = ""
        elif key == "home":
            self.row = 0
        elif key == "end":
            self.row = count - 1
        elif key in ("enter", "right"):
            self._open_step()
        elif key == "r":
            return self._activate(self.task())
        elif key == "e":
            return self._edit_task()
        elif key == "c":
            return self._copy_task()
        elif key == "q":
            return ("quit", None)
        elif len(key) == 1 and key.isdigit() and 1 <= int(key) <= count:
            self.row = int(key) - 1
            self._open_step()
        return None

    def _step_key(self, key):
        if key in ("esc", "left", "q"):
            self._back()
        elif key in ("up", "k"):
            self.scroll = max(0, self.scroll - 1)
        elif key in ("down", "j"):
            self.scroll += 1
        elif key == "pgup":
            self.scroll = max(0, self.scroll - max(1, self.height - 2))
        elif key == "pgdn":
            self.scroll += max(1, self.height - 2)
        elif key == "home":
            self.scroll = 0
        elif key == "end":
            self.scroll = 100000
        elif key in ("enter", "right", "r"):
            return self._activate(self.task())
        elif key == "e":
            return self._edit_task()
        elif key == "c":
            return self._copy_task()
        return None

    def _palette_key(self, key):
        rows = self._palette_rows()
        if key == "esc":
            self._back()
        elif key == "up":
            self.row = max(0, self.row - 1)
        elif key == "down":
            self.row = min(max(0, len(rows) - 1), self.row + 1)
        elif key == "pgup":
            self.row = max(0, self.row - max(1, self.height - 6))
        elif key == "pgdn":
            self.row = min(max(0, len(rows) - 1), self.row + max(1, self.height - 6))
        elif key in ("enter", "right"):
            if rows:
                self.row = min(self.row, len(rows) - 1)
                self._open_help(rows[self.row][0])
        elif key == "r":
            if rows:
                return ("run", [rows[min(self.row, len(rows) - 1)][0]])
        elif key == "c":
            if rows:
                return ("copy", PROG + " " + rows[min(self.row, len(rows) - 1)][0])
        elif key in ("left", "right", "home", "end", "backspace", "delete"):
            self._query_edit(key)
        elif len(key) == 1 and key.isprintable():
            self._query_insert(key)
        return None

    def _command_key(self, key):
        if key in ("esc", "left", "q"):
            self.screen = "palette"
            self.scroll = 0
        elif key in ("up", "k"):
            self.scroll = max(0, self.scroll - 1)
        elif key in ("down", "j"):
            self.scroll += 1
        elif key == "pgup":
            self.scroll = max(0, self.scroll - max(1, self.height - 2))
        elif key == "pgdn":
            self.scroll += max(1, self.height - 2)
        elif key == "home":
            self.scroll = 0
        elif key == "end":
            self.scroll = 100000
        elif key == "r":
            return ("run", [self.help_name])
        elif key == "e":
            return self._edit_text(PROG + " " + self.help_name)
        elif key == "c":
            return ("copy", PROG + " " + self.help_name)
        return None

    def _edit_key(self, key):
        if key == "esc":
            self._back()
        elif key == "enter":
            return self._edit_run()
        elif key in ("left", "right", "home", "end", "backspace", "delete"):
            self._edit_change(key)
        elif len(key) == 1 and key.isprintable():
            self.edit_text = self.edit_text[:self.edit_pos] + key + self.edit_text[self.edit_pos:]
            self.edit_pos += 1
        return None

    def _form_key(self, key):
        form = self.form
        if key == "esc":
            self.screen = "step"
            self.form = None
        elif key == "tab":
            if form["field"] == 0:
                self._complete_picture()
            else:
                form["field"] = min(2, form["field"] + 1)
        elif key == "down":
            form["field"] = min(2, form["field"] + 1)
        elif key in ("up", "shift-tab"):
            form["field"] = max(0, form["field"] - 1)
        elif key == "enter":
            if form["field"] == 2:
                return self._form_run()
            form["field"] = min(2, form["field"] + 1)
        elif key in ("left", "right", "home", "end", "backspace", "delete"):
            self._form_change(key)
        elif len(key) == 1 and key.isprintable():
            self._form_insert(key)
        return None

    def _keys_key(self, key):
        if key in ("esc", "enter", "q", "left"):
            self._back()
        elif key in ("up", "k"):
            self.scroll = max(0, self.scroll - 1)
        elif key in ("down", "j"):
            self.scroll += 1
        elif key == "pgup":
            self.scroll = max(0, self.scroll - max(1, self.height - 2))
        elif key == "pgdn":
            self.scroll += max(1, self.height - 2)
        elif key == "home":
            self.scroll = 0
        elif key == "end":
            self.scroll = 100000
        return None

    # -- actions ---------------------------------------------------------------------------------

    def _activate(self, task):
        if task.action == "form":
            self._open_form()
            return None
        if task.action == "burn":
            self.screen = "step"
            self.scroll = 0
            self.message = tr("Burn this step with your disc burner; the steps are shown here.")
            return None
        if task.action == "shell" and task.shell:
            return ("shell", task.shell)
        if task.action == "run" and task.argv:
            return ("run", list(task.argv))
        return None

    def _copy_task(self):
        command = self.task().command()
        if not command:
            self.message = tr("This step has no command to copy.")
            return None
        return ("copy", command)

    def _edit_task(self):
        task = self.task()
        if task.action != "run":
            self.message = tr("Only the steps that run a command can be edited.")
            return None
        return self._edit_text(task.command() or "")

    def _edit_text(self, text):
        if not text:
            self.message = tr("This step has no command to edit.")
            return None
        self._previous = self.screen
        self.screen = "edit"
        self.edit_text = text
        self.edit_pos = len(text)
        self.scroll = 0
        self.message = ""
        return None

    def _edit_change(self, key):
        text, pos = self.edit_text, self.edit_pos
        if key == "left":
            pos = max(0, pos - 1)
        elif key == "right":
            pos = min(len(text), pos + 1)
        elif key == "home":
            pos = 0
        elif key == "end":
            pos = len(text)
        elif key == "backspace" and pos > 0:
            text = text[:pos - 1] + text[pos:]
            pos -= 1
        elif key == "delete" and pos < len(text):
            text = text[:pos] + text[pos + 1:]
        self.edit_text, self.edit_pos = text, pos

    def _edit_run(self):
        text = self.edit_text.strip()
        if not text:
            self.message = tr("The command is empty.")
            return None
        for prefix in (PROG + " ", "discprobe "):
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        try:
            argv = split_args(text)
        except ValueError as error:
            self.message = str(error)
            return None
        if not argv:
            self.message = tr("The command is empty.")
            return None
        self.screen = self._previous
        self.scroll = 0
        return ("run", argv)

    def _open_step(self):
        self.screen = "step"
        self.scroll = 0
        self.message = ""

    def _open_help(self, name: str):
        self.help_name = name
        self.help_lines = self._command_help(name)
        self.screen = "command"
        self.scroll = 0
        self.message = ""

    def _command_help(self, name: str) -> list[str]:
        if self.builder:
            try:
                result = self.builder()
                sub = _subparsers(_parser_of(result))
                parser = sub.choices.get(name) if sub is not None else None
                if parser is not None:
                    return ui.help_text(parser.format_help(), self.t).splitlines()
            except Exception:
                pass
        return [PROG + " " + name + " -h"]

    def _open_palette(self):
        self._previous = self.screen
        self.screen = "palette"
        self.query = ""
        self.query_pos = 0
        self.row = 0
        self.scroll = 0
        self.message = ""

    def _open_keys_screen(self):
        self._previous = self.screen if self.screen != "keys" else "home"
        self.screen = "keys"
        self.scroll = 0
        self.message = ""

    def _back(self):
        if self.screen == "step":
            self.screen = "home"
        elif self.screen == "palette":
            self.screen = self._previous
        elif self.screen == "command":
            self.screen = "palette"
        elif self.screen == "edit":
            self.screen = self._previous
        elif self.screen == "form":
            self.screen = "step"
            self.form = None
        elif self.screen == "keys":
            self.screen = self._previous
        self.scroll = 0

    # -- palette text ----------------------------------------------------------------------------

    def _palette_rows(self):
        query = self.query.strip().lower()
        if not query:
            return list(self.commands)
        found = []
        for name, description in self.commands:
            score = fuzzy_score(query, name.lower())
            if score is not None:
                found.append((score, name, description))
        found.sort(key=lambda row: (-row[0], row[1]))
        return [(name, description) for _, name, description in found]

    def _query_insert(self, char: str):
        self.query = self.query[:self.query_pos] + char + self.query[self.query_pos:]
        self.query_pos += 1
        self.row = 0
        self.scroll = 0

    def _query_edit(self, key: str):
        text, pos = self.query, self.query_pos
        if key == "left":
            pos = max(0, pos - 1)
        elif key == "right":
            pos = min(len(text), pos + 1)
        elif key == "home":
            pos = 0
        elif key == "end":
            pos = len(text)
        elif key == "backspace" and pos > 0:
            text = text[:pos - 1] + text[pos:]
            pos -= 1
        elif key == "delete" and pos < len(text):
            text = text[:pos] + text[pos + 1:]
        self.query, self.query_pos = text, pos
        self.row = 0
        self.scroll = 0

    def _paste(self, text: str):
        text = text.replace("\n", " ").replace("\r", " ")
        if self.screen == "palette":
            self.query = self.query[:self.query_pos] + text + self.query[self.query_pos:]
            self.query_pos += len(text)
            self.row = 0
        elif self.screen == "edit":
            self.edit_text = self.edit_text[:self.edit_pos] + text + self.edit_text[self.edit_pos:]
            self.edit_pos += len(text)
        elif self.screen == "form" and self.form is not None:
            field = self.form["field"]
            pos = self.form["pos"][field]
            value = self.form["values"][field]
            self.form["values"][field] = value[:pos] + text + value[pos:]
            self.form["pos"][field] = pos + len(text)
        return None

    # -- form ------------------------------------------------------------------------------------

    def _open_form(self):
        self.form = {"field": 0, "values": ["", "iso/picture.iso", "latest"],
                     "pos": [0, len("iso/picture.iso"), len("latest")], "error": ""}
        self.screen = "form"
        self.scroll = 0
        self.message = ""

    def _form_insert(self, char: str):
        field = self.form["field"]
        value, pos = self.form["values"][field], self.form["pos"][field]
        self.form["values"][field] = value[:pos] + char + value[pos:]
        self.form["pos"][field] = pos + 1
        self.form["error"] = ""

    def _form_change(self, key: str):
        field = self.form["field"]
        value, pos = self.form["values"][field], self.form["pos"][field]
        if key == "left":
            pos = max(0, pos - 1)
        elif key == "right":
            pos = min(len(value), pos + 1)
        elif key == "home":
            pos = 0
        elif key == "end":
            pos = len(value)
        elif key == "backspace" and pos > 0:
            value = value[:pos - 1] + value[pos:]
            pos -= 1
        elif key == "delete" and pos < len(value):
            value = value[:pos] + value[pos + 1:]
        self.form["values"][field] = value
        self.form["pos"][field] = pos
        self.form["error"] = ""

    def _complete_picture(self):
        raw = clean_path(self.form["values"][0])
        directory, prefix = os.path.split(raw)
        base = directory or "."
        try:
            names = os.listdir(base)
        except OSError:
            self.form["error"] = tr("That folder does not exist.")
            return
        matches = []
        for name in names:
            if not name.startswith(prefix):
                continue
            full = os.path.join(base, name)
            if name.lower().endswith(IMAGE_SUFFIXES) or os.path.isdir(full):
                matches.append(name)
        if not matches:
            self.form["error"] = tr("No picture or folder starts with that.")
            return
        if len(matches) == 1:
            new = os.path.join(directory, matches[0]) if directory else matches[0]
            if os.path.isdir(os.path.join(base, matches[0])):
                new += os.sep
            self.form["values"][0] = new
            self.form["pos"][0] = len(new)
            self.form["error"] = ""
            return
        common = os.path.commonprefix(matches)
        if len(common) > len(prefix):
            new = os.path.join(directory, common) if directory else common
            self.form["values"][0] = new
            self.form["pos"][0] = len(new)
        self.form["error"] = tr("{n} matches; keep typing.").format(n=len(matches))

    def _form_run(self):
        picture = clean_path(self.form["values"][0])
        if not picture:
            self.form["error"] = tr("Choose a picture first.")
            return None
        if not os.path.isfile(picture):
            self.form["error"] = tr("That picture does not exist: {path}").format(path=picture)
            return None
        output = clean_path(self.form["values"][1]) or "iso/picture.iso"
        geometry = self.form["values"][2].strip() or "latest"
        if geometry != "latest":
            geometry = clean_path(geometry) or "latest"
        argv = ["image"]
        if self.plan.media != "dvd":
            argv += ["--media", self.plan.media]
        argv += ["--geo", geometry, "--picture", picture, "--output", output]
        self.form = None
        self.screen = "step"
        return ("run", argv)

    # -- mouse -----------------------------------------------------------------------------------

    def _mouse(self, token: str):
        try:
            _, bits, x, y, final = token.split(":")
            bits, x, y = int(bits), int(x), int(y)
        except ValueError:
            return None
        if bits & 64:
            step = -1 if (bits & 3) == 0 else 1
            if self.screen == "home":
                self.row = max(0, min(len(self.plan.tasks) - 1, self.row + step))
            elif self.screen == "palette":
                rows = self._palette_rows()
                self.row = max(0, min(max(0, len(rows) - 1), self.row + step))
            else:
                self.scroll = max(0, self.scroll + step)
            return None
        if final != "M" or (bits & 3) != 0:
            return None
        for line, x1, x2, key in self._zones:
            if line == y - 1 and x1 <= x - 1 < x2:
                return self.handle(key)
        index = self._hits.get(y - 1)
        if index is None:
            return None
        if self.screen == "home" and index < len(self.plan.tasks):
            self.row = index
            self._open_step()
        elif self.screen == "palette":
            rows = self._palette_rows()
            if index < len(rows):
                self.row = index
                self._open_help(rows[index][0])
        return None

    # -- drawing ---------------------------------------------------------------------------------

    def draw(self) -> None:
        lines = self.text()
        body = "\n".join(fit_line(line, self.width) for line in lines)
        start = ui.SYNC_START if getattr(self.t, "sync", False) else ""
        end = ui.SYNC_END if start else ""
        self.t.stream.write(start + "\x1b[H\x1b[J" + body + "\x1b[0m" + end)
        self.t.stream.flush()

    def text(self, width: int | None = None, height: int | None = None) -> list[str]:
        if width:
            self.width = width
        if height:
            self.height = height
        self._hits = {}
        self._zones = []
        self._pending_zones = []
        if self.screen == "step":
            return self._step_screen()
        if self.screen == "palette":
            return self._palette_screen()
        if self.screen == "command":
            return self._command_screen()
        if self.screen == "edit":
            return self._edit_screen()
        if self.screen == "form":
            return self._form_screen()
        if self.screen == "keys":
            return self._keys_screen()
        return self._home()

    def _chip(self, text: str) -> str:
        return filled(text, self.t, self.plan.media)

    def _keycap(self, text: str) -> str:
        return filled(text, self.t, self.plan.media, neutral=True)

    def _link(self, text: str, url: str) -> str:
        return hyperlink(text, url, self.t)

    def _selection(self, text: str) -> str:
        if not self.t.color:
            return text
        room = max(0, self.width - width_of(text))
        return filled(text + " " * room, self.t, self.plan.media)

    def _header(self) -> str:
        left = self.t.style("disc-probe", "bold") + "  " + self.t.style(tr("guided console"), "dim")
        done = sum(1 for task in self.plan.tasks if task.done)
        total = len(self.plan.tasks)
        status = tr("{done} of {total} steps done").format(done=done, total=total)
        right = self._chip(self.plan.media.upper()) + "  " + self.t.style(status, "dim")
        folder = os.path.basename(os.path.abspath(self.out)) or self.out
        if self.width >= 72 and folder:
            shown = self.t.style(folder + ("/" if not folder.endswith("/") else ""), "dim")
            right += "  " + self._link(shown, path_url(self.out))
        if width_of(left) + width_of(right) + 1 > self.width:
            right = self._chip(self.plan.media.upper()) + "  " + self.t.style(status, "dim")
        if width_of(left) + width_of(right) + 1 <= self.width:
            return left + " " * (self.width - width_of(left) - width_of(right)) + right
        return left

    def _task_line(self, task, selected: bool) -> str:
        name, detail = tr(task.name), tr(task.detail)
        tick = "[x]" if task.done else "[ ]"
        marker = ">" if selected else " "
        if self.width < 64:
            raw = "  " + marker + " " + tick + " " + name + ": " + detail
            return self._selection(raw) if selected and self.t.color else raw
        padded = i18n.pad(name, 24)
        raw = "  " + marker + " " + tick + " " + padded + " " + detail
        if selected and self.t.color:
            return self._selection(raw)
        if not self.t.color:
            return raw
        tick_style = self.t.style(tick, "green" if task.done else "dim")
        return "  " + marker + " " + tick_style + " " + padded + " " + self.t.style(detail, "dim")

    def _detail_block(self, task, compact: bool = False) -> list[str]:
        lines = [] if compact else ["  " + self.t.style(tr(task.name), "bold") + "  " + self.t.style(tr(task.detail), "dim")]
        if task is self.plan.current():
            lines.append("  " + self._chip(tr("you are here")))
        wrap = max(20, self.width - 4)
        if task.why and (not compact or self.height >= 22):
            lines += ["  " + part for part in i18n.wrap(tr(task.why), wrap)]
        lines.append("  " + self.t.style(tr("Takes:") + " " + tr(task.takes), "dim"))
        command = task.command()
        if task.action in ("run", "shell") and command:
            prefix = "" if compact else self._keycap("Enter") + " "
            lines += ["", "  " + prefix + ui.command(command, self.t)]
        elif task.action == "form":
            lines += ["", "  " + self.t.style(tr("Enter opens the picture form."), "dim")]
        elif task.action == "burn":
            lines += ["", "  " + self.t.style(tr("Done with your disc burner; open the step for the steps."), "dim")]
        return lines

    def _commit_zones(self, top: int, footer_line: int, footer_text: str) -> None:
        """Turn the buttons and footer keycaps into click targets for this frame."""
        self._zones = [(line - top, x1, x2, key) for line, x1, x2, key in self._pending_zones
                       if top <= line < top + footer_line]
        self._pending_zones = []
        self._footer_zones(footer_line, footer_text)

    def _footer_zones(self, line_index: int, footer_text: str) -> None:
        # The footer is already the last line of the frame, so its tokens are the clickable keys.
        line = visible(footer_text)
        mapping = {"Enter": "enter", "Enter/r": "enter", "Esc": "esc", "Tab": "tab",
                   "PgUp": "pgup", "PgDn": "pgdn", "r": "r", "e": "e", "c": "c",
                   "m": "m", "l": "l", "o": "o", "q": "q", "?": "?", ":": ":"}
        for match in KEYCAP_RE.finditer(line):
            key = mapping.get(match.group(0))
            if key is None:
                continue
            start = i18n.display_width(line[:match.start()])
            end = start + i18n.display_width(match.group(0))
            self._zones.append((line_index, start, end, key))

    def _button_line(self, index: int, buttons) -> str:
        line, pos = "", 0
        for label, key in buttons:
            if line:
                line += "   "
                pos += 3
            start = pos
            shown = self._keycap(tr(label))
            line += shown
            pos += width_of(shown)
            self._pending_zones.append((index, start, pos, key))
        return line

    def _task_buttons(self, task):
        first = ("Run", "r") if task.action in ("run", "shell") else ("Open", "enter")
        buttons = [first]
        if task.command():
            buttons.append(("Copy", "c"))
        if task.action == "run":
            buttons.append(("Edit", "e"))
        return buttons

    def _foot(self, text: str, extra: str = "") -> str:
        text = tr(text)
        if extra:
            text += "   " + tr(extra)
        if not self.t.color:
            return text
        parts, start = [], 0
        for match in KEYCAP_RE.finditer(text):
            if match.start() > start:
                parts.append(self.t.style(text[start:match.start()], "dim"))
            parts.append(self._keycap(match.group(0)))
            start = match.end()
        if start < len(text):
            parts.append(self.t.style(text[start:], "dim"))
        return "".join(parts)

    def _finish(self, lines: list[str], footer: str) -> list[str]:
        lines = list(lines)
        if len(lines) >= self.height:
            lines = lines[:self.height - 1]
        lines += [""] * (self.height - 1 - len(lines))
        footer_line = self._foot(footer)
        lines.append(footer_line)
        self._commit_zones(0, len(lines) - 1, footer_line)
        return lines

    def _scrolled(self, lines: list[str], footer: str) -> list[str]:
        room = max(1, self.height - 1)
        more = len(lines) > room
        if more:
            top = max(0, min(self.scroll, len(lines) - room))
            self.scroll = top
            view = list(lines[top:top + room])
        else:
            top = 0
            self.scroll = 0
            view = list(lines)
        view += [""] * max(0, room - len(view))
        footer_line = self._foot(footer, "[more]" if more else "")
        view.append(footer_line)
        self._commit_zones(top, len(view) - 1, footer_line)
        return view

    def _home(self) -> list[str]:
        lines = [self._header(), ""]
        for index, task in enumerate(self.plan.tasks):
            self._hits[len(lines)] = index
            lines.append(self._task_line(task, index == self.row))
        lines.append("")
        if self.height >= 18:
            lines += self._detail_block(self.plan.tasks[self.row], compact=True)
        if self.height >= 12:
            lines += ["", self._button_line(len(lines) + 1, self._task_buttons(self.plan.tasks[self.row]))]
        if self.message:
            lines += ["", "  " + self.t.style(self.message, "yellow")]
        final = self._finish(lines, FOOTER_HOME)
        self._hits = {row: index for row, index in self._hits.items() if row < len(final) - 1}
        return final

    def _step_screen(self) -> list[str]:
        task = self.task()
        lines = [self._header(), "", self._task_line(task, True), "", *self._detail_block(task)]
        lines += ["", self._button_line(len(lines) + 1, self._task_buttons(task) + [("Back", "esc")])]
        if self.plan.media == "bd" and task.key in ("picture", "burn"):
            lines += [""]
            for note in ("This preset carries the shape of the spiral, not its scale: the pitch is the 0.3200 um prior "
                         "and the inner radius rides on a timing offset the fit cannot see.",
                         "Do not burn a picture with it yet. Calibrate against the disc first: one BD-R and one look at "
                         "the edge is 106 turns of difference on a real disc (docs/MANUAL.md)."):
                lines += ["  " + part for part in i18n.wrap(tr(note), max(20, self.width - 4))]
        if task.action == "burn":
            output = self.plan.picture if task.key == "burn" and self.plan.picture else self.plan.random_iso
            hints = guide.burn_steps(output, self.plan.media)
            if hints:
                lines += [""] + ["  " + self.t.style(tr(line), "dim") for line in hints]
            if task.key == "burn":
                lines += [""]
                for index, line in enumerate(guide.AFTER_BURN):
                    text = tr(line)
                    lines.append("  " + (self.t.style(text, "bold") if index == 0 else text))
        if self.message:
            lines += ["", "  " + self.t.style(self.message, "yellow")]
        if self.width >= 70:
            manual_name = "docs/MANUAL.md" if i18n.active() == "zh" else "docs/MANUAL.en.md"
            lines += ["", "  " + self._link(tr("The manual is {name}.").format(name=manual_name),
                                            path_url(manual_path()))]
        if task.action in ("run", "shell"):
            footer = FOOTER_STEP
        elif task.action == "form":
            footer = FOOTER_FORM_STEP
        else:
            footer = FOOTER_BACK
        return self._scrolled(lines, footer)

    def _palette_screen(self) -> list[str]:
        rows = self._palette_rows()
        if rows:
            self.row = min(max(0, self.row), len(rows) - 1)
        head = [self._header(), ""]
        head.append("  " + self._chip(tr("All commands")) + "   " + self.t.style(tr("type to filter"), "dim"))
        head.append("  > " + self._field(self.query, self.query_pos, max(8, self.width - 6), True))
        head.append("")
        room = max(1, self.height - len(head) - 1)
        if not rows:
            body = ["  " + self.t.style(tr("No command matches."), "dim")]
        else:
            if self.row < self.scroll:
                self.scroll = self.row
            if self.row >= self.scroll + room:
                self.scroll = self.row - room + 1
            self.scroll = max(0, min(self.scroll, max(0, len(rows) - room)))
            body = []
            for offset, (name, description) in enumerate(rows[self.scroll:self.scroll + room]):
                index = self.scroll + offset
                self._hits[len(head) + offset] = index
                marker = ">" if index == self.row else " "
                if index == self.row and self.t.color:
                    body.append(self._selection("  " + marker + " " + i18n.pad(name, 14) + " " + tr(description)))
                else:
                    shown = self.t.style(name, "cyan") if self.t.color else name
                    shown += " " * max(0, 14 - i18n.display_width(name))
                    body.append("  " + marker + " " + shown + " " + tr(description))
        lines = head + body
        lines += [""] * max(0, self.height - 1 - len(lines))
        footer_line = self._foot(FOOTER_PALETTE)
        lines.append(footer_line)
        self._hits = {row: index for row, index in self._hits.items() if row < len(lines) - 1}
        self._commit_zones(0, len(lines) - 1, footer_line)
        return lines

    def _command_screen(self) -> list[str]:
        description = next((text for name, text in self.commands if name == self.help_name), "")
        lines = [self._header(), "", "  " + self._chip(self.help_name)]
        if description:
            lines.append("  " + self.t.style(tr(description), "dim"))
        lines.append("")
        lines += ["  " + line for line in self.help_lines]
        manual_name = "docs/MANUAL.md" if i18n.active() == "zh" else "docs/MANUAL.en.md"
        lines += ["", "  " + self._link(tr("The manual is {name}.").format(name=manual_name),
                                       path_url(manual_path()))]
        return self._scrolled(lines, FOOTER_HELP)

    def _edit_screen(self) -> list[str]:
        lines = [self._header(), "", "  " + self._chip(tr("Edit the command")), "",
                 "  " + self.t.style(tr("This is the line that will run. Enter runs it; Esc goes back."), "dim"),
                 "", "  " + self._field(self.edit_text, self.edit_pos, max(10, self.width - 4), True)]
        if self.message:
            lines += ["", "  " + self.t.style(self.message, "yellow")]
        return self._finish(lines, FOOTER_EDIT)

    def _form_screen(self) -> list[str]:
        form = self.form
        labels = (tr("Picture"), tr("Output ISO"), tr("Geometry"))
        hints = (tr("Drop the picture into this window, or type its path. Tab completes a path."),
                 tr("Where the ISO is written. Relative paths are inside the project folder."),
                 tr("`latest` uses the newest complete measurement, or give a results file."))
        lines = [self._header(), "", "  " + self._chip(tr("Make a picture ISO")), ""]
        for index, label in enumerate(labels):
            active = index == form["field"]
            marker = ">" if active else " "
            shown = self._field(form["values"][index], form["pos"][index], max(10, self.width - 8), active)
            title = self._chip(label) if active else self.t.style(label, "dim")
            lines.append("  " + marker + " " + title)
            lines.append("    " + shown)
            if active:
                lines.append("    " + self.t.style(hints[index], "dim"))
        if form.get("error"):
            lines += ["", "  " + filled(form["error"], self.t, self.plan.media, danger=True)]
        lines += ["", "  " + self.t.style(tr("Enter on the last field runs it."), "dim")]
        return self._finish(lines, FOOTER_FORM)

    def _keys_screen(self) -> list[str]:
        lines = [self._header(), ""]
        if self.height >= 30 and self.width >= 80:
            try:
                lines += banner.frame(0.0, self.t, self.width, media=self.plan.media)
                lines.append("")
            except Exception:
                pass
        lines.append("  " + self.t.style(tr("Keys and gestures"), "bold"))
        lines.append("")
        manual_name = "docs/MANUAL.md" if i18n.active() == "zh" else "docs/MANUAL.en.md"
        lines.append("  " + self._link(tr("The manual is {name}.").format(name=manual_name),
                                      path_url(manual_path())))
        lines.append("  " + self.t.style(tr("Ctrl+click a link (Cmd+click on macOS) to open it."), "dim"))
        lines.append("")
        pairs = [("Up/Down, j/k", "move between steps"),
                 ("Enter, right", "open the step"),
                 ("r", "run the step"),
                 ("e", "edit the command"),
                 ("c", "copy the command"),
                 (":", "all commands, with a filter"),
                 ("m", "switch disc type (DVD, CD, BD)"),
                 ("l", "switch language"),
                 ("o", "open the results folder"),
                 ("?", "this screen"),
                 ("Esc", "go back"),
                 ("q", "quit")]
        for left, right in pairs:
            key_text = tr(left)
            gap = max(2, 18 - width_of(key_text))
            lines.append("  " + self._keycap(key_text) + " " * gap + "  " + tr(right))
        lines += ["",
                  "  " + " ".join(i18n.wrap(tr("The console runs ordinary disc-probe commands. It prints each command before running it, so the command line can be learned by watching."), max(20, self.width - 4))),
                  "",
                  "  " + " ".join(i18n.wrap(tr("During a measurement, press g for a game; the run is not disturbed."), max(20, self.width - 4))),
                  "",
                  "  " + " ".join(i18n.wrap(tr("For scripts and pipes the plain version is: python -m discprobe guide"), max(20, self.width - 4)))]
        if self.mouse:
            lines += ["", "  " + " ".join(i18n.wrap(tr("Mouse: click a step, a button or a footer key; the wheel moves through the list."), max(20, self.width - 4)))]
        return self._scrolled(lines, FOOTER_KEYS)

    def _field(self, text: str, pos: int, width: int, active: bool) -> str:
        text = text or ""
        if not active:
            return i18n.fit(text, width)
        pos = max(0, min(pos, len(text)))
        start = 0
        while start < pos and i18n.display_width(text[start:pos]) > width - 1:
            start += 1
        before = text[start:pos]
        after = text[pos:]
        block = after[0] if after else " "
        if not getattr(self.t, "ansi", False):
            return i18n.fit(text[:pos] + "|" + text[pos:], width)
        room = max(0, width - i18n.display_width(before) - i18n.display_width(block))
        tail = []
        used = 0
        for char in after[1:]:
            size = i18n.display_width(char)
            if used + size > room:
                break
            tail.append(char)
            used += size
        return before + "\x1b[7m" + block + "\x1b[0m" + "".join(tail)


# --- running ------------------------------------------------------------------------------------

def run(media: str = "dvd", out: str = "results", prelude=None, intro: str | None = None) -> bool:
    """Open the guided console. Without a terminal or keys it falls back to plain lines."""
    t = ui.term()
    if not t.interactive or not t.can_prompt():
        for line in guide.guide_lines(media, out, notes=False):
            print(ui.guide_line(line, t))
        return False
    plan = guide.workflow(media, out, notes=True)
    # Keep the opening disc animation the bare `discprobe` command always had. It plays on the
    # normal screen; the console then takes over the alternate screen.
    steps = plan.tasks
    burned = min(sum(task.done for task in steps) / max(len(steps) - 1, 1), 1.0)
    banner.show(t, burned=burned, media=media)
    if prelude is not None:
        # The greeting, first-run tutorial offer and completion hint that `guide` prints.
        prelude()
    commands: list[tuple[str, str]] = []
    builder = None
    try:
        parser, groups = _default_builder()
        builder = _default_builder
        commands = _command_rows(parser, groups)
    except Exception:
        pass
    if not t.ansi:
        _numbered(plan, t)
        return False
    keys = _open_keys()
    if keys is None:
        _numbered(plan, t)
        return False
    console = Console(plan, commands, t=t, builder=builder, out=out,
                      mouse=getattr(keys, "mouse", sys.platform != "win32"))
    if intro:
        console.message = intro
    try:
        while True:
            size = shutil.get_terminal_size((80, 24))
            console.width, console.height = size.columns, size.lines
            with _Screen(t, keys, console.mouse):
                console.draw()
                action = _events(console, keys)
            if action is None:
                break
            kind, value = action
            if kind == "quit":
                break
            if kind == "run":
                _run_command(value, t)
                console.refresh()
            elif kind == "shell":
                _run_shell(value, t)
                console.refresh()
            elif kind == "copy":
                console.copy(value)
            elif kind == "open":
                if _open_path(value):
                    console.message = tr("Opened {path}.").format(path=value)
                else:
                    console.message = tr("Could not open {path}.").format(path=value)
    except KeyboardInterrupt:
        pass
    finally:
        keys.close()
    return True


def _events(console: Console, keys):
    while True:
        changed = False
        for key in keys.read(0.25):
            action = console.handle(key)
            if action is not None:
                return action
            changed = True
        size = shutil.get_terminal_size((80, 24))
        if (size.columns, size.lines) != (console.width, console.height):
            console.width, console.height = size.columns, size.lines
            changed = True
        if changed:
            console.draw()


def _run_command(argv: list[str], t) -> None:
    print()
    print(ui.command(command_text(argv), t))
    print()
    from . import __main__ as cli
    try:
        cli.main(list(argv))
    except SystemExit as exit:
        if isinstance(exit.code, str) and exit.code:
            print(exit.code, file=sys.stderr)
    _pause()


def _run_shell(line: str, t) -> None:
    print()
    print(ui.command(line, t))
    print()
    argv = split_args(line)
    if argv and argv[0] in ("python", "python3"):
        argv[0] = sys.executable
    try:
        subprocess.call(argv)
    except OSError as error:
        print(tr("Could not run it: {error}").format(error=error), file=sys.stderr)
    _pause()


def _pause() -> None:
    try:
        input(tr("Press Enter to return to the guided console. "))
    except (EOFError, KeyboardInterrupt):
        pass


def console_copy(text: str, t) -> bool:
    """Put the command on the clipboard: the terminal first, the system clipboard as well."""
    wrote = False
    if sys.platform == "win32":
        wrote = _windows_copy(text)
    else:
        for name, extra in (("wl-copy", []), ("xclip", ["-selection", "clipboard"]),
                            ("xsel", ["--clipboard", "--input"]), ("pbcopy", [])):
            path = shutil.which(name)
            if not path:
                continue
            try:
                subprocess.run([path, *extra], input=text.encode("utf-8"), timeout=2, check=False)
                wrote = True
                break
            except (OSError, subprocess.SubprocessError):
                continue
    sent = False
    try:
        payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
        t.stream.write("\x1b]52;c;" + payload + "\x07")
        t.stream.flush()
        sent = True
    except (OSError, ValueError):
        pass
    return wrote or sent


def _windows_copy(text: str) -> bool:
    """The Win32 clipboard, for terminals whose OSC 52 is ignored (Windows Terminal may)."""
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE
        for _ in range(5):
            if user32.OpenClipboard(None):
                break
            time.sleep(0.02)
        else:
            return False
        try:
            user32.EmptyClipboard()
            data = text.encode("utf-16-le") + b"\x00\x00"
            handle = kernel32.GlobalAlloc(0x0002, len(data))
            if not handle:
                return False
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                kernel32.GlobalFree(handle)
                return False
            ctypes.memmove(pointer, data, len(data))
            kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(13, handle):
                kernel32.GlobalFree(handle)
                return False
            return True
        finally:
            user32.CloseClipboard()
    except Exception:
        # The clipboard is a convenience: a missing permission or DLL must not stop the console.
        return False


def _open_path(path: str) -> bool:
    path = os.path.abspath(os.path.expanduser(path))
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        return False
    try:
        if sys.platform == "win32":
            os.startfile(path)
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
            return True
        opener = shutil.which("xdg-open")
        if opener:
            subprocess.Popen([opener, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    except OSError:
        pass
    return False


def _numbered(plan, t) -> int:
    """The same steps for a terminal without keys: numbers, plain questions, no screen tricks."""
    for line in guide.guide_lines(plan.media, plan.out, notes=True):
        print(ui.guide_line(line, t))
    while True:
        current = plan.current() or plan.tasks[0]
        default = plan.tasks.index(current) + 1
        try:
            answer = input(tr("Step number to open (Enter for {n}, q to quit): ").format(n=default)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if answer.lower() in ("q", "quit"):
            return 0
        try:
            index = (int(answer) if answer else default) - 1
        except ValueError:
            continue
        if not 0 <= index < len(plan.tasks):
            continue
        task = plan.tasks[index]
        print()
        print(t.style(tr(task.name), "bold") + "  " + t.style(tr(task.detail), "dim"))
        if task.why:
            for part in i18n.wrap(tr(task.why), 78):
                print(part)
        print(tr("Takes:") + " " + tr(task.takes))
        command = task.command()
        if command:
            print(ui.command(command, t))
        if task.action == "burn":
            for line in guide.burner_hint():
                print(tr(line))
            if task.key == "burn":
                for line in guide.AFTER_BURN:
                    print(tr(line))
        elif task.action in ("run", "shell"):
            if ui.ask(tr("Run it now?"), True):
                if task.action == "shell":
                    _run_shell(command, t)
                else:
                    _run_command(list(task.argv), t)
                plan = guide.workflow(plan.media, plan.out, notes=True)
        elif task.action == "form":
            picture = input(tr("Picture file: ")).strip()
            if not picture:
                continue
            output = input(tr("Output ISO [iso/picture.iso]: ")).strip() or "iso/picture.iso"
            geometry = input(tr("Geometry [latest]: ")).strip() or "latest"
            argv = ["image"]
            if plan.media != "dvd":
                argv += ["--media", plan.media]
            argv += ["--geo", geometry, "--picture", clean_path(picture), "--output", clean_path(output)]
            if ui.ask(tr("Run it now?"), True):
                _run_command(argv, t)
                plan = guide.workflow(plan.media, plan.out, notes=True)
        print()
        for line in guide.progress_lines(plan.media, plan.out):
            print(ui.guide_line(line, t))
