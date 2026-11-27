"""Write a pruned inventory of recorded input files, without opening images."""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from slim_support import ARTIFACTS, walk, low_priority


def main():
    low_priority()
    ARTIFACTS.mkdir(exist_ok=True)
    roots = [Path('D:/disc-probe/results'), Path('D:/disc-probe/evidence')]
    datasets, photos, json_files = [], [], []
    for root in roots:
        for path in walk(root):
            if path.name == 'targets.csv':
                summary = path.with_name('summary.json')
                if summary.is_file():
                    try:
                        fit = json.loads(summary.read_text(encoding='utf-8')).get('fit', {})
                        datasets.append(dict(path=str(path.parent), media=fit.get('media', 'dvd'),
                                             keys=sorted(fit), targets_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
                    except (ValueError, OSError) as e:
                        datasets.append(dict(path=str(path.parent), error=str(e)))
            if path.suffix.lower() in ('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp'):
                photos.append(dict(path=str(path), bytes=path.stat().st_size))
            if path.suffix.lower() == '.json':
                json_files.append(str(path))
    report = dict(roots=list(map(str, roots)), datasets=datasets, photos=photos, json_files=json_files)
    (ARTIFACTS / 'inventory.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(dict(datasets=len(datasets), photos=len(photos), json_files=len(json_files)), ensure_ascii=False))
    print('\n'.join(d['path'] for d in datasets))


if __name__ == '__main__':
    main()
