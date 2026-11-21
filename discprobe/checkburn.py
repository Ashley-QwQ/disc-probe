"""Read-only checks for a recorded disc or a saved post-burn report."""
from contextlib import nullcontext
import json
from pathlib import Path
import sys
from threading import Event

from . import burner, discid, guide, info, mmc, recorded
from .capacity import catalogue_capacity, positive_sectors, recordable_capacity
from .checkburn_content import SECTOR, probe
from .drive_lock import locked_drive

CAPACITY_REFERENCE = {0x11: 2298496, 0x1B: 2295104}
LIGHT_GUIDE = dict(id='start-guide-light',
                   label={'zh': '新手引导 · 光怎么变成图', 'en': 'Start guide · How light becomes a picture'},
                   manual={'zh': 'README.md#第-6-步看盘和拍照',
                           'en': 'README.en.md#step-6-look-at-the-disc-and-photograph-it'})
STATUS = {'excluded': ('已排除', 'Ruled out'), 'possible': ('可能', 'Possible'),
          'unknown': ('没法自动判断', 'Cannot check automatically')}
DISC_STATE = {'blank': ('空白', 'Blank'), 'recorded': ('已刻', 'Recorded'),
              'unavailable': ('不可读', 'Unavailable'), 'unknown': ('未知', 'Unknown')}
CLOSURE = {True: ('已封盘', 'Closed'), False: ('未封盘', 'Open'), None: ('封盘未知', 'Closure unknown')}
CONTENT_KIND = {'pattern': ('图案数据', 'Picture pattern'), 'random': ('随机数据', 'Random data'),
                'files': ('普通文件', 'Ordinary files'), 'unknown': ('内容未知', 'Content unknown')}


def pair(zh, en):
    return dict(zh=zh, en=en)


def _item(key, status, title, message, *, link=None):
    item = dict(id=key, status=status, status_label=pair(*STATUS[status]), title=pair(*title), message=message)
    if link:
        item['link'] = link
    return item


def _write_check(disc, verification, content, result):
    if disc['state'] == 'blank':
        return 'possible', pair('光驱报告这是一张空白盘。请确认放进的是刚刻的那张盘。',
                                'The drive reports a blank disc. Check that you inserted the disc you just burned.')
    if (disc.get('short') or disc.get('session_incomplete') or result in ('failed', 'cancelled', 'stopped')
            or verification.get('differing') or verification.get('unreadable')):
        return 'possible', pair('发现写入中断、长度不足、回读失败或与原镜像不符的迹象。先核对原始刻录报告，关掉占用光驱的软件后重读同一张盘。',
                                'The write record, recorded length or read-back shows a problem. Check the original burn report, close other drive software and reread the same disc.')
    if verification.get('status') == 'completed' and verification.get('ok', 0) > 0 and verification.get('untested') == 0:
        return 'excluded', pair(f"{verification['ok']} 个抽样块与原镜像相同。只检查了抽样位置。",
                                f"{verification['ok']} sampled blocks matched the image. This covers the sampled locations.")
    if content.get('samples', {}).get('unreadable'):
        return 'possible', pair('有抽样位置读不回来。请重读同一张盘，或换一个光驱读。',
                                'Some sampled locations could not be read. Read the same disc again or try another drive.')
    if disc['state'] == 'recorded':
        return 'unknown', pair('盘上有数据；可用原 ISO 运行 checkburn --iso 来抽样核对写入。',
                               'The disc contains data. Run checkburn --iso with the original image to compare a sample.')
    return 'unknown', pair('没有可用的盘状态或回读结果。请确认盘在光驱里，再运行 checkburn。',
                           'No disc state or read-back result is available. Check that the disc is in the drive and run checkburn.')


