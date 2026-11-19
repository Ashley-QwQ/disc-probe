"""Offline regressions from the first-tier review."""

from concurrent.futures import ThreadPoolExecutor
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from threading import Event
import time
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from discprobe import __main__ as cli
from discprobe import burner, imagedisc, iso9660, timing, ui, webui
from discprobe.drive_lock import drive_operation
from discprobe.scsi import ScsiResult
from tests.test_fault_fixes import Disc


@pytest.fixture(autouse=True)
def private_drive_state(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


@pytest.mark.skipif(os.name != "nt" or not shutil.which("powershell"), reason="Windows PowerShell required")
def test_r2_machine_powershell_respects_another_process_drive_lock(tmp_path):
    helper = Path(cli.__file__).resolve().parents[1] / "tools" / "burn_imapi.ps1"
    # Machine mode rejects -Verify before it can invoke IMAPI. Even when the
    # lock is broken, this test can never reach a recorder.
    command = ["powershell", "-NoProfile", "-NonInteractive", "-File", str(helper),
               "-Drive", "X:", "-Machine", "-Verify"]
    with drive_operation("X:", "timing"):
        result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, errors="replace", timeout=15)
    assert result.returncode != 0
    # PowerShell wraps error records at the console width, so compare with whitespace collapsed.
    assert "This drive is in use by another window or command" in " ".join(result.stderr.split()), result.stderr
    from discprobe.drive_lock import child_env
    with drive_operation("X:", "burn"):
        delegated = subprocess.run(command, cwd=tmp_path, env=child_env("X:"), capture_output=True,
                                   text=True, errors="replace", timeout=15)
    assert "Machine mode does not accept legacy session options" in " ".join(delegated.stderr.split()), delegated.stderr


_HOLD_CALIBRATION = """
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from discprobe import calibrate, __main__ as cli

def read_disc(*argv, **kwargs):
    marker = Path(os.environ['DP_TEST_CALIBRATION_READY'])
    marker.touch()
    for _ in range(600):
        if marker.with_suffix('.stop').exists():
            break
        time.sleep(.05)
    return SimpleNamespace(returncode=0, stdout='{"disc":{"present":false}}', stderr='')

calibrate.subprocess.run = read_disc
cli.main(sys.argv[1:])
"""

_SAFE_CONTENDER = """
import sys
from discprobe import __main__ as cli, burner, device, eraser

def no_hardware(*args, **kwargs):
    raise SystemExit('test fixture forbids opening a real drive')

cli._open = burner.adapter = device.Device = eraser.adapter = no_hardware
device.raise_priority = lambda: None
cli.main(sys.argv[1:])
"""


@pytest.mark.parametrize('background', ['cli', 'web'])
def test_r2_cli_refuses_while_calibration_owns_drive(tmp_path, monkeypatch, background):
    marker = tmp_path / 'ready'
    monkeypatch.setenv('DP_TEST_CALIBRATION_READY', str(marker))
    # Keep the before/after subprocesses on the same source package.
    monkeypatch.setenv('PYTHONPATH', str(Path(cli.__file__).resolve().parents[1]))
    image = finished_image(tmp_path)
    options = [sys.executable, '-X', 'utf8', '-B', '-c', _HOLD_CALIBRATION, 'calibrate', '--drive', 'X:']
    backend = job = child = None
    try:
        if background == 'cli':
            child = subprocess.Popen(options, cwd=tmp_path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            def runner(_argv, *, env, cwd, stdout):
                process = subprocess.Popen(options, env=env, cwd=cwd, stdout=stdout, stderr=stdout)
                return SimpleNamespace(wait=process.wait, cancel=process.terminate, close=lambda: None)
            backend = webui.Backend(tmp_path, drive_provider=lambda: [dict(id='X:')], runner=runner)
            ident = backend.start(dict(action='calibrate', drive='X:', args={}))['job']
            job = backend.jobs[ident]
        until = time.monotonic() + 12
        while not marker.exists() and time.monotonic() < until:
            time.sleep(.05)
        assert marker.exists(), 'calibration did not reach its injected disc read'
        results = {}
        for command, args in {'timing': [], 'geo': [], 'erase': [], 'info': [],
                              'burn': ['--iso', str(image), '--yes-write']}.items():
            result = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-c', _SAFE_CONTENDER,
                command, '--drive', 'x:', *args], cwd=tmp_path, capture_output=True,
                text=True, encoding='utf-8', timeout=15)
            results[command] = (result.returncode, result.stderr.strip())
        assert all(code == 75 and 'action: calibrate' in err for code, err in results.values()), results
    finally:
        marker.with_suffix('.stop').touch()
        if child is not None:
            child.wait(timeout=10)
        if job is not None:
            assert job.finished.wait(10)
        if backend is not None:
            backend.close()


