"""Document-to-PNG adapter for both simulate CLI and the local editor API.

No optical model here: all light, spectra, fine sampling and tone mapping are in
simulate.render(), the release's own renderer. Requests are serialized to bound
CPU/memory while HTTP and the editor remain responsive.
"""
from collections import OrderedDict
import hashlib
import io
import json
import math
from pathlib import Path
import threading

from . import editor_ops, simulate

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
    return result


def png_bytes(image):
    output=io.BytesIO()
    image.save(output,format='PNG')
    return output.getvalue()


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
        if type(size) is not int or not 200<=size<=2048 or quality not in ('draft','full'):
            raise ValueError('preview size must be 200..2048 and quality draft or full')
        pose=pose_options(payload.get('pose'))
        if not isinstance(payload.get('document'),dict):
            raise ValueError('invalid work document')
        document=editor_ops.validate(editor_ops.migrate(payload['document']))
        digest=hashlib.sha256(json.dumps(document,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        key=json.dumps([digest,pose,size,quality],sort_keys=True,separators=(',',':'))
        meta=dict(document_hash=digest,size=size,quality=quality,cache_hit=False)
        with _RENDER_LOCK:
            if key in self.images:
                self.images.move_to_end(key)
                return self.images[key],dict(meta,cache_hit=True)
            design=self.designs.get(digest)
            if design is None:
                design=editor_ops.compose(document)
                # Retain ordinary 20 um works; very large grids may be rendered but
                # must not accumulate in a long-lived HTTP process.
                if design.nbytes<=72*1024*1024:
                    self.designs[digest]=design
                    while sum(a.nbytes for a in self.designs.values())>96*1024*1024:
                        self.designs.popitem(last=False)
            else:
                self.designs.move_to_end(digest)
            image=simulate.render(design,size,materials=document['materials'],fine=quality=='full',**pose)
            data=png_bytes(image)
            self.images[key]=data
            while len(self.images)>12 or sum(map(len,self.images.values()))>32*1024*1024:
                self.images.popitem(last=False)
            return data,meta

    def swatches(self,pose=None):
        pose=pose_options(pose)
        key=json.dumps(pose,sort_keys=True)
        with _RENDER_LOCK:
            if key not in self.palettes:
                palette=json.loads((Path(__file__).parent/'web/home/design/swatches.json').read_text(encoding='utf8'))
                colours=simulate.material_swatches(list(palette['swatches'].values()),pose['camera'],pose['flash'])
                self.palettes[key]=dict(pose=pose,colours=colours,model='discprobe.simulate',sample_mm=[40,0])
                if len(self.palettes)>8:self.palettes.popitem(last=False)
            return self.palettes[key]
