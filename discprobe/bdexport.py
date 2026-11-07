"""Turn a Blu-ray constant-linear-speed measurement into a DiscImageStudio Blu-ray preset.

DiscImageStudio models a Blu-ray layer as a spiral between two radii with a fixed channel bit
length: `BluRayDiscParameters` carries `TotalSectors`, `InnerRadiusMm`, `OuterRadiusMm` and an
optional pitch shape `p(x) = p0 (1 + c1 x + c2 x^2 + c3 x^3)`. With no coefficients the engine
solves one constant pitch from those three numbers, which is exactly the family a constant-pitch
BD-R or BD-RE lives in. So a preset needs three numbers, and a `geo --media bd` run measures two
of them: the radius of sector 0 and the pitch (or, equivalently, the linear speed).

The conversion is not a fit. The run already gives

    r0    the radius at LBA 0,
    p     the track pitch (anchored on the BD standard, or measured against a known speed),
    N     the sector count, from the disc's own last LBA,

and DiscImageStudio derives its radius at sector s from the same r^2 = r0^2 + p s S / pi, where
S = 30066.75 channel bits of 74.50 nm is one sector of track. Any two of (r0, p, outer radius)
fix the third, so whichever of them the run does not trust can be derived and the others written
down unchanged.

`pitchLinear`/`pitchQuadratic`/`pitchCubic` are relative shape coefficients, not a pitch: a
constant-pitch preset leaves them at 0 and lets the engine solve p from the radii and the track
length. Setting `pitchLinear = 0.32` would be read as "a pitch 1.32 times p0 at the outer edge",
which is why nothing here writes them.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import time

# ISO/IEC 30190 Blu-ray: one recording unit is 2760 run-in bits, 496 * 1932 channel bits of
# payload and 1104 run-out bits; 32 sectors to a unit; 74.50 nm per channel bit.
BD_BITS_PER_CLUSTER = 496 * 1932
BD_BITS_PER_RECORDING_UNIT = 2760 + BD_BITS_PER_CLUSTER + 1104      # 962 136
BD_SECTORS_PER_RECORDING_UNIT = 32
BD_CHANNEL_BIT_LENGTH_NM = 74.50
BD_SECTORS_PER_LAYER = 12_219_392
BD_NOMINAL_PITCH_UM = 0.320
BD_MAX_RADIUS_MM = 60.0
FILE_NAME = "blu-ray-presets.json"
SCHEMA_VERSION = 1


class BdPresetError(ValueError):
    """The measurement cannot be written as a preset DiscImageStudio will load."""


def sector_mm(bit_nm: float = BD_CHANNEL_BIT_LENGTH_NM) -> float:
    """Track length of one sector: 30066.75 channel bits of the given length."""
    return BD_BITS_PER_RECORDING_UNIT / BD_SECTORS_PER_RECORDING_UNIT * bit_nm * 1e-6


def track_length_mm(total_sectors: int, bit_nm: float = BD_CHANNEL_BIT_LENGTH_NM) -> float:
    return total_sectors * sector_mm(bit_nm)


def outer_radius_mm(inner_mm: float, pitch_um: float, total_sectors: int,
                    bit_nm: float = BD_CHANNEL_BIT_LENGTH_NM) -> float:
    """Radius the last sector reaches, from the same area identity the whole tool is built on."""
    area = pitch_um * 1e-3 * track_length_mm(total_sectors, bit_nm) / math.pi
    return math.sqrt(inner_mm * inner_mm + area)


def pitch_um_from_slope(slope_ms2_per_lba: float, v_m_s: float,
                        bit_nm: float = BD_CHANNEL_BIT_LENGTH_NM) -> float:
    """p = a v^2 / (4 pi S) for the T^2 slope, with T in ms, v in mm/ms and S in mm."""
    return slope_ms2_per_lba * v_m_s * v_m_s / (4 * math.pi * sector_mm(bit_nm)) * 1e3


def check(total_sectors: int, inner_mm: float, outer_mm: float, layer_count: int = 1) -> None:
    """The conditions DiscImageStudio's `BluRayDiscParameters.Validate` applies to a preset file."""
    if layer_count != 1:
        raise BdPresetError("DiscImageStudio writes single-layer Blu-ray discs only, so a preset "
                            "cannot describe a two-layer disc")
    if total_sectors <= 0 or total_sectors % BD_SECTORS_PER_RECORDING_UNIT or total_sectors > BD_SECTORS_PER_LAYER:
        raise BdPresetError(f"DiscImageStudio needs a sector count that is a positive multiple of "
                            f"{BD_SECTORS_PER_RECORDING_UNIT} and no more than {BD_SECTORS_PER_LAYER}; "
                            f"--sectors {total_sectors} is none of those")
    if not (0 < inner_mm < outer_mm <= BD_MAX_RADIUS_MM):
        raise BdPresetError(f"DiscImageStudio needs 0 < inner < outer <= {BD_MAX_RADIUS_MM:g} mm; this "
                            f"measurement came out inner {inner_mm:.3f}, outer {outer_mm:.3f} mm")


