import base64
from contextlib import closing
import http.client
import io
import json
import struct
import threading
import zlib

import cv2
import numpy as np
from PIL import Image, ImageCms, ImageOps
import pytest

from discprobe import colour_input, editor_colour, editor_ops, editor_preview, template_grid, webui


SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
# D65 RGB primaries (x, y). The generated names identify test profiles, not vendor files.
PRIMARIES = {
    'Display P3': [(0.68, 0.32), (0.265, 0.69), (0.15, 0.06)],
    'Adobe RGB compatible': [(0.64, 0.33), (0.21, 0.71), (0.15, 0.06)],
    'Rec.2020': [(0.708, 0.292), (0.170, 0.797), (0.131, 0.046)],
}
D65_TO_D50 = np.array([[1.04792979, .02294687, -.05019227],
                       [.02962781, .99043443, -.0170738],
                       [-.00924304, .01505519, .75187428]])
PALETTE = np.array([[[211, 69, 48], [231, 166, 62], [89, 148, 83], [50, 122, 154]],
                    [[26, 42, 91], [144, 78, 141], [212, 158, 128], [11, 11, 11]],
                    [[224, 224, 224], [128, 128, 128], [61, 152, 143], [180, 192, 97]],
                    [[44, 95, 204], [229, 117, 153], [116, 78, 53], [147, 181, 221]]], np.uint8)


def named_profile(name):
    base = SRGB.tobytes()
    tags = {tag: base[offset:offset+size] for tag, offset, size in
            struct.iter_unpack('>4sII', base[132:132+12*struct.unpack_from('>I', base, 128)[0]])}
    x, y = np.array(PRIMARIES[name]).T
    xyz = np.stack((x/y, np.ones(3), (1-x-y)/y))
    matrix = D65_TO_D50 @ (xyz * np.linalg.solve(xyz, [.95045593, 1., 1.08905775]))
    for tag, column in zip((b'rXYZ', b'gXYZ', b'bXYZ'), matrix.T):
        tags[tag] = b'XYZ \0\0\0\0' + struct.pack('>3i', *np.rint(column*65536).astype(int))
    del tags[b'chrm']
    if name == 'Adobe RGB compatible':
        for tag in (b'rTRC', b'gTRC', b'bTRC'):
            tags[tag] = struct.pack('>4sIIH', b'curv', 0, 1, 563)
    elif name == 'Rec.2020':
        a, b = 1.09929682680944, .018053968510807
        params = np.rint(65536*np.array([1/.45, 1/a, (a-1)/a, 1/4.5, 4.5*b])).astype(int)
        for tag in (b'rTRC', b'gTRC', b'bTRC'):
            tags[tag] = struct.pack('>4sIHH5i', b'para', 0, 3, 0, *params)
    desc = name.encode('utf-16-be')
    tags[b'desc'] = struct.pack('>4sIII4sII', b'mluc', 0, 1, 12, b'enUS', len(desc), 28) + desc
    offsets, body = bytearray(), bytearray()
    start = 132 + len(tags)*12
    for tag, data in tags.items():
        offsets.extend(struct.pack('>4sII', tag, start+len(body), len(data)))
        body.extend(data + b'\0'*(-len(data) % 4))
    return struct.pack('>I', start+len(body)) + base[4:128] + struct.pack('>I', len(tags)) + offsets + body


def png(image, profile=None):
    output = io.BytesIO()
    image.save(output, 'PNG', icc_profile=profile)
    return output.getvalue()


def png16(samples, profile):
    # OpenCV encodes native 16-bit BGR(A). Add the PNG iCCP chunk after IHDR.
    order = [2, 1, 0, 3] if samples.shape[-1] == 4 else [2, 1, 0]
    ok, data = cv2.imencode('.png', samples[..., order])
    assert ok
    raw = data.tobytes()
    chunk = b'iCCP' + b'ICC\0\0' + zlib.compress(profile)
    return raw[:33] + struct.pack('>I', len(chunk)-4) + chunk + struct.pack('>I', zlib.crc32(chunk)) + raw[33:]


def sample_images():
    """The same modest-gamut swatches encoded in each source space."""
    image = Image.fromarray(PALETTE)
    yield 'sRGB', png(image, SRGB.tobytes())
    for name in PRIMARIES:
        profile = named_profile(name)
        encoded = ImageCms.profileToProfile(image, SRGB, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                                             renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC)
        yield name, png(encoded, profile)
    # Encode the Display P3 samples from linear sRGB before either space is reduced to 8 bits.
    source = PALETTE / 255
    linear = np.where(source <= .04045, source / 12.92, ((source + .055) / 1.055)**2.4)
    p3 = linear @ np.array([[.82246197, .17753803, 0], [.0331942, .9668058, 0],
                            [.01708263, .07239744, .91051993]]).T
    encoded = np.where(p3 <= .0031308, 12.92*p3, 1.055*p3**(1/2.4)-.055)
    yield 'Display P3 16-bit', png16(np.rint(encoded*65535).astype(np.uint16), named_profile('Display P3'))


def rgba(data):
    with Image.open(io.BytesIO(data)) as picture:
        return np.asarray(picture.convert('RGBA'))


