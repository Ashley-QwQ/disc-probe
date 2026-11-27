"""Read-only media checks shared by the burn CLI and the web preflight."""
import json
from pathlib import Path

from . import mmc

EXPECTED_MID_ENV = 'DISCPROBE_BURN_EXPECTED_MID'


def problem(code, zh, en, **fields):
    return dict(code=code, zh=zh, en=en, **fields)


def tray_problem(tray):
    if tray == 'open':
        return problem('tray_open', '托盘开着。放入空白盘，关上托盘，再检查。',
                       'The tray is open. Insert a blank disc, close the tray, then check again.')
    if tray == 'empty':
        return problem('no_disc', '光驱里没有盘。放入空白盘，再检查。',
                       'No disc in the drive. Insert a blank disc and check again.')
    if tray in ('loading', 'changed'):
        return problem('disc_loading', '光驱正在认盘。等几秒，再检查。',
                       'The drive is reading the disc. Wait a few seconds and check again.')
    return problem('disc_unreadable', '读不到光盘状态。检查光驱连接，放好光盘，再检查。',
                   'Could not read the disc state. Check the drive connection, seat the disc, and check again.')


def medium_problem(disc, media, *, erase=False, append=False):
    reason = disc.get('not_ready')
    if reason:
        return tray_problem({mmc.TRAY_OPEN: 'open', mmc.NO_DISC: 'empty', mmc.NOT_RECOGNISED: 'empty',
                             mmc.LOADING: 'loading', mmc.DISC_CHANGED: 'changed'}.get(reason))
    kind = disc.get('kind') or mmc.PROFILES.get(disc.get('profile')) or str(disc.get('media') or '').upper()
    if disc.get('media') in ('cd', 'dvd', 'bd') and disc['media'] != media:
        return problem('wrong_media', f'光驱里是 {kind}，这份镜像需要 {media.upper()}。请换一张空白 {media.upper()}。',
                       f'Wrong disc kind: the drive holds {kind}. Insert a blank {media.upper()} for this image.')
    if disc.get('blank') is False and not append:
        if disc.get('rewritable'):
            if erase:
                return None
            return problem('recorded_rw', '这张可擦写盘已有内容。换一张空白盘，或确认擦除后重刻。',
                           'This rewritable disc has data. Insert a blank disc or explicitly choose to erase it before burning.')
        if disc.get('closed') is True or disc.get('profile') in (0x08, 0x10, 0x40):
            return problem('finalized', f'{kind} 已封盘。请换一张空白盘。',
                           f'This {kind} is finalized. Insert a blank disc.')
        if disc.get('closed') is False:
            return problem('recorded_open', f'{kind} 已有内容，尚未封盘。请换一张空白盘。',
                           f'This {kind} already contains data and is still open. Insert a blank disc.')
        return problem('recorded', '这张盘已有内容。请换一张空白盘。',
                       'This disc already contains data. Insert a blank disc.')
    if disc.get('blank') is None:
        return tray_problem(None)
    return None


def capacity_problem(sectors, available):
    if type(available) is not int or available <= 0:
        return problem('capacity_unknown', '读不到可写容量。重新检查光盘，或换一张容量已知的空白盘。',
                       'Could not read writable capacity. Check again or insert a blank disc with known capacity.')
    if sectors > available:
        return problem('too_small', f'镜像需要 {sectors:,} 扇区，这张盘只有 {available:,} 个可写扇区。换一张容量足够的空白盘，或重新生成较小的镜像。',
                       f'The image does not fit: it needs {sectors:,} sectors and this disc has {available:,} writable sectors. Insert a larger blank disc or make a smaller image.')
    return None


def mid_code(value):
    return value.strip() if (isinstance(value, str) and value.strip() and
                             value.strip().casefold() not in ('unknown', 'unknown disc')) else None


def batch_problem(actual, expected):
    actual, expected = mid_code(actual), mid_code(expected)
    if actual and expected and actual.casefold() != expected.casefold():
        return problem('other_batch',
                       f'这张盘是 {actual}，你的作品是按 {expected} 这批盘标定的。换了牌子，图案位置可能对不上。请换回 {expected}，或先给 {actual} 这批标定。',
                       f'This disc is {actual}. Your work was calibrated for {expected}. With a different batch, the picture may be misaligned. Put in a {expected} disc or calibrate the {actual} batch first.',
                       actual_mid=actual, expected_mid=expected)
    return None


def write_problem(reason, *, read_back=False):
    text = str(reason).lower()
    if 'c0aa0202' in text:
        return problem('disc_missing_during_write', '光驱在刻录时报告没有介质。重新检查这张盘和托盘，再决定是否换盘重刻。',
                       'The drive reported no disc during the write. Check the disc and tray before deciding whether to use another disc.')
    if 'session close failed' in text or 'disc/session is not closed' in text:
        return problem('close_failed', '光驱未能封盘。先重新读取这张盘，确认数据和封盘状态，再决定是否重刻。',
                       'The drive could not finalize the disc. Re-read this disc to check the recorded data and session before burning another.')
    if read_back:
        return problem('read_back_failed', '刻录后的抽样回读没有通过。先重新读取这张盘，再决定是否重刻。',
                       'The sampled read-back failed. Re-read this disc before deciding whether to burn another.')
    return None


def _json_object(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def measurement_mid(summary_path):
    identity = _json_object(Path(summary_path)).get('identity')
    return mid_code(identity.get('disc')) if isinstance(identity, dict) else None


def expected_batch(image, *, work=None, work_root=None, explicit=None, fallback=None, root=None):
    """Prefer a saved or selected batch. Otherwise use the ISO's measurement provenance."""
    work = work or {}
    batch = work.get('batch')
    selected = mid_code(batch.get('mid')) if isinstance(batch, dict) else None
    if selected or mid_code(explicit):
        return selected or mid_code(explicit)
    sidecar = image.with_suffix('.image.json')
    spec = _json_object(sidecar) if root is None or sidecar.resolve().is_relative_to(root) else {}
    if saved := mid_code(spec.get('calibration_mid')):
        return saved
    for value, base in ((spec.get('geometry_from'), image.parent), (work.get('geo_run'), work_root)):
        if not isinstance(value, str) or not value.strip() or '\0' in value or value.startswith(('\\\\', '//')):
            continue
        try:
            path = Path(value)
            path = (base / path if base is not None else path).resolve()
        except (ValueError, OSError):
            continue
        if root is not None and not path.is_relative_to(root):
            continue
        summary_path = path if path.name == 'summary.json' else path / 'summary.json'
        if root is not None and not summary_path.resolve().is_relative_to(root):
            continue
        if mid := measurement_mid(summary_path):
            return mid
    return mid_code(fallback)