def parameters(fit: dict, total_sectors: int, *, inner_mm: float | None = None,
               outer_mm: float | None = None, pitch_um: float | None = None,
               bit_nm: float = BD_CHANNEL_BIT_LENGTH_NM) -> dict:
    """The `parameters` object of a Blu-ray preset, from a `model: "clv"` geo fit.

    `inner_mm`, `outer_mm` and `pitch_um` override what the run measured; any of them that is
    left out is measured or derived, and one derived value is enough to close the set.
    """
    anchors = fit.get("dis_equivalent") if fit.get("media") == "bd" else None
    anchors = anchors if isinstance(anchors, dict) else {}
    p = pitch_um if pitch_um is not None else fit.get("pitch_um")
    if p is None:
        p = anchors.get("pitch_um_estimate")     # the angle ladder measures v = p/b
    if p is None:
        v = fit.get("v_m_s")
        slope = fit.get("slope_ms2_per_lba")
        if v is None or slope is None:
            raise BdPresetError("this run measured neither a pitch nor a linear speed, so there is no "
                                "pitch to write down (anchor one with --pitch-um or --linear-mm-s)")
        p = pitch_um_from_slope(slope, v, bit_nm)
    r0 = inner_mm if inner_mm is not None else fit.get("r0_mm")
    if r0 is None:
        r0 = anchors.get("inner_radius_mm")      # ... and u = r0/b
    if r0 is None:
        raise BdPresetError("this geo fit has no r0_mm")
    r_out = outer_mm if outer_mm is not None else outer_radius_mm(r0, p, total_sectors, bit_nm)
    check(total_sectors, r0, r_out)
    return {"totalSectors": int(total_sectors), "layerCount": 1, "innerRadiusMm": float(r0),
            "outerRadiusMm": float(r_out), "startAngleDegrees": 0.0}


def preset(fit: dict, total_sectors: int, preset_id: str, name: str, description: str, *,
           inner_mm: float | None = None, outer_mm: float | None = None, pitch_um: float | None = None,
           bit_nm: float = BD_CHANNEL_BIT_LENGTH_NM, invert: bool = False) -> dict:
    """The `{id, displayName, parameters, invertMapping}` record the BD catalog stores."""
    params = parameters(fit, total_sectors, inner_mm=inner_mm, outer_mm=outer_mm, pitch_um=pitch_um,
                        bit_nm=bit_nm)
    return {"id": preset_id, "displayName": name, "description": description, **params,
            "invertMapping": bool(invert)}


def document(preset_obj: dict) -> dict:
    """The shape `BluRayPresetStore.Import` accepts (`parameters` plus `luminanceMapping`)."""
    params = {k: preset_obj[k] for k in ("totalSectors", "layerCount", "innerRadiusMm", "outerRadiusMm",
                                         "startAngleDegrees") if k in preset_obj}
    return {"parameters": params, "luminanceMapping": {"invert": bool(preset_obj.get("invertMapping", False))},
            "source": {k: preset_obj[k] for k in ("id", "displayName", "description") if k in preset_obj},
            "measuredWith": "discprobe geo --media bd"}


