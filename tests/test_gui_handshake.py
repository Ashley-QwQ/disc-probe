"""Core/GUI compatibility and packaging checks; no device enumeration or reads."""
import http.client
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile

from discprobe import api, webui
from discprobe.__main__ import _build_parser
from discprobe.version import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_handshake_smoke():
    """Also runs in the CLI's existing zero-argument selftest loader."""
    _, manifest = api.load_manifest(api.BUNDLED_GUI)
    assert not api.check_manifest(manifest)
    assert not api.api_matches('2.0', manifest['required_api'])
    assert api.version_payload()['core_version'] == __version__


class HandshakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        _, self.manifest = api.load_manifest(api.BUNDLED_GUI)

    def pack(self, manifest=None):
        gui = self.root / 'gui'
        (gui / 'home').mkdir(parents=True, exist_ok=True)
        (gui / 'home/index.html').write_text('<h1>External GUI</h1>', encoding='utf-8')
        (gui / 'gui.json').write_text(json.dumps(self.manifest if manifest is None else manifest), encoding='utf-8')
        return gui

    def server(self, gui=None):
        backend = webui.Backend(self.root, drive_provider=lambda: [])
        server = webui.Server(backend, 0, gui=gui)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def close():
            server.shutdown(); thread.join(); server.server_close()
        self.addCleanup(close)
        return server

    def get(self, server, path):
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
        try:
            conn.request('GET', path)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_payload_http_and_cli_are_identical(self):
        payload = api.version_payload()
        self.assertEqual(payload['core_version'], __version__)
        self.assertEqual(payload['api_version'], '1.0')
        self.assertEqual(payload['supported_older_api_majors'], [])
        self.assertEqual(len(payload['capabilities']), len(set(payload['capabilities'])))
        self.assertTrue(set(self.manifest['required_capabilities']) <= set(payload['capabilities']))
        status, body = self.get(self.server(), '/api/version')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), payload)
        command = subprocess.run([sys.executable, '-B', '-m', 'discprobe', 'version', '--json'],
                                 cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(command.stdout), payload)

    def test_manifest_schema(self):
        gui = self.pack()
        self.assertEqual(api.load_manifest(gui)[1], self.manifest)
        for update in ({'name':''}, {'gui_version':1}, {'required_api':'^1'},
                       {'required_api':'>=1.0junk <2'}, {'required_capabilities':'state'},
                       {'required_capabilities':['state', 'state']}, {'optional_capabilities':['state']},
                       {'optional_capabilities':[False]}):
            with self.subTest(update=update):
                self.pack({**self.manifest, **update})
                with self.assertRaises(ValueError): api.load_manifest(gui)
        for value in ([], None, {'name':'other'}):
            (gui / 'gui.json').write_text(json.dumps(value), encoding='utf-8')
            with self.assertRaises(ValueError): api.load_manifest(gui)

    def test_ranges_and_mismatched_major(self):
        for version, expected in [('1.0', True), ('1.19', True), ('0.9', False), ('2.0', False), ('1.0.1', False)]:
            self.assertEqual(api.api_matches(version, '>=1.0 <2'), expected)
        for value, phrase in [('0.9', 'update the core'), ('2.0', 'update the GUI')]:
            with self.assertRaisesRegex(ValueError, phrase):
                api.check_manifest(self.manifest, {**api.version_payload(), 'api_version':value})
        bad = {**self.manifest, 'required_api':'>=2.0 <3'}
        with self.assertRaisesRegex(ValueError, 'API'):
            self.server(self.pack(bad))

    def test_missing_required_and_optional(self):
        payload = api.version_payload()
        payload['capabilities'].remove('geo')
        with self.assertRaisesRegex(ValueError, 'geo'): api.check_manifest(self.manifest, payload)
        payload = api.version_payload()
        payload['capabilities'].remove('templates')
        self.assertEqual(api.check_manifest(self.manifest, payload), {'templates'})
        # Checks return fresh lists; a caller cannot mutate the core registry.
        self.assertIn('templates', api.version_payload()['capabilities'])

    def test_gui_option_serves_selected_assets_and_manifest(self):
        gui = self.pack()
        args = _build_parser()[0].parse_args(['webui', '--gui', str(gui)])
        self.assertEqual(args.gui, str(gui))
        server = self.server(gui)
        self.assertEqual(self.get(server, '/home/'), (200, b'<h1>External GUI</h1>'))
        self.assertEqual(json.loads(self.get(server, '/gui.json')[1]), self.manifest)
        self.assertEqual(self.get(server, '/../version.py')[0], 404)

    def test_gui_option_invalid_stops_before_listening(self):
        command = subprocess.run([sys.executable, '-B', '-m', 'discprobe', 'webui', '--gui', str(self.root)],
                                 cwd=ROOT, capture_output=True, timeout=20)
        self.assertNotEqual(command.returncode, 0)
        self.assertIn(b'gui.json', command.stderr)
        self.assertNotIn(b'Traceback', command.stderr)

    def test_wheel_contains_runtime_files(self):
        spec = importlib.util.spec_from_file_location('discprobe_test_builder', ROOT / '_build_backend.py')
        backend = importlib.util.module_from_spec(spec); spec.loader.exec_module(backend)
        filename = backend.build_wheel(self.root)
        with zipfile.ZipFile(self.root / filename) as wheel:
            names = set(wheel.namelist())
            for name in ('discprobe/web/gui.json', 'discprobe/web/home/index.html',
                         'discprobe/web/home/handshake.mjs', 'discprobe/web/fonts/MonaSans-VF.ttf',
                         'discprobe/web/home/sim/textures.bin', 'discprobe/_presets/catalogue.json',
                         'discprobe/_data/community-calibrations/dis-github.json',
                         'discprobe/_tools/burn_imapi.ps1', 'discprobe/simulate_lut.npz'):
                self.assertIn(name, names)
            metadata = wheel.read(next(n for n in names if n.endswith('.dist-info/METADATA'))).decode()
            for dependency in ('numpy', 'Pillow', 'scipy', 'opencv-python'):
                self.assertIn('Requires-Dist: ' + dependency, metadata)
            entries = wheel.read(next(n for n in names if n.endswith('/entry_points.txt'))).decode()
            self.assertIn('disc-probe = discprobe.__main__:main', entries)
