"""Cross-check recorded length using only the existing read-only MMC commands.

Track allocation and blank capacity are not recorded length. An end read proves
only that sector is readable; it is not a whole-disc verification.
"""
from . import mmc
from .drive_lock import locked_drive

# Real drives disagree by a sector or two without anything being wrong: a closed CD reports two run-out
# sectors more in READ CAPACITY than its track's last recorded address (six saved GH70N records), and two
# other drives report a closed DVD's capacity one sector past its LRA and TOC lead-out. Only a difference
# beyond one DVD ECC block is treated as a mismatch.
TOLERANCE = 16


def metadata(read, *, capacity=None, toc=None):
    """read(cdb, allocation) returns a ScsiResult; retain unavailable replies."""
    report = {}
    for key, cdb, size, parser in (
        ('disc_information', mmc.read_disc_information(), 34, mmc.parse_disc_information),
        ('capacity', mmc.read_capacity(), 8, mmc.parse_capacity),
        ('toc', mmc.read_toc(0), 2048, mmc.parse_toc),
    ):
        res = capacity if key == 'capacity' else toc if key == 'toc' else None
        if res is None:
            res = read(cdb, size)
        report[key] = dict(status=res.status, parsed=parser(res.data) if res.ok and len(res.data) >= min(size, 8) else {})
    disc = report['disc_information']['parsed']
    last = disc.get('last_track_last_session') or 1
    res = read(mmc.read_track_information(last), 48)
    report['track_last'] = dict(status=res.status, parsed=mmc.parse_track_information(res.data) if res.ok else {})
    # Some drives identify the next blank track as the last track of an open
    # disc. Its allocation is not evidence that the previous session was written.
    if last > 1 and report['track_last']['parsed'].get('blank'):
        res = read(mmc.read_track_information(last - 1), 48)
        report['track_last'] = dict(status=res.status, parsed=mmc.parse_track_information(res.data) if res.ok else {})
    return report


def track_end(track):
    if track.get('blank') is not False:
        return None
    if track.get('lra_valid'):
        return track['last_recorded'] + 1
    if track.get('nwa_valid'):
        # NWA may include a session border: it is an upper bound, not proof.
        return None
    size = track.get('track_size', 0)
    return track.get('track_start', 0) + size if size else None


