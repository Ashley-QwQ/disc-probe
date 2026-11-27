"""Small, offline fault reproductions; every device is an explicit fake."""
import json
import threading
from unittest.mock import Mock

import pytest

from discprobe import burner, info, mmc, recorded, timing
from discprobe.scsi import ScsiResult, Sense, check_allowed
from discprobe.sim import SimDrive
from tests.iso_fixture import write_checked_iso


class Disc(SimDrive):
    def __init__(self, *, written=4096, reported=None, closed=True, session_closed=True,
                 track_reported=None, end_error=None):
        super().__init__(capacity=max(written, 4096), seed=23)
        self.written = written
        self.reported = written if reported is None else reported
        self.track_reported = self.reported if track_reported is None else track_reported
        self.closed, self.session_closed, self.end_error = closed, session_closed, end_error
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, cdb, data_len=0, direction=1, timeout_s=None):
        check_allowed(cdb)
        self.calls.append(cdb)
        op = cdb[0]
        if op == 0x51:
            d = bytearray(34)
            d[:2] = (32).to_bytes(2, 'big')
            d[2] = (2 if self.closed else 1) | (12 if self.session_closed else 0)
            d[3:7] = bytes([1, 1, 1, 1])
        elif op == 0x52:
            d = bytearray(48)
            d[:2] = (46).to_bytes(2, 'big')
            d[2:4] = bytes([1, 1])
            d[6], d[7] = 1, 2 if self.closed else 3
            d[12:20] = ((0 if self.closed else self.track_reported).to_bytes(4, 'big') +
                        (0 if self.closed else 8192 - self.track_reported).to_bytes(4, 'big'))
            d[24:32] = self.track_reported.to_bytes(4, 'big') + (self.track_reported - 1).to_bytes(4, 'big')
        elif op == 0x25:
            d = (self.reported - 1).to_bytes(4, 'big') + (2048).to_bytes(4, 'big')
        elif op in (0x28, 0xA8):
            lba = int.from_bytes(cdb[2:6], 'big')
            count = int.from_bytes(cdb[7:9] if op == 0x28 else cdb[6:10], 'big')
            sense = Sense(5, 0x21, 0) if lba + count > self.written else self.end_error
            if sense:
                return ScsiResult(2, b'', sense, 0, 100)
            return super().execute(cdb, data_len, direction, timeout_s)
        else:
            return super().execute(cdb, data_len, direction, timeout_s)
        return ScsiResult(0, bytes(d)[:data_len], None, 0, 100)


@pytest.mark.parametrize('reported,track', [(5120, 5120), (5120, 4096), (3072, 3072)])
def test_capacity_disagreement_warns_in_info_and_stops_measurements(reported, track):
    dev = Disc(reported=reported, track_reported=track)
    report = info.collect(dev)
    assert report['capacity_check']['status'] == 'mismatch'
    assert 'Capacity mismatch' in '\n'.join(info.summarize(report))
    probe = timing.TimingProbe(Disc(reported=reported, track_reported=track), log=lambda *a: None)
    with pytest.raises(timing.NoReadableDisc, match='Capacity mismatch.*same disc'):
        probe.setup()
    assert probe.summary['capacity_check']['status'] == 'mismatch'
    # geo calls this setup before examining random content.


def test_healthy_capacity_and_medium_error_are_not_called_capacity_mismatches():
    for end_error in (None, Sense(3, 0x11, 0)):
        report = info.collect(Disc(end_error=end_error))
        assert report['capacity']['parsed']['last_lba'] == 4095
        assert 'capacity_check' not in report
        assert 'Capacity mismatch' not in '\n'.join(info.summarize(report))
    probe = timing.TimingProbe(Disc(), log=lambda *a: None)
    probe.setup()
    assert probe.last_lba == 4095


def test_open_medium_uses_confirmed_recorded_length_with_warning():
    messages = []
    probe = timing.TimingProbe(Disc(reported=8192, track_reported=4096, closed=False), log=messages.append)
    probe.setup()
    assert probe.last_lba == 4095
    assert probe.summary['setup']['capacity_source'] == 'confirmed track recorded end'
    assert any('confirmed recorded length of 4096' in line for line in messages)
    probe = timing.TimingProbe(Disc(reported=8192, track_reported=4096, closed=False,
                                   end_error=Sense(3, 0x11, 0)), log=lambda *a: None)
    with pytest.raises(timing.NoReadableDisc, match='recorded length.*could not be confirmed'):
        probe.setup()