def checklist(disc, verification, content, calibration, result=None):
    write, message = _write_check(disc, verification or {}, content or {}, result)
    checks = [_item('write', write, ('数据没写进去或刻坏了', 'Data missing or damaged'), message)]
    file_copy = (content or {}).get('image_as_file')
    kind = (content or {}).get('kind')
    if file_copy:
        file_status = 'possible'
        file_words = pair('根目录只有少量镜像或图片文件，抽样未发现盘面图案数据。已有 ISO 请选“刻录光盘映像”。只有 PNG/JPG 时，先用刻图软件生成镜像。',
                          'The root holds only a few image files and the sample found no picture pattern. Use “Burn disc image” for an ISO. Generate a disc image first if you only have a PNG or JPG.')
    elif file_copy is False or disc['state'] == 'blank':
        file_status = 'excluded'
        file_words = pair('抽查结果与把镜像或图片当文件刻进去的情况不符。',
                          'The evidence does not match a disc containing the image as a file.')
        if kind == 'random':
            file_words = pair('抽样像随机测量数据。这种盘用来测量，盘面通常没有图。',
                              'The samples look like random measurement data. A measurement disc usually shows no picture.')
        elif kind == 'files':
            file_words = pair('根目录像普通数据盘。请核对生成的刻图镜像是否选对。',
                              'The root looks like an ordinary data disc. Check which image you chose to burn.')
    else:
        file_status = 'unknown'
        file_words = pair('没有足够的文件系统和盘面抽样证据。可以打开盘的根目录，看看是否只放进了 ISO 或图片文件。',
                          'There is not enough filesystem and sample evidence. Open the disc root and check whether it only contains an ISO or picture files.')
    checks.append(_item('image_as_file', file_status, ('把镜像或图片当文件烧了', 'Image burned as a file'), file_words))
    checks.append(_item('lighting', 'unknown', ('看的角度和光照', 'Viewing angle and light'),
                        pair('看数据面。关掉房间的灯，把手电放在眼睛旁边，在约一米外倾斜盘 20–30°，避开倒影，慢慢转动。如果用吸顶灯，就背对它。',
                             'Look at the data side. Turn off the room lights, hold a torch by your eyes, and tilt the disc 20–30° about a metre away. Avoid reflections and turn it slowly. If using a ceiling light, face away from it.'),
                        link=LIGHT_GUIDE))

    geometry = calibration.get('status')
    if geometry == 'nominal':
        geometry_status = 'possible'
        geometry_words = pair('这次用了 DIS 名义预设。若只看到同心环，用同批盘做标定，再用实测预设重新生成。',
                              'This burn used a nominal DIS preset. If you only see rings, calibrate the same batch and regenerate with the measured preset.')
    elif geometry in ('linked', 'batch_record'):
        geometry_status = 'unknown'
        geometry_words = (pair('找到了这次刻录关联的测量。实物的几何仍要看同批盘上的直线是否扭曲。',
                               'A measurement is linked to this burn. Check straight lines on a disc from the same batch for twist.')
                          if geometry == 'linked' else
                          pair('找到了同标识的测量记录。请核对是不是同一批盘，以及生成镜像时是否用了这份测量。',
                               'A measurement with the same media code was found. Check that it was from the same batch and used to build this image.'))
    else:
        geometry_status = 'unknown'
        geometry_words = pair('刻录数据看不出当时用的预设。若只看到同心环，核对标定记录和这张镜像用的几何。',
                              'The burn data cannot identify the preset used. If you only see rings, check the calibration records and the geometry used to build the image.')
    checks.append(_item('geometry', geometry_status, ('没标定或几何不对', 'Missing calibration or wrong geometry'), geometry_words))

    media = disc.get('kind')
    if media in ('CD-R', 'CD-RW') or disc.get('media') == 'cd':
        media_status = 'possible'
        media_words = pair('CD-R 的图偏淡，CD-RW 通常更淡。用小光源再找一次角度。DVD-R、DVD+R 通常最亮。',
                           'CD-R pictures are faint and CD-RW is usually fainter. Try a small light and adjust the angle. DVD-R and DVD+R are usually brightest.')
    else:
        media_status = 'unknown'
        media_words = pair('DVD-R、DVD+R 通常最亮。盘的类型只能提供线索，实际亮度要在灯下看。',
                           'DVD-R and DVD+R are usually brightest. The disc type is a clue. Check the actual brightness under a light.')
    checks.append(_item('media', media_status, ('盘的类型和亮度', 'Disc type and brightness'), media_words))
    checks.append(_item('drive', 'unknown', ('光驱和供电', 'Drive and power'),
                        pair('超薄 USB 光驱可以直连电脑后面的 USB 3.0 口，或用有独立供电的连接。读写不稳时试低一档速度。',
                             'For a slim USB drive, use a rear USB 3.0 port directly or use a separately powered connection. If reading or writing is unstable, try a lower speed.')))
    return checks


