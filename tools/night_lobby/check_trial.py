"""Check only base with the existing export functions and recorded encoding."""
import ast
import io
import json
from pathlib import Path
import shutil
import sys
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
TRIAL = Path('F:/dp-archive/tmp/lobbypool/trial')
HOME = ROOT / 'discprobe/web/home'
source = ROOT / 'tools/night_b_export.py'
tree = ast.parse(source.read_text(encoding='utf-8'))
names = {'kind', 'encode', 'match_lossy', 'paper_stats', 'night_b_matches', 'diff'}
nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
assert {n.name for n in nodes} == names
recipes = json.loads((ROOT / 'tools/night_b_manifest.json').read_text(encoding='utf-8'))['pictures']
ns = dict(ast=ast, io=io, np=np, Image=Image, Path=Path, ROOT=ROOT, HOME=HOME,
          RECIPES=recipes, _LOSSY={})
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), ns)
meta = json.loads((HOME / 'lobby/lobby.json').read_text(encoding='utf-8'))
box = next(l['box'] for l in meta['layers'] if l['name'] == 'base')
paper = Image.open(TRIAL / 'F_lobby_a/desk_base_paper.png').convert('RGB').crop(box)
how = ns['kind'](HOME / 'lobby/base_dark.webp')
if how == 'lossy':
    how = ns['match_lossy'](paper, HOME / 'lobby/base_paper.webp')
paper_encoded = ns['encode'](paper, how)
actual = Image.open(io.BytesIO(paper_encoded)).convert('RGBA')
expected = Image.open(HOME / 'lobby/base_paper.webp').convert('RGBA')
stats = ns['paper_stats'](actual, expected)
accepted = ns['night_b_matches'](stats)
row = dict(file='lobby/base_dark.webp', job='F_lobby_a', layers=['base'], box=box,
           encoding=how, paper_gate='night-b', paper_stats=stats, paper_accepted=accepted,
           paper_exact=np.array_equal(np.asarray(actual), np.asarray(expected)),
           paper_changed_pixels=int(np.any(np.asarray(actual) != np.asarray(expected), axis=2).sum()),
           thresholds=dict(rgb_mean=.3, alpha_mean=.02, over8_percent=.1),
           functions_from='tools/night_b_export.py (AST extracted, unchanged)',
           writes='trial candidates only; no committed image, paper or manifest writes')
if '--paper-only' in sys.argv:
    report_name = 'paper-check-preview.json'
else:
    dark = Image.open(TRIAL / 'F_lobby_a/desk_base_dark.png').convert('RGB').crop(box)
    (TRIAL / 'base_trial_dark.webp').write_bytes(ns['encode'](dark, how))
    shutil.copyfile(TRIAL / 'F_lobby_a/desk_base_dark.png', TRIAL / 'base_trial_dark.png')
    report_name = 'paper-check.json'
(TRIAL / report_name).write_text(json.dumps([row], indent=2) + '\n', encoding='utf-8')
print(json.dumps(row, indent=2))
raise SystemExit(0 if accepted else 2)