def catalog_entry(preset_obj: dict) -> dict:
    """The record the `blu-ray-presets.json` catalog keeps (its `Entry` has no description field)."""
    return {"id": preset_obj["id"], "displayName": preset_obj["displayName"],
            "parameters": {k: preset_obj[k] for k in ("totalSectors", "layerCount", "innerRadiusMm",
                                                      "outerRadiusMm", "startAngleDegrees")},
            "invertMapping": bool(preset_obj.get("invertMapping", False))}


def default_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "DiscImageStudio", FILE_NAME)


def read_catalog(path: str) -> dict:
    """The catalog file, or an empty one when it does not exist yet."""
    if not os.path.exists(path):
        return {"schemaVersion": SCHEMA_VERSION, "presets": []}
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if not text.strip():
        return {"schemaVersion": SCHEMA_VERSION, "presets": []}
    try:
        document_in = json.loads(text)
    except json.JSONDecodeError as e:
        raise BdPresetError(f"{path} is not plain JSON ({e.msg} at line {e.lineno}); DiscImageStudio "
                            "accepts comments there, but this tool does not rewrite a file it cannot "
                            "read back unchanged, so the file was left alone") from None
    if not isinstance(document_in, dict) or not isinstance(document_in.get("presets"), list):
        raise BdPresetError(f"{path} has no presets list, so it is not a Blu-ray preset catalog "
                            "(DiscImageStudio writes one as {\"schemaVersion\": 1, \"presets\": [...]})")
    version = document_in.get("schemaVersion")
    if version not in (None, SCHEMA_VERSION):
        raise BdPresetError(f"{path} says schemaVersion {version}; this tool writes schema "
                            f"{SCHEMA_VERSION} and will not guess how another version lays its "
                            "presets out")
    document_in.setdefault("schemaVersion", SCHEMA_VERSION)
    return document_in


def _same(left: dict, right: dict) -> bool:
    return all(left.get(k) == v for k, v in right.items())


def install(preset_obj: dict, path: str | None = None, replace: bool = False) -> dict:
    """Write one preset into the DiscImageStudio Blu-ray catalog, leaving everything else intact.

    `DiscImageStudio` keeps Blu-ray presets in their own file (`blu-ray-presets.json`), apart from
    the CD and DVD catalogs, so this never touches `disc-presets.json`.
    """
    target = os.path.abspath(path or default_path())
    entry = catalog_entry(preset_obj)
    catalog = read_catalog(target)
    items = catalog["presets"]
    created = not os.path.exists(target)
    action, index = "added", None
    for i, existing in enumerate(items):
        if isinstance(existing, dict) and existing.get("id") == entry["id"]:
            index = i
            if _same({k: v for k, v in existing.items() if k != "id"},
                     {k: v for k, v in entry.items() if k != "id"}):
                action = "unchanged"
            elif replace:
                action = "replaced"
            else:
                action = "exists"
            break
    version = catalog.get("schemaVersion", SCHEMA_VERSION)
    backup = None
    if action in ("unchanged", "exists"):
        if action == "exists":
            raise BdPresetError(f"{target} already has a preset called '{entry['id']}' with other "
                                "values; pass --replace to overwrite it")
        return {"path": target, "action": action, "created": False, "backup": None, "from_schema": version}
    if action == "replaced":
        items[index] = entry
    else:
        items.append(entry)
    if not created:
        backup = f"{target}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
        suffix = 1
        while os.path.exists(backup):
            backup = f"{target}.{time.strftime('%Y%m%d-%H%M%S')}-{suffix}.bak"
            suffix += 1
        shutil.copy2(target, backup)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    temporary = target + ".tmp"
    with open(temporary, "w", encoding="utf-8", newline="\n") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(temporary, target)
    return {"path": target, "action": action, "created": created, "backup": backup, "from_schema": version}


