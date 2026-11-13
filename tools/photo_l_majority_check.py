"""Offline fixed-pose checks and a prespecified stratified held-out sample.

Run --prepare before --run. Sources and selection are frozen in plan.json;
raw diagnostics/images remain in scratch. Each worker uses one compute thread;
optional disjoint partitions permit at most two worker processes.
"""
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '1'
os.environ['DISCPROBE_WORKERS'] = '1'

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

OUT = Path('C:/disc-probe-scratch/photo-l/majority')
BASE = Path('C:/disc-probe-scratch/pcal-blur')
ROOT = Path(__file__).resolve().parents[1]
OTHER = Path('D:/disc-probe/.claude/worktrees/pcal-lottery')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    return json.loads(Path(path).read_bytes())


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def source(path):
    return dict(path=str(path), sha256=sha(path.read_bytes()))


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / 'plan.json').exists():
        raise ValueError('plan already exists; retain the prespecified selection')
    strata, count = {}, 0
    for i in range(1025):
        path = BASE / 'heldout' / f'case_{i:05d}.json'
        if not path.is_file():
            continue
        case = load(path)
        count += 1
        if case.get('negative') is not None or case.get('truth') is None:
            continue
        key = (case['family'], case['condition'])
        if key not in strata:
            strata[key] = source(path)
    plan = dict(rule='complete case ids 00000..01024; smallest id per positive family/condition; no replacement',
                rate_rotations_deg=[0, 120, 240], counterexample_rotations_deg=[0, 90, 45, 180],
                wrong_threshold_mm=.326, available_prefix_cases=count,
                rate_sources=[strata[k] for k in sorted(strata)],
                counterexample_sources=[source(Path('C:/disc-probe-scratch/pcal-lottery/heldout/case_00703.json')),
                                        source(BASE / 'heldout/case_00929.json')],
                old_poses=source(Path('C:/disc-probe-scratch/photo-l/poses/summary.json')),
                note='Stratified sample, not a full-set population rate; each triple shares truth/camera/seed. '
                     'A failed render-hash check is NOT_RUN, never replaced. Original reads are saved v1 diagnostics.')
    save(OUT / 'plan.json', plan)
    print('prepared', len(strata), 'rate triples', flush=True)


def setup():
    # Refuse excluded paths before any file open or directory traversal.
    excluded = ''.join(map(chr, (98, 108, 105, 110, 100)))
    def guard(event, args):
        if event in ('open', 'os.listdir', 'os.scandir') and args and isinstance(args[0], (str, bytes)):
            if excluded in os.fsdecode(args[0]).lower():
                raise RuntimeError('excluded path')
    sys.addaudithook(guard)
    import discprobe
    from discprobe import pcal
    discprobe.__path__.append(str(OTHER / 'discprobe'))
    spec = importlib.util.spec_from_file_location('majority_render_study', OTHER / 'tools/pcal_blur_study.py')
    study = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(OTHER))
    spec.loader.exec_module(study)
    import cv2
    cv2.setNumThreads(1)
    assert Path(pcal.__file__).read_bytes() == (OTHER / 'discprobe/pcal.py').read_bytes()
    return pcal, study


def checked(item):
    raw = Path(item['path']).read_bytes()
    if sha(raw) != item['sha256']:
        raise ValueError('source changed: ' + item['path'])
    return json.loads(raw)


