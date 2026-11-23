"""Read embedded ICC colour into the editor's existing 8-bit sRGB raster."""
from __future__ import annotations

from functools import lru_cache
import io
import struct

import numpy as np
from PIL import Image, ImageCms, ImageOps

WEB_FORMATS = ('PNG', 'JPEG', 'WEBP', 'BMP')
WEB_TYPES = ('image/png', 'image/jpeg', 'image/webp', 'image/bmp')
WEB_BYTES = 24 * 2**20
WEB_PIXELS = 36_000_000
FALLBACK = 'Could not use the embedded ICC profile. The picture was read as sRGB.'
CONVERTED = 'Converted from {profile} to sRGB.'


def _tags(profile):
    count, = struct.unpack_from('>I', profile, 128)
    if count > (len(profile) - 132) // 12:
        raise ValueError('invalid ICC tag table')
    tags = {}
    for name, offset, size in struct.iter_unpack('>4sII', profile[132:132 + 12*count]):
        if offset + size > len(profile):
            raise ValueError('invalid ICC tag bounds')
        tags[name] = memoryview(profile)[offset:offset + size]
    return tags


def _fixed(data, count, offset=8):
    return np.array(struct.unpack_from(f'>{count}i', data, offset)) / 65536


def _matrix(tags):
    columns = [tags[name] for name in (b'rXYZ', b'gXYZ', b'bXYZ')]
    if any(column[:4] != b'XYZ ' for column in columns):
        raise ValueError('invalid ICC colourant')
    return np.stack([_fixed(column, 3) for column in columns], axis=1)


def _curve(data):
    """Evaluate an ICC curve for all unsigned 16-bit source codes."""
    x = np.linspace(0, 1, 65536)
    if data[:4] == b'curv':
        count, = struct.unpack_from('>I', data, 8)
        if count == 0:
            return x
        samples = np.frombuffer(data, dtype='>u2', offset=12, count=count)
        if count == 1:
            return x ** (samples[0] / 256)
        return np.interp(x, np.linspace(0, 1, count), samples / 65535)
    if data[:4] != b'para':
        raise ValueError('unsupported ICC tone curve')
    kind, = struct.unpack_from('>H', data, 8)
    if kind > 4:
        raise ValueError('unknown ICC parametric tone curve')
    g, *params = _fixed(data, (1, 3, 4, 5, 7)[kind], 12)
    if g <= 0:
        raise ValueError('invalid ICC gamma')
    if kind == 0:
        return x ** g
    a, b, *rest = params
    if kind <= 2:
        c = rest[0] if rest else 0
        return np.maximum(a*x + b, 0) ** g + c
    c, d, *offsets = rest
    e, f = offsets or (0, 0)
    return np.where(x >= d, np.maximum(a*x + b, 0) ** g + e, c*x + f)


@lru_cache(maxsize=1)
def _srgb():
    return ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))


class _HighDepthPNG:
    """Use unchanged PNG samples and ICC matrix/curve tags. Pillow's RGB modes are 8-bit."""

    def __init__(self, raw, profile, space):
        import cv2

        self.grey = space == 'GRAY'
        self.curves = self.matrix = None
        if profile:
            tags = _tags(profile)
            if any(name[:3] in (b'A2B', b'D2B') for name in tags):
                raise ValueError('16-bit ICC lookup table is unsupported')
            names = (b'kTRC',) if self.grey else (b'rTRC', b'gTRC', b'bTRC')
            self.curves = [_curve(tags[name]) for name in names]
            if not all(np.isfinite(curve).all() for curve in self.curves):
                raise ValueError('invalid ICC tone curve')
            if not self.grey:
                self.matrix = np.linalg.solve(_matrix(_tags(_srgb().tobytes())), _matrix(tags))
        try:
            self.samples = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_UNCHANGED)
        except cv2.error as exc:
            raise ValueError('could not read 16-bit PNG samples') from exc
        if self.samples is None or self.samples.dtype != np.uint16:
            raise ValueError('could not read 16-bit PNG samples')
        self.has_alpha = self.samples.ndim == 3 and self.samples.shape[2] in (2, 4)

    def band(self, box):
        left, top, right, bottom = box
        samples = self.samples[top:bottom, left:right]
        rgb = ((samples if samples.ndim == 2 else samples[..., 0])[..., None]
               if self.grey else samples[..., 2::-1])
        result = np.empty((*samples.shape[:2], 4), np.uint8)
        if self.curves is None:
            result[..., :3] = _scale16(rgb)
        else:
            linear = np.stack([curve[rgb[..., i]] for i, curve in enumerate(self.curves)], axis=-1)
            if self.matrix is not None:
                linear = linear @ self.matrix.T
            linear = np.clip(linear, 0, 1)
            srgb = np.where(linear <= .0031308, 12.92*linear, 1.055*linear**(1/2.4) - .055)
            result[..., :3] = np.rint(srgb * 255).astype(np.uint8)
        result[..., 3] = _scale16(samples[..., -1]) if self.has_alpha else 255
        return Image.fromarray(result)

    def bounds(self):
        height, width = self.samples.shape[:2]
        if not self.has_alpha:
            return 0, 0, width, height
        rows, cols = np.zeros(height, bool), np.zeros(width, bool)
        for top in range(0, height, 128):
            band = self.samples[top:top + 128, :, -1] > 128
            rows[top:top + len(band)] = band.any(axis=1)
            cols |= band.any(axis=0)
        y, x = np.flatnonzero(rows), np.flatnonzero(cols)
        return (int(x[0]), int(y[0]), int(x[-1]) + 1, int(y[-1]) + 1) if len(y) else None


