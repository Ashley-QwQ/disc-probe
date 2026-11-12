"""Add an exported preset to DiscImageStudio's user preset file.

DiscImageStudio keeps user presets in %LOCALAPPDATA%\\DiscImageStudio\\disc-presets.json
and reads the file once, at startup. The file is JSON but the app's reader also accepts
comments and trailing commas, so reading here tolerates those too. Writing produces plain
JSON in the shape the app itself saves, keeping the top-level keys and the presets that are
already there.

Only that one file is touched. A preset whose id is already present is left alone when its
values match, refused when they differ (unless --replace is given), and enabled again when
its id sits in the matching disabled list.

Comments and trailing commas are read but not kept: the rewrite is plain JSON, the same shape
the app itself saves. `install` says which of them it dropped so the caller can warn. A
comment that is never closed is refused, and so is writing to the file the export itself is
about to write (that would have eaten the user's presets before they were read).
"""

from __future__ import annotations

import datetime
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


def target_path(path: str | None = None) -> str:
    """Where the presets are written: --dis-presets or DiscImageStudio's own file."""
    return os.path.abspath(path or default_path())


def same_file(first: str, second: str) -> bool:
    """Whether two paths name one file, existing or not.

    samefile() is the honest test when both exist (it follows links and case); when one does
    not exist yet there is nothing to stat, so compare the normalised absolute paths.
    """
    first, second = os.path.abspath(first), os.path.abspath(second)
    try:
        return os.path.samefile(first, second)
    except OSError:
        return os.path.normcase(os.path.realpath(first)) == os.path.normcase(os.path.realpath(second))


def refuse_same_file(output: str, target: str) -> None:
    """Refuse an export that would overwrite the preset file before it is read.

    disexport writes --output first and installs afterwards. If both name one file the export
    has already replaced the presets (and there is no backup, because nothing was read yet),
    so this has to be checked before anything is written.
    """
    if same_file(output, target):
        raise InstallError(
            f"--output and the DiscImageStudio preset file are the same file ({target}). The export would "
            f"overwrite your presets before they are read, so nothing was written. Use another --output "
            f"name, or omit --output and let --install write only the preset file.")


def check_identity(preset_id: str | None, display_name: str | None) -> tuple[str | None, str | None]:
    """Clean the --id and --name the command line was given.

    None means the option was not used, and the caller supplies its own default. Surrounding
    whitespace is dropped, because DiscImageStudio shows the name and compares the id exactly as
    they are stored. An empty value and the reserved id `__manual__` are refused here, before an
    export writes a file whose preset DiscImageStudio would refuse as a whole.
    """
    if preset_id is not None:
        preset_id = preset_id.strip()
        if not preset_id:
            raise InstallError("--id is empty: DiscImageStudio needs an id to tell presets apart")
        if preset_id == "__manual__":
            raise InstallError("--id __manual__ is reserved by DiscImageStudio; choose another id")
    if display_name is not None:
        display_name = display_name.strip()
        if not display_name:
            raise InstallError("--name is empty: it is the name DiscImageStudio shows in its preset list")
    return preset_id, display_name


def install(preset: dict, path: str | None = None, replace: bool = False) -> dict:
    """Merge `preset` into the user preset file and return what happened.

    Keys: action (added, replaced, enabled, unchanged), path, backup, created, count,
    upgraded, dropped (the tolerant syntax the rewrite did not keep), kept (fields of the
    existing preset this tool does not write, and carried over), dropped_fields (fields of the
    existing preset left out because DiscImageStudio would refuse their value). The file is not
    rewritten when the preset is already there unchanged, and then nothing is reported as
    dropped, because nothing was written.
    """
    family = _family(preset)
    _validate_preset(preset)
    path = target_path(path)
    document, text, dropped = _read(path)
    created = document is None
    if created:
        document = {"schemaVersion": CURRENT_SCHEMA, "cdPresets": [], "dvdPresets": [],
                    "bluRayPresets": [], "disabledCdPresetIds": [], "disabledDvdPresetIds": [],
                    "disabledBluRayPresetIds": []}
        upgraded, from_schema = False, CURRENT_SCHEMA
    else:
        upgraded, from_schema = _prepare_document(document, path)
    items_key, disabled_key = FAMILIES[family]
    items = document[items_key]
    index = next((i for i, item in enumerate(items) if item.get("id") == preset["id"]), None)
    disabled = document.get(disabled_key)
    was_disabled = isinstance(disabled, list) and preset["id"] in disabled
    kept: list[str] = []
    dropped_fields: list[str] = []

    if index is None:
        items.append(preset)
        action = "added"
    elif _same_values(items[index], preset):
        action = "unchanged"
    elif not replace:
        raise InstallError(f"preset '{preset['id']}' is already in {path} with different values; "
                           f"pass --replace to overwrite it, or --id to add it under another id")
    else:
        kept = sorted(key for key in items[index] if key not in preset)
        merged = {**items[index], **preset}
        dropped_fields = _drop_unusable_fields(merged, "sectors" in preset)
        if dropped_fields:
            kept = [key for key in kept if key not in dropped_fields]
        items[index] = merged
        action = "replaced"
    if was_disabled:
        disabled.remove(preset["id"])
        if action == "unchanged":
            action = "enabled"
    changed = created or upgraded or action != "unchanged"
    # Only a file that is actually rewritten can lose its comments and trailing commas.
    dropped = dropped if changed else []
    backup = None
    if changed:
        if not created:
            backup = _backup_path(path)
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
            "count": len(items), "upgraded": upgraded, "from_schema": from_schema,
            "dropped": dropped, "kept": kept, "dropped_fields": dropped_fields}


