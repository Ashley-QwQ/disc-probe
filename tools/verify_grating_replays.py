"""Compare an archived role card against its rebuilt labels, textures and full disc image."""
import argparse
import hashlib
import json
from pathlib import Path

from audit_colour_solver import hash_iso


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original_iso',type=Path)
    parser.add_argument('original_labels',type=Path)
    parser.add_argument('original_textures',type=Path)
    parser.add_argument('rebuilt_iso',type=Path)
    parser.add_argument('--remove-rebuilt-iso',action='store_true')
    args = parser.parse_args()
    rebuilt_labels = args.rebuilt_iso.with_suffix('.labels.npy')
    rebuilt_textures = rebuilt_labels.with_suffix('.textures.json')
    labels = [digest(path) for path in (args.original_labels,rebuilt_labels)]
    specs = [json.loads(path.read_text(encoding='utf-8-sig'))['textures']
             for path in (args.original_textures,rebuilt_textures)]
    iso = [hash_iso(path) for path in (args.original_iso,args.rebuilt_iso)]
    result = dict(labels=labels, same_labels=labels[0] == labels[1], materials=len(specs[0]),
                  same_textures=specs[0] == specs[1], iso=iso,
                  same_iso_without_dates=iso[0]['without_dates'] == iso[1]['without_dates'])
    print(json.dumps(result,indent=2))
    if not all(result[k] for k in ('same_labels','same_textures','same_iso_without_dates')):
        raise SystemExit(1)
    if args.remove_rebuilt_iso:
        if args.rebuilt_iso.resolve() == args.original_iso.resolve():
            raise ValueError('Rebuilt ISO must differ from the original path')
        args.rebuilt_iso.unlink()


if __name__ == '__main__':
    main()
