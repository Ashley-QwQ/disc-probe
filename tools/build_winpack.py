"""Build the core ZIP and three portable ZIPs from one Windows and Linux staging tree.

    python tools/build_winpack.py --ref v0.1.0 --label 0.1.0 --out D:/disc-probe-dist

The original runtime archives and wheels must be in the read-only input cache.
The lock is verified before installing or unpacking any input. The Windows
runtime is checked before and after trim.
--worktree includes
uncommitted source. --audit-tests also runs the external pytest harness.
"""

from __future__ import annotations

import argparse
from email.parser import BytesParser
import fnmatch
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import unquote, urlsplit
import zipfile

PYTHON = "3.13.14"
PACKAGES = ("numpy", "pillow", "scipy", "opencv-python-headless")
PY_MINOR = ".".join(PYTHON.split(".")[:2])
PY_TAG = "cp" + PY_MINOR.replace(".", "")
LOCK = Path(__file__).with_name("pack_inputs.lock.json")
WHEEL_PLATFORMS = {
    "windows": ("win_amd64",),
    "linux": ("manylinux_2_28_x86_64", "manylinux_2_27_x86_64", "manylinux2014_x86_64", "manylinux_2_17_x86_64"),
}
SELFTEST_DATA = "tests/data/bd_discussion_samples/local_uj272_bd_zones.csv"
SOURCE = ("discprobe", "tools", "presets", "data", "pyproject.toml", "_build_backend.py", "INSTALL-linux.md", "docs/API_VERSIONING.md", "docs/MANUAL.md", "docs/MANUAL.en.md", "README.md", "README.en.md", "AGENTS.md", "skills", "STYLE.md", "DESIGN.md", "LICENSE", "start-linux.sh", "先看我 Read me first.txt", SELFTEST_DATA)
LEAVE_OUT = ("__pycache__", "tests", "test", "*.pyi", "*.pdb")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINUX_START = "start-linux.sh"
START_NAME = "开始 Start (Windows).bat"
READ_FIRST = "先看我 Read me first.txt"
PORTABLE = {
    "full": ("windows", "linux"),
    "win64": ("windows",),
    "linux-x86_64": ("linux",),
}
PLATFORM_FILES = {
    "windows": {"python", START_NAME, "winpack-keep-list.json"},
    "linux": {"linux", LINUX_START, "linuxpack-keep-list.json"},
}
DOWNLOAD_DOCS = ("README.md", "README.en.md", "INSTALL-linux.md")
SIZE_MARKER = re.compile(r"<!-- size:([\w-]+) -->[^<\r\n]+<!-- /size -->")
VARIANT_FILES = {"release-build.json", "package.json", "NOTICE.txt", READ_FIRST}
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

This package carries Python {python} for {platforms}, plus {packages}.
Runtime sources and versions are listed in release-build.json. The trim is
recorded in {keep_lists}.
Dependency licences are in each runtime's site-packages/*.dist-info.

