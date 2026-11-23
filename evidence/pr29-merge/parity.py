"""Compare the timing artifacts and full default DVD grid ISO with 95d3289."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from zipfile import ZipFile

from verify import ROOT, TEMP, setup

BASE = "95d3289"
STAMP = "2026-11-23T12:00:00"


def run_cli(source, args):
    sys.path.insert(0, source)
    from discprobe import __main__ as cli, iso9660

    class FixedDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromisoformat(STAMP).replace(tzinfo=tz)

    # CLI directory names and ISO9660 timestamps are supplied the same clock.
    clock = SimpleNamespace(datetime=FixedDatetime, timezone=datetime.timezone)
    cli.datetime = iso9660.datetime = clock
    cli.main(args)


def baseline_source(folder):
    # Export only the tracked source and small configuration needed by these
    # commands. No checkout or second worktree is needed.
    paths = subprocess.check_output(
        ["git", "ls-files", "-z", "--", ":(glob)discprobe/**/*.py", ":(glob)discprobe/*.json",
         "discprobe/web/home/design/swatches.json", ":(glob)presets/*.json", ":(exclude,icase,glob)**/*[b]lind*",
         ":(exclude,icase,glob)**/*[b]lind*/**"], cwd=ROOT).decode().split("\0")[:-1]
    archive = folder / "baseline.zip"
    subprocess.run(["git", "archive", "--format=zip", f"--output={archive}", BASE, "--", *paths],
                   cwd=ROOT, check=True)
    source = folder / "source"
    with ZipFile(archive) as package:
        package.extractall(source)
    return source


def fingerprint(path):
    with path.open("rb") as f:
        return dict(bytes=path.stat().st_size, sha256=hashlib.file_digest(f, "sha256").hexdigest())


def main():
    setup()
    out = TEMP / "parity"
    out.mkdir(exist_ok=True)
    env = dict(os.environ, DISCPROBE_WORKERS="2", DISCPROBE_PLAIN="1",
               DISCPROBE_HOME=str(out / "home"), LOCALAPPDATA=str(out / "localappdata"),
               PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    timing_out = out / "timing"
    timing_run = timing_out / "timing-SIM-cav-20261123-120000"
    geo = out / "geo-SIM-fixed"
    geo.mkdir(exist_ok=True)
    geometry = geo / "summary.json"
    geometry.write_text(json.dumps(dict(fit=dict(u=23.93 / .0001336, v=.000735 / .0001336,
        bit_nm_assumed=133.6, measured_span_mm=[24, 58]))) + "\n", encoding="utf-8")
    image = out / "grid.iso"
    results = {}
    with TemporaryDirectory(prefix="parity-source-", dir=TEMP) as name:
        baseline = baseline_source(Path(name))
        for revision, source in ((BASE, baseline), ("merge", ROOT)):
            stats = {}
            for command, args in (
                ("timing", ["timing", "--sim", "cav", "--seed", "7", "--out", str(timing_out)]),
                ("image", ["image", "--geo", str(geometry), "--output", str(image)]),
            ):
                if min(shutil.disk_usage(d).free for d in ("D:/", "F:/")) < 5 * 1024**3:
                    raise SystemExit("STOP: D: or F: has less than 5 GiB free")
                log = out / f"{revision}-{command}.log"
                with log.open("wb") as stream:
                    subprocess.run([sys.executable, "-B", "-X", "utf8", __file__, "cli", str(source), *args],
                                   cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
                if command == "timing":
                    for file in ("events.csv", "summary.json"):
                        stats[f"timing/{file}"] = fingerprint(timing_run / file)
                        (timing_run / file).unlink()
                    timing_run.rmdir()
                else:
                    stats["image/grid.iso"] = fingerprint(image)
                    image.unlink()
                    for name in ("grid.image.json", "grid.preview.png", "grid.iso.verification.json", "grid.iso.lock"):
                        (out / name).unlink(missing_ok=True)
                print(revision, command, json.dumps(stats), flush=True)
            results[revision] = stats
    match = results[BASE] == results["merge"]
    rendered = json.dumps(dict(match=match, revisions=results), indent=2) + "\n"
    (out / "results.json").write_text(rendered, encoding="utf-8")
    if not match:
        raise SystemExit("Timing or image bytes changed")
    geometry.unlink()
    geo.rmdir()
    timing_out.rmdir()


if __name__ == "__main__":
    if sys.argv[1:2] == ["cli"]:
        run_cli(sys.argv[2], sys.argv[3:])
    else:
        main()
