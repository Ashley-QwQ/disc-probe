"""Offline DVD session tests. No hardware factories are allowed to reach a device."""
import io
import json
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

import numpy as np

from discprobe import burner, labelsession as S, randomlabel as L, randomdisc, mmc
from discprobe.geo import Ladder
from discprobe.scsi import ScsiResult
from discprobe.sim import SimDrive

ROOT = Path(__file__).resolve().parents[1]
GEO = ROOT / 'evidence/geo/random_disc_summary.json'


class LabelSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.iso = self.root / 'session.iso'
        self.iso.write_bytes(bytes(32 * 2048))

    def test_keep_open_and_append_preflight(self):
        rec = Mock()
        rec.inspect.return_value = dict(media='dvd', blank=True, closed=False,
                                       next_writable=0, free_sectors=100, speeds_x=[4, 8, 16])
        rec.write.return_value = 8
        options = dict(recorder=rec, yes_write=True, no_verify=True)
        result = burner.burn('fake', self.iso, keep_open=True, **options)
        self.assertTrue(result['keep_open'])
        self.assertEqual(rec.write.call_args.kwargs['keep_open'], True)
        rec.inspect.return_value.update(blank=False, next_writable=1640000)
        rec.write.reset_mock()
        result = burner.burn('fake', self.iso, append=True, expect_start=1640000, **options)
        self.assertEqual(result['first_lba'], 1640000)
        self.assertTrue(rec.write.call_args.kwargs['append'])
        for changes in (dict(next_writable=1640016), dict(blank=True), dict(closed=True)):
            saved = rec.inspect.return_value.copy()
            rec.inspect.return_value.update(changes)
            rec.write.reset_mock()
            with self.assertRaises(burner.BurnError):
                burner.burn('fake', self.iso, append=True, expect_start=1640000, **options)
            rec.write.assert_not_called()
            rec.inspect.return_value = saved
        for flags in (dict(append=True), dict(expect_start=123), dict(keep_open=True, append=True, expect_start=123),
                      dict(media='cd', keep_open=True)):
            rec.write.reset_mock()
            with self.assertRaises(burner.BurnError):
                burner.burn('fake', self.iso, **options, **flags)
            rec.write.assert_not_called()

    def test_appended_readback_uses_absolute_lbas_and_relative_file_offsets(self):
        self.iso.write_bytes(bytes(16 * 2048) + bytes([0x66]) * (16 * 2048))
        dev = Mock()
        dev.__enter__ = Mock(return_value=dev)
        dev.__exit__ = Mock(return_value=False)
        seen = []
        def execute(cdb, **kw):
            lba = int.from_bytes(cdb[2:6], 'big')
            seen.append(lba)
            return ScsiResult(0, bytes([0 if lba == 1640000 else 0x66]) * kw['data_len'], None, 0, 1)
        dev.execute.side_effect = execute
        result = burner.verify_image('fake', self.iso, 'dvd', threading.Event(),
                                     start_lba=1640000, device_factory=lambda _: dev)
        self.assertEqual(seen, [1640000, 1640016])
        self.assertEqual((result['ok'], result['differing']), (2, 0))

    def fake_disc(self, state=1, nwa=1640000, valid=True):
        dev = Mock()
        def execute(cdb, **kw):
            data = bytearray(kw['data_len'])
            if cdb[0] == 0x46:
                data[6:8] = (0x11).to_bytes(2, 'big')
            elif cdb[0] == 0x51:
                data[2], data[6] = state, 1
            elif cdb[0] == 0x52:
                self.assertIn(int.from_bytes(cdb[2:6], 'big'), (1, 0xff))
                data[7] = int(valid)
                data[12:16] = nwa.to_bytes(4, 'big')
                data[16:20] = (2298496 - nwa).to_bytes(4, 'big')
            else:
                self.fail('unexpected device command')
            return ScsiResult(0, bytes(data), None, 0, 1)
        dev.execute.side_effect = execute
        dev.__enter__ = Mock(return_value=dev)
        dev.__exit__ = Mock(return_value=False)
        return dev

    def test_label_reads_nwa_through_mmc_and_command(self):
        dev = self.fake_disc()
        self.assertEqual(S.disc_state(dev), (1640000, 2298496))
        args = types.SimpleNamespace(start_lba=None, sectors=2295104, drive='fake', geo=str(GEO),
                                     text='BOX4', output=str(self.iso))
        with patch('discprobe.imapi.ImapiDevice', return_value=dev), patch.object(S, 'write_iso', return_value={'total_sectors':2250000}) as write:
            S.run(args)
        self.assertEqual(write.call_args.args[3:5], (1640000, 2295104))
        for state, valid in ((0, True), (2, True), (1, False)):
            with self.assertRaises(ValueError):
                S.disc_state(self.fake_disc(state=state, valid=valid))

    def test_pending_stops_at_planned_end_and_marks_only_one_sector(self):
        with patch.object(L, 'STOP_SECTORS', 17008):
            randomdisc.write_iso(str(self.iso), label='BOX4', log=lambda *_: None)
        spec = json.loads(self.iso.with_suffix('.image.json').read_text())
        self.assertEqual((spec['state'], spec['total_sectors']), ('pending', 17008))
        self.assertEqual(self.iso.stat().st_size, 17008 * 2048)
        with self.iso.open('rb') as stream:
            stream.seek(32 * 2048)
            self.assertEqual(L.read_marker(stream.read(2048), 17008), spec)
        with self.assertRaisesRegex(burner.BurnError, 'keep-open'):
            burner.burn('fake', self.iso, yes_write=True, recorder=Mock())

    def test_pending_geo_uses_recorded_end_even_if_drive_reports_full_capacity(self):
        spec = S.pending('BOX4', 2295104, 'dvd')
        dev = SimDrive(jitter_us=0, outlier_rate=0, layout_sectors={L.PENDING_LBA: L.marker(spec)})
        original = dev.execute
        reads = []
        def execute(cdb, *a, **kw):
            result = original(cdb, *a, **kw)
            if cdb[0] in (0x28, 0xa8):
                lba = int.from_bytes(cdb[2:6], 'big')
                if lba == L.PENDING_LBA:
                    result.data = L.marker(spec)
                else:
                    reads.append(lba)
                    self.assertLess(lba, L.STOP_SECTORS)
            return result
        dev.execute = execute
        ladder = Ladder(dev, max_targets=8, state_check=False, log=lambda *_: None)
        ladder.run()
        self.assertEqual(ladder.tp.last_lba, L.STOP_SECTORS - 1)
        self.assertEqual(ladder.ranges, [((int((L.STOP_SECTORS - 1)*.03)+15)//16*16,
                                         int((L.STOP_SECTORS - 1)*.85)//16*16)])
        self.assertTrue(reads)

    def test_appended_layout_supersedes_pending_and_skips_session_border(self):
        pending = S.pending('BOX4', 2295104, 'dvd')
        final = S.measured_label('BOX4', 2295104, str(GEO)).spec
        start = L.STOP_SECTORS + 47120
        final.update(first_lba=start, avoid_lba=[[L.STOP_SECTORS, start], [32,33]])
        dev = SimDrive(jitter_us=0, outlier_rate=0, layout_sectors={32: L.marker(pending), L.MARKER_LBA: L.marker(final)})
        original = dev.execute
        def execute(cdb, *a, **kw):
            result = original(cdb, *a, **kw)
            if cdb[0] == 0x51:
                result.status = 0
                data = bytearray(34)
                data[2] = 2
                result.data = bytes(data)
            elif cdb[0] in (0x28, 0xa8):
                lba = int.from_bytes(cdb[2:6], 'big')
                if lba == 32:
                    result.data = L.marker(pending)
                elif lba == L.MARKER_LBA:
                    result.data = L.marker(final)
                else:
                    self.assertFalse(L.STOP_SECTORS <= lba < start)
                    self.assertFalse(final['exclude_lba'][0] <= lba < final['exclude_lba'][1])
            return result
        dev.execute = execute
        ladder = Ladder(dev, max_targets=8, state_check=False, log=lambda *_: None)
        ladder.run()
        self.assertEqual(ladder.tp.summary['random_label']['state'], 'written')
        self.assertEqual(ladder.tp.last_lba, 2295103)
        ladder.tp.period_reads = 20
        ladder.tp.period_test()
        ladder.tp.phase_test()

    def test_measured_band_marker_completion_and_border_checks(self):
        label = S.measured_label('BOX4 disc-probe', 2295104, str(GEO))
        self.assertEqual(label.spec['u'], json.loads(GEO.read_text())['fit']['u'])
        self.assertEqual(L.read_marker(L.marker(label.spec), 2295104), label.spec)
        for start in (L.STOP_SECTORS, L.STOP_SECTORS + 47104, label.span[0], 2295104):
            with self.assertRaises(ValueError):
                S.write_iso(self.iso, 'BOX4', str(GEO), start, log=lambda *_: None)
            self.assertEqual(self.iso.stat().st_size, 32*2048)
        fit = json.loads(GEO.read_text())
        fit['fit']['completion_sectors'] = 48
        path = self.root / 'geo.json'
        path.write_text(json.dumps(fit))
        label = S.measured_label('BOX4', 2295104, str(path))
        self.assertEqual(label.spec['completion_sectors'], 48)
        self.assertEqual(label.spec['u'], fit['fit']['u'])
        data = np.zeros((32, 2048), np.uint8)
        label.patch(data, L.MARKER_LBA - 16)
        self.assertEqual(L.read_marker(data[16].tobytes(), 2295104), label.spec)

    def test_preview_rejects_inconsistent_measured_metadata_before_render(self):
        from discprobe import simulate
        spec = S.measured_label('BOX4', 2295104, str(GEO)).spec
        spec['radius_mm'] = [40,41]
        path = self.root / 'wrong.image.json'
        path.write_text(json.dumps(spec))
        with patch.object(simulate, 'render') as render, self.assertRaisesRegex(ValueError, 'unsupported'):
            simulate.random_label(path, size=40)
        render.assert_not_called()


def test_stdlib_suite():
    result = unittest.TextTestRunner(stream=io.StringIO()).run(unittest.defaultTestLoader.loadTestsFromTestCase(LabelSessionTests))
    assert result.wasSuccessful(), result.errors + result.failures


test_stdlib_suite.__test__ = False
