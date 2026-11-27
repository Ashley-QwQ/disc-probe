"""The browser's lamp view (design/lamp-optics.mjs) against discprobe.simulate_a3.render, the model it ports."""
import base64
import json
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile

import numpy as np
import pytest

from discprobe import simulate_a3, focal

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

PALETTE = json.loads((ROOT / "discprobe/web/home/design/swatches.json").read_text(encoding="utf8"))


def materials():
    swatches = list(PALETTE["swatches"].values())
    known = next(m for m in swatches if simulate_a3.known(m) and simulate_a3.canonical(m["spec"]) not in ("A5", "B9"))
    return [dict(id="background", spec="B9"), dict(id="dark", spec="A5"),
            dict(known, period_um=known["periods_um"][0]), dict(id="rec", spec="RND"),
            dict(id="stretched", spec="0102030405", period_um=1.3)]


def blocks(n=200):
    """Labels in blocks of a whole coverage pixel, so both sides see the same shares."""
    y, x = np.indices((n, n))
    r = np.hypot(x - n / 2 + .5, y - n / 2 + .5) * 120 / n
    a = np.degrees(np.arctan2(y - n / 2, x - n / 2)) % 360
    labels = np.zeros((n, n), np.uint8)
    labels[(r > 26) & (r < 56) & (a < 90)] = 1
    labels[(r > 30) & (r < 50) & (a >= 90) & (a < 180)] = 2
    labels[(r > 30) & (r < 56) & (a >= 180) & (a < 250)] = 3
    labels[(r > 28) & (r < 52) & (a >= 250)] = 4
    labels[(x // 7 + y // 9) % 5 == 0] = 1
    return labels


def run_js(job):
    with tempfile.TemporaryDirectory(prefix="dp-lamp-") as folder:
        src, out = Path(folder) / "job.json", Path(folder) / "out.bin"
        src.write_text(json.dumps(job))
        done = subprocess.run(["node", str(ROOT / "tests/lamp_runner.mjs"), str(src), str(out)], check=True,
                              capture_output=True, text=True, timeout=240)
        meta = json.loads(done.stdout)
        rgba = np.frombuffer(out.read_bytes(), np.uint8).reshape(job["size"], job["size"], 4)
    return rgba, meta


def job(labels, mats, pose, size, k, share=None, annulus=(24, 58)):
    n = labels.shape[0]
    j = dict(labels=base64.b64encode(np.ascontiguousarray(labels).tobytes()).decode(), n=n, materials=mats, pose=pose,
             size=size, k=k, annulus=list(annulus))
    if share is not None:
        j["share"] = base64.b64encode(share.astype("<f4").tobytes()).decode()
    return j


@pytest.mark.parametrize("pose", [
    dict(camera=[0., 70., 330.], flash=[-43.66, 89.79, 330.], rotate=0),
    dict(camera=[20., 85., 330.], flash=[-23.66, 104.79, 330.], rotate=17),
    dict(camera=[0., 28.45, 206.5], flash=[0., 76.35, 206.5], rotate=200),
    dict(camera=list(focal.CAMERA), flash=list(focal.FLASH), rotate=200),
    dict(camera=[0., 28.45, 206.5], flash=[0., 76.35, 206.5], rotate=200, delta_scale=.93),
])
def test_matches_python_render(pose):
    labels, mats = blocks(), materials()
    for size, fine in [(200, False), (200, True)]:
        k = int(np.ceil(2000 / size)) if fine else 1
        design = np.kron(labels, np.ones((10, 10), np.uint8))           # 2000 cells: each block is one pixel's square
        py = np.asarray(simulate_a3.render(design, size, materials=mats, fine=fine, annulus_mm=(24, 58), **pose))
        js, meta = run_js(job(labels, mats, pose, size, k))
        assert meta["unknown"] == ["stretched"]
        diff = np.abs(js[..., :3].astype(int) - py.astype(int))
        assert diff.max() <= 2, (size, fine, diff.max())
        assert diff.mean() < .05


def test_dither_share_mixes_like_the_burn_cells():
    """A dithered grey: the core counts the cells (a 50 % checkerboard), the browser uses the share it was dithered at."""
    n, mats = 200, materials()[:2]
    y, x = np.indices((2000, 2000))
    r = np.hypot(x - 999.5, y - 999.5) * .06
    design = np.where((r > 30) & (r < 50), (x + y) % 2, 0).astype(np.uint8)
    pose = dict(camera=[0., 28.45, 206.5], flash=[0., 76.35, 206.5], rotate=0)
    py = np.asarray(simulate_a3.render(design, n, materials=mats, fine=False, annulus_mm=(24, 58), **pose))
    rr = np.hypot(*np.indices((n, n)) - n / 2 + .5) * 120 / n
    share = np.where((rr > 30) & (rr < 50), .5, np.nan)
    js, _ = run_js(job(design[::10, ::10] * 0, mats, pose, n, 1, share=share))
    diff = np.abs(js[..., :3].astype(int) - py.astype(int))
    ring = (rr > 31) & (rr < 49)
    assert diff[ring].max() <= 3
    assert diff.mean() < .5


def test_tables_are_the_npz():
    assert subprocess.run([sys.executable, str(ROOT / "tools/lamp_tables.py"), "--check"], cwd=ROOT).returncode == 0


def test_scheduling():
    subprocess.run(["node", str(ROOT / "tests/test_editor_lamp.mjs")], check=True, timeout=120)


def test_document_end_to_end():
    """A work with a dithered picture and a coloured ring: the browser path (the editor's composer at a 512 grid, the
    dark share of dithered cells) against the core's (every 20 um burn cell composed, then simulate_a3.render)."""
    from discprobe import editor_ops as E
    y, x = np.indices((96, 96))
    grey = np.clip(40 + 2.2 * x + 30 * np.sin(y / 9), 0, 255).astype(np.uint8)
    rgba = np.dstack([grey, grey, grey, np.full_like(grey, 255)])
    mat = dict(materials()[2], rgb=[90, 200, 120])
    grid = E.grid(60)
    mask = E.selection(dict(tool="ring", inner=47, outer=55), grid)
    document = E.migrate(dict(version=2, media="dvd", cell=.02, maskGrid=grid,
        materials=[dict(id="background", spec="B9", rgb=[205, 200, 190]), dict(id="dark", spec="A5", rgb=[40, 40, 40]), mat],
        layers=[dict(id=1, kind="image", name="p", x=0, y=0, width=80, w=96, h=96, height=80,
                     raster=dict(width=96, height=96, rgba=base64.b64encode(rgba.tobytes()).decode()))],
        selections=[dict(id="ring", name="Ring", bits=base64.b64encode(mask).decode())],
        assignments=[dict(selection="ring", material=mat["id"])]))
    pose = dict(camera=[0., 28.45, 206.5], flash=[0., 76.35, 206.5], rotate=30)
    design = E.compose(E.validate(document))
    py = np.asarray(simulate_a3.render(design, 256, materials=document["materials"], fine=False, annulus_mm=(24, 58), **pose)).astype(int)
    with tempfile.TemporaryDirectory(prefix="dp-lamp-doc-") as folder:
        src, out = Path(folder) / "doc.json", Path(folder) / "out.bin"
        src.write_text(json.dumps(dict(document=document, n=512, pose=pose, size=256, k=1)))
        subprocess.run(["node", str(ROOT / "tests/lamp_runner.mjs"), "--document", str(src), str(out)], check=True,
                       capture_output=True, timeout=240)
        js = np.frombuffer(out.read_bytes(), np.uint8).reshape(256, 256, 4)[..., :3].astype(int)
    r = np.hypot(*np.indices((256, 256)) - 127.5) * 120 / 256
    disc = (r > 26) & (r < 56)
    diff = np.abs(js - py)[disc].mean(-1)
    # the same picture, the same light. Away from edges only the dither's grain differs (cells counted against the
    # share they were dithered at); an edge (of the picture, of the 2 mm selection cells) may fall a pixel apart
    edge = np.zeros(py.shape[:2], bool)
    for image in (py, js):
        for axis in (0, 1):
            step = np.abs(np.diff(image, axis=axis)).max(-1) > 20
            edge |= np.pad(step, [(0, 1), (0, 0)] if axis == 0 else [(0, 0), (0, 1)])
    for _ in range(2):                                       # two pixels either side
        edge = edge | np.roll(edge, 1, 0) | np.roll(edge, -1, 0) | np.roll(edge, 1, 1) | np.roll(edge, -1, 1)
    inner = disc & ~edge
    assert inner.mean() > .5 * disc.mean()
    assert diff.mean() < 3, diff.mean()
    assert np.abs(js - py)[inner].mean(-1).max() <= 12
    assert np.abs(js - py)[inner].mean() < 1
    assert abs(js[disc].mean() - py[disc].mean()) < 1


def test_fitted_colour_labels_and_delta_match_lamp_renderer(tmp_path, monkeypatch):
    from PIL import Image
    from discprobe import editor_colour, editor_ops, simulate
    from discprobe.editor_preview import lamp_tables

    monkeypatch.delenv('DISCPROBE_TEXLIB', raising=False)
    source = tmp_path / 'art.png'
    Image.fromarray(np.array([[[120,190,228],[255,198,64]], [[56,151,92],[50,92,171]]], np.uint8)).save(source)
    table = editor_colour.active_table()
    document = editor_colour.design(source, 'iphone17pro', 22.3)
    pose = editor_colour.work_rig(document)
    size = 200
    labels = editor_ops.compose(document, editor_ops.grid(size))
    assert np.unique(labels).size > 2
    args = job(labels, document['materials'], pose, size, 1)
    args.update(table=lamp_tables(table), diffractionOnly=True)
    request, output, delta = (tmp_path / name for name in ('job.json','pixels.bin','delta.bin'))
    request.write_text(json.dumps(args),encoding='utf-8')
    subprocess.run(['node',str(ROOT/'tests/lamp_runner.mjs'),str(request),str(output),str(delta)],
                   check=True,capture_output=True,timeout=60)
    axis = (np.arange(size)+.5)*(120/size)-60
    x,y = np.meshgrid(axis,-axis)
    actual_delta = np.fromfile(delta,'<f8').reshape(size,size)
    np.testing.assert_allclose(actual_delta,simulate.along_track(x,y,**pose)*table['delta_scale'],atol=1e-13,rtol=0)
    js = np.fromfile(output,np.uint8).reshape(size,size,4)[...,:3].astype(int)
    py = np.asarray(simulate_a3.render(labels,size,materials=document['materials'],table=table,
                   diffraction_only=True,fine=False,annulus_mm=document['annulus_mm'],**pose)).astype(int)
    diff = np.abs(js-py)
    assert diff.max() <= 2
    assert diff.mean() < .05
