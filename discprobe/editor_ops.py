"""Portable DP work documents; raster masks and label composition, no device access.

SVG uses the page's embedded RGBA raster. Original SVG is retained as source evidence.
The sampling contract is documented in docs/EDITOR_DOCUMENT.md.
"""
from __future__ import annotations
import base64
import copy
import io
import json
import math
from collections import deque
from contextlib import ExitStack, contextmanager
from pathlib import Path
import numpy as np
from . import editor_pattern
from . import editor_tone
COVERAGE=np.array([[0,8,2,10],[12,4,14,6],[3,11,1,9],[15,7,13,5]])


def q(v):
    return np.floor(np.asarray(v) * 1e6 + .5) / 1e6


def grid(size=600):
    return dict(width=size, height=size, left_mm=-60, top_mm=-60,
                cell_mm=120 / size, annulus_mm=[24, 58])


def boolean_mask(a, b, op="replace"):
    a, b = np.asarray(a, dtype=bool), np.asarray(b, dtype=bool)
    if a.shape != b.shape:
        raise ValueError("mask dimensions")
    return {"add": lambda: a | b, "subtract": lambda: a & ~b,
            "intersect": lambda: a & b, "replace": lambda: b.copy()}[op]().astype(np.uint8)


def polygon(x, y, points):
    inside = np.zeros(np.broadcast(x, y).shape, bool)
    for i, (a, b) in enumerate(points):
        c, d = points[i - 1]
        if b != d:
            inside ^= ((b > y) != (d > y)) & (x < (c-a)*(y-b)/(d-b)+a)
    return inside


def selection(d, g, rgba=None):
    w, h, cell = g["width"], g["height"], g["cell_mm"]
    if d["tool"] == "colour":
        px = np.asarray(rgba, dtype=np.uint8).reshape(h, w, 4)
        sx, sy = map(math.floor, d["seed"])
        out = np.zeros((h, w), np.uint8)
        if not 0 <= sx < w or not 0 <= sy < h:
            return out
        near = np.max(np.abs(px.astype(np.int16) - px[sy, sx].astype(np.int16)), axis=2) <= d.get("tolerance", 18)
        if d.get("contiguous", True):
            todo = deque([(sx, sy)])
            out[sy, sx] = 1
            while todo:
                x, y = todo.popleft()
                for xx, yy in ((x-1,y), (x+1,y), (x,y-1), (x,y+1)):
                    if 0 <= xx < w and 0 <= yy < h and near[yy, xx] and not out[yy, xx]:
                        out[yy, xx] = 1
                        todo.append((xx, yy))
            return out
        return near.astype(np.uint8)
    x = q(g["left_mm"] + (np.arange(w)[None, :] + .5)*cell)
    y = q(g["top_mm"] + (np.arange(h)[:, None] + .5)*cell)
    if d["tool"] == "rectangle":
        a, b = d["a"], d["b"]
        out = (x >= min(a[0],b[0])) & (x < max(a[0],b[0])) & (y >= min(a[1],b[1])) & (y < max(a[1],b[1]))
    elif d["tool"] == "lasso":
        out = polygon(x, y, d["points"])
    elif d["tool"] in ("ring", "sector"):
        r = q(np.hypot(x, y))
        out = (r >= d.get("inner", 0)) & (r < d.get("outer", 60))
        if d["tool"] == "sector" and abs(d["end"]-d["start"]) < 360:
            out &= q((np.degrees(np.arctan2(y,x))-d["start"]) % 360) < q((d["end"]-d["start"]) % 360)
    else:
        raise ValueError("unknown selection tool")
    return out.astype(np.uint8)


def migrate(data):
    d = copy.deepcopy(data)
    if not isinstance(d, dict) or not isinstance(d.get("layers"), list) or d.get("version", 1) not in (1, 2):
        raise ValueError("unsupported editor document")
    d.update(format="disc-probe design", version=2)
    for k, v in dict(selections=[], assignments=[], maskGrid=grid(), cell=.02,
                     annulus_mm=[26,58] if d.get("media")=="cd" else [24,58],
                     materials=[dict(id="background",spec="B9",rgb=[205,200,190]),dict(id="dark",spec="A5",rgb=[40,40,40])]).items():
        d.setdefault(k, v)
    for i, l in enumerate(d["layers"]):
        for k,v in dict(id=i+1,visible=True,locked=False,opacity=1,x=0,y=0,width=80,rot=0,
                        sourceKind="bitmap" if l.get("kind")=="image" else l.get("kind")).items():
            l.setdefault(k,v)
        if l.get("kind")=="fx":
            l.setdefault("shape",dict(type="rectangle"))
            ident=f'legacy-fx-{l["id"]}'
            if not any(a.get("id")==ident for a in d["assignments"]):
                d["assignments"].append(dict(id=ident,layer=l["id"],effect=dict(kind=l["fxKind"],y1=l.get("y1",55),y2=l.get("y2",100))))
        if not l.get("raster") and not l.get("shape") and l.get("picture"):
            from PIL import Image
            im = Image.open(io.BytesIO(base64.b64decode(l["picture"].split(",",1)[1]))).convert("RGBA")
            l["raster"] = dict(width=im.width,height=im.height,rgba=base64.b64encode(im.tobytes()).decode())
            l.update(w=im.width,h=im.height)
    return d


