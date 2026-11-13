// Words for photo calibration, shared by the phone page and the computer page.
// Every reason comes from the core's per-photo `status` (discprobe/photo.py REASONS); nothing here guesses one.
// Every state is something that already happened on the computer (received, queued, read), never a live camera check.
const pair = (zh, en) => ({zh, en});

// What to do next, short, then why. Keys are the reader's statuses.
export const photoReasons = {
  ok: {act: pair('可以用', 'Usable'), why: pair('这张照片读出来了。', 'This photo was read.')},
  no_rim: {act: pair('拍全盘', 'Show the whole disc'),
    why: pair('没找到整张盘的边。把整张盘拍进画面，四周留一点边。', 'The disc edge was not found. Get the whole disc in frame, with a little margin.')},
  too_few_votes: {act: pair('换光照', 'Change the light'),
    why: pair('能读的彩色条纹太少。背对吸顶灯，盘朝自己转 20–30°；盘上有白色圆形反光就微调避开。', 'Too little readable colour pattern. Stand with the ceiling lamp behind you and tilt the disc 20–30° towards you; nudge it if a round white glare sits on the disc.')},
  weak_peak: {act: pair('换光照', 'Change the light'),
    why: pair('条纹太淡，读不准。背对吸顶灯，避开盘上的白色反光，让彩色条纹更亮。', 'The pattern is too faint to read. Put the ceiling lamp behind you and keep its white glare off the disc.')},
  few_inliers: {act: pair('转一下盘', 'Turn the disc'),
    why: pair('条纹里对得上的部分太少。转一下盘，换个角度再拍。', 'Too few parts of the pattern agree. Turn the disc and shoot from another angle.')},
  rings_not_found: {act: pair('拍全盘', 'Show the whole disc'),
    why: pair('找不到标靶的圆环。拍全盘、对好焦，确认拍的是这次刻的标靶盘。', 'The target rings were not found. Show the whole disc in focus, and check it is the target disc burned for this run.')},
  two_peaks: {act: pair('转一下盘', 'Turn the disc'),
    why: pair('有两种对法都说得通。转一下盘，再拍一张不同角度的。', 'Two alignments both look possible. Turn the disc and take another from a different angle.')},
  poor_angle_coverage: {act: pair('转一下盘', 'Turn the disc'),
    why: pair('彩色条纹只盖住盘的一小块。转一下盘或换个角度，让条纹绕得更全。', 'The colour pattern covers only a small part of the disc. Turn the disc or change the angle so it reaches further round.')},
  poor_radius_coverage: {act: pair('补内外圈', 'Cover inner and outer rings'),
    why: pair('条纹没从内圈铺到外圈。调一下倾斜角度，让内圈和外圈都出现彩色条纹。', 'The pattern does not reach from the inner to the outer rings. Change the tilt so both show colour.')},
  large_residual: {act: pair('拍全盘', 'Show the whole disc'),
    why: pair('条纹位置和预期对不上。拍全盘、别被手或物体挡住，确认拍的是这次刻的标靶盘。', 'The pattern does not fit the expected positions. Show the whole, unobstructed disc, and check it is this run’s target disc.')},
  unstable_L: {act: pair('转一下盘', 'Turn the disc'),
    why: pair('同一张照片里不同部分读数不一致。转一下盘重拍。', 'Different parts of this photo disagree. Turn the disc and retake.')},
  shape_not_1_over_r: {act: pair('转一下盘', 'Turn the disc'),
    why: pair('内外圈给出的结果对不上。确认是这次刻的标靶盘，转一下盘重拍。', 'Inner and outer rings disagree. Check it is this run’s target disc, turn it and retake.')},
  unreadable_image: {act: pair('重新发送', 'Send again'),
    why: pair('这张图片打不开。重新拍，或在相册里导出 JPEG 再发。', 'The image could not be opened. Retake, or export a JPEG from your photos and send that.')},
  duplicate_photo: {act: pair('换个角度', 'Change the angle'),
    why: pair('这张和另一张是同一张照片。转一下盘，拍一张新的。', 'This is the same picture as another one. Turn the disc and take a new one.')},
};
const unknownReason = photo => ({act: pair('重拍', 'Retake'),
  why: pair(photo.reason || '读不准这张照片。转一下盘再拍一张。', photo.reason || 'This photo could not be read reliably. Turn the disc and take another.')});