def test_r3_concurrent_iso_does_not_delete_other_output(tmp_path):
    image = tmp_path / "same.iso"
    marker = Path(str(image) + iso9660.UNFINISHED)
    first_bytes = b"first writer" * 128

    def second():
        with ui._whole_or_gone(str(image)):
            image.write_bytes(b"second writer")

    with ui._whole_or_gone(str(image)), ThreadPoolExecutor(max_workers=1) as pool:
        image.write_bytes(first_bytes)
        try:
            pool.submit(second).result(timeout=5)
        except (OSError, ValueError):
            pass
        assert image.read_bytes() == first_bytes
        assert marker.exists()
    assert not marker.exists()


def finished_image(tmp_path):
    image = tmp_path / "image.iso"
    image.write_bytes(bytes(64 * 2048))
    # This mirrors the verification record for a successfully checked image.
    # The old code ignores it, so it can be used in the pre-change test as well.
    Path(str(image) + '.verification.json').write_text(json.dumps({
        "status": "passed", "size": image.stat().st_size, "mtime_ns": image.stat().st_mtime_ns}), encoding="utf-8")
    return image


def test_r4_log_failure_precedes_erase(tmp_path):
    image = finished_image(tmp_path)
    Path(str(image) + ".burn.jsonl").mkdir()
    recorder = Mock()
    recorded = dict(media="dvd", rewritable=True, blank=False, capacity_sectors=100, speeds_x=[8])
    blank = dict(recorded, blank=True, free_sectors=100)
    recorder.inspect.side_effect = [recorded, recorded, recorded, blank, blank]
    recorder.erase.return_value = {}
    with pytest.raises((OSError, burner.BurnError), match="log|Permission|denied"):
        burner.burn("X:", image, yes_write=True, erase=True, recorder=recorder)
    recorder.erase.assert_not_called()
    recorder.write.assert_not_called()


def geometry(tmp_path, *, unvalidated=False):
    run = tmp_path / "geo-X-20261118-120000"
    run.mkdir()
    geo = run / "summary.json"
    fit = dict(u=180000, v=5.5, bit_nm_assumed=133.3, measured_span_mm=[24, 57])
    if unvalidated:
        fit.update(completion_status="correction_unvalidated", correction_file="correction.json",
                   varying_pitch=True, correction_validation=dict(independent_rms_deg=5))
        (run / "correction.json").write_text(json.dumps(dict(radius_valid_mm=[24, 57],
            spline=dict(t=[24, 24, 24, 24, 57, 57, 57, 57], c=[2, 2, 2, 2], k=3))), encoding="utf-8")
    geo.write_text(json.dumps(dict(fit=fit)), encoding="utf-8")
    return geo


def image_command(tmp_path, monkeypatch, *, problems=(), unvalidated=False):
    folder = tmp_path / "iso"
    folder.mkdir()
    image = folder / "out.iso"
    geo = geometry(tmp_path, unvalidated=unvalidated)

    def write_iso(path, *_args, **_kwargs):
        path = Path(path)
        path.write_bytes(bytes(64 * 2048))
        spec = path.with_suffix(".image.json")
        spec.write_text("{}", encoding="utf-8")
        return str(spec)

    writer = Mock(side_effect=write_iso)
    monkeypatch.setattr(imagedisc, "grid_design", Mock(return_value=np.zeros((64, 64), bool)))
    monkeypatch.setattr(imagedisc, "write_iso", writer)
    monkeypatch.setattr(imagedisc, "verify_iso", Mock(return_value=list(problems)))
    monkeypatch.setattr(imagedisc, "preview", Mock())
    monkeypatch.setattr(cli, "_image_ready", Mock())
    return image, writer, ["image", "--geo", str(geo), "--output", str(image), "--no-photo-l"]


