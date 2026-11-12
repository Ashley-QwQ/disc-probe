"""Refresh build-only UTF-8 flags and provenance after the extracted gate.

Refuses any runtime source change. This avoids repeating numerical tests for a
build-command encoding option while keeping packaged source reviewable.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from slim_support import ROOT, ARTIFACTS, low_priority, walk
low_priority()

gate = json.loads((ARTIFACTS / 'extracted.json').read_text(encoding='utf-8'))
if gate['selftest']['returncode'] != 0:
    raise SystemExit('extracted selftest did not pass; no zip')
spec = importlib.util.spec_from_file_location('_slim_builder', ROOT / 'tools/build_winpack.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
out = Path('D:/disc-probe-dist/slim-20261111')
changes = {}
for kind in ('core', 'full-win64'):
    root = out / f'disc-probe-slim-20261111-{kind}'
    before = {str(p.relative_to(root)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
              for folder in ('discprobe', 'tools') for p in walk(root / folder)}
    builder.copy_source(SimpleNamespace(worktree=True, ref='HEAD'), str(root))
    after = {str(p.relative_to(root)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
             for folder in ('discprobe', 'tools') for p in walk(root / folder)}
    changed = [p for p in set(before) | set(after) if before.get(p) != after.get(p)]
    if set(changed) - {'tools/build_winpack.py'}:
        raise RuntimeError('runtime source changed after gate: ' + repr(changed))
    changes[kind] = changed
    if kind == 'core':
        package = json.loads((root / 'package.json').read_text(encoding='utf-8'))
        package['worktree'] = True
        (root / 'package.json').write_text(json.dumps(package, indent=1), encoding='utf-8')
    (root / 'source-sha256.json').write_text(json.dumps(after, indent=2, ensure_ascii=False), encoding='utf-8')
    builder.pack(str(root), str(out), '6fba5ee + uncommitted working tree')
(ARTIFACTS / 'repack.json').write_text(json.dumps(dict(changes=changes, reason='explicit -X utf8 for isolated build checks; core metadata identifies uncommitted worktree', extracted_gate=gate['selftest']),
                                                               indent=2, ensure_ascii=False), encoding='utf-8')
