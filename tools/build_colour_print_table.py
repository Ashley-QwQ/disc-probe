"""Extract the DVD colour-print palette from the calibrated zero-background scenario."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


SCENARIO = '0.000'
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / 'discprobe/colour_print'


def safe(path):
    path = Path(path).absolute()
    if 'b' + 'lind' in str(path).casefold() or 'b' + 'lind' in str(path.resolve()).casefold():
        raise ValueError('excluded path')
    return path.resolve()


def sha256(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def build(table, material_sets, output):
    table, material_sets, output = map(safe, (table, material_sets, output))
    scenario = json.loads(material_sets.read_text(encoding='utf-8-sig'))['scenarios'][SCENARIO]
    materials = scenario['materials']
    specs = [row['spec'] for row in materials]
    if scenario['background_Y'] != 0 or len(specs) != 58 or len(set(specs)) != 58:
        raise ValueError('expected 58 distinct materials at background Y=0')

    with np.load(table, allow_pickle=False) as z:
        provenance = json.loads(z['provenance_json'].item())
        if provenance['background_Y_in_table'] != 0 or provenance['delta_scale_applied'] or z['lamp'].item() != 'LED':
            raise ValueError('expected LED diffraction-only XYZ at unscaled delta nodes')
        index = {spec: i for i, spec in enumerate(z['specs'].tolist())}
        xyz = z['xyz']
        delta = z['delta']
        if len(delta) != 341 or not np.allclose(delta, np.linspace(.10, .95, 341), atol=1e-7, rtol=0):
            raise ValueError('unexpected fitted delta grid')
        source_sha = sha256(table)
        manifest = dict(scenario=SCENARIO, materials=materials, source_table_sha256=source_sha,
                        source_material_sets_sha256=sha256(material_sets), signature=z['signature'].item(),
                        geometry_to_model_delta=provenance['parameters']['delta_scale'])
        arrays = {key: z[key] for key in ('delta', 'cmf_nm', 'cmf', 'xyz_to_srgb', 'lamp', 'signature', 'source')}
        arrays.update(specs=np.array(specs), xyz=xyz[[index[s] for s in specs]], fitted=np.array(True),
                      reference_y=xyz[[index['A5'], index['B9']], :, 1].max(),
                      delta_scale=np.array(manifest['geometry_to_model_delta']), source_table_sha256=np.array(source_sha))

    output.mkdir(parents=True, exist_ok=True)
    output_table, output_materials = (safe(output / name) for name in ('table.npz', 'materials.json'))
    np.savez_compressed(output_table, **arrays)
    manifest['table_sha256'] = sha256(output_table)
    output_materials.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--table', required=True, type=Path)
    cli.add_argument('--material-sets', required=True, type=Path)
    cli.add_argument('--out', type=Path, default=DEFAULT_OUTPUT)
    args = cli.parse_args()
    build(args.table, args.material_sets, args.out)


if __name__ == '__main__':
    main()
