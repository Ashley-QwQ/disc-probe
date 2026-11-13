"""Completion hooks for image and burn commands; no drive access here."""
from . import i18n, works


def add_options(sub):
    for name in ("image", "burn", "calibrate"):
        sub.choices[name].add_argument("--work", help="append successful image or burn records to this work")
    # calibrate forwards these to its burn child, alongside --work.
    sub.choices["calibrate"].add_argument("--disc-code", dest="disc_id_code", help="disc code for the work burn record")


def check_work(args):
    ident = getattr(args, "work", None)
    if ident:
        try:
            works.Store().show(ident)
        except (works.WorkError, OSError) as exc:
            raise SystemExit(i18n.tr(str(exc))) from None


def _completed(args, iso, **fields):
    if getattr(args, "work", None):
        try:
            works.Store().link(args.work, iso, disc_code=getattr(args, "disc_id_code", None), **fields)
        except (works.WorkError, OSError) as exc:
            raise SystemExit(i18n.tr("work record could not be saved: {a}").format(a=str(exc))) from None


def image_completed(args):
    _completed(args, args.output, kind="iso")


def burn_completed(args, result):
    if result.get("result") == "completed":
        _completed(args, args.iso, kind="burn", drive=args.drive,
                   speed=result.get("selected_speed_x", args.speed),
                   actual_speed_x=result.get("actual_speed_x"), verification=result.get("verification"))