def _scale16(samples):
    return ((samples.astype(np.uint32) + 128) // 257).astype(np.uint8)


class EmbeddedICC:
    """Prepare one conversion per image, then apply it in strips if needed."""

    def __init__(self, image, stream, *, enabled=True):
        self.image = image
        self.profile = None
        self.fallback = enabled and 'icc_profile' in image.info
        self.transform = self.high_depth = None
        if not self.fallback:
            return
        data = image.info['icc_profile']
        depth = kind = None
        if image.format == 'PNG':
            stream.seek(24)  # PNG signature, chunk header and IHDR width/height.
            depth, kind = stream.read(2)
        grey = kind in (0, 4)
        try:
            profile = ImageCms.ImageCmsProfile(io.BytesIO(data))
            space = profile.profile.xcolor_space.strip()
            mode = {'RGB': 'RGB', 'GRAY': 'L', 'CMYK': 'CMYK', 'Lab': 'LAB'}[space]
            if image.mode != mode and ({mode, image.mode} & {'CMYK', 'LAB'}):
                raise ValueError('ICC profile does not match image channels')
            self.transform = ImageCms.buildTransform(profile, _srgb(), mode, 'RGB',
                                                     renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC)
            self.mode = mode
            if depth == 16:
                if space != ('GRAY' if grey else 'RGB'):
                    raise ValueError('ICC profile does not match PNG channels')
                stream.seek(0)
                self.high_depth = _HighDepthPNG(stream.read(), data, space)
            name = profile.profile.profile_description or 'ICC'
        except (ImageCms.PyCMSError, ImportError, OSError, KeyError, TypeError, ValueError,
                struct.error, np.linalg.LinAlgError):
            self.transform = self.high_depth = None
            if depth == 16:
                stream.seek(0)
                self.high_depth = _HighDepthPNG(stream.read(), None, 'GRAY' if grey else 'RGB')
            return
        self.profile = (' '.join(''.join(c for c in name if c.isprintable()).split()) or 'ICC')[:120]
        self.fallback = False

    def band(self, box=None):
        if self.high_depth is not None:
            return self.high_depth.band(box or (0, 0, *self.image.size))
        block = self.image.crop(box) if box is not None else self.image
        if self.transform is None:
            return block.convert('RGBA')
        result = ImageCms.applyTransform(block.convert(self.mode), self.transform).convert('RGBA')
        if 'A' in block.getbands() or 'transparency' in block.info:
            result.putalpha(block.convert('RGBA').getchannel('A'))
        return result

    def picture(self):
        if self.transform is None and self.high_depth is None:
            return ImageOps.exif_transpose(self.image).convert('RGBA')
        if self.high_depth is None:
            result = self.band()
        else:
            result = Image.new('RGBA', self.image.size)
            for top in range(0, result.height, 128):
                result.paste(self.band((0, top, result.width, min(top + 128, result.height))), (0, top))
        result.info['exif'] = self.image.getexif().tobytes()
        result = ImageOps.exif_transpose(result)
        result.info.clear()
        return result

    def notice(self):
        if self.profile:
            return {'profile': self.profile}
        return {'fallback': True} if self.fallback else None


def web_picture(raw):
    with io.BytesIO(raw) as stream, Image.open(stream, formats=WEB_FORMATS) as image:
        if image.width * image.height > WEB_PIXELS:
            raise ValueError('image exceeds 36 million pixels')
        conversion = EmbeddedICC(image, stream)
        notice = conversion.notice()
        if notice is None:
            return None, None
        picture = conversion.picture()
        output = io.BytesIO()
        picture.save(output, 'PNG', compress_level=3, icc_profile=None)
        return output.getvalue(), notice
