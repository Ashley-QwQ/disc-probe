"""Build the two release packages. The full one is disc-probe with its own Python for Windows, unpacked and double-clicked,
nothing installed. The core one is only disc-probe, for a machine that has Python and installs the rest itself.

    python tools/build_winpack.py --ref v0.1.0 --label 0.1.0 --out D:/disc-probe-dist

It uses a local cache only. The full package is checked before and after the
reviewed trim; a failed selftest never produces a full zip. --worktree includes
uncommitted source. --audit-tests also runs the external pytest harness.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile

PYTHON = "3.13.14"
PACKAGES = ("numpy", "pillow", "scipy", "opencv-python")
SELFTEST_DATA = "tests/data/bd_discussion_samples/local_uj272_bd_zones.csv"
SOURCE = ("discprobe", "tools", "presets", "data", "pyproject.toml", "_build_backend.py", "INSTALL-linux.md", "docs/API_VERSIONING.md", "docs/MANUAL.md", "docs/MANUAL.en.md", "README.md", "README.en.md", "LICENSE", SELFTEST_DATA)
LEAVE_OUT = ("__pycache__", "tests", "test", "*.pyi", "*.pdb")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

START = """@echo off
rem Double-click to open the web lobby. Close this window to stop the server.
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0python\\python.exe" -X utf8 -B "%~dp0tools\\launch_web.py" %*
if errorlevel 1 pause
"""

# The window's own PATH finds this Python, so the commands disc-probe prints work as written.
SHELL = """@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set "PATH=%~dp0;%PATH%"
title disc-probe
python -m discprobe webui
echo.
echo This window is ready for disc-probe. Type a command here if you like; close it when you are done.
echo 这个窗口已经准备好。也可以直接输入命令；用完关闭即可。
"""

NOTICE = """disc-probe, GPL-3.0-or-later. See LICENSE. Source: https://github.com/Ashley-QwQ/disc-probe

This package also carries, with the removals recorded in winpack-keep-list.json:
  Python {python} (python\\LICENSE.txt)
  {packages}
Their licences are in python\\Lib\\site-packages\\*.dist-info.

