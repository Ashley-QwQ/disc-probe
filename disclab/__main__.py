"""python -m disclab <command> --lab LAB ...

    box     make a box of discs (truth goes to LAB/answers.json)
    tray    put a disc into a lab drive (or --open to open the tray)
    dp      run a discprobe command against the lab: python -m disclab dp --lab LAB -- geo --drive X: ...
    env     print the environment a shell needs to run discprobe against the lab
    loop    the whole path for some discs: random -> geo -> target -> photos -> photo L -> picture -> score
    photos  render phone photos of a burned disc
    score   compare what disc-probe measured with the answers
    web     serve the web page against the lab (development only)
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
    argv = [sys.executable, "-B", "-m", "discprobe", *map(str, args)]
    print("$ discprobe " + " ".join(map(str, args)), flush=True)
    res = subprocess.run(argv, cwd=ROOT, env=lab_env(lab), text=True, encoding="utf-8", errors="replace",
                         stdin=subprocess.DEVNULL, capture_output=capture, timeout=timeout)
    if check and res.returncode:
        if capture:
            sys.stdout.write(res.stdout[-4000:] + res.stderr[-4000:])
        raise SystemExit(f"discprobe {args[0]} failed with exit code {res.returncode}")
    return res


def cmd_box(a):
    from .scenario import create_from_args
    try:
        box = create_from_args(a)
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from None
    print(json.dumps(box, ensure_ascii=False, indent=2))


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


def cmd_dp(a):
    lab = Lab(a.lab)
    rest = a.rest[1:] if a.rest and a.rest[0] == "--" else a.rest
    sys.exit(dp(lab, rest, check=False).returncode)


def cmd_env(a):
    lab = Lab(a.lab)
    env = lab_env(lab, {})
    for k in (ENV, "DISCLAB_ROOT", "PYTHONPATH", "DISCPROBE_WORKERS"):
        print(f'$env:{k} = "{env[k]}"' if a.powershell else f'export {k}="{env[k]}"')


def main(argv=None):
    from .compat import require_discprobe
    require_discprobe()
    p = argparse.ArgumentParser(prog="python -m disclab", description=__doc__,
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

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