def check(report, read=None, *, audio=False, recorded_end=False):
    """recorded_end: on a closed disc, read the end of the track's recorded data rather than the end READ
    CAPACITY gives. A closed CD's last two sectors there are run-out, not data; some drives retry such a
    sector for seconds (an HP GT31N slim drive took over 3 s). Measurements keep the READ CAPACITY end."""
    def parsed(key):
        entry = report.get(key, {})
        return (entry.get('parsed') or {}) if entry.get('status') in (None, 0) and not entry.get('error') else {}
    cap, disc = parsed('capacity'), parsed('disc_information')
    track = parsed('track_last') or parsed('track_1')
    reported = cap.get('last_lba')
    reported = reported + 1 if reported is not None and cap.get('block_length') == 2048 else None
    end = track_end(track)
    sources = dict(read_capacity=reported, track_recorded_end=end, disc_status=disc.get('disc_status'),
                   track_free_blocks=track.get('free_blocks'), next_writable=track.get('next_writable') if track.get('nwa_valid') else None)
    reasons = []
    closed = disc.get('disc_status') == 'complete'
    if disc.get('disc_status') == 'empty' and track.get('blank') is False:
        reasons.append('DISC INFORMATION says empty, but track information says recorded')
    # READ CAPACITY on an open disc can describe the whole medium.
    # On an open disc READ CAPACITY may describe the whole medium, or (seen on a GH70N) a single sector:
    # it is not compared there; the track's recorded end and an end read decide.
    if reported is not None and end is not None and closed and abs(reported - end) > TOLERANCE:
        reasons.append(f'READ CAPACITY says {reported} sectors, track recorded end says {end}')
    leadouts = [t['start_lba'] for t in parsed('toc').get('tracks', []) if t['track'] == 0xAA]
    if (closed or not disc) and leadouts and reported is not None and abs(leadouts[-1] - reported) > TOLERANCE:
        sources['toc_leadout'] = leadouts[-1]
        reasons.append(f'READ CAPACITY says {reported} sectors, TOC lead-out says {leadouts[-1]}')
    if track.get('lra_valid') and track.get('track_size') and not track.get('nwa_valid'):
        allocation_end = track.get('track_start', 0) + track['track_size']
        if end is not None and allocation_end + TOLERANCE < end:
            reasons.append(f'track allocation ends at {allocation_end}, before recorded end {end}')
    if track.get('nwa_valid') and end is not None and track.get('next_writable', 0) + TOLERANCE < end:
        reasons.append('track next writable address precedes its last recorded address')
    # Prerecorded capacity is independent of written length and of free space.
    from .capacity import recordable_capacity
    physical = recordable_capacity(report)
    if physical and end is not None:
        sources['recordable_sectors'] = physical[0]
        if end > physical[0] + TOLERANCE:
            reasons.append(f'recorded end {end} exceeds recordable capacity {physical[0]}')
        if track.get('nwa_valid') and track.get('next_writable', 0) + track.get('free_blocks', 0) > physical[0] + TOLERANCE:
            reasons.append('next writable address plus free blocks exceeds recordable capacity')
    result = dict(status='unknown', sources=sources, warnings=[])
    if not closed and end is not None and reported is not None and end < reported:
        result['open_recorded_sectors'] = end
    # Probe only recorded data. Audio uses different sector bytes/READ CD.
    probe_end = end if not closed else reported
    if recorded_end and closed and end is not None and reported is not None:
        probe_end = min(end, reported)
    if read and probe_end and not audio and disc.get('disc_status') != 'empty':
        try:
            res = read(mmc.read10(probe_end - 1, 1), 2048)
            result['end_read'] = dict(lba=probe_end - 1, status=res.status, sense=str(res.sense or ''))
            if res.ok and len(res.data) == 2048:
                result['status'] = 'confirmed_end'
                result['confirmed_recorded_sectors'] = probe_end
            elif res.sense and res.sense.key == 5 and res.sense.asc == 0x21:
                reasons.append(f'reported end LBA {probe_end - 1} is out of range ({res.sense})')
            # A medium error is a readability fault, not evidence of wrong capacity.
        except OSError as exc:
            result['end_read'] = dict(lba=probe_end - 1, error=str(exc))
    if reasons:
        result['status'] = 'mismatch'
        result['warnings'] = ['Capacity mismatch: ' + '; '.join(reasons) +
                              '. Re-read this same disc after closing other drive software, or try another drive; do not measure geometry until the recorded length agrees.']
    return result


@locked_drive("verify")
def burn_state(drive, sectors, *, keep_open=False, start_lba=0, device_factory=None):
    if device_factory is None:
        from .device import Device
        device_factory = Device
    with device_factory(drive) as dev:
        report = metadata(lambda cdb, size: dev.execute(cdb, data_len=size, timeout_s=3))
    disc = report['disc_information']['parsed']
    track = report['track_last']['parsed']
    end = track_end(track)
    expected = start_lba + sectors
    reasons, unconfirmed = [], []
    # Fail only on evidence: a recorded end clearly short of the image, or a disc read as not closed.
    # A drive that cannot report these is a warning, not a failed burn.
    if end is None:
        unconfirmed.append('the recorded length could not be confirmed')
    elif end + TOLERANCE < expected:
        reasons.append(f'the disc holds only {max(0, end - start_lba)} of {sectors} sectors')
    if not disc:
        unconfirmed.append('the disc/session closure could not be confirmed')
    elif keep_open:
        if disc.get('disc_status') != 'incomplete' or disc.get('last_session_state') != 3:
            reasons.append('the first session is not closed with the disc open as requested')
    elif disc.get('disc_status') != 'complete' or disc.get('last_session_state') != 3:
        reasons.append('the disc/session is not closed')
    return dict(status='failed' if reasons else 'completed', recorded_end=end, expected_end=expected,
                disc=disc, track=track, unconfirmed=unconfirmed,
                reason=('Write interrupted or session close failed: the drive said it finished, but ' + ' / '.join(reasons)) if reasons else None)
