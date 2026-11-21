"""Solve a DVD picture for two or three disc tilts, or rebuild a saved role card."""
from __future__ import annotations

import contextlib
import csv
import json
import math
from pathlib import Path
import sys

import numpy as np

from . import editor_colour, editor_ops, imagedisc, simulate, texlib
from .i18n import tr

GRID = 2000
RECORD_GRID = 6000
ANGLE_WINDOWS = (-1., -.5, 0., .5, 1.)
MAX_MATERIALS = 150
GATE_KEYS = ('worst_eight_sector_F512_percent', 'worst_eight_sector_lean', 'max_abs_frame_end_DSV')
ARROW = 'MIX:' + ','.join(f'{byte:02X}' for byte in range(256) if byte != 0x92)
ASSETS = Path(__file__).with_name('grating_card')
DEFAULT_LOOKUP = ASSETS / 'delta-lookup.npz'
DEFAULT_INDEX = ASSETS / 'angle-curves-index.csv'
DEFAULT_CHECKS = ASSETS / 'channel-checks.json'


def add_parser(sub):
    command = sub.add_parser('gratingcard', help='make a DVD picture that changes when the disc is tilted')
    command.add_argument('images', nargs='*', help='two or three pictures, one per target angle')
    command.add_argument('--angles', nargs='+', type=float, required=True, help='target angles in degrees, in picture order')
    command.add_argument('--titles', nargs='+', help='names to show at each angle (default: picture names)')
    command.add_argument('--axis', choices=('x', 'y'), default='x', help='tilt axis through the disc centre (default: x)')
    command.add_argument('--geo', required=True, help='measured DVD geometry JSON or run folder')
    command.add_argument('--lookup', type=Path, help='override the bundled role card response table with an NPZ file')
    command.add_argument('--index', type=Path, help='eligible texture CSV (default: angle-curves-index.csv beside lookup)')
    command.add_argument('--channel-checks', type=Path, help='channel results from the original channel gate')
    command.add_argument('--camera', nargs=3, type=float, metavar=('X', 'Y', 'Z'), help='lens position in disc mm (default: lookup)')
    command.add_argument('--flash', nargs=3, type=float, metavar=('X', 'Y', 'Z'), help='flash position in disc mm (default: lookup)')
    command.add_argument('--centre', nargs=2, type=float, metavar=('X', 'Y'), default=(39., 0.),
                         help='picture centre on the data side in mm (default: 39 0)')
    command.add_argument('--width', type=float, default=24., help='picture box width in mm (default: 24)')
    command.add_argument('--r-max', type=float, default=54., help='outer image radius in mm (default: 54)')
    command.add_argument('--output', type=Path, default=Path('iso/grating-card.iso'), help='output ISO path')
    command.add_argument('--replay', type=Path, help='rebuild an archived weights NPZ or editor work JSON')
    command.add_argument('--json', action='store_true', help='print the result as JSON')
    command.set_defaults(func=run)
    return command


def read_json(path):
    return json.loads(texlib.safe(path).read_text(encoding='utf-8-sig'))


def gate_passed(row):
    if not isinstance(row, dict) or row.get('passed') is not True:
        return False
    f512, lean, dsv = (row.get(name, row.get(short)) for name, short in zip(GATE_KEYS, ('F512', 'lean', 'dsv')))
    return (all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in (f512, lean, dsv))
            and f512 < 1.5 and lean <= .15 and dsv <= 100)


def checked_textures(results):
    if not isinstance(results, dict):
        raise ValueError(tr('The channel report must index results by texture.'))
    passed = set()
    for spec, row in results.items():
        try:
            allowed = bool(spec) and 0x92 not in bytes.fromhex(spec)
        except ValueError:
            allowed = False
        if allowed and gate_passed(row):
            passed.add(spec)
    return passed