def validate(d):
    if len(d["layers"]) > 16 or not 1 <= len(d["materials"]) <= 256:
        raise ValueError("at most 16 layers and 256 materials")
    ids = [m["id"] for m in d["materials"]]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate material id")
    ann=d["annulus_mm"]
    if len(ann)!=2 or any(type(n) not in (int,float) or not math.isfinite(n) for n in ann) or not 0<=ann[0]<ann[1]<=60:
        raise ValueError("invalid writable annulus")
    if len(d["selections"])>256 or len(d["assignments"])>1024:
        raise ValueError("at most 256 selections and 1024 assignments")
    for m in d["materials"]:
        spec = m["spec"]
        if not isinstance(spec,str) or (spec != "RND" and (
                not 2 <= len(spec) <= 256 or len(spec)%2 or any(c not in "0123456789abcdefABCDEF" for c in spec))):
            raise ValueError("material must be a supported hex byte texture")
    for l in d["layers"]:
        if any(type(l[k]) not in (int,float) or not math.isfinite(l[k]) for k in ("x","y","width","rot","opacity")) or not 0 < l["width"] <= 240 or not 0 <= l["opacity"] <= 1:
            raise ValueError("invalid layer transform")
        if "height" in l and (type(l["height"]) not in (int,float) or not math.isfinite(l["height"]) or not 0<l["height"]<=240):
            raise ValueError("invalid layer height")
        if "shape" in l and l["shape"]["type"] not in ("rectangle","ellipse","polygon","line","stroke"):
            raise ValueError("unknown shape")
        if "raster" in l:
            r=l["raster"]
            if not 0 < r["width"]*r["height"] <= 36_000_000 or len(base64.b64decode(r["rgba"],validate=True)) != r["width"]*r["height"]*4:
                raise ValueError("raster dimensions")
        if "tone" in l:
            editor_tone.tone(l["tone"])
        if l.get("sourceKind")=="svg" and not l.get("raster"):
            raise ValueError("SVG requires the page raster fallback beside the original")
        if not l.get("raster") and not l.get("shape"):
            raise ValueError("layer needs an RGBA raster or shape; use image --design for old path-based edit documents")
        if "gridPng" in l:
            from .template_grid import PNG_DATA_PREFIX, PNG_LIMIT
            png = l["gridPng"]
            if (l.get("kind") != "image" or not l.get("raster") or l.get("shape") or
                    not isinstance(png, str) or not png.startswith(PNG_DATA_PREFIX) or
                    len(png) > len(PNG_DATA_PREFIX) + 4 * ((PNG_LIMIT + 2) // 3)):
                raise ValueError("invalid native template layer")
    g=d["maskGrid"]
    if not 1 <= g["width"] <= 2400 or not 1 <= g["height"] <= 2400 or g["cell_mm"] <= 0:
        raise ValueError("mask grid")
    for s in d["selections"]:
        raw=base64.b64decode(s["bits"],validate=True)
        if len(raw)!=g["width"]*g["height"] or any(v>1 for v in raw):
            raise ValueError("mask bits")
    layer_ids=[l["id"] for l in d["layers"]];mask_ids=[s["id"] for s in d["selections"]]
    pictures = {l['id'] for l in d['layers'] if l.get('kind') == 'image' and l.get('raster') and not l.get('shape')}
    if len(set(layer_ids))!=len(layer_ids) or len(set(mask_ids))!=len(mask_ids):
        raise ValueError("duplicate layer or selection id")
    for a in d["assignments"]:
        if ("layer" in a)==("selection" in a) or ("layer" in a and a["layer"] not in layer_ids) or ("selection" in a and a["selection"] not in mask_ids):
            raise ValueError("unknown assignment target")
        if sum(k in a for k in ("material","pattern","effect","colour"))!=1:
            raise ValueError("choose material, pattern, effect or colour")
        if "material" in a and a["material"] not in ids:
            raise ValueError("unknown material")
        if "pattern" in a:
            editor_pattern.validate({**a["pattern"],"materials":[ids.index(k) for k in a["pattern"]["materials"]]})
        if "effect" in a:
            e=a["effect"]
            if e["kind"] not in ("flow","ox","merge","sync") or any(type(e.get(k,55)) not in (int,float) or not math.isfinite(e.get(k,55)) or not 0<=e.get(k,55)<=150 for k in ("y1","y2")):
                raise ValueError("invalid effect")
        if 'colour' in a:
            from .editor_colour import work_rig
            if d.get('media', 'dvd') != 'dvd' or a.get('layer') not in pictures:
                raise ValueError('colour fill requires a DVD picture layer')
            c = a['colour']
            if not isinstance(c, dict) or c.get('dither') not in ('ordered', 'nearest'):
                raise ValueError('colour fill needs ordered or nearest dithering')
            if c.get('mapping', 'perceptual') not in ('perceptual', 'vivid'):
                raise ValueError('colour mapping must be perceptual or vivid')
            candidates = c.get('materials')
            if (not isinstance(candidates, list) or not candidates or any(k not in ids for k in candidates)
                    or len(candidates) != len(set(candidates))):
                raise ValueError('colour fill needs distinct known material IDs')
            work_rig(d)
    return d


def shape_hit(s,u,v):
    if s["type"]=="rectangle": return (np.abs(u)<.5)&(np.abs(v)<.5)
    if s["type"]=="ellipse": return u*u+v*v<.25
    if s["type"]=="polygon": return polygon(u,v,s["points"])
    out=np.zeros(np.broadcast(u,v).shape,bool)
    points=s.get("points",[[-.5,-.5],[.5,.5]])
    for (a,b),(c,d) in zip(points,points[1:]):
        dx,dy=c-a,d-b
        t=np.clip(((u-a)*dx+(v-b)*dy)/(dx*dx+dy*dy or 1),0,1)
        out|=(u-a-t*dx)**2+(v-b-t*dy)**2<(s.get("stroke",.03)/2)**2
    return out


def effect_pose(e,u,v,parity):
    a,b=e.get("y1",55),e.get("y2",100)
    if e["kind"]=="sync":return np.full(np.broadcast(u,v).shape,a)
    if e["kind"]=="flow":return a+(b-a)*(.5-v)
    if e["kind"]=="ox":
        w=3.5/20/2
        o=np.abs(np.hypot(u,v)-(.5-w))<=w
        x=(np.maximum(np.abs(u),np.abs(v))<=.5-w)&(np.minimum(np.abs(u-v),np.abs(u+v))/math.sqrt(2)<=w)
        return np.where(o&x,np.where(parity,a,b),np.where(o,a,np.where(x,b,np.nan)))
    if e["kind"]=="merge":
        x,y=u*5,v*5;r=np.sqrt(((x-1)**2+y*y)*((x+1)**2+y*y))
        return np.where(r>2.2,np.nan,a+(b-a)*r)
    raise ValueError("unknown effect")


def delta(x,y,phone):
    r=np.maximum(np.hypot(x,y),1e-9);v=0
    for px,py in ((0,-phone),(-43.66,-phone-19.79)):
        n=np.sqrt((px-x)**2+(py-y)**2+330**2)
        v+=(-(px-x)*y+(py-y)*x)/n/r
    return np.abs(v)


def _picture_values(px, materials, tone):
    slots = np.full(px.shape[:-1], -1, np.int16)
    # Only explicit template colours identify materials. The palette's swatches can share RGB.
    for k, rgb in materials:
        same = (slots < 0) & np.all(px[..., :3] == rgb, axis=-1)
        slots[same] = k
    lum = editor_tone.luminance(*(px[..., c].astype(np.int32) for c in range(3)))
    return slots, tone[lum]


@contextmanager
def _native_layers(document, scratch):
    colour_layers = {a['layer'] for a in document['assignments'] if 'colour' in a}
    with ExitStack() as stack:
        native = {}
        for l in document['layers']:
            if l.get("gridPng") and l["visible"]:
                from .template_grid import PNG_DATA_PREFIX, native_raster
                raw = base64.b64decode(l["gridPng"][len(PNG_DATA_PREFIX):], validate=True)
                native[l["id"]] = stack.enter_context(native_raster(raw, scratch, manage_icc=l['id'] in colour_layers))
                del raw
        yield native


def compose(data, g=None, out=None, *, colour_table=None, scratch=None):
    d = validate(migrate(data))
    with _native_layers(d, scratch) as native:
        return _compose(d, g, out, colour_table, native)


def _compose(d, g, out, colour_table, native):
    g=g or grid(round(120/d["cell"]))
    w,h=g["width"],g["height"]
    out=np.zeros((h,w),np.uint8) if out is None else out
    ids={m["id"]:i for i,m in enumerate(d["materials"])}
    layer_fills = {l['id']: [] for l in d['layers']}
    for a in d['assignments']:
        if 'layer' in a:
            fills = layer_fills[a['layer']]
            if 'colour' in a:
                fills.clear()  # Colour fully covers the layer wherever its alpha allows a write.
            fills.append(a)
    masks={s["id"]:np.frombuffer(base64.b64decode(s["bits"]),np.uint8).reshape(d["maskGrid"]["height"],-1) for s in d["selections"]}
    raster={l["id"]:np.frombuffer(base64.b64decode(l["raster"]["rgba"]),np.uint8).reshape(l["raster"]["height"],l["raster"]["width"],4) for l in d["layers"] if l.get("raster")}
    colour = {}
    coloured = [l for l in d['layers'] if l['visible'] and layer_fills[l['id']] and 'colour' in layer_fills[l['id']][0]]
    if coloured:
        from . import editor_colour, simulate, simulate_a3
        pose = editor_colour.work_rig(d)
        table = editor_colour.active_table(d) if colour_table is None else colour_table
        for l in coloured:
            c = layer_fills[l['id']][0]['colour']
            legacy = editor_colour.legacy_colour(c)
            layer_table = simulate_a3.tables() if legacy and table.get('fitted') else table
            vivid = c.get('mapping') == 'vivid'
            args = (d['materials'], [ids[k] for k in c['materials']], c['dither'], layer_table)
            if layer_table.get('fitted'):
                rgba = raster[l['id']]
                height = l.get('height', l['width'] * l.get('h',1)/l.get('w',1))
                matcher = editor_colour.AngleMatcher(*args, rgba, l['width'], height, vivid=vivid)
                codes = matcher.codes
            else:
                if vivid:
                    raise ValueError('vivid colour mapping requires a fitted colour table')
                matcher = editor_colour.Matcher(*args, relative=not legacy)
                codes = None
            colour[l['id']] = matcher, layer_table.get('delta_scale', 1.), codes
    dark=ids.get("dark",next((i for i,m in enumerate(d["materials"]) if m["spec"]=="A5"),1))
    # per picture: the template colour each pixel matches (-1: none) and its toned grey (editor_tone)
    source_slots={};greys={};tones={};diffusion={};tone_tables={}
    material_colours = [(k, m["rgb"]) for k, m in enumerate(d["materials"])
                        if "rgb" in m and m.get("template_name")]
    for l in d["layers"]:
        if l.get("raster") and l['id'] not in colour:
            ident = l["id"]
            tones[ident] = editor_tone.tone(l.get("tone"))
            tone_tables[ident] = np.asarray(editor_tone.table(tones[ident]), np.uint8)
            if ident not in native:
                source_slots[ident], greys[ident] = _picture_values(raster[ident], material_colours, tone_tables[ident])
            if tones[ident]["dither"]=="floyd-steinberg":
                diffusion[ident]=editor_tone.Diffusion(w,tones[ident]["strength"])
    columns=np.arange(w)
    def shade(a,x,y,u,v,j):
        if "pattern" in a:
            p={**a["pattern"],"materials":[ids[k] for k in a["pattern"]["materials"]]}
            return editor_pattern.render(p,{**g,"height":1,"top_mm":g["top_mm"]+j*g["cell_mm"],"annulus_mm":d["annulus_mm"]})[0].astype(int)
        if "effect" in a:
            pose=effect_pose(a["effect"],u,v,(np.arange(w)+j)%2)
            dt=delta(x,y,pose);wave=a["effect"].get("wavelength_um",.53)
            best=np.full(w,np.inf);slot=np.full(w,-1)
            for k,m in enumerate(d["materials"]):
                if m.get("period_um"):
                    err=np.abs(m["period_um"]*dt-wave);hit=err<best;best[hit]=err[hit];slot[hit]=k
            return slot
        return np.full(w,ids[a["material"]])
    x=q(g["left_mm"]+(np.arange(w)+.5)*g["cell_mm"])
    for j in range(h):
        y=float(q(g["top_mm"]+(j+.5)*g["cell_mm"]))
        row=out[j];row[:]=0
        r=q(np.hypot(x,y));writable=(r>=d['annulus_mm'][0])&(r<d['annulus_mm'][1])
        dt = None
        for l in d["layers"]:
            if not l["visible"]:continue
            r=l.get("raster");s=l.get("shape")
            if not r and not s:continue
            a=math.radians(l["rot"]);dx,dy=x-l["x"],y-l["y"]
            u=q((dx*math.cos(a)+dy*math.sin(a))/l["width"])
            v=q((-dx*math.sin(a)+dy*math.cos(a))/l.get("height",l["width"]*l.get("h",1)/l.get("w",1)))
            if r:
                sx=np.floor((u+.5)*r["width"]).astype(int);sy=np.floor((v+.5)*r["height"]).astype(int)
                cy,cx=np.clip(sy,0,r["height"]-1),np.clip(sx,0,r["width"]-1)
                inside=(sx>=0)&(sy>=0)&(sx<r["width"])&(sy<r["height"])
                exact = native.get(l["id"])
                if exact is None:
                    px=raster[l["id"]][cy,cx]
                else:
                    px = exact.row(np.floor((u + .5) * exact.side).astype(int),
                                   np.floor((v + .5) * exact.side).astype(int))
                    if l["id"] not in diffusion and not px[:, 3].any():
                        continue
                hit=inside&(px[:,3]*l["opacity"]>255*(COVERAGE[j%4,columns%4]+.5)/16)
                if l['id'] in colour:
                    hit &= writable
                    if not hit.any():
                        continue
                    if dt is None:
                        # Composition rows run down the canvas; the optical frame runs toward 12 o'clock.
                        dt = simulate.along_track(x, -y, **pose)
                    slots = np.full(w, -1, dtype=int)
                    matcher, scale, codes = colour[l['id']]
                    target = codes[cy[hit],cx[hit]] if codes is not None else editor_colour.picture_lab(px[hit,:3])
                    slots[hit] = matcher.row(dt[hit] * scale, target, j, columns[hit])
                else:
                    if exact is None:
                        slots = source_slots[l["id"]][cy,cx]
                        grey = greys[l["id"]][cy,cx]
                    else:
                        slots, grey = _picture_values(px, material_colours, tone_tables[l["id"]])
                    slots = slots.astype(int)
                    # the rest of the picture: its toned grey, dithered on this grid
                    take=inside&(px[:,3]>0)&(slots<0)
                    grey=grey.astype(np.int32);t=tones[l["id"]]
                    if l["id"] in diffusion:
                        dark_cells=diffusion[l["id"]].row(j,grey,take)
                    else:
                        dark_cells=editor_tone.matrix_dark(t["dither"],t["strength"],j,columns,grey)&take
                    slots=np.where(slots>=0,slots,np.where(dark_cells,dark,0))
            else:
                hit=shape_hit(s,u,v)&(255*l["opacity"]>255*(COVERAGE[j%4,np.arange(w)%4]+.5)/16);slots=np.full(w,dark)
            for a in layer_fills[l['id']]:
                if 'colour' not in a:
                    z=shade(a,x,y,u,v,j);slots=np.where(z>=0,z,slots)
            hit &= slots >= 0  # A fitted colour with no table support leaves the underlying cells alone.
            row[hit]=slots[hit]
        for a in d["assignments"]:
            if a.get("selection"):
                mg=d["maskGrid"];sx=np.floor((x-mg["left_mm"])/mg["cell_mm"]).astype(int);sy=math.floor((y-mg["top_mm"])/mg["cell_mm"])
                if not 0<=sy<mg["height"]:continue
                hit=(sx>=0)&(sx<mg["width"])&(masks[a["selection"]][sy,np.clip(sx,0,mg["width"]-1)]!=0)
                z=shade(a,x,y,x/120,np.full(w,y/120),j);hit&=z>=0;row[hit]=z[hit]
        row[~writable]=0
    return out


def compose_file(source, target, *, table_path=None):
    d=validate(migrate(json.loads(Path(source).read_text(encoding="utf-8-sig"))))
    if d["cell"] not in (.02,.01,.005):raise ValueError("choose 20, 10 or 5 um cells")
    table = None
    if table_path and any('colour' in a for a in d['assignments']):
        from .editor_colour import active_table
        table = active_table(d, table_path)
    n=round(120/d["cell"]);target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    with _native_layers(d, target.parent) as native:
        out=np.lib.format.open_memmap(target,mode="w+",dtype=np.uint8,shape=(n,n))
        _compose(d, None, out, table, native)
        out.flush()
    manifest=target.with_suffix(".textures.json")
    manifest.write_text(json.dumps(dict(textures=[m["spec"] for m in d["materials"]],document_version=2),indent=2),encoding="utf8")
    return d
