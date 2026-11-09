"""Tests for the guided console: key decoding, command lines, screens, forms and the menu entry.

The console is a plain state machine, so most of it can be tested without a terminal: fake keys go
in, screens and actions come out. Only the escape-sequence wrapper needs a fake stream.
"""

from __future__ import annotations

import io
import os
import tempfile

from . import console, guide, i18n


class FakeTerm:
    def __init__(self):
        self.stream = io.StringIO()
        self.color = False
        self.ansi = True
        self.sync = False
        self.interactive = True
        self.truecolor = False
        self.blocks = False
        self.unicode = False
        self.green = False
        self.taskbar = False

    def style(self, text, name="bold"):
        return text

    def can_prompt(self):
        return True


class FakeKeys:
    def __init__(self):
        self.resumed = 0
        self.paused = 0
        self.closed = 0

    def resume(self):
        self.resumed += 1

    def pause(self):
        self.paused += 1

    def close(self):
        self.closed += 1

    def read(self, timeout=0.25):
        return []


def _screen(c, width, height):
    return [console.visible(line) for line in c.text(width, height)]


def _keys(c):
    keys, rest = console.parse_keys(b"\x1b[A\x1b[<0;10;5M\x1b[200~hi\x1b[201~abc")
    c.check(keys == ["up", "mouse:0:10:5:M", "paste:hi", "a", "b", "c"], "keys: arrows, mouse and paste decode")
    c.check(rest == b"", "keys: no bytes are left over")
    keys, rest = console.parse_keys(b"\x1b[")
    c.check(keys == [] and rest == b"\x1b[", "keys: an incomplete CSI sequence stays buffered")
    keys, rest = console.parse_keys("\u76d8".encode("utf-8"))
    c.check(keys == ["\u76d8"] and rest == b"", "keys: UTF-8 text arrives as one character")
    keys, _ = console.parse_keys(b"\r\t\x7f\x03")
    c.check(keys == ["enter", "tab", "backspace", "ctrl-c"], "keys: control bytes become names")
    keys, _ = console.parse_keys(b"\x1b[<64;10;5M")
    c.check(keys == ["mouse:64:10:5:M"], "keys: the wheel is a mouse event")


def _lines(c):
    c.check(console.split_args(r'"C:\my file.png" --output=iso/x.iso') ==
            [r"C:\my file.png", "--output", "iso/x.iso"], "lines: a quoted Windows path is one argument")
    c.check(console.split_args('--picture="a b.png"') == ["--picture", "a b.png"],
            "lines: --option=value splits into two arguments")
    c.check(console.split_args("image --geo latest") == ["image", "--geo", "latest"],
            "lines: plain words split on spaces")
    try:
        console.split_args('"open')
    except ValueError:
        closed = True
    else:
        closed = False
    c.check(closed, "lines: an unclosed quote is reported")
    c.check(console.clean_path('"file:///C:/my file.png"') == "C:/my file.png",
            "lines: quotes and file:// are not part of a dropped path")
    c.check(console.command_text(["image", "--picture", "my pic.png"]) ==
            'python -m discprobe image --picture "my pic.png"', "lines: a printed command quotes spaces")
    c.check(console.fuzzy_score("tim", "timing") is not None and
            console.fuzzy_score("tim", "timing") > console.fuzzy_score("ing", "timing"),
            "lines: a prefix outranks a later match")
    c.check(console.fuzzy_score("zzz", "timing") is None, "lines: missing letters do not match")


def _workflow(c, folder):
    plan = guide.workflow("cd", folder, notes=True)
    c.check([task.key for task in plan.tasks] ==
            ["packages", "drive", "disc", "timing", "geo", "picture", "burn"],
            "workflow: the seven steps, in order")
    c.check(plan.tasks[0].action == "shell" and plan.tasks[0].shell == guide.INSTALL,
            "workflow: packages install in a shell")
    c.check(plan.tasks[1].action == "run" and plan.tasks[1].argv == ["list"],
            "workflow: the drive step lists drives")
    c.check(plan.tasks[5].action == "form" and plan.tasks[5].form == "image",
            "workflow: the picture step opens the form")
    c.check(plan.tasks[6].action == "burn", "workflow: the last step is a burn")
    c.check(plan.tasks[3].argv is not None and "--media" in plan.tasks[3].argv and
            "cd" in plan.tasks[3].argv, "workflow: a CD plan passes --media cd")
    bd_plan = guide.workflow("bd", folder, notes=True)
    c.check(bd_plan.tasks[3].argv is not None and "bd" in bd_plan.tasks[3].argv,
            "workflow: a Blu-ray plan passes --media bd")
    c.check(bd_plan.tasks[4].argv is not None and "--bd-zones" in bd_plan.tasks[4].argv,
            "workflow: the Blu-ray geometry step asks for zones")
    c.check(plan.current() is not None and not plan.current().done, "workflow: the current step is the first undone")