export const reasonOf = (photo = {}) => Object.prototype.hasOwnProperty.call(photoReasons, photo.status) ? photoReasons[photo.status] : unknownReason(photo);
// One line: the action, then why. Same shape as guidance.mjs photoReasonWords, so callers can switch.
export function photoReasonWords(photo = {}) {
  const r = reasonOf(photo);
  return photo.status === 'ok' || photo.verdict === 'ok' ? r.why : pair(`${r.act.zh}：${r.why.zh}`, `${r.act.en}: ${r.why.en}`);
}

export const seconds = s => {
  if (!Number.isFinite(s) || s < 0) return pair('', '');
  const n = Math.round(s);
  return n < 60 ? pair(`${n} 秒`, `${n} s`) : pair(`${Math.floor(n / 60)} 分 ${n % 60} 秒`, `${Math.floor(n / 60)} min ${n % 60} s`);
};

// One photo's stage. `listing` is the /api/photos answer; its times are the computer's own clock.
// Stages: waiting (received, no read yet), queued (a read of other photos is running), reading, ok, outlier
// (read fine but outside the majority; the core named it), retake, failed.
export function photoStage(photo = {}, listing = {}) {
  const a = listing.analysis, inRead = !!a && (a.photos || []).includes(photo.id);
  const now = Number.isFinite(listing.now) ? listing.now : Date.now() / 1000;
  const covered = (listing.read_photos || []).includes(photo.id);
  const took = covered && Number.isFinite(listing.read_at) && Number.isFinite(photo.time) ? listing.read_at - photo.time : null;
  if (photo.verdict) {
    const r = reasonOf(photo), ok = photo.verdict === 'ok';
    const after = took !== null && took >= 0 ? seconds(took) : null;
    const own = a?.state === 'done' && inRead && Number.isFinite(a.seconds) ? seconds(a.seconds) : null;
    const outlier = ok && outliersOf(listing).some(o => o.id === photo.id);
    if (outlier) return {stage: 'outlier', act: pair('和多数不一致', 'Outside the majority'),
      why: pair('这张自己读得出来，但读数和多数照片对不上，没参与取值。建议转一下盘重拍这张。', 'This photo reads fine on its own, but its value does not match the majority, so it was left out. Turn the disc and retake it.'),
      seconds: took, when: after ? pair(`收到后 ${after.zh} 读完`, `read ${after.en} after it arrived`) : pair('', '')};
    return {stage: ok ? 'ok' : 'retake', act: r.act, why: r.why, seconds: took,
      when: after ? pair(`收到后 ${after.zh} 读完${own ? `（读取本身 ${own.zh}）` : ''}`, `read ${after.en} after it arrived${own ? ` (the read itself took ${own.en})` : ''}`) : pair('', '')};
  }
  if (a?.state === 'reading' && inRead) {
    const s = seconds(a.seconds);
    return {stage: 'reading', act: pair('读取中', 'Reading'), why: pair(`电脑正在读，已 ${s.zh}。`, `The computer is reading it: ${s.en} so far.`), seconds: a.seconds, when: pair('', '')};
  }
  if (a?.state === 'reading') return {stage: 'queued', act: pair('排队', 'Queued'),
    why: pair('电脑在读前面的照片，读完就接着读这张。', 'The computer is reading earlier photos; this one is next.'), when: pair('', '')};
  if (a?.state === 'failed' && inRead) return {stage: 'failed', act: pair('没读完', 'Not read'),
    why: pair('这一轮读取没有完成。电脑会在下一张到达时再读；也可以在电脑上重试。', 'This read did not finish. The computer reads again when the next photo arrives, or retry on the computer.'), when: pair('', '')};
  const waited = Number.isFinite(photo.time) ? seconds(now - photo.time) : pair('', '');
  return {stage: 'waiting', act: pair('已收到', 'Received'),
    why: pair(`电脑已存好，等待读取${waited.zh ? `（已 ${waited.zh}）` : ''}。`, `Saved on the computer, waiting to be read${waited.en ? ` (${waited.en})` : ''}.`), when: pair('', '')};
}

