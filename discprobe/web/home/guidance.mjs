// Display advice follows guide.py after_timing, after_geo, after_geo_stop and AFTER_BURN.
// These are instructions, never a substitute for a core verdict or a measurement.
const pair = (zh, en) => ({zh, en});
// Shared by the computer strip and the token-scoped phone page. New reader
// codes need only one entry here; unknown codes retain the server's explanation.
export const photoReasons = {
  ok: pair('照片可以用。', 'The photo is usable.'),
  no_rim: pair('把整张盘拍进画面，四周留一点边。', 'Keep the whole disc in frame with a little space around it.'),
  too_few_votes: pair('转动盘，移动灯光，让条纹更清楚。', 'Turn the disc and move the light to make the pattern clearer.'),
  few_inliers: pair('转动盘，再拍一张清楚的条纹。', 'Turn the disc and take another clear photo of the pattern.'),
  rings_not_found: pair('把整张盘拍进画面，移动灯光让圆环清楚。', 'Keep the whole disc in frame and move the light to show the rings.'),
  weak_peak: pair('条纹太弱。移动灯光，轻点盘面使相机对焦。', 'The pattern is faint. Move the light and tap the disc to focus.'),
  two_peaks: pair('有两个可能的位置。转动盘，换个角度重拍。', 'Two positions look possible. Turn the disc and retake from another angle.'),
  poor_angle_coverage: pair('转动盘，让更多方向的条纹出现在画面里。', 'Turn the disc to show the pattern in more directions.'),
  poor_radius_coverage: pair('把整张盘拍进画面，让内圈和外圈都清楚。', 'Keep the whole disc in frame so both inner and outer rings are clear.'),
  large_residual: pair('条纹位置对不上。把盘放平，拍全盘。', 'The pattern does not fit. Lay the disc flat and photograph the whole disc.'),
  unstable_L: pair('这张照片的位置读数不稳定。转动盘重拍。', 'The position reading varies within this photo. Turn the disc and retake.'),
  shape_not_1_over_r: pair('内外圈的读数对不上。拍全盘，移动灯光后重拍。', 'Inner and outer readings disagree. Keep the whole disc in frame and move the light.'),
  unreadable_image: pair('照片打不开。重新拍照，或从相册导出 JPEG 后再发。', 'The image could not be opened. Retake or export a JPEG from Photos and send it.'),
  duplicate_photo: pair('这张照片重复了。转动盘，拍一张不同角度的。', 'This photo is a duplicate. Turn the disc and take a different view.'),
};
export function photoReasonWords(photo = {}) {
  return Object.prototype.hasOwnProperty.call(photoReasons, photo.status) ? photoReasons[photo.status] : pair(photo.reason || '', photo.reason || '');
}
export function photoStateWords(photo = {}) {
  if (!photo.verdict) return pair('读取中', 'Reading');
  if (photo.verdict === 'ok') return pair('可以用', 'Usable');
  const reason = photoReasonWords(photo);
  return pair('重拍：' + reason.zh, 'Retake: ' + reason.en);
}
export function photoOverallWords(photos = [], verdict) {
  // An old ok read cannot cover newly arrived, as-yet unread photos.
  if (verdict === 'ok' && photos.length && photos.every(p => p.verdict))
    return pair('够了，回到电脑上看结果。', "That's enough. Look at the computer.");
  // the phone page asks for 3 (the reader needs 2 clear ones; the third covers a retake)
  if (!photos.length) return pair('还没收到照片。拍第一张吧。', 'No photos yet. Take the first one.');
  if (photos.some(p => !p.verdict)) return pair(`已收到 ${photos.length} 张，正在读……`, `Received ${photos.length}. Reading…`);
  const ok = photos.filter(p => p.verdict === 'ok').length, more = Math.max(1, 3 - ok);
  return pair(`已收到 ${photos.length} 张，能用 ${ok} 张。再拍 ${more} 张不同角度的。`,
    `Received ${photos.length}, ${ok} usable. Take ${more} more from different angles.`);
}
// These words describe the saved file's decision, never the provisional photo read.
export function photoSaveWords(decision = {}) {
  if (decision.written === true && Number.isFinite(decision.frames)) return pair(
    `沿轨常数已写入：L = ${decision.frames} frames。来自照片，盘批次无关，换光驱要重拍；只适用于这次几何测量和刻录路径。`,
    `Along-track constant written: L = ${decision.frames} frames. From photos, independent of disc batch; rephotograph after changing drives. Only for this geometry run and burn path.`);
  const reasons = {
    different_run: pair('照片对应的是另一次测量。', 'The photos belong to a different geometry run.'),
    different_drive: pair('照片对应的是另一台光驱或另一台电脑。', 'The photos belong to a different drive or computer.'),
    unknown_drive: pair('不知道照片对应的具体光驱身份。', 'The specific drive identity is unknown.'),
    verdict_not_ok: pair('照片没有通过检查。', 'The photo verdict is not ok.'),
    missing_L: pair('照片没有给出可信的 L，数值未知。', 'The photo has no usable L; its value is unknown.'),
    no_photo: pair('没有照片结果，数值未知。', 'No photo result; its value is unknown.'),
    not_cd: pair('照片没有给出适用于 CD 的帧数。', 'The photo has no applicable CD frame value.'),
    invalid_photo: pair('照片记录无法读取或不完整。', 'The photo record is unreadable or incomplete.'),
    invalid_preset: pair('无法核对已保存的预设。', 'The saved preset could not be verified.'),
  };
  const reason = reasons[decision.reason] || pair('没有已确认写入的 L，数值未知。', 'No confirmed saved L; its value is unknown.');
  return pair('沿轨常数没写进去：' + reason.zh, 'Along-track constant not written: ' + reason.en);
}
// Body copy never contains terminal syntax. Actions are resolved from the same verdict.
export function recoveryKind(result = {}) {
  const part = result.geo || result.timing || result;
  const m = part.measurement || {}, reason = m.stopped || '';
  if (/medium|recorded area|fails on|cannot read/.test(reason)) return 'media';
  if (/not turning at a constant speed/.test(reason)) return 'rotation';
  if (!result.geo && m.rotation && !['unknown','CAV'].includes(m.rotation)) return 'rotation';
  return ['good','usable','too_noisy','drive_changed','narrow_span','stopped_early'].includes(part.verdict) ? part.verdict : 'unknown';
}
export function measurementRecovery(result = {}) {
  const part = result.geo || result.timing || result, m = part.measurement || {}, a = m.speed_advice;
  if (!result.geo && m.rotation === 'CLV' && a) {
    const route = a.media === 'bd'
      ? pair(' 可在终端使用 BD 的 CLV 分区拟合。', ' The BD CLV zone fit is available in Terminal.')
      : a.media === 'cd'
        ? pair(' CD 的 CLV 实验路线需要独立的速度或轨距依据，测不出沿轨常数，也不是已标定的角度图。', ' The experimental CD CLV route needs an independent speed or pitch anchor; it cannot determine the along-track constant or a calibrated angle map.')
        : pair('', '');
    const body = a.exhausted
      ? a.all_clv
        ? pair(`这台光驱在所有试过的 ${a.media.toUpperCase()} 速度下似乎都保持恒定线速度。请换一台光驱。`, `This drive appears to keep a constant linear speed for ${a.media.toUpperCase()}s at every speed tried. Try another drive.`)
        : pair('列表中的速度都试过了，请换一台光驱。', 'Every speed on the list has been tried. Try another drive.')
      : pair(`这次保持恒定线速度。下一步尝试尚未试过的 ${a.next_speed} kB/s；CD 在较高速度下可能改用恒定角速度。`, `This run kept a constant linear speed. Next try the untried ${a.next_speed} kB/s; higher CD speeds may allow CAV.`);
    return pair(body.zh + route.zh, body.en + route.en);
  }
  if (m.completion_status && m.completion_status !== 'target_reached') return pair(
    `测量只完成了一部分。实测范围为 ${JSON.stringify(m.coverage?.measured_intervals_mm || m.span_mm || [])} mm；范围外属于外推，局部误差小不能证明整盘可用。`,
    `Partial measurement. Measured radii: ${JSON.stringify(m.coverage?.measured_intervals_mm || m.span_mm || [])} mm. Outside is extrapolation; small local error does not validate the whole disc.`);
  if (m.correction && ['good','usable'].includes(part.verdict)) return pair(
    '盘的轨距会变化，已自动加密测量并保存平滑角度修正，生成图片时会自动使用。详情有重复读数误差、独立检查、耗时及测点稀疏区；范围外仍是外推。DIS 预设可能无法复现这条曲线，导出前须检查转换误差。',
    'Track pitch varies. Extra points were measured and a smooth angle correction was saved; images use it automatically. Details contain repeat errors, independent checks, time and thin areas. Outside measured radii is extrapolation. A DIS preset may not reproduce the curve: check conversion error.');
  return ({
    good: pair('测量可用，可以保存。', 'The measurement is usable and ready to save.'),
    usable: pair('测量有些噪声，但仍可使用。可以保存，也可以保留这张盘再测一次。', 'There is some noise, but the measurement is usable. Save it, or keep this disc and measure again.'),
    too_noisy: pair('这次读数太乱，不能依赖。保留这张测量盘，重新检查转速再测；仍然如此时，试试其他读取速度或光驱。', 'The readings are too noisy to rely on. Keep this measurement disc, check rotation and measure again. If this persists, try another reading speed or drive.'),
    drive_changed: pair('光驱在测量前后的状态不一致，不能依赖这次结果。保留这张盘，重新检查转速并测量。', 'The drive behaved differently before and after measuring. Do not rely on this result. Keep the disc, check rotation and measure again.'),
    narrow_span: pair('只测准了盘面的一部分，范围以外还需要补测。保留这张盘，检查转速后重新测量。', 'Only part of the disc was measured. The rest still needs measuring. Keep this disc, check rotation and measure again.'),
    stopped_early: pair('测量中途停了，不能当作整张盘的结果。保留这张盘，重新检查转速再测；若总停在同一处，请查看详情中的避开方法。', 'Measuring stopped early. This is not a whole-disc result. Keep the disc, check rotation and measure again. If it always stops in one place, see Details for ways to leave that area out.'),
    unknown: pair('还不知道结果是否可用。先保留数据，重新检查转速；若仍无法确定，请查看详情中的分析方法，不必急着重刻。', 'It is not known whether this result is usable. Keep the data and check rotation again. If it remains uncertain, see Details for analysis before burning another disc.'),
    rotation: pair('光驱没有保持稳定转速。先手动弹出并放回这张测量盘，再检查转速。仍不稳定时，请试试其他读取速度或光驱。', 'The drive did not hold a steady rotation. Manually eject and reload this measurement disc, then check rotation again. If it stays unstable, try another reading speed or drive.'),
    media: pair('这张盘有一部分读不出来。如果盘上还有图案或其他内容，请只测其中的测量区域，方法见详情。如果整张都是测量数据，盘可能已损坏，请换一张同批空白盘。', 'Part of this disc could not be read. If it also contains a picture or other content, measure only its measurement area; see Details. If the whole disc contains measurement data, it may be damaged. Use a fresh blank from the same batch.'),
  })[recoveryKind(result)];
}
export function recoveryAction(result = {}) {
  const kind = recoveryKind(result);
  const m = (result.timing || result).measurement || {};
  if (!result.geo && m.rotation === 'CLV' && m.speed_advice?.exhausted)
    return {id:'drive', label:pair('选择其他光驱', 'Choose another drive')};
  if (['good','usable'].includes(kind) && result.geo) return {id:'save', label:pair('保存测量', 'Save measurement')};
  if (kind === 'media') return {id:'blank', label:pair('换空白盘并检测', 'Check a new blank')};
  return {id:'measure', label:pair('检查转速并重测', 'Check rotation and remeasure')};
}
// The executor is shared by the UI and drive-free tests. Geometry starts only after a usable CAV check.
export async function remeasure(run, previous = {}) {
  const m = (previous.timing || previous).measurement || {}, a = m.speed_advice;
  if (m.rotation === 'CLV' && a?.exhausted) return previous;
  const timing = await run('timing', m.rotation === 'CLV' && a?.next_speed ? {speed:a.next_speed} : {});
  if (!['good','usable'].includes(timing?.verdict) || timing.measurement?.rotation !== 'CAV') return {timing};
  const geo = await run('geo', {speed:'keep'});
  return {timing, geo};
}
export function recoveryCommands(result, {drive, media, sectors}) {
  const part = result.geo || result.timing || {}, kind = recoveryKind(result);
  const base = `python -m discprobe`, flags = `--drive ${JSON.stringify(drive)} --media ${media}`;
  const m = part.measurement || {}, a = m.speed_advice;
  if (!result.geo && m.rotation === 'CLV' && a) {
    const commands = a.next_speed ? [`${base} timing ${flags} --speed ${a.next_speed}`] : [];
    if (media === 'bd') commands.push(`${base} geo ${flags} --speed keep --bd-zones 25`);
    return commands.join('\n');
  }
  const commands = [`${base} timing ${flags}`, `${base} geo ${flags} --speed keep`, `${base} timing ${flags} --speed SPEED`, `${base} geo ${flags} --speed keep`];
  if (kind === 'media' || kind === 'stopped_early') commands.push(`${base} geo ${flags} --ranges START-END`);
  if (kind === 'narrow_span') {
    commands.push(`${base} disexport --media ${media} --geo ${JSON.stringify(part.path)} --sectors ${sectors} --r-min START --r-max END --output presets/fitted.json`);
  }
  if (kind === 'unknown' && result.geo?.path) commands.push(`python tools/geo_polyfit.py ${JSON.stringify(part.path)}`);
  if (part.measurement?.correction && part.path) commands.push(`${base} image --media ${media} --geo ${JSON.stringify(part.path)} --correction ${JSON.stringify(part.path + '/' + part.measurement.correction)} --picture my_picture.png --output iso/picture.iso`);
  return commands.join('\n');
}
export const cdPhoto = pair(
  '照片还没有给出可保存的沿轨常数。计时测不出沿轨道的绝对位置，标定还未完成。可以继续拍不同角度的照片；也可以保留测量、导出 DIS 预设，在 DiscImageStudio 用另一张同批空盘做精细标定，再刻成品。',
  'The photos have not supplied an along-track constant that can be saved. Timing cannot determine the absolute along-track position, so calibration is incomplete. Take more photos from different angles, or keep the measurement, export a DIS preset and fine-calibrate in DiscImageStudio on another blank from this batch before burning the picture.');
