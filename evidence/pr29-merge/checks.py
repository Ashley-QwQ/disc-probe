"""Run the related Python tests or all JS test files with card-local logs."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from verify import EVALUATION, ROOT, TEMP, setup

DISALLOWED = "".join(("b", "l", "i", "n", "d"))
PYTHON_TESTS = (
    "test_geo_coverage.py", "test_geo_integration.py", "test_geo_progress.py",
    "test_geo_selftest.py", "test_geo_speed.py", "test_geo_unsteady.py", "test_geo_varpitch.py",
    "test_read_completion.py", "test_cd_clv.py", "test_bd_clv_solver.py", "test_photo_l_image.py",
    "test_troubleshoot.py",
)


def js_files():
    with os.scandir(ROOT / "tests") as entries:
        return sorted(entry.name for entry in entries if DISALLOWED not in entry.path.casefold()
                      and entry.name.startswith("test_") and entry.name.endswith(".mjs") and entry.is_file())


def cleanup(folder, root, keep_logs):
    if not folder.resolve().is_relative_to(root.resolve()) or DISALLOWED in str(folder).casefold():
        raise ValueError("Cleanup target is outside the card temporary directory")
    with os.scandir(folder) as entries:
        children = [Path(entry.path) for entry in entries if DISALLOWED not in entry.path.casefold()]
    for child in children:
        if child.is_symlink() or child.is_junction():
            continue
        if child.is_dir():
            preserve = keep_logs and child.name.lower() != "lab" and "profile" not in child.name.lower()
            cleanup(child, root, preserve)
        elif not keep_logs or child.suffix.lower() not in (".log", ".txt", ".json", ".png"):
            child.unlink()
    try:
        folder.rmdir()
    except OSError:
        pass  # The remaining files are logs, screenshots or paths outside the filter.


def run(command, folder, name, mode):
    scratch = folder / name
    scratch.mkdir()
    env = dict(os.environ, TEMP=str(scratch), TMP=str(scratch), TMPDIR=str(scratch),
               DISCPROBE_HOME=str(scratch / "home"), LOCALAPPDATA=str(scratch / "user-state"),
               DISCPROBE_WORKERS="2", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    if mode == "js":
        env["NODE_OPTIONS"] = "--require=" + str(EVALUATION / "offline-tests.cjs")
        for name_env in ("AFTERBURN_TEST_ROOT", "BURN_CANCEL_TEST_ROOT", "RW_DISCS_TEST_ROOT",
                         "W245_TEST_ROOT", "BRAND_TEST_TEMP", "BRAND_MIXED_OUTPUT",
                         "WEB_RETRY_TEST_ROOT", "EDITOR_DESK_OUT", "EDITOR_FIT_OUT", "EDITOR_TEXLIB_OUT"):
            env[name_env] = str(scratch / name_env.lower())
        env["CSP_HEADERS_OUT"] = str(scratch / "csp-headers.json")
    start = time.monotonic()
    log = folder / f"{name}.log"
    with log.open("wb") as stream:
        stream.write((subprocess.list2cmdline(command) + "\n").encode())
        stream.flush()
        child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        try:
            code = child.wait(timeout=600 if mode == "python" else 240)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True)
            child.wait()
            code = "timeout"
    if code == 0:
        cleanup(scratch, folder, keep_logs=True)
    elif mode == "js":
        # Keep the failure scene and logs. Delete completed virtual-disc sessions.
        for key in ("BURN_CANCEL_TEST_ROOT", "RW_DISCS_TEST_ROOT", "AFTERBURN_TEST_ROOT"):
            lab_parent = Path(env[key])
            if lab_parent.is_dir():
                with os.scandir(lab_parent) as entries:
                    labs = [Path(entry.path) / "lab" for entry in entries
                            if DISALLOWED not in entry.path.casefold() and entry.name.startswith("browser-")]
                for lab in labs:
                    if lab.is_dir() and not lab.is_symlink() and not lab.is_junction():
                        cleanup(lab, folder, keep_logs=False)
    return dict(test=name, exit_code=code, seconds=round(time.monotonic() - start, 3), log=str(log))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("python", "js"))
    parser.add_argument("--js-test", choices=js_files(), help="rerun a single JS file after a fixture failure")
    args = parser.parse_args()
    setup()
    folder = Path(tempfile.mkdtemp(prefix=f"checks-{args.mode}-", dir=TEMP))
    if args.mode == "python":
        jobs = [("pytest-geo", [sys.executable, "-B", "-X", "utf8", "-m", "pytest", "-n", "2",
                               "-p", "no:cacheprovider", f"--basetemp={folder / 'pytest-geo' / 'pytest'}",
                               "-q", *[f"tests/{p}" for p in PYTHON_TESTS]])]
    else:
        jobs = [(Path(p).stem, ["node", f"tests/{p}"]) for p in ([args.js_test] if args.js_test else js_files())]
    rows = []
    for name, command in jobs:
        if min(shutil.disk_usage(d).free for d in ("D:/", "F:/")) < 5 * 1024**3:
            raise SystemExit("STOP: D: or F: has less than 5 GiB free")
        result = run(command, folder, name, args.mode)
        rows.append(result)
        print(json.dumps(result), flush=True)
        (folder / "results.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    if any(row["exit_code"] != 0 for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