def _commands(c):
    from . import __main__ as cli
    parser, sub, _defaults = cli._build_parser()
    rows = console._command_rows(parser, cli.COMMAND_GROUPS)
    names = [name for name, _ in rows]
    c.check("menu" not in names, "commands: menu is not offered inside the console")
    c.check(names and names[0] == "guide" and "cdprobe" in names, "commands: the palette follows the grouped order")
    c.check("menu" in sub.choices and bool(sub.choices["menu"].description), "commands: the menu parser exists")
    menu_media = next((action for action in sub.choices["menu"]._actions if action.dest == "menu_media"), None)
    c.check(menu_media is not None and tuple(menu_media.choices) == ("dvd", "cd", "bd"),
            "commands: the menu parser takes --media dvd/cd/bd")


def _console(c, folder):
    plan = guide.workflow("dvd", folder, notes=True)
    commands = [("timing", "Measure the drive timing"), ("geo", "Measure the spiral geometry")]
    term = FakeTerm()
    c_fake = console.Console(plan, commands, t=term, out=folder)
    current = plan.current()
    expected = plan.tasks.index(current) if current is not None else 0
    c.check(c_fake.screen == "home" and c_fake.row == expected, "console: starts on the current step")

    home = _screen(c_fake, 100, 30)
    c.check(len(home) == 30 and home[-1].startswith("Up/Down move"), "console: a 100x30 home has a footer")
    c.check(any("guided console" in line for line in home), "console: the header names the console")
    c.check(len(_screen(c_fake, 80, 24)) == 24 and len(_screen(c_fake, 40, 12)) == 12,
            "console: 80x24 and 40x12 still fill the screen")
    c_fake.text(100, 30)
    c.check(c_fake._hits.get(2) == 0, "console: the first task row is clickable")

    c_fake.handle("down")
    c_fake.handle("up")
    c_fake.handle("enter")
    c.check(c_fake.screen == "step", "console: Enter opens a step")
    c_fake.handle("esc")
    c.check(c_fake.screen == "home", "console: Esc returns home")

    c_fake.handle(":")
    c.check(c_fake.screen == "palette", "console: : opens the command palette")
    for char in "tim":
        c_fake.handle(char)
    rows = c_fake._palette_rows()
    c.check(rows and rows[0][0] == "timing", "console: the palette filters by name")
    c_fake.handle("enter")
    c.check(c_fake.screen == "command" and c_fake.help_name == "timing", "console: Enter opens command help")
    c_fake.handle("esc")
    c.check(c_fake.screen == "palette", "console: Esc leaves help for the palette")
    c_fake.handle("esc")
    c.check(c_fake.screen == "home", "console: Esc leaves the palette for where it opened")

    c_fake.handle("2")
    c.check(c_fake.screen == "step" and c_fake.row == 1, "console: a digit jumps to that step")
    action = c_fake.handle("r")
    c.check(action == ("run", ["list"]), "console: r runs the step command")
    c_fake.handle("esc")

    c_fake.row = 1
    action = c_fake.handle("e")
    c.check(action is None and c_fake.screen == "edit" and c_fake.edit_text.startswith(guide.PROG),
            "console: e edits the step command")
    action = c_fake.handle("enter")
    c.check(action == ("run", ["list"]), "console: Enter in the editor runs the edited command")
    c_fake.handle("esc")

    c_fake.row = 1
    action = c_fake.handle("c")
    c.check(action is not None and action[0] == "copy" and action[1].startswith(guide.PROG + " list"),
            "console: c copies the command")
    action = c_fake.handle("o")
    c.check(action is not None and action[0] == "open" and action[1] == os.path.abspath(folder),
            "console: o opens the results folder")
    c.check(c_fake.handle("ctrl-c") == ("quit", None), "console: Ctrl+C quits")

    c_fake.handle("?")
    c.check(c_fake.screen == "keys", "console: ? opens the key screen")
    c_fake.handle("esc")
    c.check(c_fake.screen == "home", "console: Esc leaves the key screen")

    c_fake.text(40, 12)
    c_fake.draw()
    drawn = c_fake.t.stream.getvalue()
    c.check(drawn.startswith("\x1b[H\x1b[J") and drawn.count("\n") == 11,
            "console: draw clears the screen and writes exactly the height")

    screen = FakeTerm()
    keys = FakeKeys()
    with console._Screen(screen, keys, mouse=True):
        c.check("\x1b[?1049h" in screen.stream.getvalue() and keys.resumed == 1,
                "console: the alternate screen is entered and keys resume")
    after = screen.stream.getvalue()
    c.check("\x1b[?1049l" in after and "\x1b[?1000l" in after and keys.paused == 1,
            "console: the alternate screen, mouse and keys are restored")
    c.check(console.width_of(console.fit_line("x" * 100, 20)) <= 20, "console: long lines fit the width")