// Whether the computer's photo step is open on this run. Only that page starts a read.
export function deskWords(listing = {}) {
  if (listing.desk_elsewhere) return {state: 'elsewhere', words: pair(
    '电脑已经换到另一次标定。在电脑上重新扫码；这个页面发的照片只算到原来那一次，不会挂到新的上。',
    'The computer has moved to another calibration. Scan its new code; photos sent here stay with the earlier run and never join the new one.')};
  const waiting = (listing.photos || []).some(p => !p.verdict) && listing.analysis?.state !== 'reading';
  if (waiting && (listing.desk_age === null || listing.desk_age === undefined || listing.desk_age > 12)) return {state: 'closed', words: pair(
    '照片已存在电脑上，但电脑上的“拍照”这一步没打开，所以还没开始读。在电脑上回到标定的拍照步骤，会自动读取。',
    'Your photos are saved on the computer, but its photo step is not open, so nothing is being read. Open the calibration’s photo step on the computer and it reads them by itself.')};
  return {state: 'open', words: pair('', '')};
}

// The ok photos the core put outside a unique majority. A tie between two camps names nobody, so none here.
export function outliersOf(listing = {}) {
  const a = listing.adoption || {};
  if (a.state === 'split') return [];
  const list = Array.isArray(a.outliers) ? a.outliers : Array.isArray(listing.outliers) ? listing.outliers : [];
  return list.filter(o => o && o.id);
}
// "These few disagree with the majority; retake them", naming at most three by their file names.
export function outlierWords(outliers = []) {
  if (!outliers.length) return null;
  const names = outliers.slice(0, 3).map(o => o.name || o.id).join('、'), more = outliers.length > 3 ? ` 等 ${outliers.length} 张` : '';
  const namesEn = outliers.slice(0, 3).map(o => o.name || o.id).join(', '), moreEn = outliers.length > 3 ? ` and ${outliers.length - 3} more` : '';
  return pair(`这几张和多数不一致，没参与取值，建议转盘重拍：${names}${more}。`, `These disagree with the majority and were left out; turn the disc and retake them: ${namesEn}${moreEn}.`);
}

// L in plain numbers: always signed, never "0" for a value that does not exist.
const mm = v => Number.isFinite(v) ? `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(3)} mm` : '';

// Why the core did not accept a group of photos (photo.photo_agreement), as what to do next.
export const agreementReasons = {
  same_pose: pair('几张照片的角度太接近（盘面转角相差不到 10°），不能互相印证。把盘转大一点角度再拍一张。',
    'The photos are too close in angle (less than 10° of disc rotation apart), so they cannot check each other. Turn the disc further and take another.'),
  duplicate_photo: pair('有两张其实是同一张原图。转一下盘，拍一张新的。', 'Two of them are the same original picture. Turn the disc and take a new one.'),
  unknown_spread_or_pose: pair('读数缺少一致性范围或盘面转角，不能判断。再拍一张不同角度的。', 'A reading lacks its spread or disc angle, so agreement cannot be checked. Take another from a different angle.'),
  unknown_photo_input: pair('有照片的原图记录不完整。重新发送原图再读一次。', 'A photo’s original is not recorded. Send the original again and reread.'),
  ambiguous_majority: pair('读数分成了两派，各占一样多，没有多数。请再拍几张不同角度的。', 'The readings split into two equal camps with no majority. Take a few more from different angles.'),
  group_not_ok: pair('两张一致，但读取器的整组检查没有通过。再拍一张不同角度的。', 'The photos agree, but the reader’s group check did not pass. Take another from a different angle.'),
};