def _disc(state='unknown', *, end=None, closed=None, media=None, kind=None, **details):
    capacity = details.get('blank_capacity_sectors')
    return dict(state=state, recorded_sectors=end, last_lba=end - 1 if end else None, closed=closed, media=media,
                kind=kind, used_fraction=end / capacity if end is not None and capacity else None, **details)


def _disc_summary(disc, content):
    state = DISC_STATE[disc['state']]
    closed = CLOSURE[disc['closed']]
    kind = CONTENT_KIND[(content or {}).get('kind', 'unknown')]
    end = disc['recorded_sectors']
    capacity = disc.get('blank_capacity_sectors')
    length = (f'已刻 {end} 扇区', f'{end} sectors recorded') if end is not None else ('', '')
    if end is not None and capacity:
        used = f"{end} / {capacity} ({disc['used_fraction']:.1%})"
        length = (f'已刻 {used} 扇区', f'{used} sectors recorded')
        if (disc.get('capacity_source') or '').startswith('nominal'):
            length = (f'{length[0]}，按标称空白容量', f'{length[1]}, nominal blank capacity')
    media = disc['kind'] or (disc['media'].upper() if disc['media'] in ('cd', 'dvd', 'bd') else '')
    zh, en = (' · '.join(filter(None, (media, state[i], closed[i], length[i], kind[i]))) for i in range(2))
    return pair(zh, en)


def _new_report(disc, *, source, verification=None, content=None, calibration=None, result=None):
    calibration = calibration or dict(status='unknown')
    return dict(source=source, disc=disc, verification=verification, content=content, calibration=calibration,
                disc_summary=_disc_summary(disc, content),
                checklist=checklist(disc, verification, content, calibration, result))


def _saved_calibration(report, linked=None):
    from .presets import NOMINAL_IDS

    geometry = ((report.get('identity') or {}).get('body') or {}).get('geometry') or {}
    if isinstance(geometry.get('preset_id'), str) and geometry['preset_id'] in NOMINAL_IDS:
        return dict(status='nominal', source='disc_identity', preset_id=geometry['preset_id'])
    geo = linked or geometry.get('geo_run')
    return dict(status='linked', record=geo) if geo else dict(status='unknown')


def saved_report(record, media):
    """Inspect this particular saved burn, independent of what's now in the drive."""
    report = record.get('report') or record
    state = report.get('disc_state') or {}
    raw_disc = state.get('disc') or {}
    end, expected = state.get('recorded_end'), state.get('expected_end')
    end = end if positive_sectors(end) else None
    disc_status = raw_disc.get('disc_status')
    closed = {'complete': True, 'incomplete': False, 'empty': False}.get(disc_status)
    disc_state = ('blank' if disc_status == 'empty' else 'recorded' if
                  disc_status in ('complete', 'incomplete') or positive_sectors(end) else 'unknown')
    disc = _disc(disc_state, end=0 if disc_state == 'blank' else end, closed=closed, media=media,
                 expected_end=expected, short=_short(end, expected), drive=record.get('drive'),
                 blank_capacity_sectors=None, capacity_source=None)
    return _new_report(disc, source='saved_burn', verification=report.get('verification'),
                       calibration=_saved_calibration(report, record.get('geo_run')), result=report.get('result'))


def _short(end, expected):
    return type(end) is int and positive_sectors(expected) and end + recorded.TOLERANCE < expected


