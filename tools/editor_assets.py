"""Refresh the bundled singles palette offline; no source assets are modified."""
import hashlib
import json
from pathlib import Path
import numpy as np
from discprobe.editor_ops import delta
from discprobe import simulate

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('D:/disc-probe/docs/goals/night/palette/palette_merged.json')

def rgb(nm):
    # Existing tools/lut_scatter.py wavelength_rgb, also used by the template job.
    r=g=b=0
    if nm<440:r=-(nm-440)/40;b=1
    elif nm<490:g=(nm-440)/50;b=1
    elif nm<510:g=1;b=-(nm-510)/20
    elif nm<580:r=(nm-510)/70;g=1
    elif nm<645:r=1;g=-(nm-645)/65
    else:r=1
    if not 400<=nm<=700:return [50,50,50]
    return [int(round(max(0,min(1,c))*255)) for c in (r,g,b)]

def main():
    raw=SOURCE.read_bytes();source=json.loads(raw)
    # Preserve the first-round project's 255 stable slots; the upstream research
    # palette can grow independently, while the existing writer accepts uint8.
    retained=json.loads((ROOT/'tools/editor-material-ids.json').read_text(encoding='utf8'))
    template=Path('D:/disc-probe/.claude/worktrees/editor-template/evidence/template/sample/swatches.json')
    aliases={}
    if template.exists():
        exported=json.loads(template.read_text(encoding='utf-8-sig'))
        aliases={m['id']:(name,m) for name,m in exported['swatches'].items() if m.get('kind')=='single'}
    swatches={}
    for i,m in enumerate(retained):
        period=m['periods_um'][0]
        name=f'{period:.3f} µm';srgb=m.get('srgb',m.get('rgb'))
        extra={}
        if m.get('template_name'):extra['template_name']=m['template_name']
        swatches[name+' '+m['id']]=dict(id=m['id'],kind='single',spec=m['spec'],periods_um=m['periods_um'],periods_T=m['periods_T'],
                             srgb=srgb,hex='#'+''.join(f'{c:02x}' for c in srgb),source=m['source'],
                             risk=m['risk'],period_conflict=m['period_conflict'],**extra)
    data=dict(schema_version=1,colour_status='model-placeholder-until-photo-validation',
              source=dict(file='palette_merged.json',sha256=hashlib.sha256(raw).hexdigest(),selection='first-round 255 stable single material definitions',available_singles=len(source['singles']),
                          retained_manifest='tools/editor-material-ids.json',retained_manifest_sha256=hashlib.sha256((ROOT/'tools/editor-material-ids.json').read_bytes()).hexdigest()),
              pose=dict(camera=[0,70,330],flash=[-43.66,89.79,330],sample_mm=[40,0],axes='x right, y up'),swatches=swatches)
    lut_path=Path(simulate.__file__).with_name('simulate_lut.npz')
    with np.load(lut_path) as lut:
        used={'A5','B9'}|{m['spec'] for m in swatches.values() if len(m['spec'])==2}
        data['preview_lut']=dict(source='discprobe/simulate_lut.npz',sha256=hashlib.sha256(lut_path.read_bytes()).hexdigest(),
            reference_period_um=.8528123052898693,photo_saturation=simulate.PHOTO_SATURATION,
            single={code:((lut['single'][int(code,16)]/255.)**2-.02).ravel().tolist() for code in sorted(used)},
            groove=lut['groove'].astype(float).ravel().tolist(),
            recipe_policy='A5 spectral-response LUT warped by period ratio; no measured multi-byte spectral LUT')
        # Exact single-byte reference vectors from the existing Python preview.
        x,y=np.array(40.),np.array(0.)
        dt=simulate.along_track(x,y,simulate.CAMERA,simulate.FLASH)
        cx,cy=simulate.unit(simulate.CAMERA,x,y);lx,ly=simulate.unit(simulate.FLASH,x,y)
        dr=abs((cx+lx)*x+(cy+ly)*y)/40
        it=int(np.rint(dt/.005));ir=int(np.rint(dr/.005));checks=[]
        for code in sorted(used):
            linear=((lut['single'][int(code,16),it]/255.)**2-.02+.15*lut['groove'][ir]+.05*.177)*4
            grey=linear@np.array([.2126,.7152,.0722]);linear=np.clip(grey+simulate.PHOTO_SATURATION*(linear-grey),0,1)
            encoded=np.where(linear<=.0031308,12.92*linear,1.055*linear**(1/2.4)-.055)
            checks.append(dict(spec=code,rgb=np.uint8(np.clip(encoded*255,0,255)).tolist()))
        data['preview_checks']=checks
    data['display_colours']=simulate.material_swatches(list(swatches.values()))
    data['display_model']=dict(module='discprobe.simulate',entry='material_swatches',sample_mm=[40,0],
                               policy='same spectra, linear-light averaging and encode_photo as render; multi-byte periods use A5 response warp')
    target=ROOT/'discprobe/web/home/design/swatches.json'
    target.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(f'{len(swatches)} single materials -> {target.relative_to(ROOT)}')

if __name__=='__main__':main()