def test_r5_failed_dvd_self_check_exits_and_blocks_burn(tmp_path, monkeypatch):
    image, _writer, argv = image_command(tmp_path, monkeypatch, problems=["injected bad sector"])
    try:
        result = cli._main(argv)
    except SystemExit as exc:
        result = exc.code
    backend = webui.Backend(tmp_path, drive_provider=lambda: [])
    with pytest.raises(webui.APIError, match="verification|校验"):
        backend.iso_file("iso/out.iso")
    assert result == 1
    assert image.is_file()
    assert json.loads(Path(str(image) + '.verification.json').read_text(encoding="utf-8"))["status"] == "failed"
    recorder = Mock()
    with pytest.raises(burner.BurnError, match="verification|校验"):
        burner.burn("X:", image, yes_write=True, recorder=recorder)
    recorder.inspect.assert_not_called()


def test_r5_missing_record_is_refused_and_passed_record_can_burn(tmp_path):
    image = finished_image(tmp_path)
    recorder = Mock()
    recorder.inspect.return_value = dict(blank=True, media="dvd", free_sectors=100, speeds_x=[8])
    recorder.write.return_value = 8
    options = dict(yes_write=True, recorder=recorder, no_verify=True,
                   state_checker=lambda *_args, **_kwargs: dict(status="completed"))
    assert burner.burn("X:", image, **options)["result"] == "completed"
    recorder.reset_mock()
    Path(str(image) + '.verification.json').unlink()
    with pytest.raises(burner.BurnError, match="verification|校验"):
        burner.burn("X:", image, **options)
    recorder.inspect.assert_not_called()


def test_r6_unvalidated_geo_requires_explicit_opt_in(tmp_path, monkeypatch, capsys):
    _image, writer, argv = image_command(tmp_path, monkeypatch, unvalidated=True)
    with pytest.raises(SystemExit) as rejected:
        cli._main(argv)
    assert rejected.value.code != 0
    assert '角度修正未通过独立检查' in capsys.readouterr().err
    writer.assert_not_called()
    cli._main([*argv, "--allow-unvalidated-correction"])
    assert isinstance(writer.call_args.kwargs["correction"], imagedisc.SplineCorrection)


def test_r7_corrupt_partial_final_block_is_sampled(tmp_path):
    image = tmp_path / "tail.iso"
    image.write_bytes(bytes(33 * 2048))
    medium = bytes(32 * 2048) + bytes([1]) * 2048
    reads = []

    def read(cdb, *, data_len, **_kwargs):
        lba = int.from_bytes(cdb[2:6], "big")
        reads.append((lba, data_len))
        return ScsiResult(0, medium[lba * 2048:lba * 2048 + data_len], None, 0, 0)

    drive = Mock()
    drive.__enter__ = Mock(return_value=drive)
    drive.__exit__ = Mock(return_value=False)
    drive.execute.side_effect = read
    result = burner.verify_image("X:", image, "dvd", Event(), device_factory=lambda _: drive)
    assert reads == [(0, 32768), (16, 32768), (32, 2048)]
    assert result["differing"] == 1 and result["failures"][0]["lba"] == 32


def test_r8_timing_uses_read_back_open_track_end():
    drive = Disc(written=4096, reported=1, track_reported=4096, closed=False)
    probe = timing.TimingProbe(drive, speed_kbs=None, log=lambda *_: None)
    probe.setup()
    assert probe.last_lba == 4095
    assert probe.summary["setup"]["capacity_source"] == "confirmed track recorded end"


def test_r9_same_second_result_dirs_do_not_overwrite(tmp_path, monkeypatch):
    class Fixed(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 18, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(datetime, "datetime", Fixed)
    args = SimpleNamespace(out=tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        paths = list(pool.map(lambda _: Path(cli._outdir(args, "geo", SimpleNamespace(name="X:"))), range(2)))
    for index, path in enumerate(paths):
        cli._write_json(path / "summary.json", {"job": index})
    assert paths[0] != paths[1]
    assert [json.loads((p / "summary.json").read_bytes())["job"] for p in paths] == [0, 1]
