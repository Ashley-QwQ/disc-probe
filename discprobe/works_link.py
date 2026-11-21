"""Completion hooks for image and burn commands; no drive access here."""
import os
from pathlib import Path
from . import i18n, works

MEASUREMENT_ENV = "DISCPROBE_MEASUREMENT_BURN"


def add_options(sub):
    for name in ("image", "burn", "calibrate", "checkdisc"):
        sub.choices[name].add_argument("--work", help="append successful image or burn records to this work")
    # calibrate forwards these to its burn child, alongside --work.
    sub.choices["calibrate"].add_argument("--disc-code", dest="disc_id_code", help="disc code for the work burn record")


def check_work(args):
    ident = getattr(args, "work", None)
    if ident:
        try:
            return works.Store().show(ident)
        except (works.WorkError, OSError) as exc:
            raise SystemExit(i18n.tr(str(exc))) from None


def _completed(args, iso, **fields):
    if getattr(args, "work", None):
        try:
            works.Store().link(args.work, iso, disc_code=getattr(args, "disc_id_code", None), **fields)
        except (works.WorkError, OSError) as exc:
            raise SystemExit(i18n.tr("work record could not be saved: {a}").format(a=str(exc))) from None


def image_completed(args):
    design = os.environ.get("DISCPROBE_IMAGE_WORK_DESIGN")
    _completed(args, args.output, kind="iso", **({"source_design_asset": design} if design else {}))


def burn_completed(args, result):
    if result:
        measurement = os.environ.get(MEASUREMENT_ENV) == "1"
        if measurement and not getattr(args, "work", None):
            return
        if not getattr(args, "work", None):
            # CLI and unsaved web jobs must remain reviewable after their process exits too.
            store = works.Store()
            iso = str(Path(args.iso).resolve())
            existing = next((w for w in store.list() if any(r.get("iso_path") == iso for r in w["discs"])), None)
            if existing:
                args.work = existing["id"]
            else:
                made = store.new(Path(args.iso).stem, getattr(args, "media", "dvd"), source_design_missing=True)
                args.work = made["id"]
                store.patch(args.work, {"note": "刻录记录；未提供设计稿 / Burn record; no source design supplied"})
                result = dict(result, source_design_missing=True)
        _completed(args, args.iso, kind="burn", drive=args.drive,
                   speed=result.get("selected_speed_x", args.speed),
                   result=result.get("result", "unknown"), report=result,
                   preview_available=not measurement and not result.get("source_design_missing", False),
                   job_id=os.environ.get("DISCPROBE_JOB"),
                   **({"measurement": True} if measurement else {}),
                   actual_speed_x=result.get("actual_speed_x"), verification=result.get("verification"))