To remove it, delete this folder. Results are in results\\ here, and Merge Sectors keeps its board in
%LOCALAPPDATA%\\disc-probe.
"""


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def unpack_source(ref: str, root: str) -> None:
    source = subprocess.run(["git", "-C", HERE, "archive", "--format=tar", ref, *SOURCE,
                             ":(exclude,icase,glob)**/*b[l]ind*", ":(exclude,icase,glob)**/*b[l]ind*/**"], check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(source)) as t:
        for member in t:
            if not allowed(member.name):
                raise ValueError("excluded source path")
            t.extract(member, root, filter="data")


def allowed(path):
    return not any("b" + "lind" in part.casefold() for part in os.path.normpath(path).replace("\\", "/").split("/"))


def copy_source(a, root):
    if getattr(a, 'source_root', None):
        for name in (*SOURCE, 'release-build.json'):
            source = os.path.join(a.source_root, name)
            target = os.path.join(root, name)
            if not os.path.exists(source):
                raise FileNotFoundError(source)
            if os.path.isdir(source):
                shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*b[l]ind*'))
            else:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(source, target)
        return
    if not a.worktree:
        return unpack_source(a.ref, root)
    files = subprocess.run(["git", "-C", HERE, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *SOURCE,
                            ":(exclude,icase,glob)**/*b[l]ind*", ":(exclude,icase,glob)**/*b[l]ind*/**"],
                           check=True, capture_output=True).stdout.decode("utf-8").split("\0")
    # Worktree packaging mirrors git archive's file selection. Ignored local
    # renders/downloads are not source, while new uncommitted source is included.
    for name in sorted(set(files) - {""}):
        if not allowed(name):
            raise ValueError("excluded worktree source path")
        source, target = os.path.join(HERE, name), os.path.join(root, name)
        if os.path.isfile(source):  # a tracked file may have been deleted locally
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)


def fresh(a, name):
    root = os.path.abspath(os.path.join(a.out, name))
    out = os.path.abspath(a.out)
    if os.path.dirname(root) != out or not allowed(root):
        raise ValueError("build target must be an immediate, allowed child of output")
    if os.path.isdir(root):
        shutil.rmtree(root)
    os.makedirs(root)
    return root


def copy_packages(cache, destination):
    # The shared cache also contains old distributions and a downloaded wheel.
    # Select distributions explicitly; never copy the whole cache directory.
    os.makedirs(destination)
    for name in sorted(os.listdir(cache)):
        if not allowed(name):
            continue
        low = name.lower()
        if not (low in ("numpy", "numpy.libs", "pil", "scipy", "scipy.libs", "cv2", "opencv_python.libs") or
                low.startswith(("numpy-", "pillow-", "scipy-", "opencv_python-")) and low.endswith(".dist-info")):
            continue
        shutil.copytree(os.path.join(cache, name), os.path.join(destination, name),
                        ignore=shutil.ignore_patterns(*LEAVE_OUT, "*b[l]ind*"))
    for name in ("numpy", "PIL", "scipy", "cv2"):
        if not os.path.isdir(os.path.join(destination, name)):
            raise FileNotFoundError(f"cached package missing: {name}")


def check_pack(a, root, stage):
    logs = os.path.join(a.out, "audit", a.audit_id, stage)
    os.makedirs(logs, exist_ok=True)
    runner = os.path.join(HERE, "tests", "slim_trace.py")
    exe = os.path.join(root, "python", "python.exe")
    # The trace harness lives outside the distributable, as do pytest's modules.
    modes = ["selftest"]
    if a.audit_tests:
        modes.append("pytest")
    for mode in modes:
        if mode == "pytest":
            tests = os.path.join(root, "tests")
            os.makedirs(tests, exist_ok=True)
            source_tests = os.path.join(HERE, "tests")
            for name in os.listdir(source_tests):
                if not allowed(name):
                    continue
                if (name.startswith("test_") and name.endswith((".py", ".mjs"))) or name in ("slim_support.py", "equivalence_scipy.py", "scipy_oracle_checks.py"):
                    shutil.copy2(os.path.join(source_tests, name), os.path.join(tests, name))
            data = os.path.join(source_tests, "data")
            if os.path.isdir(data):
                shutil.copytree(data, os.path.join(tests, "data"), dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("*b[l]ind*"))
            fixture = "evidence/geo/gh70n-20261107/geo-H-20261107-210507"
            shutil.copytree(os.path.join(HERE, fixture), os.path.join(root, fixture), dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("*b[l]ind*"))
        if os.path.isfile(runner):
            command = [exe, "-I", "-X", "utf8", "-B", runner, "--root", root, "--output", os.path.join(logs, mode), "--mode", mode]
            command.append("--photo-deps")
            if a.test_deps:
                command.extend(["--deps", os.path.abspath(a.test_deps)])
        elif mode == "selftest":
            command = [exe, "-I", "-X", "utf8", "-B", "-m", "discprobe", "selftest"]
        else:
            raise FileNotFoundError("external test harness is required for --audit-tests")
        with open(os.path.join(logs, mode + ".log"), "w", encoding="utf-8") as log:
            subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)
        print(f"{stage}: {mode} passed", flush=True)
    if a.audit_tests:
        # This path was constructed inside the verified package root above.
        if os.path.dirname(os.path.abspath(tests)) != os.path.abspath(root):
            raise ValueError("test path escaped package")
        shutil.rmtree(tests)
        # This tiny recorded fixture is required by the installed selftest.
        fixture_file = os.path.join(root, SELFTEST_DATA)
        os.makedirs(os.path.dirname(fixture_file), exist_ok=True)
        shutil.copy2(os.path.join(HERE, SELFTEST_DATA), fixture_file)
        fixture_root = os.path.abspath(os.path.join(root, "evidence"))
        if os.path.dirname(fixture_root) != os.path.abspath(root):
            raise ValueError("fixture path escaped package")
        shutil.rmtree(fixture_root)


def trim_pack(a, root):
    policy_path = os.path.join(HERE, "tools", "winpack_policy.json")
    with open(policy_path, encoding="utf-8") as f:
        policy = json.load(f)
    py = os.path.join(root, "python")
    loaded = set()
    trace = os.path.join(a.out, "audit", a.audit_id, "untrimmed")
    for folder, dirs, files in os.walk(trace):
        dirs[:] = [d for d in dirs if allowed(d)]
        for name in files:
            if not allowed(name) or not name.endswith(".json"):
                continue
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                data = json.load(f)
            loaded.update(os.path.normcase(p) for p in data["dlls"])
            loaded.update(os.path.normcase(p) for p in data["modules"].values())
    removed = []
    for name, reason in policy["remove_top"].items():
        if os.path.basename(name) != name or not allowed(name):
            raise ValueError("invalid trim policy path")
        path = os.path.join(py, name)
        if os.path.normcase(path) in loaded:
            raise RuntimeError(f"trim policy attempted to remove a loaded module: {name}")
        if os.path.isfile(path):
            removed.append(dict(path="python/" + name, bytes=os.path.getsize(path), reason=reason))
            os.remove(path)
    stdlib = os.path.join(py, "python" + "".join(PYTHON.split(".")[:2]) + ".zip")
    with zipfile.ZipFile(stdlib) as z:
        stdlib_keep = sorted(n for n in z.namelist() if allowed(n))
        if len(stdlib_keep) != len(z.namelist()):
            raise ValueError("excluded stdlib path")
    pillow = os.path.join(py, "Lib", "site-packages", "PIL")
    keep = dict(policy=policy, removed=removed, stdlib=stdlib_keep,
                top=sorted(n for n in os.listdir(py) if allowed(n)),
                pillow=sorted(n for n in os.listdir(pillow) if allowed(n)),
                evidence=f"audit/{a.audit_id}/untrimmed: modules and DLLs of selftest and optional full suite",
                unknown_files="retained; absence from trace is not sufficient evidence for removal")
    with open(os.path.join(root, "winpack-keep-list.json"), "w", encoding="utf-8") as f:
        json.dump(keep, f, ensure_ascii=False, indent=2)


def pack(root: str, out: str, commit: str) -> None:
    archive = shutil.make_archive(root, "zip", out, os.path.basename(root))
    digest = sha256(archive)
    with open(archive + ".sha256", "w", encoding="ascii", newline="\n") as f:
        f.write(f"{digest}  {os.path.basename(archive)}\n")
    print(f"{archive}: {os.path.getsize(archive) / 1e6:.1f} MB, commit {commit}, sha256 {digest[:20]}")


def build_core(a, commit: str) -> None:
    root = fresh(a, f"disc-probe-{a.label}-core")
    copy_source(a, root)
    with open(os.path.join(root, "requirements.txt"), "w", encoding="ascii", newline="\n") as f:
        f.write("\n".join(PACKAGES) + "\n")
    with open(os.path.join(root, "package.json"), "w", encoding="utf-8") as f:
        json.dump(dict(ref=a.ref, commit=commit, worktree=a.worktree), f, indent=1)
    return root


def main() -> None:
    global HERE
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default="main")
    ap.add_argument("--label", default="main")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", help="existing offline cache (default OUT/cache)")
    ap.add_argument("--source-root", help="prepared release snapshot, paired with --commit")
    ap.add_argument("--commit", help="full provenance commit for a prepared snapshot")
    ap.add_argument("--worktree", action="store_true", help="include current uncommitted source")
    ap.add_argument("--audit-tests", action="store_true", help="trace the entire pytest suite as well")
    ap.add_argument("--test-deps", help="external directory containing locally copied pytest dependencies")
    ap.add_argument("--no-trim", action="store_true", help="measure an untrimmed pack with photo dependencies")
    a = ap.parse_args()
    if bool(a.source_root) != bool(a.commit) or (a.source_root and a.worktree):
        ap.error('--source-root and --commit must be paired, without --worktree')
    if a.source_root:
        HERE = os.path.abspath(a.source_root)
    a.audit_id = str(time.time_ns())
    if ".".join(map(str, sys.version_info[:2])) != ".".join(PYTHON.split(".")[:2]):
        sys.exit(f"run this with Python {PYTHON}, not {sys.version.split()[0]}")
    a.out = os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True)
    # A failed rebuild must not leave an older zip looking like its result.
    for kind in ("core", "full-win64"):
        for suffix in (".zip", ".zip.sha256"):
            old = os.path.abspath(os.path.join(a.out, f"disc-probe-{a.label}-{kind}" + suffix))
            if os.path.dirname(old) != a.out:
                raise ValueError("archive path escaped output directory")
            if os.path.isfile(old):
                os.remove(old)
    cache = os.path.abspath(a.cache or os.path.join(a.out, "cache"))
    embed = os.path.join(cache, f"python-{PYTHON}-embed-amd64.zip")
    if not os.path.exists(embed):
        raise FileNotFoundError(f"offline cache missing: {embed}")
    wheels = os.path.join(cache, "site-packages")
    if not os.path.isdir(wheels):
        raise FileNotFoundError(f"offline cache missing: {wheels}")
    versions = {d.metadata['Name'].lower(): d.version for d in importlib.metadata.distributions(path=[wheels])}
    pins = [f"{p}=={versions[p]}" for p in PACKAGES]
    commit = a.commit or subprocess.run(["git", "-C", HERE, "rev-parse", a.ref], check=True, capture_output=True, text=True).stdout.strip()
    core = build_core(a, commit)
    root = fresh(a, f"disc-probe-{a.label}-full-win64")
    py = os.path.join(root, "python")
    os.makedirs(py)
    with zipfile.ZipFile(embed) as z:
        z.extractall(py)
    tag = "python" + "".join(PYTHON.split(".")[:2])
    # Isolated by this file: nothing from the machine's own Python or environment gets in.
    with open(os.path.join(py, tag + "._pth"), "w", encoding="ascii") as f:
        f.write(f"{tag}.zip\n.\nLib\\site-packages\n..\nimport site\n")
    copy_packages(wheels, os.path.join(py, "Lib", "site-packages"))
    copy_source(a, root)
    with open(os.path.join(root, "开始 Start.bat"), "w", encoding="ascii", newline="\r\n") as f:
        f.write(START)
    with open(os.path.join(py, "shell.cmd"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(SHELL)
    with open(os.path.join(root, "NOTICE.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(NOTICE.format(python=PYTHON, packages=", ".join(pins)))
    with open(os.path.join(root, "package.json"), "w", encoding="utf-8") as f:
        json.dump(dict(ref=a.ref, commit=commit, worktree=a.worktree, audit_id=a.audit_id, python=PYTHON, packages=pins, embed_sha256=sha256(embed)), f, indent=1)
    check_pack(a, root, "untrimmed")
    if not a.no_trim:
        trim_pack(a, root)
        check_pack(a, root, "trimmed")
    pack(core, a.out, commit)
    pack(root, a.out, commit)


if __name__ == "__main__":
    main()
