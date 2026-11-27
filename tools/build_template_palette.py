"""Rebuild the small, attributable template swatch snapshot using local sources only.

python tools/build_template_palette.py D:/disc-probe/docs/goals/night/palette/palette_merged.json
No palette input paths are followed; the merged file is the authority for singles.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from discprobe import simulate
from discprobe.simulate_spectrum import texture_table
from discprobe.template import WARNING


def build(path):
    raw = Path(path).read_bytes()
    merged = json.loads(raw)
    delta = float(simulate.along_track(40., 0., simulate.CAMERA, simulate.FLASH))
    label_delta = delta  # Preserve the already exported material names and their period labels.
    # Keep material identities stable while replacing the colour model.
    selected = []
    used = set()
    for target in np.linspace(410, 640, 16):
        candidates = [r for r in merged['singles'] if r['spec'] not in used
                      and not r['period_conflict'] and r['risk'].startswith('low')
                      and len(r['periods_um']) == 1
                      and 400 <= r['periods_um'][0]*delta*1000 <= 700]
        row = min(candidates, key=lambda r: (abs(r['periods_um'][0]*delta*1000-target), r['spec']))
        used.add(row['spec'])
        selected.append(row)
    # Extend the release's 256-byte LUT with the SAME full ECC/EFMPlus PSD model.
    # This deterministic NPZ keeps ordinary export fast and independent of private sources.
    arrays = dict(specs=np.array([r['spec'] for r in selected]),
                  rgb=np.stack([texture_table(r['spec']) for r in selected]))
    extra_path = Path(simulate.__file__).with_name('simulate_texture_lut.npz')
    with zipfile.ZipFile(extra_path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,arr in arrays.items():
            stream=io.BytesIO(); np.lib.format.write_array(stream,arr,allow_pickle=False)
            info=zipfile.ZipInfo(name+'.npy',date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,stream.getvalue())
    simulate._extra_tables.cache_clear()
    pose = dict(camera=list(simulate.CAMERA),flash=list(simulate.FLASH),size=800,patch=[666,400,667,401])
    effective = [(666.5)*120/800-60,60-(400.5)*120/800]
    delta = float(simulate.along_track(*effective,simulate.CAMERA,simulate.FLASH))
    lut_path = Path(simulate.__file__).with_name('simulate_lut.npz')
    model = dict(name=simulate.TEXTURE_COLOUR_MODEL,version=simulate.TEXTURE_COLOUR_VERSION,
                 function='discprobe.simulate.texture_colour',
                 release='v0.1.2.1',lut_sha256=hashlib.sha256(lut_path.read_bytes()).hexdigest(),
                 extended_lut_sha256=hashlib.sha256(extra_path.read_bytes()).hexdigest(),
                 spectrum='full recording ECC/EFMPlus PSD; existing CIE/LED integration; 3 LBAs 64000/900000/1700000',
                 encoding='release sqrt 8-bit LUT, linear-light box filter, saturation .6, sRGB floor to uint8')
    swatches = {}
    for row in selected:
        lam = row['periods_um'][0] * delta * 1000
        rgb = list(simulate.texture_colour(row['spec'],delta,pose=pose))
        name = f'DP-{len(swatches)+1:02d} {row["periods_um"][0]*label_delta*1000:.0f}nm {row["spec"]}'
        swatches[name] = dict(kind='single', spec=row['spec'], periods_um=row['periods_um'],
                             periods_T=row['periods_T'], srgb=rgb, hex='#'+''.join(f'{v:02x}' for v in rgb),
                             computed=dict(function=model['function'],model=model['name'],version=model['version'],
                                           wavelength_nm=lam,delta=delta,pose=pose,
                                           note='Wavelength is a period label only; RGB comes from the complete recording spectrum'),
                             **{k:row[k] for k in ('id', 'source', 'purity', 'purity_basis', 'risk',
                                                  'risk_basis', 'period_conflict')})
    # Existing five-step grey experiment: chart-selected bright pair, fractions 0/.25/.5/.75/1.
    # Keep it explicitly separate from canonical singles; it is a recipe, never a made-up byte spec.
    with np.load(lut_path) as z:
        zone = int(np.clip(np.searchsorted(z['band_edges'], delta)-1, 0, len(z['band_bytes'])-1))
        bright_bytes = z['band_bytes'][zone]
    for share in (0., .25, .5, .75, 1.):
        descriptor = dict(components=[dict(spec='A5',weight=1-share),
                                     *[dict(spec=f'{v:02X}',weight=share/len(bright_bytes)) for v in bright_bytes]])
        rgb = list(simulate.texture_colour(descriptor,delta,pose=pose))
        name = f'DP-G{int(share*100):03d} 灰阶 Grey'
        swatches[name] = dict(kind='grey-recipe', spec=None, periods_um=[], srgb=rgb,
                             hex='#'+''.join(f'{v:02x}' for v in rgb),
                             recipe=dict(dark='A5', light=[f'{v:02X}' for v in bright_bytes], bright_fraction=share,
                                         method='linear-light area mixture; not an encoded single texture'),
                             source='art/compose_grey.py: LEVELS and chart-selected bright/dark experiment; simulate.render(light="bands")',
                             computed=dict(function=model['function'],model=model['name'],version=model['version'],
                                           descriptor=descriptor,delta=delta,pose=pose,band_zone=zone,
                                           note='Same texture_colour function; weighted spectra in linear light; may be tinted'),
                             risk='UNKNOWN', risk_basis='Photo validation of this grey recipe is not established')
    return dict(schema_version=2, comment=WARNING,model=model,
                source=dict(file='palette_merged.json', sha256=hashlib.sha256(raw).hexdigest(),
                            selection='16 distinct low-risk non-conflicting singles near 410..640 nm, plus 5 existing grey recipes'),
                pose=dict(**pose,sample_mm=effective,delta=delta,axes='x right, y up; one physical render pixel near r40 mm'),
                trust='Same model as simulate v0.1.2.1, not photo validated; position and pose dependent. DVD only; CD/BD files are reference colours, not predictions.',
                swatches=swatches)


if __name__ == '__main__':
    result = build(sys.argv[1])
    out = Path(__file__).resolve().parents[1] / 'discprobe/template_palette.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    for name, row in result['swatches'].items():
        print(name, row['hex'])
