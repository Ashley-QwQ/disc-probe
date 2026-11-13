"""CLI adapter kept separate from the shared command module."""
import argparse
import json
from pathlib import Path
import sys

from . import i18n, works


def file_bytes(path, limit):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise works.WorkError("invalid request size", 413)
    return raw


def add_parser(sub):
    parser = sub.add_parser("works", help="keep past works on this computer")
    parser.add_argument("--json", action="store_true", help="print works information as JSON")
    commands = parser.add_subparsers(dest="works_command", required=True, metavar="<operation>")
    definitions = (
        ("list", "list saved works"), ("show", "show a work and its recent history"),
        ("new", "create a saved work"), ("save", "save a portable design to a work"),
        ("rename", "rename a saved work"), ("duplicate", "copy a saved work"),
        ("delete", "move a work to the trash"), ("restore", "restore a work from the trash"),
        ("export", "export a work with its assets and records"),
        ("import", "import a discdesign file or work archive"),
        ("mark", "mark a work as done or failed"),
    )
    children = {}
    for name, help_text in definitions:
        child = commands.add_parser(name, help=i18n.tr(help_text), description=i18n.tr(help_text))
        child.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                           help="print works information as JSON")
        child.set_defaults(func=run)
        children[name] = child
    for name in ("show", "save", "rename", "duplicate", "delete", "restore", "export", "mark"):
        children[name].add_argument("id", help="saved work id")
    for name in ("new", "rename"):
        children[name].add_argument("name", help="work name, including Chinese")
    children["duplicate"].add_argument("name", nargs="?", help="name of the copy")
    children["list"].add_argument("--status", choices=works.STATUSES, help="filter by work status")
    children["list"].add_argument("--media", choices=("dvd", "cd", "bd"), help="filter by disc kind")
    children["list"].add_argument("--sort", choices=("time", "name"), default="time", help="sort works by time or name")
    children["new"].add_argument("--media", choices=("dvd", "cd", "bd"), default="dvd", help="disc kind for a new work")
    children["new"].add_argument("--from", dest="source", help="portable design to start from")
    for name in ("save", "import"):
        children[name].add_argument("file", help="design or archive file")
    children["save"].add_argument("--thumb", help="512 x 512 PNG thumbnail")
    children["export"].add_argument("out", help="destination ZIP file")
    children["mark"].add_argument("status", choices=("done", "failed"), help="confirmed work result")
    children["mark"].add_argument("--note", default="", help="result note; required for failed works")
    for child in children.values():
        i18n.localize_parser(child)
    return parser


def run(args):
    store, op = works.Store(), args.works_command
    try:
        if op == "list":
            result = store.list(args.status, args.media, args.sort)
        elif op == "show":
            result = store.show(args.id, opened=True)
        elif op == "new":
            raw = file_bytes(args.source, works.DESIGN_LIMIT) if args.source else None
            result = store.new(args.name, args.media, raw, str(Path(args.source).resolve()) if args.source else None)
        elif op == "save":
            result = store.save(args.id, file_bytes(args.file, works.DESIGN_LIMIT),
                                file_bytes(args.thumb, works.THUMB_LIMIT) if args.thumb else None)
        elif op == "rename":
            result = store.patch(args.id, dict(name=args.name))
        elif op == "duplicate":
            result = store.duplicate(args.id, args.name)
        elif op == "delete":
            result = store.delete(args.id)
        elif op == "restore":
            result = store.restore(args.id)
        elif op == "export":
            works.atomic(Path(args.out), store.export(args.id))
            result = dict(id=args.id, path=str(Path(args.out).resolve()))
        elif op == "import":
            result = store.import_bytes(file_bytes(args.file, works.ARCHIVE_LIMIT), str(Path(args.file).resolve()))
        else:
            result = store.patch(args.id, dict(status=args.status, note=args.note))
    except (works.WorkError, OSError) as exc:
        message = i18n.tr(str(exc))
        print(json.dumps(dict(error=message), ensure_ascii=False) if args.json else message, file=sys.stderr)
        raise SystemExit(1) from None
    if args.json:
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    elif op == "show":
        labels = (("id", "Work id"), ("name", "Work name"), ("created_at", "Created at"),
                  ("updated_at", "Updated at"), ("opened_at", "Last opened at"),
                  ("media", "Disc kind"), ("disc_type", "Recordable disc type"),
                  ("batch", "Disc batch"), ("geo_run", "Geometry run"), ("photo_l", "Photo L source"),
                  ("cell_um", "Cell size in micrometres"), ("status", "Work status"),
                  ("note", "Work note"), ("source_file", "Original design path"),
                  ("discs", "Disc records"), ("history", "Recent work history"))
        for key, label in labels:
            value = result.get(key)
            text = json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else str(value) if value is not None else "—"
            print(i18n.tr(label) + ": " + text)
    elif isinstance(result, list):
        for work in result:
            print(f"{work['id']}  {work['name']}  {work['media']}  {work['status']}  {work['updated_at']}")
        if not result:
            print(i18n.tr("No saved works."))
    elif "name" in result:
        print(f"{result['id']}  {result['name']}  {result['status']}")
    else:
        print(result["path"])
