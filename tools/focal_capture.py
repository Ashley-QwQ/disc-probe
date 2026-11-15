"""One-time, read-only extraction of SHOW-E fixed cells and old source provenance.

External sources are optional research inputs, never runtime dependencies. Run only to
refresh the frozen regression fixture; normal rebuilds use tools/focal_data files.
"""
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from discprobe import focal as F
from discprobe.hashing import file_sha256 as sha

DATA=ROOT/'data/focal'
FIXTURES=ROOT/'tools/focal_data'
POSE=Path('D:/disc-probe/docs/goals/showcase/pose')
TEMPLATE=POSE.parent/'template'
RECIPE=Path('D:/disc-probe/docs/goals/iso-cleanup/recipes/IMG2654-1x21-H.json')
LABELS=Path('C:/disc-probe-scratch/showcase-iso/img2654I.npy')


def capture():
    FIXTURES.mkdir(parents=True,exist_ok=True)
    recipe=json.loads(RECIPE.read_text(encoding='utf-8'))
    # The frozen external recipe records exact original bytes, not portable hashes.
    assert hashlib.sha256(LABELS.read_bytes()).hexdigest()==recipe['inputs'][str(LABELS)]
    textures=LABELS.with_suffix('.textures.txt')
    assert hashlib.sha256(textures.read_bytes()).hexdigest()==recipe['inputs'][str(textures)]
    specs=textures.read_text(encoding='ascii').split()
    assert specs==recipe['params']['textures']
    report=json.loads(LABELS.with_suffix('.json').read_text(encoding='utf-8'))
    labels=np.load(LABELS,mmap_mode='r',allow_pickle=False)
    assert labels.shape==(6000,6000) and labels.dtype==np.uint8
    samples=[]
    for label,spec in enumerate(specs):
        yy,xx=np.where(labels[10::20,10::20]==label)
        x=(xx*20+10+.5-3000)/50
        y=(3000-(yy*20+10+.5))/50
        keep=(np.hypot(x,y)>=24.063)&(np.hypot(x,y)<=56.600)
        xy=np.c_[x[keep],y[keep]]
        count=int(np.count_nonzero(labels==label))
        # Small patches can miss the 0.4mm lattice: retain actual original cells as fallback.
        if not len(xy) and count:
            iy,ix=np.where(labels==label)
            pick=np.linspace(0,len(ix)-1,min(64,len(ix))).astype(int)
            xy=np.c_[(ix[pick]+.5-3000)/50,(3000-iy[pick]-.5)/50]
        samples.append(dict(label=label,spec=spec,source_cells=count,
                            period_um=report.get('periods_um',{}).get(spec),xy_mm=xy.tolist()))
    np.savez_compressed(FIXTURES/'show_e_preview.npz',labels=labels[5::10,5::10])
    sources=[POSE/'pose_1x.json',POSE/'delta_map_1x.npy',POSE/'search_low.py',
             POSE/'build_deliverables.py',TEMPLATE/'make_rulers.py',TEMPLATE/'build_1x_labels.py',RECIPE]
    old=json.loads(sources[0].read_text(encoding='utf-8'))
    manifest=dict(sources=[dict(path=str(p),sha256=sha(p)) for p in sources],chosen=old['chosen'],framing=old['framing'])
    (DATA/'legacy.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    fixture=dict(name='SHOW-E 4-14 / IMG2654-1x21-H',recipe_sha256=sha(RECIPE),
                 labels_sha256=sha(LABELS),texture_sha256=sha(textures),report_sha256=sha(LABELS.with_suffix('.json')),
                 source_shape=list(labels.shape),cell_mm=.02,sample_stride_cells=20,
                 delta_scale=.93,delta_offset=0,materials=samples,ruler_patches=report['rulers']['patches'],
                 preview=dict(file='show_e_preview.npz',sha256=sha(FIXTURES/'show_e_preview.npz'),
                              note='600x600 nearest-centre samples of original labels, for illustrative preview only'),
                 prior_alpha_preview='not located; old-parameter preview reconstructed, not claimed as historical capture')
    raw=(json.dumps(fixture,separators=(',',':'))+'\n').encode('utf-8')
    (FIXTURES/'show_e_samples.json.gz').write_bytes(gzip.compress(raw,mtime=0))
    # Cross-check the original map at representative rows against the restored original geometry.
    d=np.load(POSE/'delta_map_1x.npy',mmap_mode='r',allow_pickle=False)
    for j in (0,1024,1536,2048,3000):
        assert np.allclose(d[j:j+1],F.map_rows(j,j+1,camera=old['chosen']['camera'],flash=old['chosen']['flash']),
                           equal_nan=True,atol=1e-7,rtol=0)
    print('captured',len(samples),'labels;',sum(bool(m['xy_mm']) for m in samples),'sampled;',
          len(report['rulers']['patches']),'ruler patches; legacy map coordinates match')


if __name__=='__main__':
    capture()
