"""Place a picture on the disc at the terminal: move it, size it, turn it, choose where grey turns dark.

`edit` opens it. It saves a small design file for `image --design` and never touches a drive. It draws only when a key
changes something, on a small disc at a few times its width in cells, so it stays cheap on a slow machine. Which
keys do what lives here with no terminal in it, like the result picker.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import time

from . import design as project_file
from . import i18n, imagecheck, snake, ui
from .i18n import tr

POLL_S = 0.03
SUPERSAMPLE = 4             # design cells per thumbnail pixel, so edges come out as shades
MIN_PIXELS = 24
PANEL_WIDTH = 36
MOST_UNDO = 200
# (move in mm, size in mm, turn in degrees, threshold, trim)
STEPS = {"coarse": (2.0, 2.0, 5.0, 0.05, 0.02), "fine": (0.2, 0.5, 0.5, 0.01, 0.005)}
EDGES = ("left", "right", "top", "bottom")      # the order c goes through them
# the key that hides more of an edge, the key that shows more
EDGE_KEYS = {"left": ("right", "left"), "right": ("left", "right"), "top": ("down", "up"), "bottom": ("up", "down")}
OPPOSITE = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}
LETTER_ARROWS = {"h": "left", "j": "down", "k": "up", "l": "right"}
ARROWS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0), "k": (0, -1), "j": (0, 1), "h": (-1, 0), "l": (1, 0)}


class Editor:
    def __init__(self, project: project_file.Project, sources: dict, t: ui.Term, r_min: float, r_max: float):
        self.project, self.sources, self.t = project, sources, t
        self.r_min, self.r_max = r_min, r_max
        self.layer = project.layers[-1]
        self.first = self.layer
        self.step = "coarse"
        self.edge = None        # which edge the arrows trim, or None when they move the picture
        self.undo: list[project_file.Layer] = []
        self.dirty = self.done = self.save = False
        self.warned = False
        self._drawn = None

    def _set(self, **changes) -> None:
        changed = project_file.clamped(dataclasses.replace(self.layer, **changes))
        if changed == self.layer:
            return
        self.undo = self.undo[-MOST_UNDO + 1:] + [self.layer]
        self._use(changed)
        self.dirty = True

    def _use(self, layer: project_file.Layer) -> None:
        self.project.layers[-1] = self.layer = layer

    def _trim(self, key: str, step: float) -> None:
        more, less = EDGE_KEYS[self.edge]
        key = LETTER_ARROWS.get(key, key)
        if key not in (more, less):
            return
        now = getattr(self.layer, f"trim_{self.edge}")
        room = project_file.MOST_TRIM - getattr(self.layer, f"trim_{OPPOSITE[self.edge]}")
        wanted = now + step if key == more else now - step
        self._set(**{f"trim_{self.edge}": round(min(max(wanted, 0.0), room), 3)})

    def handle(self, key: str) -> None:
        move, size, turn, level, trim = STEPS[self.step]
        leaving = self.warned
        self.warned = False
        lay = self.layer
        if key in ARROWS and self.edge:
            self._trim(key, trim)
        elif key in ARROWS:
            dx, dy = ARROWS[key]
            self._set(x_mm=round(lay.x_mm + dx * move, 3), y_mm=round(lay.y_mm + dy * move, 3))
        elif key in ("+", "="):
            self._set(size_mm=round(lay.size_mm + size, 3))
        elif key in ("-", "_"):
            self._set(size_mm=round(lay.size_mm - size, 3))
        elif key == "[":
            self._set(rotation_deg=round(lay.rotation_deg - turn, 3))
        elif key == "]":
            self._set(rotation_deg=round(lay.rotation_deg + turn, 3))
        elif key in (",", "<"):
            self._set(threshold=round(lay.threshold - level, 3))
        elif key in (".", ">"):
            self._set(threshold=round(lay.threshold + level, 3))
        elif key in ("i", "I"):
            self._set(invert=not lay.invert)
        elif key == "\t":
            self.step = "fine" if self.step == "coarse" else "coarse"
        elif key in ("a", "A"):
            found = project_file.auto_threshold(self.sources[lay.path], lay)
            if found is not None:
                self._set(threshold=found)
        elif key in ("c", "C"):
            self.edge = EDGES[EDGES.index(self.edge) + 1] if self.edge in EDGES[:-1] else None if self.edge else EDGES[0]
        elif key == "0":
            self._set(x_mm=0.0, y_mm=0.0, size_mm=project_file.DEFAULT_SIZE_MM, rotation_deg=0.0, threshold=0.5, invert=False,
                      trim_left=0.0, trim_top=0.0, trim_right=0.0, trim_bottom=0.0)
        elif key in ("u", "U"):
            if self.undo:
                self._use(self.undo.pop())
                self.dirty = self.layer != self.first or bool(self.undo)
        elif key in ("\r", "\n"):
            self.save = self.done = True
        elif key == "\x03" or (key in ("q", "Q", "\x1b") and (leaving or not self.dirty)):
            self.done = True
        elif key in ("q", "Q", "\x1b"):
            self.warned = True

    def _preview(self, pixels: int):
        state = (pixels, tuple(dataclasses.astuple(x) for x in self.project.layers))
        if self._drawn is None or self._drawn[0] != state:
            dark = project_file.render(self.project, pixels * SUPERSAMPLE, self.sources)
            self._drawn = state, dark, imagecheck.thumbnail(dark, self.r_min, self.r_max, self.t, pixels)
        return self._drawn[1], self._drawn[2]

    def panel(self, dark) -> list[str]:
        lay = self.layer
        lines = [os.path.basename(lay.path), ""]
        if len(self.project.layers) > 1:
            lines[1:1] = [tr(f"Editing the top one of {len(self.project.layers)} pictures")]
        lines += [tr(f"Position  {lay.x_mm:+.1f}, {lay.y_mm:+.1f} mm"),
                  tr(f"Size      {lay.size_mm:.1f} mm"),
                  tr(f"Turned    {lay.rotation_deg:+.1f} deg"),
                  tr(f"Dark below {lay.threshold * 100:.0f}% brightness"),
                  tr("Colours   swapped" if lay.invert else "Colours   as they are"),
                  tr("Steps     fine" if self.step == "fine" else "Steps     coarse")]
        if lay.trim_left or lay.trim_top or lay.trim_right or lay.trim_bottom:
            lines.append(tr(f"Trimmed   L {lay.trim_left * 100:.1f} R {lay.trim_right * 100:.1f} T {lay.trim_top * 100:.1f} B {lay.trim_bottom * 100:.1f}%"))
        if self.edge:
            lines.append(tr(f"Trimming the {self.edge} edge (c: next)"))
        lines.append("")
        if dark is not None:
            share, lost = project_file.coverage(dark, self.r_min, self.r_max)
            lines.append(tr(f"Dark {share * 100:.0f}% of the drawable part"))
            if lost >= 0.005:
                lines.append(tr(f"{lost * 100:.0f}% of the dark area is cut off"))
            lines.append("")
        lines += [tr("Arrows move  + - size  [ ] turn"), tr(", . grey line  a auto  i swap"),
                  tr("c trim  Tab steps  u undo  0 reset"), tr("Enter save  q leave")]
        if self.warned:
            lines += ["", tr("Not saved. q again to leave, Enter to save.")]
        return lines

    def lines(self, columns: int, rows: int) -> list[str]:
        width = max(10, columns - 1)
        beside = min(rows * 2, width - PANEL_WIDTH - 4)
        beside -= beside % 2
        if beside >= MIN_PIXELS:
            dark, thumb = self._preview(beside)
            panel = self.panel(dark)
            room = width - beside - 4
            count = min(rows, max(len(thumb), len(panel)))
            blank = " " * (beside + 2)
            return [(thumb[i] if i < len(thumb) else blank) + "  " + (i18n.fit(panel[i], room) if i < len(panel) else "")
                    for i in range(count)]
        panel = self.panel(None)
        above = min((rows - len(panel)) * 2, width - 2)
        above -= above % 2
        if above >= MIN_PIXELS:
            dark, thumb = self._preview(above)
            return thumb + [i18n.fit(line, width) for line in self.panel(dark)][:rows - len(thumb)]
        return [i18n.fit(line, width) for line in [tr("Make the window larger to see the disc."), *panel]][:rows]


def _draw(editor: Editor, t: ui.Term) -> None:
    size = shutil.get_terminal_size((100, 24))
    t.stream.write("\x1b[H" + "\x1b[K\n".join(editor.lines(size.columns, size.lines)) + "\x1b[K\x1b[J")
    t.stream.flush()


def start(file: str, output: str | None) -> tuple[project_file.Project, str]:
    """The project to open, and where it saves. A design file reopens; a picture carries on from its own design file."""
    if file.lower().endswith(".json"):
        return project_file.load(file), output or file
    if not os.path.isfile(file):
        raise ValueError(f"cannot read the picture {file}: there is no such file")
    path = output or os.path.splitext(os.path.basename(file))[0] + ".design.json"
    picture = os.path.abspath(file)
    if os.path.exists(path):
        found = project_file.load(path)
        if len(found.layers) == 1 and os.path.normcase(found.layers[0].path) == os.path.normcase(picture):
            return found, path
        if not output:
            raise ValueError(f"{path} already holds another design. Choose a new name with --output, or open it with: edit {path}")
    return project_file.Project([project_file.Layer(picture)]), path


def run(project: project_file.Project, output: str, r_min: float, r_max: float, t: ui.Term | None = None, keys=None, pause=time.sleep) -> bool:
    """True if a design was saved. Raises ValueError where nobody can press keys, or a picture can't be read."""
    t = t or ui.term()
    if not t.can_prompt() or not t.ansi:
        raise ValueError("edit needs a terminal. Without one: image --picture my_picture.png --diameter-mm 116")
    sources = {layer.path: project_file.read_source(layer.path, project_file.PREVIEW_SOURCE_PX) for layer in project.layers}
    keys = keys or snake.open_keys()
    if keys is None:
        raise ValueError("edit needs a terminal. Without one: image --picture my_picture.png --diameter-mm 116")
    editor = Editor(project, sources, t, r_min, r_max)
    t.stream.write("\x1b[?1049h\x1b[?25l")      # its own screen, so what was above is still there afterwards
    try:
        size = shutil.get_terminal_size((100, 24))
        _draw(editor, t)
        while not editor.done:
            pressed = keys.read()
            for key in pressed:
                editor.handle(key)
            now = shutil.get_terminal_size((100, 24))
            if (pressed or now != size) and not editor.done:
                size = now
                _draw(editor, t)
            pause(POLL_S)
    finally:
        t.stream.write("\x1b[?25h\x1b[?1049l")
        t.stream.flush()
        keys.close()
    if editor.save:
        project_file.save(project, output)
    return editor.save
