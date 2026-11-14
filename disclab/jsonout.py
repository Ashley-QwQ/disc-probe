"""One structured response for CLI callers and future front ends."""
from __future__ import annotations

import argparse
import contextlib
from contextvars import ContextVar
import json
import math
from pathlib import Path
import sys

from .lab import Lab


_structured = ContextVar("disclab_structured", default=False)


def diagnostics_active():
    return _structured.get()


def response(lab=None, *, outputs=None, scores=None, errors=None):
    return dict(status="error" if errors else "ok", lab=str(Lab(lab).root) if lab else None,
                outputs=outputs or {}, scores=scores or {}, errors=errors or [])


def emit(value):
    def finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            return None
        if isinstance(item, dict):
            return {k: finite(v) for k, v in item.items()}
        if isinstance(item, (tuple, list)):
            return [finite(v) for v in item]
        return item
    print(json.dumps(finite(value), ensure_ascii=False, allow_nan=False, default=str), flush=True)


class Parser(argparse.ArgumentParser):
    """Keep parse failures in the same envelope, including before dispatch."""
    json_mode = False

    def error(self, message):
        if self.json_mode:
            self.print_usage(sys.stderr)
            emit(response(errors=[dict(type="ArgumentError", message=message)]))
            raise SystemExit(2)
        super().error(message)

    def print_help(self, file=None):
        if self.json_mode:
            super().print_help(sys.stderr)
            emit(response(outputs=dict(help=self.format_help())))
        else:
            super().print_help(file)


def configure(parser, sub):
    parser.add_argument("--json", action="store_true", help="one JSON response; diagnostics on stderr")
    for name, child in sub.choices.items():
        child.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                           help="one JSON response; diagnostics on stderr")
        child.set_defaults(command=name)


def last_step(lab, kind):
    for row in reversed(lab.state().get("steps", {}).get(kind, [])):
        if row.get("status") == "ok" and row.get("paths"):
            return row
    raise ValueError(f"first complete {kind} / 请先完成 {kind}")


def geo_folder(lab):
    for path in reversed(last_step(lab, "geo")["paths"]):
        p = Path(path)
        if p.name == "summary.json" and p.parent.name.startswith("geo-"):
            return p.parent
    raise ValueError("no geo summary / 没有 geo 结果")


def artifacts(args):
    """Paths named by a disc-probe invocation, without parsing its human log."""
    paths = []
    for flag in ("--output", "--out", "--run"):
        if flag in args and args.index(flag) + 1 < len(args):
            path = Path(args[args.index(flag) + 1]).resolve()
            if path.exists():
                paths.append(str(path))
                if path.is_file():
                    sidecar = path.with_suffix(".image.json")
                    if sidecar.exists():
                        paths.append(str(sidecar))
                else:
                    paths.extend(str(p) for p in sorted(path.glob("*/summary.json")))
                    paths.extend(str(p) for p in sorted(path.glob("*.json")))
    return list(dict.fromkeys(paths))


def record_dp(lab, args, code):
    args = list(map(str, args))
    if not args:
        return {}
    outputs = dict(argv=args, paths=artifacts(args), exit_code=code)
    drive = args[args.index("--drive") + 1] if "--drive" in args else None
    outputs["disc"] = lab.state().get("drives", {}).get(drive, {}).get("tray")
    lab.step(args[0], status="ok" if code == 0 else "error", **outputs)
    if args[0] == "photo" and "--run" in args:
        path = Path(args[args.index("--run") + 1]).resolve() / "photo.json"
        disc = args[args.index("--disc-id") + 1] if "--disc-id" in args else outputs["disc"]
        lab.step("photo_L", status="ok" if code == 0 else "error", disc=disc, paths=[str(path)])
    if args[0] == "image":
        lab.step("pictures", status="ok" if code == 0 else "error", **outputs)
    return outputs


def invoke(a):
    """The CLI and TUI dispatch through this function; no front-end state."""
    structured = getattr(a, "json", False)
    lab = Lab(a.lab) if getattr(a, "lab", None) else None
    result = response(a.lab if lab else None)
    code = 0
    token = _structured.set(structured or diagnostics_active())
    try:
        with contextlib.redirect_stdout(sys.stderr) if structured else contextlib.nullcontext():
            value = a.func(a)
        result["outputs"] = value if isinstance(value, dict) else dict(result=value) if value is not None else {}
        code = result["outputs"].get("exit_code", 0)
        if code:
            result.update(status="error", errors=[dict(type="CommandError", message=f"exit code {code}")])
    except (Exception, SystemExit, KeyboardInterrupt) as exc:
        if isinstance(exc, SystemExit) and (exc.code is None or exc.code == 0):
            pass
        else:
            code = (exc.code if isinstance(exc, SystemExit) and isinstance(exc.code, int) else
                    130 if isinstance(exc, KeyboardInterrupt) else 1)
            result.update(status="error", errors=[dict(type=type(exc).__name__, message=str(exc))])
            if not structured:
                print(str(exc), file=sys.stderr)
    finally:
        _structured.reset(token)
    lab = Lab(a.lab) if getattr(a, "lab", None) else None
    result["lab"] = str(lab.root) if lab else None
    if lab and lab.state_path.exists():
        try:
            result["scores"] = {p.stem: lab.read(p) for p in sorted((lab.root / "scores").glob("*.json"))}
            lab.step(a.command, status=result["status"], disc=getattr(a, "disc", None),
                     outputs=result["outputs"], errors=result["errors"])
        except Exception as exc:
            code = code or 1
            result.update(status="error", errors=result["errors"] + [dict(type=type(exc).__name__, message=str(exc))])
    if structured:
        emit(result)
    return result, code


def run(argv):
    """Run exactly the same parser/dispatcher from a prompt or another Python caller."""
    from .__main__ import main
    return main(list(map(str, argv)), return_response=True)
