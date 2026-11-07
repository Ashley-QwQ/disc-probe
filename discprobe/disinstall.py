"""Add an exported preset to DiscImageStudio's user preset file.

DiscImageStudio keeps user presets in %LOCALAPPDATA%\\DiscImageStudio\\disc-presets.json
and reads the file once, at startup. The file is JSON but the app's reader also accepts
comments and trailing commas, so reading here tolerates those too. Writing produces plain
JSON in the shape the app itself saves, keeping the top-level keys and the presets that are
already there.

Only that one file is touched. A preset whose id is already present is left alone when its
values match, refused when they differ (unless --replace is given), and enabled again when
its id sits in the matching disabled list.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import tempfile

FILE_NAME = "disc-presets.json"
CURRENT_SCHEMA = 4
MAX_UINT = 2 ** 32 - 1
FAMILIES = {"cd": ("cdPresets", "disabledCdPresetIds"), "dvd": ("dvdPresets", "disabledDvdPresetIds")}


class InstallError(ValueError):
    """Something about the file or the preset makes the install unsafe."""


def default_path() -> str:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise InstallError("no %LOCALAPPDATA% here; pass --dis-presets with the path of DiscImageStudio's "
                           "disc-presets.json")
    return os.path.join(base, "DiscImageStudio", FILE_NAME)


def install(preset: dict, path: str | None = None, replace: bool = False) -> dict:
    """Merge `preset` into the user preset file and return what happened.

    Keys: action (added, replaced, enabled, unchanged), path, backup, created, count,
    upgraded. The file is not rewritten when the preset is already there unchanged.
    """
    family = _family(preset)
    _validate_preset(preset)
    path = os.path.abspath(path or default_path())
    document, text = _read(path)
    created = document is None
    if created:
        document = {"schemaVersion": CURRENT_SCHEMA, "cdPresets": [], "dvdPresets": [],
                    "bluRayPresets": [], "disabledCdPresetIds": [], "disabledDvdPresetIds": [],
                    "disabledBluRayPresetIds": []}
        upgraded = False
    else:
        upgraded = _prepare_document(document, path)
    items_key, disabled_key = FAMILIES[family]
    items = document[items_key]
    index = next((i for i, item in enumerate(items) if item.get("id") == preset["id"]), None)
    disabled = document.get(disabled_key)
    was_disabled = isinstance(disabled, list) and preset["id"] in disabled

    if index is None:
        items.append(preset)
        action = "added"
    elif items[index] != preset:
        if not replace:
            raise InstallError(f"preset '{preset['id']}' is already in {path} with different values; "
                               f"pass --replace to overwrite it, or --id to add it under another id")
        items[index] = preset
        action = "replaced"
    else:
        action = "unchanged"
    if was_disabled:
        disabled.remove(preset["id"])
        if action == "unchanged":
            action = "enabled"
    changed = created or upgraded or action != "unchanged"
    backup = None
    if changed:
        if not created:
            backup = path + ".bak"
            try:
                shutil.copy2(path, backup)
            except OSError as e:
                raise InstallError(f"cannot back up {path}: {e.strerror or e}") from None
        crlf = text is not None and "\r\n" in text
        try:
            _write_atomic(path, _render(document, crlf))
        except OSError as e:
            raise InstallError(f"cannot write {path}: {e.strerror or e}") from None
    return {"action": action, "path": path, "backup": backup, "created": created,
            "count": len(items), "upgraded": upgraded}


def _family(preset: dict) -> str:
    if not isinstance(preset, dict):
        raise InstallError("the preset is not a JSON object")
    has_cd, has_dvd = "sectors" in preset, "totalSectors" in preset
    if has_cd == has_dvd:
        raise InstallError("the preset needs exactly one of 'sectors' (CD) or 'totalSectors' (DVD)")
    return "cd" if has_cd else "dvd"


def _validate_preset(preset: dict) -> None:
    preset_id = preset.get("id")
    for key in ("id", "displayName", "description"):
        value = preset.get(key)
        if not isinstance(value, str) or not value.strip():
            raise InstallError(f"the preset has no {key}")
    if preset_id == "__manual__":
        raise InstallError("the preset id '__manual__' is reserved by DiscImageStudio")
    family = _family(preset)
    total_key = "sectors" if family == "cd" else "totalSectors"
    total = preset.get(total_key)
    if not _integer(total) or total <= 0:
        raise InstallError(f"the preset's {total_key} is not a positive integer")
    if family == "dvd" and total > MAX_UINT:
        raise InstallError("the preset's totalSectors does not fit DiscImageStudio's 32-bit field")
    inner, outer = preset.get("innerRadiusMm"), preset.get("outerRadiusMm")
    if not _number(inner) or not _number(outer) or inner <= 0 or outer <= 0:
        raise InstallError("the preset's radii are not positive numbers")
    if outer <= inner:
        raise InstallError("the preset's outer radius is not larger than its inner radius")
    pitches = [preset.get(key) for key in ("pitchLinear", "pitchQuadratic", "pitchCubic")]
    if not all(_number(value) for value in pitches):
        raise InstallError("the preset's pitch terms are not finite numbers")
    if not _pitch_positive(*pitches):
        raise InstallError("the preset's pitch does not stay positive over the whole disc")
    velocity_key = "linearVelocityMmPerSecond" if family == "cd" else "channelBitLengthNm"
    if velocity_key in preset:
        value = preset[velocity_key]
        if not _number(value) or value <= 0:
            raise InstallError(f"the preset's {velocity_key} is not a positive number")


def _number(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _pitch_positive(linear: float, quadratic: float, cubic: float) -> bool:
    """DiscImageStudio's check: 1 + c1 x + c2 x^2 + c3 x^3 must stay positive on [0, 1].

    It checks both ends and every stationary point of the cubic. Same arithmetic as
    DvdTrackGeometry.PositiveOnInterval, so a preset accepted here is accepted there.
    """
    def polynomial(x: float) -> float:
        return ((cubic * x + quadratic) * x + linear) * x + 1.0

    def positive(x: float) -> bool:
        value = polynomial(x)
        return math.isfinite(value) and value > 0

    first, last = 0.0, 1.0
    if not positive(first) or not positive(last):
        return False
    scale = max(abs(linear), abs(quadratic), abs(cubic))
    if scale == 0:
        return True
    a, b, c = 3 * (cubic / scale), 2 * (quadratic / scale), linear / scale

    def check(x: float) -> bool:
        return x <= first or x >= last or positive(x)

    if a == 0:
        return b == 0 or check(-c / b)
    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        return True
    q = -0.5 * (b + math.copysign(math.sqrt(discriminant), b))
    if q == 0:
        return check(-b / (2 * a))
    return check(q / a) and check(c / q)


def _read(path: str) -> tuple[dict | None, str | None]:
    try:
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    except FileNotFoundError:
        return None, None
    except OSError as e:
        raise InstallError(f"cannot read {path}: {e.strerror or e}") from None
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        try:
            document = json.loads(_strip_trailing_commas(_strip_comments(text)))
        except json.JSONDecodeError as e:
            raise InstallError(f"{path} is not valid JSON: {e.msg} at line {e.lineno}") from None
    if not isinstance(document, dict):
        raise InstallError(f"{path} does not hold a DiscImageStudio preset object")
    return document, text


def _strip_comments(text: str) -> str:
    """Drop // and /* */ comments, leaving string contents alone."""
    out = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _strip_trailing_commas(text: str) -> str:
    """Drop a comma that is followed only by whitespace and a closing bracket."""
    out = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _prepare_document(document: dict, path: str) -> bool:
    """Check the parts of the file this module needs, and migrate it to schema 4.

    Returns True when the document was migrated (the caller then writes it back).
    """
    version = document.get("schemaVersion")
    if not _integer(version) or version not in (2, 3, 4):
        raise InstallError(f"{path} has no DiscImageStudio schemaVersion (2, 3 or 4)")
    for key in ("cdPresets", "dvdPresets"):
        items = document.get(key)
        if not isinstance(items, list):
            raise InstallError(f"{path} has no {key} list")
        if any(not isinstance(item, dict) for item in items):
            raise InstallError(f"{path} has a {key} entry that is not an object")
    blu_ray = document.get("bluRayPresets")
    if blu_ray is not None and not isinstance(blu_ray, list):
        raise InstallError(f"{path} has a bluRayPresets value that is not a list")
    for key in ("disabledCdPresetIds", "disabledDvdPresetIds", "disabledBluRayPresetIds"):
        value = document.get(key)
        if value is not None and not isinstance(value, list):
            raise InstallError(f"{path} has a {key} value that is not a list")
    if version == CURRENT_SCHEMA:
        if blu_ray is None:
            document["bluRayPresets"] = []
            return True
        return False
    document["schemaVersion"] = CURRENT_SCHEMA
    if blu_ray is None:
        document["bluRayPresets"] = []
    return True


def _render(document: dict, crlf: bool) -> str:
    text = json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    return text.replace("\n", "\r\n") if crlf else text


def _write_atomic(path: str, text: str) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".disc-presets-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
