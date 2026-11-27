"""Hardware-free checks of early generator output and worker selection."""
import io
import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch, Mock

import pytest
from discprobe import __main__ as cli, imagedisc as image


@pytest.mark.parametrize("command", ["image", "random", "rings", "calib", "tiles", "beacons", "calibdisc", "disexport", "cdprobe", "spokes"])
def test_preparation_precedes_generator(command):
    def generate(args):
        assert "Preparing the design" in output.getvalue()
    # Replace parsing only: exercise the real dispatch without image files or devices.
    import argparse
    parser = Mock()
    parser.parse_args.return_value = argparse.Namespace(func=generate, media="dvd")
    with patch.object(cli, "_build_parser", return_value=(parser, Mock(), {"cd": {}, "bd": {}})), patch("sys.stdout", new_callable=io.StringIO) as output:
        cli._main([command])


def test_worker_message_precedes_slow_setup():
    # Stop at preallocation, before any worker could start or write an image.
    with patch.dict(os.environ, DISCPROBE_WORKERS="3"), patch.object(image, "PARALLEL_MIN_SECTORS", 1), patch("builtins.open", side_effect=OSError("stop before writing")), patch("sys.stdout", new_callable=io.StringIO) as output:
        assert image.workers() == 3
        with pytest.raises(OSError, match="stop before writing"):
            next(image._write_chunks("unused.iso", {}, [(0, 32)], 0))
        assert "Starting 3 worker processes (DISCPROBE_WORKERS=3)" in output.getvalue()
    with patch.dict(os.environ, DISCPROBE_WORKERS="1"):
        assert image.workers() == 1


def test_burn_page_recorded_events_and_words():
    node = shutil.which("node")
    if not node:
        pytest.skip("node unavailable")
    script = Path(__file__).with_name("test_burn_page.cjs")
    result = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
