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

from discprobe import simulate_a3

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
