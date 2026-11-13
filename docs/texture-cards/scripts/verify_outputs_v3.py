"""Validate completed V3 outputs and all-row Monte Carlo variation.

Run only when the renderer's encoding workers have exited. Visual review is
separate and is never inferred from this program's numerical checks.
"""
import json
import re
import zlib
from pathlib import Path
import numpy as np
from PIL import Image
import wave_model as M
import make_cards as L


def main():
    data=json.loads((M.HERE.parent/'data'/'palette_merged.json').read_text(encoding='utf-8'))
    rows=sorted(data['singles'],key=lambda r:(r['periods_um'][0],r['spec']))
    expected=[r['id'] for r in rows]
    result={'model_signature':M.signature()[0],'sheet_1':{},'source_files_unchanged_since_validation':False}
    val=json.loads((M.OUT/'validation.json').read_text(encoding='utf-8'))
    assert val['source_provenance']['signature']==M.signature()[0]
    assert val['source_provenance']['source_hashes']==M.provenance()['source_hashes']
    result['source_files_unchanged_since_validation']=True
    for lamp in ('led','d65'):
        name='sheet_1_singles_'+lamp
        manifest=json.loads((M.OUT/(name+'_manifest.json')).read_text(encoding='utf-8'))
        assert [r['id'] for r in manifest['rows']]==expected
        assert manifest['count']==260 and manifest['text_overlap_count']==0
        assert manifest['annotation_minimum_pt']>=5 and manifest['label_minimum_pt']>=6
        assert manifest['model_signature']==M.signature()[0]
        image=Image.open(M.OUT/(name+'.png')).convert('RGB')
        with Image.open(M.OUT/(name+'.png')) as png:
            assert png.size==(3508,4961) and len(png.info['icc_profile'])>0
            assert all(abs(d-300)<.001 for d in png.info['dpi'])
            icc=png.info['icc_profile']
        pdf_bytes=(M.OUT/(name+'.pdf')).read_bytes()
        profile=re.search(rb'<< /Length (\d+) /N 3 [^\n]* >>\nstream\n',pdf_bytes)
        assert profile
        profile_data=pdf_bytes[profile.end():profile.end()+int(profile.group(1))]
        assert zlib.decompress(profile_data)==icc
        pdf=L.verify_pdf(M.OUT/(name+'.pdf'),[image])
        assert M.sha(M.OUT/(name+'.png'))==manifest['PNG_sha256']
        assert M.sha(M.OUT/(name+'.pdf'))==manifest['PDF_sha256']
        # Check that no annotation is written across the modelled main strip.
        for row in manifest['rows']:
            x0,y0,x1,y1=row['strip_bbox']
            for a in manifest['text_boxes']:
                b=a['bbox']
                assert not (b[0]<x1 and b[2]>x0 and b[1]<y1 and b[3]>y0),(row['id'],a['text'])
        result['sheet_1'][lamp]={'count':260,'IDs_once':True,'PDF':pdf,'text_over_colour':False,'same_sRGB_ICC_in_PNG_and_PDF':True,
                                  'PNG_sha256':manifest['PNG_sha256'],'PDF_sha256':manifest['PDF_sha256']}
    # Eight complete blocks per row; split even/odd samples into independent
    # four-block means and compare the fully integrated LED predictions.
    first=[];second=[]
    for row in rows:
        key=M.hashlib.sha256(row['spec'].encode()).hexdigest()[:24]+'.npz'
        with np.load(M.CACHE/key) as z:
            assert str(z['signature'])==M.signature()[0] and len(z['samples'])==8
            records=json.loads(str(z['records_json']))
            assert len(records)==8 and len({r['seed'] for r in records})==8
            mass=z['samples']
            first.append(mass[::2].mean(0));second.append(mass[1::2].mean(0))
    op,_=M.build_operator()
    a=M.xyz_from_mass(np.array(first),op)[:,:,0,:]
    b=M.xyz_from_mass(np.array(second),op)[:,:,0,:]
    norms=np.max((a+b)/2,axis=(1,2))
    errors=np.max(abs(a-b),axis=(1,2))/norms
    result['all_260_sampling']={'eight_blocks_per_texture':True,'real_ECC_blocks_total':2080,
        'even_vs_odd_4_block_mean_relative_XYZ_difference_median':float(np.median(errors)),
        'p95':float(np.percentile(errors,95)),'max':float(np.max(errors)),
        'worst_id':rows[int(np.argmax(errors))]['id'],
        'scope':'Numerical sampling variation, not uncertainty in mark dimensions, lamp SPD or material optics.'}
    M.atomic_json(M.OUT/'output_checks.json',result)
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    main()
