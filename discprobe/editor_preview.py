"""Document-to-PNG adapter for both simulate CLI and the local editor API.

No optical model here: the light, spectra, fine sampling and tone mapping of a work
document are in simulate_a3.render() (A3 v3 textures, Disc Lab's optics). Requests are serialized to bound
CPU/memory while HTTP and the editor remain responsive.
"""
from collections import OrderedDict
import hashlib
import io
import json
import math
from pathlib import Path
import threading

from . import editor_ops, simulate, simulate_a3, texlib

_RENDER_LOCK=threading.Lock()


def pose_options(pose=None):
    pose={} if pose is None else pose
    if not isinstance(pose,dict):
        raise ValueError('invalid viewing pose')
    result={}
    for key,default in [('camera',simulate.CAMERA),('flash',simulate.FLASH)]:
        value=pose.get(key,default)
        if not isinstance(value,(list,tuple)) or len(value)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>100000 for v in value) or value[2]<=0:
            raise ValueError('camera and flash must have finite coordinates and positive height')
        result[key]=tuple(float(v) for v in value)
    rotation=pose.get('rotate',0)
    if type(rotation) not in (int,float) or not math.isfinite(rotation):
        raise ValueError('rotation must be finite')
    result['rotate']=float(rotation)%360
    # the practice discs' fitted scale of the along-track factor (design/pose-swatches.json); 1 = the plain model
    scale=pose.get('delta_scale',1.)  # explicit legacy-work compatibility; new geometry uses 1
    if type(scale) not in (int,float) or not .5<=scale<=1.5:
        raise ValueError('delta_scale must be between 0.5 and 1.5')
    result['delta_scale']=float(scale)
    return result


def png_bytes(image):
    output=io.BytesIO()
    image.save(output,format='PNG')
    return output.getvalue()


def burn_map(design, size, materials, table):
    import numpy as np
    from PIL import Image

    used = np.flatnonzero(np.bincount(design.ravel()))
    swatches = simulate_a3.burn_colours([materials[slot] for slot in used], table)
    c = (np.arange(size) + .5) * 120 / size - 60
    x, y = np.meshgrid(c, -c)
    linear = np.zeros((size, size, 3))
    for slot, share in simulate.coverage_iter(design, size, x, y):
        material = materials[slot]
        if slot == 0 or material['id'] == 'background':
            rgb = (218, 214, 205)
        elif material['spec'] == 'A5':
            rgb = (62, 60, 56)
        else:
            rgb = swatches.get(material['id'], (105, 105, 105))
        linear += share[..., None] * (np.asarray(rgb) / 255)**2.2
    return Image.fromarray(np.uint8(np.rint(np.clip(linear, 0, 1)**(1/2.2)*255)))


