"""Command line: python -m discprobe <command>; run it with -h, or `guide`, to see the commands."""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import math
import os
import sys

try:
    from . import guide, i18n, info, mmc, timing, ui
except ImportError as e:    # half a copy of this folder: i18n may be what is missing, so it says so in both languages
    if (e.name or "").split(".")[0] != __package__:
        raise
    sys.exit(f"The disc-probe files in {os.path.dirname(os.path.abspath(__file__))} are incomplete. Download or clone it again, "
             "then run this from inside the new folder.\n"
             "这个文件夹里的 disc-probe 文件不完整。请重新下载或 clone，再到新的文件夹里运行。")

# Tile target palette: the A5/92 pair, B9 and 66, aperiodic mixes of the 3.2T (A5-like)
# and 8T (92-like) classes, then along-track periods 32T, 48T and 64T (16T is 92). The
# period sequences were found with discprobe/efmplus.py and hold their period from any
# start state (evidence/coverage/periods.txt).
DEFAULT_PALETTE = ("A5", "92", "B9", "66", "MIX:A5,62,B1,61,65,A7", "MIX:92,87,83,8D,60",
                   "8B", "2AE304", "ED00")
TIMING_WAIT_S, GEO_WAIT_S = 90.0, 300.0     # usual lengths, until a run can estimate its own


class _Rerun(Exception):
    """Start over with these arguments added, after the person agreed to them."""

    def __init__(self, extra):
        self.extra = extra


def _fail(message, hints=()):
    """Exit with an error, plus what to do about it at a terminal."""
    if ui.term().interactive and hints:
        print(message, file=sys.stderr)
        _next(hints)
        sys.exit(1)
    sys.exit(message)


def _reason(e: OSError) -> str:
    """The system's message, for a sentence of ours; it brings its own full stop. Scripts see it as it always was."""
    return e.strerror.rstrip(" .\u3002") if ui.term().interactive else e.strerror


def _os_error(e: OSError) -> str:
    """At a terminal a missing file is said plainly; scripts keep the form they always saw."""
    if isinstance(e, FileNotFoundError) and e.filename and ui.term().interactive:
        name = str(e.filename)
        where = "" if os.path.isabs(name) else f"\nIt looked in {os.getcwd()}. A full path works too, in quotes if it has spaces."
        example = "\nmy_picture.png is only an example: use the name of your own picture." if os.path.basename(name) == "my_picture.png" else ""
        return f"no such file: {name}{where}{example}"
    return f"error: {e}"


def _next(lines, args=None) -> None:
    """Advice after a command; the lines to copy stand out. With `args`, the progress list goes before what comes next."""
    if lines and args is not None and ui.term().interactive and not getattr(args, "sim", None) and "geo-SIM-" not in str(getattr(args, "geo", "")):
        at = next((i for i, line in enumerate(lines) if line.startswith("Next")), 0)
        lines = [*lines[:at], *guide.progress_lines(getattr(args, "media", "dvd"), getattr(args, "out", "results")), *lines[at:]]
    if lines:
        ui.say()
    for line in lines:
        if isinstance(line, guide.Quiet):
            ui.say(line, "dim")
        elif isinstance(line, guide.Step):
            ui.say(ui.guide_line(line))
        else:
            ui.say(ui.command(i18n.tr(line)) if line.lstrip().startswith("python ") else line)


def _cdrdao_toc(args, layout: str | None = None) -> None:
    """On Linux, a CD ISO gets a cdrdao toc beside it: the burner there that writes the layout the ISO was made for."""
    if sys.platform == "linux" and getattr(args, "media", "dvd") == "cd":
        from . import cd
        print(f"cdrdao toc: {os.path.abspath(cd.write_cdrdao_toc(args.output, layout))}")


def _image_ready(args, preview: str, design=None, files: str = "") -> None:
    """The advice for a finished picture ISO. One from a simulated run is told not to reach a disc at all.
    `files` says where the spec and preview went; it comes after the look at the disc, which is tall."""
    if design is not None and ui.term().interactive and design.dtype == bool:
        from . import imagecheck
        imagecheck.show(design, args)
    if files:
        print(files)
    if "geo-SIM-" not in args.geo:
        _cdrdao_toc(args)
    ui.iso_ready(args.output)       # after the disc, which is tall, or this scrolls away again
    simulated = None
    if (design is not None and design.dtype == bool and getattr(args, "media", "dvd") == "dvd"
            and ui.term().can_prompt()
            and ui.ask("Make a simulated photo of it too? A model, not a measurement; it takes about ten seconds.")):
        simulated = _simulated_photo(args, design)
    _next(guide.after_image(args.output, preview, args.geo, getattr(args, "picture", None),
                            getattr(args, "design", None), getattr(args, "media", "dvd"), simulated), args)
    if "geo-SIM-" not in args.geo:
        ui.burn_warning()


def _simulated_photo(args, design) -> str | None:
    """Twelve predicted views of the disc beside the picture, next to the ISO; None when the textures can't be modelled."""
    from . import simulate
    path = os.path.splitext(args.output)[0] + ".simulated.png"
    try:
        with ui.busy("Rendering the simulated photo..."):
            simulate.sheet(design, getattr(args, "picture", None), 420, args.dark, args.light,
                           simulate.CAMERA, simulate.FLASH).save(path)
    except ValueError as e:
        print(f"No simulated photo: {e}")
        return None
    return path


def _need_hardware_platform() -> None:
    if sys.platform not in ("win32", "linux"):
        sys.exit(guide.PORTS)


def _choose_drive(args) -> None:
    """At a terminal a missing --drive can be worked out."""
    if args.drive or sys.platform not in ("win32", "linux") or not ui.term().interactive:
        return
    drives = guide.optical_drives()
    if len(drives) == 1:
        args.drive = drives[0]
        ui.say(f"Using the only optical drive, {args.drive}")
    elif not drives:
        sys.exit("no optical drive found; to try the flow without one, add --sim cav")
    elif ui.term().can_prompt():
        print("Optical drives: " + "  ".join(drives))
        while args.drive not in drives:
            try:
                answer = input(i18n.tr(f"Which drive? [{drives[0]}] ")).strip()
            except EOFError:
                sys.exit("no drive chosen")
            answer = answer or drives[0]
            if sys.platform == "win32":
                answer = answer.upper()
                args.drive = answer if answer.endswith(":") else answer + ":"
            else:
                args.drive = next((d for d in drives if os.path.basename(d) == answer), answer)


