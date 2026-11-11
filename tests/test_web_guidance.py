"""No drive access: exercise browser advice and failed job transport in Node."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_web_guidance():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is not installed')
    subprocess.run([node, str(Path(__file__).with_suffix('.mjs'))], check=True)


def test_no_dead_capability_copy():
    home = Path(__file__).resolve().parents[1] / 'discprobe/web/home'
    design = (home / 'design.js').read_text(encoding='utf-8')
    calibrate = (home / 'calibrate.js').read_text(encoding='utf-8')
    burn = (home / 'burn.js').read_text(encoding='utf-8')
    for stale in ('burnLater:', 'nextLater:', 'fineGrid:', 'one-off patch'):
        assert stale not in design
    assert 'phone-link.js' not in calibrate
    assert 'placeholder' not in burn
    assert "!ctx.photograph" in burn
    assert 'measurementRecovery(flow)' in calibrate
    assert 'error.result' in calibrate
    preview = (home / 'preview.js').read_text(encoding='utf-8')
    assert 'readNote:' not in preview and 'folderLater:' not in preview
    assert 'ctx.showInFolder ?' in preview