def test_equivalent_profiles_reach_the_solver(tmp_path):
    first_labels = first_preview = None
    for name, data in sample_images():
        path = tmp_path / 'swatches.png'
        path.write_bytes(data)
        notices = []
        doc = editor_colour.design(path, 'iphone17pro', 22.3, report_icc=notices.append)
        assert notices == [{'profile': {'sRGB': 'sRGB built-in', 'Display P3 16-bit': 'Display P3'}.get(name, name)}]
        raster = doc['layers'][0]['raster']
        pixels = np.frombuffer(base64.b64decode(raster['rgba']), np.uint8).reshape(4, 4, 4)
        assert np.abs(pixels[..., :3].astype(int) - PALETTE).max() <= 1, name
        if name.endswith('16-bit'):
            np.testing.assert_array_equal(pixels[..., :3], PALETTE)
        editor_colour.add_direction_arrow(doc)
        labels = editor_ops.compose(doc, editor_ops.grid(180))
        preview = rgba(editor_preview.Renderer().render(dict(document=doc, size=200))[0])
        if first_labels is None:
            first_labels, first_preview = labels, preview
        assert np.mean(labels != first_labels) < .02, name
        assert np.mean(np.abs(preview.astype(int) - first_preview)) < 1, name


def test_cli_reports_conversion_and_fallback(tmp_path, capsys):
    from discprobe import __main__ as cli

    source = tmp_path / 'input.png'
    out = tmp_path / 'work.json'
    args = ['colour-design', str(source), '--phone', 'iphone17pro', '--height', '22.3', '-o', str(out)]
    source.write_bytes(dict(sample_images())['Display P3'])
    cli.main(['--lang', 'zh', *args])
    assert capsys.readouterr().err == '已按 Display P3 转换为 sRGB。\n'
    source.write_bytes(png(Image.fromarray(PALETTE), b'invalid profile'))
    cli.main(['--lang', 'en', *args])
    assert capsys.readouterr().err == colour_input.FALLBACK + '\n'
    fallback = out.read_bytes()
    source.write_bytes(png(Image.fromarray(PALETTE)))
    cli.main(['--lang', 'en', *args])
    assert capsys.readouterr().err == ''
    assert out.read_bytes() == fallback


def test_profile_fallback_and_exif_orientation():
    image = Image.fromarray(PALETTE[:2])
    image.getexif()[274] = 6
    output = io.BytesIO()
    image.save(output, 'PNG', exif=image.getexif(), icc_profile=b'invalid profile')
    data = output.getvalue()
    with Image.open(io.BytesIO(data)) as original:
        expected = np.asarray(ImageOps.exif_transpose(original).convert('RGBA'))
    picture, notice = colour_input.web_picture(data)
    assert notice == {'fallback': True}
    np.testing.assert_array_equal(rgba(picture), expected)
    with Image.open(io.BytesIO(picture)) as converted:
        assert 'icc_profile' not in converted.info


def test_16_bit_rgb_and_alpha_are_rounded_only_after_conversion():
    # Both pixels have the same top bytes. The low bytes cross an sRGB rounding boundary.
    samples = np.array([[[12851, 12851, 12851, 127], [13007, 13007, 13007, 129]]], np.uint16)
    picture, notice = colour_input.web_picture(png16(samples, SRGB.tobytes()))
    assert notice == {'profile': 'sRGB built-in'}
    assert rgba(picture).tolist() == [[[50, 50, 50, 0], [51, 51, 51, 1]]]
    picture, notice = colour_input.web_picture(png16(samples, b'invalid profile'))
    assert notice == {'fallback': True}
    assert rgba(picture).tolist() == [[[50, 50, 50, 0], [51, 51, 51, 1]]]


def test_template_preview_and_native_raster_use_the_same_profile(monkeypatch):
    monkeypatch.setattr(template_grid, 'GRID_SIDES', {20: 4})
    monkeypatch.setattr(template_grid, 'PREVIEW_SIDE', 4)
    raw = dict(sample_images())['Display P3 16-bit']
    notices = []
    picture, bounds = template_grid.preview_png(raw, report_icc=notices.append)
    assert notices == [{'profile': 'Display P3'}]
    assert bounds == [-60, -60, 60, 60]
    managed = rgba(picture)
    np.testing.assert_array_equal(managed[..., :3], PALETTE)
    with template_grid.native_raster(raw, manage_icc=True) as native:
        for y in range(4):
            np.testing.assert_array_equal(native.row(np.arange(4), np.full(4, y)), managed[y])
    legacy, _ = template_grid.preview_png(raw)
    assert not np.array_equal(rgba(legacy), managed)


def test_colour_input_http_contract(tmp_path):
    backend = webui.Backend(tmp_path, drive_provider=lambda: [])
    with webui.Server(backend, 0) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            image = Image.fromarray(PALETTE)
            for profile, status, notice in ((None, 204, None), (b'invalid', 200, {'fallback': True}),
                                             (SRGB.tobytes(), 200, {'profile': 'sRGB built-in'})):
                with closing(http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)) as conn:
                    conn.request('POST', '/api/colour-input', png(image, profile), {'Content-Type': 'image/png'})
                    response = conn.getresponse()
                    body = response.read()
                    assert response.status == status
                    if notice:
                        assert json.loads(response.getheader('X-Discprobe-ICC')) == notice
                        np.testing.assert_array_equal(rgba(body)[..., :3], PALETTE)
                    else:
                        assert not body and response.getheader('X-Discprobe-ICC') is None
        finally:
            server.shutdown()
            thread.join(timeout=10)
