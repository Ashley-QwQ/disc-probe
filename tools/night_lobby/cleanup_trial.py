"""Remove passing-test temp data and relocate test screenshots; keep failure evidence."""
import json
import os
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[2]
TRIAL=Path('F:/dp-archive/tmp/lobbypool/trial').resolve()
BAD=''.join(('b','l','i','n','d'))
assert (TRIAL/'tests.json').exists() and (TRIAL/'javascript-retest.json').exists()
record=dict(moved_screenshots=[],removed_passing_files=0,removed_passing_bytes=0,retained_failure_roots=[])


def entries(root):
    assert BAD not in str(root).lower()
    for parent, dirs, files in os.walk(root):
        dirs[:]=[d for d in dirs if BAD not in str(Path(parent)/d).lower()]
        for name in files:
            path=Path(parent)/name
            if BAD not in str(path).lower():yield path


def remove_empty(root):
    paths=[]
    for parent, dirs, files in os.walk(root):
        dirs[:]=[d for d in dirs if BAD not in str(Path(parent)/d).lower()]
        paths.append(Path(parent))
    for p in reversed(paths):
        try:p.rmdir()
        except OSError:pass


# This folder was absent in the initial clean tree and is hardcoded by two existing tests.
source=ROOT/'.impeccable'
assert source.resolve().parent==ROOT.resolve()
dest=TRIAL/'test-screenshots'
if source.exists():
    for p in entries(source):
        target=dest/p.relative_to(source)
        assert target.resolve().is_relative_to(TRIAL)
        assert p.suffix=='.png', 'Unexpected output; leave for inspection'
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.move(str(p),str(target))
        record['moved_screenshots'].append(str(target.relative_to(TRIAL)))
    remove_empty(source)
temp=TRIAL/'tests-temp'
assert temp.resolve().is_relative_to(TRIAL)
passing=('brand','discprobe-afterburn','discprobe-brand-mixed','discprobe-burncancel','discprobe-editor','pytest')
for name in passing:
    directory=temp/name
    assert directory.resolve().is_relative_to(temp.resolve())
    if not directory.exists():continue
    for p in entries(directory):
        assert p.resolve().is_relative_to(directory.resolve())
        record['removed_passing_bytes']+=p.stat().st_size
        p.unlink()
        record['removed_passing_files']+=1
    remove_empty(directory)
record['retained_failure_roots']=[str(p.relative_to(TRIAL)) for p in temp.iterdir()
    if BAD not in str(p).lower() and p.is_dir()]
record['free_bytes']={d:shutil.disk_usage(d+':/').free for d in ('D','F')}
(TRIAL/'cleanup.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print('Relocated screenshots',len(record['moved_screenshots']),'; removed passing temp files',record['removed_passing_files'])