def _form(c, folder):
    plan = guide.workflow("dvd", folder, notes=True)
    c_fake = console.Console(plan, [], t=FakeTerm(), out=folder)
    index = next(i for i, task in enumerate(plan.tasks) if task.key == "picture")
    c_fake.row = index
    c_fake.handle("enter")
    c_fake.handle("enter")
    c.check(c_fake.screen == "form" and c_fake.form is not None, "form: the picture step opens the form")

    missing = os.path.join(folder, "missing.png")
    for char in missing:
        c_fake.handle(char)
    c_fake.handle("enter")
    c_fake.handle("enter")
    action = c_fake.handle("enter")
    c.check(action is None and "does not exist" in c_fake.form["error"], "form: a missing picture is refused")

    c_fake._open_form()
    picture = os.path.join(folder, "picture one.png")
    with open(picture, "wb") as handle:
        handle.write(b"not a real picture, but the form only needs a file")
    for char in picture:
        c_fake.handle(char)
    c_fake.handle("enter")
    c_fake.handle("enter")
    action = c_fake.handle("enter")
    c.check(action is not None and action[0] == "run" and action[1][0] == "image",
            "form: a real picture becomes an image command")
    c.check(picture in action[1] and "--geo" in action[1] and "--output" in action[1],
            "form: the command carries the picture, geometry and output")
    c.check(c_fake.form is None and c_fake.screen == "step", "form: running closes the form")

    folder_with_one = os.path.join(folder, "one")
    os.makedirs(folder_with_one, exist_ok=True)
    open(os.path.join(folder_with_one, "poster.png"), "wb").close()
    c_fake._open_form()
    c_fake.form["values"][0] = folder_with_one + os.sep
    c_fake.form["pos"][0] = len(c_fake.form["values"][0])
    c_fake.handle("tab")
    c.check(c_fake.form["values"][0].endswith("poster.png"), "form: Tab completes a picture path")

    cd_plan = guide.workflow("cd", folder, notes=True)
    cd_console = console.Console(cd_plan, [], t=FakeTerm(), out=folder)
    cd_console.row = next(i for i, task in enumerate(cd_plan.tasks) if task.key == "picture")
    cd_console.handle("enter")
    cd_console.handle("enter")
    cd_console.form["values"][0] = picture
    cd_console.form["pos"][0] = len(picture)
    cd_console.form["field"] = 2
    action = cd_console.handle("enter")
    c.check(action is not None and "--media" in action[1] and "cd" in action[1],
            "form: a CD plan passes --media cd")

    bd_plan = guide.workflow("bd", folder, notes=True)
    bd_console = console.Console(bd_plan, [], t=FakeTerm(), out=folder)
    bd_console.row = next(i for i, task in enumerate(bd_plan.tasks) if task.key == "picture")
    bd_console.handle("enter")
    bd_console.handle("enter")
    bd_console.form["values"][0] = picture
    bd_console.form["pos"][0] = len(picture)
    bd_console.form["field"] = 2
    action = bd_console.handle("enter")
    c.check(action is not None and "--media" in action[1] and "bd" in action[1],
            "form: a Blu-ray plan passes --media bd")


def _language(c):
    from . import __main__ as cli
    i18n.use("en")
    try:
        parser, sub, _defaults = cli._build_parser()
        menu_en = sub.choices["menu"].description
        media_en = next(action.help for action in sub.choices["menu"]._actions if action.dest == "menu_media")

        plan = guide.workflow("dvd", os.path.join(tempfile.gettempdir(), "disc-probe-console-test"), notes=True)
        c_fake = console.Console(plan, [], t=FakeTerm(), out=plan.out)
        c_fake.toggle_language()
        c.check(i18n.active() == "zh", "language: l switches to Chinese")
        head = console.visible(c_fake.text(100, 30)[0])
        c.check("引导控制台" in head, "language: the header is translated")
        c_fake.toggle_language()
        c.check(i18n.active() == "en", "language: l switches back to English")

        i18n.use("zh")
        parser, sub, _defaults = cli._build_parser()
        menu_zh = sub.choices["menu"].description
        media_zh = next(action.help for action in sub.choices["menu"]._actions if action.dest == "menu_media")
        c.check(menu_zh and menu_zh != menu_en, "language: the menu description has a Chinese entry")
        c.check(media_zh and media_zh != media_en, "language: the menu option help has a Chinese entry")
        c.check("中文" in i18n.tr("Language: {name}").format(name="中文"), "language: translated messages encode")
    finally:
        i18n.use("en")
        os.environ.pop("DISCPROBE_LANG", None)


def run(c) -> None:
    print("guided console: key decoding, command lines, screens, forms, menu and Chinese")
    _keys(c)
    _lines(c)
    _commands(c)
    with tempfile.TemporaryDirectory() as folder:
        _workflow(c, folder)
        _console(c, folder)
        _form(c, folder)
    _language(c)
