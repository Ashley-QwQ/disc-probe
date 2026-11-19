"""Offline brand/font integration and distribution contracts (no optical devices)."""
import hashlib
import http.client
from html.parser import HTMLParser
import importlib.util
from pathlib import Path
import threading
import zipfile

from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(Path(name).stem, ROOT / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(not Path('C:/Windows/Fonts/ariblk.ttf').is_file(), reason='Windows local fallback calibration')
def test_title_metric_css_rebuild_and_title_only_scope():
    import re
    script = load('tools/align_title_fonts.py')
    css, report = script.generate()
    for product in ('discprobe', 'disclab'):
        assert (ROOT / product / 'web/fonts/titles.css').read_text(encoding='utf-8') == css
    # Existing selector scope is the contract: no body/layout/color declarations.
    old = (ROOT / 'tests/fixtures/title-fonts-before.css').read_text(encoding='utf-8')
    strip_comments = lambda text: re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    old_rule = re.findall(r'([^{}]+)\{([^{}]*)\}', strip_comments(old))[-1]
    new_rule = re.findall(r'([^{}]+)\{([^{}]*)\}', strip_comments(css))[-1]
    assert tuple(part.strip() for part in new_rule) == tuple(part.strip() for part in old_rule)
    # Override percentages must account for size-adjust; effective metrics are
    # the original Archivo metrics for every declared fallback width.
    for block in re.findall(r'@font-face\s*\{([^}]+)\}', css):
        values = dict(re.findall(r'([\w-]+):\s*([\d.]+)%;', block))
        scale = float(values['size-adjust']) / 100
        for metric, expected in report['target_em'].items():
            effective = float(values[metric + '-override']) / 100 * scale
            assert effective == pytest.approx(expected, abs=1e-7)


def test_title_font_covers_all_interface_chinese_and_level_one():
    from fontTools.ttLib import TTFont
    script = load('tools/subset_title_font.py')
    font = TTFont(ROOT / 'discprobe/web/fonts' / script.OUTPUT)
    cmap = font.getBestCmap()
    missing = script.required_characters() - set(map(chr, cmap))
    assert not missing, 'Rebuild title font: missing ' + ''.join(sorted(missing))
    assert len(script.gb2312_level_one()) == 3755
    assert not set(map(ord, 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789')) & cmap.keys()
    assert font['OS/2'].usWeightClass == 900
    assert font['name'].getDebugName(1) == 'Disc Title SC'
    for name in (script.OUTPUT, 'titles.css', 'OFL-SourceHanSans.txt'):
        assert (ROOT / 'disclab/web/fonts' / name).read_bytes() == (ROOT / 'discprobe/web/fonts' / name).read_bytes()


@pytest.mark.parametrize('product', ['probe', 'lab', 'neo'])
def test_icons_have_required_frames_and_png_sizes(product):
    folder = ROOT / 'discprobe/web/brand' / product
    for name, sizes in [('favicon.ico', {16, 32, 48}), (f'disc-{product}.ico', {16, 24, 32, 48, 64, 128, 256})]:
        icon = Image.open(folder / name)
        assert icon.ico.sizes() == {(s, s) for s in sizes}
        for size in sizes:
            frame = icon.ico.getimage((size, size))
            assert frame.mode == 'RGBA' and frame.getbbox()
    for size in (64, 128, 256, 512):
        assert Image.open(folder / f'disc-{product}-{size}.png').size == (size, size)
    assert Image.open(folder / 'apple-touch-icon.png').size == (180, 180)
    if product == 'lab':
        for file in folder.iterdir():
            assert file.read_bytes() == (ROOT / 'disclab/web/brand/lab' / file.name).read_bytes()


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'link':
            attrs = dict(attrs)
            self.links[attrs.get('rel')] = attrs.get('href')


def test_every_page_has_product_icons_and_offline_title_styles():
    script = load('tools/subset_title_font.py')
    for page in script.web_sources():
        if page.suffix != '.html':
            continue
        links = Links(page.read_text(encoding='utf-8')).links
        product = 'lab' if page.is_relative_to(ROOT / 'disclab') else 'probe'
        web = ROOT / ('disclab/web' if product == 'lab' else 'discprobe/web')
        for rel, name in [('icon', 'favicon.ico'), ('apple-touch-icon', 'apple-touch-icon.png')]:
            href = links[rel]
            path = web / href.lstrip('/') if href.startswith('/') else page.parent / href
            assert path.resolve() == web / f'brand/{product}/{name}', page
            assert path.is_file()
        if page.name != 'samples.html':
            assert 'fonts/titles.css' in page.read_text(encoding='utf-8'), page


def test_phone_can_load_new_assets_without_desk_session(tmp_path):
    from discprobe import webui
    backend = webui.Backend(tmp_path, drive_provider=lambda: [])
    server = webui.Server(backend, 0, lan=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for path in ('/fonts/titles.css', '/fonts/SourceHanSansSC-Heavy-subset.woff2',
                     '/brand/probe/favicon.ico', '/brand/probe/apple-touch-icon.png'):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
            connection.request('GET', path)
            response = connection.getresponse()
            assert response.status == 200, path
            assert response.read() == (ROOT / 'discprobe/web' / path.lstrip('/')).read_bytes()
            assert not response.getheader('Set-Cookie')
            connection.close()
        for path in ('/api/state', '/home/', '/brand/build_marks.py', '/fonts/OFL-SourceHanSans.txt'):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
            connection.request('GET', path)
            response = connection.getresponse()
            assert response.status == 403, path
            response.read()
            connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_release_inventory_and_real_package_bytes(tmp_path, monkeypatch):
    release = load('tools/release.py')
    backend = load('_build_backend.py')
    winpack = load('tools/build_winpack.py')
    manifest = release.brand_inventory(ROOT)
    assert len([p for p in manifest if p['file'].endswith('.svg')]) == 24
    assert len([p for p in manifest if p['file'].endswith('.ico')]) == 8
    assert len([p for p in manifest if p['file'].endswith('.woff2')]) == 2
    # Small real wheel/sdist fixture containing every brand file and its licenses.
    core_paths = [p['file'] for p in manifest if p['file'].startswith('discprobe/')]
    extras = ['tools/export_brand_icons.py', 'tools/subset_title_font.py', 'STYLE.md', 'DESIGN.md']
    required = ['pyproject.toml', '_build_backend.py', 'LICENSE', 'README.md', 'README.en.md',
                'discprobe/version.py', 'docs/API_VERSIONING.md', 'INSTALL-linux.md',
                'tests/data/bd_discussion_samples/local_uj272_bd_zones.csv']
    fixture = tmp_path / 'fixture'
    for name in core_paths + extras + required:
        target = fixture / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    monkeypatch.setattr(backend, 'ROOT', fixture)
    wheel = tmp_path / backend.build_wheel(tmp_path)
    sdist = tmp_path / backend.build_sdist(tmp_path)
    with zipfile.ZipFile(wheel) as archive:
        for name in core_paths:
            assert archive.read(name) == (ROOT / name).read_bytes()
        for name in extras[:2]:
            assert archive.read('discprobe/_' + name) == (ROOT / name).read_bytes()
    import tarfile
    with tarfile.open(sdist) as archive:
        for name in core_paths + extras:
            assert archive.extractfile(f'{backend.identity()}/{name}').read() == (ROOT / name).read_bytes()
    # The full bundle uses SOURCE and this same copy/archive machinery.
    assert {'discprobe', 'tools', 'STYLE.md', 'DESIGN.md'} <= set(winpack.SOURCE)
    archive_path = tmp_path / 'full-brand-payload.zip'
    inventory = release.zip_package(ROOT, [ROOT / name for name in core_paths + extras], archive_path, 'disc-probe')
    with zipfile.ZipFile(archive_path) as archive:
        for item in inventory:
            assert hashlib.sha256(archive.read(item['file'])).hexdigest() == item['sha256']
    lab = [ROOT / p['file'] for p in manifest if p['file'].startswith('disclab/')]
    release.zip_package(ROOT / 'disclab', lab, tmp_path / 'lab-brand.zip', 'disclab')
    with zipfile.ZipFile(tmp_path / 'lab-brand.zip') as archive:
        assert archive.read('disclab/web/brand/lab/favicon.ico') == (ROOT / 'disclab/web/brand/lab/favicon.ico').read_bytes()
    from disclab.package import build
    with zipfile.ZipFile(build(tmp_path / 'standalone-lab.zip')) as archive:
        for path in lab:
            assert archive.read(path.relative_to(ROOT).as_posix()) == path.read_bytes()
