"""Build the core ZIP and the full ZIP with portable Windows and Linux Python.

    python tools/build_winpack.py --ref v0.1.0 --label 0.1.0 --out D:/disc-probe-dist

The Windows embed and base dependencies come from a read-only cache.
Missing pinned Linux inputs and the Windows headless wheel are cached from
their official sources. The Windows runtime is checked before and after trim.
--worktree includes
uncommitted source. --audit-tests also runs the external pytest harness.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile

PYTHON = "3.13.14"
PACKAGES = ("numpy", "pillow", "scipy", "opencv-python-headless")
DEPENDENCIES = dict(zip(PACKAGES, ("2.5.1", "12.3.0", "1.18.1", "5.0.0.93"), strict=True))
PY_MINOR = ".".join(PYTHON.split(".")[:2])
LINUX_TAG = "20260610"
LINUX_ARCHIVE = f"cpython-{PYTHON}+{LINUX_TAG}-x86_64-unknown-linux-gnu-install_only.tar.gz"
LINUX_SHA256 = "31ebbb024fecb446d7f25a5b59ca1d4955597ca3f5b4b76f55b30a8987eb61c9"
LINUX_URL = ("https://github.com/astral-sh/python-build-standalone/releases/download/"
             f"{LINUX_TAG}/{LINUX_ARCHIVE}")
LINUX_PLATFORMS = ("manylinux_2_28_x86_64", "manylinux_2_27_x86_64", "manylinux2014_x86_64")
LINUX_WHEELS = {
    "numpy": ("numpy-2.5.1-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl",
              "9726558e8db4a5bf7929a70ae50f63abda4daf0efe810e3bfbab95976f75fc1a"),
    "pillow": ("pillow-12.3.0-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl",
               "0847a763afefb695bc912d7c131e7e0632d4edc1d8698f58ddabec8e46b8b6d3"),
    "scipy": ("scipy-1.18.1-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl",
              "fdaf5ea890a6183d0565f51a61799d67081bd5b1cf03c5f4b3fd3732108625c9"),
    "opencv-python-headless": ("opencv_python_headless-5.0.0.93-cp37-abi3-manylinux_2_28_x86_64.whl",
                               "ed709fdf9aa0bd1f2ed8549e71d19449b03a675bb581eb292285f6861953be37"),
}
WINDOWS_WHEELS = {
    "opencv-python-headless": ("opencv_python_headless-5.0.0.93-cp37-abi3-win_amd64.whl",
                              "829717b6a95554f273e49e357cee3b3a2a26b6f4842fbc1bed2b45bdd8f87e0e"),
}
SELFTEST_DATA = "tests/data/bd_discussion_samples/local_uj272_bd_zones.csv"
SOURCE = ("discprobe", "tools", "presets", "data", "pyproject.toml", "_build_backend.py", "INSTALL-linux.md", "docs/API_VERSIONING.md", "docs/MANUAL.md", "docs/MANUAL.en.md", "README.md", "README.en.md", "STYLE.md", "DESIGN.md", "LICENSE", "start-linux.sh", "先看我 Read me first.txt", SELFTEST_DATA)
LEAVE_OUT = ("__pycache__", "tests", "test", "*.pyi", "*.pdb")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINUX_START = "start-linux.sh"

START_NAME = "开始 Start (Windows).bat"
# CMD treats the first line as a label. In sh, the trailing comment hides the CR.
START = (
    ":; printf '%s\\n' '这是 Windows 启动器。Linux 请运行 bash start-linux.sh。 / "
    "This is the Windows launcher. On Linux, run bash start-linux.sh.'; exit 1 #\n"
    '@cd /d "%~dp0" && "%~dp0python\\python.exe" -X utf8 -B -m discprobe webui --open %*\n'
)


def write_start(root):
    with open(os.path.join(root, START_NAME), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(START)

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

This package carries Python {python} for Windows and Linux, plus {packages}.
Runtime sources and versions are listed in release-build.json. The trim is
recorded in winpack-keep-list.json and linuxpack-keep-list.json.
Dependency licences are in each runtime's site-packages/*.dist-info.

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
                             ":(exclude,icase,glob)**/*b[l]ind*", ":(exclude,icase,glob)**/*b[l]ind*/**",
                             ":(exclude,glob)**/delta_map_1x.npy"], check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(source)) as t:
        for member in t:
            if not allowed(member.name):
                raise ValueError("excluded source path")
            t.extract(member, root, filter="data")


def allowed(path):
    return not any("b" + "lind" in part.casefold() or part == 'delta_map_1x.npy'
                   for part in os.path.normpath(path).replace("\\", "/").split("/"))


def ignore_files(patterns):
    def ignored(_directory, names):
        return [name for name in names if not allowed(name)
                or any(fnmatch.fnmatch(name, pattern) for pattern in patterns)]
    return ignored


def copy_source(a, root):
    if getattr(a, 'source_root', None):
        for name in (*SOURCE, 'release-build.json'):
            source = os.path.join(a.source_root, name)
            target = os.path.join(root, name)
            if not os.path.exists(source):
                raise FileNotFoundError(source)
            if os.path.isdir(source):
                shutil.copytree(source, target, ignore=ignore_files(('__pycache__', '*.pyc')))
            else:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(source, target)
        return
    if not a.worktree:
        return unpack_source(a.ref, root)
    files = subprocess.run(["git", "-C", HERE, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", *SOURCE,
                            ":(exclude,icase,glob)**/*b[l]ind*", ":(exclude,icase,glob)**/*b[l]ind*/**",
                            ":(exclude,glob)**/delta_map_1x.npy"],
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


def copy_windows_base(cache, destination):
    # The shared cache also contains old distributions and a downloaded wheel.
    # Select distributions explicitly; never copy the whole cache directory.
    for name in sorted(os.listdir(cache)):
        if not allowed(name):
            continue
        low = name.lower()
        if not (low in ("numpy", "numpy.libs", "pil", "scipy", "scipy.libs") or
                low in {f"{p}-{DEPENDENCIES[p]}.dist-info" for p in PACKAGES[:-1]}):
            continue
        shutil.copytree(os.path.join(cache, name), os.path.join(destination, name),
                        ignore=ignore_files(LEAVE_OUT))
    for name in ("numpy", "PIL", "scipy"):
        if not os.path.isdir(os.path.join(destination, name)):
            raise FileNotFoundError(f"cached package missing: {name}")


def verify_digest(path, expected):
    if sha256(path) != expected:
        raise ValueError(f"SHA-256 mismatch for {path}")


def pip_command(command, *platforms):
    return [sys.executable, "-B", "-m", "pip", "--disable-pip-version-check", command,
            "--no-cache-dir", "--no-deps", "--only-binary=:all:", "--implementation", "cp",
            "--python-version", PY_MINOR,
            *[flag for platform in platforms for flag in ("--platform", platform)]]


def install_wheels(cache, destination, wheels, platforms):
    cache = Path(cache).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    # Ignore local pip settings so no other index or transport enters the build.
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("PIP_")}
    env["PIP_CONFIG_FILE"] = os.devnull
    missing = [name for name, (file, _) in wheels.items() if not (cache / file).is_file()]
    if missing:
        # Download in isolation so a failed transfer never poisons the cache.
        with tempfile.TemporaryDirectory(dir=cache) as stage:
            subprocess.run([*pip_command("download", *platforms), "--index-url", "https://pypi.org/simple/",
                            "--dest", stage, *[f"{name}=={DEPENDENCIES[name]}" for name in missing]],
                           env=env, check=True)
            for name in missing:
                file, expected = wheels[name]
                candidate = Path(stage) / file
                verify_digest(candidate, expected)
                candidate.replace(cache / file)
    for file, expected in wheels.values():
        verify_digest(cache / file, expected)
        with zipfile.ZipFile(cache / file) as archive:
            if any(not allowed(member) for member in archive.namelist()):
                raise ValueError(f"excluded wheel entry in {file}")
    subprocess.run([*pip_command("install", *platforms), "--no-index", "--no-compile",
                    "--target", str(destination), *[str(cache / file) for file, _ in wheels.values()]],
                   env=env, check=True)


def installed_versions(destination):
    versions = {d.metadata["Name"].lower(): d.version
                for d in importlib.metadata.distributions(path=[str(destination)])}
    actual = {name: versions.get(name) for name in PACKAGES}
    if actual != DEPENDENCIES or "opencv-python" in versions:
        raise ValueError(f"unexpected dependency set at {destination}: {versions}")
    return actual


def copy_packages(windows_cache, destination, cache):
    # pip --target writes to a fresh directory; it must never merge two cv2 trees.
    install_wheels(cache, destination, WINDOWS_WHEELS, ("win_amd64",))
    copy_windows_base(windows_cache, destination)
    return installed_versions(destination)


def linux_archive(cache):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / LINUX_ARCHIVE
    if not path.is_file():
        with tempfile.TemporaryDirectory(dir=cache) as stage:
            candidate = Path(stage) / path.name
            with urllib.request.urlopen(LINUX_URL, timeout=60) as source, candidate.open("wb") as output:
                shutil.copyfileobj(source, output)
            verify_digest(candidate, LINUX_SHA256)
            candidate.replace(path)
    verify_digest(path, LINUX_SHA256)
    return path


def build_linux(cache, root):
    removed = {
        "python/include": "Headers for building CPython extensions.",
        "python/lib/pkgconfig": "Development metadata for linking CPython.",
        f"python/lib/libpython{PY_MINOR}.so": "Linker alias; keep the versioned runtime library.",
        f"python/bin/python{PY_MINOR}-config": "Development script for linking CPython.",
        "python/bin/python3-config": "Alias for the development script.",
        f"python/lib/python{PY_MINOR}/config-{PY_MINOR}-x86_64-linux-gnu": "Build configuration and static archive.",
        f"python/lib/python{PY_MINOR}/test": "CPython test suite.",
        "python/share/terminfo": "Optional terminal database. None of the bundled commands use curses.",
    }
    base = Path(root) / "linux"
    aliases = ("python/bin/python", "python/bin/python3")
    links = {}
    with tarfile.open(linux_archive(cache)) as archive:
        for member in archive:
            name = member.name
            parts = PurePosixPath(name).parts
            if not parts or parts[0] != "python" or ".." in parts or "\\" in name:
                raise ValueError("unexpected Linux runtime path")
            if not allowed(name) or any(name == p or name.startswith(p + "/") for p in removed):
                continue
            target = base.joinpath(*parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
            elif member.issym() and "/" not in member.linkname and member.linkname not in (".", ".."):
                if not allowed(member.linkname):
                    raise ValueError("excluded Linux runtime link")
                links[name] = member.linkname
            else:
                raise ValueError("unexpected Linux runtime archive entry type")
    for name, link in links.items():
        target = base / name
        if name in aliases and link == f"python{PY_MINOR}":
            # Keep ZIP entries regular for Windows unpackers, without duplicating the ELF.
            target.write_text(f'#!/bin/sh\nexec "$(dirname -- "$0")/{link}" "$@"\n', encoding="ascii", newline="\n")
        else:
            shutil.copyfile(target.with_name(link), target)
    site = base / f"python/lib/python{PY_MINOR}/site-packages"
    # An independent target keeps pip from replacing the existing stdlib site-packages.
    staging = base / "wheel-target"
    install_wheels(cache, staging, LINUX_WHEELS, LINUX_PLATFORMS)
    shutil.copytree(staging, site, dirs_exist_ok=True, ignore=ignore_files((*LEAVE_OUT, "bin", "Scripts")))
    shutil.rmtree(staging)
    keep = dict(removed=removed, wheel_omit=[*LEAVE_OUT, "bin", "Scripts"],
                python_aliases=list(aliases), runtime="Keep standard library modules, shared libraries and licences.")
    write_json(Path(root) / "linuxpack-keep-list.json", keep)
    return dict(python=PYTHON, dependencies=installed_versions(site), platform="linux-x86_64-glibc-2.28",
                runtime=dict(file=LINUX_ARCHIVE, sha256=LINUX_SHA256),
                wheels={name: dict(file=file, sha256=digest) for name, (file, digest) in LINUX_WHEELS.items()})


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    archive = root + ".zip"
    prefix = Path(root).name
    with tempfile.TemporaryDirectory(dir=out) as stage:
        candidate = Path(stage) / Path(archive).name
        with zipfile.ZipFile(candidate, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for folder, dirs, names in os.walk(root):
                dirs[:] = sorted(d for d in dirs if allowed(d))
                for name in sorted(n for n in names if allowed(n)):
                    source = Path(folder) / name
                    relative = source.relative_to(root).as_posix()
                    entry = zipfile.ZipInfo.from_file(source, f"{prefix}/{relative}")
                    executable = relative == LINUX_START or relative.startswith("linux/python/bin/")
                    entry.create_system = 3
                    entry.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    with source.open("rb") as stream, z.open(entry, "w") as output:
                        shutil.copyfileobj(stream, output)
        candidate.replace(archive)
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
    ap.add_argument("--cache", help="pinned runtime and wheel download cache (default OUT/cache)")
    ap.add_argument("--windows-cache", help="read-only Windows embed ZIP and base site-packages (default --cache)")
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
    if ".".join(map(str, sys.version_info[:2])) != PY_MINOR:
        sys.exit(f"run this with Python {PYTHON}, not {sys.version.split()[0]}")
    a.out = os.path.abspath(a.out)
    os.makedirs(a.out, exist_ok=True)
    # A failed rebuild must not leave an older zip looking like its result.
    for kind in ("core", "full"):
        for suffix in (".zip", ".zip.sha256"):
            old = os.path.abspath(os.path.join(a.out, f"disc-probe-{a.label}-{kind}" + suffix))
            if os.path.dirname(old) != a.out:
                raise ValueError("archive path escaped output directory")
            if os.path.isfile(old):
                os.remove(old)
    cache = os.path.abspath(a.cache or os.path.join(a.out, "cache"))
    windows_cache = os.path.abspath(a.windows_cache or cache)
    if not all(allowed(path) for path in (cache, windows_cache)):
        raise ValueError("excluded cache path")
    embed = os.path.join(windows_cache, f"python-{PYTHON}-embed-amd64.zip")
    if not os.path.exists(embed):
        raise FileNotFoundError(f"offline cache missing: {embed}")
    wheels = os.path.join(windows_cache, "site-packages")
    if not os.path.isdir(wheels):
        raise FileNotFoundError(f"offline cache missing: {wheels}")
    commit = a.commit or subprocess.run(["git", "-C", HERE, "rev-parse", a.ref], check=True, capture_output=True, text=True).stdout.strip()
    core = build_core(a, commit)
    root = fresh(a, f"disc-probe-{a.label}-full")
    py = os.path.join(root, "python")
    os.makedirs(py)
    with zipfile.ZipFile(embed) as z:
        if any(not allowed(member) for member in z.namelist()):
            raise ValueError("excluded Windows embed entry")
        z.extractall(py)
    tag = "python" + "".join(PYTHON.split(".")[:2])
    # Isolated by this file: nothing from the machine's own Python or environment gets in.
    with open(os.path.join(py, tag + "._pth"), "w", encoding="ascii") as f:
        f.write(f"{tag}.zip\n.\nLib\\site-packages\n..\nimport site\n")
    versions = copy_packages(wheels, os.path.join(py, "Lib", "site-packages"), cache)
    copy_source(a, root)
    linux = build_linux(cache, root)
    write_start(root)
    with open(os.path.join(py, "shell.cmd"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(SHELL)
    with open(os.path.join(root, "NOTICE.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(NOTICE.format(python=PYTHON, packages=", ".join(f"{p}=={v}" for p, v in versions.items())))
    build_info = Path(root) / "release-build.json"
    info = json.loads(build_info.read_text(encoding="utf-8")) if build_info.is_file() else dict(commit=commit)
    windows = dict(python=PYTHON, dependencies=versions, embed_sha256=sha256(embed),
                   wheels={name: dict(file=file, sha256=digest) for name, (file, digest) in WINDOWS_WHEELS.items()})
    write_json(build_info, dict(info, windows=windows, linux=linux))
    write_json(Path(root) / "package.json",
               dict(ref=a.ref, commit=commit, worktree=a.worktree, audit_id=a.audit_id,
                    windows=windows, linux=linux))
    check_pack(a, root, "untrimmed")
    if not a.no_trim:
        trim_pack(a, root)
        check_pack(a, root, "trimmed")
    pack(core, a.out, commit)
    pack(root, a.out, commit)


if __name__ == "__main__":
    main()
