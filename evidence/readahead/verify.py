"""Offline acceptance checks for the read-ahead card. Run from the repository root."""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import importlib.abc
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
TEMP = Path("D:/dp-dev/tmp/readahead")
BASE = "f99ac21"
FORBIDDEN = "blind"
PATCHED = ("__main__", "geo", "sim", "timing", "zh")
STAMP = datetime.datetime(2026, 11, 26, 12)
WINDOWS = {"cd": 24, "dvd": 112}


def setup():
    if shutil.disk_usage(TEMP.drive + "/").free < 5 * 1024**3:
        raise SystemExit("STOP: D: has less than 5 GiB free")
    TEMP.mkdir(parents=True, exist_ok=True)
    os.chdir(ROOT)
    os.environ.update(TEMP=str(TEMP), TMP=str(TEMP), TMPDIR=str(TEMP),
                      DISCPROBE_PLAIN="1", DISCPROBE_HOME=str(TEMP / "home"),
                      LOCALAPPDATA=str(TEMP / "user-state"), DISCPROBE_WORKERS="2",
                      OPENBLAS_NUM_THREADS="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    sys.path.insert(0, str(ROOT))


class Baseline(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Load changed modules straight from Git and use the shared checked-in fixtures."""

    def __init__(self, with_sim=False):
        self.modules = set(PATCHED) - ({"sim"} if with_sim else set())

    def find_spec(self, fullname, path, target=None):
        package, _, name = fullname.partition(".")
        if package == "discprobe" and name in self.modules:
            return importlib.util.spec_from_file_location(fullname, ROOT / f"discprobe/{name}.py", loader=self)

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        exec(self.get_code(module.__name__), module.__dict__)

    def get_code(self, fullname):
        path = ROOT / "discprobe" / (fullname.rpartition(".")[2] + ".py")
        source = subprocess.check_output(["git", "show", f"{BASE}:discprobe/{path.name}"], cwd=ROOT)
        return compile(source, str(path), "exec")


def child(revision, task, *args):
    if revision.startswith("base"):
        sys.meta_path.insert(0, Baseline(with_sim=revision in ("base-with-sim", "base-uncached")))
    if task == "cli":
        from discprobe import __main__ as cli, geo_checkpoint

        class FixedDatetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return STAMP.replace(tzinfo=tz)

        cli.datetime = geo_checkpoint.datetime = SimpleNamespace(datetime=FixedDatetime, timezone=datetime.timezone)
        # A deterministic wall clock keeps run names, elapsed times and ZIP times
        # comparable. SimDrive still has its own seeded spindle clock.
        time.monotonic = lambda: 1000.0
        time.time = STAMP.timestamp
        if revision in ("base-with-sim", "base-uncached", "current-uncached", "current-no-fua"):
            from discprobe.sim import SimDrive
            cli._open = lambda a: SimDrive(seed=a.seed, media=a.media, fua_honoured=revision != "current-no-fua",
                                           read_ahead_sectors=0 if revision.endswith("-uncached") else WINDOWS[a.media])
        cli.main(list(args))
    elif task == "replay":
        replay(Path(args[0]))


def run(revision, task, log, *args):
    command = [sys.executable, "-B", "-X", "utf8", __file__, "child", revision, task, *map(str, args)]
    env = None
    if task == "selftest":
        command = [sys.executable, "-B", "-u", "-X", "utf8", "-m", "discprobe", "selftest"]
        env = dict(os.environ, PYTHONPATH=str(log.parent), RA_SELFTEST_BASELINE=str(revision == "base"))
    started = time.perf_counter()
    with log.open("wb") as output:
        result = subprocess.run(command, env=env, stdout=output, stderr=subprocess.STDOUT)
    return result.returncode, time.perf_counter() - started


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def emit(folder, name, data):
    body = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    (folder / f"{name}.json").write_text(body, encoding="utf-8")
    print(body, flush=True)


def cli_run(folder, revision, task, media, variant, window=None):
    dest = folder / "same-output-path"
    log = folder / f"{revision}-{task}-{media}-{variant}-{window}.log"
    args = [task, "--sim", variant, "--media", media, "--seed", "7", "--out", dest]
    if window is not None:
        args.extend(["--sim-read-ahead-sectors", window])
    status, _ = run(revision, "cli", log, *args)
    (result,) = safe_children(dest)
    files = safe_children(result)
    hashes = {p.name: digest(p) for p in files if p.is_file()}
    summary = {}
    events = []
    if "summary.json" in hashes:
        summary = json.loads((result / "summary.json").read_text(encoding="utf-8"))
    if "events.csv" in hashes:
        with (result / "events.csv").open(newline="", encoding="utf-8") as stream:
            events = list(csv.DictReader(stream))
    # Only this known run folder is produced by the child; delete its artifacts
    # after fingerprinting them so both revisions use exactly the same path.
    for path in files:
        path.unlink()
    result.rmdir()
    dest.rmdir()
    return {"exit": status, "files": hashes, "terminal": digest(log)}, summary, events


def safe_children(folder):
    return [p for p in folder.iterdir() if FORBIDDEN not in str(p).casefold()]


def parity(folder, selected=None):
    rows = []
    for media in WINDOWS:
        for variant in ("cav", "cav-nofua", "cav-flush", "cav-audio"):
            for task in ("timing", "geo"):
                if selected and selected != [media, variant, task]:
                    continue
                base, *_ = cli_run(folder, "base", task, media, variant)
                current, *_ = cli_run(folder, "current", task, media, variant)
                rows.append(dict(media=media, variant=variant, task=task, match=base == current,
                                 baseline=base, current=current))
        for task in ("timing", "geo"):
            if selected and selected != [media, "uncached-control", task]:
                continue
            base, *_ = cli_run(folder, "base-uncached", task, media, "cav")
            current, *_ = cli_run(folder, "current-uncached", task, media, "cav")
            rows.append(dict(media=media, variant="uncached-control", task=task, match=base == current,
                             baseline=base, current=current))
    emit(folder, "parity", rows)
    assert rows and all(row["match"] for row in rows)


def fit_metrics(summary):
    fields = ("r0_mm_at_bit", "pitch_um_at_bit", "u", "v", "residual_rms_deg", "angle_sigma_deg")
    return {key: summary["fit"][key] for key in fields}


def simulate(folder):
    rows = []
    for media, window in WINDOWS.items():
        before, failed, events = cli_run(folder, "base-with-sim", "geo", media, "cav")
        after, repaired, current_events = cli_run(folder, "current", "geo", media, "cav-readahead", window)
        control, normal, control_events = cli_run(folder, "current", "geo", media, "cav-readahead", 0)
        timing, measured, _ = cli_run(folder, "current", "timing", media, "cav-readahead", window)
        assert before["exit"] == 1 and "could not measure LBA" in failed["stopped"]
        assert after["exit"] == control["exit"] == timing["exit"] == 0
        assert repaired["fit"]["completion_status"] == normal["fit"]["completion_status"] == "target_reached"
        assert repaired["cache"]["strategy"] == measured["cache"]["strategy"] == "fua"
        lba = int(re.search(r"could not measure LBA (\d+) near the reference", failed["stopped"])[1])
        first_ref = next(int(ref["lba"]) for ref, x in zip(events, events[1:])
                         if ref["label"] == "ref" and x["label"] == "target" and int(x["lba"]) == lba)
        repaired_lbas = [e["lba"] for e in current_events if e["label"] == "target"]
        control_lbas = [e["lba"] for e in control_events if e["label"] == "target"]
        assert str(lba) in repaired_lbas and repaired_lbas == control_lbas
        assert after["files"]["targets.csv"] == control["files"]["targets.csv"]
        fit, reference = fit_metrics(repaired), fit_metrics(normal)
        delta = {k: fit[k] - reference[k] for k in fit}
        rows.append(dict(media=media, input_window=window, old_stop=failed["stopped"],
                         first_lba=lba, ref_lba=first_ref, first_lba_gap=lba - first_ref,
                         before_strategy=failed["cache"]["strategy"], after_cache=repaired["cache"],
                         timing_cache=measured["cache"], timing_rotation=measured["period"]["rotation"]["mode"],
                         after_target_reads=len(repaired_lbas), control_target_reads=len(control_lbas),
                         fit=fit, control=reference, delta=delta))
        no_fua, no_fua_summary, _ = cli_run(folder, "current-no-fua", "geo", media, "cav")
        assert no_fua["exit"] == 1 and "from its read-ahead cache" in no_fua_summary["stopped"]
        assert no_fua_summary["cache"]["strategy"] == "plain"
        rows[-1]["no_fua_stop"] = no_fua_summary["stopped"]
    emit(folder, "simulate", rows)


def replay(folder):
    # Use the exact PR #29 input manifest, without walking unrelated drive trees.
    sys.path[:0] = [str(ROOT / "evidence/pr29-merge"), str(ROOT / "evidence/pr29-eval")]
    import evaluate
    import verify as pr29
    manifest = json.loads((pr29.EVALUATION / "replay_manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["runs"]:
        path = Path(entry["path"])
        assert FORBIDDEN not in str(path).casefold()
        assert all(digest(path / name) == sha for name, sha in entry["sha256"].items()), path
    evaluate.candidates = lambda: ([Path(e["path"]) for e in manifest["runs"]], manifest["roots"])
    pr29.compare_replay(folder)


def replay_compare(folder):
    hashes = {}
    for revision in ("base", "current"):
        out = folder / revision
        out.mkdir()
        code, _ = run(revision, "replay", folder / f"{revision}-replay.log", out)
        assert code == 0
        files = [p for p in safe_children(out) if p.is_file()] + safe_children(out / "replay_logs")
        hashes[revision] = {p.relative_to(out).as_posix(): digest(p) for p in files}
    comparison = json.loads((folder / "current/replay-comparison.json").read_text(encoding="utf-8"))
    assert not comparison["differences"] and comparison["same_inputs"] == 38
    emit(folder, "replay", dict(files=len(hashes["base"]), match=hashes["base"] == hashes["current"],
                                comparison=comparison, hashes=hashes))
    assert hashes["base"] == hashes["current"]


def syswow(folder):
    from discprobe.timing import CACHE_HIT_US, CACHE_RATIO, read_ahead_hits
    data = Path("D:/dp-dev/tmp/syswow/cd-lba")
    timing = data / "timing-D-20261126-150932"
    geo = data / "geo-D-20261126-151239"
    summary = json.loads((timing / "summary.json").read_text(encoding="utf-8-sig"))
    with (geo / "events.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    pairs = []
    for ref, target in zip(rows, rows[1:]):
        if (ref["label"], ref["lba"], target["label"], target["lba"]) == ("ref", "178122", "target", "178130"):
            pairs.append(tuple(SimpleNamespace(duration_us=float(row["duration_us"]), status=int(row["status"]),
                                               t_end_ns=int(row["t_end_ns"]), t_start_ns=int(row["t_start_ns"]))
                               for row in (ref, target)))
    cache = summary["cache"]
    turn_us = cache["plain"]["p50_us"]
    limit = min(turn_us / 2, max(CACHE_HIT_US, turn_us / CACHE_RATIO))
    assert read_ahead_hits(pairs, turn_us)
    assert cache["fua_reads_media"] and not cache["plain_served_from_cache"]
    emit(folder, "syswow", dict(cache=cache, positions=[178122, 178130], target_limit_us=limit,
                                 pairs=len(pairs), hits=sum(x.duration_us < limit for _, x in pairs),
                                 ref_median_us=statistics.median(r.duration_us for r, _ in pairs),
                                 target_median_us=statistics.median(x.duration_us for _, x in pairs),
                                 host_gap_us=[f((x.t_start_ns - r.t_end_ns) / 1000 for r, x in pairs) for f in (min, max)],
                                 detected=read_ahead_hits(pairs, turn_us)))


def selftest(folder):
    # Use -m for both revisions, including Windows multiprocessing children. The
    # startup hook only substitutes pre-change source when running the baseline.
    (folder / "sitecustomize.py").write_text(
        "import faulthandler, os, sys\n"
        "faulthandler.dump_traceback_later(900, repeat=True)\n"
        "if os.environ.get('RA_SELFTEST_BASELINE') == 'True':\n"
        f"    sys.path.insert(0, {str(Path(__file__).parent)!r})\n"
        "    from verify import Baseline\n"
        "    sys.meta_path.insert(0, Baseline())\n"
        "    sys.path.pop(0)\n", encoding="utf-8")
    rows = []
    for revision in ("base", "current"):
        status, seconds = run(revision, "selftest", folder / f"{len(rows)}-{revision}-selftest.log")
        rows.append(dict(revision=revision, exit=status, seconds=round(seconds, 3)))
        print(rows[-1], flush=True)
    base, current = (statistics.mean(row["seconds"] for row in rows if row["revision"] == rev)
                     for rev in ("base", "current"))
    emit(folder, "selftest", dict(runs=rows, baseline_s=base, current_s=current, change_pct=100 * (current / base - 1)))
    assert all(row["exit"] == 0 for row in rows) and current <= base * 1.10


def js(folder, selected=()):
    from unittest.mock import patch

    sys.path.insert(0, str(ROOT / "evidence/pr29-merge"))
    import checks
    browser = ("D:/20261001film/tools/browsers/chrome-headless-shell/win64-154.0.8037.57/"
               "chrome-headless-shell-win64/chrome-headless-shell.exe")
    os.environ["DP_TEST_BROWSER"] = browser
    # Keep the PR's offline preloader and add the same kind of Windows cleanup
    # fallback as removeProfile in tests/browser.mjs, for Disc Lab directories.
    preloader = folder / "offline-tests.cjs"
    paths = [checks.EVALUATION / preloader.name, ROOT / "evidence/readahead/browser-cleanup.cjs"]
    preloader.write_text("".join(f"require({json.dumps(str(path))});\n" for path in paths), encoding="utf-8")
    checks.EVALUATION = folder

    class BrowserProcess(subprocess.Popen):
        def wait(self, timeout=None):
            # The original runner's outer 240 s overlaps the fixture's own 240 s
            # job timeout. Let the whole fixture finish and report its result.
            if timeout == 240 and self.args[0] == "node":
                timeout = 1800 if self.args[1].endswith("test_reshoot_browser.mjs") else 600
            return super().wait(timeout=timeout)

    available = checks.js_files()
    rows = []
    for test in selected or available:
        assert test in available, test
        if shutil.disk_usage(TEMP.drive + "/").free < 5 * 1024**3:
            raise SystemExit("STOP: D: has less than 5 GiB free")
        with patch.object(subprocess, "Popen", BrowserProcess):
            row = checks.run(["node", f"tests/{test}"], folder, Path(test).stem, "js")
        rows.append(row)
        print(json.dumps(row), flush=True)
    emit(folder, "js", rows)
    assert all(row["exit_code"] == 0 for row in rows)


def main():
    setup()
    if sys.argv[1:2] == ["child"]:
        child(*sys.argv[2:])
        return
    jobs = dict(parity=parity, simulate=simulate, replay=replay_compare, syswow=syswow, selftest=selftest, js=js)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=jobs)
    parser.add_argument("--js-test", action="append", default=[])
    parser.add_argument("--parity-case", nargs=3, metavar=("MEDIA", "SIM", "COMMAND"))
    args = parser.parse_args()
    mode = args.mode
    folder = Path(tempfile.mkdtemp(prefix=mode + "-", dir=TEMP))
    print(folder, flush=True)
    if mode == "js":
        js(folder, args.js_test)
    elif mode == "parity":
        parity(folder, args.parity_case)
    else:
        jobs[mode](folder)


if __name__ == "__main__":
    main()
