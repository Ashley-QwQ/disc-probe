"""Guard this card's Python verification processes against browser launches."""

import glob
import inspect
import os
from pathlib import Path
import re
import shlex
import sys
from unittest.mock import patch


EXCLUDED = 'b' + 'lind'
BROWSER = re.compile(
    r'(?:^|[/\s"\'=])(?:msedge(?:webview2)?|chrome(?:-headless-shell)?|chromium|firefox|brave|iexplore)'
    r'(?:\.exe)?(?=$|[\s"\'])', re.I)
JS_CHECKS = {
    ('test_editor_pose_swatches', 'test_web_rig_panel_node'),
    ('test_geo_progress', 'test_web_progress_bounds'),
    ('test_geo_unsteady', 'test_page_calibrate_arguments'),
    ('test_lamp_optics', 'test_dither_share_mixes_like_the_burn_cells'),
    ('test_lamp_optics', 'test_document_end_to_end'),
    ('test_lamp_optics', 'test_scheduling'),
    ('test_web_guidance', 'test_start_guide'),
    ('test_web_guidance', 'test_web_guidance'),
}
PATH_CHECKS = {('test_focal_geometry', 'test_frozen_photo_and_video_placement_geometry')}


def _audit(event, args):
    if event in ('socket.connect', 'socket.bind') and isinstance(args[1], tuple) and args[1][1] == 8765:
        raise RuntimeError('VT verification forbids use of port 8765')
    if event in ('open', 'os.listdir', 'os.scandir') and isinstance(args[0], (str, bytes, os.PathLike)):
        if EXCLUDED in os.fsdecode(args[0]).casefold():
            raise RuntimeError('VT verification blocked an excluded path')
    if event in ('webbrowser.open', 'os.startfile', 'os.startfile/2'):
        raise RuntimeError('VT verification forbids desktop launches')
    if event == 'subprocess.Popen':
        executable, raw = args[:2]
    elif event in ('os.exec', 'os.posix_spawn'):
        executable, raw = args[:2]
    elif event == 'os.spawn':
        executable, raw = args[1:3]
    elif event == 'os.system':
        executable, raw = '', os.fsdecode(args[0])
    else:
        return
    command = raw if isinstance(raw, str) else ' '.join(os.fsdecode(a) for a in raw)
    command = command.replace('\\', '/').casefold()
    launch = os.fsdecode(executable or '').replace('\\', '/')
    if BROWSER.search(launch) or BROWSER.search(command) or '.mjs' in command:
        raise RuntimeError('VT verification forbids browser and MJS launches')
    head = re.match(r'^\s*(?:"([^"]+)"|(\S+))', command)
    program = (head[1] or head[2]).rsplit('/', 1)[-1] if head else ''
    if program in ('node', 'node.exe', 'npx', 'npm'):
        # Known selftest commands use Node stdin with a fake DOM, a CJS fake
        # DOM fixture, or a version query.
        rest = [a.strip('"') for a in shlex.split(command, posix=False)[1:]]
        fixture = str(ROOT / 'tests/test_burn_page.cjs').replace('\\', '/').casefold()
        if program in ('npx', 'npm') or rest not in ([], ['--version'], [fixture]):
            raise RuntimeError('VT verification blocked an unreviewed Node entry point')


def _filter_selftest():
    from discprobe import selftest

    original_run = selftest._tests_folder
    original_signature = inspect.signature
    original_glob = glob.glob
    fixture = inspect.Signature([inspect.Parameter('external_fixture', inspect.Parameter.POSITIONAL_OR_KEYWORD)])

    def signature(fn, *args, **kwargs):
        module = getattr(fn, '__module__', '') or ''
        if module.startswith('discprobe_tests_'):
            test = module.removeprefix('discprobe_tests_'), fn.__name__
            if test in JS_CHECKS or test in PATH_CHECKS:
                reason = 'MJS launch disabled' if test in JS_CHECKS else 'excluded input path'
                print(f'  SKIP  {test[0]}::{test[1]} ({reason})')
                return fixture
        return original_signature(fn, *args, **kwargs)

    def safe_glob(*args, **kwargs):
        return [path for path in original_glob(*args, **kwargs) if EXCLUDED not in os.fsdecode(path).casefold()]

    def tests_folder(checker):
        with patch.object(inspect, 'signature', signature), patch.object(glob, 'glob', safe_glob):
            original_run(checker)

    selftest._tests_folder = tests_folder


ROOT = Path(__file__).resolve().parents[3]
sys.addaudithook(_audit)
if sys.orig_argv[-3:] == ['-m', 'discprobe', 'selftest']:
    _filter_selftest()