def _open(args):
    if args.sim:
        from .sim import SimDrive
        mode, _, variant = args.sim.partition("-")
        media = getattr(args, "media", "dvd")
        sectors = getattr(args, "sectors", 1)
        return SimDrive(mode=mode, fua_honoured=variant in ("", "audio"), flush_honoured=variant == "flush",
                        seed=args.seed, media=media, cd_audio=variant == "audio",
                        cd_read_offset_bytes=getattr(args, "read_offset_bytes", 0.0),
                        block=32 if media == "bd" and sectors == 32 else None)
    _need_hardware_platform()
    transport = getattr(args, "transport", "auto")
    if sys.platform == "linux" and transport != "auto":
        sys.exit("--transport spti|imapi is Windows-only; on Linux use --transport auto (SG_IO)")
    _choose_drive(args)
    if not args.drive:
        example = "/dev/sr0" if sys.platform == "linux" else "E:"
        sys.exit(f"give --drive {example} (see `python -m discprobe list`) or --sim cav|clv|cav-nofua")
    if sys.platform == "linux":
        from .device import Device
        try:
            return Device(args.drive)
        except OSError as e:
            sys.exit(f"{_reason(e)}. Optical drives here: {' '.join(guide.optical_drives()) or 'none'}")
    if transport != "imapi":
        from .spti import SptiDevice
        try:
            return SptiDevice(args.drive)
        except ValueError as e:
            sys.exit(f"{e} (see `python -m discprobe list`)")
        except OSError as e:
            # SPTI often needs an elevated process; IMAPI2 reaches the same drive without it.
            if transport == "spti" or e.errno != 5:
                sys.exit(f"{_reason(e)}. Optical drives here: {' '.join(guide.optical_drives()) or 'none'}")
            print("note: SPTI was refused (not elevated); using the IMAPI2 transport instead")
    from .imapi import ImapiDevice
    return ImapiDevice(args.drive)


def _check_disc(dev, args) -> None:
    """At a terminal, catch an empty tray or the wrong media settings before minutes of measuring."""
    if not ui.term().interactive:
        return
    from .scsi import DATA_IN, DATA_NONE
    ready = dev.execute(mmc.test_unit_ready(), 0, DATA_NONE)
    reason = mmc.not_ready(ready.sense)
    if reason:
        sys.exit(reason)
    cfg = dev.execute(mmc.get_configuration(), 4096, DATA_IN)
    family = mmc.media_family(mmc.parse_configuration(cfg.data).get("current_profile") if cfg.ok else None)
    if family == "cd" and args.media == "dvd":
        if ui.ask("This is a CD, but the command has DVD settings. Add --media cd?"):
            dev.close() if hasattr(dev, "close") else None
            raise _Rerun(["--media", "cd"])
    if family == "bd" and getattr(args, "media", "dvd") != "bd" and args.func in (cmd_geo, cmd_timing):
        if ui.ask("This is a Blu-ray disc, which the drive reads at a constant linear speed. Add --media bd?"):
            dev.close() if hasattr(dev, "close") else None
            raise _Rerun(["--media", "bd"])


def _blu_ray_speed(dev, args) -> None:
    """--media has no BD, so a multiple was worked out for DVD. Only the disc can tell."""
    multiple = getattr(args.speed, "multiple", None)
    if multiple is None or args.sim:
        return
    from .scsi import DATA_IN
    cfg = dev.execute(mmc.get_configuration(), 4096, DATA_IN)
    if cfg.ok and mmc.media_family(mmc.parse_configuration(cfg.data).get("current_profile")) == "bd":
        args.speed = round(multiple * mmc.BD_1X_KBPS)
        print(f"This is a Blu-ray disc, so {multiple:g}x is {args.speed} kB/s")


def _measuring(dev, args):
    """What the probe reads through: at a terminal, a wrapper that also draws the progress line."""
    if not ui.term().interactive and not os.environ.get("DISCPROBE_EVENTS"):
        return dev
    limit = f" It gives up after {args.max_minutes:g} minutes." if getattr(args, "max_minutes", 0) else ""
    ui.say(f"Measuring on {getattr(dev, 'name', 'the drive')}. Ctrl+C stops and keeps what was measured.{limit}", "dim")
    return ui.ProgressDevice(dev)


def _identity(args, dev) -> dict | None:
    """Which drive and disc this is, for the results list. Before any timing; a simulated run has none."""
    if getattr(args, "sim", None):
        return None
    try:
        return info.identify(dev, getattr(args, "media", None))
    except Exception:       # a label, never worth stopping a measurement
        return None


