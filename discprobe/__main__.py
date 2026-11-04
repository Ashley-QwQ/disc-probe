"""Command line: python -m discprobe {list,info,timing,geo,spokes,scan,rings,ringscan,calib,calscan,selftest}"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import sys

from . import info, timing

# Tile target palette: the A5/92 pair, B9 and 66, aperiodic mixes of the 3.2T (A5-like)
# and 8T (92-like) classes, then along-track periods 32T, 48T and 64T (16T is 92). The
# period sequences were found with discprobe/efmplus.py and hold their period from any
# start state (evidence/coverage/periods.txt).
DEFAULT_PALETTE = ("A5", "92", "B9", "66", "MIX:A5,62,B1,61,65,A7", "MIX:92,87,83,8D,60",
                   "8B", "2AE304", "ED00")


def _open(args):
    if args.sim:
        from .sim import SimDrive
        mode, _, variant = args.sim.partition("-")
        return SimDrive(mode=mode, fua_honoured=variant == "", flush_honoured=variant == "flush",
                        seed=args.seed, media=getattr(args, "media", "dvd"))
    if not args.drive:
        sys.exit("give --drive E: (see `python -m discprobe list`) or --sim cav|clv|cav-nofua")
    from .spti import SptiDevice
    return SptiDevice(args.drive)


def _outdir(args, kind: str, dev) -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    tag = getattr(dev, "name", "drive").replace(":", "")
    path = os.path.join(args.out, f"{kind}-{tag}-{stamp}")
    os.makedirs(path, exist_ok=True)
    return path


def _write_json(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def cmd_list(args):
    from .spti import list_optical_drives
    drives = list_optical_drives()
    print("\n".join(drives) if drives else "no optical drives found")


def cmd_info(args):
    dev = _open(args)
    try:
        report = info.collect(dev)
    finally:
        dev.close() if hasattr(dev, "close") else None
    out = _outdir(args, "info", dev)
    _write_json(os.path.join(out, "info.json"), report)
    for line in info.summarize(report):
        print(line)
    print(f"\nFull dump: {os.path.abspath(out)}")


def cmd_timing(args):
    if not args.sim:
        from .spti import raise_priority
        if not raise_priority():
            print("note: could not raise process priority")
    dev = _open(args)
    targets = [float(x) for x in args.targets.split(",")] if args.targets else timing.DEFAULT_TARGETS
    probe = timing.TimingProbe(
        dev, read_method=args.read, reps=args.reps, period_reads=args.period_reads,
        targets=targets, ref_fraction=args.ref, speed_kbs=args.speed, pure_cav=args.cav,
        evict_sectors=args.evict_sectors, sectors=args.sectors, host_delay_ms=args.host_delay_ms, media=args.media)
    try:
        summary = probe.run()
    except timing.NoReadableDisc as e:
        sys.exit(str(e))
    finally:
        dev.close() if hasattr(dev, "close") else None
        out = _outdir(args, "timing", dev)
        rows = probe.events_as_rows()
        if rows:
            with open(os.path.join(out, "events.csv"), "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
        summary = probe.summary
        summary["device"] = getattr(dev, "name", None)
        summary["args"] = {k: v for k, v in vars(args).items()
                           if k != "func" and (k != "media" or v != "dvd")}
        _write_json(os.path.join(out, "summary.json"), summary)
        print(f"\nRaw events and summary: {os.path.abspath(out)}")


def cmd_spokes(args):
    from .spokes import SpokeSpec, generate
    spec = SpokeSpec(radius_mm=args.radius_mm, size_px=args.size)
    spec_path = generate(args.output, spec)
    print(f"Pattern: {os.path.abspath(args.output)}\nSpec:    {os.path.abspath(spec_path)}")
    print(f"Make the image exactly fill the DiscImageStudio canvas (radius {args.radius_mm} mm), centred.")


def cmd_scan(args):
    from .scan import analyse
    from .spokes import SpokeSpec
    spec = SpokeSpec.load(args.spec)
    centre = tuple(float(v) for v in args.centre.split(",")) if args.centre else None
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.join(args.out, f"scan-{os.path.splitext(os.path.basename(args.image))[0]}-{stamp}")
    try:
        analyse(args.image, spec, out, dpi=args.dpi, centre=centre, r_min=args.r_min, r_max=args.r_max)
    except RuntimeError as e:
        sys.exit(str(e))
    print(f"\nphase.csv, summary.json and check images: {os.path.abspath(out)}")


def cmd_rings(args):
    from .rings import RingLayout, describe, verify_iso, write_iso
    if args.media == "cd":
        from .cdrings import RingLayout, verify_iso, write_iso
    layout = RingLayout(textures=tuple(t.strip().upper() for t in args.textures.split(",")),
                        groups=args.groups, ring_width_mm=args.ring_width_mm, start_mm=args.start_mm,
                        r0_mm=args.r0_mm, pitch_um=args.pitch_um, bit_nm=args.bit_nm,
                        filler=args.filler.upper()).build()
    for line in describe(layout):
        print(line)
    if args.describe:
        return
    try:
        print(f"\nWriting {os.path.abspath(args.output)}")
        spec_path = write_iso(args.output, layout)
    except ValueError as e:
        sys.exit(str(e))
    problems = verify_iso(args.output, layout)
    print("Verified: sampled sectors in every ring record the intended byte" if not problems
          else "VERIFY FAILED:\n  " + "\n  ".join(problems[:10]))
    print(f"Layout: {os.path.abspath(spec_path)}  (needed by ringscan)")
    print("Burn with any image burner (Windows Disc Image Burner works) and note the speed. "
          "The file system is an empty ISO 9660 placeholder.")
    if problems:
        sys.exit(1)


def cmd_ringscan(args):
    from .rings import RingLayout
    from .ringscan import analyse
    layout = RingLayout.load(args.layout)
    refs = args.refs or ("0D,AA" if layout.kind == "cd-texture-rings" else "A5,92")
    centre = tuple(float(v) for v in args.centre.split(",")) if args.centre else None
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.join(args.out, f"ringscan-{stamp}")
    try:
        analyse(args.images, layout, out, dpi=args.dpi, centre=centre,
                refs=tuple(t.strip().upper() for t in refs.split(',')))
    except RuntimeError as e:
        sys.exit(str(e))
    print(f"\nrings.csv, textures.csv, summary.json and unrolled views: {os.path.abspath(out)}")


def cmd_calib(args):
    from .calib import CalLayout, describe, refine_layout, verify_iso, write_iso
    common = dict(start_mm=args.start_mm, end_mm=args.end_mm, guard_mm=args.guard_mm)
    try:
        if args.refine_from:
            with open(args.refine_from, encoding="utf-8") as f:
                fit = json.load(f).get("fit")
            if not fit:
                sys.exit(f"{args.refine_from} has no geometry fit")
            layout = refine_layout(fit, groups=args.groups or 20, **common)
        else:
            layout = CalLayout(s_range=args.s_range, s_step=args.s_step, groups=args.groups or 3,
                               r0_mm=args.r0_mm, pitch_um=args.pitch_um, bit_nm=args.bit_nm, **common).build()
    except ValueError as e:
        sys.exit(str(e))
    for line in describe(layout):
        print(line)
    if args.describe:
        return
    print(f"\nWriting {os.path.abspath(args.output)} (about a minute)")
    try:
        spec_path = write_iso(args.output, layout)
    except ValueError as e:
        sys.exit(str(e))
    problems = verify_iso(args.output, layout)
    print("Verified: guards are pure, bands follow their patterns" if not problems
          else "VERIFY FAILED:\n  " + "\n  ".join(problems[:10]))
    print(f"Layout: {os.path.abspath(spec_path)}  (needed by calscan)")
    print("Burn with any image burner (Windows Disc Image Burner works). "
          "The file system is an empty ISO 9660 placeholder.")
    if problems:
        sys.exit(1)


def cmd_calscan(args):
    from .calib import CalLayout
    from .calscan import analyse
    layout = CalLayout.load(args.layout)
    centre = tuple(float(v) for v in args.centre.split(",")) if args.centre else None
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.join(args.out, f"calscan-{os.path.splitext(os.path.basename(args.image))[0]}-{stamp}")
    try:
        analyse(args.image, layout, out, dpi=args.dpi, centre=centre)
    except RuntimeError as e:
        sys.exit(str(e))
    print(f"\nbands.csv, phase.csv, summary.json and unrolled.png: {os.path.abspath(out)}")


def cmd_geo(args):
    from .geo import Ladder, write_outputs
    ranges = None
    if args.ranges:
        ranges = [tuple(int(x) for x in part.split("-")) for part in args.ranges.split(",")]
    elif args.rings_layout:
        from .rings import RingLayout
        lay = RingLayout.load(args.rings_layout)
        m = args.margin_sectors
        ranges = [(r["lba_start"] + m, r["lba_end"] - m) for r in lay.rings
                  if r["texture"].upper() == args.texture.upper()]
    if not args.sim:
        from .spti import raise_priority
        raise_priority()
    dev = _open(args)
    ladder = Ladder(dev, ranges=ranges, r0_mm=args.r0_mm, pitch_um=args.pitch_um, bit_nm=args.bit_nm,
                    reps=args.reps, max_targets=args.max_targets, ref_lba=args.ref_lba,
                    speed_kbs=None if args.sim else args.speed, host_delay_ms=args.host_delay_ms, media=args.media,
                    chi2_abort=args.chi2_abort)
    out = _outdir(args, "geo", dev)
    try:
        res = ladder.run()
    except RuntimeError as e:
        print(f"stopped: {e}")
        res = None
    finally:
        dev.close() if hasattr(dev, "close") else None
        if ladder.targets and ladder.cov is not None:
            write_outputs(ladder, out)
    if res:
        print()
        print(f"u = r0/b = {res['u']:.3f}, v = p/b = {res['v']:.7f}  (chi2/dof {res['chi2_per_dof']:.2f}, "
              f"residual rms {res['residual_rms_deg']:.3f} deg)")
        print(f"With bit length {res['bit_nm_assumed']} nm: r0 {res['r0_mm_at_bit']:.5f} mm, "
              f"pitch {res['pitch_um_at_bit']:.6f} um")
        print(f"Angle uncertainty across the measured span {res['measured_span_mm'][0]}-"
              f"{res['measured_span_mm'][1]} mm: {res['angle_sigma_measured_span_deg']:.3f} deg (1 sigma); "
              f"across {'25' if args.media == 'cd' else '24'}-58 mm: {res.get('angle_sigma_deg', float('nan')):.2f} deg")
    print(f"targets.csv, summary.json, events.csv: {os.path.abspath(out)}")
    if args.media == "cd" and res is None:
        sys.exit(1)


def cmd_image(args):
    from . import imagedisc
    writer = imagedisc
    if args.media == "cd":
        from . import cdimage as writer
    with open(args.geo, encoding="utf-8") as f:
        fit = json.load(f)["fit"]
    if args.media == "cd" and fit.get("media") != "cd":
        sys.exit("CD image needs a CD geometry fit (media=cd); DVD fits must not be reused")
    u, v, bit = fit["u"], fit["v"], fit["bit_nm_assumed"]
    if args.design_npy:
        import numpy as np
        design = np.load(args.design_npy)
        if design.shape != (imagedisc.SIZE, imagedisc.SIZE):
            sys.exit(f"design must be {imagedisc.SIZE} x {imagedisc.SIZE} cells of {imagedisc.CELL_MM} mm")
        if args.textures:
            design = design.astype(np.uint8)
        elif design.dtype != bool:
            sys.exit("a label design (not boolean) needs --textures, one per label")
        kind = f"design {os.path.basename(args.design_npy)}"
    elif args.picture:
        design = imagedisc.picture_design(args.picture, args.diameter_mm)
        kind = f"picture {os.path.basename(args.picture)}"
    else:
        design = imagedisc.grid_design(r_min=26.0 if args.media == "cd" else 24.5,
                                      r_max=args.r_max, line=args.line_mm)
        kind = f"grid, {args.line_mm} mm lines"
    total = writer.sectors_to_radius(u, v, bit, args.r_max + 0.6)
    if args.media == "dvd":
        total = min(total, 2295104)
    else:
        from .cd import check_capacity
        check_capacity(total)
    tex = f"textures {' '.join(args.textures)}" if args.textures else f"dark {args.dark}, light {args.light}"
    print(f"{kind}, geometry u {u:.3f}, v {v:.7f} from {args.geo}; {total} sectors "
          f"({total * 2048 / 1e9:.2f} GB), {tex}")
    corr = imagedisc.load_correction(args.correction) if args.correction else None
    spec = writer.write_iso(args.output, design, u, v, bit, total, args.dark, args.light,
                               meta={"geometry_from": os.path.abspath(args.geo), "design": kind,
                                     "correction": os.path.abspath(args.correction) if args.correction else None},
                               correction=corr, textures=args.textures)
    problems = writer.verify_iso(args.output, design, u, v, bit, total, args.dark, args.light, correction=corr,
                                    textures=args.textures)
    print("Verified: sampled sectors match the design" if not problems else "VERIFY FAILED: " + "; ".join(problems[:5]))
    prev = os.path.splitext(args.output)[0] + ".preview.png"
    if design.dtype == bool:
        imagedisc.preview(design, prev)
    else:
        from . import tiledisc
        tiledisc.preview(design, args.textures, prev)
    print(f"Spec: {os.path.abspath(spec)}\nPreview (data-side view): {os.path.abspath(prev)}")
    if args.media == "cd" and problems:
        sys.exit(1)


def cmd_gridscan(args):
    from . import gridscan, imagedisc
    design = imagedisc.grid_design(r_min=26.0 if args.media == "cd" else 24.5,
                                  r_max=args.r_max, line=args.line_mm)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    for path in args.images:
        out = os.path.join(args.out, f"gridscan-{os.path.splitext(os.path.basename(path))[0]}-{stamp}")
        kw = {"r_min": 26.5} if args.media == "cd" else {}
        gridscan.analyse(path, design, out, dpi=args.dpi, force_mirrored=None if args.auto_mirror else False, **kw)
        print(f"  phi.csv and summary.json: {os.path.abspath(out)}")


def cmd_correction(args):
    from .gridscan import fit_correction
    c = fit_correction(args.phi, args.output, degree=args.degree, geometry=args.geo)
    print(f"{c['points_used']} rings from {len(args.phi)} scans, fit residual rms {c['residual_rms_deg']:.4f} deg")
    print(f"Angle correction: {os.path.abspath(args.output)}  (use with image --correction)")


def cmd_disexport(args):
    from .disexport import export
    out = export(args.geo, args.sectors, args.correction, args.output, args.r_min, args.r_max, args.id, args.name)
    f = out["fit"]
    print(f"inner {f['innerRadiusMm']:.9f} mm, outer {f['outerRadiusMm']:.9f} mm, pitch shape "
          f"{f['pitchLinear']:.3e} {f['pitchQuadratic']:.3e} {f['pitchCubic']:.3e}")
    print(f"angle difference to the measured map over {f['fit_range_mm'][0]}-{f['fit_range_mm'][1]} mm: "
          f"max {f['max_angle_diff_deg']:.4f} deg, rms {f['rms_angle_diff_deg']:.4f} deg")
    print(f"DiscImageStudio preset object in {os.path.abspath(args.output)} (key 'preset')")


def cmd_tiles(args):
    from . import imagedisc, tiledisc
    writer = imagedisc
    if args.media == "cd":
        from . import cdimage as writer
    with open(args.geo, encoding="utf-8") as f:
        fit = json.load(f)["fit"]
    if args.media == "cd" and fit.get("media") != "cd":
        sys.exit("CD tiles need a CD geometry fit (media=cd)")
    u, v, bit = fit["u"], fit["v"], fit["bit_nm_assumed"]
    geo = {"ring_edges_mm": tuple(args.ring_edges), "tile_mm": args.tile_mm, "cols": args.cols,
           "scale_mm": tuple(args.scale) if args.scale else None, "gap_mm": args.gap_mm,
           "shuffle_seed": args.shuffle}
    labels, textures, layout = tiledisc.design(args.palette, **geo)
    if args.media == "cd":
        textures = [{"A5": "0D", "92": "AA"}.get(t, t) for t in textures]
        layout.update(media="cd", id_dark="0D", id_light="AA")
    outer = max(args.ring_edges[-1], args.scale[1] if args.scale else 0)
    total = writer.sectors_to_radius(u, v, bit, outer + 0.6)
    if args.media == "dvd":
        total = min(total, 2295104)
    else:
        from .cd import check_capacity
        check_capacity(total)
    print(f"{sum(layout['sectors_per_ring'])} tiles, palette {' '.join(args.palette)}; geometry u {u:.3f}, "
          f"v {v:.7f} from {args.geo}; {total} sectors ({total * 2048 / 1e9:.2f} GB)")
    corr = imagedisc.load_correction(args.correction) if args.correction else None
    meta = {"geometry_from": os.path.abspath(args.geo), "design": "tile palette target",
            "correction": os.path.abspath(args.correction) if args.correction else None}
    spec = writer.write_iso(args.output, labels, u, v, bit, total, meta=meta, correction=corr, textures=textures)
    problems = writer.verify_iso(args.output, labels, u, v, bit, total, correction=corr, textures=textures)
    print("Verified: sampled sectors match the design" if not problems else "VERIFY FAILED: " + "; ".join(problems[:5]))
    base = os.path.splitext(args.output)[0]
    tiledisc.save_layout({**layout, "textures": textures}, base + ".tiles.json")
    tiledisc.preview(labels, textures, base + ".preview.png")
    print(f"Spec: {os.path.abspath(spec)}\nLayout: {os.path.abspath(base + '.tiles.json')}\n"
          f"Preview (data-side view, false colours): {os.path.abspath(base + '.preview.png')}")
    if args.media == "cd" and problems:
        sys.exit(1)


def cmd_tilescan(args):
    from . import tilescan
    for i, path in enumerate(args.scans):
        out = os.path.join(args.output_dir, f"{i + 1}_{os.path.splitext(os.path.basename(path))[0]}")
        s = tilescan.analyse(path, args.layout, out, dpi=args.dpi)
        for name, v in s["levels_a5_0_92_1"].items():
            print(f"    {name:24s} {v}")


def cmd_random(args):
    from .randomdisc import write_iso
    print(f"Writing {os.path.abspath(args.output)}: {args.sectors} sectors of seeded random data")
    write_iso(args.output, args.sectors, args.seed, media=args.media)
    print("Burn it with any image burner, then run `geo` on it.")


def cmd_selftest(args):
    from .selftest import run
    sys.exit(0 if run() else 1)


def main(argv=None):
    p = argparse.ArgumentParser(prog="discprobe", description="Read-only optical drive probe")
    sub = p.add_subparsers(required=True)

    sp = sub.add_parser("list", help="list optical drives")
    sp.set_defaults(func=cmd_list)

    def common(sp):
        sp.add_argument("--drive", help="drive letter, e.g. E:")
        sp.add_argument("--sim", choices=["cav", "clv", "cav-nofua", "cav-flush"],
                        help="use the simulated drive (nofua: FUA ignored; flush: FUA ignored but a "
                             "zero-length FUA read drops the cache)")
        sp.add_argument("--seed", type=int, default=1, help="simulation seed")
        sp.add_argument("--out", default="results", help="output directory (default: results)")

    sp = sub.add_parser("info", help="dump drive and disc information")
    common(sp)
    sp.set_defaults(func=cmd_info)

    sp = sub.add_parser("timing", help="cache/FUA test, CAV check, sector phase measurement")
    common(sp)
    sp.add_argument("--read", choices=["auto", "read10", "read12", "readcd"], default="auto")
    sp.add_argument("--reps", type=int, default=40, help="R/X pairs per phase target")
    sp.add_argument("--period-reads", type=int, default=60, help="reads per zone in the period test")
    sp.add_argument("--targets", help="comma-separated disc fractions, default 0.15,0.35,0.55,0.75,0.95")
    sp.add_argument("--ref", type=float, default=0.05, help="reference sector as a disc fraction")
    sp.add_argument("--speed", type=int,
                    help="SET CD SPEED read speed in kB/s, e.g. DVD 8x = 11080, 16x = 22160 (omit to leave as is)")
    sp.add_argument("--cav", action="store_true",
                    help="set the Rotational Control bit of SET CD SPEED; MMC defines it for writing, "
                         "so whether reads change is only known from the period test")
    sp.add_argument("--sectors", type=int, default=1,
                    help="sectors per measurement read; 16 reads one whole aligned DVD ECC block")
    sp.add_argument("--host-delay-ms", type=float, default=25.0,
                    help="random pause (0..N ms) before each timed read, so repeated reads do not all "
                         "span the same number of revolutions; should exceed one revolution")
    sp.add_argument("--evict-sectors", type=int, default=1024,
                    help="sectors read elsewhere before each measurement when the cache cannot be bypassed")
    sp.set_defaults(func=cmd_timing)

    sp = sub.add_parser("spokes", help="generate the radial-spoke calibration pattern")
    sp.add_argument("--output", default="spokes.png")
    sp.add_argument("--radius-mm", type=float, default=58.0,
                    help="disc radius at the image edge: DiscImageStudio canvas radius (CD 57.5, DVD/BD the generation outer radius)")
    sp.add_argument("--size", type=int, default=4096, help="image size in pixels")
    sp.set_defaults(func=cmd_spokes)

    sp = sub.add_parser("scan", help="measure spoke rotation versus radius on a flatbed scan")
    sp.add_argument("image", help="scan file (PNG/TIFF; avoid JPEG)")
    sp.add_argument("--spec", required=True, help="the .spokes.json written next to the pattern")
    sp.add_argument("--dpi", type=float, help="scan resolution if the file does not record it")
    sp.add_argument("--centre", help="approximate disc centre X,Y in pixels if detection fails")
    sp.add_argument("--r-min", type=float, default=20.0)
    sp.add_argument("--r-max", type=float, default=59.0)
    sp.add_argument("--out", default="results")
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("rings", help="write the DVD texture-ring test ISO (one recorded byte per ring)")
    sp.add_argument("--output", default="rings.iso")
    sp.add_argument("--textures", default="A5,B9,66,64,E4,92,RND",
                    help="scrambled-domain bytes in hex, or RND; must include A5 and 92")
    sp.add_argument("--groups", type=int, default=3, help="repeats of the full texture set, inner to outer")
    sp.add_argument("--ring-width-mm", type=float, default=1.4)
    sp.add_argument("--start-mm", type=float, default=25.0, help="radius where the first ring starts")
    sp.add_argument("--filler", default="92", help="texture between the data start and the first ring")
    sp.add_argument("--r0-mm", type=float, default=24.0, help="nominal data start radius for placing rings")
    sp.add_argument("--pitch-um", type=float, default=0.74)
    sp.add_argument("--bit-nm", type=float, default=133.3)
    sp.add_argument("--describe", action="store_true", help="print the layout without writing")
    sp.set_defaults(func=cmd_rings)

    sp = sub.add_parser("ringscan", help="measure texture brightness on scans of the ring disc")
    sp.add_argument("images", nargs="+", help="one or more scans (PNG/TIFF, no auto adjustments); "
                                              "rotate the disc between scans for repeats")
    sp.add_argument("--layout", required=True, help="the .rings.json written next to the ISO")
    sp.add_argument("--refs", help="dark,bright references (DVD A5,92; CD 0D,AA) defining levels 0 and 1; "
                                                    "use the darkest and brightest textures the scan shows")
    sp.add_argument("--dpi", type=float, help="scan resolution if the file does not record it")
    sp.add_argument("--centre", help="approximate disc centre X,Y in pixels if detection fails")
    sp.add_argument("--out", default="results")
    sp.set_defaults(func=cmd_ringscan)

    sp = sub.add_parser("calib", help="write a multi-hypothesis calibration ISO (bracketing disc, or refinement disc)")
    sp.add_argument("--output", default="cal.iso")
    sp.add_argument("--refine-from", help="summary.json of a calscan run: write the refinement disc, every band "
                                          "drawn with that fit")
    sp.add_argument("--s-range", type=float, default=0.012, help="largest local-rate offset tried, e.g. 0.012 = 1.2 %%")
    sp.add_argument("--s-step", type=float, default=0.002)
    sp.add_argument("--groups", type=int, help="repeats of the hypothesis set (default 3; 20 for refinement)")
    sp.add_argument("--start-mm", type=float, default=25.0)
    sp.add_argument("--end-mm", type=float, default=57.0)
    sp.add_argument("--guard-mm", type=float, default=0.2)
    sp.add_argument("--r0-mm", type=float, default=24.0, help="centre geometry of the sweep")
    sp.add_argument("--pitch-um", type=float, default=0.74)
    sp.add_argument("--bit-nm", type=float, default=133.3)
    sp.add_argument("--describe", action="store_true", help="print the layout without writing")
    sp.set_defaults(func=cmd_calib)

    sp = sub.add_parser("calscan", help="fit the disc geometry from a scan of a calibration disc")
    sp.add_argument("image", help="scan (PNG/TIFF, grey or colour, no auto adjustments)")
    sp.add_argument("--layout", required=True, help="the .cal.json written next to the ISO")
    sp.add_argument("--dpi", type=float)
    sp.add_argument("--centre", help="approximate disc centre X,Y in pixels if detection fails")
    sp.add_argument("--out", default="results")
    sp.set_defaults(func=cmd_calscan)

    sp = sub.add_parser("geo", help="measure the spiral geometry of a burned DVD from read timing (ladder)")
    common(sp)
    sp.add_argument("--speed", type=int, default=5540, help="read speed to fix, kB/s (default 4x = 5540)")
    sp.add_argument("--ranges", help="readable LBA ranges a-b,c-d (default 3-85 %% of the recorded area)")
    sp.add_argument("--rings-layout", help="texture-ring layout file: use only the rings of --texture")
    sp.add_argument("--texture", default="RND")
    sp.add_argument("--margin-sectors", type=int, default=3000, help="kept away from ring edges")
    sp.add_argument("--ref-lba", type=int)
    sp.add_argument("--reps", type=int, default=24, help="reference/target read pairs per rung")
    sp.add_argument("--max-targets", type=int, default=22)
    sp.add_argument("--host-delay-ms", type=float, default=25.0)
    sp.add_argument("--r0-mm", type=float, default=24.0, help="prior geometry (loose)")
    sp.add_argument("--pitch-um", type=float, default=0.74)
    sp.add_argument("--bit-nm", type=float, default=133.3)
    sp.add_argument("--chi2-abort", type=float, default=25.0,
                    help="stop when chi2/dof of the constant-pitch fit exceeds this; raise it for media "
                         "whose pitch varies (CD: a smooth S of a few degrees), the 90-degree residual "
                         "check still catches whole-turn errors")
    sp.set_defaults(func=cmd_geo)

    sp = sub.add_parser("image", help="write a picture ISO placed with a measured geometry (grid test by default)")
    sp.add_argument("--geo", required=True, help="summary.json of a geo run")
    sp.add_argument("--output", default="iso/grid.iso")
    sp.add_argument("--picture", help="greyscale picture to threshold instead of the grid test")
    sp.add_argument("--design-npy", help="prepared boolean design (True = dark), 6000 x 6000 cells of 0.02 mm, data-side view")
    sp.add_argument("--diameter-mm", type=float, default=116.0, help="picture diameter on the disc")
    sp.add_argument("--r-max", type=float, default=56.0, help="outer radius of the drawing")
    sp.add_argument("--line-mm", type=float, default=0.3, help="grid line width")
    sp.add_argument("--correction", help="angle-correction file (phi(r) measured on a burned grid)")
    sp.add_argument("--dark", default="A5")
    sp.add_argument("--light", default="B9", help="light texture (B9 scanned brightest on Ritek F1)")
    sp.add_argument("--textures", nargs="+", help="for a label design (uint8): one texture per label, "
                    "e.g. A5 92 8B00 RND MIX:92,4F")
    sp.set_defaults(func=cmd_image)

    sp = sub.add_parser("tiles", help="write a self-locating texture palette target (IDs + swatches in every tile)")
    sp.add_argument("--geo", required=True, help="summary.json of a geo run")
    sp.add_argument("--output", default="iso/tiles.iso")
    sp.add_argument("--palette", nargs="+", default=list(DEFAULT_PALETTE),
                    help="up to 9 textures: a byte (A5), a repeated sequence (8B00), RND, or MIX:92,4F")
    sp.add_argument("--correction", help="angle-correction file")
    sp.add_argument("--ring-edges", type=float, nargs="+", default=[25.0, 33.0, 41.0, 49.0, 57.0],
                    help="radii (mm) separating the tile rings")
    sp.add_argument("--tile-mm", type=float, default=8.0, help="tile size along the arc")
    sp.add_argument("--cols", type=int, default=7, help="cell columns per tile (4 hold the ID, the rest swatches)")
    sp.add_argument("--scale", type=float, nargs=2, metavar=("R0", "R1"), help="add an angle scale band (mm)")
    sp.add_argument("--gap-mm", type=float, default=0.5, help="background gap between tiles")
    sp.add_argument("--shuffle", type=int, metavar="SEED",
                    help="give every tile its own random swatch order (decouples texture from position)")
    sp.set_defaults(func=cmd_tiles)

    sp = sub.add_parser("tilescan", help="read IDs and swatch levels from flatbed scans of the tile palette target")
    sp.add_argument("scans", nargs="+", help="scan images (PNG/TIFF/JPEG)")
    sp.add_argument("--layout", default="iso/tiles.tiles.json", help="layout file written by the tiles command")
    sp.add_argument("--dpi", type=float, default=600.0)
    sp.add_argument("--output-dir", default="results/tilescan")
    sp.set_defaults(func=cmd_tilescan)

    sp = sub.add_parser("gridscan", help="measure line straightness on scans of the burned grid test")
    sp.add_argument("images", nargs="+")
    sp.add_argument("--dpi", type=float, default=600.0)
    sp.add_argument("--r-max", type=float, default=56.0, help="must match the image command")
    sp.add_argument("--line-mm", type=float, default=0.3, help="must match the image command")
    sp.add_argument("--auto-mirror", action="store_true", help="let the (weak) mirror test decide orientation")
    sp.add_argument("--out", default="results")
    sp.set_defaults(func=cmd_gridscan)

    sp = sub.add_parser("correction", help="fit an angle-correction curve from gridscan phi.csv files")
    sp.add_argument("phi", nargs="+", help="phi.csv files written by gridscan")
    sp.add_argument("--output", default="angle_correction.json")
    sp.add_argument("--degree", type=int, default=4)
    sp.add_argument("--geo", help="summary.json of the geo run the grid disc was burned with (recorded only)")
    sp.set_defaults(func=cmd_correction)

    sp = sub.add_parser("disexport", help="fit the measured angle map as a DiscImageStudio DVD preset (cubic pitch)")
    sp.add_argument("--geo", required=True, help="summary.json of a geo run")
    sp.add_argument("--correction", help="angle-correction file from the correction command")
    sp.add_argument("--sectors", type=int, default=2298496, help="totalSectors of the preset (disc capacity)")
    sp.add_argument("--r-min", type=float, default=25.8, help="fit range: use the measured span")
    sp.add_argument("--r-max", type=float, default=54.4)
    sp.add_argument("--id", default="discprobe-dvd-r")
    sp.add_argument("--name", default="DVD-R (drive-timing calibration)")
    sp.add_argument("--output", default="dis_preset.json")
    sp.set_defaults(func=cmd_disexport)

    sp = sub.add_parser("random", help="write a random-data ISO for full-disc timing calibration")
    sp.add_argument("--output", default="iso/random.iso")
    sp.add_argument("--sectors", type=int, default=2295104)
    sp.add_argument("--seed", type=int, default=1)
    sp.set_defaults(func=cmd_random)

    sp = sub.add_parser("selftest", help="parser checks and end-to-end runs on the simulated drive and a synthetic scan")
    sp.set_defaults(func=cmd_selftest)

    # Add media only to commands with an implemented CD path. Existing DVD
    # defaults are retained verbatim; explicit CD options override CD defaults.
    cd_defaults = {
        "rings": dict(output="iso/cd-rings.iso", textures="0D,AA,10,63,RND", filler="AA",
                      r0_mm=25.0, pitch_um=1.6, start_mm=26.0, ring_width_mm=2.0),
        "random": dict(output="iso/cd-random.iso", sectors=359849),
        "geo": dict(r0_mm=25.0, pitch_um=1.6, speed=2822, reps=32, max_targets=36),
        "timing": dict(speed=2822),
        "image": dict(output="iso/cd-grid.iso", dark="0D", light="AA", line_mm=0.6),
        "tiles": dict(output="iso/cd-tiles.iso", palette=["0D", "AA", "10", "63", "RND", "0DAA", "00FF", "1063", "0D10AA"]),
        "gridscan": dict(line_mm=0.6),
    }
    for name in cd_defaults:
        sub.choices[name].add_argument("--media", choices=("dvd", "cd"), default="dvd")
    args = p.parse_args(argv)
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if getattr(args, "media", "dvd") == "cd":
        from .cd import BIT_NM
        name = raw_args[0]
        defaults = cd_defaults[name].copy()
        if name in ("rings", "geo"):
            defaults["bit_nm"] = BIT_NM
        supplied = {a.split("=")[0] for a in raw_args if a.startswith("--")}
        for key, value in defaults.items():
            if "--" + key.replace("_", "-") not in supplied:
                setattr(args, key, value)
    args.func(args)


if __name__ == "__main__":
    main()