def _media_state(dev, drive, root):
    quick = info.quick(dev)
    parsed = lambda key: guide._parsed(quick, key)
    ready = quick['test_unit_ready']
    if ready.get('status') != 0 or ready.get('error') or ready.get('sense'):
        return _disc('unavailable', drive=drive, reason=mmc.not_ready(ready.get('sense')) or ready.get('error')), False, 0
    cfg, di, cap, atip = (parsed(key) for key in ('configuration', 'disc_information', 'capacity', 'atip'))
    profile = cfg.get('current_profile')
    media = mmc.media_family(profile)
    track = parsed('track_1')
    status = di.get('disc_status')
    blank = status == 'empty' or (not status and track.get('blank') is True)
    mid = info.disc_id(parsed('dvd_prerecorded_0e'), parsed('dvd_plus_adip_11'), atip)
    kind = atip.get('disc_type') if profile == 0x08 and atip else mmc.PROFILES.get(profile)
    if kind in ('CD-R', 'CD-RW') and profile == 0x08:
        # Some readers report CD-ROM after finalization. ATIP identifies the medium.
        quick['configuration']['parsed']['current_profile'] = 0x0A if kind == 'CD-RW' else 0x09
    capacity = recordable_capacity(quick) or catalogue_capacity(mid, media, root)
    if profile == 0x10 and mid:
        # A finalized DVD can be reported as ROM by the reader.
        profile = 0x11 if parsed('dvd_prerecorded_0e').get('manufacturer_id') else 0x1B
        kind = mmc.PROFILES[profile]
    if not capacity and profile in CAPACITY_REFERENCE:
        capacity = CAPACITY_REFERENCE[profile], 'nominal single-layer capacity for this media profile'
    drive_info = parsed('inquiry')
    name = f"{drive_info.get('vendor', '')} {drive_info.get('product', '')}".strip() or None
    details = dict(media=media, kind=kind, drive=drive, drive_name=name, mid=mid,
                   blank_capacity_sectors=capacity[0] if capacity else None, capacity_source=capacity[1] if capacity else None)
    if blank:
        return _disc('blank', end=0, closed=False, **details), False, 0

    def toc(fmt):
        try:
            reply = dev.execute(mmc.read_toc(fmt), data_len=2048, timeout_s=3)
        except OSError:
            return []
        if not reply.ok or len(reply.data) < 4:
            return []
        size = int.from_bytes(reply.data[:2], 'big') + 2
        return mmc.parse_toc(reply.data[:size])['tracks']

    tracks = toc(0)
    real_tracks = [t for t in tracks if 1 <= t['track'] <= 99]
    audio = media == 'cd' and bool(real_tracks) and not any(t['data'] for t in real_tracks)
    sessions = toc(1) if di.get('sessions', 0) > 1 else []
    start = next((t['start_lba'] for t in sessions if t['data'] and t['track'] != 0xAA), 0)
    last_number = di.get('last_track_last_session') or 1
    if last_number > 1:
        for number in (last_number, last_number - 1):
            try:
                reply = dev.execute(mmc.read_track_information(number), data_len=48, timeout_s=3)
            except OSError:
                continue
            last = mmc.parse_track_information(reply.data) if reply.ok else {}
            if last.get('blank') is False:
                track = last
                break
    end = recorded.track_end(track)
    if not positive_sectors(end):
        end = None
    if end is None and status != 'incomplete':
        end = next((t['start_lba'] for t in tracks if t['track'] == 0xAA and positive_sectors(t['start_lba'])), None)
        if not end and cap.get('block_length') in (2048, 2352) and type(cap.get('last_lba')) is int:
            end = cap['last_lba'] + 1 if positive_sectors(cap['last_lba'] + 1) else None
    disc = _disc('recorded' if end or status in ('complete', 'incomplete') else 'unknown', end=end,
                 closed={'complete': True, 'incomplete': False}.get(status),
                 session_incomplete=status == 'incomplete' and di.get('last_session_state') != 3 and bool(end),
                 **details)
    return disc, audio, start if end and 0 <= start < end else 0