def _geo_clv(args):
    """`geo --media bd`: the drive holds the linear speed, so fit spindle periods against LBA.

    The angle ladder needs the *angular* rate held constant, which no BD drive offers: MMC has no
    command that sets a read speed for Blu-ray, and the drive picks CLV for BD-R/BD-RE and CAV for
    a pressed BD-ROM. Under CLV a turn takes T = 2*pi*r/v, and r^2 grows linearly with the sector,
    so T^2 is a straight line in LBA and carries (r0, pitch) up to one anchor.
    """
    from .clv import DEFAULT_ZONES, ClvLadder, ConstantAngularVelocity, write_outputs
    if args.media == "cd":
        if args.linear_mm_s is None and not getattr(args, "cd_clv_pitch_explicit", False):
            sys.exit("CD CLV needs an independently known --linear-mm-s or an explicit --pitch-um anchor; --speed is only a request.")
        if args.linear_mm_s is not None and getattr(args, "cd_clv_pitch_explicit", False):
            sys.exit("Choose one CD CLV anchor: --linear-mm-s or --pitch-um.")
        anchor = args.linear_mm_s if args.linear_mm_s is not None else args.pitch_um
        if not math.isfinite(anchor) or anchor <= 0:
            sys.exit("The CD CLV anchor must be finite and positive.")
        print(i18n.tr(guide.CD_CLV_LIMIT))
        if args.bd_zones is not None and args.bd_zones < 5:
            sys.exit("CD CLV needs at least five zones (--clv-zones).")
    if args.sectors != 1:
        sys.exit("--sectors 1 only: a CLV fit uses the time to turn once, which one sector gives")
    if not args.sim:
        _need_windows()
        from .spti import raise_priority
        raise_priority()
    dev = _open(args)
    _check_disc(dev, args)
    _blu_ray_speed(dev, args)
    reader = _measuring(dev, args)
    zones = DEFAULT_ZONES
    if args.bd_zones:
        if args.bd_zones < 3:
            sys.exit("--bd-zones needs at least 3: a straight line through two points has nothing left to check")
        zones = tuple(0.05 + 0.90 * i / (args.bd_zones - 1) for i in range(args.bd_zones))
    ladder = ClvLadder(reader, media=args.media, reps=args.reps, zones=zones,
                       speed_kbs=None if args.sim else args.speed,
                       pitch_um=None if args.linear_mm_s else args.pitch_um,
                       v_m_s=None if not args.linear_mm_s else args.linear_mm_s / 1000.0,
                       r0_mm=args.r0_mm, host_delay_ms=args.host_delay_ms,
                       fit_offset=args.fit_offset)
    ladder.tp.summary["identity"] = _identity(args, dev)
    ladder.tp.summary["args"] = {k: v for k, v in vars(args).items() if k != "func"}
    if args.sim:
        ladder.tp.summary["simulated"] = True
    progress, log = None, print
    if reader is not dev:
        def status():
            period = (ladder.summary or {}).get("period") or {}
            done = len(period.get("zones") or [])
            if not period:
                stage = "cache test" if "cache" not in ladder.summary else "waiting for a steady spindle"
                return None, stage, None
            return done / max(len(ladder.zones), 1), f"zone {done}/{len(ladder.zones)}", None
        status.location = lambda: ({"lba": reader.event_lba} if hasattr(reader, "event_lba") else {})
        progress = reader.progress = ui.Progress(status, keys=ui.open_keys(), pulse=reader.read_times,
                                                 wait_s=GEO_WAIT_S)
        log = ladder.log = ladder.tp.log = progress.log
    out = _outdir(args, "geo", dev)
    stopped, res, hand_off = None, None, None
    try:
        res = ladder.run()
    except ConstantAngularVelocity as e:
        # Not a failure: this disc wants the other instrument. The probe is all this run did.
        if args.media == "cd":
            stopped = str(e)
            log(f"stopped: {e}")
        else:
            hand_off = e
    except (RuntimeError, ValueError) as e:
        log(f"stopped: {e}")
        stopped = str(e)
    finally:
        if progress:
            progress.close()
        dev.close() if hasattr(dev, "close") else None
        if (ladder.summary or {}).get("period") and hand_off is None:
            write_outputs(ladder, out, None if res else stopped or "interrupted")
    if hand_off is not None:
        print(i18n.tr("This disc turns at a constant angular velocity, so its period carries no radius. "
                      "Measuring the spiral from sector addresses instead."))
        args.bd_angular = True
        args.sectors = 32 if getattr(args, "sectors", 1) == 1 else args.sectors
        return cmd_geo(args)
    if res:
        print()
        print(i18n.tr("r0 {a} mm, pitch {b} um, linear speed {c} m/s  (R^2 {d} over {e} zones, anchor: {f})")
              .format(a=f"{res['r0_mm']:.4f}", b=f"{res['pitch_um']:.4f}", c=f"{res['v_m_s']:.3f}",
                      d=f"{res['r2']:.6f}", e=res["zones_used"], f=i18n.tr(res["anchor"])))
        sigma = [i18n.tr("r0 {a} um").format(a=f"{res['sigma_r0_mm'] * 1000:.1f}")
                 if res.get("sigma_r0_mm") is not None else i18n.tr("r0 (anchor)"),
                 i18n.tr("pitch {a} um").format(a=f"{res['sigma_pitch_um']:.4f}")
                 if res.get("sigma_pitch_um") is not None else i18n.tr("pitch (anchor)")]
        if res.get("sigma_v_m_s") is not None:
            sigma.append(i18n.tr("speed {a} m/s").format(a=f"{res['sigma_v_m_s']:.3f}"))
        print(i18n.tr("1 sigma: {a}").format(a=("，" if i18n.active() == "zh" else ", ").join(sigma)))
        derived = (ladder.summary or {}).get("derived") or {}
        if derived.get("outer_radius_mm"):
            tail = i18n.tr(" (a full 25 GB layer: the standard puts its edge at 58.0 mm)") if derived.get("full_layer") else ""
            print(i18n.tr("the outermost sector lands at {a} mm{b}").format(a=f"{derived['outer_radius_mm']:.3f}", b=tail))
        brk = res.get("break_fit")
        if brk:
            print(i18n.tr("the periods do not lie on one line: two lines with a break at sector {a} leave {b}% less "
                          "residual. That is what a disc read in zones looks like, and the numbers above are the "
                          "single line through it, not a spiral measurement")
                  .format(a=f"{brk['break_lba']:,}", b=f"{brk['improvement'] * 100:.0f}"))
        extrapolated = res.get("r0_extrapolated_mm")
        if extrapolated and extrapolated > 0.5:
            print(i18n.tr("r0 sits {a} mm inside the innermost zone ({b} mm), so it comes from the line's curvature "
                          "rather than from a point measured there; the tolerance above is the fit's, not the model's")
                  .format(a=f"{extrapolated:.2f}", b=f"{res['r_first_mm']:.2f}"))
        if res.get("offset_ms") is not None:
            sig = res.get("sigma_offset_ms")
            fitted = res.get("offset_fitted_ms")
            if fitted is not None and not res.get("offset_ms"):
                print(i18n.tr("period offset: {a} us (1 sigma {b} us), which the data cannot tell from zero, "
                              "so the fit left it out and r0 is the plain answer")
                      .format(a=f"{fitted * 1000:+.1f}", b="?" if sig is None else f"{sig * 1000:.1f}"))
            else:
                print(i18n.tr("period offset {a} us (1 sigma {b} us): the fit already took it out of r0")
                      .format(a=f"{res['offset_ms'] * 1000:+.1f}",
                              b="?" if sig is None else f"{sig * 1000:.1f}")
                      if sig is not None else
                      i18n.tr("period offset {a} us: the fit already took it out of r0")
                      .format(a=f"{res['offset_ms'] * 1000:+.1f}"))
        dropped = res.get("zones_dropped_lbas") or []
        if dropped:
            shown = ", ".join(f"{int(x):,}" for x in dropped[:4])
            more = "" if len(dropped) <= 4 else f" and {len(dropped) - 4} more"
            print(i18n.tr("Left {a} zone(s) out of the fit: their period did not follow the line "
                          "(sector {b}{c}). A zone can lock to a harmonic of the spindle instead of the "
                          "spindle itself; zones.csv lists every zone, used or not")
                  .format(a=len(dropped), b=shown, c=more))
        print(i18n.tr("zones.csv, summary.json: {a}").format(a=os.path.abspath(out)))
        last = derived.get("last_lba")
        if last is not None and args.media == "bd" and not getattr(args, "sim", None):
            print(i18n.tr("For a DiscImageStudio preset: {a} disexport --geo {b} --sectors {c} --install")
                  .format(a=guide.PROG, b=out, c=f"{int(last) + 1}"))
        if res.get("v_m_s_anchor") is None:          # pitch was the anchor, so pitch is still nominal
            print(i18n.tr("Pass --linear-mm-s to trade that anchor for a pitch: without it the pitch is nominal "
                          "and only r0/v is measured."))
        if args.media == "cd":
            print(i18n.tr(guide.CD_CLV_LIMIT))
    else:
        print("no results written: it stopped before the fit.")
    if res is None:
        sys.exit(1)