To remove it, delete this folder. Results are in the results folder here.{windows_state}
"""

SINGLE_READ_FIRST = {
    "win64": (
        "解压后双击“开始 Start (Windows).bat”。\n"
        "After extracting, double-click “开始 Start (Windows).bat”.\n\n"
        "另有两个平台都能用的 full 包，以及单独的 linux-x86_64 包。\n"
        "Also available: full for both platforms, and linux-x86_64 for Linux.\n"
    ),
    "linux-x86_64": (
        "解压后运行 bash start-linux.sh。Linux 需要 glibc 2.28 或更新。\n"
        "After extracting, run bash start-linux.sh. Linux requires glibc 2.28 or later.\n\n"
        "另有两个平台都能用的 full 包，以及单独的 win64 包。\n"
        "Also available: full for both platforms, and win64 for Windows.\n"
    ),
}


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
    out = os.path.abspath(a.build_root)
    root = os.path.abspath(os.path.join(out, name))
    if os.path.dirname(root) != out or not allowed(root):
        raise ValueError("build target must be an immediate, allowed child of output")
    os.makedirs(root)
    return root


def verify_wheel(path, entry, platform):
    from pip._vendor.packaging.specifiers import SpecifierSet
    from pip._vendor.packaging.tags import Tag, parse_tag
    from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename

    name, version, _, tags = parse_wheel_filename(path.name)
    wanted = Tag(entry["python_tag"], entry["abi"], entry["platform"])
    compatible = (wanted.interpreter == PY_TAG and wanted.abi == PY_TAG
                  or wanted.abi == "abi3" and wanted.interpreter.startswith("cp")
                  and wanted.interpreter[2:].isdigit() and 32 <= int(wanted.interpreter[2:]) <= int(PY_TAG[2:]))
    if name != entry["name"] or str(version) != entry["version"]:
        raise ValueError(f"wheel name or version does not match lock: {path.name}")
    if wanted not in tags or wanted.platform not in WHEEL_PLATFORMS[platform] or not compatible:
        raise ValueError(f"wheel platform or ABI does not match {platform} lock: {path.name}")
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if any(not allowed(member) for member in names):
            raise ValueError(f"excluded entry in {path.name}")
        metadata, = (member for member in names if member.endswith(".dist-info/METADATA"))
        wheel_file, = (member for member in names if member.endswith(".dist-info/WHEEL"))
        info = BytesParser().parsebytes(archive.read(metadata))
        wheel = BytesParser().parsebytes(archive.read(wheel_file))
    if canonicalize_name(info["Name"]) != name or info["Version"] != str(version):
        raise ValueError(f"wheel METADATA name or version does not match lock: {path.name}")
    if wanted not in {tag for field in wheel.get_all("Tag", []) for tag in parse_tag(field)}:
        raise ValueError(f"wheel WHEEL tag does not match lock: {path.name}")
    if info["Requires-Python"] and PYTHON not in SpecifierSet(info["Requires-Python"]):
        raise ValueError(f"wheel requires a different Python version: {path.name}")
    return info.get_all("Requires-Dist", [])


def verify_requirements(platform, versions, requirements):
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.utils import canonicalize_name

    windows = platform == "windows"
    markers = dict(implementation_name="cpython", implementation_version=PYTHON,
                   python_version=PY_MINOR, python_full_version=PYTHON,
                   platform_python_implementation="CPython", platform_machine="AMD64" if windows else "x86_64",
                   os_name="nt" if windows else "posix", sys_platform="win32" if windows else "linux",
                   platform_system="Windows" if windows else "Linux", extra="")
    for file, fields in requirements:
        for field in fields:
            req = Requirement(field)
            if req.marker and not req.marker.evaluate(markers):
                continue
            version = versions.get(canonicalize_name(req.name))
            if req.url or req.extras or version is None or version not in req.specifier:
                raise ValueError(f"{platform} lock does not satisfy dependency {field!r} of {file}")


def stage_inputs(cache, windows_cache, stage):
    """Verify private copies before opening a wheel or extracting a runtime."""
    raw = LOCK.read_bytes()
    lock = json.loads(raw)
    if lock.get("schema") != 1:
        raise ValueError("unsupported portable input lock schema")
    provenance = dict(lock_sha256=hashlib.sha256(raw).hexdigest())
    for platform in WHEEL_PLATFORMS:
        entries = lock[platform]
        if len({entry["name"] for entry in entries}) != len(entries):
            raise ValueError(f"duplicate {platform} input in lock")
        runtimes = [entry for entry in entries if entry["kind"] == "runtime"]
        wheels = [entry for entry in entries if entry["kind"] == "wheel"]
        if (len(runtimes) != 1 or len(runtimes) + len(wheels) != len(entries)
                or not set(PACKAGES) <= {entry["name"] for entry in wheels}):
            raise ValueError(f"incomplete {platform} input lock")
        windows = platform == "windows"
        runtime = runtimes[0]
        wheelhouse = stage / platform
        wheelhouse.mkdir()
        requires = []
        for entry in entries:
            file = entry["file"]
            parsed_url = urlsplit(entry["url"])
            expected_host = "files.pythonhosted.org" if entry["kind"] == "wheel" else (
                "www.python.org" if windows else "github.com")
            if (not allowed(file) or Path(file).name != file or "/" in file or "\\" in file
                    or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
                    or parsed_url.scheme != "https" or parsed_url.netloc != expected_host
                    or unquote(parsed_url.path.rsplit("/", 1)[-1]) != file):
                raise ValueError(f"invalid {platform} input lock record: {entry['name']}")
            if entry is runtime:
                expected_platform = "win_amd64" if windows else "x86_64-unknown-linux-gnu"
                expected_file = (re.escape(f"python-{PYTHON}-embed-amd64.zip") if windows else
                                 rf"cpython-{re.escape(PYTHON)}\+\d{{8}}-{expected_platform}"
                                 r"-install_only_stripped\.tar\.gz")
                if (entry["name"] != "cpython" or entry["version"] != PYTHON
                        or entry["platform"] != expected_platform or entry["python_tag"] != PY_TAG
                        or entry["abi"] != PY_TAG or not re.fullmatch(expected_file, file)):
                    raise ValueError(f"runtime version, platform, ABI or asset name does not match {platform} lock: {file}")
            source = (windows_cache if windows and entry is runtime else cache) / file
            if not source.is_file():
                raise FileNotFoundError(f"missing locked {platform} input {entry['name']}: expected {source}")
            staged = wheelhouse / file
            shutil.copyfile(source, staged)
            if sha256(staged) != entry["sha256"]:
                raise ValueError(f"SHA-256 mismatch for locked {platform} input {source}")
            if entry is not runtime:
                try:
                    requires.append((file, verify_wheel(staged, entry, platform)))
                except ValueError as exc:
                    raise ValueError(f"invalid wheel {file}: {exc}") from exc
        verify_requirements(platform, {item["name"]: item["version"] for item in wheels}, requires)
        provenance[platform] = [dict(entry, verified=True) for entry in entries]
    return provenance


def install_wheels(stage, platform, destination, entries):
    wheelhouse = stage / platform
    wheels = {entry["name"]: entry for entry in entries if entry["kind"] == "wheel"}
    requirements = wheelhouse / "requirements.txt"
    requirements.write_text("".join(f"{name}=={item['version']} --hash=sha256:{item['sha256']}\n"
                                    for name, item in wheels.items()), encoding="ascii", newline="\n")
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("PIP_")}
    env["PIP_CONFIG_FILE"] = os.devnull
    if Path(destination).exists():
        raise FileExistsError(f"wheel target must be new: {destination}")
    subprocess.run([sys.executable, "-B", "-m", "pip", "--disable-pip-version-check", "install",
                    "--require-hashes", "--no-index", "--no-deps", "--no-cache-dir", "--no-compile",
                    "--only-binary=:all:", "--implementation", "cp", "--python-version", PY_MINOR,
                    *[flag for tag in WHEEL_PLATFORMS[platform] for flag in ("--platform", tag)],
                    "--find-links", str(wheelhouse), "-r", str(requirements), "--target", str(destination)],
                   env=env, check=True)
    expected = {name: entry["version"] for name, entry in wheels.items()}
    versions = {dist.metadata["Name"].lower(): dist.version
                for dist in importlib.metadata.distributions(path=[str(destination)])}
    if versions != expected:
        raise ValueError(f"unexpected installed {platform} dependency set: {versions}")
    return versions


def prepare_release_inputs(cache, windows_cache, destination, report):
    with tempfile.TemporaryDirectory(dir=Path(destination).parent, prefix="pinned-inputs-") as temporary:
        stage = Path(temporary)
        provenance = stage_inputs(Path(cache), Path(windows_cache), stage)
        install_wheels(stage, "windows", destination, provenance["windows"])
        write_json(report, provenance)


def build_linux(stage, root, entries):
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
    runtime, = (entry for entry in entries if entry["kind"] == "runtime")
    with tarfile.open(stage / "linux" / runtime["file"]) as archive:
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
    staging = stage / "linux-installed"
    versions = install_wheels(stage, "linux", staging, entries)
    shutil.copytree(staging, site, dirs_exist_ok=True, ignore=ignore_files((*LEAVE_OUT, "bin", "Scripts")))
    keep = dict(removed=removed, wheel_omit=[*LEAVE_OUT, "bin", "Scripts"],
                python_aliases=list(aliases), runtime="Keep standard library modules, shared libraries and licences.")
    write_json(Path(root) / "linuxpack-keep-list.json", keep)
    return dict(python=PYTHON, dependencies=versions, platform="linux-x86_64-glibc-2.28",
                runtime=runtime, wheels={entry["name"]: entry for entry in entries if entry["kind"] == "wheel"})


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


def linux_batch_file(path):
    return path.startswith("linux/") and path.lower().endswith(".bat")


def write_payload(root, archive, omit=(), *, skip_linux_batch=False):
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for folder, dirs, names in os.walk(root):
            at_root = Path(folder) == root
            dirs[:] = sorted(d for d in dirs if allowed(d) and not (at_root and d in omit))
            for name in sorted(n for n in names if allowed(n) and not (at_root and n in omit)):
                source = Path(folder) / name
                relative = source.relative_to(root).as_posix()
                if skip_linux_batch and linux_batch_file(relative):
                    continue
                entry = zipfile.ZipInfo.from_file(source, f"{archive.stem}/{relative}")
                executable = relative == LINUX_START or relative.startswith("linux/python/bin/")
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                with source.open("rb") as stream, output.open(entry, "w") as member:
                    shutil.copyfileobj(stream, member)


def excluded_platform_files(platforms):
    return set().union(*(paths for platform, paths in PLATFORM_FILES.items() if platform not in platforms))


def download_doc(text, inventory):
    if sorted(SIZE_MARKER.findall(text)) != sorted(inventory):
        raise ValueError("download guide must contain one size marker per portable variant")
    for variant, entry in inventory.items():
        for version in ("<version>", "<版本>"):
            text = text.replace(f"disc-probe-{version}-{variant}.zip", entry["file"])
    return SIZE_MARKER.sub(lambda match: f"{inventory[match[1]]['size'] / 1e6:.3f} MB", text)


def portable_metadata(variant, info, package, docs, read_first, inventory):
    platforms = PORTABLE[variant]
    runtimes = {platform: info[platform] for platform in platforms}
    release = {key: value for key, value in info.items() if key not in PLATFORM_FILES}
    versions = next(iter(runtimes.values()))["dependencies"]
    keep_lists = []
    if "windows" in runtimes and package["trimmed"]:
        keep_lists.append("winpack-keep-list.json")
    if "linux" in runtimes:
        keep_lists.append("linuxpack-keep-list.json")
    notice = NOTICE.format(
        python=PYTHON, platforms=" and ".join(platform.title() for platform in platforms),
        packages=", ".join(f"{name}=={version}" for name, version in versions.items()),
        keep_lists=" and ".join(keep_lists) or "the build audit",
        windows_state=("\nOn Windows, Merge Sectors keeps its board in %LOCALAPPDATA%\\disc-probe."
                       if "windows" in runtimes else ""),
    )
    members = {
        "release-build.json": json.dumps(dict(release, **runtimes, variant=variant, portable_packages=inventory),
                                         ensure_ascii=False, indent=2) + "\n",
        "package.json": json.dumps(dict(package, **runtimes, variant=variant), ensure_ascii=False, indent=2) + "\n",
        "NOTICE.txt": notice,
        **{name: download_doc(text, inventory) for name, text in docs.items()},
    }
    note = SINGLE_READ_FIRST[variant].encode("utf-8") if variant in SINGLE_READ_FIRST else read_first
    return {**{name: text.encode("utf-8") for name, text in members.items()}, READ_FIRST: note}


def store_metadata(archive, prefix, members, mode):
    with zipfile.ZipFile(archive, mode, compression=zipfile.ZIP_STORED) as output:
        for name, data in members.items():
            entry = zipfile.ZipInfo(f"{prefix}/{name}")
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            output.writestr(entry, data)


def verify_portable_archives(archives, inventory):
    inventories = {}
    for variant, archive in archives.items():
        prefix = archive.stem + "/"
        with zipfile.ZipFile(archive) as source:
            names = source.namelist()
            info = json.loads(source.read(prefix + "release-build.json"))
            if (len(set(names)) != len(names) or not all(name.startswith(prefix) for name in names)
                    or info["variant"] != variant or info["portable_packages"] != inventory):
                raise ValueError(f"inconsistent portable inventory in {archive.name}")
            hashes = {}
            for name in names:
                relative = name.removeprefix(prefix)
                if relative not in VARIANT_FILES:
                    with source.open(name) as data:
                        hashes[relative] = hashlib.file_digest(data, "sha256").hexdigest()
        inventories[variant] = hashes
    full = inventories["full"]
    if not {START_NAME, LINUX_START, "python/python.exe", "linux/python/bin/python3",
            "discprobe/data/troubleshoot.json"} <= full.keys():
        raise ValueError("full archive is missing a launcher, bundled interpreter or troubleshooting data")
    for variant, platforms in PORTABLE.items():
        omit = excluded_platform_files(platforms)
        expected = {path: digest for path, digest in full.items()
                    if path.split("/", 1)[0] not in omit
                    and not (variant == "linux-x86_64" and linux_batch_file(path))}
        if (inventories[variant] != expected
                or (variant == "linux-x86_64" and any(path.lower().endswith(".bat") for path in expected))):
            raise ValueError(f"{variant} payload differs from the shared build")
    print(f"Portable payload verified: {sum(path.startswith('discprobe/') for path in full)} application files "
          "and matching platform files.", flush=True)


def pack_portable(root, directory, label, info, package):
    archives = {variant: directory / f"disc-probe-{label}-{variant}.zip" for variant in PORTABLE}
    docs = {name: (root / name).read_text(encoding="utf-8") for name in DOWNLOAD_DOCS}
    read_first = (root / READ_FIRST).read_bytes()
    for variant, archive in archives.items():
        omit = excluded_platform_files(PORTABLE[variant]) | set(DOWNLOAD_DOCS) | VARIANT_FILES
        write_payload(root, archive, omit, skip_linux_batch=variant == "linux-x86_64")
    payload_bytes = {variant: archive.stat().st_size for variant, archive in archives.items()}
    inventory = {variant: dict(file=archive.name, size=0, platforms=list(PORTABLE[variant]))
                 for variant, archive in archives.items()}
    empty_zip = io.BytesIO()
    store_metadata(empty_zip, "", {}, "w")
    # Stored metadata grows only when a size gains a digit. Measure the small
    # metadata ZIPs to account for filenames and headers without recompressing payloads.
    for _ in range(10):
        additions = {variant: portable_metadata(variant, info, package, docs, read_first, inventory)
                     for variant in archives}
        sizes = {}
        for variant, archive in archives.items():
            probe = io.BytesIO()
            store_metadata(probe, archive.stem, additions[variant], "w")
            sizes[variant] = payload_bytes[variant] + probe.tell() - empty_zip.tell()
        if all(inventory[variant]["size"] == size for variant, size in sizes.items()):
            break
        for variant, size in sizes.items():
            inventory[variant]["size"] = size
    else:
        raise ValueError("portable ZIP sizes did not settle")
    for variant, archive in archives.items():
        store_metadata(archive, archive.stem, additions[variant], "a")
        if archive.stat().st_size != inventory[variant]["size"]:
            raise ValueError(f"portable ZIP size mismatch: {archive.name}")
    verify_portable_archives(archives, inventory)
    return archives.values()


def build_core(a, commit: str) -> None:
    root = fresh(a, f"disc-probe-{a.label}-core")
    copy_source(a, root)
    with open(os.path.join(root, "requirements.txt"), "w", encoding="ascii", newline="\n") as f:
        f.write("\n".join(PACKAGES) + "\n")
    with open(os.path.join(root, "package.json"), "w", encoding="utf-8") as f:
        json.dump(dict(ref=a.ref, commit=commit, worktree=a.worktree), f, indent=1)
    return root


def main(argv=None) -> None:
    global HERE
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", default="main")
    ap.add_argument("--label", default="main")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", help="read-only cache of original pinned archives and wheels (default OUT/cache)")
    ap.add_argument("--windows-cache", help="separate read-only Windows embed ZIP directory (default --cache)")
    ap.add_argument("--source-root", help="prepared release snapshot, paired with --commit")
    ap.add_argument("--commit", help="full provenance commit for a prepared snapshot")
    ap.add_argument("--worktree", action="store_true", help="include current uncommitted source")
    ap.add_argument("--audit-tests", action="store_true", help="trace the entire pytest suite as well")
    ap.add_argument("--test-deps", help="external directory containing locally copied pytest dependencies")
    ap.add_argument("--no-trim", action="store_true", help="measure an untrimmed pack with photo dependencies")
    a = ap.parse_args(argv)
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
    for kind in ("core", *PORTABLE):
        for suffix in (".zip", ".zip.sha256"):
            old = os.path.abspath(os.path.join(a.out, f"disc-probe-{a.label}-{kind}" + suffix))
            if os.path.dirname(old) != a.out:
                raise ValueError("archive path escaped output directory")
            if os.path.isfile(old):
                os.remove(old)
    cache = Path(a.cache or os.path.join(a.out, "cache")).resolve()
    windows_cache = Path(a.windows_cache or cache).resolve()
    if not all(allowed(path) for path in (cache, windows_cache)):
        raise ValueError("excluded cache path")
    with tempfile.TemporaryDirectory(dir=a.out, prefix="pack-stage-") as directory:
        a.build_root = directory
        stage = Path(directory)
        inputs = stage_inputs(cache, windows_cache, stage)
        build_bundle(a, stage, inputs)


def build_bundle(a, stage, inputs):
    commit = a.commit or subprocess.run(["git", "-C", HERE, "rev-parse", a.ref], check=True, capture_output=True, text=True).stdout.strip()
    core = build_core(a, commit)
    root = fresh(a, f"disc-probe-{a.label}-full")
    py = os.path.join(root, "python")
    os.makedirs(py)
    runtime, = (entry for entry in inputs["windows"] if entry["kind"] == "runtime")
    with zipfile.ZipFile(stage / "windows" / runtime["file"]) as z:
        if any(not allowed(member) for member in z.namelist()):
            raise ValueError("excluded Windows embed entry")
        z.extractall(py)
    tag = "python" + "".join(PYTHON.split(".")[:2])
    # Isolated by this file: nothing from the machine's own Python or environment gets in.
    with open(os.path.join(py, tag + "._pth"), "w", encoding="ascii") as f:
        f.write(f"{tag}.zip\n.\nLib\\site-packages\n..\nimport site\n")
    installed = stage / "windows-installed"
    versions = install_wheels(stage, "windows", installed, inputs["windows"])

    def windows_omit(directory, names):
        # Preserve the previous full bundle's OpenCV typing and package files.
        patterns = () if Path(directory).is_relative_to(installed / "cv2") else (*LEAVE_OUT, "bin", "Scripts")
        return ignore_files(patterns)(directory, names)

    shutil.copytree(installed, Path(py) / "Lib/site-packages",
                    ignore=windows_omit)
    copy_source(a, root)
    linux = build_linux(stage, root, inputs["linux"])
    write_start(root)
    with open(os.path.join(py, "shell.cmd"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(SHELL)
    build_info = Path(root) / "release-build.json"
    info = json.loads(build_info.read_text(encoding="utf-8")) if build_info.is_file() else dict(commit=commit)
    if "pack_inputs" in info and info["pack_inputs"] != inputs:
        raise ValueError("verified inputs differ from release preflight")
    windows = dict(python=PYTHON, dependencies=versions, embed_sha256=runtime["sha256"], runtime=runtime,
                   wheels={entry["name"]: entry for entry in inputs["windows"] if entry["kind"] == "wheel"})
    info = dict(info, windows=windows, linux=linux, pack_inputs=inputs)
    write_json(build_info, info)
    package = dict(ref=a.ref, commit=commit, worktree=a.worktree, audit_id=a.audit_id, trimmed=not a.no_trim)
    write_json(Path(root) / "package.json", dict(package, windows=windows, linux=linux))
    check_pack(a, root, "untrimmed")
    if not a.no_trim:
        trim_pack(a, root)
        check_pack(a, root, "trimmed")
    candidates = stage / "archives"
    candidates.mkdir()
    portable = pack_portable(Path(root), candidates, a.label, info, package)
    core_archive = candidates / (Path(core).name + ".zip")
    write_payload(Path(core), core_archive)
    pending = []
    for archive in (core_archive, *portable):
        digest = sha256(archive)
        checksum = archive.with_suffix(".zip.sha256")
        checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii", newline="\n")
        pending.extend((archive, checksum))
        print(f"{archive.name}: {archive.stat().st_size / 1e6:.3f} MB, commit {commit}, sha256 {digest[:20]}")
    published = []
    try:
        for candidate in pending:
            target = Path(a.out) / candidate.name
            candidate.replace(target)
            published.append(target)
    except OSError:
        for target in published:
            target.unlink()
        raise


if __name__ == "__main__":
    main()
