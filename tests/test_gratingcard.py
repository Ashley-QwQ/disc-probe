"""The angle solver, channel limits, direction mark and virtual DVD readback."""
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import pytest

from discprobe import dvd, gratingcard as G, iso9660
from discprobe.image_output import require_checked
from test_checkburn import cli, lab, report, virtual_write


def small_geometry(path):
    u, bit = 180518.44062237992, 133.3
    v = math.pi*((54.6/(bit*1e-6))**2-u*u)/(8192*G.imagedisc.SECTOR_BITS)
    path.write_text(json.dumps(dict(fit=dict(u=u, v=v, bit_nm_assumed=bit, measured_span_mm=[24,58]))),
                    encoding='utf-8')


def optical_fixture(root):
    lookup, index, checks = [root / n for n in ('delta-lookup.npz','angle-curves-index.csv','channel.json')]
    delta = np.linspace(0,.95,381)
    camera, flash = [0,28.45,221.74],[0,76.39,221.74]
    poses, _ = G.illumination(np.array([39.]),np.array([0.]),camera,flash,'x',[0,6],.93)
    responses = np.exp(-.5*((delta[None,:]-poses.T)/.035)**2)
    xyz = np.zeros((4,len(delta),4,3),np.float32)
    xyz[1:3,:,0] = responses[...,None]*np.array([.40,.55,.20])
    xyz[3,:,0] = .99
    specs = ['00','A5','B9','92']
    np.savez(lookup, delta=delta, xyz_order=xyz, spec=specs, scale=.93, camera=camera, flash=flash,
             annulus=[25.75,53.99], paper_white=[.95,1,1.088], background=[.015,.018,.02])
    with index.open('w',encoding='utf-8',newline='') as stream:
        writer = csv.writer(stream)
        writer.writerows([['spec'], *[[s] for s in specs]])
    checks.write_text(json.dumps({s:dict(passed=True,F512=.1,lean=.01,dsv=64) for s in specs}),encoding='utf-8')
    return lookup, checks


def art(path, side):
    picture = Image.new('RGB',(12,12),'black')
    ImageDraw.Draw(picture).rectangle((side,2,side+4,9),fill='white')
    picture.save(path)


def normal_iso(path):
    data = bytearray(path.read_bytes())
    for sector, start, size in ((16,813,34),(16,174,7),(20,18,7),(20,52,7)):
        off = 2048*sector+start
        data[off:off+size] = bytes(size)
    return hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize('change, allowed', [({}, True), ({'F512':1.5}, False), ({'lean':.1501}, False),
                                             ({'dsv':101}, False), ({'passed':False}, False)])
def test_channel_limits(change, allowed):
    row = dict(passed=True,F512=.01,lean=.15,dsv=100)
    row.update(change)
    assert G.gate_passed(row) is allowed
    assert '92' not in G.checked_textures({'92':row})


def test_card_cli_and_virtual_readback(lab):
    root = lab.root.parent
    lookup, gates = optical_fixture(root)
    geo = root/'geometry.json'
    small_geometry(geo)
    images = [root/'left.png',root/'right.png']
    for path, side in zip(images, (0,7), strict=True):
        art(path,side)
    out = root/'deck.iso'
    argv = ['gratingcard',*images,'--geo',geo,'--lookup',lookup,'--channel-checks',gates,
            '--angles',0,6,'--width',3,'--output',out,'--json']
    result = json.loads(cli(lab,'--lang','en',*argv))
    assert result['verified'] is True
    assert result['views'] == [{'angle_deg':0.,'picture':'left'},{'angle_deg':6.,'picture':'right'}]
    assert 'Positive X tilt raises 12 o’clock.' in Path(result['viewing_guide']).read_text(encoding='utf-8')
    labels = np.load(result['labels'],allow_pickle=False)
    assert labels.shape == (6000,6000) and labels.dtype == np.uint8
    specs = json.loads(Path(result['textures']).read_text(encoding='utf-8'))['textures']
    assert specs == ['00','A5','B9',G.ARROW]
    left_half = labels[2980:3020,4880:4948]
    right_half = labels[2980:3020,4952:5020]
    assert (left_half == specs.index('A5')).sum() > (left_half == specs.index('B9')).sum()
    assert (right_half == specs.index('B9')).sum() > (right_half == specs.index('A5')).sum()
    rows, cols = np.where(labels == specs.index(G.ARROW))
    assert len(rows) > 1000
    radii = np.hypot((cols+.5)*.02-60,60-(rows+.5)*.02)
    assert radii.min() == pytest.approx(43.5, abs=.06)
    assert radii.max() == pytest.approx(52.8, abs=.06)
    require_checked(out,out.stat())
    with out.open('rb') as stream:
        for lba in range(out.stat().st_size//2048):
            payload = np.frombuffer(stream.read(2048),np.uint8)
            if lba not in iso9660.SECTORS:
                assert not np.any(dvd.recorded(payload,lba) == 0x92)
    assert normal_iso(out) == 'd708214a92b668fee4c88f60f163fdbfcca93304cadd953a3021f46a0456bdb6'
    virtual_write(lab,out)
    assert report(lab,'--iso',out)['verification']['ok'] == 96


def test_replay_swaps_background_after_dithering():
    pixels = np.full((G.GRID,G.GRID),-1,np.int32)
    pixels[500:502,600:602] = 0
    labels,specs = G.dither(pixels,np.array([[.25,.75]],np.float32),['A5','00'],1)
    assert specs == ['00','A5'] and labels[0,0] == 0
    for y in range(1500,1506):
        for x in range(1800,1806):
            assert labels[y,x] == (G.editor_colour.BAYER[y%8,x%8] < .25)


def test_bundled_lookup_and_three_target_angles(tmp_path):
    checked = G.checked_textures(G.read_json(G.DEFAULT_CHECKS))
    table = G.Lookup(G.DEFAULT_LOOKUP,G.DEFAULT_INDEX,checked)
    assert len(table.specs) == 124
    assert all(0x92 not in bytes.fromhex(spec) for spec in table.specs)
    paths = [tmp_path/f'state-{i}.png' for i in range(3)]
    for path, side in zip(paths,(0,3,7),strict=True):
        art(path,side)
    pixels, weights, specs = G.solve(table,paths,[0,6,-2.5],'x',table.camera,table.flash,
                                     table.annulus,(39.,0.),3.)
    labels, _ = G.dither(pixels,weights,specs,0)
    assert set(specs) <= checked
    assert hashlib.sha256(labels).hexdigest() == '51f3db960abde53a377176f856d82613ec010d234b28da012401b7a8309675ff'