def run(partition=None):
    from discprobe import photo
    from PIL import Image
    import numpy as np
    plan = load(OUT / 'plan.json')
    pcal, study = setup()
    old = checked(plan['old_poses'])
    reader_sha = sha(Path(pcal.__file__).read_bytes())
    if old['reader_source_sha256'] != reader_sha:
        raise ValueError('saved +90 reads used another v1 source')

    def evaluate(item, deltas, tag, previous=None):
        case = checked(item)
        if previous is not None and (previous['source_sha256'] != item['sha256']
                or previous['original_pixel_sha256'] != case['image_sha256']
                or previous['status'] != 'RUN'):
            raise ValueError('saved +90 pose does not match this source')
        target = OUT / (tag + '.json')
        try:
            cached = load(target) if target.is_file() else {}
        except ValueError:
            cached = {}  # A stopped worker may have left its last checkpoint incomplete.
        if (cached.get('source') != item or cached.get('rotations_deg') != deltas
                or cached.get('reader_source_sha256') != reader_sha
                or cached.get('plan_sha256') != sha((OUT / 'plan.json').read_bytes())):
            cached = {}
        cached_photos = {d: p for d, p in zip(deltas, cached.get('photos', []))}
        config = {k: case[k] for k in ('stage', 'id', 'family', 'condition', 'seed', 'truth', 'rotation', 'negative')}
        # Some families carry additional generator parameters; readers/traces never enter the renderer.
        for k in ('case', 'polarity', 'scene', 'blur', 'gain', 'cross', 'window', 'visibility'):
            if k in case:
                config[k] = case[k]
        row = dict(source=item, rotations_deg=deltas, truth_mm=case['truth'],
                   reader_source_sha256=reader_sha, plan_sha256=sha((OUT / 'plan.json').read_bytes()),
                   policy_source_sha256=sha(Path(photo.__file__).read_bytes()))
        if cached.get('original_pixel_sha256') == cached.get('expected_pixel_sha256') == case['image_sha256']:
            digest = cached['original_pixel_sha256']
        else:
            image, _, _ = study.image(config)
            digest = sha(image.tobytes())
        row['original_pixel_sha256'] = digest
        row['expected_pixel_sha256'] = case['image_sha256']
        if digest != case['image_sha256'] or case['reader_hashes']['pcal.py'] != reader_sha:
            row.update(status='NOT_RUN', reason='original pixels or v1 source do not match saved evidence')
            save(target, row)
            return row
        readings = []
        for delta in deltas:
            ident = tag + f'-turn{delta}'
            if delta == 0:
                result, pixels, mode = case['readers']['v1']['result'], digest, 'saved v1 diagnostic'
            elif delta == 90 and previous is not None:
                result, pixels, mode = previous['alternative'], previous['turned_pixel_sha256'], 'saved fixed +90 v1 diagnostic'
            elif delta in cached_photos:
                result = cached_photos[delta]
                pixels, mode = result['input_sha256'], result['evidence_mode']
            else:
                job = dict(config, rotation=(config['rotation'] + math.radians(delta)) % (2 * math.pi))
                image, _, focal = study.image(job)
                pixels = sha(image.tobytes())
                Image.fromarray(image).save(OUT / (ident + '.png'))
                result = pcal.read_photo(image, pcal.design_burn(), focal_px=focal)
                mode = 'new default v1 read'
            readings.append(dict(result, id=ident, input_sha256=pixels, evidence_mode=mode))
            row.update(status='RUN', photos=readings)
            save(target, row)
            print(ident, result['status'], result.get('L_mm'), flush=True)
        groups = []
        sizes = [2, 3, 4] if previous is not None else [3]
        for size in sizes:
            decision = photo.photo_agreement(readings[:size])
            error = decision['L_mm'] - case['truth'] if decision['written'] else None
            groups.append(dict(size=size, decision=decision, error_mm=error,
                               wrong=abs(error) > plan['wrong_threshold_mm'] if error is not None else False))
        row['groups'] = groups
        save(target, row)
        return row

    examples = ([evaluate(s, plan['counterexample_rotations_deg'], 'known-' + str(i), old['cases'][i])
                 for i, s in enumerate(plan['counterexample_sources'])] if partition is None else [])
    rates = [evaluate(s, plan['rate_rotations_deg'], 'rate-' + f'{i:03d}')
             for i, s in enumerate(plan['rate_sources'])
             if partition is None or i % partition[1] == partition[0]]
    if partition is not None:
        print('partition complete', partition, len(rates), flush=True)
        return
    real = []
    real_sources = []
    study_freeze = source(BASE / 'frozen.json')
    frozen_hashes = checked(study_freeze)['hashes']
    if frozen_hashes[str(OTHER / 'discprobe/pcal.py')] != reader_sha:
        raise ValueError('study freeze used another v1 source')
    for path in sorted((BASE / 'real').glob('case_*.json')):
        case = load(path)
        image_path = Path(case['path'])
        raw = image_path.read_bytes()
        # Match the saved decoded-pixel hash without re-running v1.
        from PIL import ImageOps
        with Image.open(image_path) as im:
            pixel_sha = sha(np.asarray(ImageOps.exif_transpose(im).convert('RGB')).tobytes())
        per_record_reader = case.get('reader_hashes', {}).get('pcal.py')
        if (pixel_sha != case['image_sha256'] or frozen_hashes[str(image_path)] != sha(raw)
                or per_record_reader not in (None, reader_sha)):
            raise ValueError('real photo or reader does not match saved diagnostic')
        real_sources.append(dict(diagnostic=source(path), original=source(image_path), pixel_sha256=pixel_sha,
                                 reader_hash_scope='per-record' if per_record_reader else
                                                   'study freeze; real JSON has no per-record source hash'))
        real.append(dict(case['readers']['v1']['result'], id=image_path.name, input_sha256=sha(raw)))
    decisions = [r['groups'][0] for r in rates if r['status'] == 'RUN']
    summary = dict(policy=photo.PHOTO_L_POLICY, plan=plan, counterexamples=examples,
                   reader_version='v1', reader_sha256=photo.READER_SHA256,
                   reader_source_sha256=reader_sha,
                   policy_source_sha256=sha(Path(photo.__file__).read_bytes()),
                   check_script_sha256=sha(Path(__file__).read_bytes()),
                   rate=dict(planned=len(rates), run=len(decisions), not_run=len(rates)-len(decisions),
                             applications=sum(d['decision']['written'] for d in decisions),
                             wrong_applications=sum(d['wrong'] for d in decisions)),
                   rate_groups=rates, real_decision=photo.photo_agreement(real), real_sources=real_sources,
                   real_study_freeze=study_freeze,
                   real_photos=[{k:p.get(k) for k in ('id', 'status', 'L_mm', 'zone_spread_mm', 'c_deg', 'input_sha256')}
                                for p in real])
    save(OUT / 'summary.json', summary)
    print(json.dumps(dict(rate=summary['rate'], real=summary['real_decision']), indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--partition', type=int, nargs=2, metavar=('INDEX', 'COUNT'))
    args = parser.parse_args()
    if args.prepare == args.run:
        parser.error('choose exactly one of --prepare and --run')
    if args.partition and (not args.run or not 0 <= args.partition[0] < args.partition[1] <= 2):
        parser.error('partition requires --run and 0 <= INDEX < COUNT <= 2')
    prepare() if args.prepare else run(args.partition)
