"""Thin local-service adapter; all allocation stays in discfiles.plan."""
from pathlib import Path
import json
import math

from . import discfiles


def source_folder(value):
    if not isinstance(value, str) or not value or len(value) > 1024 or '\0' in value or value.startswith('-'):
        raise ValueError('请输入本机文件夹路径 / enter a local folder path')
    path = Path(value).absolute()
    if str(path).startswith(('\\\\', '//')):
        raise ValueError('不支持网络文件夹 / network folders are unsupported')
    return str(path)


def request(root, payload):
    from .webui import local_path
    if not isinstance(payload, dict) or set(payload) - {'folder', 'files_at', 'margin', 'writable_sectors', 'geo', 'r_max', 'media'}:
        raise ValueError('Invalid files layout request')
    geometry = None
    if payload.get('geo'):
        from . import guide
        from .photo import photo_l, shifted_u
        path = guide.resolve_geo(local_path(root, payload['geo']), 'dvd')
        geometry = json.loads(Path(path).read_text(encoding='utf-8'))['fit']
        if geometry.get('media', 'dvd') != 'dvd' or (geometry.get('model') == 'dis_import' and not geometry.get('image_compatible')):
            raise ValueError('需要可用于出图的 DVD 几何 / compatible DVD geometry required')
        geometry = {**geometry, 'u': shifted_u(geometry, photo_l(path, media='dvd'))}
    total = payload.get('writable_sectors')
    if total is None and geometry:
        from .imagedisc import sectors_to_radius
        r_max = float(payload.get('r_max', 56))
        if not math.isfinite(r_max) or not 1 <= r_max <= 58:
            raise ValueError('Invalid outer radius')
        total = min(discfiles.MAX_SECTORS, geometry.get('capacity_sectors') or
                    sectors_to_radius(geometry['u'], geometry['v'], geometry['bit_nm_assumed'], r_max+.6))
    if total is None:
        raise ValueError('请先选择实测几何，或填写空白盘的可写扇区数 / geometry or writable sectors required')
    layout = discfiles.plan(source_folder(payload.get('folder')), payload.get('files_at', 'inner'), total,
                            margin=payload.get('margin'), geometry=geometry, media=payload.get('media', 'dvd'))
    return {**layout.as_dict(), 'folder': str(layout.folder), 'radius_source': 'measured' if geometry else 'nominal'}
