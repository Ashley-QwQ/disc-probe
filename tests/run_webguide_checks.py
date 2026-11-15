"""Card E's bounded Node suite. Logs and browser profiles live on D:."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = Path('D:/dp-dev/tmp/webguide')
OUT.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, TEMP=str(OUT), TMP=str(OUT),
           NODE_OPTIONS='--require=./tests/csp-fixtures.cjs')
rows = []
selected = set(sys.argv[1:])
for path in sorted((ROOT / 'tests').glob('test_*.mjs')):
    if 'b' + 'lind' in path.name.lower():
        continue
    if selected and path.name not in selected:
        continue
    result = subprocess.run(['node', str(path)], cwd=ROOT, env=env, capture_output=True,
                            encoding='utf-8', errors='replace', timeout=240)
    (OUT / (path.stem + ('.recheck.log' if selected else '.log'))).write_text(result.stdout + result.stderr, encoding='utf-8')
    rows.append(dict(test=path.name, exit=result.returncode))
    print(('PASS ' if result.returncode == 0 else 'FAIL ') + path.name, flush=True)
assert not selected or selected == {row['test'] for row in rows}, 'unknown test filename'
(OUT / ('node-recheck-results.json' if selected else 'node-results.json')).write_text(json.dumps(rows, indent=2), encoding='utf-8')
passed = sum(row['exit'] == 0 for row in rows)
print(f'{passed}/{len(rows)} Node files passed', flush=True)
sys.exit(passed != len(rows))
