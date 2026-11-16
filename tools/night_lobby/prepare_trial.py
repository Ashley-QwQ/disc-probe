"""Prepare the bounded lobby base trial without traversing excluded paths."""
from __future__ import annotations

import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
TRIAL = Path(os.environ.get('LOBBY_TRIAL', 'F:/dp-archive/tmp/lobbypool/trial'))
SOURCE = Path('F:/dp-archive/tmp/lobbypool/x79stage/stage')
BLENDER = Path('F:/dp-archive/tools/blender-5.2.2-windows-x64/blender.exe')
EXCLUDED = ''.join(('b', 'l', 'i', 'n', 'd'))


def safe(path):
    p = Path(path)
    if EXCLUDED in str(p).lower():
        raise ValueError('Excluded path')
    return p


def sha(path):
    return hashlib.sha256(safe(path).read_bytes()).hexdigest()


def write_json(path, data):
    safe(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def protected():
    paths = []
    for parent, dirs, files in os.walk(ROOT / 'discprobe/web/home'):
        dirs[:] = [d for d in dirs if EXCLUDED not in str(Path(parent) / d).lower()]
        for name in files:
            p = Path(parent) / name
            if EXCLUDED in str(p).lower():
                continue
            if '_paper.' in name or p.parent.name == 'lobby':
                paths.append(p)
    paths += [ROOT / 'tools/night_b_manifest.json', ROOT / 'tools/night_b_export_report.json']
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(set(paths))}


def main():
    TRIAL.mkdir(parents=True, exist_ok=True)
    stage = TRIAL / 'stage'
    stage.mkdir(exist_ok=True)
    free = {drive: shutil.disk_usage(drive + ':/').free for drive in ('D', 'F')}
    if min(free.values()) < 5_000_000_000:
        raise SystemExit('Disk below 5 GB')
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    assert branch == 'web/lobby-pool-20261116', branch
    comparison = {}
    for name in ('render_round5_nightb.py', 'render_fax_nightb.py', 'night_b_palette.py', 'glow_review.json'):
        source = safe(SOURCE / name)
        shutil.copyfile(source, stage / name)
        local = safe(Path('D:/disc-probe/art/desk/night-b') / name)
        entry = {'source': str(source), 'sha256': sha(source), 'bytes': source.stat().st_size,
                 'local_exists': local.exists()}
        if local.exists():
            entry['local_sha256'] = sha(local)
            entry['identical'] = sha(local) == sha(source)
            if not entry['identical']:
                (TRIAL / (name + '.local.diff')).write_text(''.join(difflib.unified_diff(
                    local.read_text(encoding='utf-8').splitlines(True),
                    source.read_text(encoding='utf-8').splitlines(True),
                    fromfile='local', tofile='x79-provided')), encoding='utf-8')
        comparison[name] = entry
    write_json(TRIAL / 'preflight.json', {'branch': branch, 'free_bytes': free,
               'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'blender': str(BLENDER), 'inputs': comparison, 'protected': protected()})
    shutil.copyfile(ROOT / 'discprobe/web/home/lobby/base_dark.webp', TRIAL / 'base_old_dark.webp')
    # Exact, read-only remote paths only. Bytes travel through a binary pipe, never PowerShell text.
    scene = stage / 'room_fax.blend'
    remote = '/home/knappy/nightb/stage/room_fax.blend'
    size = int(subprocess.check_output(['ssh', '-o', 'BatchMode=yes', 'x79', 'stat -c %s ' + remote], timeout=30))
    if not scene.exists():
        with (TRIAL / 'scene-copy.log').open('wb') as log:
            source_proc = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', 'x79',
                'tar cf - -C /home/knappy/nightb/stage room_fax.blend'], stdout=subprocess.PIPE, stderr=log)
            target_proc = subprocess.Popen(['tar', 'xf', '-', '-C', str(stage)], stdin=source_proc.stdout, stdout=log, stderr=log)
            source_proc.stdout.close()
            assert target_proc.wait() == 0
            assert source_proc.wait() == 0
    assert scene.stat().st_size == size
    remote_sha = subprocess.check_output(['ssh', '-o', 'BatchMode=yes', 'x79', 'sha256sum ' + remote], timeout=30).decode('ascii').split()[0]
    assert sha(scene) == remote_sha
    write_json(TRIAL / 'scene-copy.json', {'remote': 'x79:' + remote, 'remote_bytes': size,
               'local_bytes': scene.stat().st_size, 'sha256': sha(scene), 'sha256_matches_remote': True})
    print(json.dumps({'free_bytes': free, 'comparison': comparison, 'scene_bytes': size}, indent=2))


if __name__ == '__main__':
    main()
