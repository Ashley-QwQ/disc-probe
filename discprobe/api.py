"""The core/GUI socket. Range grammar is deliberately small and shared with the GUI."""
from __future__ import annotations

import json
from pathlib import Path
import re

from .version import __version__

API_VERSION = "1.0"
SUPPORTED_OLDER_API_MAJORS = ()  # No earlier public API major exists yet.
CAPABILITIES = (
    "state", "drives-info", "jobs-events", "timing", "geo", "image-design",
    "editor", "burn", "photo-calibration", "phone-link", "presets",
    "catalogue", "results-history", "greetings", "templates", "presets-io", "works",
)
BUNDLED_GUI = Path(__file__).with_name("web")
_VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)", re.ASCII)
_BOUND = re.compile(r"(>=|<=|>|<|=)(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?", re.ASCII)


def version_payload():
    return dict(core_version=__version__, api_version=API_VERSION,
                capabilities=list(CAPABILITIES),
                supported_older_api_majors=list(SUPPORTED_OLDER_API_MAJORS))


def api_bounds(required):
    """Space-separated AND comparisons, e.g. >=1.0 <2. No implicit OR or prereleases."""
    if not isinstance(required, str) or not required.strip():
        raise ValueError("required_api must be a range such as >=1.0 <2")
    bounds = []
    for token in required.split():
        match = _BOUND.fullmatch(token)
        if not match:
            raise ValueError("required_api must use space-separated comparisons such as >=1.0 <2")
        op, major, minor = match.groups()
        bounds.append((op, (int(major), int(minor or 0))))
    return bounds


def api_matches(version, required):
    if not isinstance(version, str) or not _VERSION.fullmatch(version):
        return False
    value = tuple(map(int, version.split(".")))
    return all({">=": value >= bound, "<=": value <= bound, ">": value > bound,
                "<": value < bound, "=": value == bound}[op]
               for op, bound in api_bounds(required))


def load_manifest(folder):
    """Validate a pack without executing anything from it."""
    root = Path(folder).expanduser().resolve()
    try:
        manifest = json.loads((root / "gui.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError("GUI folder needs a valid gui.json / GUI 文件夹需要有效的 gui.json") from exc
    if not isinstance(manifest, dict):
        raise ValueError("gui.json must be an object / gui.json 必须是对象")
    for key in ("name", "gui_version", "required_api"):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise ValueError(f"gui.json: {key} must be a nonempty string / 必须是非空字符串")
    api_bounds(manifest["required_api"])
    for key in ("required_capabilities", "optional_capabilities"):
        values = manifest.get(key)
        if (not isinstance(values, list) or
                any(not isinstance(v, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", v, re.ASCII) for v in values) or
                len(set(values)) != len(values)):
            raise ValueError(f"gui.json: {key} must be a list of unique capability names / 必须是能力名称列表")
    if set(manifest["required_capabilities"]) & set(manifest["optional_capabilities"]):
        raise ValueError("gui.json: required and optional capabilities overlap / 必需与可选能力重复")
    if not (root / "home" / "index.html").is_file():
        raise ValueError("GUI folder needs home/index.html / GUI 文件夹缺少 home/index.html")
    return root, manifest


def check_manifest(manifest, payload=None):
    payload = version_payload() if payload is None else payload
    if not api_matches(payload["api_version"], manifest["required_api"]):
        value = tuple(map(int, payload["api_version"].split(".")))
        above = any((op in ("<", "<=", "=") and value > bound) or (op == "<" and value == bound)
                    for op, bound in api_bounds(manifest["required_api"]))
        if above:
            raise ValueError("GUI API range does not match; update the GUI pack. / GUI API 范围不兼容，请更新 GUI 包。")
        raise ValueError("GUI API range does not match; update the core. / GUI API 范围不兼容，请更新核心。")
    missing = set(manifest["required_capabilities"]) - set(payload["capabilities"])
    if missing:
        raise ValueError("Update the core; GUI requires capabilities / 请更新核心，GUI 缺少必需能力: " + ", ".join(sorted(missing)))
    return set(manifest["optional_capabilities"]) - set(payload["capabilities"])