def _geo_fit(args, media=None) -> dict:
    """Load --geo, which may be a summary.json, a geo result folder or `latest`."""
    try:
        if args.geo.lower() == "pick":
            from . import picker
            chosen = picker.choose(media)
            if chosen is None:
                sys.exit("Nothing chosen.")
            path = os.path.join(chosen.path, "summary.json")
            print(f"Using the geo result you chose: {guide.describe_chosen(path)}")
        else:
            path = guide.resolve_geo(args.geo, media, radius_range=getattr(args, '_radius_range', None))
    except ValueError as e:
        sys.exit(str(e))
    if args.geo.lower() == "latest":
        print(f"Using the latest geo result: {guide.describe_chosen(path)}")
        chosen = guide.latest_geo(media, radius_range=getattr(args, '_radius_range', None))
        if chosen is not None and not chosen.reliable(getattr(args, '_radius_range', None)):
            print("It was judged too noisy to rely on, and there is nothing better. To see them all: python -m discprobe results --pick")
        elif chosen is not None and guide.passed_over(chosen, media):
            print(f"Left out {guide.passed_over(chosen, media)} newer run(s) judged too noisy. To see them all: python -m discprobe results --pick")
    args.geo = path
    try:
        with open(path, encoding="utf-8") as f:
            fit = json.load(f)["fit"]
        if fit.get("model") == "clv" and fit.get("media") == "cd":
            sys.exit(i18n.tr(guide.CD_CLV_LIMIT))
        return fit
    except FileNotFoundError:
        latest = guide.latest_geo(media)
        _fail(f"no such geo result: {path}",
              [f"Your last measurement is {guide.describe_chosen(os.path.join(latest.path, 'summary.json'))}.",
               "Use it with --geo latest."] if latest else ["Run geo first, then use --geo latest."])
    except (ValueError, KeyError, TypeError):
        sys.exit(f"{path} is not the summary.json of a geo run (it has no geometry fit)")


def _refuse_audio_fit(fit: dict) -> None:
    """image and tiles write a data track. A fit of a CD-DA track counts from DiscImageStudio's origin, not that one's."""
    if fit.get("track") == "audio":
        _fail("This geo result measured an audio track burned by DiscImageStudio, which counts positions from a "
              "different origin than the data track written here, so the design would land in the wrong place.",
              ["For image or tiles, use a geo result from a burned data disc: python -m discprobe results --pick",
               "This result is for a DiscImageStudio preset: python -m discprobe disexport"])


def _outdir(args, kind: str, dev) -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    tag = getattr(dev, "name", "drive").replace(":", "")
    path = os.path.join(args.out, f"{kind}-{tag}-{stamp}")
    os.makedirs(path, exist_ok=True)
    _Parser.last_out = path
    return path


def _write_json(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def cmd_list(args):
    _need_hardware_platform()
    from .device import list_optical_drives
    drives = list_optical_drives()
    print("\n".join(drives) if drives else "no optical drives found")
    _next(guide.after_list(drives))


def cmd_info(args):
    if getattr(args, "image", None):
        return cmd_whois(args)
    dev = _open(args)
    try:
        report = info.collect(dev)
        from . import discid
        try:
            report["disc_identity"] = discid.read_device(dev, detailed=True)
            identity = report['disc_identity']['record']
            if identity and getattr(args, "register", None):
                report["disc_identity"]["register"] = discid.match_register(identity, args.register)
        except (OSError, ValueError) as exc:
            report["disc_identity"] = dict(status="unavailable_or_invalid", error=str(exc), hash_verified=False)
    finally:
        dev.close() if hasattr(dev, "close") else None
    out = _outdir(args, "info", dev)
    _write_json(os.path.join(out, "info.json"), report)
    for line in info.summarize(report):
        print(line)
    print(json.dumps(report["disc_identity"], ensure_ascii=False, indent=2))
    print(f"\nFull dump: {os.path.abspath(out)}")
    _next(guide.after_info(args, report))


def cmd_whois(args):
    from . import discid
    if getattr(args, "image", None) and (args.drive or getattr(args, "sim", None)):
        sys.exit("Choose --image or --drive, not both")
    try:
        if getattr(args, "image", None):
            result = discid.read_image(args.image, detailed=True)
        else:
            dev = _open(args)
            try:
                result = discid.read_device(dev, detailed=True)
            finally:
                dev.close() if hasattr(dev, "close") else None
        record = result['record']
        if record and getattr(args, "register", None):
            result["register"] = discid.match_register(record, args.register)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps(dict(status="unavailable_or_invalid", reason="read_failed", hash_verified=False, error=str(exc)), ensure_ascii=False))
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result['reason'] != 'ok':
        sys.exit(1)