// One statement of how many discs, used by the start guide, the calibration page, the new-work form and the
// preview. 3 is the goal, 4 when the error is large; it is never a promise, and a bad photo costs no disc.
export const discGoal = pair('目标是第 3 张盘出成品；误差大时第 4 张。这是目标，不是保证。', 'The goal is the finished picture on disc 3, or disc 4 if the error is large. A goal, not a promise.');
export const discRoute = [
  pair('第 1 张：测量盘。刻随机数据，用来测转速和盘面几何。', 'Disc 1: the measurement disc. Random data, to measure speed and geometry.'),
  pair('第 2 张：检查盘。刻标靶或第一张图，用手机拍照，看实际偏了多少。', 'Disc 2: the check disc. A target or your first picture, photographed to see how far off it is.'),
  pair('第 3 张：成品，用修正后的结果刻。', 'Disc 3: the finished picture, burned with the corrected result.'),
  pair('误差大时：第 3 张再检查一次，第 4 张才是成品。', 'If the error is large, disc 3 is a second check and disc 4 is the finished picture.')];
export const retakeNote = pair('照片拍坏了（太暗、没拍全、有反光）只要重拍，不用重刻。', 'A bad photo (too dark, not the whole disc, glare) is retaken, not re-burned.');
export function calibrationBudget(media) {
  const cd = media === 'cd';
  if (media === 'bd') return {
    items: [pair('BD 仍在试验中：耗盘数量未知。', 'BD is experimental: the disc budget is unknown.'), pair('分区测量约 2 分钟；刻录时间未知。', 'Zone measurement: about 2 minutes; burn time unknown.')],
    note:pair('刻好测量盘后才能检查光驱；暂无可靠的总用时预算。', 'The drive can only be checked after burning the measurement disc; no reliable total time is available.'),
    details:pair('两个半径仍需其他依据，不能套用 DVD 的预算。', 'The two radii still need other evidence. The DVD budget does not apply.')};
  return {
    items:[
      discGoal,
      pair('生成测量文件：几十秒。', 'Make the measurement file: tens of seconds.'),
      cd ? pair('刻测量盘：约 11 分钟，依光驱而异。', 'Burn the measurement disc: about 11 minutes, depending on the drive.') : pair('刻测量盘：约 14 分钟。', 'Burn the measurement disc: about 14 minutes.'),
      pair('检查转速：1–3 分钟；测量盘面：约 5 分钟。', 'Check rotation: 1–3 minutes; measure the disc: about 5 minutes.'),
      cd ? pair('拍照检查和刻成品：时间尚不确定，见详情。', 'Photo check and the picture burn: time unknown; see Details.') : pair('刻成品：约 14 分钟，依速度和内容而异。', 'Burn the picture: about 14 minutes, depending on speed and content.')],
    note:pair('刻好测量盘后才能检查光驱；约一小时是目标，不是保证。', 'The drive can only be checked after the measurement burn; about an hour is a goal, not a promise.'),
    details:{zh:[...discRoute.map(x => x.zh), retakeNote.zh].join(' ') + ' 以上为 README 与现有流程的估时，不是新测试。失败可能多耗盘。保留测量盘，同批盘可复用。' + (cd ? ' CD 的 11 分钟来自 GH70N、8 倍速。页面会自动合读不同角度的照片，读取沿轨常数；读不准时会说明重拍原因。也可以导出 DIS 预设，在 DiscImageStudio 用另一张同批空盘精细标定。' : ''),
      en:[...discRoute.map(x => x.en), retakeNote.en].join(' ') + ' These estimates come from the README and existing workflow, not new benchmarks. Failures may cost more discs. Keep the measurement disc for this batch.' + (cd ? ' The CD observation was 11 minutes at 8× on GH70N. The page automatically reads photos from different angles together for the along-track constant, with retake advice when needed. Alternatively, export a DIS preset and fine-calibrate in DiscImageStudio with another blank.' : '')}};
}
export function budgetHTML(media, lang) {
  const b = calibrationBudget(media);
  return `<section class="cal-budget"><ul>${b.items.map(x=>`<li>${x[lang]}</li>`).join('')}</ul><p>${b.note[lang]}</p><details><summary>${lang === 'zh' ? '详情' : 'Details'}</summary><p>${b.details[lang]}</p></details></section>`;
}
export const afterBurn = [
  pair('关掉房间的灯，把手机手电等小光源放在眼睛旁边。盘拿到约一米外，轻轻倾斜，避开灯和自己的倒影，慢慢转动；盘面暗下来时能看到图。彩虹扇面是沟槽，不是图片。看的是数据面，与预览相同。', 'Turn off the room lights and hold a small light, such as a phone torch, beside your eyes. Hold the disc about a metre away, tilt it away from reflections of the light and yourself, and turn it slowly. The picture shows when the surface goes dark. The rainbow fan is the grooves, not your picture. Look at the data side, as in the preview.'),
  pair('图案位置正确就完成了，以后同批盘可以复用这次测量。看不见图：先别再刻，按顺序查三样：光照（最常见）、刻录报告（写入、关盘、回读）、几何。线条扭曲或断开：核对是否同批盘、同一台刻录机；若是，几何可能不准。只有光照和刻录报告都没问题、线条仍然扭曲时，才用另一张空白盘刻网格测试：直线能分清是几何不准还是图本身的问题。', 'If the picture is in the right place, you are done; reuse the measurement for later discs from this batch. No picture: do not burn again yet. Check three things in order: the light (the most likely cause), the burn report (written, closed, read back), then the geometry. Twisted or broken lines: check the batch and burner match the measurement; if they do, geometry may be off. Only if the light and the burn report are fine and the lines are still twisted, burn a grid on another blank: straight lines tell a wrong geometry from a wrong picture.'),
  pair('刻录失败或中断：DVD+R、DVD-R、CD-R 不能再用，换一张空白盘；再次失败时换一个刻录速度，慢不一定更好。', 'If the burn failed or stopped, a DVD+R, DVD-R or CD-R cannot be reused; take a fresh blank. If it fails again, try another burn speed; slower is not always better.'),
];
// Why `calibrate` stopped (calibrate.py Stopped reasons), in words, with what to do next. burnStarted: the
// page saw the burn report a result, so the disc may be partly written. Unknown reasons are shown as they are.
export function stopReason(reason = '', {burnStarted = false} = {}) {
  const r = String(reason);
  let m;
  if (/the drive's speed is not steady/.test(r)) return pair('光驱在内圈和外圈测到的每圈时间对不上，也不是整圈的倍数，说明这次测量时转速在变。可以再测一次；如果每次都这样，这台光驱这次没法用来测几何。', 'The time per turn near the centre and near the edge does not match, and is not a whole multiple either, so the drive was changing speed during this run. Measure again; if it happens every time, this drive cannot measure the geometry for now.');
  if (/the burn did not finish/.test(r)) return burnStarted
    ? pair('测量盘没有刻完：这张盘已经写了一部分，不能再用。换一张同批空白盘，再点“重新检测”。', 'The measurement disc did not finish burning. It is partly written and cannot be used again. Put in a fresh blank from this batch, then press Check again.')
    : pair('测量盘没有开始刻，盘没有动过。看一眼光驱和这张盘，再点“重新检测”。', 'The measurement burn did not start; the disc is untouched. Check the drive and the disc, then press Check again.');
  if (/no disc is ready/.test(r)) return pair('光驱里没有准备好的盘。放回测量盘，等灯不闪了，再点“重新检测”。', 'No disc is ready in the drive. Put the measurement disc back, wait for the light to settle, then press Check again.');
  if (/is blank, not a measurement disc/.test(r)) return pair('光驱里是空白盘，不是刻好的测量盘。放回测量盘再检测。', 'The drive holds a blank, not the measurement disc. Put the measurement disc back and check again.');
  if ((m = /the disc is a (\w+) disc, not (\w+)/.exec(r))) return pair(`光驱里是 ${m[1].toUpperCase()} 盘，这里要的是 ${m[2].toUpperCase()}。换对的盘再检测。`, `The drive holds a ${m[1].toUpperCase()} disc; this needs ${m[2].toUpperCase()}. Put the right disc in and check again.`);
  if ((m = /maker code is (.+), not (.+)/.exec(r))) return pair(`这张盘的厂商编号是 ${m[1]}，不是这批的 ${m[2]}。放回同批的测量盘。`, `This disc's maker code is ${m[1]}, not this batch's ${m[2]}. Put this batch's measurement disc back.`);
  if (/recordable capacity is unknown/.test(r)) return pair('不知道这批空白盘的总容量，没法写预设。在终端用 calibrate --sectors 给出空白盘的容量。', 'The blank disc capacity is unknown, so no preset could be written. In Terminal, give it with calibrate --sectors.');
  if ((m = /the (timing|geo) measurement was not usable/.exec(r))) return m[1] === 'timing'
    ? pair('转速检查没通过，没有接着测几何。保留这张测量盘，弹出放回后再测；还不行就换个读取速度或光驱。', 'The rotation check did not pass, so the geometry was not measured. Keep the measurement disc, eject and reload it, and measure again; if it persists, try another reading speed or drive.')
    : pair('几何测量不能用。保留这张测量盘，检查转速后再测。', 'The geometry measurement is not usable. Keep the measurement disc, check rotation and measure again.');
  if (/the preset was not written/.test(r)) return pair('测量完成，但预设没写出来。测量数据还在，可以点保存再试。', 'Measured, but the preset was not written. The measurement is kept; save again.');
  if (/cancelled/.test(r)) return pair('已取消。已经测出的数据保留着。', 'Cancelled. What was measured so far is kept.');
  return pair(r, r);
}

// ---------------------------------------------------------------- the start guide (guide.js)
// The same four things, in the same order, as guide.py tutorial_lines. Nothing here is measured: it is what
// the tool is for and how it is meant to be used, so each line says "goal" or "needs" and never "done".
export const introCards = [
  {id: 'how', title: pair('图案是怎么出来的', 'How the picture forms'),
    body: pair('盘的数据面是一条很密的螺旋轨道，像衍射光栅：光照上去，会按角度散成彩虹。disc-probe 决定每一处写什么，让图在合适的角度显出来。所以要在暗处，用一个小光源，倾斜着看；彩虹扇面是轨道本身，不是你的图。',
      'The data side is a tight spiral of tracks, like a diffraction grating: light on it spreads into a rainbow by angle. disc-probe decides what is written where, so the picture shows at the right angle. Look in the dark, under one small light, tilting the disc. The rainbow fan is the tracks themselves, not your picture.')},
  {id: 'need', title: pair('要什么盘和光驱', 'What discs and drive you need'),
    body: pair('一台既能刻又能读盘的光驱（Windows 或 Linux，DVD 试得最多；CD 在 Windows 上要用另一条刻录命令，BD 仍在试验），同一盒的几张空白 DVD-R、DVD+R 或 CD-R（刻了就不能擦），再加一部手机拍照。',
      'A drive that can both burn and read discs (Windows or Linux; DVD is the most tried, CD on Windows needs a separate burn command, BD is experimental), a few blank DVD-R, DVD+R or CD-R from one box (they cannot be erased once burned), and a phone for the photos.')},
  {id: 'discs', title: pair('要几张盘', 'How many discs'), body: discGoal, list: discRoute},
  {id: 'retake', title: pair('照片拍坏了怎么办', 'If a photo goes wrong'),
    body: pair('照片拍坏了只要重拍，同一张盘可以拍很多次，不用重刻。页面会说是哪里不行：没拍全、条纹太弱、光线不对。只有盘本身没刻好，才需要换盘。',
      'A bad photo only needs retaking. The same disc can be photographed as often as you like. The page says what was wrong: not the whole disc, a faint pattern, the light. Only a disc that was not burned properly needs replacing.')},
];
export const disShortcut = {
  title: pair('已经在用 DiscImageStudio（DIS）？', 'Already use DiscImageStudio (DIS)?'),
  body: pair('导入 DIS 预设，直接做图，跳过前面的测量盘。导入的几何是从 DIS 转换来的，不是 disc-probe 自己测的：刻出来的位置准不准，要看第一张盘。',
    'Import a DIS preset and make your picture straight away, skipping the measurement disc. The geometry is converted from DIS, not measured by disc-probe: how accurate the first disc comes out is for the first disc to show.'),
  button: pair('导入 DIS 预设', 'Import a DIS preset'),
  missing: pair('这个版本的核心没有提供预设导入。', 'This core does not offer preset import.')};
// The teaching animation: four scenes, each with its caption. The captions are also the plain list shown
// when motion is off, the page is in the background or the animation is skipped.
export const lightScenes = [
  pair('盘面是一圈圈很密的轨道，像一把梳子。', 'The disc surface is a spiral of very fine tracks, like a comb.'),
  pair('一束光照到轨道上。', 'A beam of light lands on the tracks.'),
  pair('轨道把光按波长折向不同方向，散成彩虹。', 'The tracks bend each colour of the light in a different direction, spreading a rainbow.'),
  pair('倾斜盘，让进入眼睛的那束光落在图案所在的位置，图就显出来。', 'Tilt the disc until the beam that reaches your eye comes from where the picture is, and it shows.')];

// Where the person is, from what is on disk. Programs can only check files and drive answers: a burn that
// ended, a disc in the drive and a picture seen under a lamp are the person's, so those rows say "unknown"
// instead of "done". `state` is /api/state; `intro` is whether this browser has been through the four things
// (a convenience kept locally, never a measurement).
export const statusWords = {
  done: pair('已完成', 'Done'), now: pair('现在', 'Now'), todo: pair('还没到', 'Not yet'),
  unknown: pair('还不知道', 'Not known'), problem: pair('要处理', 'Needs attention')};
export function journey(state = {}, {intro = false, media, withIntro = true} = {}) {
  media = media || state.media || 'dvd';
  const cd = media === 'cd', bd = media === 'bd';
  const steps = Object.fromEntries((state.steps || []).map(s => [s.id, s]));
  const offline = !(state.steps || []).length;
  const rows = [];
  const add = (id, status, zh, en, known, unknown, next, extra = {}) => rows.push({id, status, title: pair(zh, en), known, unknown, next, ...extra});
  if (withIntro) add('intro', intro ? 'done' : 'todo', '读完开始之前的四件事', 'Read the four things first',
    intro ? pair('你在这个浏览器里读过了。这只是个提醒，不代表盘和光驱已经准备好。', 'You have read them in this browser. That is only a reminder; it says nothing about the discs or the drive.')
      : pair('图案怎么出来、要什么盘、要几张、拍坏了怎么办。', 'How the picture forms, what you need, how many discs, what to do about a bad photo.'),
    null, {kind: 'read', label: pair('读开始之前的四件事', 'Read the four things')});
  if (offline) {
    const gone = pair('读不到电脑上的进度：本机服务没有回应。', 'Cannot read progress: the local service did not answer.');
    const gonest = pair('这一步是否完成还不知道。启动 webui 后再看。', 'Whether this step is done is not known. Start webui and look again.');
    for (const [id, zh, en] of [['ready', '软件和光驱', 'Software and drive'], ['disc1', '第 1 张：测量盘', 'Disc 1: measurement disc'], ['timing', '测转速', 'Check the speed'],
      ['geo', '测盘面几何', 'Measure the geometry'], ['check', '第 2 张：检查盘', 'Disc 2: check disc'], ['picture', '做出第一张成品的文件', 'Make the file for the first picture'], ['burn', '刻成品，看盘', 'Burn it and look']])
      add(id, 'unknown', zh, en, gone, gonest, {kind: 'refresh', label: pair('重新读取进度', 'Read the progress again')});
    return {rows, current: rows[0]?.id || null, offline,
      milestone: {reached: false, words: pair('读不到进度，不知道能不能刻第一张成品。', 'Progress cannot be read, so it is not known whether you can burn the first picture.')}};
  }
  const ready = !!(steps.packages?.done && steps.drive?.done);
  add('ready', ready ? 'done' : 'problem', '软件和光驱', 'Software and drive',
    ready ? pair('需要的 Python 包齐了，光驱可见。', 'The Python packages are there and a drive is visible.') : pair('缺软件，或看不到光驱。', 'Missing packages, or no drive visible.'),
    ready ? null : steps.packages?.done ? pair('没有找到光驱：接好、放进盘，再读一次。', 'No drive found: connect it, put a disc in, and read again.')
      : pair('缺 Python 包：' + (steps.packages?.detail || ''), 'Missing Python packages: ' + (steps.packages?.detail || '')),
    {kind: 'refresh', label: pair('重新检查光驱', 'Check the drive again')}, {data: steps.drive?.detail});
  const d1 = steps.random_disc || {}, fileMade = /burn it/.test(d1.detail || '');
  add('disc1', d1.done ? 'done' : fileMade ? 'unknown' : 'todo', '第 1 张：测量盘', 'Disc 1: measurement disc',
    d1.done ? pair('测量盘已经测过。', 'The measurement disc has been measured.') : fileMade ? pair('测量文件已经生成。', 'The measurement file is made.') : pair('还没有测量盘。', 'There is no measurement disc yet.'),
    fileMade && !d1.done ? pair('盘有没有刻好、是不是在光驱里，程序还不知道，要放进去测了才知道。', 'Whether the disc was burned and is in the drive is not known until it is measured.') : null,
    {kind: 'newwork', label: pair('去标定这批盘', 'Calibrate this batch')});
  const trouble = (step, part) => {
    const kind = recoveryKind({[part]: {verdict: step.verdict}});
    return !step.done && step.verdict && ['too_noisy', 'drive_changed', 'narrow_span', 'stopped_early', 'unknown'].includes(kind) ? measurementRecovery({[part]: {verdict: step.verdict}}) : null;
  };
  for (const [id, zhName, enName] of [['timing', '测转速', 'Check the speed'], ['geo', '测盘面几何', 'Measure the geometry']]) {
    const step = steps[id] || {}, words = trouble(step, id);
    add(id, step.done ? 'done' : words ? 'problem' : 'todo', zhName, enName,
      step.done ? (id === 'timing' ? pair('转速稳定，结果可用。', 'The speed is steady and the result is usable.') : pair('盘面几何测好了。', 'The geometry is measured.'))
        : words ? pair('做过一次，结果不能用。', 'It ran once, but the result cannot be used.') : pair('还没测。', 'Not measured yet.'),
      words, {kind: 'newwork', label: pair('去标定这批盘', 'Calibrate this batch')}, {data: step.done ? step.detail : null});
  }
  add('check', 'unknown', '第 2 张：检查盘', 'Disc 2: check disc',
    pair('这一步程序读不到进度。', 'The program cannot read progress for this step.'),
    cd ? pair('CD 还缺一个沿轨常数，要靠检查盘的照片读出来；没有它，径向线可能扭。', 'A CD still needs an along-track constant, read from photos of the check disc. Without it, radial lines may twist.')
      : pair('偏了多少，要刻检查盘、拍照才知道。DVD 也可以先做图，但图歪了就没有依据判断原因。', 'How far off it is is not known until you burn a check disc and photograph it. A DVD can go ahead and make the picture, but if it comes out off you will have nothing to tell why.'),
    {kind: 'newwork', label: pair('去标定，拍照检查', 'Calibrate and photograph')}, {optional: !cd && !bd, human: true});
  const pic = steps.picture_iso || {};
  add('picture', pic.done ? 'done' : 'todo', '做出第一张成品的文件', 'Make the file for the first picture',
    pic.done ? pair('成品的刻录文件已生成。', 'The burn file for the picture is made.') : pair('还没有成品的刻录文件。', 'There is no burn file for the picture yet.'),
    pic.done ? pair('文件做好了不等于盘刻好了。', 'A finished file is not a burned disc.') : null,
    {kind: 'newwork', label: pair('开始新作品', 'Start a new work')}, {data: pic.done ? pic.detail : null});
  add('burn', 'unknown', '刻成品，看盘', 'Burn it and look',
    pair('刻录和看盘都在电脑之外，程序只知道刻录页给出的报告。', 'Burning and looking happen outside the program; it only knows what the burn page reports.'),
    pair('图在不在盘上，只有你在暗处看了才知道。没出图先查光照、刻录报告和几何。', 'Whether the picture is on the disc is only known when you look in the dark. If it does not show, check the light, the burn report and the geometry.'),
    {kind: 'trouble', label: pair('看没出图先查什么', 'See what to check if nothing shows')}, {human: true});
  // The row to do now: the first not done and not merely optional. A row the program cannot confirm stays
  // "unknown" until it is; it is never skipped as if it were done.
  const now = rows.find(r => r.status !== 'done' && !r.optional);
  if (now) now.now = true;
  const reached = !!pic.done && ['ready', 'disc1', 'timing', 'geo'].every(id => rows.find(r => r.id === id)?.status === 'done');
  return {rows, current: now?.id || null, offline: false,
    milestone: {reached, words: reached
      ? (cd ? pair('可以刻第一张成品了，但 CD 的沿轨常数还没确认，径向线可能扭。', 'You can burn the first picture, but the CD along-track constant is not confirmed and radial lines may twist.')
        : pair('可以刻第一张成品了。刻完之后，图在不在盘上要你自己看。', 'You can burn the first picture. Whether it shows on the disc is for you to see after burning.'))
      : pair('还不能刻第一张成品：上面还有没做完的步骤。', 'Not ready to burn the first picture: steps above are not finished.')}};
}
// What to check when no picture shows, in the order that costs least. Another disc is only suggested with
// its reason stated (`reburn`); nothing here starts a burn.
export const troubleChecks = [
  {id: 'light', title: pair('先查光照', 'First, the light'),
    body: pair('关灯，小光源放在眼睛旁边，盘离眼睛约一米，倾斜避开灯和自己的倒影，慢慢转。换一个光源、换几个角度，再看一遍。多数“没出图”到这里就解决了。',
      'Lights off, a small light beside your eyes, the disc about a metre away, tilted away from the light and your reflection, turning slowly. Try another light and a few angles. Most "no picture" ends here.'),
    reburn: null},
  {id: 'burn', title: pair('再看读写结果', 'Then the burn report'),
    body: pair('刻录页给出四项：写入、关盘、回读、图案。写入或关盘没成功，或回读有很多坏块，说明数据没有写对。回读只有零星坏块时，先看图，图不对再说。',
      'The burn page reports four things: written, closed, read back, picture. If writing or closing failed, or many blocks did not read back, the data was not written properly. With only a few bad blocks, look at the disc first.'),
    reburn: pair('只有写入或关盘失败，这张盘才作废，要换空白盘并换个速度（慢不一定更好）。原因：盘上的数据不对，光照再好也看不到。', 'Only if writing or closing failed is this disc spoiled: use a fresh blank at another speed (slower is not always better). Why: the data on the disc is wrong, and no light will show it.')},
  {id: 'geo', title: pair('最后查几何', 'Last, the geometry'),
    body: pair('线条扭曲或断开：核对是不是同一批盘、同一台刻录机、同一个光驱的测量。都是的话，几何可能不准，回到测量，看覆盖范围和检查结果，并拍检查盘的照片看偏差。',
      'Twisted or broken lines: check it was the same batch, the same burner and a measurement from the same drive. If so, the geometry may be off: go back to the measurement, look at its coverage and checks, and photograph the check disc to see the error.'),
    reburn: pair('只有光照和刻录报告都没问题、线条仍然扭曲时，才刻一张网格盘。原因：直线能分清是几何不准还是图本身的问题。', 'Only when the light and the burn report are fine and lines still twist, burn a grid disc. Why: straight lines tell a wrong geometry from a wrong picture.')},
];
export const troubleNote = pair('disc-probe 不会自动让你再刻一张。要再刻，页面会先写明原因。', 'disc-probe never asks you to burn again on its own. If another disc is needed, the page says why first.');

// What each calibration phase can say besides its own progress: what is not known yet, and what to do
// next. The progress itself is the page's (a job's real percent and time); a wait that has no measure of its
// own says so rather than counting up. `ctx.good` is whether the measurement reviewed is usable.
export function stepAdvice(phase, ctx = {}) {
  const t = {
    inspect: [pair('光驱里是哪种盘，还不知道。', 'Which disc is in the drive is not known yet.'), pair('检测之后，页面会告诉你：是先刻一张测量盘，还是这张已经是测量盘，可以直接测量。', 'After the check, the page says whether to burn a measurement disc first, or whether this one already is one and can be measured.')],
    prepare: [pair('这张盘刻不刻得成功，刻完才知道。', 'Whether this disc will burn properly is only known after it has burned.'), pair('空白盘：生成测量镜像，再刻。已刻好的测量盘：勾选后直接测转速。', 'A blank: make the measurement image, then burn it. An already burned measurement disc: tick the box and measure the speed.')],
    random: [pair('这是在生成文件，没有进度可量；几十秒。', 'This is a file being made, with no measure of progress; a few tens of seconds.'), pair('等它完成，不用操作。', 'Wait for it; nothing to do.')],
    burn: [pair('刻得成不成功，刻完并回读后才知道。', 'Whether the burn succeeds is only known after it has finished and been read back.'), pair('确认盘是这批的空白盘，再按住确认条。刻的时候不要动光驱。', 'Check it is a blank from this batch, then hold the confirmation. Leave the drive alone while it burns.')],
    burning: [pair('盘有没有刻完整，要等刻完后的抽样回读；抽样不是整盘校验。', 'Whether the disc was burned completely is only known from the read-back after it ends; a sample is not a whole-disc check.'), pair('等它刻完，不要动光驱。', 'Wait for it to finish and leave the drive alone.')],
    checking: [pair('这是不是这批的盘、刻满了没有，读完才知道。', 'Whether this is the right batch and fully burned is known once the read finishes.'), pair('等几秒。', 'Wait a few seconds.')],
    timing: [pair('光驱转得稳不稳，测完才知道。', 'Whether the drive spins steadily is known once this ends.'), pair('稳了才会接着测几何。不稳就换读取速度或光驱，不用急着再刻盘。', 'Geometry follows only if it is steady. If not, try another reading speed or drive; no need to burn another disc.')],
    geo: [pair('测到的半径范围和误差，测完才知道。进度条是实际读到的位置，不是预估。', 'The radii covered and the error are known once this ends. The bar is where the head has actually read, not an estimate.'), pair('等它测完，约 5 分钟。', 'Wait for it to end; about 5 minutes.')],
    saving: [pair('预设写好了没有，写完才知道。', 'Whether the preset was written is known once it is.'), pair('等一下。', 'Wait a moment.')],
    review: ctx.good === false
      ? [pair('这次结果不能依赖。', 'This result cannot be relied on.'), pair('按下面的提示重测。这不需要再刻一张盘。', 'Measure again as the notes below say. This does not need another disc.')]
      : [pair('预设里的位置准不准，刻出图、拍照检查之后才知道；CD 的沿轨常数还要靠照片。', 'How accurate the preset is is known only after a disc is burned and photographed; a CD also needs photos for its along-track constant.'), pair('保存测量。', 'Save the measurement.')],
    saved: [pair('保存的是测量，不是成品：位置准不准，要刻出来才知道。', 'What is saved is a measurement, not a picture: how accurate it is, a burned disc will show.'), pair('做图并刻第 2 张检查盘，拍照看偏差，再刻成品。', 'Make the picture, burn disc 2 as the check disc, photograph it to see the error, then burn the finished picture.')],
  }[phase];
  return t ? {unknown: t[0], next: t[1]} : null;
}
export function adviceHTML(phase, lang, ctx = {}) {
  const a = stepAdvice(phase, ctx);
  if (!a) return '';
  const l = lang === 'en' ? 'en' : 'zh', head = l === 'zh' ? ['还不知道：', '下一步：'] : ['Not known yet: ', 'Next: '];
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  return `<div class="cal-guide"><p><b>${head[0]}</b>${esc(a.unknown[l])}</p><p><b>${head[1]}</b>${esc(a.next[l])}</p></div>`;
}