def arrow_channel():
    """Apply the archive's MIX-A channel tests to the random orientation-arrow bytes."""
    from . import dvd, efmplus, simulate_spectrum

    worst = {name:0. for name in GATE_KEYS}
    for index,lba in enumerate((32000,512016,1056032,1784064)):
        lbas = np.arange(lba,lba+16)
        pure = imagedisc.texture_bytes(ARROW,lbas)
        rng = np.random.default_rng(20261119+index)
        patterned = rng.integers(0,255,size=pure.shape,dtype=np.uint8)
        patterned[patterned >= 0x92] += 1
        start = (0,3,5,8)[index]
        patterned[start:start+8] = pure[start:start+8]
        for recorded in (pure,patterned):
            user = (recorded ^ dvd.MASKS[dvd.preset_index(lba)]).ravel()
            rows = simulate_spectrum.recording_rows(user,lba)
            for boundary in (efmplus.Boundary(1,0,True),efmplus.Boundary(2,60,False),
                             efmplus.Boundary(3,-60,True),efmplus.Boundary(4,30,False)):
                levels, _ = efmplus.encode_rows(rows,boundary)
                signed = 2*levels.astype(np.int32)-1
                level = np.r_[boundary.dsv,boundary.dsv+np.cumsum(signed)]
                frame_ends = np.abs(level[1488::1488])
                long_windows = np.abs(level[512:]-level[:-512]) > 64
                frame_lean = np.abs(signed.reshape(-1,1488)[:,32:].mean(axis=1))
                sector = 1488*26
                metrics = (
                    100*max(long_windows[i*sector:(i+8)*sector-511].mean() for i in range(9)),
                    max(frame_lean[i*26:(i+8)*26].mean() for i in range(9)),
                    frame_ends.max(),
                )
                for key,value in zip(GATE_KEYS,metrics):
                    worst[key] = max(worst[key],float(value))
    return dict(passed=True,**worst)


def coordinates(vector, axis, angle):
    """Rotate the lamp and lens inversely into the tilted disc's data-side frame."""
    x, y, z = vector
    angle = math.radians(angle)
    c, s = math.cos(angle), math.sin(angle)
    if axis == 'x':
        return x, c*y+s*z, -s*y+c*z
    return c*x-s*z, y, s*x+c*z


class Lookup:
    def __init__(self, path, index, checked):
        with texlib.safe(index).open(encoding='utf-8-sig', newline='') as stream:
            eligible = {row['spec'] for row in csv.DictReader(stream)}
        approved = eligible & checked
        with np.load(texlib.safe(path), allow_pickle=False) as table:
            use = [i for i, spec in enumerate(table['spec']) if spec in approved]
            self.specs = table['spec'][use].tolist()
            curves = table['xyz_order']
            self.grid = table['delta']
            self.scale = float(table['scale'])
            self.camera, self.flash = table['camera'], table['flash']
            self.annulus, self.white, self.background = table['annulus'], table['paper_white'], table['background']
            if not self.specs or len(self.specs) != len(set(self.specs)):
                raise ValueError(tr('No distinct eligible textures passed the channel gate.'))
            if (self.grid.ndim != 1 or len(self.grid) < 2 or not np.isfinite(self.grid).all()
                    or not np.all(np.diff(self.grid) > 0) or not .5 <= self.scale <= 1.5
                    or curves.shape != (len(table['spec']), len(self.grid), 4, 3)):
                raise ValueError(tr('Invalid role card response table.'))
            self.xyz = curves[use].sum(axis=2)
            for vector in (self.camera, self.flash, self.white, self.background):
                if vector.shape != (3,) or not np.isfinite(vector).all():
                    raise ValueError(tr('Invalid role card response table.'))
            if (self.annulus.shape != (2,) or not 0 < self.annulus[0] < self.annulus[1] <= 58
                    or (self.white <= 0).any() or (self.background < 0).any()
                    or not np.isfinite(self.xyz).all() or (self.xyz < 0).any()):
                raise ValueError(tr('Invalid role card response table.'))

    def response(self, delta):
        if np.any(delta < self.grid[0]) or np.any(delta > self.grid[-1]):
            raise ValueError(tr('An angle leaves the range of the texture response table.'))
        hi = np.searchsorted(self.grid, delta, side='right').clip(1, len(self.grid)-1)
        weight = ((delta-self.grid[hi-1])/(self.grid[hi]-self.grid[hi-1])).astype(np.float32)
        return self.xyz[:, hi-1]*(1-weight[..., None]) + self.xyz[:, hi]*weight[..., None]


