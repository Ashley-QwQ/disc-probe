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
# A burner writes a lead-out after the last sector and counts it against the disc, so a preset that
# claims every sector leaves an image the disc cannot take ("overburn 2 KB" with one burner, 1.12 MB
# with another: ImgBurn reserves about a megabyte for a Blu-ray lead-out). Two mebibytes covers that
# and costs 0.002 mm of radius, which is far below what this measurement can see.
USABLE_MARGIN_SECTORS = 1024
# A formatted disc's inner spare area is about a percent of the spiral; anything much shorter
# than that is a disc that was not filled, and its missing sectors are not in front of sector 0.
ISA0_MIN_FRACTION = 0.90
# An inner spare area is a fixed percent of the spiral: 4096 clusters, 131 072 sectors, on a
# 25 GB disc. A shortfall smaller than a thousand clusters is a lead-out margin or simply a
# disc with fewer sectors, and pulling sector 0 back for it would move the spiral for nothing.
ISA0_MIN_SECTORS = BD_SECTORS_PER_RECORDING_UNIT * 1024
FILE_NAME = "disc-presets.json"
SCHEMA_VERSION = 4
BD_PRESET_LIST = "bluRayPresets"
CATALOG_LISTS = ("cdPresets", "dvdPresets", BD_PRESET_LIST,
                 "disabledCdPresetIds", "disabledDvdPresetIds", "disabledBluRayPresetIds")


class BdPresetError(ValueError):
    """The measurement cannot be written as a preset DiscImageStudio will load."""


def pitch_mm(pitch_um: float) -> float:
    """Track pitch in millimetres from the micrometres the command line speaks in."""
    return float(pitch_um) * 1e-3


def sector_mm(bit_nm: float = BD_CHANNEL_BIT_LENGTH_NM) -> float:
    """Track length of one sector: 30066.75 channel bits of the given length."""
    return BD_BITS_PER_RECORDING_UNIT / BD_SECTORS_PER_RECORDING_UNIT * bit_nm * 1e-6


def track_length_mm(total_sectors: int, bit_nm: float = BD_CHANNEL_BIT_LENGTH_NM) -> float:
    return total_sectors * sector_mm(bit_nm)


def twist_turns(inner_mm: float, outer_mm: float, pitch_um: float) -> float:
    """How many turns the spiral makes between those two radii."""
    return (outer_mm - inner_mm) / (pitch_um * 1e-3)


def twist_pitch_ppm(inner_mm: float, outer_mm: float, pitch_um: float, twist_deg: float,
                    at_mm: float | None = None) -> float:
    """The pitch error that puts the picture `twist_deg` out of true, read at `at_mm`.

    A picture is placed at radii; the disc's own spiral turns by `2 pi (r - r0) / p` out to those
    radii. Let the pitch be a relative `eps` too large and the same sector lands at
    `theta = 2 pi (r_t - r0) / (p (1 + eps))`, which is short of where the layout put it by

        d_theta = pi * eps * (r - r0)^2 / (p * r),

    quadratic in the distance from the inner edge: near the hub almost nothing, at the rim a whole
    wedge. The 3.4-fold difference from the naive `eps * turns` counting comes from the radius:
    the sector also sits a little further out (`eps (r^2 - r0^2) / 2r`), and being further out
    earns most of the angle back, so what is left is the quadratic residual.

    That also says what this correction can and cannot do. A preset can only move the pitch its
    layout implies, so it can take out a shear of this (pitch) kind and nothing else. A picture
    sheared by an angular scale error instead falls off linearly in `(r - r0)`, and no pitch will
    pull it straight -- which is what the second burn is for: it either comes down or it is the
    another kind.
    """
    r = float(outer_mm if at_mm is None else at_mm)
    span = r - float(inner_mm)
    if span <= 0:
        raise BdPresetError(f"an angle read at {r:g} mm says nothing about a disc whose inner radius "
                            f"is {inner_mm:g} mm")
    p_mm = pitch_um * 1e-3
    eps = math.radians(abs(float(twist_deg))) * p_mm * r / (math.pi * span * span)
    return math.copysign(eps * 1e6, float(twist_deg))


def outer_radius_mm(inner_mm: float, pitch_um: float, total_sectors: int,
                    bit_nm: float = BD_CHANNEL_BIT_LENGTH_NM) -> float:
    """Radius the last sector reaches, from the same area identity the whole tool is built on."""
    area = pitch_um * 1e-3 * track_length_mm(total_sectors, bit_nm) / math.pi
    return math.sqrt(inner_mm * inner_mm + area)


def pitch_um_from_slope(slope_ms2_per_lba: float, v_m_s: float,
                        bit_nm: float = BD_CHANNEL_BIT_LENGTH_NM) -> float:
    """p = a v^2 / (4 pi S) for the T^2 slope, with T in ms, v in mm/ms and S in mm."""
    return slope_ms2_per_lba * v_m_s * v_m_s / (4 * math.pi * sector_mm(bit_nm)) * 1e3


