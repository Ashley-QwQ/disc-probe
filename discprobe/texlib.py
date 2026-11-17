"""Optional, read-only texture catalog. Works pin specs, never a moving winner ID."""
from functools import lru_cache
import json
import math
import os
from pathlib import Path
from zipfile import BadZipFile

def safe(path):
    p = Path(path).absolute()
    if 'b' + 'lind' in str(p).casefold() or 'b' + 'lind' in str(p.resolve()).casefold():
        raise ValueError('excluded path')
    return p.resolve()


def canonical(spec):
    seq = bytes.fromhex(spec)
    if not seq:
        raise ValueError('empty texture')
    for n in range(1, len(seq) + 1):
        if len(seq) % n == 0 and seq[:n] * (len(seq) // n) == seq:
            return seq[:n].hex().upper()


def _stamp(path):
    s = path.stat()
    return str(path), s.st_size, s.st_mtime_ns


@lru_cache(maxsize=2)
def _load(table_stamp, catalog_stamp):
    import numpy as np
    with np.load(table_stamp[0], allow_pickle=False) as z:
        arrays = {k: z[k] for k in z.files}
    specs = arrays['specs']
    delta, xyz = arrays['delta'], arrays['xyz']
    if (specs.dtype.kind != 'U' or specs.ndim != 1 or delta.ndim != 1 or len(delta) < 2
            or xyz.shape != (len(specs), len(delta), 3) or not np.isfinite(xyz).all()
            or not np.isfinite(delta).all() or not np.all(np.diff(delta) > 0)
            or not {'A5', 'B9'} <= set(specs)):
        raise ValueError('invalid texture colour table')
    for name in ('cmf_nm', 'cmf', 'xyz_to_srgb', 'signature'):
        arrays[name]  # required by both renderers
    if (arrays['cmf'].shape != (len(arrays['cmf_nm']),3) or arrays['xyz_to_srgb'].shape != (3,3)
            or any(not np.isfinite(arrays[k]).all() for k in ('cmf_nm','cmf','xyz_to_srgb'))):
        raise ValueError('invalid texture colour transforms')
    with open(catalog_stamp[0], encoding='utf-8-sig') as f:
        rows = [json.loads(line) for line in f if line.strip()]
    if not rows or any(canonical(r['spec_canonical']) not in specs for r in rows):
        raise ValueError('catalog/table mismatch')
    return dict(arrays=arrays, rows=rows, table=table_stamp[0],
                token=(table_stamp, catalog_stamp, str(arrays['signature'])))


def library():
    root = os.environ.get('DISCPROBE_TEXLIB')
    if not root:
        return None
    try:
        root = safe(root)
        return _load(_stamp(safe(root / 'colour_table.npz')), _stamp(safe(root / 'textures.jsonl')))
    except (OSError, ValueError, KeyError, TypeError, EOFError, BadZipFile):
        return None


def configure(root):
    os.environ['DISCPROBE_TEXLIB'] = str(safe(root))
    _load.cache_clear()
    from . import simulate_a3
    simulate_a3.tables.cache_clear()


@lru_cache(maxsize=1)
def legacy_materials():
    p = Path(__file__).parent / 'web/home/design/swatches.json'
    return list(json.loads(p.read_text(encoding='utf-8'))['swatches'].values())


def resolve(value):
    """Resolve CLI references; explicit byte sequences retain their original bytes."""
    lib = library()
    for m in legacy_materials():
        if value == m['id']:
            return m['spec']
    if lib:
        for r in lib['rows']:
            if value == r['id']:
                return r['spec_canonical']
    if value.upper().startswith('TEX:'):
        return canonical(value[4:])
    if value.upper() == 'RND' or value.lower() == 'bands' or value.upper().startswith('MIX:'):
        return value
    canonical(value)  # clear validation error for an unknown ID
    return value


def lab(rgb):
    import numpy as np
    if isinstance(rgb, str):
        rgb = [int(rgb.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)]
    v = np.asarray(rgb, float) / 255
    v = np.where(v <= .04045, v / 12.92, ((v + .055) / 1.055) ** 2.4)
    xyz = np.array([[.4124564, .3575761, .1804375], [.2126729, .7151522, .0721750],
                    [.0193339, .1191920, .9503041]]) @ v / [.95047, 1, 1.08883]
    f = np.where(xyz > (6/29)**3, np.cbrt(xyz), xyz / (3*(6/29)**2) + 4/29)
    return np.array([116*f[1]-16, 500*(f[0]-f[1]), 200*(f[1]-f[2])])


def metrics(row, delta):
    """Y interpolates; stability conservatively takes both surrounding samples.

    Missing/full-window-outside-model values never become zero stability.
    """
    import numpy as np
    c = row['colour']
    if delta is None:
        s = c.get('stability_at_burn', {})
        return dict(y=c.get('burn_y'), stability=s.get('de05'), fades=s.get('fades_out', True))
    if not .10 <= delta <= .95:
        return dict(y=None, stability=None, fades=True)
    pos = (delta - .10) / .05
    lo, hi = max(0, int(math.floor(pos+1e-7))), min(17, int(math.ceil(pos-1e-7)))
    def values(k):
        a = c.get(k, [None]*18)
        return [a[i] for i in sorted({lo, hi})]
    ys, ds, fs = values('y_by_delta'), values('stability_de05'), values('fades_out')
    y = None if None in ys else float(np.interp(pos, [lo, hi], [ys[0], ys[-1]]))
    return dict(y=y, stability=None if None in ds else max(ds), fades=any(v is not False for v in fs))


def materials(lib):
    # Every catalog goal remains searchable. Equal specs share a saved identity,
    # but are only visually grouped in the curated area, never in All materials.
    out = []
    for r in lib['rows']:
        if r['grade'] not in ('converged', 'best_so_far'):
            continue
        spec = canonical(r['spec_canonical'])
        rgb = r['colour'].get('burn_srgb') or '#696969'
        out.append(dict(id='tex:'+spec, spec=spec, name=r['id'],
                        texture_ids=[r['id']], periods_um=r.get('periods_um', []),
                        period_um=next(iter(r.get('periods_um', [])), None),
                        rgb=[int(rgb[i:i+2], 16) for i in (1, 3, 5)],
                        purity=min(r.get('purity') or [0]),
                        tested=r.get('a3v3', {}).get('same_spec') is True,
                        colour=r['colour']))
    return out


def add_parser(sub):
    p = sub.add_parser('textures', help='query the optional texture library (no drive access)')
    p.add_argument('--texlib')
    s = p.add_subparsers(dest='texture_command', required=True)
    f = s.add_parser('find')
    f.add_argument('--grade', choices=['converged', 'best_so_far', 'approx'])
    f.add_argument('--kind')
    f.add_argument('--near')
    f.add_argument('--delta', type=float)
    f.add_argument('--max-de05', type=float)
    f.add_argument('--min-y', type=float)
    f.add_argument('--top', type=int, default=10)
    show = s.add_parser('show')
    show.add_argument('id')
    for q in (f, show):
        q.add_argument('--json', action='store_true')
        q.add_argument('--texlib', default=__import__('argparse').SUPPRESS)
    p.set_defaults(func=command)


def command(a):
    import numpy as np
    lib = library()
    if not lib:
        raise ValueError('texture library unavailable; set DISCPROBE_TEXLIB or --texlib')
    rows = lib['rows']
    if a.texture_command == 'show':
        spec = resolve(a.id)
        result = [r for r in rows if r['spec_canonical'] == canonical(spec)]
    else:
        if a.top < 1 or (a.delta is not None and (not math.isfinite(a.delta) or not .1 <= a.delta <= .95)):
            raise ValueError('top must be positive; delta must be 0.10..0.95')
        for v in (a.min_y, a.max_de05):
            if v is not None and (not math.isfinite(v) or v < 0):
                raise ValueError('metric limits must be finite and nonnegative')
        near = lab(a.near) if a.near else None
        result = []
        for r in rows:
            if a.grade and a.grade != r['grade'] or a.kind and a.kind != r['kind']:
                continue
            m = metrics(r, a.delta)
            if a.min_y is not None and (m['y'] is None or m['y'] < a.min_y):
                continue
            if a.max_de05 is not None and (m['stability'] is None or m['stability'] > a.max_de05):
                continue
            if near is not None:
                c = r['colour']['burn_srgb'] if a.delta is None else r['colour']['srgb_by_delta'][round((a.delta-.1)/.05)]
                if c is None:
                    continue
                r = dict(r, delta_E=float(np.linalg.norm(lab(c)-near)))
            result.append(r)
        result.sort(key=lambda r: (r.get('delta_E', 0), r['id']))
        result = result[:a.top]
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