def _sector_reader(dev, *, audio=False):
    size = 2352 if audio else SECTOR

    def read(lba, count):
        cdb = mmc.read_cd(lba, count) if audio else mmc.read10(lba, count)
        reply = dev.execute(cdb, data_len=size * count, timeout_s=3)
        if not reply.ok or len(reply.data) != size * count:
            raise OSError(f'LBA {lba}: status {reply.status}; sense {reply.sense}; {len(reply.data)} bytes')
        return reply.data

    return read


def _burn_rows(path):
    with path.open(encoding='utf-8-sig') as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                yield row


def _log_result(path, identity=None):
    latest, last_result = None, None
    for row in _burn_rows(path):
        if row.get('type') == 'burn_preflight':
            latest = row
            last_result = None
        elif row.get('type') == 'burn_result':
            row_id = (((row.get('identity') or {}).get('body') or {}).get('id'))
            if identity is not None and row_id != identity:
                continue
            if latest and latest.get('image') == row.get('image') and latest.get('drive') == row.get('drive'):
                row['expected_sectors'] = latest.get('sectors')
            if identity is not None:
                return row
            last_result = row
    return last_result


def _image_identity(read, end, enabled):
    if not enabled or not end or end < discid.LBA + discid.SIZE // SECTOR:
        return None
    try:
        return discid.read(read, discid.recorded_total(read, end))
    except (OSError, ValueError):
        return None


def _calibration(disc, identity, log, out, dis_nominal):
    if dis_nominal:
        return dict(status='nominal', source='user')
    saved = _saved_calibration(dict(identity=identity) if identity else log or {})
    if saved['status'] != 'unknown':
        return saved
    if disc.get('mid'):
        for run in guide.scan(out):
            if (run.kind == 'geo' and run.media == disc['media'] and not run.simulated
                    and (run.summary.get('identity') or {}).get('disc') == disc['mid']
                    and guide.result_verdict(run, run.media) in ('good', 'usable')):
                return dict(status='batch_record', record=run.path, mid=disc['mid'])
    return saved


def _open_device(drive):
    from .device import Device

    try:
        return Device(drive)
    except OSError as exc:
        if sys.platform != 'win32' or exc.errno != 5:
            raise
        from .imapi import ImapiDevice
        return ImapiDevice(drive)