// Whether the along-track constant (L) is adopted from this read. States follow the core's majority rule:
// a unique largest set of ok photos that share a common value, at least two-thirds of all ok photos, with two
// distinct originals at least 10 degrees apart; L is their median. One alone is provisional. Two equal camps
// that do not overlap are a split: nobody is named an outlier.
export function adoptionWords(adoption = {}, photos = []) {
  const spread = Number.isFinite(adoption.spread_mm) ? ` ${adoption.spread_mm.toFixed(3)} mm` : '';
  const agree = Number.isFinite(adoption.agreeing_count) ? adoption.agreeing_count : Number.isFinite(adoption.n_agree) && adoption.n_agree > 0 ? adoption.n_agree : null;
  const okCount = Number.isFinite(adoption.ok_count) ? adoption.ok_count : Number.isFinite(adoption.n_ok) ? adoption.n_ok : null;
  const need = Number.isFinite(adoption.required_count) ? adoption.required_count : null;
  const out = outlierWords(adoption.state === 'split' ? [] : adoption.outliers || []);
  const plus = (base, extra) => extra ? pair(base.zh + extra.zh, base.en + ' ' + extra.en) : base;
  switch (adoption.state) {
    case 'adopted': return {state: 'adopted', title: pair('已采用', 'Adopted'),
      body: plus(agree && okCount ? pair(`${okCount} 张可用照片里 ${agree} 张读数一致，是多数（至少要 ${need ?? '三分之二'}${need ? ' 张' : ''}），采用它们的中位数。`,
          `${agree} of ${okCount} usable photos agree, a majority (at least ${need ?? 'two-thirds'} needed); their median is adopted.`)
        : pair(`${agree ? agree + ' 张' : '几张'}不同角度的照片读数一致，采用它们的中位数。`, `${agree || 'Several'} photos from different angles agree; their median is adopted.`), out)};
    case 'provisional': {
      const v = mm(adoption.provisional_mm);
      return {state: 'provisional', title: pair('暂定', 'Provisional'),
        body: pair(`临时 L${v ? ' ' + v : ''}，尚未采用。只有一张照片读出来；转一下盘，再拍一张不同角度的，两张一致才采用。用同一张盘，不用重刻。`,
          `Provisional L${v ? ' ' + v : ''}, not adopted. Only one photo was read; turn the disc and take another from a different angle. Two that agree are adopted. Same disc, no new burn.`)};
    }
    case 'disagree': {
      const two = okCount === 2;
      const base = two ? pair(`两张读出的值对不上${spread ? `（相差${spread}）` : ''}，不采用。转一下盘再拍一张，看哪张和它一致；用同一张盘，不用重刻。`,
          `The two photos give different values${spread ? ` (${spread.trim()} apart)` : ''}, so neither is adopted. Turn the disc and take another to see which it agrees with. Same disc, no new burn.`)
        : agree && okCount ? pair(`最多 ${agree} 张读数一致，没到 ${okCount} 张可用照片的三分之二（${need ?? Math.ceil(okCount * 2 / 3)} 张），不采用。转一下盘再拍几张；用同一张盘，不用重刻。`,
          `At most ${agree} photos agree, short of two-thirds of the ${okCount} usable ones (${need ?? Math.ceil(okCount * 2 / 3)}), so nothing is adopted. Turn the disc and take a few more. Same disc, no new burn.`)
        : pair(`照片读出的值对不上${spread ? `（相差${spread}）` : ''}，不采用。转一下盘再拍几张；用同一张盘，不用重刻。`, `The photos disagree${spread ? ` (${spread.trim()} apart)` : ''}, so nothing is adopted. Turn the disc and take a few more. Same disc, no new burn.`);
      return {state: 'disagree', title: two ? pair('两张不一致', 'Two photos disagree') : pair('读数不一致', 'Readings disagree'), body: plus(base, out)};
    }
    case 'split': return {state: 'split', title: pair('分成两派', 'Split into two camps'),
      body: pair(`两组读数分成了两派${agree ? `（各 ${agree} 张）` : ''}，一样多又互不重叠，没法判断哪组对，这次不采用。请再拍几张不同角度的；用同一张盘，不用重刻。`,
        `The readings split into two camps${agree ? ` of ${agree} each` : ''} that do not overlap, so neither can be preferred and nothing is adopted. Take a few more from different angles. Same disc, no new burn.`)};
    case 'refused': {
      const why = agreementReasons[adoption.reason] || pair('这组照片没有通过采用检查。再拍一张不同角度的。', 'This group did not pass the adoption check. Take another from a different angle.');
      return {state: 'refused', title: pair('不采用', 'Not adopted'), body: plus(why, out)};
    }
    default: {
      const any = photos.length, read = photos.filter(p => p.verdict).length;
      return {state: 'none', title: pair(any ? (read ? '还没有可用的' : '等待读取') : '还没有照片', any ? (read ? 'Nothing usable yet' : 'Waiting to read') : 'No photos yet'),
        body: any ? (read ? pair('按每张下面写的做，再拍一张。需要至少两张不同角度、读数一致的照片。', 'Follow the advice under each photo and take another. At least two photos from different angles that agree are needed.')
          : pair('电脑收到照片后才读，读完才知道能不能用。', 'The computer reads each photo after it arrives; only then is it known whether it can be used.'))
          : pair('拍第一张。至少要两张不同角度、读数一致的照片。', 'Take the first photo. At least two from different angles that agree are needed.')};
    }
  }
}

