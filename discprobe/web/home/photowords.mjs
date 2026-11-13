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
// Stages: waiting (received, no read yet), queued (a read of other photos is running), reading, ok, retake, failed.
export function photoStage(photo = {}, listing = {}) {
  const a = listing.analysis, inRead = !!a && (a.photos || []).includes(photo.id);
  const now = Number.isFinite(listing.now) ? listing.now : Date.now() / 1000;
  const covered = (listing.read_photos || []).includes(photo.id);
  const took = covered && Number.isFinite(listing.read_at) && Number.isFinite(photo.time) ? listing.read_at - photo.time : null;
  if (photo.verdict) {
    const r = reasonOf(photo), ok = photo.verdict === 'ok';
    const after = took !== null && took >= 0 ? seconds(took) : null;
    const own = a?.state === 'done' && inRead && Number.isFinite(a.seconds) ? seconds(a.seconds) : null;
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

// Whether the along-track constant (L) is used. States follow the core's two-photo rule:
// at least two photos at different angles that agree are needed; one alone is provisional.
export function adoptionWords(adoption = {}, photos = []) {
  const spread = Number.isFinite(adoption.spread_mm) ? ` ${adoption.spread_mm.toFixed(3)} mm` : '';
  const n = Number.isFinite(adoption.n_agree) ? adoption.n_agree : null;
  switch (adoption.state) {
    case 'adopted': return {state: 'adopted', title: pair('已采用', 'Adopted'),
      body: pair(`${n ? n + ' 张' : '几张'}不同角度的照片读数一致${spread ? `（相差${spread}）` : ''}，沿轨常数会用在这次标定上。`,
        `${n ? n : 'Several'} photos from different angles agree${spread ? ` (within${spread})` : ''}; the along-track constant is used for this calibration.`)};
    case 'provisional': return {state: 'provisional', title: pair('暂定', 'Provisional'),
      body: pair('只有一张照片读出来，只算暂定，不会用。转一下盘，再拍一张不同角度的；两张一致才采用。用同一张盘，不用重刻。',
        'Only one photo was read, so the value is provisional and not used. Turn the disc and take one more from a different angle; two that agree are adopted. Use the same disc, no new burn.')};
    case 'disagree': return {state: 'disagree', title: pair('两张不一致', 'Photos disagree'),
      body: pair(`几张照片读出的值对不上${spread ? `（相差${spread}）` : ''}，这次不采用。确认拍的都是这次刻的标靶盘，转一下盘再拍一张；用同一张盘，不用重刻。`,
        `The photos give different values${spread ? ` (${spread.trim()} apart)` : ''}, so none is used. Check they all show this run’s target disc, turn it and take another. Same disc, no new burn.`)};
    default: {
      const any = photos.length, read = photos.filter(p => p.verdict).length;
      return {state: 'none', title: pair(any ? (read ? '还没有可用的' : '等待读取') : '还没有照片', any ? (read ? 'Nothing usable yet' : 'Waiting to read') : 'No photos yet'),
        body: any ? (read ? pair('按每张下面写的做，再拍一张。需要至少两张不同角度、读数一致的照片。', 'Follow the advice under each photo and take another. At least two photos from different angles that agree are needed.')
          : pair('电脑收到照片后才读，读完才知道能不能用。', 'The computer reads each photo after it arrives; only then is it known whether it can be used.'))
          : pair('拍第一张。至少要两张不同角度、读数一致的照片。', 'Take the first photo. At least two from different angles that agree are needed.')};
    }
  }
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