def test_capacity_cross_checks_disc_status_track_and_free_space():
    report = dict(disc_information=dict(parsed=dict(disc_status='empty')),
                  track_1=dict(parsed=dict(blank=False, lra_valid=True, last_recorded=4095,
                                          nwa_valid=True, next_writable=3000, free_blocks=6000)))
    result = recorded.check(report)
    assert result['status'] == 'mismatch'
    assert 'empty' in result['warnings'][0] and 'precedes' in result['warnings'][0]
    # A separate prerecorded capacity is required before treating free blocks
    # as inconsistent; an open track's reservation is not a recorded length.
    report['disc_information']['parsed']['disc_status'] = 'incomplete'
    report['configuration'] = dict(parsed=dict(current_profile=9))
    report['atip'] = dict(parsed=dict(disc_subtype=0, last_leadout_start_lba=8192))
    report['track_1']['parsed']['next_writable'] = 4096
    result = recorded.check(report)
    assert 'free blocks exceeds recordable capacity' in result['warnings'][0]


@pytest.mark.parametrize('closed,session_closed,keep_open,written,start,good', [
    (True, True, False, 4096, 0, True),
    (False, True, True, 4096, 0, True),
    (True, True, False, 6144, 2048, True),
    (False, False, False, 1638, 0, False),
    (True, True, False, 1638, 0, False),
    (False, False, True, 4096, 0, False),
    (False, True, False, 4096, 0, False),
    (True, True, True, 4096, 0, False),
])
def test_burn_state_checks_length_and_requested_session(closed, session_closed, keep_open, written, start, good):
    dev = Disc(written=written, closed=closed, session_closed=session_closed)
    state = recorded.burn_state('FAKE', 4096, start_lba=start, keep_open=keep_open, device_factory=lambda _: dev)
    assert (state['status'] == 'completed') is good
    if not good:
        assert 'drive said it finished' in state['reason']
    assert {0x51, 0x52} <= {c[0] for c in dev.calls}


@pytest.mark.parametrize('fault', ['unreadable', 'differing', 'cancelled', 'unavailable', 'untested', 'state', None])
def test_burn_result_and_log_fail_with_samples_or_state(tmp_path, fault):
    iso = tmp_path / 'small.iso'
    write_checked_iso(iso, bytes(32 * 2048))
    rec = Mock()
    rec.inspect.return_value = dict(blank=True, media='dvd', free_sectors=4096, speeds_x=[8])
    rec.write.return_value = 8
    verify = dict(status='completed', ok=2, differing=0, unreadable=0, untested=0, failures=[])
    if fault in ('unreadable', 'differing', 'untested'):
        verify[fault] = 1
    elif fault in ('cancelled', 'unavailable'):
        verify.update(status=fault, untested=2)
    state = dict(status='failed', reason='Write interrupted: disc holds only 16 of 32 sectors / is not closed') if fault == 'state' else dict(status='completed')
    options = dict(yes_write=True, recorder=rec, verifier=lambda *a: verify, state_checker=lambda *a, **k: state,
                   no_verify=fault == 'state')
    if fault:
        with pytest.raises(burner.BurnError):
            burner.burn('FAKE', iso, **options)
    else:
        result = burner.burn('FAKE', iso, **options)
        assert result['result'] == 'completed' and result['verified']
    final = json.loads((tmp_path / 'small.iso.burn.jsonl').read_text().splitlines()[-1])
    assert final['result'] == ('failed' if fault else 'completed')
    assert final['verification'] == (dict(status='skipped') if fault == 'state' else verify)
    rec.write.assert_called_once()


@pytest.mark.parametrize('written,closed,good', [(32, True, True), (12, False, False)])
def test_default_burn_state_reopens_fake_device_with_no_verify(tmp_path, monkeypatch, written, closed, good):
    from discprobe import device
    iso = tmp_path / 'state.iso'
    write_checked_iso(iso, bytes(32 * 2048))
    rec = Mock()
    rec.inspect.return_value = dict(blank=True, media='dvd', free_sectors=4096, speeds_x=[8])
    rec.write.return_value = 8
    dev = Disc(written=written, closed=closed)
    opened = Mock(return_value=dev)
    monkeypatch.setattr(device, 'Device', opened)
    if good:
        result = burner.burn('FAKE', iso, yes_write=True, recorder=rec, no_verify=True)
        assert result['result'] == 'completed' and result['verified'] is False
        # a healthy burn now also reports the closed-disc state (the after-burn review reads it); the old fields stay
        assert result['disc_state']['status'] in ('completed', 'unknown')
    else:
        with pytest.raises(burner.BurnError, match='only 12 of 32 sectors.*not closed'):
            burner.burn('FAKE', iso, yes_write=True, recorder=rec, no_verify=True)
    opened.assert_called_once_with('FAKE')
    assert {0x51, 0x52} <= {c[0] for c in dev.calls}
    assert not any(c[0] in (0x28, 0xA8) for c in dev.calls)


def _closed_report(capacity_sectors, lra, leadout=None):
    report = dict(
        capacity=dict(status=0, parsed=dict(last_lba=capacity_sectors - 1, block_length=2048)),
        disc_information=dict(status=0, parsed=dict(disc_status='complete', last_session_state=3)),
        track_1=dict(status=0, parsed=dict(blank=False, lra_valid=True, last_recorded=lra, nwa_valid=False,
                                           track_start=0, track_size=lra + 1)))
    if leadout is not None:
        report['toc'] = dict(status=0, parsed=dict(tracks=[dict(track=1, data=True, start_lba=0),
                                                           dict(track=0xAA, data=True, start_lba=leadout)]))
    return report