def pullback_inner_mm(r0_mm: float, pitch_um: float, sectors: int,
                       bit_nm: float = BD_CHANNEL_BIT_LENGTH_NM) -> float:
    """The radius of a sector this many sectors *inside* the measured LBA 0.

    A formatted BD-RE starts its logical LBA 0 after an inner spare area (four thousand and
    ninety-six clusters on a 25 GB disc, 131 072 sectors), so the measured r0 is that much
    further out than the physical start of the data zone. Walking the same spiral backwards
    over those sectors gives the start of the data zone, which is where an unspared BD-R
    begins to write.
    """
    area = r0_mm * r0_mm - pitch_mm(pitch_um) * sector_mm(bit_nm) * int(sectors) / math.pi
    if area <= 0:
        raise BdPresetError(f"{sectors:,} sectors back from LBA 0 would leave no radius at all; "
                            "the measured inner radius and the pitch cannot both be right")
    return math.sqrt(area)


def usable_sectors_for(total_sectors: int, usable_sectors: int | None = None) -> int:
    """Sectors a project may fill, by default one recording unit short of the disc.

    A preset that claims `totalSectors` usable builds an image the disc cannot take, because the
    burner still has to write a lead-out inside it. Two mebibytes is enough for the burners seen
    here and moves the outer radius by 0.002 mm, which no run of this tool could resolve.
    """
    usable = total_sectors - USABLE_MARGIN_SECTORS if usable_sectors is None else int(usable_sectors)
    if usable <= 0:
        usable = total_sectors
    if usable > total_sectors:
        raise BdPresetError(f"usable sector count {usable} is more than the disc holds ({total_sectors})")
    usable -= usable % BD_SECTORS_PER_RECORDING_UNIT
    if usable <= 0:
        raise BdPresetError(f"usable sector count rounded down to a multiple of "
                            f"{BD_SECTORS_PER_RECORDING_UNIT} leaves nothing to write")
    return usable


def check(total_sectors: int, inner_mm: float, outer_mm: float, layer_count: int = 1,
          usable_sectors: int | None = None) -> None:
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
    if usable_sectors is not None:
        if usable_sectors <= 0 or usable_sectors > total_sectors or usable_sectors % BD_SECTORS_PER_RECORDING_UNIT:
            raise BdPresetError(f"DiscImageStudio needs 0 < usable <= {total_sectors} sectors and a "
                                f"multiple of {BD_SECTORS_PER_RECORDING_UNIT}; {usable_sectors} is not "
                                "useable")


def parameters(fit: dict, total_sectors: int, *, inner_mm: float | None = None,
               outer_mm: float | None = None, pitch_um: float | None = None,
               bit_nm: float = BD_CHANNEL_BIT_LENGTH_NM,
               usable_sectors: int | None = None,
               measured_sectors: int | None = None, pullback_isa0: bool = False,
               twist_deg: float | None = None, twist_at_mm: float | None = None) -> dict:
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
    if pullback_isa0 and measured_sectors and total_sectors > measured_sectors:
        # A spare area is a fixed few percent of the disc; a disc that simply was not filled can be
        # most of the way short, and moving its sector 0 inwards would be wrong by millimetres.
        if measured_sectors < ISA0_MIN_FRACTION * total_sectors:
            raise BdPresetError(
                f"this disc was measured up to sector {measured_sectors:,} of {total_sectors:,}: that is "
                f"too short to be a spare area, so the missing sectors are probably unrecorded rather "
                f"than reserved, and pulling them back in front of sector 0 would move it by "
                f"{r0 - pullback_inner_mm(r0, p, total_sectors - measured_sectors, bit_nm):.3f} mm. "
                f"Leave --pullback-isa0 off for a disc that was not filled")
        r0 = pullback_inner_mm(r0, p, total_sectors - measured_sectors, bit_nm)
    if twist_deg:
        # The dial says how far the picture is sheared; the timing measured only c = pi r0^2 / (p S).
        # Correcting the pitch therefore has to carry r0 with it: c stays what was measured.
        disc_end = outer_mm if outer_mm is not None else outer_radius_mm(r0, p, total_sectors, bit_nm)
        eps = twist_pitch_ppm(r0, disc_end, p, twist_deg, at_mm=twist_at_mm or disc_end) * 1e-6
        p = p * (1.0 + eps)
        if inner_mm is None:                    # a measured r0 scales with the pitch; a given one does not
            r0 = r0 * math.sqrt(1.0 + eps)
    r_out = outer_mm if outer_mm is not None else outer_radius_mm(r0, p, total_sectors, bit_nm)
    usable = usable_sectors_for(total_sectors, usable_sectors)
    check(total_sectors, r0, r_out, usable_sectors=usable)
    return {"totalSectors": int(total_sectors), "layerCount": 1, "innerRadiusMm": float(r0),
            "outerRadiusMm": float(r_out), "startAngleDegrees": 0.0, "usableSectors": int(usable)}