def _drop_unusable_fields(preset: dict, cd: bool | None = None) -> list[str]:
    """Remove fields that would make the merged preset invalid for DiscImageStudio.

    A preset merged from an older one can carry values the current app refuses. It validates the
    whole file on load and falls back to the built-in presets when that fails, so one stale field
    would hide every user preset. `usableSectors` must be positive, within the total, and a
    multiple of 1 on CD and 16 elsewhere (DiscPresetJsonStore.ValidateUsableSectors); optional
    text must not be blank when it is present. The fields are dropped rather than refused: they
    are not ours, and a preset that would otherwise install is worth keeping.
    """
    dropped = []
    # What we just exported says which kind this is. A leftover from the other kind must not decide it.
    cd = "sectors" in preset if cd is None else cd
    other = "totalSectors" if cd else "sectors"
    if other in preset:
        del preset[other]
        dropped.append(other)
    if "usableSectors" in preset:
        total = preset.get("sectors" if cd else "totalSectors")
        usable = preset["usableSectors"]
        alignment = 1 if cd else 16
        if (not isinstance(usable, int) or isinstance(usable, bool) or not isinstance(total, int)
                or usable <= 0 or usable > total or usable % alignment):
            del preset["usableSectors"]
            dropped.append("usableSectors")
    for name in ("displayNameResourceKey", "descriptionResourceKey", "contributor"):
        value = preset.get(name)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            del preset[name]
            dropped.append(name)
    return dropped


def _same_values(existing: dict, preset: dict) -> bool:
    """Whether the existing preset already holds every field this tool writes.

    Extra fields are ignored: DiscImageStudio added an optional `usableSectors` in 1.5.0, and a
    preset that carries it is still the same preset. It is also why a replace merges instead of
    replacing wholesale, so that setting survives a re-export.
    """
    return all(existing.get(key) == value for key, value in preset.items())


def _backup_path(path: str) -> str:
    """A name that is new every time: the first backup is the file as it was before any install."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = f"{path}.{stamp}.bak"
    attempt = 1
    while os.path.exists(candidate):
        candidate = f"{path}.{stamp}-{attempt}.bak"
        attempt += 1
    return candidate


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


def _read(path: str) -> tuple[dict | None, str | None, list[str]]:
    """The parsed document, its text, and the syntax the rewrite will not keep."""
    try:
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    except FileNotFoundError:
        return None, None, []
    except OSError as e:
        raise InstallError(f"cannot read {path}: {e.strerror or e}") from None
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        try:
            uncommented = _strip_comments(text)
        except _UnclosedComment:
            raise InstallError(f"{path} has a /* comment with no closing */; the file was left alone. "
                               f"Close or remove the comment and run the install again.") from None
        trimmed = _strip_trailing_commas(uncommented)
        notes = []
        if uncommented != text:
            notes.append("comments")
        if trimmed != uncommented:
            notes.append("trailing commas")
        try:
            document = json.loads(trimmed)
        except json.JSONDecodeError as e:
            raise InstallError(f"{path} is not valid JSON: {e.msg} at line {e.lineno}") from None
    else:
        notes = []
    if not isinstance(document, dict):
        raise InstallError(f"{path} does not hold a DiscImageStudio preset object")
    return document, text, notes


class _UnclosedComment(ValueError):
    """A /* with no */ before the end of the file."""


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
            end = text.find("*/", i + 2)
            if end < 0:
                raise _UnclosedComment()
            i = end + 2
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


def _prepare_document(document: dict, path: str) -> tuple[bool, int]:
    """Check the parts of the file this module needs, and migrate it to schema 4.

    Returns whether the document was changed (the caller then writes it back) and the schema
    it was in, so the caller can say whether it was upgraded or only completed.
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
            return True, version
        return False, version
    document["schemaVersion"] = CURRENT_SCHEMA
    if blu_ray is None:
        document["bluRayPresets"] = []
    return True, version


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