@pytest.mark.parametrize('capacity,lra,leadout', [
    (359752, 359749, None),          # closed CD: READ CAPACITY two run-out sectors past the LRA (GH70N records)
    (2295104, 2295102, 2295103),     # closed DVD on two other drives: capacity one past LRA and lead-out
])
def test_real_drive_small_differences_are_not_mismatches(capacity, lra, leadout):
    from discprobe.recorded import check
    assert check(_closed_report(capacity, lra, leadout))['warnings'] == []


def test_injected_capacity_error_is_still_a_mismatch():
    from discprobe.recorded import check
    assert check(_closed_report(4096 + 1024, 4095))['warnings']


def test_burn_state_fails_only_on_evidence():
    from discprobe import recorded

    class Dev:
        def __init__(self, replies): self.replies = replies
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, cdb, data_len=0, timeout_s=3):
            return self.replies(cdb)

    def factory(lra, closed=True, readable=True):
        def replies(cdb):
            from discprobe import mmc
            if not readable:
                return ScsiResult(2, b'', Sense(5, 0x20, 0), 0, 1)
            if cdb[0] == 0x51:      # READ DISC INFORMATION
                data = bytearray(34); data[2] = 0x0E if closed else 0x05; data[6] = 1
                return ScsiResult(0, bytes(data), None, 0, 1)
            if cdb[0] == 0x52:      # READ TRACK INFORMATION
                data = bytearray(48); data[0:2] = (46).to_bytes(2, 'big'); data[5] = 0x00; data[6] = 0x00; data[7] = 0x02
                data[24:28] = (lra + 1).to_bytes(4, 'big'); data[28:32] = lra.to_bytes(4, 'big')
                return ScsiResult(0, bytes(data), None, 0, 1)
            return ScsiResult(2, b'', Sense(5, 0x20, 0), 0, 1)
        return lambda drive: Dev(replies)

    short = recorded.burn_state('X:', 4096, device_factory=factory(1637))
    assert short['status'] == 'failed' and '1638 of 4096' in short['reason']
    unknown = recorded.burn_state('X:', 4096, device_factory=factory(0, readable=False))
    assert unknown['status'] == 'completed' and unknown['unconfirmed']


class SlowRunOut(Disc):
    """A closed CD: READ CAPACITY counts two run-out sectors past the track's data, and the drive retries a
    read there until its own timeout (an HP GT31N in a USB case, 3 s)."""
    def __init__(self, *, slow_from=4094):
        super().__init__(written=4096, reported=4096, track_reported=4094)
        self.slow_from = slow_from

    def execute(self, cdb, data_len=0, direction=1, timeout_s=None):
        if cdb[0] == 0x28 and int.from_bytes(cdb[2:6], 'big') >= self.slow_from:
            self.calls.append(cdb)
            raise TimeoutError('READ(10): The semaphore timeout period has expired.')
        return super().execute(cdb, data_len, direction, timeout_s)


def _reads(dev):
    return [int.from_bytes(c[2:6], 'big') for c in dev.calls if c[0] == 0x28]


def test_info_reads_the_recorded_end_of_a_closed_cd_not_its_run_out():
    dev = SlowRunOut()
    wrapped = info.InfoDevice(dev)
    try:
        report = info.collect(wrapped)
    finally:
        wrapped.close()
    assert _reads(dev) == [4093]
    assert wrapped.errors == [] and wrapped.unsupported == []
    assert 'capacity_check' not in report


def test_info_carries_on_when_the_optional_end_read_times_out():
    dev = SlowRunOut(slow_from=0)
    wrapped = info.InfoDevice(dev)
    try:
        report = info.collect(wrapped)
    finally:
        wrapped.close()
    assert wrapped.errors == [] and not wrapped.failed
    assert len(wrapped.unsupported) == 1 and 'READ(10)' in wrapped.unsupported[0]
    assert report['capacity']['parsed']['last_lba'] == 4095 and 'capacity_check' not in report
    # an ordinary command that times out still stops info
    with pytest.raises(TimeoutError):
        wrapped2 = info.InfoDevice(dev)
        try:
            wrapped2.execute(mmc.read10(0, 1), 2048)
        finally:
            assert wrapped2.failed and wrapped2.errors
            wrapped2.close()


def test_measurements_keep_the_read_capacity_end_read():
    report = recorded.metadata(SlowRunOut().execute)
    seen = []
    def read(cdb, size):
        seen.append(int.from_bytes(cdb[2:6], 'big'))
        return ScsiResult(2, b'', Sense(3, 0x11, 0), 0, 100)
    recorded.check(report, read)
    assert seen == [4095]
