"""Reversible disc library operations shared by the CLI and the web UI."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil

from . import guide, measurement_jobs, webui_catalog, works


TRASH_ID = re.compile(r'\d{8}T\d{12}Z-[0-9a-f]{8}', re.ASCII)


def _safe(base, relative):
    path = base / relative
    if ('blind' in path.as_posix().casefold() or Path(relative).anchor or
            '..' in Path(relative).parts or not path.is_relative_to(base)):
        raise works.WorkError('unsafe library path')
    for part in (path, *path.parents):
        if part == base.parent:
            break
        if works.redirected(part):
            raise works.WorkError('unsafe library path')
    return path


def _tree(path):
    """Check a directory before relocating or removing it."""
    if not path.is_dir():
        return
    for folder, dirs, files in os.walk(path):
        for name in dirs + files:
            _safe(path, (Path(folder) / name).relative_to(path))


class Library:
    def __init__(self, root, out, store=None):
        self.root, self.out = Path(root).resolve(), Path(out).resolve()
        self.works = works.Store(self.out) if store is None else store
        self.trash = self.out / '.trash'
        self.metadata = self.root / 'catalogue.json'

    def _metadata(self):
        _safe(self.root, 'catalogue.json')
        return webui_catalog.read_metadata(self.metadata)

    def _archives(self):
        folder = _safe(self.out, '.trash')
        if folder.is_dir():
            for entry in sorted(folder.iterdir()):
                if TRASH_ID.fullmatch(entry.name):
                    yield _safe(folder, entry.name)

    def _recover(self):
        for folder in self._archives():
            marker = _safe(folder, 'pending')
            if not marker.is_file():
                continue
            manifest = json.loads(_safe(folder, 'batch.json').read_bytes())
            restoring = marker.read_text(encoding='ascii') == 'restore'
            self._transition(folder, manifest, restoring=restoring, recovering=True)

    def rows(self, *, progress=None):
        with self.works._locked():
            self._recover()
            return webui_catalog.catalogue(self.root, self.out, occupied=measurement_jobs.occupied(self.out),
                                           progress=progress)

    def trashed(self):
        with self.works._locked():
            self._recover()
            entries = []
            for folder in self._archives():
                if (_safe(folder, 'deleted')).is_file():
                    manifest = json.loads(_safe(folder, 'batch.json').read_bytes())
                    entries.append(dict(trash_id=folder.name, id=manifest['id'], name=manifest['name']))
            return entries

    def _plan(self, ident, *, deleting=False):
        inventory = {}
        occupied = measurement_jobs.occupied(self.out)
        groups = webui_catalog.catalogue(self.root, self.out, inventory=inventory, occupied=occupied)
        entry = next((row for rows in groups.values() for row in rows if row['id'] == ident), None)
        if not entry:
            raise works.WorkError('disc batch not found', 404)
        references = inventory[ident]
        if deleting and (entry['s'] == 'measuring' or any(path and str(self.root / path) in occupied for path in references)):
            raise measurement_jobs.MeasurementRunning()
        shared = set().union(*(paths for key, paths in inventory.items() if key != ident))
        retained = sorted(references & shared)
        files = sorted(name for name in references - shared if _safe(self.root, name).exists())
        dependencies = []
        for folder in self.works.root.iterdir():
            if not works.ID.fullmatch(folder.name):
                continue
            folder = self.works._safe(folder)
            if not (folder / 'work.json').is_file():
                continue
            work = self.works._read(folder)
            batch = work.get('batch')
            linked_id = batch.get('id') if isinstance(batch, dict) else batch
            geo_refs = [work.get('geo_run'), *(d.get('geo_run') for d in work['discs'] if isinstance(d, dict))]
            for value in geo_refs:
                if isinstance(value, str) and not Path(value).is_absolute():
                    # Work metadata paths are relative to the works data root.
                    value = str(self.works.root.parent / value)
                relative = webui_catalog._relative(self.root, value)
                if relative in references or relative and Path(relative).parent.as_posix() in references:
                    break
            else:
                if linked_id != ident:
                    continue
            dependencies.append(dict(id=work['id'], name=work['name']))
        plan = dict(id=ident, name=entry['name'], files=files, retained=retained,
                    works=sorted(dependencies, key=lambda w: w['id']))
        plan['revision'] = hashlib.sha256(works.encoded(plan)).hexdigest()
        return plan

    def preview(self, ident):
        with self.works._locked():
            self._recover()
            return self._plan(ident)

    def _pairs(self, folder, manifest):
        for index, name in enumerate(manifest['files']):
            yield _safe(self.root, name), _safe(folder, f'files/{index}')
        for ident in manifest['moved_works']:
            yield self.works._safe(self.works.root / works.valid_id(ident)), _safe(folder, f'works/{ident}')

    def _transition(self, folder, manifest, *, restoring=False, recovering=False):
        before, after = manifest['metadata'], manifest['replacement']
        if restoring:
            before, after = after, before
        table = self._metadata()
        ident = manifest['id']
        if table.get(ident) != before and not (recovering and table.get(ident) == after):
            raise works.WorkError('disc batch metadata changed', 409)
        pairs = list(self._pairs(folder, manifest))
        if restoring:
            pairs = [(destination, source) for source, destination in pairs]
        remaining = []
        for source, destination in pairs:
            if recovering and not source.exists() and destination.exists():
                continue
            if not source.exists() or destination.exists():
                raise works.WorkError('a library file is missing or its destination is occupied', 409)
            _tree(source)
            remaining.append((source, destination))
        marker = _safe(folder, 'pending')
        if not recovering:
            works.atomic(marker, b'restore' if restoring else b'delete')
        moved = []
        try:
            for source, destination in remaining:
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.rename(source, destination)
                moved.append((source, destination))
            if table.get(ident) != after:
                if after is None:
                    table.pop(ident, None)
                else:
                    table[ident] = after
                works.atomic(self.metadata, works.encoded(table))
        except OSError:
            if not recovering:
                for source, destination in reversed(moved):
                    os.rename(destination, source)
                marker.unlink()
            raise
        deleted = _safe(folder, 'deleted')
        if restoring:
            deleted.unlink(missing_ok=True)
        else:
            works.atomic(deleted, b'')
        marker.unlink()

    def delete(self, ident, *, with_works=None, permanent=False, revision=None):
        with self.works._locked():
            self._recover()
            plan = self._plan(ident, deleting=True)
            if revision is not None and revision != plan['revision']:
                raise works.WorkError('disc batch changed; review the files before deleting', 409)
            if plan['works'] and with_works is None:
                raise works.WorkError('choose whether to keep or move dependent works', 409)
            old = self._metadata().get(ident)
            # A file containing several presets belongs to all of them. Keep
            # that file in place and hide only this batch's row.
            hidden = dict(hidden_presets=plan['retained']) if ident.startswith('preset:') and plan['retained'] else None
            key = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ-') + secrets.token_hex(4)
            folder = _safe(self.out, '.trash/' + key)
            folder.mkdir(parents=True)
            manifest = dict(plan, metadata=old, replacement=hidden,
                            moved_works=[w['id'] for w in plan['works']] if with_works else [])
            works.atomic(folder / 'batch.json', works.encoded(manifest))
            self._transition(folder, manifest)
            if permanent:
                _tree(folder)
                shutil.rmtree(folder)
            return dict(plan, trash_id=None if permanent else key, permanent=permanent)

    def restore(self, key):
        if not isinstance(key, str) or not TRASH_ID.fullmatch(key):
            raise works.WorkError('invalid library trash id')
        with self.works._locked():
            self._recover()
            folder = _safe(self.out, '.trash/' + key)
            manifest = guide._load(str(_safe(folder, 'batch.json')))
            if not manifest or not _safe(folder, 'deleted').is_file():
                raise works.WorkError('disc batch is not in the trash', 404)
            self._transition(folder, manifest, restoring=True)
            return dict(id=manifest['id'], restored=True)


def add_parser(sub):
    import argparse
    import sys
    from . import i18n

    parser = sub.add_parser('library', help='manage saved disc batches')
    parser.add_argument('--json', action='store_true', help='print library information as JSON')
    commands = parser.add_subparsers(dest='library_command', required=True)

    def run(args):
        root = Path.cwd()
        store = Library(root, root / 'results')
        try:
            if args.library_command == 'list':
                result = store.rows()
            elif args.library_command == 'trash':
                result = store.trashed()
            elif args.library_command == 'show':
                result = store.preview(args.id)
            elif args.library_command == 'delete':
                result = store.delete(args.id, with_works=args.with_works, permanent=args.permanent)
            else:
                result = store.restore(args.id)
        except (ValueError, OSError) as exc:
            message = i18n.tr(str(exc))
            print(json.dumps(dict(error=message), ensure_ascii=False) if args.json else message, file=sys.stderr)
            raise SystemExit(1) from None
        print(json.dumps(result, ensure_ascii=False, indent=None if args.json else 2))

    for command, help_text in (
        ('list', 'list saved disc batches'), ('show', 'list the files and works linked to a batch'),
        ('delete', 'move a disc batch to the trash'), ('restore', 'restore a disc batch from the trash'),
        ('trash', 'list batches in the trash'),
    ):
        child = commands.add_parser(command, help=i18n.tr(help_text), description=i18n.tr(help_text))
        child.add_argument('--json', action='store_true', default=argparse.SUPPRESS,
                           help='print library information as JSON')
        if command not in ('list', 'trash'):
            child.add_argument('id', help='trash id' if command == 'restore' else 'disc batch id')
        if command == 'delete':
            choices = child.add_mutually_exclusive_group()
            choices.add_argument('--with-works', action='store_const', const=True,
                                 help='move dependent works with the batch')
            choices.add_argument('--keep-works', dest='with_works', action='store_const', const=False,
                                 help='leave dependent works in the works library')
            child.add_argument('--permanent', action='store_true', help='remove these files permanently')
        child.set_defaults(func=run)
        i18n.localize_parser(child)