def cmd_disc(args):
    """Which disc is in the drive, for the web page: a handful of read-only commands, nothing written to
    disk, one JSON line on stdout ({"tray", "drive", "disc"}). `info` is the full dump."""
    import json
    from . import webui_catalog
    dev = _open(args)
    try:
        report = info.quick(dev)
    finally:
        dev.close() if hasattr(dev, "close") else None
    tur = report.get("test_unit_ready", {})
    inq = (report.get("inquiry") or {}).get("parsed") or {}
    ready = "sense" not in tur and "error" not in tur
    out = dict(tray=tray_state(tur.get("sense"), ready) if "error" not in tur else "unknown",
               drive=f"{inq.get('vendor', '')} {inq.get('product', '')}".strip() or None,
               disc=webui_catalog.disc_report(report) if ready else None)
    print(json.dumps(out, ensure_ascii=False))


def tray_state(sense, ok: bool) -> str:
    """What TEST UNIT READY says about the tray: ready, open, empty (closed, no disc), loading, changed."""
    if ok:
        return "ready"
    text = str(sense or "")
    if text.startswith("2/3A/"):
        return "open" if text[5:] == "02" else "empty"
    if text.startswith("6/28/"):
        return "changed"
    return "loading" if text.startswith("2/04/") else "unknown"


def cmd_swap(args):
    """Wait, read-only, while a disc is taken out and another put in: TEST UNIT READY every half second until the
    drive has been without a disc (or reports a new one) and then has one ready. Nothing moves the tray."""
    import time
    from .scsi import DATA_NONE
    dev = _open(args)
    deadline = time.monotonic() + args.minutes * 60
    seen, out = None, False
    try:
        while time.monotonic() < deadline:
            res = dev.execute(mmc.test_unit_ready(), 0, DATA_NONE)
            state = tray_state(res.sense, res.ok)
            if state != seen:
                ui.event("tray", state=state)
                print({"ready": "Disc ready", "open": "Tray open", "empty": "Tray closed, no disc",
                       "loading": "Reading the disc...", "changed": "The drive reports a new disc",
                       "unknown": f"Not ready ({res.sense})"}[state], flush=True)
                seen = state
            if state in ("open", "empty", "changed"):
                out = True
            elif state == "ready" and (out or args.ready_now):
                return
            time.sleep(0.5)
    finally:
        dev.close() if hasattr(dev, "close") else None
    sys.exit(f"No disc change within {args.minutes:g} minutes")


