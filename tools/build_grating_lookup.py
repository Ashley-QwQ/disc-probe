"""Pack the eligible, channel-checked textures actually used on the two recorded role cards."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from discprobe import gratingcard as G


def package(archive, character, output):
    original = archive/'delta-lookup.npz'
    index = archive/'angle-curves-index.csv'
    reports = [archive/'pair-channel-check.json',character/'gate-cache.json']
    manifests = [archive/'flip-a.labels.textures.json',character/'g6/labels.textures.json']
    sources = [original,index,*reports,*manifests]
    used = set().union(*(G.read_json(path)['textures'] for path in manifests))
    results = {}
    for path in reports:
        report = G.read_json(path)
        for spec in G.checked_textures(report):
            row = report[spec]
            results[spec] = dict(passed=True,**{full:row.get(full,row.get(short))
                for full,short in zip(G.GATE_KEYS,('F512','lean','dsv'))})
    with index.open(encoding='utf-8-sig',newline='') as stream:
        fields = ('spec','id','rev','texlib_rev','risk')
        rows = [{key:row[key] for key in fields} for row in csv.DictReader(stream)
                if row['spec'] in used & results.keys()]
    names = {row['spec'] for row in rows}
    output.mkdir(parents=True,exist_ok=True)
    with np.load(original,allow_pickle=False) as table:
        keep = np.array([i for i,spec in enumerate(table['spec']) if spec in names])
        assert len(keep) == len(names)
        data = {key:table[key] for key in table.files}
        for key in ('spec','xyz_order','fitted_spec'):
            data[key] = data[key][keep]
        np.savez_compressed(output/G.DEFAULT_LOOKUP.name,**data)
    with (output/G.DEFAULT_INDEX.name).open('w',encoding='utf-8',newline='') as stream:
        writer = csv.DictWriter(stream,fields,lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    (output/G.DEFAULT_CHECKS.name).write_text(json.dumps({name:results[name] for name in sorted(names)},
                                                        indent=2)+'\n',encoding='utf-8')
    provenance = dict(used=len(used), included=len(names), omitted=sorted(used-names),
                      inputs_sha256={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in sources})
    (output/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(provenance,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('flip_archive',type=Path)
    parser.add_argument('character_work',type=Path)
    parser.add_argument('--out',type=Path,default=G.ASSETS)
    args = parser.parse_args()
    package(args.flip_archive,args.character_work,args.out)
