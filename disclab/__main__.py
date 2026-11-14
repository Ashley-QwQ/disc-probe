"""python -m disclab <command> --lab LAB ...

    box     make a box of discs (truth goes to LAB/answers.json)
    tray    put a disc into a lab drive (or --open to open the tray)
    dp      run a discprobe command against the lab: python -m disclab dp --lab LAB -- geo --drive X: ...
    env     print the environment a shell needs to run discprobe against the lab
    loop    the whole path for some discs: random -> geo -> target -> photos -> photo L -> picture -> score
    photos  render phone photos of a burned disc
    score   compare what disc-probe measured with the answers
    web     serve disc-probe's own web page against the lab (practice on the real page)
    desk    the Lab's desk page: disc basket, burner and phone (a shell over the --json commands)
    status  the box, drive, discs and practice flow as one object
    step    run one practice step by disc-probe's name, or 'next'
    swap    put a blank from the basket into the tray
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from .lab import ENV, Lab

ROOT = Path(__file__).resolve().parent.parent
BOOT = Path(__file__).resolve().parent / "boot"


def lab_env(lab: Lab, base=None) -> dict:
    env = dict(os.environ if base is None else base)
    env[ENV] = str(lab.root)
    env["DISCLAB_ROOT"] = str(ROOT)
    env["PYTHONPATH"] = os.pathsep.join([str(BOOT), str(ROOT)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    env.setdefault("DISCPROBE_WORKERS", "3")
    env["DISCPROBE_PLAIN"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def dp(lab: Lab, args, *, check=True, capture=False, timeout=None):
    """Run `python -m discprobe ARGS` against the lab, from the unpacked package root."""
    from .jsonout import diagnostics_active, record_dp
    relay = diagnostics_active() and not capture
    argv = [sys.executable, "-B", "-m", "discprobe", *map(str, args)]
    print("$ discprobe " + " ".join(map(str, args)), flush=True)
    res = subprocess.run(argv, cwd=ROOT, env=lab_env(lab), text=True, encoding="utf-8", errors="replace",
                         stdin=subprocess.DEVNULL, capture_output=capture or relay, timeout=timeout)
    if relay:
        sys.stderr.write(res.stdout + res.stderr)
    record_dp(lab, args, res.returncode)
    if check and res.returncode:
        if capture:
            sys.stdout.write(res.stdout[-4000:] + res.stderr[-4000:])
        raise SystemExit(f"discprobe {args[0]} failed with exit code {res.returncode}")
    return res


def cmd_box(a):
    from .scenario import create_from_args
    lab = Lab(a.lab)
    try:
        box = create_from_args(a)
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from None
    print(json.dumps(box, ensure_ascii=False, indent=2))
    return dict(box=box, paths=[str(lab.box_path), str(lab.answers_path), str(lab.state_path)])


def cmd_tray(a):
    lab = Lab(a.lab)
    with lab.locked_state() as st:
        d = st["drives"].setdefault(a.drive, dict(reader=a.reader or "gh70n", tray=None, open=False))
        if a.reader:
            d["reader"] = a.reader
        if a.open:
            d["open"] = True
        else:
            if a.disc and a.disc not in lab.answers()["discs"]:
                raise SystemExit(f"no disc {a.disc!r} in this box")
            d["tray"], d["open"] = a.disc, False
        lab.event(st, "tray", drive=a.drive, disc=d["tray"], open=d["open"])
    print(json.dumps(lab.state()["drives"], ensure_ascii=False))
    return dict(drives=lab.state()["drives"])


def cmd_dp(a):
    lab = Lab(a.lab)
    rest = a.rest[1:] if a.rest and a.rest[0] == "--" else a.rest
    res = dp(lab, rest, check=False, capture=getattr(a, "json", False))
    if getattr(a, "json", False):
        sys.stderr.write(res.stdout + res.stderr)
    from .jsonout import artifacts
    return dict(argv=rest, paths=artifacts(rest), exit_code=res.returncode)


def cmd_env(a):
    lab = Lab(a.lab)
    env = lab_env(lab, {})
    for k in (ENV, "DISCLAB_ROOT", "PYTHONPATH", "DISCPROBE_WORKERS"):
        print(f'$env:{k} = "{env[k]}"' if a.powershell else f'export {k}="{env[k]}"')
    return dict(environment={k: env[k] for k in (ENV, "DISCLAB_ROOT", "PYTHONPATH", "DISCPROBE_WORKERS")})


def main(argv=None, *, return_response=False):
    from .compat import require_discprobe
    from . import jsonout
    argv = list(sys.argv[1:] if argv is None else argv)
    outer_args = argv[:argv.index("--")] if "--" in argv else argv
    jsonout.Parser.json_mode = "--json" in outer_args
    try:
        require_discprobe()
    except SystemExit as exc:
        if jsonout.Parser.json_mode:
            jsonout.emit(jsonout.response(errors=[dict(type="CompatibilityError", message=str(exc))]))
            raise SystemExit(1) from None
        raise
    p = jsonout.Parser(prog="python -m disclab", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(required=True)

    s = sub.add_parser("box")
    s.add_argument("--lab", required=True)
    s.add_argument("--media", default="dvd-r")
    s.add_argument("--count", type=int, default=12)
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--batch", type=int, default=1)
    s.add_argument("--stampers", type=int, default=1)
    s.add_argument("--reader", default="gh70n")
    s.add_argument("--drives", nargs="+", default=["X:"])
    s.add_argument("--uv-noise", type=float, nargs=2, default=[0.0, 0.0], metavar=("U_BITS", "V_REL"),
                   help="per-disc spread of u (bits) and v (relative) within a stamper; default none")
    s.set_defaults(func=cmd_box)

    # Scenario/fault extension: keep registration together for sibling CLI work.
    from . import scenario, faults
    scenario.configure_box(s)
    faults.add_parser(sub)

    s = sub.add_parser("tray")
    s.add_argument("--lab", required=True)
    s.add_argument("--drive", default="X:")
    s.add_argument("--disc")
    s.add_argument("--reader")
    s.add_argument("--open", action="store_true")
    s.set_defaults(func=cmd_tray)

    s = sub.add_parser("dp")
    s.add_argument("--lab", required=True)
    s.add_argument("rest", nargs=argparse.REMAINDER)
    s.set_defaults(func=cmd_dp)

    s = sub.add_parser("env")
    s.add_argument("--lab", required=True)
    s.add_argument("--powershell", action="store_true")
    s.set_defaults(func=cmd_env)

    from . import loop, photos, poses, score, web
    loop.add_parser(sub)
    poses.add_parser(sub)
    photos.add_parser(sub)
    score.add_parser(sub)
    web.add_parser(sub)

    # TUI/API registration stays together for the parallel scenario branch merge.
    from . import tui, practice
    tui.add_parser(sub)
    practice.add_parser(sub)
    from . import flow, desk
    flow.add_parser(sub)
    desk.add_parser(sub)
    jsonout.configure(p, sub)
    a = p.parse_args(argv)
    structured = getattr(a, "json", False)
    result, code = jsonout.invoke(a, echo=structured)
    if return_response:
        return result
    if code:
        # On the command line a failure keeps its own words (SystemExit prints them once); JSON mode
        # has already emitted them in the response object.
        message = (result.get("errors") or [{}])[-1].get("message")
        if not structured and code == 1 and message and message != "1":
            raise SystemExit(message)
        raise SystemExit(code)


if __name__ == "__main__":
    main()