def preset(fit: dict, total_sectors: int, preset_id: str, name: str, description: str, *,
           inner_mm: float | None = None, outer_mm: float | None = None, pitch_um: float | None = None,
           bit_nm: float = BD_CHANNEL_BIT_LENGTH_NM, invert: bool = False,
           usable_sectors: int | None = None, measured_sectors: int | None = None,
           pullback_isa0: bool = False) -> dict:
    """The `{id, displayName, parameters, invertMapping}` record the BD catalog stores."""
    params = parameters(fit, total_sectors, inner_mm=inner_mm, outer_mm=outer_mm, pitch_um=pitch_um,
                        bit_nm=bit_nm, usable_sectors=usable_sectors,
                        measured_sectors=measured_sectors, pullback_isa0=pullback_isa0)
    return {"id": preset_id, "displayName": name, "description": description, **params,
            "invertMapping": bool(invert)}


def document(preset_obj: dict) -> dict:
    """The shape `BluRayPresetStore.Import` accepts (`parameters` plus `luminanceMapping`)."""
    params = {k: preset_obj[k] for k in ("totalSectors", "layerCount", "innerRadiusMm", "outerRadiusMm",
                                         "startAngleDegrees", "usableSectors") if k in preset_obj}
    return {"parameters": params, "luminanceMapping": {"invert": bool(preset_obj.get("invertMapping", False))},
            "source": {k: preset_obj[k] for k in ("id", "displayName", "description") if k in preset_obj},
            "measuredWith": "discprobe geo --media bd"}


def catalog_entry(preset_obj: dict) -> dict:
    """The record `disc-presets.json` keeps under `bluRayPresets` (schema 4: flat fields).

    DiscImageStudio's own user Blu-ray preset looks like this — `totalSectors`, the two radii and
    the polarity, with no nested `parameters` object and no `layerCount` (one layer is the only
    thing it supports). `BluRayPresetStore` in the source tree writes a different file with a
    nested shape, but nothing in the app reads it, so this is the shape that reaches the UI.
    """
    entry = {"id": preset_obj["id"], "displayName": preset_obj["displayName"],
             "totalSectors": int(preset_obj["totalSectors"]),
             "innerRadiusMm": float(preset_obj["innerRadiusMm"]),
             "outerRadiusMm": float(preset_obj["outerRadiusMm"]),
             "invertMapping": bool(preset_obj.get("invertMapping", False))}
    if preset_obj.get("usableSectors") is not None:
        entry["usableSectors"] = int(preset_obj["usableSectors"])
    description = str(preset_obj.get("description") or "").strip()
    if description:       # DiscImageStudio rejects a description that is present but blank
        entry["description"] = description
    return entry


def suggested_file_name(display_name: str, suffix: str = ".json") -> str:
    """The file name that becomes the preset name when DiscImageStudio imports it.

    `BluRayPresetStore.Import` builds the entry from the parameters and takes the *file name* as
    the preset's display name, so a document written to `dis_preset_bd.json` adds a preset called
    "dis_preset_bd" however good the name inside the file is.
    """
    bad = set('<>:"/\\|?*')
    cleaned = "".join("-" if (ch in bad or ord(ch) < 32) else ch for ch in str(display_name))
    cleaned = " ".join(cleaned.split()).strip(" .")
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip(" .")
    return (cleaned or "Blu-ray preset") + suffix


def default_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "DiscImageStudio", FILE_NAME)


def read_catalog(path: str) -> dict:
    """The preset file, or an empty schema-4 one when it does not exist yet."""
    if not os.path.exists(path):
        return {"schemaVersion": SCHEMA_VERSION, **{name: [] for name in CATALOG_LISTS}}
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if not text.strip():
        return {"schemaVersion": SCHEMA_VERSION, **{name: [] for name in CATALOG_LISTS}}
    try:
        document_in = json.loads(text)
    except json.JSONDecodeError as e:
        raise BdPresetError(f"{path} is not plain JSON ({e.msg} at line {e.lineno}); DiscImageStudio "
                            "accepts comments there, but this tool does not rewrite a file it cannot "
                            "read back unchanged, so the file was left alone") from None
    if not isinstance(document_in, dict) or not isinstance(document_in.get(BD_PRESET_LIST), list):
        raise BdPresetError(f"{path} has no {BD_PRESET_LIST} list, so it is not the DiscImageStudio "
                            f"preset file this tool knows (it writes a file with schemaVersion 4 and a "
                            f"{BD_PRESET_LIST} array)")
    version = document_in.get("schemaVersion")
    if version != SCHEMA_VERSION:
        raise BdPresetError(f"{path} says schemaVersion {version}; this tool writes schema "
                            f"{SCHEMA_VERSION}. Open DiscImageStudio once so it migrates the file, "
                            "then run this again")
    for name in CATALOG_LISTS:
        document_in.setdefault(name, [])
    return document_in