@locked_drive('verify')
def check(drive, *, iso=None, burn_log=None, dis_nominal=False, out='results', start_lba=None, cancel=None,
          device_factory=None):
    device_factory = device_factory or _open_device
    image = Path(iso).resolve() if iso is not None else None
    image_stat = image.stat() if image else None
    expected = image_stat.st_size if image_stat else None
    if expected is not None and (not positive_sectors(expected // SECTOR) or expected % SECTOR or not image.is_file()):
        raise ValueError('ISO 必须是非空的完整扇区镜像 / ISO must be a nonempty whole-sector image')
    log = _log_result(Path(burn_log)) if burn_log else None
    if burn_log and log is None:
        raise ValueError('日志里没有已保存的刻录结果 / No saved burn result in this log')
    if log and image and log.get('image') and Path(log['image']).resolve() != image:
        raise ValueError('这份刻录日志对应另一份镜像 / This burn log names a different image')
    if start_lba is not None and (image is None or not 0 <= start_lba < 0xFFFFFFFF
                                  or start_lba + expected // SECTOR > 0xFFFFFFFF):
        raise ValueError('--start-lba 需要 ISO 和有效的起始扇区 / --start-lba requires an ISO and a valid starting sector')

    with device_factory(drive) as dev:
        disc, audio, start = _media_state(dev, drive, Path(out).resolve().parent)
        end = disc['recorded_sectors']
        read = _sector_reader(dev, audio=audio)
        identity = _image_identity(read, end, not audio)
        body = (identity or {}).get('body', {})
        matched_log = False
        if not log and body.get('burn') and image:
            try:
                log = _log_result(Path(str(image) + '.burn.jsonl'), body['id'])
            except FileNotFoundError:
                pass
            matched_log = log is not None
        elif log and (log.get('identity') or {}).get('body', {}).get('id') and identity:
            # Even an explicitly supplied record must yield to a conflicting on-disc ID.
            logged = log['identity']['body']['id']
            if logged != body['id']:
                log = _log_result(Path(burn_log), body['id'])
        if log and image_stat:
            # A saved comparison only covers the source present at the time.
            stamp = log.get('time')
            if (type(stamp) in (int, float) and image_stat.st_mtime > stamp
                    or positive_sectors(log.get('expected_sectors')) and expected // SECTOR != log['expected_sectors']):
                log = None
        offset = start_lba if start_lba is not None else (log or {}).get('first_lba', 0)
        if type(offset) is not int or not 0 <= offset < 0xFFFFFFFF or (expected and offset + expected // SECTOR > 0xFFFFFFFF):
            raise ValueError('刻录日志的起始扇区无效 / Invalid starting sector in the burn log')
        saved = (log or {}).get('verification')
        length = expected // SECTOR if expected else (log or {}).get('expected_sectors')
        logged_end = ((log or {}).get('disc_state') or {}).get('expected_end')
        intended = offset + length if positive_sectors(length) else logged_end
        disc.update(expected_end=intended, short=_short(end, intended))
        if (saved and saved.get('status') != 'skipped' and disc['state'] == 'recorded'
                and not disc['short'] and offset == log.get('first_lba', 0)):
            verification = saved
            origin = 'matched_burn_log' if matched_log else 'supplied_burn_log'
        elif image and not audio and disc['state'] == 'recorded' and disc['media'] in ('cd', 'dvd', 'bd'):
            source = image
            if body.get('burn'):
                try:
                    template = discid.read_image(image)
                    if template and body.get('generator', {}).get('template_id') == template['body']['id']:
                        source = discid.PatchedImage(image, identity)
                except (OSError, ValueError):
                    pass
            verification = burner.verify_image(drive, source, disc['media'], cancel or Event(),
                                               device_factory=lambda _: nullcontext(dev), start_lba=offset)
            origin = 'drive'
        else:
            verification, origin = None, 'drive'
        inspected = probe(read, end, disc['media'], start=start, audio=audio) if end else None
    calibration = _calibration(disc, identity, log, out, dis_nominal)
    return _new_report(disc, source=origin, verification=verification, content=inspected, calibration=calibration,
                       result=(log or {}).get('result') if disc['state'] == 'recorded' else None)


def add_parser(sub):
    parser = sub.add_parser('checkburn', help='刻后只读排查 / check a recorded disc without writing')
    parser.add_argument('--drive', required=True, help='光驱 / drive (E: or /dev/sr0)')
    parser.add_argument('--iso', help='原 ISO，用来抽样比对 / original ISO for sampled comparison')
    parser.add_argument('--burn-log', help='确认对应这张盘的日志 / .burn.jsonl you have matched to this disc')
    parser.add_argument('--start-lba', type=int, help='追加镜像的起始扇区 / start sector of an appended image')
    parser.add_argument('--dis-nominal', action='store_true', help='用了 DIS 名义预设 / a nominal DIS preset was used')
    parser.add_argument('--out', default='results', help='测量记录目录 / measurement records directory')
    parser.add_argument('--json', action='store_true', help='输出 JSON / emit JSON')
    parser.set_defaults(func=run)


def run(args):
    from . import i18n
    result = check(args.drive, iso=args.iso, burn_log=args.burn_log, dis_nominal=args.dis_nominal,
                   out=args.out, start_lba=args.start_lba)
    if args.json:
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        return
    lang = 'zh' if i18n.active() == 'zh' else 'en'
    disc = result['disc']
    print(disc['drive'], result['disc_summary'][lang])
    check_result = result['verification']
    if check_result:
        origin = pair('日志', 'log') if result['source'].endswith('_log') else pair('现场回读', 'drive')
        print(pair('回读抽样', 'Read-back sample')[lang], f"({origin[lang]})", json.dumps(check_result, ensure_ascii=True))
    for item in result['checklist']:
        print(f"{item['title'][lang]} [{item['status_label'][lang]}] {item['message'][lang]}")
        if 'link' in item:
            print(f"  webui → {item['link']['label'][lang]}  ({item['link']['manual'][lang]})")