def source_pixels(paths, width):
    """Fit each source to a common centred box, retaining its aspect and opacity."""
    from PIL import Image, ImageOps

    images = []
    for path in paths:
        with Image.open(texlib.safe(path)) as original:
            picture = ImageOps.exif_transpose(original).convert('RGBA')
            scale = min(width/picture.width, GRID/picture.height)
            new_size = tuple(max(1,round(size*scale)) for size in picture.size)
            picture = picture.resize(new_size,Image.Resampling.LANCZOS)
            images.append(picture)
    height = max(image.height for image in images)
    frames, coverage = [], []
    for im in images:
        canvas = Image.new('RGBA', (width,height))
        canvas.paste(im, ((width-im.width)//2,(height-im.height)//2))
        pixels = np.asarray(canvas)
        opacity = pixels[...,3:4].astype(np.float32)/255
        rgb = np.asarray(pixels[...,:3]*opacity, dtype=np.uint8)
        frames.append(Image.fromarray(rgb).quantize(24, dither=Image.Dither.NONE))
        coverage.append(opacity[...,0] >= .5)
    return frames, np.any(coverage, axis=0)


def position(images, centre, width):
    pitch = 120 / GRID
    width_px = round(width/pitch)
    frames, coverage = source_pixels(images, width_px)
    height_px = coverage.shape[0]
    x0 = round((60+centre[0])/pitch-width_px/2)
    y0 = round((60-centre[1])/pitch-height_px/2)
    if x0 < 0 or y0 < 0 or x0+width_px > GRID or y0+height_px > GRID:
        raise ValueError(tr('Place the pictures inside the disc.'))
    x, y = np.meshgrid((x0+np.arange(width_px)+.5)*pitch-60, 60-(y0+np.arange(height_px)+.5)*pitch)
    return frames, coverage, x, y, x0, y0


def illumination(x, y, camera, flash, axis, angles, scale):
    delta, irradiance = [], []
    for angle in angles:
        c, f = coordinates(camera,axis,angle), coordinates(flash,axis,angle)
        if c[2] <= 0 or f[2] <= 0:
            raise ValueError(tr('The lens and flash must stay above the tilted disc.'))
        delta.append(simulate.along_track(x, y, c, f)*scale)
        irradiance.append(np.dot(flash,flash)/((f[0]-x)**2+(f[1]-y)**2+f[2]**2))
    return np.stack(delta,axis=-1), np.stack(irradiance,axis=-1)


def target_mixes(table, delta, irradiance, colours):
    """Fit common recording area shares to all views using constrained nonnegative least squares."""
    from scipy.optimize import nnls

    xyz = table.response(delta) * irradiance[None,...,None]
    # White is a brightness both poses can approach. Average opposing colour channels
    # independently of luminance, as in the original joint colour fit.
    white_y = max(float(np.min(np.quantile(xyz[...,1],.98,axis=0))),1e-6)
    if len(table.specs) == 1:
        return np.ones((len(colours),1),np.float32)
    opponent = np.array([[0,1,0], [2,-2,0], [0,.8,-.8]])
    basis = (xyz / table.white) @ opponent.T / white_y
    bg = ((table.background / table.white) @ opponent.T / white_y) * irradiance[:,None]
    target = colours @ editor_colour.SRGB_XYZ.T / editor_colour.WHITE @ opponent.T - bg
    # Include the angular window in the solve at a lower weight than the target pose.
    weights = np.tile([.2,.35,1.,.35,.2],len(colours[0])//len(ANGLE_WINDOWS))[...,None]
    basis = (basis*weights).reshape(len(table.specs),-1)
    target = (target*weights).reshape(len(colours),-1)
    out = np.zeros((len(colours),len(table.specs)),np.float32)
    for i, desired in enumerate(target):
        error = np.square(basis-desired).sum(axis=1)
        shortlist = np.argsort(error,kind='stable')[:24]
        matrix = np.vstack((basis[shortlist].T,np.full(len(shortlist),30.)))
        mix, _ = nnls(matrix,np.r_[desired,30.],maxiter=2000)
        mix[mix < .01] = 0
        if not mix.any():
            mix[0] = 1.
        out[i,shortlist] = mix / mix.sum()
    return out


def solve(table, images, angles, axis, camera, flash, annulus, centre, width):
    frames, coverage, x, y, x0, y0 = position(images,centre,width)
    active = coverage & (np.hypot(x,y) >= annulus[0]) & (np.hypot(x,y) < annulus[1])
    if not active.any():
        raise ValueError(tr('No picture overlaps the writable ring.'))
    poses = [angle+offset for angle in angles for offset in ANGLE_WINDOWS]
    delta, light = illumination(x[active],y[active],camera,flash,axis,poses,table.scale)
    # Bucket by the full δ path, so images at different physical angles stay coupled.
    bins = np.rint(delta/.01).astype(np.int16)
    _, groups = np.unique(bins,axis=0,return_inverse=True)
    order = np.argsort(groups,kind='stable')
    boundaries = np.r_[0,np.flatnonzero(np.diff(groups[order]))+1,len(order)]
    codes = np.stack([np.asarray(im)[active] for im in frames],axis=1)
    palettes = np.zeros((len(frames),24,3),np.float32)
    for i, image in enumerate(frames):
        palette = np.asarray(image.getpalette()[:72]).reshape(-1,3)
        palettes[i,:len(palette)] = editor_colour.LINEAR[palette]
    pix = np.full(active.sum(),-1,np.int32)
    solutions, counts, first = [], [], 0
    for left,right in zip(boundaries,boundaries[1:]):
        cells = order[left:right]
        paths = delta[cells].mean(axis=0)
        if np.any(paths > table.grid[-1]) or np.any(paths < table.grid[0]):
            continue
        pairs, keys, frequency = np.unique(codes[cells],axis=0,return_inverse=True,return_counts=True)
        colours = palettes[np.arange(len(frames))[None,:],pairs]
        colours = np.repeat(colours,len(ANGLE_WINDOWS),axis=1)
        pix[cells] = keys + first
        first += len(pairs)
        solutions.append(target_mixes(table,paths,light[cells].mean(axis=0),colours))
        counts.extend(frequency)
    if not solutions:
        raise ValueError(tr('No cells have a table response at all target angles.'))
    weights = np.concatenate(solutions)
    usage = np.asarray(counts) @ weights
    palette = np.argsort(-usage,kind='stable')[:MAX_MATERIALS]
    palette = palette[usage[palette] > 0]
    # One background is common to all angles, as in the original cards.
    probes = delta[::max(1,len(delta)//64)].clip(table.grid[0],table.grid[-1])
    dark = int(np.argmin(table.response(probes)[...,1].mean(axis=(1,2))))
    names = [table.specs[dark], *(table.specs[i] for i in palette if i != dark)]
    use = [dark, *(int(i) for i in palette if i != dark)]
    used = weights[:,use]
    used[:,0] += np.maximum(1.-used.sum(axis=1),0)
    grid = np.full((GRID, GRID),-1,np.int32)
    grid[y0:y0+active.shape[0],x0:x0+active.shape[1]][active] = pix
    return grid, used, names


def dither(pixels, weights, names, background):
    """Compile the original 0.06 mm weight grid onto the 20 µm Bayer grid."""
    if (pixels.shape != (GRID,GRID) or pixels.dtype.kind not in 'iu' or weights.ndim != 2 or not len(weights)
            or not 1 <= len(names) <= 255 or weights.shape[1] != len(names)
            or not 0 <= background < len(names) or pixels.min() < -1 or pixels.max() >= len(weights)
            or not np.isfinite(weights).all() or (weights < 0).any()):
        raise ValueError(tr('Invalid archived grating weight grid.'))
    cdf = np.cumsum(weights,axis=1)
    if np.any(cdf[:,-1] <= 0):
        raise ValueError(tr('Invalid archived grating weight grid.'))
    cdf /= cdf[:,-1:]
    permutation = list(range(len(names)))
    permutation[0], permutation[background] = permutation[background], permutation[0]
    relabel = np.argsort(permutation).astype(np.uint8)
    labels = np.zeros((RECORD_GRID,RECORD_GRID),np.uint8)
    columns = np.arange(RECORD_GRID)
    for j in range(RECORD_GRID):
        solution = pixels[j//3,columns//3]
        hit = solution >= 0
        phase = editor_colour.BAYER[j%8,columns[hit]%8]
        selected = (phase[:,None] >= cdf[solution[hit],:-1]).sum(axis=1)
        labels[j,hit] = relabel[selected]
    return labels, [names[i] for i in permutation]


def add_arrow(labels, names, annulus):
    definition = read_json(editor_colour.DIRECTION_ARROW)
    xs, ys = np.array(definition['data_side_mm'],float).T
    dx, dy = xs.max()-xs.min(),ys.max()-ys.min()
    x0, y0 = (xs.min()+xs.max())/2, (ys.min()+ys.max())/2
    if ys.max() > annulus[1]-definition['rim_margin_mm'] or ys.min() < annulus[0]:
        raise ValueError(tr('The measured ring must contain the 12 o’clock arrow at 43.5–52.8 mm.'))
    grid = (np.arange(RECORD_GRID)+.5)*(120/RECORD_GRID)-60
    cols = np.flatnonzero(abs(grid-x0) <= dx/2)
    rows = np.flatnonzero(abs(-grid-y0) <= dy/2)
    u,v = np.meshgrid((grid[cols]-x0)/dx,(grid[rows]+y0)/dy)
    hit = editor_ops.shape_hit({'type':'polygon','points':np.column_stack(((xs-x0)/dx,(y0-ys)/dy)).tolist()},u,v)
    rr, cc = np.ix_(rows,cols)
    labels[rr,cc] = np.where(hit,np.uint8(len(names)),labels[rr,cc])
    names.append(ARROW)


def replay(path):
    if path.suffix.lower() == '.npz':
        with np.load(texlib.safe(path),allow_pickle=False) as grid:
            return dither(grid['pix_sol'],grid['W_tab'],grid['materials'].tolist(),int(grid['bg_slot']))
    document = editor_ops.validate(editor_ops.migrate(read_json(path)))
    if document['media'] != 'dvd' or document['cell'] != .02:
        raise ValueError(tr('A replay needs a DVD work on the 20 µm grid.'))
    return editor_ops.compose(document), [m['spec'] for m in document['materials']]


def describe(axis, angles, images, camera=None, flash=None):
    return dict(axis=axis, camera_mm=camera, flash_mm=flash,
                views=[dict(angle_deg=angle, picture=label) for angle,label in zip(angles,images,strict=True)])


def write_view(path, view):
    lines = ['# ' + tr('How to view the grating card'), '',
             tr('Face the data side. Keep the lens and flash fixed while tilting the disc through its centre.'),
             tr('Positive X tilt raises 12 o’clock. Positive Y tilt lowers 3 o’clock.'),
             tr('Use a dark room and a single small lamp or the phone flash.'), '',
             f"{tr('Tilt axis')} {view['axis'].upper()}"]
    if view['camera_mm'] is not None:
        for label,key in [('Lens','camera_mm'),('Flash','flash_mm')]:
            lines.append(f"{tr(label)} `{view[key]}` mm")
    lines.extend(f"- {item['angle_deg']:+g}°  {item['picture']}" for item in view['views'])
    lines += ['', tr('Angles are design estimates. Check the first disc under the specified light.')]
    path.write_text('\n'.join(lines)+'\n',encoding='utf-8')


def ensure_new(paths):
    if any(path.exists() for path in paths):
        raise ValueError(tr('Choose a new output path. A card file already exists.'))


def write_card(args, labels, specs, output, image_args, view):
    from .__main__ import cmd_image
    from .image_output import exclusive

    labels_path, view_path = output.with_suffix('.labels.npy'), output.with_suffix('.view.md')
    manifest_path = labels_path.with_suffix('.textures.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    with exclusive(labels_path):
        ensure_new((output,labels_path,manifest_path,view_path))
        np.save(labels_path,labels)
        manifest_path.write_text(json.dumps(dict(textures=specs,background=specs[0]),indent=2)+'\n',encoding='utf-8')
        image_args.design_npy = str(labels_path)
        image_args.textures = specs
        # Retain the normal image writer and verification. Omit its desktop burn advice.
        with contextlib.redirect_stdout(sys.stderr) if args.json else contextlib.nullcontext():
            cmd_image(image_args,show_next=False)
        write_view(view_path,view)
    return dict(iso=str(output), labels=str(labels_path), textures=str(manifest_path),
                preview=str(output.with_suffix('.preview.png')), verified=True,
                viewing_guide=str(view_path), replay=bool(args.replay), **view)


def run(args):
    from .__main__ import _build_parser, _geo_fit, _require_fit_media

    try:
        if (len(args.angles) not in (2,3) or len(set(args.angles)) != len(args.angles)
                or not all(math.isfinite(a) and abs(a) <= 15 for a in args.angles)):
            raise ValueError(tr('Choose two or three distinct target angles between −15° and +15°.'))
        if (not math.isfinite(args.r_max) or not 25. <= args.r_max <= 58.
                or not math.isfinite(args.width) or not .12 <= args.width <= 116.
                or not all(math.isfinite(v) for v in args.centre)):
            raise ValueError(tr('Invalid card dimensions.'))
        if args.geo.lower() in ('latest','pick'):
            raise ValueError(tr('Give the path to a DVD geometry JSON or run folder.'))
        if (args.replay and args.images) or (not args.replay and len(args.images) != len(args.angles)):
            raise ValueError(tr('Give one picture per angle, or supply an archived input with --replay.'))
        if args.titles and len(args.titles) != len(args.angles):
            raise ValueError(tr('Give one title per angle.'))
        if bool(args.camera) != bool(args.flash):
            raise ValueError(tr('Give both lens and flash positions to override the table pose.'))
        if any(not math.isfinite(v) for v in (args.camera or [])+(args.flash or [])):
            raise ValueError(tr('Lens and flash coordinates must be finite.'))
        if (args.lookup or args.replay) and args.channel_checks is None:
            raise ValueError(tr('Custom lookup and replay inputs need their original channel report.'))
        output = texlib.safe(args.output)
        if output.suffix.lower() != '.iso':
            raise ValueError(tr('The output path must end in .iso.'))
        ensure_new((output,output.with_suffix('.labels.npy'),output.with_suffix('.labels.textures.json'),
                    output.with_suffix('.view.md')))
        parser = _build_parser()[0]
        image_args = parser.parse_args(['image','--geo',args.geo,'--no-photo-l',
                                       '--r-max',str(args.r_max),'--output',str(output)])
        fit = _geo_fit(image_args,'dvd')
        _require_fit_media(image_args,fit)
        checked = checked_textures(read_json(args.channel_checks or DEFAULT_CHECKS))
        cam, flash = args.camera, args.flash
        if args.replay:
            labels, specs = replay(args.replay)
            labels_for_views = [tr('Archived view') + f' {i+1}' for i in range(len(args.angles))]
        else:
            lookup = args.lookup or DEFAULT_LOOKUP
            index = args.index or lookup.with_name(DEFAULT_INDEX.name)
            table = Lookup(lookup,index,checked)
            cam = cam or table.camera.tolist()
            flash = flash or table.flash.tolist()
            annulus = (float(table.annulus[0]),min(float(table.annulus[1]),args.r_max))
            pixels, weights, specs = solve(table,args.images,args.angles,args.axis,cam,flash,annulus,args.centre,args.width)
            labels, specs = dither(pixels,weights,specs,0)
            labels_for_views = [Path(name).stem for name in args.images]
        if missing := set(specs)-checked:
            raise ValueError(tr('Missing passing channel evidence for texture:') + ' ' + sorted(missing)[0])
        if not args.replay:
            add_arrow(labels,specs,annulus)
            if not gate_passed(arrow_channel()):
                raise ValueError(tr('The random orientation arrow did not pass the channel gate.'))
        view = describe(args.axis,args.angles,args.titles or labels_for_views,cam,flash)
        result = write_card(args,labels,specs,output,image_args,view)
    except (OSError,ValueError,TypeError,KeyError) as exc:
        sys.exit(str(exc))
    if args.json:
        print(json.dumps(result,ensure_ascii=False))
    else:
        print(tr('Viewing guide:') + ' ' + result['viewing_guide'])