def cmd_timing(args):
    if not args.sim:
        _need_hardware_platform()
        from .device import raise_priority
        if not raise_priority():
            print("note: could not raise process priority")
    dev = _open(args)
    _check_disc(dev, args)
    _blu_ray_speed(dev, args)
    targets = [float(x) for x in args.targets.split(",")] if args.targets else timing.DEFAULT_TARGETS
    reader = _measuring(dev, args)
    probe = timing.TimingProbe(
        reader, read_method=args.read, reps=args.reps, period_reads=args.period_reads,
        targets=targets, ref_fraction=args.ref, speed_kbs=args.speed, pure_cav=args.cav,
        evict_sectors=args.evict_sectors, sectors=args.sectors, host_delay_ms=args.host_delay_ms, media=args.media,
        stop_if_not_cav=not args.force, time_limit_s=args.max_minutes * 60 if args.max_minutes else None)
    probe.summary["identity"] = _identity(args, dev)
    progress = None
    if reader is not dev:
        progress = reader.progress = ui.Progress(ui.timing_status(probe, reader), keys=ui.open_keys(), pulse=reader.read_times, wait_s=TIMING_WAIT_S)
        probe.log = progress.log
    stopped = None
    finished = False
    try:
        summary = probe.run()
        finished = True
    except timing.NoReadableDisc as e:
        stopped = str(e)
    finally:
        if progress:
            progress.close()
        dev.close() if hasattr(dev, "close") else None
        out = _outdir(args, "timing", dev)
        rows = probe.events_as_rows()
        if rows:
            with open(os.path.join(out, "events.csv"), "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
        summary = probe.summary
        if not finished:        # also for Ctrl+C or a drive that vanished, which pass through here
            summary["stopped"] = stopped or "interrupted"
        summary["device"] = getattr(dev, "name", None)
        summary["args"] = {k: v for k, v in vars(args).items()
                           if k != "func" and (k != "media" or v != "dvd")}
        _write_json(os.path.join(out, "summary.json"), summary)
        ui.result_event("timing", out, summary.get("stopped"))
        print(f"\nRaw events and summary: {os.path.abspath(out)}")
    if stopped:
        _fail(stopped, guide.after_timing_stop(args, stopped))
    if progress:
        ui.say(f"Finished in {ui.clock(ui.time.monotonic() - progress.started)}", "dim")
    _next(guide.after_timing(args, summary), args)


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
        with ui.writing(args.output, layout.total_sectors) as log:
            spec_path = write_iso(args.output, layout, log=log)
    except ValueError as e:
        sys.exit(str(e))
    with ui.busy("Checking what was written..."):
        problems = verify_iso(args.output, layout)
    print("Verified: sampled sectors in every ring record the intended byte" if not problems
          else "VERIFY FAILED:\n  " + "\n  ".join(problems[:10]))
    print(f"Layout: {os.path.abspath(spec_path)}  (needed by ringscan)")
    _cdrdao_toc(args)
    print("Burn it and note the speed.")
    for line in guide.burn_steps(args.output, args.media):
        print(line)
    print("The file system is an empty ISO 9660 placeholder.")
    if problems:
        sys.exit(1)
    ui.iso_ready(args.output)
    ui.burn_warning()


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
        with ui.writing(args.output, layout.total_sectors) as log:
            from . import discid
            spec_path = write_iso(args.output, layout, log=log, **discid.options(args))
    except ValueError as e:
        sys.exit(str(e))
    with ui.busy("Checking what was written..."):
        problems = verify_iso(args.output, layout)
    print("Verified: guards are pure, bands follow their patterns" if not problems
          else "VERIFY FAILED:\n  " + "\n  ".join(problems[:10]))
    print(f"Layout: {os.path.abspath(spec_path)}  (needed by calscan)")
    print("Burn it.")
    for line in guide.burn_steps(args.output):
        print(line)
    print("The file system is an empty ISO 9660 placeholder.")
    if problems:
        sys.exit(1)
    ui.iso_ready(args.output)
    ui.burn_warning()


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
    media = getattr(args, "media", "dvd")
    from . import read_completion
    if getattr(args, 'refit', None):
        try:
            source = read_completion.summary_path(args.refit)
            saved = json.loads(source.read_text(encoding='utf-8'))
            value, origin = read_completion.resolve(saved.get('identity'), args.completion_sectors,
                                                     saved['fit'].get('media', 'dvd'))
            if args.completion_sectors is None and origin is None:
                value = saved['fit'].get('completion_sectors', 0)
                origin = dict(origin='stored')
            output = args.out if args.out != 'results' else os.path.join(
                args.out, source.parent.name + f'-completion-{value}')
            fit, method = read_completion.save_reapplied(source, value, output, source=origin)
        except (OSError, ValueError) as e:
            sys.exit(str(e))
        print(read_completion.notice(value, origin))
        print(f"Completion offset applied: {method}; u={fit['u']:.8f}, v={fit['v']:.10f}; {output}")
        return
    if media != 'dvd' and getattr(args, 'completion_sectors', None) is not None:
        sys.exit('--completion-sectors is for DVD')
    if getattr(args, "cd_clv", False):
        if media != "cd":
            sys.exit("--cd-clv requires --media cd")
        return _geo_clv(args)
    if media == "bd" and not getattr(args, "bd_angular", False):
        return _geo_clv(args)
    from .geo import Ladder, write_outputs
    allowed = (1,) if media == "cd" else (1, 16, 32) if media == "bd" else (1, 16)
    if args.sectors not in allowed:
        sys.exit(f"--sectors {args.sectors}: geo reads 1 sector, on a DVD 16 for one whole ECC block, "
                 "on a Blu-ray 32 for one recording unit")
    ranges = None
    if args.ranges:
        try:
            ranges = [tuple(int(x) for x in part.split("-")) for part in args.ranges.split(",")]
        except ValueError:
            ranges = [()]
        if any(len(r) != 2 or r[0] >= r[1] for r in ranges):
            sys.exit(f"--ranges {args.ranges}: give LBA ranges as start-end, for example 70000-1900000 "
                     "or 2000-90000,120000-356000")
    elif args.rings_layout:
        from .rings import RingLayout
        lay = RingLayout.load(args.rings_layout)
        m = args.margin_sectors
        ranges = [(r["lba_start"] + m, r["lba_end"] - m) for r in lay.rings
                  if r["texture"].upper() == args.texture.upper()]
    if not args.sim:
        _need_hardware_platform()
        from .device import raise_priority
        raise_priority()
    dev = _open(args)
    _check_disc(dev, args)
    _blu_ray_speed(dev, args)
    reader = _measuring(dev, args)
    ladder = Ladder(reader, ranges=ranges, r0_mm=args.r0_mm, pitch_um=args.pitch_um, bit_nm=args.bit_nm,
                    reps=args.reps, max_targets=args.max_targets, ref_lba=args.ref_lba,
                    speed_kbs=None if args.sim else args.speed, host_delay_ms=args.host_delay_ms, media=args.media,
                    chi2_abort=args.chi2_abort, sectors=args.sectors,
                    read_offset_bytes=args.read_offset_bytes, auto_correct=not getattr(args, 'no_auto_correction', False))
    ladder.tp.summary["identity"] = _identity(args, dev)
    try:
        value, origin = read_completion.resolve(ladder.tp.summary['identity'],
                                                 getattr(args, 'completion_sectors', None), media)
    except ValueError as e:
        dev.close() if hasattr(dev, 'close') else None
        sys.exit(str(e))
    ladder.completion_sectors, ladder.completion_source = value, origin
    if media == 'dvd':
        print(read_completion.notice(value, origin))
    ladder.tp.summary["args"] = {k: v for k, v in vars(args).items() if k != "func"}
    if args.sim:
        ladder.tp.summary["simulated"] = True
    progress, log = None, print
    if reader is not dev:
        progress = reader.progress = ui.Progress(ui.geo_status(ladder, reader), keys=ui.open_keys(), pulse=reader.read_times, wait_s=GEO_WAIT_S)
        log = ladder.log = progress.log
    out = _outdir(args, "geo", dev)
    stopped = None
    res = None
    try:
        res = ladder.run()
    except RuntimeError as e:
        log(f"stopped: {e}")
        stopped = str(e)
    finally:
        if progress:
            progress.close()
        dev.close() if hasattr(dev, "close") else None
        if ladder.targets and ladder.cov is not None:
            write_outputs(ladder, out, None if res else stopped or "interrupted")   # also for Ctrl+C or a drive that vanished
    at_terminal = ui.term().interactive
    detail = (lambda text: ui.say(text, "dim")) if at_terminal else print    # at a terminal the plain summary comes first
    if res:
        print()
        if at_terminal:
            ui.say(guide.geo_summary(res, len(ladder.targets)))
        detail(f"u = r0/b = {res['u']:.3f}, v = p/b = {res['v']:.7f}  (chi2/dof {res['chi2_per_dof']:.2f}, "
               f"residual rms {res['residual_rms_deg']:.3f} deg)")
        detail(f"With bit length {res['bit_nm_assumed']} nm: r0 {res['r0_mm_at_bit']:.5f} mm, "
               f"pitch {res['pitch_um_at_bit']:.6f} um")
        detail(f"Angle uncertainty across the measured span {res['measured_span_mm'][0]}-"
               f"{res['measured_span_mm'][1]} mm: {res['angle_sigma_measured_span_deg']:.3f} deg (1 sigma); "
               f"across {'25' if args.media == 'cd' else '24'}-58 mm: {res.get('angle_sigma_deg', float('nan')):.2f} deg")
        coverage = res['coverage']
        detail(f"Measured intervals (mm): {coverage['measured_intervals_mm']}. Largest unsampled gap: "
               f"{coverage['largest_unsampled_gap_mm']:.3f} mm. Model bias between samples is not bounded.")
        detail(f"Geometry measurement took {res['elapsed_s']:.1f} s; status: {res['completion_status']}.")
    if res and res["chi2_per_dof"] > 2 and not at_terminal and not res.get('correction_file'):
        print(f"The constant-pitch fit leaves more than noise. See whether a varying pitch fits better: "
              f"python tools/geo_polyfit.py {out}")
    if ladder.targets and ladder.cov is not None:
        print(f"targets.csv, summary.json, events.csv: {os.path.abspath(out)}")
        if not res:
            print("It stopped early, so `--geo latest` won't use these. Don't burn from them.")
    elif stopped not in mmc.NOT_READY:
        print("no results written: it stopped before the first fit. Run `timing` to see how noisy this drive is.")
    if progress and res:
        ui.say(f"Finished in {ui.clock(ui.time.monotonic() - progress.started)}", "dim")
    if res:
        _next(guide.after_geo(args, res, out), args)
    else:
        unreadable = [] if ladder.auto_ranges else sorted({e.lba for e in ladder.tp.events if e.sense.startswith("3/")})
        _next(guide.after_geo_stop(args, stopped or "", unreadable))
    if res is None:     # scripts must not take a run that stopped for one that finished
        sys.exit(1)


def _warn_other_run(args, fit) -> None:
    """A correction left over from an earlier run still loads and still gives a tidy result, so nothing else would show it."""
    from . import imagedisc
    if not args.correction and fit.get('correction_file'):
        name = fit['correction_file']
        if os.path.basename(name) != name:
            sys.exit('invalid automatic correction filename')
        args.correction = os.path.join(os.path.dirname(args.geo), name)
        if not os.path.isfile(args.correction):
            sys.exit('automatic angle correction is missing; restore correction.json for this geo run')
        print(f'Using the automatic angle correction: {args.correction}')
    if not args.correction:
        return
    try:
        run = imagedisc.correction_other_run(args.correction, fit["u"], fit["v"], args.geo)
    except (OSError, ValueError, KeyError):     # the step that needs the file says what is wrong with it
        return
    if run and not imagedisc.correction_from_timing(args.correction):
        print(f"Warning: {os.path.basename(args.correction)} was measured on a grid burned with another geo run "
              f"({run}), so it does not fit this one. Use that run, or burn and scan a grid made with this one.")
    elif run:
        print(f"Warning: {os.path.basename(args.correction)} was made from another geo run ({run}), so it does not fit this one. Make it again:")
        print(f"  python tools/geo_polyfit.py {os.path.dirname(args.geo) or '.'} --write-correction {args.correction} --order quadratic")
    elif imagedisc.correction_unchecked(args.correction):
        print(f"Note: {os.path.basename(args.correction)} does not record a geo run that can be read, so it could not be "
              "checked against this one. It only fits the geometry its scanned grid was burned with.")


def cmd_edit(args):
    from . import editor, imagecheck
    try:
        project, output = editor.start(args.file, args.output)
        saved = editor.run(project, output, imagecheck._inner_mm(args), args.r_max)
    except ValueError as e:
        sys.exit(str(e))
    if not saved:
        print("Nothing saved.")
        return
    print(f"Saved: {os.path.abspath(output)}")
    _next(guide.after_edit(output, args.media))


def cmd_simulate(args):
    from . import imagedisc, simulate
    if args.random_label_image:
        if not args.output or args.sheet:
            sys.exit("--random-label-image needs --output and does not support --sheet")
        try:
            simulate.random_label(args.random_label_image, args.size, args.actual_geo,
                                  args.camera, args.flash, rotate=args.rotate).save(args.output)
        except (OSError, ValueError, KeyError) as e:
            sys.exit(f"simulate: {e}")
        print(i18n.tr("Prediction from a model, not a photo; real contrast and brightness may differ."))
        return
    if args.actual_geo:
        sys.exit("--actual-geo needs --random-label-image")
    try:
        if args.work:
            from .editor_preview import Renderer
            from pathlib import Path
            if not args.output or args.sheet:
                raise ValueError("work simulation requires --output; use --rotate for another view")
            document=json.loads(Path(args.work).read_text(encoding="utf-8-sig"))
            data,_=Renderer().render(dict(document=document,size=args.size,
                pose=dict(camera=args.camera,flash=args.flash,rotate=args.rotate)))
            Path(args.output).write_bytes(data)
            print(i18n.tr("Prediction from a model, not a photo; real contrast and brightness may differ."))
            return
        if args.design:
            from . import design as project_file
            design = project_file.render(project_file.load(args.design))
        elif args.design_npy:
            design = simulate.load_design(args.design_npy)
        else:
            design = imagedisc.picture_design(args.picture, args.diameter_mm)
        if not args.output and not args.sheet:
            raise ValueError("give --output or --sheet")
        if args.output:
            simulate.render(design, args.size, args.dark, args.light, args.camera, args.flash, args.rotate).save(args.output)
        if args.sheet:
            simulate.sheet(design, args.picture, args.size, args.dark, args.light, args.camera, args.flash).save(args.sheet)
    except (ValueError, TypeError) as e:
        sys.exit(f"simulate: {e}")
    print(i18n.tr("Prediction from a model, not a photo; real contrast and brightness may differ."))


def _require_fit_media(args, fit, tiles: bool = False) -> None:
    """A picture is placed and encoded for one medium: a CD fit run through the DVD writer (a missing
    --media cd) still builds an ISO that verifies against its own wrong model (the 6pro audit of 1f7f92e)."""
    measured = "bd" if (fit.get("model") == "clv" or fit.get("media") == "bd") else fit.get("media") or "dvd"
    wanted = getattr(args, "media", None) or "dvd"
    if measured == wanted:
        return
    if measured == "cd":
        sys.exit("This geometry was measured on a CD; add --media cd to make a CD tile target." if tiles else
                 "This geometry was measured on a CD; add --media cd to make a CD picture.")
    names = {"dvd": "DVD", "bd": "Blu-ray"}
    sys.exit(f"This geometry was measured on a {names.get(measured, measured)}, but a "
             f"{'CD' if wanted == 'cd' else 'DVD'} {'tile target' if tiles else 'picture'} needs one measured on that disc.")


def cmd_compose(args):
    from .editor_ops import compose_file
    try:
        doc = compose_file(args.work, args.out)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        sys.exit(str(exc))
    print(f"{args.out}: uint8 material labels; {len(doc['materials'])} textures")
    print(f"Texture order: {os.path.splitext(args.out)[0]}.textures.json")


def cmd_image(args):
    from . import imagedisc
    writer = imagedisc
    if args.media == "cd":
        from . import cdimage as writer
    # Explicit files (including an audio-track fit) can be rejected before loading
    # a design. Resolve `latest` after the drawing span is known, so a partial run
    # can still be selected for a small picture inside its measured interval.
    fit = None
    if args.geo.lower() != 'latest':
        fit = _geo_fit(args, args.media)
        _require_fit_media(args, fit)
        _refuse_audio_fit(fit)
    if args.design and (args.design_npy or args.picture):
        sys.exit("--design replaces --picture and --design-npy: give one of them")
    if args.design_npy:
        import numpy as np
        design = np.load(args.design_npy)
        try:
            imagedisc.check_cells(design, args.cell_um)
        except ValueError as e:
            sys.exit(str(e))
        if args.textures:
            design = design.astype(np.uint8)
        elif design.dtype != bool:
            sys.exit("a label design (not boolean) needs --textures, one per label")
        kind = f"design {os.path.basename(args.design_npy)}"
    elif args.picture or args.design:
        if args.design:
            from . import design as project_file
            try:
                design = project_file.render(project_file.load(args.design), size=imagedisc.CELL_SIDES[args.cell_um or 20])
            except ValueError as e:
                sys.exit(str(e))
        else:
            design = imagedisc.picture_design(args.picture, args.diameter_mm, cell=(args.cell_um or 20) / 1000)
        if args.media == "cd":      # the file system sits here, and write_iso refuses a drawing on top of it
            kept = imagedisc.clear_inside(design, 26.0)
            if (kept != design).any():
                ui.say("The middle of a CD holds its file system, so the picture is left out inside 26 mm radius.", "dim")
            design = kept
        kind = f"design {os.path.basename(args.design)}" if args.design else f"picture {os.path.basename(args.picture)}"
    else:
        design = imagedisc.grid_design(r_min=26.0 if args.media == "cd" else 24.5,
                                      r_max=args.r_max, line=args.line_mm, size=imagedisc.CELL_SIDES[args.cell_um or 20])
        kind = f"grid, {args.line_mm} mm lines"
    args._radius_range = imagedisc.drawing_span(design)
    fit = fit or _geo_fit(args, args.media)
    _require_fit_media(args, fit)
    _refuse_audio_fit(fit)
    _warn_other_run(args, fit)
    u, v, bit = fit['u'], fit['v'], fit['bit_nm_assumed']
    if args.along_track_frames:
        from .cd import FRAME_BITS
        if args.media != 'cd':
            sys.exit('--along-track-frames is for CD')
        u = math.sqrt(u * u - v * args.along_track_frames * FRAME_BITS / math.pi)
    total = writer.sectors_to_radius(u, v, bit, args.r_max + 0.6)
    if args.media == "dvd":
        total = min(total, 2295104)
    else:
        from .cd import check_capacity, CAPACITY
        # As on DVD, a drawing out to the rim stops where the disc does. IMAPI refused 359849 and 359800 sectors
        # on an 80-minute CD-R and burned 359600 (KNOWLEDGE, 2026-11-04): closing the disc needs room.
        room = CAPACITY - 249
        if total > room:
            print(f"The disc ends before {args.r_max:g} mm: the image stops at {room} sectors, and the picture's "
                  "outermost ring is left out.")
            total = room
        check_capacity(total)
    first = args.start_lba
    if first and args.media != "dvd":
        sys.exit("--start-lba is for DVD for now")
    if first and not 32 <= first < total:
        sys.exit(f"--start-lba must lie between 32 and the image's end, LBA {total}")
    if first:
        r_first = bit * 1e-6 * math.sqrt(u * u + v * first * imagedisc.SECTOR_BITS / math.pi)
        print(f"Appending from LBA {first} (about {r_first:.2f} mm): the file holds only that part, with no file system. "
              "Whatever the design has inside that radius is left out.")
    lead = 0
    if args.random_below_mm:
        if args.media != "dvd":
            sys.exit("--random-below-mm is for DVD for now")
        lead = min(writer.sectors_to_radius(u, v, bit, args.random_below_mm), total)
        print(f"Random data up to {args.random_below_mm:g} mm (LBA {lead}); the picture starts there.")
    extra = {**({"first_lba": first} if first else {}), **({"lead_lba": lead} if lead else {})}
    if args._radius_range:
        from .coverage import range_warning
        if args.media == 'cd':
            from .cd import SECTOR_BITS as picture_bits
        else:
            picture_bits = imagedisc.SECTOR_BITS
        radius_at = lambda l: bit * 1e-6 * math.sqrt(u * u + v * l * picture_bits / math.pi)
        span = [max(args._radius_range[0], radius_at(max(first, lead))),
                min(args._radius_range[1], radius_at(total))]
        if span[1] > span[0]:
            warning = range_warning(fit, span)
            if warning:
                print(f'Warning: {warning}')
