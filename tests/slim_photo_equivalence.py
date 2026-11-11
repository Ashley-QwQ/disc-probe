"""Synthetic photo end-to-end comparisons; no source photographs are fabricated.

Uses reduced 800px tile photos to bound runtime. The report explicitly records
this change from the application's default 1200px fitting width.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys
import warnings

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parent)]
from slim_support import ROOT, ARTIFACTS, low_priority
low_priority()
import numpy as np
from PIL import Image
from discprobe import tilephoto, numerics, beacondisc, beaconread, tiledisc
from slim_equivalence import load_module, write, differences
import equivalence_scipy as old


@contextmanager
def backend(name):
    saved = {}
    names = ['gaussian_filter', 'maximum_filter', 'fftconvolve', 'least_squares', 'minimize']
    for module in (numerics, tilephoto):
        for key in names:
            if hasattr(module, key):
                saved[module, key] = getattr(module, key)
                if name == 'old':
                    setattr(module, key, getattr(old, key))
    try:
        yield
    finally:
        for (module, key), value in saved.items():
            setattr(module, key, value)


def tiles():
    synth = load_module(ROOT / 'tools/synth_photo_test.py', '_audit_synth_photo')
    synth.W, synth.H_PX, synth.F = 800, 600, 560.
    layout = Path('D:/disc-probe/evidence/tilescan/tiles_layout.json')
    lay = json.loads(layout.read_text(encoding='utf-8'))
    labels, textures, _ = tiledisc.design(lay['palette'], **tiledisc.geometry(lay))
    H = synth.camera_h((20., 10., 170.), roll_deg=17.)
    rgb = synth.render(labels, textures, H, .3)
    source = ARTIFACTS / 'synthetic-tile.png'
    Image.fromarray((rgb * 255).astype('uint8')).save(source)
    tilephoto.FIT_WIDTH = 800
    results = {}
    for name in ('old', 'new'):
        messages = []
        with backend(name), warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter('always')
            result = tilephoto.analyse(str(source), str(layout), str(ARTIFACTS / ('photo-' + name)),
                                       mirrors=(False,), focal_px=synth.F, log=messages.append)
        results[name] = dict(value=result, messages=messages, warnings=[str(w.message) for w in ws])
        write('photo_partial.json', results)
    results['delta'] = differences(results['old']['value'], results['new']['value'])
    results['input_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    results['scope'] = 'one shared synthetic 800x600 raster; FIT_WIDTH=800 on both paths, default is 1200'
    # Compare every field of every tile's measured colour/readout.
    import csv
    a = list(csv.DictReader((ARTIFACTS / 'photo-old/tiles.csv').open()))
    b = list(csv.DictReader((ARTIFACTS / 'photo-new/tiles.csv').open()))
    fields = {}
    for aa, bb in zip(a, b):
        for key, value in aa.items():
            try:
                delta = abs(float(value) - float(bb[key]))
            except (ValueError, TypeError):
                delta = float(value != bb[key])
            fields[key] = max(fields.get(key, 0), delta)
    results['tile_field_max_delta'] = fields
    results['csv_byte_identical'] = (ARTIFACTS / 'photo-old/tiles.csv').read_bytes() == (ARTIFACTS / 'photo-new/tiles.csv').read_bytes()
    return results


def beacon():
    labels, textures, _ = beacondisc.design()
    from discprobe.imagedisc import HALF_MM, CELL_MM, SIZE
    ppm = 8.
    yy, xx = np.mgrid[:1024, :1024]
    x, y = (xx + .5 - 512) / ppm, (512 - yy - .5) / ppm
    ix = np.clip(((x + HALF_MM) / CELL_MM).astype(int), 0, SIZE - 1)
    iy = np.clip(((HALF_MM - y) / CELL_MM).astype(int), 0, SIZE - 1)
    rng = np.random.default_rng(721)
    colours = rng.integers(20, 230, (len(textures), 3), dtype=np.uint8)
    rgb = colours[labels[iy, ix]]
    rgb[np.hypot(x, y) > 60] = 30
    out = {}
    whole = {}
    for name in ('old', 'new'):
        with backend(name):
            out[name] = beaconread.read_tiles(rgb, ppm)
            whole[name] = beaconread.read_disc(rgb, ppm)
    return dict(count_old=len(out['old']), count_new=len(out['new']), identical=out['old'] == out['new'],
                max_field_delta=differences(out['old'], out['new']), input_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),
                scope='synthetic front-facing beacon raster, 8 px/mm',
                disc_old=whole['old'], disc_new=whole['new'], disc_identical=whole['old'] == whole['new'],
                disc_max_field_delta=differences(whole['old'], whole['new']), **out)


if __name__ == '__main__':
    if not old.AVAILABLE:
        print('SKIPPED: optional SciPy oracle absent')
    else:
        if '--beacon-only' not in sys.argv:
            write('photo.json', tiles())
            print('tilephoto: evidence written', flush=True)
        write('beacon.json', beacon())
        print('beaconread: evidence written', flush=True)