class Renderer:
    def __init__(self):
        self.designs=OrderedDict()
        self.images=OrderedDict()
        self.palettes=OrderedDict()

    def render(self,payload):
        if not isinstance(payload,dict):
            raise ValueError('invalid preview request')
        size=payload.get('size',420)
        quality=payload.get('quality','full')
        view=payload.get('view','lamp')
        if type(size) is not int or not 200<=size<=2048 or quality not in ('draft','full'):
            raise ValueError('preview size must be 200..2048 and quality draft or full')
        if view not in ('lamp', 'burn'):
            raise ValueError('preview view must be lamp or burn')
        exposure=payload.get('exposure',0)
        if type(exposure) not in (int,float) or not -3 <= exposure <= 3:
            raise ValueError('preview exposure must be between -3 and 3 stops')
        if not isinstance(payload.get('document'),dict):
            raise ValueError('invalid work document')
        document=editor_ops.validate(editor_ops.migrate(payload['document']))
        requested_pose = payload.get('pose')
        if requested_pose is None and any('colour' in a for a in document['assignments']):
            from .editor_colour import work_rig
            requested_pose = work_rig(document)
        pose=pose_options(requested_pose)
        digest=hashlib.sha256(json.dumps(document,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        table = simulate_a3.tables()
        source = table['source_key']
        design_key = (digest, source) if any('colour' in a for a in document['assignments']) else digest
        key=json.dumps([digest,pose,size,quality,source,view,exposure],sort_keys=True,separators=(',',':'))
        meta=dict(document_hash=digest,size=size,quality=quality,cache_hit=False)
        with _RENDER_LOCK:
            if key in self.images:
                self.images.move_to_end(key)
                return self.images[key],dict(meta,cache_hit=True)
            design=self.designs.get(design_key)
            if design is None:
                design=editor_ops.compose(document, colour_table=table)
                # Retain ordinary 20 um works; very large grids may be rendered but
                # must not accumulate in a long-lived HTTP process.
                if design.nbytes<=72*1024*1024:
                    self.designs[design_key]=design
                    while sum(a.nbytes for a in self.designs.values())>96*1024*1024:
                        self.designs.popitem(last=False)
            else:
                self.designs.move_to_end(design_key)
            if view == 'burn':
                image = burn_map(design, size, document['materials'], table)
            else:
                image=simulate_a3.render(design,size,materials=document['materials'],fine=quality=='full',annulus_mm=document['annulus_mm'],table=table,exposure=exposure,**pose)
            data=png_bytes(image)
            self.images[key]=data
            while len(self.images)>12 or sum(map(len,self.images.values()))>32*1024*1024:
                self.images.popitem(last=False)
            return data,meta

    def swatches(self,pose=None):
        pose=pose_options(pose)
        lib=texlib.library()
        key=json.dumps([pose,simulate_a3.tables()['source_key']],sort_keys=True)
        with _RENDER_LOCK:
            if key not in self.palettes:
                if lib:
                    result=self.texture_swatches(lib,pose)
                    self.palettes[key]=result
                    while len(self.palettes)>8:self.palettes.popitem(last=False)
                    return result
                palette=json.loads((Path(__file__).parent/'web/home/design/swatches.json').read_text(encoding='utf8'))
                colours=simulate_a3.swatches(list(palette['swatches'].values()),pose['camera'],pose['flash'],delta_scale=pose['delta_scale'])
                self.palettes[key]=dict(pose=pose,colours=colours,model='discprobe.simulate_a3 (A3 v3)',sample_mm=[40,0],
                                       burn=simulate_a3.burn_colours(list(palette['swatches'].values())))
                if len(self.palettes)>8:self.palettes.popitem(last=False)
            return self.palettes[key]

    def texture_swatches(self,lib,pose):
        import numpy as np
        mats=texlib.materials(lib)
        x,y=np.array([[40.]]),np.array([[0.]])
        cx,cy=simulate.unit(np.asarray(pose['camera']),x,y)
        lx,ly=simulate.unit(np.asarray(pose['flash']),x,y)
        delta=float(abs(cy[0,0]+ly[0,0])*pose['delta_scale'])
        for m in mats:
            m.update(texlib.metrics(m,delta))
            del m['colour']
        return dict(pose=pose,source='texlib',signature=str(lib['token']),materials=mats,
                    colours=simulate_a3.swatches(mats,pose['camera'],pose['flash'],delta_scale=pose['delta_scale']),
                    burn=simulate_a3.burn_colours(mats),delta=delta,sample_mm=[40,0],
                    model='discprobe.simulate_a3 (A3 v3)')


def lamp_tables():
    """One atomic response binds browser metadata and curves to the same source."""
    import base64
    import numpy as np
    t=simulate_a3.tables()
    c=['A5_PERIOD_UM','PITCH_UM','TEX_GAIN','DESATURATE','VEIL','VEIL_RGB','GLARE_GAIN',
       'RAINBOW_GAIN','ZERO_ORDER_DARK','OTHER_DARK','HUB_MM','EDGE_MM','FINE_SAMPLES']
    meta=dict(specs=list(t['specs']),signature=t['signature'],source_key=t['source_key'],
              delta=dict(first=float(t['delta'][0]),last=float(t['delta'][-1]),n=len(t['delta'])),
              cmf=dict(first_nm=float(t['cmf_nm'][0]),last_nm=float(t['cmf_nm'][-1]),
                       n=len(t['cmf_nm']),values=t['cmf'].ravel().tolist()),
              xyz_to_srgb=t['m'].ravel().tolist(),constants={k:getattr(simulate_a3,k) for k in c})
    return dict(meta=meta,xyz=base64.b64encode(np.asarray(t['xyz'],dtype='<f4').tobytes()).decode('ascii'))