def _same(left: dict, right: dict) -> bool:
    return all(left.get(k) == v for k, v in right.items())


def install(preset_obj: dict, path: str | None = None, replace: bool = False) -> dict:
    """Write one preset into the DiscImageStudio preset file, leaving everything else intact.

    That file (`disc-presets.json`) holds CD, DVD and Blu-ray presets in separate lists, and it is
    the one the window reads, so the entry has to go into its `bluRayPresets` list rather than a
    catalog of its own.
    """
    target = os.path.abspath(path or default_path())
    entry = catalog_entry(preset_obj)
    catalog = read_catalog(target)
    items = catalog[BD_PRESET_LIST]
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


def _twist_report(fit: dict, total_sectors: int, inner_mm, outer_mm, pitch_um, bit_nm,
                  usable_sectors, measured, pullback_isa0, twist_deg, twist_at_mm, twisted: dict) -> dict:
    """What the dial reading changed: the pitch it implies and how far the two radii moved."""
    plain = parameters(fit, total_sectors, inner_mm=inner_mm, outer_mm=outer_mm, pitch_um=pitch_um,
                       bit_nm=bit_nm, usable_sectors=usable_sectors, measured_sectors=measured,
                       pullback_isa0=pullback_isa0)
    at = twist_at_mm or plain["outerRadiusMm"]
    turns = twist_turns(plain["innerRadiusMm"], at, 0.32)
    ppm = twist_pitch_ppm(plain["innerRadiusMm"], plain["outerRadiusMm"], 0.32, twist_deg, at_mm=at)
    return {"twist_deg": twist_deg,
            "twist_turns": turns,
            "twist_pitch_ppm": ppm,
            "twist_r0_shift_um": 1e3 * (twisted["innerRadiusMm"] - plain["innerRadiusMm"]),
            "twist_outer_shift_um": 1e3 * (twisted["outerRadiusMm"] - plain["outerRadiusMm"])}


def export(geo_summary: str, total_sectors: int, out_path: str, preset_id: str, name: str, *,
           inner_mm: float | None = None, outer_mm: float | None = None, pitch_um: float | None = None,
           bit_nm: float = BD_CHANNEL_BIT_LENGTH_NM, usable_sectors: int | None = None,
           pullback_isa0: bool = False, twist_deg: float | None = None,
           twist_at_mm: float | None = None) -> dict:
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
    setup = run.get("setup") or {}
    measured = None if setup.get("last_lba") is None else int(setup["last_lba"]) + 1
    # A disc that was not filled ends wherever the burn ended, which need not be a recording-unit
    # boundary; DiscImageStudio needs totalSectors to be one, so the preset covers the last whole unit.
    requested = int(total_sectors)
    total_sectors = requested - requested % BD_SECTORS_PER_RECORDING_UNIT
    params = parameters(fit, total_sectors, inner_mm=inner_mm, outer_mm=outer_mm, pitch_um=pitch_um,
                        bit_nm=bit_nm, measured_sectors=measured, pullback_isa0=pullback_isa0,
                        twist_deg=twist_deg, twist_at_mm=twist_at_mm)
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
                 outer_mm=params["outerRadiusMm"], pitch_um=p, bit_nm=bit_nm,
                 usable_sectors=usable_sectors)
    out = {"preset": obj, "document": document(obj),
           "fit": {k: fit.get(k) for k in ("model", "anchor", "r0_mm", "pitch_um", "v_m_s", "r2",
                                           "zones_used", "sigma_r0_mm", "offset_ms", "sigma_offset_ms",
                                           "chi2_per_dof", "rungs")},
           "derived": {"pitch_um": p, "sector_mm": sector_mm(bit_nm),
                       "measured_sectors": measured,
                       "total_sectors_requested": requested,
                       "pullback_sectors": (total_sectors - measured
                                            if pullback_isa0 and measured and total_sectors > measured
                                            else 0),
                       "usable_sectors": params["usableSectors"],
                       "track_length_mm": track_length_mm(total_sectors, bit_nm),
                       "outer_from_pitch_mm": outer_radius_mm(params["innerRadiusMm"], p, total_sectors, bit_nm),
                       **(_twist_report(fit, total_sectors, inner_mm, outer_mm, pitch_um, bit_nm,
                                        usable_sectors, measured, pullback_isa0, twist_deg, twist_at_mm,
                                        params)
                          if twist_deg else {})},
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
