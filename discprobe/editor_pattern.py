"""DP pattern reference v1. Row-major uint16 material slots, mm, y down."""
from pathlib import Path
import json, math, sys
import numpy as np

Q=1_000_000  # integer nanometres per millimetre
def ticks(v):
    return np.floor(np.asarray(v)*Q+0.5).astype(np.int64)
def integer(v, low, high):
    return type(v) in (int,float) and math.isfinite(v) and v==math.floor(v) and low<=v<=high
def validate(d):
    if not integer(d.get('version'),1,1): raise ValueError('pattern version must be 1')
    if d.get('pattern') not in ('diamond','dots','stripes'): raise ValueError('unknown pattern')
    if d.get('coordinates') not in ('cartesian','polar'): raise ValueError('unknown coordinates')
    for key in ('pitch_mm','size_mm','angle_deg'):
        if isinstance(d.get(key),bool) or not isinstance(d.get(key),(int,float)) or not math.isfinite(d[key]): raise ValueError(key)
    if abs(d['angle_deg'])>360000: raise ValueError('angle out of range')
    if not 0<d['size_mm']<=d['pitch_mm']/2 or not 1e-5<=d['pitch_mm']<=50: raise ValueError('size/pitch out of range')
    for key in ('origin_mm','phase_mm'):
        if len(d[key])!=2 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or abs(x)>120 for x in d[key]): raise ValueError(key)
    if not isinstance(d['materials'],list) or len(d['materials'])!=2 or any(not integer(x,0,65534) for x in d['materials']): raise ValueError('material slots')
    if d['coordinates']=='polar' and (type(d['reference_radius_mm']) not in (int,float) or not math.isfinite(d['reference_radius_mm']) or not 0<d['reference_radius_mm']<=60): raise ValueError('reference radius')
    if 'segments' in d and not integer(d['segments'],1,100000): raise ValueError('segments')
    return d
def render(d, grid):
    validate(d)
    n,m=grid['height'],grid['width'];cell=grid['cell_mm']
    if not integer(n,1,24000) or not integer(m,1,24000) or type(cell) not in (int,float) or not math.isfinite(cell) or cell<=0: raise ValueError('grid')
    n,m=int(n),int(m)
    if any(type(grid[k]) not in (int,float) or not math.isfinite(grid[k]) or abs(grid[k])>120 for k in ('left_mm','top_mm')): raise ValueError('grid origin')
    ann=grid['annulus_mm']
    if len(ann)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in ann) or not 0<=ann[0]<ann[1]<=60: raise ValueError('annulus')
    x=ticks(grid['left_mm']+(np.arange(m)+.5)*cell)/Q
    out=np.full((n,m),65535,dtype='<u2')
    p=int(ticks(d['pitch_mm']));a=math.radians(d['angle_deg']);co,si=math.cos(a),math.sin(a)
    half=int(ticks(d['size_mm']/2));diamond_half=int(ticks(d['size_mm']*math.sqrt(2)/2))
    cx,cy=d['origin_mm'];phx,phy=d['phase_mm'];ann=grid['annulus_mm']
    segments=d.get('segments',max(1,math.floor(2*math.pi*d.get('reference_radius_mm',40)/d['pitch_mm']+.5)))
    def mod(v):
        r=v%p
        return np.minimum(r,p-r)
    for j in range(n):
        y=int(ticks(grid['top_mm']+(j+.5)*cell))/Q
        dx,dy=x-cx,y-cy
        if d['coordinates']=='cartesian':
            u=ticks(dx*co+dy*si-phx);v=ticks(-dx*si+dy*co-phy)
        else:
            theta=(np.arctan2(dy,dx)-a)%(2*math.pi)
            u=ticks(np.hypot(dx,dy)-phx)
            v=ticks(theta*segments*d['pitch_mm']/(2*math.pi)-phy)
        if d['pattern']=='stripes': mask=mod(u)<half
        elif d['pattern']=='dots': mask=mod(u)**2+mod(v)**2<half**2
        else: mask=(mod(u+v)<diamond_half)|(mod(u-v)<diamond_half)
        r=ticks(np.hypot(x,y))
        keep=(r>=int(ticks(ann[0])))&(r<int(ticks(ann[1])))
        out[j,keep]=np.where(mask,d['materials'][0],d['materials'][1])[keep]
    return out
if __name__=='__main__':
    spec=json.loads(Path(sys.argv[1]).read_text(encoding='utf8'))
    render(spec['fill'],spec['grid']).tofile(sys.argv[2])