def export(geo_summary: str, total_sectors: int, out_path: str, preset_id: str, name: str, *,
           inner_mm: float | None = None, outer_mm: float | None = None, pitch_um: float | None = None,
           bit_nm: float = BD_CHANNEL_BIT_LENGTH_NM) -> dict:
    """Build the preset for one CLV run and, when `out_path` is given, write the importable document."""
    with open(geo_summary, encoding="utf-8") as f:
        run = json.load(f)
    fit = run.get("fit", {})
    angular = fit.get("model") != "clv"
    if angular:
        anchors = fit.get("dis_equivalent") if fit.get("media") == "bd" else None
        if not isinstance(anchors, dict):
            raise BdPresetError("this geo result is neither a Blu-ray run nor a constant-linear-speed one; a "
                                "DVD or CD preset comes from `disexport` without --media bd")
        # The angle ladder measures u = r0/b and v = p/b, so the two numbers a Blu-ray preset needs are
        # already in the result and nothing is fitted again here.
        fit = {**fit, "r0_mm": anchors.get("inner_radius_mm"),
               "pitch_um": anchors.get("pitch_um_estimate"), "zones_used": fit.get("rungs"),
               "r2": None, "v_m_s": None, "anchor": "the angle ladder (u = r0/b, v = p/b)"}
    params = parameters(fit, total_sectors, inner_mm=inner_mm, outer_mm=outer_mm, pitch_um=pitch_um,
                        bit_nm=bit_nm)
    anchors = fit.get("dis_equivalent") if fit.get("media") == "bd" else None
    anchors = anchors if isinstance(anchors, dict) else {}
    p = pitch_um if pitch_um is not None else fit.get("pitch_um")
    if p is None:
        p = anchors.get("pitch_um_estimate")     # the angle ladder measures v = p/b
    if p is None:
        p = pitch_um_from_slope(fit["slope_ms2_per_lba"], fit["v_m_s"], bit_nm)
    if angular:
        chi2 = fit.get("chi2_per_dof")
        desc = (f"Drive-timing calibration (discprobe, angle ladder: u = r0/b, v = p/b); "
                f"{fit.get('rungs', '?')} rungs, chi^2/dof {'?' if chi2 is None else f'{chi2:.2f}'}, "
                f"r0 {params['innerRadiusMm']:.4f} mm, pitch {p:.4f} um")
    else:
        desc = (f"Drive-timing calibration (discprobe, constant linear speed){'; pitch anchored' if fit.get('pitch_um_anchor') else ''}; "
                f"{fit.get('zones_used', '?')} zones, R^2 {fit.get('r2', float('nan')):.6f}, "
                f"r0 {params['innerRadiusMm']:.4f} mm, pitch {p:.4f} um")
    obj = preset(fit, total_sectors, preset_id, name, desc, inner_mm=params["innerRadiusMm"],
                 outer_mm=params["outerRadiusMm"], pitch_um=p, bit_nm=bit_nm)
    out = {"preset": obj, "document": document(obj),
           "fit": {k: fit.get(k) for k in ("model", "anchor", "r0_mm", "pitch_um", "v_m_s", "r2",
                                           "zones_used", "sigma_r0_mm", "offset_ms", "sigma_offset_ms",
                                           "chi2_per_dof", "rungs")},
           "derived": {"pitch_um": p, "sector_mm": sector_mm(bit_nm),
                       "track_length_mm": track_length_mm(total_sectors, bit_nm),
                       "outer_from_pitch_mm": outer_radius_mm(params["innerRadiusMm"], p, total_sectors, bit_nm)},
           "source": {"geo": os.path.basename(geo_summary.replace("\\", "/"))},
           "written": None}
    if out_path:
        # What goes to the file is the shape `BluRayPresetStore.Import` reads: `parameters` at the
        # root. Everything else the run says stays in the returned report and on the screen.
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out["document"], f, indent=2, ensure_ascii=False)
            f.write("\n")
        out["written"] = os.path.abspath(out_path)
    return out