// Whether a picture made from this run will use the adopted L (the core's photo_l gate), and if not, why.
// Shown after adoption; it never claims a correction the core would refuse.
export const applicationReasons = {
  no_photo: pair('还没有照片结果。', 'No photo result yet.'),
  verdict_not_ok: pair('照片还没有被采用。', 'The photos are not adopted yet.'),
  unknown_disc: pair('没填标靶盘号，不会用到出图上。在上面填这张标靶盘的编号，再读一次。', 'No target disc number, so it is not used for pictures. Enter this target disc’s number above and read again.'),
  different_disc: pair('这些照片属于不同的标靶盘，不能合在一起。', 'These photos belong to different target discs and cannot be combined.'),
  unknown_burn_path: pair('不知道这张标靶盘是用哪台刻录器、什么程序和模式刻的，所以不能说已修正。用这一页刻标靶盘，刻录信息会自动记下。', 'It is not known which burner, program and mode burned this target disc, so no correction can be claimed. Burn the target from this page and the details are recorded.'),
  unknown_drive: pair('测量记录里没有光驱身份，不能确认是同一台光驱。', 'The measurement does not record the drive, so it cannot be matched.'),
  different_drive: pair('照片对应的是另一台光驱或另一台电脑。', 'The photos belong to another drive or computer.'),
  different_run: pair('照片对应的是另一次测量，或测量已经改过。', 'The photos belong to another measurement, or the measurement changed.'),
  different_media: pair('照片和测量的盘种不一致。', 'The photos and the measurement are for different disc kinds.'),
  unsupported_media: pair('照片 L 只用于 CD 和 DVD。', 'Photo L applies to CD and DVD only.'),
  unsupported_model: pair('这种测量模型（CLV）没有可修正的角度映射。', 'This measurement model (CLV) has no angle map to correct.'),
  unknown_reader: pair('读取器版本对不上，不采用。', 'The reader version does not match, so it is not used.'),
  unknown_channel_bit_length: pair('测量里缺少通道位长度，DVD 换算不了。', 'The measurement lacks the channel bit length needed for DVD.'),
  missing_L: pair('结果里没有 L。', 'The result has no L.'),
  inconsistent_L: pair('记录里的 L 前后不一致，不采用。', 'The recorded L is inconsistent, so it is not used.'),
  invalid_photo: pair('照片记录读不出或不完整。', 'The photo record is unreadable or incomplete.'),
  opted_out: pair('这次出图选择了不用照片修正。', 'This picture opted out of the photo correction.'),
  invalid_saved_photo_L: pair('ISO 旁保存的 L 记录校验不通过，没有沿用。', 'The L saved beside the ISO failed its check and was not reused.'),
  missing_image_record: pair('没有找到这张 ISO 的出图记录。', 'This ISO’s image record was not found.'),
  ...agreementReasons,
  one_photo_provisional: pair('只有一张照片，临时值不会用。', 'Only one photo; a provisional value is never used.'),
  photos_disagree: pair('照片之间不一致，不会用。', 'The photos disagree, so it is not used.'),
  no_accepted_photos: pair('还没有能用的照片。', 'No usable photos yet.'),
};
// The value in the run's own units: CD frames, or DVD sectors; never CD frames for a DVD.
function lUnits(app, media) {
  const parts = [mm(app.L_mm)];
  if (media === 'cd' && Number.isFinite(app.frames)) parts.push(`${app.frames.toFixed(2)} frames`);
  else if (Number.isFinite(app.sectors)) parts.push(`${app.sectors.toFixed(3)} sectors`);
  return parts.filter(Boolean).join(' · ');
}
export function applicationWords(app = {}, media = 'cd') {
  if (app.written) {
    const v = lUnits(app, media), disc = app.disc_id ? `（标靶盘 ${app.disc_id}）` : '', discEn = app.disc_id ? ` (target disc ${app.disc_id})` : '';
    return {applied: true, words: pair(`出图会用 L ${v}${disc}。`, `Pictures will use L ${v}${discEn}.`)};
  }
  const why = applicationReasons[app.reason] || pair('出图不会用这次的照片 L。', 'Pictures will not use this photo L.');
  return {applied: false, words: why};
}
// A picture ISO's own record (image job result.photo_l). `reopened`: the ISO was opened again, not just made.
export function photoLWords(photoL = {}, media = 'cd', {reopened = false} = {}) {
  if (photoL?.written) {
    const v = lUnits(photoL, media), version = photoL.reader_version ? ` · reader ${photoL.reader_version}` : '';
    return reopened ? pair(`沿用此 ISO 已保存的 L ${v}${version}。`, `Reusing the L saved with this ISO: ${v}${version}.`)
      : pair(`这张 ISO 用了照片 L ${v}${version}。`, `This ISO uses photo L ${v}${version}.`);
  }
  const why = applicationReasons[photoL?.reason] || pair('这张 ISO 没有用照片修正。', 'This ISO has no photo correction.');
  return pair(`这张 ISO 没有用照片 L：${why.zh}`, `This ISO has no photo L: ${why.en}`);
}

// The shooting method that works in an ordinary room (from users' own shots).
export const shootingTips = [
  pair('房间有吸顶灯：背对它站，让灯在你身后。', 'With a ceiling lamp: stand with your back to it, so it is behind you.'),
  pair('盘数据面朝上，朝自己转 20–30°，让彩色条纹出来。', 'Data side up, tilt the disc 20–30° towards you until the colour bands show.'),
  pair('盘上出现吸顶灯的白色圆形反光，就微调角度避开它。', 'If the lamp makes a round white glare on the disc, tilt a little to move it off.'),
  pair('整张盘都在画面里，四周留一点边。', 'Keep the whole disc in frame, with a little margin.'),
  pair('每拍一张都转一下盘，换个角度；至少两张。', 'Turn the disc between shots; at least two photos.'),
  pair('重拍用同一张标靶盘，不用重新刻。', 'Retakes use the same target disc; nothing is burned again.'),
];
