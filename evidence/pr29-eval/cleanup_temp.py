"""Clean only this card's successful temporary fixtures; keep logs and screenshots."""
import json
import os
from pathlib import Path
import shutil

ROOT = Path('F:/dp-dev-tmp/pr29eval').resolve()
OUT = Path(__file__).resolve().parent
BLOCKED = ''.join(('b','l','i','n','d'))
KEEP = {'.log','.txt','.png','.json'}


def main():
    assert str(ROOT).lower().replace('\\','/') == 'f:/dp-dev-tmp/pr29eval'
    counts = dict(removed_files=0, removed_logical_bytes=0, retained_files=0, failures=[])
    before = {d:shutil.disk_usage(d).free for d in ('D:/','F:/')}

    def prune(folder, all_files=False):
        assert folder.resolve().is_relative_to(ROOT)
        with os.scandir(folder) as entries:
            children = [Path(e.path) for e in entries if BLOCKED not in e.path.lower()]
        for path in children:
            try:
                if path.is_symlink():
                    continue
                if path.is_dir():
                    prune(path, all_files or path.name.lower().startswith('profile') or path.name.lower()=='edge')
                    if not any(path.iterdir()):
                        path.rmdir()
                elif all_files or path.suffix.lower() not in KEEP:
                    size = path.stat().st_size
                    path.unlink()
                    counts['removed_files'] += 1
                    counts['removed_logical_bytes'] += size
                else:
                    counts['retained_files'] += 1
            except OSError as e:
                counts['failures'].append(dict(path=str(path),error=str(e)))

    for name in ('checks','pilot','final_pilot'):
        folder = ROOT/name
        if folder.is_dir():
            prune(folder, name!='checks')
            if not any(folder.iterdir()):
                folder.rmdir()
    counts.update(before_free_bytes=before, after_free_bytes={d:shutil.disk_usage(d).free for d in before},
                  note='Removed bytes are logical sizes; sparse fixtures were not all physically allocated. Only this card F: temp was touched.')
    (OUT/'temp_cleanup.json').write_text(json.dumps(counts,indent=2),encoding='utf-8')
    print(json.dumps(counts))


if __name__=='__main__':
    main()
