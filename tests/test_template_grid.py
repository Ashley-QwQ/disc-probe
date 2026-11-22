import base64
import io
import json

import numpy as np
from PIL import Image, PngImagePlugin
import pytest

from discprobe import editor_ops, template_grid


@pytest.fixture
def batch(tmp_path):
    source = tmp_path / 'batch.json'
    source.write_text(json.dumps(dict(totalSectors=2_297_888, innerRadiusMm=24, outerRadiusMm=58)),
                      encoding='utf-8')
    return source


@pytest.mark.parametrize('pitch,side,dpi', [(5, 24000, 5080), (10, 12000, 2540), (20, 6000, 1270)])
def test_full_disc_files_match_the_core_grid(batch, pitch, side, dpi):
    stem, files = template_grid.export_files(batch, grid=pitch, batch='试盘 RITEKF1')
    assert stem.startswith(f'dp_template_{pitch}um_试盘-RITEKF1_2297888s_pose-x0_y70_z330mm_rot0deg-')
    disk_grid = editor_ops.grid(round(120 / (pitch / 1000)))
    assert (disk_grid['width'], disk_grid['height'], disk_grid['cell_mm']) == (side, side, pitch / 1000)
    assert set(files) == {f'{stem}_{name}' for name in ('canvas.png', 'guide.png', 'README.txt')}
    for name in ('canvas', 'guide'):
        with PngImagePlugin.PngImageFile(io.BytesIO(files[f'{stem}_{name}.png'])) as im:
            assert im.size == (side, side)
            assert im.mode == 'RGBA'
            assert im.info['dpi'] == pytest.approx((dpi, dpi), abs=.001)
    if pitch == 20:
        with Image.open(io.BytesIO(files[f'{stem}_guide.png'])) as guide:
            assert guide.getpixel((0, 0))[3] == guide.getpixel((3000, 3000))[3] == 0
            assert guide.crop((2980, 360, 3020, 385)).getbbox()  # tip of the 12 o'clock outline
            assert guide.crop((3370, 2980, 3382, 3020)).getbbox()  # centre-hole edge


def test_painted_png_returns_at_the_same_pixel(batch, tmp_path):
    stem, files = template_grid.export_files(batch, grid=20)
    x, y = 4321, 1789
    painted = io.BytesIO()
    with Image.open(io.BytesIO(files[f'{stem}_canvas.png'])) as canvas:
        assert canvas.getbbox() is None
        canvas.putpixel((x, y), (0, 0, 0, 255))
        canvas.save(painted, 'PNG', dpi=canvas.info['dpi'])
    preview, bounds = template_grid.preview_png(painted.getvalue())
    assert bounds == pytest.approx([(x * .02) - 60, (y * .02) - 60,
                                    ((x + 1) * .02) - 60, ((y + 1) * .02) - 60])
    with Image.open(io.BytesIO(preview)) as im:
        assert im.size == (1200, 1200)
        raster = dict(width=im.width, height=im.height, rgba=base64.b64encode(im.tobytes()).decode())
    layer = dict(kind='image', raster=raster, width=120,
                 gridPng=template_grid.PNG_DATA_PREFIX + base64.b64encode(painted.getvalue()).decode())
    patch = dict(width=3, height=3, left_mm=-60 + (x - 1) * .02,
                 top_mm=-60 + (y - 1) * .02, cell_mm=.02)
    labels = editor_ops.compose(dict(layers=[layer]), patch, scratch=tmp_path)
    np.testing.assert_array_equal(labels, [[0, 0, 0], [0, 1, 0], [0, 0, 0]])
