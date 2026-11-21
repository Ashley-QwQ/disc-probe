"""Reproduce the colour audit without a drive. Run from the repository root."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageOps

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from discprobe import editor_colour as C, editor_ops as E, simulate, simulate_a3


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def source():
    image = np.full((96, 96, 3), 255, np.uint8)
    image[:32] = [(239,34,43)] * 32 + [(22,190,69)] * 32 + [(19,56,244)] * 32
    image[32:64] = [(250,239,6)] * 32 + [(240,8,230)] * 32 + [(9,225,240)] * 32
    image[64:] = np.linspace(0, 255, 96, dtype=np.uint8)[None, :, None]
    image[66:73, 4:12] = 250  # asymmetric orientation mark
    return image


def serve(root):
    import scipy.ndimage  # load the native libraries on the main thread
    from discprobe import webui

    os.environ['DISC_PROBE_NO_DRIVES'] = '1'
    os.environ['DISCPROBE_WORKERS'] = '2'
    os.environ['PYTHONPATH'] = str(REPO)
    Image.fromarray(source()).save(root / 'source.png')
    geo = 'geo-SIM-colour-audit.json'
    dump(root / geo, {'fit': {'u': 180518.44062237992, 'v': 5.591208641983095,
                            'bit_nm_assumed': 133.3, 'measured_span_mm': [24, 58]}})
    server = webui.Server(webui.Backend(root, drive_provider=lambda: []), 0)
    print(json.dumps({'port': server.server_port, 'geo': geo}), flush=True)

    def shutdown():
        sys.stdin.read()
        server.shutdown()
    threading.Thread(target=shutdown, daemon=True).start()
    with server:
        server.serve_forever()


def cli(root, *args):
    env = {**os.environ, 'PYTHONPATH': str(REPO), 'DISC_PROBE_NO_DRIVES': '1',
           'DISCPROBE_WORKERS': '2'}
    summary = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-m', 'discprobe',
                              '--lang', 'en', *map(str, args)], cwd=root, env=env,
                             capture_output=True, text=True, encoding='utf-8')
    (root / (args[0] + '.log')).write_text(summary.stdout + summary.stderr, encoding='utf-8')
    summary.check_returncode()


def hash_iso(path):
    """Compare all bytes, with a separate hash zeroing only ISO 9660 timestamps."""
    full, comparable = hashlib.sha256(), hashlib.sha256()
    with path.open('rb') as stream:
        header = bytearray(stream.read(21 * 2048))
        assert header[16*2048+1:16*2048+6] == b'CD001'
        full.update(header)
        for sector, offset, count in [(16, 813, 34), (16, 174, 7), (20, 18, 7), (20, 52, 7)]:
            start = sector * 2048 + offset
            header[start:start+count] = bytes(count)
        comparable.update(header)
        while data := stream.read(4 * 1024**2):
            full.update(data)
            comparable.update(data)
    return dict(bytes=path.stat().st_size, raw=full.hexdigest(), without_dates=comparable.hexdigest())


def parity(root):
    evidence = json.loads((root / 'web.json').read_text(encoding='utf-8'))
    compose, image = evidence['http']
    web = compose['response']
    args = image['request']['args']
    cli(root, 'colour-design', 'source.png', '--phone', 'iphone17pro', '--height', 22.3, '-o', 'cli.json')
    web_doc = E.validate(json.loads((root / web['work']).read_text(encoding='utf-8')))
    raw_doc = json.loads((root / 'cli.json').read_text(encoding='utf-8'))
    raw_layer, web_layer = raw_doc['layers'][0], web_doc['layers'][0]
    same_rgba = raw_layer['raster'] == web_layer['raster']
    assert same_rgba
    baseline = E.compose(raw_doc, E.grid(600))
    placement = {key:web_layer[key] for key in ('x', 'y', 'width', 'height', 'rot')}
    raw_layer.update(placement)
    raw_doc['annulus_mm'] = web_doc['annulus_mm']
    placed = E.compose(raw_doc, E.grid(600))
    dump(root / 'cli-placed.json', raw_doc)
    cli(root, 'compose', web['work'], '--out', 'web-via-cli.npy')
    assert hashlib.sha256((root / web['design_npy']).read_bytes()).digest() == hashlib.sha256(
        (root / 'web-via-cli.npy').read_bytes()).digest()
    cli(root, 'compose', 'cli-placed.json', '--out', 'cli.npy')
    cli_labels = np.load(root / 'cli.npy', mmap_mode='r')
    web_labels = np.load(root / web['design_npy'], mmap_mode='r')
    cli_textures = json.loads((root / 'cli.textures.json').read_text(encoding='utf-8'))['textures']
    combined = sorted(set(web['textures']) | set(cli_textures))
    index = {spec:i for i,spec in enumerate(combined)}
    cli_slots = np.array([index[spec] for spec in cli_textures], dtype=np.uint8)
    web_slots = np.array([index[spec] for spec in web['textures']], dtype=np.uint8)
    cli_iso, web_iso = root / 'cli.iso', root / args['output']
    assert cli_iso != web_iso
    cli(root, 'image', '--geo', args['geo'], '--r-max', args['r_max'],
        '--design-npy', 'cli.npy', '--textures', *cli_textures, '--output', cli_iso)
    report = dict(rgba_equal=same_rgba, web_placement=placement,
                  default_cli_width=2*E.grid()['annulus_mm'][1],
                  default_placement_differences_at_600=int(np.count_nonzero(baseline != placed)),
                  labels_differ=int(np.count_nonzero(cli_labels != web_labels)), label_count=cli_labels.size,
                  texture_cells_differ=int(np.count_nonzero(cli_slots[cli_labels] != web_slots[web_labels])),
                  same_work_npy_bytes_equal=True, web_slots=len(web_slots), cli_slots=len(cli_slots),
                  textures_equal=web['textures'] == cli_textures,
                  cli=hash_iso(cli_iso), web=hash_iso(web_iso))
    dump(root / 'parity.json', report)
    if report['cli']['without_dates'] == report['web']['without_dates']:
        cli_iso.unlink()
        web_iso.unlink()
    print(json.dumps(report, indent=2))


def hand_delta(x, y, camera, flash):
    radius = math.hypot(x, y)
    return abs(sum((-y*(px-x) + x*(py-y)) /
                   (radius * math.sqrt((px-x)**2 + (py-y)**2 + pz**2))
                   for px, py, pz in (camera, flash)))


def geometry(doc, table):
    # Actual coordinates received by the solver, after the input layer has been turned.
    doc['layers'][0]['rot'] = 37
    g = E.grid(120)
    spy = []
    original = simulate.along_track
    def record(x, y, **pose):
        value = original(x, y, **pose)
        spy.append((x, y, pose, value))
        return value
    with patch.object(simulate, 'along_track', record):
        E.compose(doc, g)
    rig = C.rig_data()
    d = rig['phones'][0]['flash_mm']
    z = next(h['camera_z_mm'] for h in rig['heights'] if h['id'] == '21')
    cam, flash = (0, 28.45, z), (0, 28.45+d, z)
    rows = []
    for x, y, pose, values in spy[::max(1, len(spy)//5)]:
        assert pose == dict(camera=cam, flash=flash)
        for i in (22, 29, 86, 97):
            direct = hand_delta(x[i], y, cam, flash)
            rows.append(dict(x=float(x[i]), y=y, actual=float(values[i]), hand=direct,
                             lookup=direct*table['delta_scale'],
                             y_flip=hand_delta(x[i], -y, cam, flash),
                             x_mirror=hand_delta(-x[i], y, cam, flash),
                             horizontal_flash=hand_delta(x[i],y,cam,(d,28.45,z)),
                             light_at_table_height=hand_delta(x[i],y,(0,28.45,z+1.3),(0,28.45+d,z+1.3))))
    assert max(abs(r['actual']-r['hand']) for r in rows) < 1e-12
    # A rotated disc changes where a labelled point lands under the fixed lamp.
    # Test that separately from rotating a source layer within an otherwise fixed disc.
    labels = np.zeros((240,240), np.uint8)
    labels[99:120,195:206] = 1
    material = [{'spec':'B9'},{'spec':'F9'}]
    render = dict(size=240, materials=material, table=table, fine=False,
                  diffraction_only=True, camera=cam, flash=flash)
    normal = np.asarray(simulate_a3.render(labels, **render))
    # A slightly smaller test turn keeps the marker away from the no-colour line.
    turned = np.asarray(simulate_a3.render(labels, rotate=35, **render))
    before = np.argwhere(normal.any(axis=2)).mean(axis=0)
    after = np.argwhere(turned.any(axis=2)).mean(axis=0)
    assert before[1] > 195 and after[1] < before[1] and after[0] < before[0]
    return dict(camera=cam, flash=flash, rows=rows, marker_yx=before.tolist(),
                marker_at_35_deg_yx=after.tolist())


def model(root):
    from scipy.ndimage import uniform_filter

    Image.fromarray(source()).save(root / 'model-source.png')
    doc = C.design(root / 'model-source.png', 'iphone17pro', 22.3)
    table = C.active_table()
    result = {'geometry':geometry(doc, table)}
    doc['layers'][0]['rot'] = 0
    layer = doc['layers'][0]
    size = 600
    g = E.grid(size)
    code, palette = C.picture_codes(np.array(Image.fromarray(source()).convert('RGBA')),
                                    layer['width'], layer['width'])
    c = (np.arange(size)+.5)*g['cell_mm']-60
    x, y = np.meshgrid(c, -c)
    dt = simulate.along_track(x, y, **C.work_rig(doc)) * table['delta_scale']
    r = np.hypot(x, y)
    ij = np.floor((c/layer['width']+.5)*96).astype(int)
    ring = (r >= 24) & (r < 58) & (abs(x) < layer['width']/2) & (abs(y) < layer['width']/2)
    valid = ring & (dt >= table['delta'][0]) & (dt <= table['delta'][-1])
    xv, yv = np.nonzero(valid)
    source_code = code[ij[xv], ij[yv]]
    goal = palette[source_code % C.SOURCE_COLOURS].copy()
    goal[:,0] += C.EDGE_LIGHTNESS * ((source_code//C.SOURCE_COLOURS).astype(float)-2)/2
    grid = table['delta']
    hi = np.searchsorted(grid, dt[valid], side='right').clip(1,len(grid)-1)
    weight = ((dt[valid]-grid[hi-1])/(grid[hi]-grid[hi-1]))[:,None,None]
    curves = table['xyz'].transpose(1,0,2) / simulate_a3.reference_y(table)
    candidates_xyz = curves[hi-1] + weight*(curves[hi]-curves[hi-1])
    candidates = C.xyz_lab(candidates_xyz)
    low = candidates[...,0].min(axis=1)
    span = np.ptp(candidates[...,0], axis=1)
    chroma = np.linalg.norm(candidates[...,1:],axis=2).max(axis=1)
    squeeze = .55 * (1-np.clip(span/100,0,1))
    map_scale = np.minimum(chroma/134*(1+.35*squeeze),1)
    target = goal.copy()
    target[:,0] = low + span*np.clip(goal[:,0]/100,0,1)
    target[:,1:] *= map_scale[:,None]
    distances = np.linalg.norm(candidates-target[:,None,:],axis=2)
    result['support'] = dict(in_table=int(valid.sum()), in_picture=int(ring.sum()),
                             scale_percentiles=np.percentile(map_scale,[5,50,95]).tolist())
    regions = np.where(ij[xv] >= 64, 6, (ij[xv]//32)*3 + ij[yv]//32)
    modes = {}
    for mode in ('nearest', 'ordered'):
        doc['assignments'][0]['colour']['dither'] = mode
        labels = E.compose(doc,g)
        assert ((labels != 0) == valid).all()
        indices = np.array([table['specs'].get(m['spec'],-1) for m in doc['materials']])[labels[valid]]
        assert (indices >= 0).all()
        row = np.arange(len(indices))
        xyz = candidates_xyz[row,indices]
        picked = distances[row,indices]
        # Local area mixing uses linear XYZ. Only fully supported 8x8 windows are compared.
        samples = np.zeros(labels.shape + (3,))
        samples[valid] = xyz
        mean_lab = C.xyz_lab(uniform_filter(samples, size=(8,8,1))[valid])
        mean_err = np.linalg.norm(mean_lab-target,axis=1)
        flat = uniform_filter(valid.astype(float), size=8)[valid] > .999
        for boundary in (32,64):
            flat &= np.abs(ij[xv] - boundary) >= 2
        flat &= (ij[xv] < 64) & (np.abs(ij[yv] - 32) >= 2) & (np.abs(ij[yv] - 64) >= 2)
        rgb = np.asarray(simulate_a3.render(labels, size, materials=doc['materials'], table=table,
                                           annulus_mm=doc['annulus_mm'], fine=False,
                                           diffraction_only=True, **C.work_rig(doc)))
        Image.fromarray(rgb).save(root / f'model-{mode}.png')
        modes[mode] = dict(used_textures=int(np.unique(labels[valid]).size),
                           exact_nearest_fraction=float(np.mean(picked <= distances.min(1)+1e-6)),
                           pooled_error=np.percentile(mean_err[flat],[50,95]).tolist(),
                           regions=[dict(name=name, cells=int(mask.sum()),
                                         delta_e=np.percentile(picked[mask],[50,95]).tolist(),
                                         oracle_median=float(np.median(distances.min(1)[mask])))
                                    for i, name in enumerate(('red','green','blue','yellow','magenta','cyan','grey ramp'))
                                    if (mask := regions == i).any()])
        y_channel = np.zeros(labels.shape)
        y_channel[valid] = xyz[:,1]
        # High spatial frequencies: decorrelate smooth lighting with local mean, then measure the
        # fixed 8x8 phase on the solid swatches. This is model/grid evidence, not a print artifact test.
        phase = np.zeros((8,8))
        high_pass = (y_channel - uniform_filter(y_channel, size=8))[valid]
        for j in range(8):
            for i in range(8):
                phase[j,i] = high_pass[flat & (xv%8 == j) & (yv%8 == i)].mean()
        modes[mode]['bayer_phase_rms_reference_y'] = float(np.std(phase))
        modes[mode]['phase_lag_axis'] = [
            float(np.corrcoef(phase.ravel(),np.roll(phase, shift, axis=1).ravel())[0,1]) for shift in (1,2,4)]
    result['selection'] = modes
    dump(root / 'model.json', result)


def photo(root, archive):
    """Sample the same interiors on the colour4 design and the archived phone photo."""
    from scipy.ndimage import map_coordinates
    from PIL import ImageDraw
    from discprobe import beacondisc, beaconread, tiledisc

    frame = 'IMG_7122'
    records = json.loads((archive / 'exam3_geometry.json').read_text(encoding='utf-8'))
    pose = next(r for r in records if r['name'] == frame and r['used'])
    with Image.open(archive / 'photos' / (frame + '.jpeg')) as photo_file:
        pixels = np.asarray(ImageOps.exif_transpose(photo_file).convert('RGB'))
    table = C.active_table()
    # Archived phone-drawing offset in the EXIF-normalized landscape camera axes.
    assert pose['orient'] == 3
    camera = np.array(pose['C_rim'])
    flash = camera + np.array(pose['R_rim']).T @ (19.79, -43.66, 0.)
    H = np.array(pose['H'])
    spec = 'F9'
    palette = beacondisc.PALETTE
    assert set(palette) & set(table['specs']) == {spec}
    samples, chips = [], []
    edges = np.linspace(.15, .85, 9)
    u, v = np.meshgrid(edges, edges)
    for identifier in pose['read']:
        ring, sector = beacondisc.ring_sector(identifier)
        r0, dr, a0, da = beacondisc._tile_frame(ring, sector)
        slots = tiledisc.swatch_slots(ring, sector, len(palette), beacondisc._geometry())
        column, row = divmod(int(slots[palette.index(spec)]), 3)
        r = r0 + (row+u.ravel())/3*dr
        pad = beacondisc.GAP_MM/2/r
        a = a0 + pad + (beacondisc.ID_FRAC+(column+v.ravel())/3*(1-beacondisc.ID_FRAC))*(da-2*pad)
        x, y = r*np.cos(a), r*np.sin(a)
        xy = beaconread.project(H,x,y)
        dt = simulate.along_track(x,y,camera,flash)*table['delta_scale']
        observed_xyz = np.mean([map_coordinates(C.LINEAR[pixels[..., k]], [xy[:,1],xy[:,0]],
                                                 order=1, cval=np.nan) for k in range(3)],axis=1) @ C.SRGB_XYZ.T
        predicted_xyz = simulate_a3.material_xyz({'spec':spec},dt,table).mean(axis=0)
        within = (dt >= table['delta'][0]) & (dt <= table['delta'][-1])
        record = dict(tile=identifier, centre_px=np.mean(xy,axis=0).tolist(), in_table=int(within.sum()),
                      observed_y=float(observed_xyz[1]), predicted_y=float(predicted_xyz[1]))
        for prefix, xyz in [('observed', observed_xyz), ('predicted', predicted_xyz)]:
            if xyz[1] > 0:
                # Match luminance at each patch to compare hue without equating the camera exposure to the LUT.
                lab = C.xyz_lab(xyz * (.2/xyz[1]))
                record[prefix+'_hue'] = math.degrees(math.atan2(lab[2],lab[1])) % 360
                record[prefix+'_chroma'] = float(np.hypot(*lab[1:]))
        if within.all() and min(record['observed_chroma'], record['predicted_chroma']) >= 10:
            record['hue_error'] = abs((record['predicted_hue']-record['observed_hue']+180)%360-180)
        samples.append(record)
        chips.append([tuple(np.uint8(np.clip(np.rint(
            255*np.interp((table['m']@xyz)*(.2/xyz[1]), C.LINEAR, np.arange(256)/255)), 0, 255)))
            for xyz in (observed_xyz,predicted_xyz)])
    used = [r for r in samples if r['in_table'] == 81]
    errors = [r['hue_error'] for r in used if 'hue_error' in r]
    dump(root / 'photo.json', dict(frame=frame, spec=spec, camera=camera.tolist(), flash=flash.tolist(),
                                   sha256=hashlib.sha256((archive/'photos'/(frame+'.jpeg')).read_bytes()).hexdigest(),
                                   full_support=len(used), hue_samples=len(errors),
                                   median_hue_error=float(np.median(errors)) if errors else None,
                                   brightness_r=float(np.corrcoef([r['observed_y'] for r in used],
                                                                   [r['predicted_y'] for r in used])[0,1]),
                                   regions=samples))
    plate = Image.new('RGB', (610, 120+len(chips)*28), 'white')
    draw = ImageDraw.Draw(plate)
    draw.text((12,10), 'Colour4 / IMG_7122 / F9   -   same luminance for hue comparison', fill='black')
    draw.text((12,45), 'Tile         Photo             Prediction         Hue error', fill='black')
    for i, (row, colours) in enumerate(zip(samples,chips)):
        y = 65 + i*28
        draw.text((12,y+5), str(row['tile']), fill='black')
        for x, rgb in zip((76,180), colours):
            draw.rectangle((x,y,x+58,y+22), fill=rgb)
        draw.text((330,y+5), f"{row['hue_error']:.1f} deg" if 'hue_error' in row else 'low chroma', fill='black')
    plate.save(root / 'photo-regions.png')


def library(root, archive, character_textures):
    """Compare the two response tables on their common calibrated interval."""
    table = C.active_table()
    source_path = archive / 'delta-lookup.npz'
    with np.load(source_path, allow_pickle=False) as z:
        slots = {spec:index for index,spec in enumerate(z['spec'])}
        common = sorted(table['specs'].keys() & slots.keys())
        ids = [slots[spec] for spec in common]
        fit = z['fitted_spec']
        grid = z['delta']
        use = (grid >= z['fit_min']) & (grid <= z['fit_max'])
        reference = z['xyz_order'][ids][:,use].sum(axis=2)
        packed = table['xyz'][[table['specs'][spec] for spec in common]]
        interpolated = np.array([[np.interp(grid[use],table['delta'],channel) for channel in rgb.T]
                                 for rgb in packed]).transpose(0,2,1)
        # Sum and check every order before considering this file for the ordinary colour solver.
        report = dict(lookup_specs=len(slots), fitted_rows=int(fit.sum()), packed_specs=len(table['specs']),
                      common=len(common), common_fitted=int(fit[ids].sum()),
                      packed_missing=sorted(set(table['specs'])-set(slots)),
                      packed_with_92=sum(0x92 in bytes.fromhex(spec) for spec in table['specs']),
                      common_delta_points=int(use.sum()),
                      max_abs_xyz=float(np.max(np.abs(interpolated-reference))),
                      lookup_shape=list(z['xyz_order'].shape), lookup_delta=[float(grid[0]),float(grid[-1])],
                      bundled_delta=table['delta'][[0,-1]].tolist(),
                      lookup_bytes=source_path.stat().st_size, bundled_bytes=C.DEFAULT_TABLE.stat().st_size,
                      lookup_delta_scale=float(z['scale']), bundled_delta_scale=table['delta_scale'])
        if character_textures:
            character = set(json.loads(character_textures.read_text(encoding='utf-8'))['textures'])
            report.update(character_specs=len(character), character_with_92=sum(0x92 in bytes.fromhex(s) for s in character),
                          character_in_lookup=len(character & slots.keys()),
                          character_in_web=len(character & table['specs'].keys()))
    dump(root / 'library.json', report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('serve', 'parity', 'model', 'photo', 'library'))
    parser.add_argument('root', type=Path)
    parser.add_argument('--archive', type=Path, help='historical colour4 or flip-pairs project directory')
    parser.add_argument('--character-textures', type=Path, help='historical role card texture manifest for library mode')
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.mode == 'serve':
        serve(root)
    elif args.mode == 'parity':
        parity(root)
    elif args.mode == 'model':
        model(root)
    elif args.archive is None:
        parser.error('--archive is required for this mode')
    elif args.mode == 'photo':
        photo(root,args.archive.resolve())
    else:
        library(root,args.archive.resolve(),args.character_textures)


if __name__ == '__main__':
    main()
