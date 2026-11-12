// Display advice follows guide.py after_timing, after_geo, after_geo_stop and AFTER_BURN.
// These are instructions, never a substitute for a core verdict or a measurement.
const pair = (zh, en) => ({zh, en});
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
  if (['good','usable'].includes(kind) && result.geo) return {id:'save', label:pair('保存测量', 'Save measurement')};
  if (kind === 'media') return {id:'blank', label:pair('换空白盘并检测', 'Check a new blank')};
  return {id:'measure', label:pair('检查转速并重测', 'Check rotation and remeasure')};
}
// The executor is shared by the UI and drive-free tests. Geometry starts only after a usable CAV check.
export async function remeasure(run) {
  const timing = await run('timing', {});
  if (!['good','usable'].includes(timing?.verdict) || timing.measurement?.rotation !== 'CAV') return {timing};
  const geo = await run('geo', {speed:'keep'});
  return {timing, geo};
}
export function recoveryCommands(result, {drive, media, sectors}) {
  const part = result.geo || result.timing || {}, kind = recoveryKind(result);
  const base = `python -m discprobe`, flags = `--drive ${JSON.stringify(drive)} --media ${media}`;
  const commands = [`${base} timing ${flags}`, `${base} geo ${flags} --speed keep`, `${base} timing ${flags} --speed SPEED`, `${base} geo ${flags} --speed keep`];
  if (kind === 'media' || kind === 'stopped_early') commands.push(`${base} geo ${flags} --ranges START-END`);
  if (kind === 'narrow_span') {
    commands.push(`${base} disexport --media ${media} --geo ${JSON.stringify(part.path)} --sectors ${sectors} --r-min START --r-max END --output presets/fitted.json`);
  }
  if (kind === 'unknown' && result.geo?.path) commands.push(`python tools/geo_polyfit.py ${JSON.stringify(part.path)}`);
  return commands.join('\n');
}
export const cdPhoto = pair(
  '网页的 CD 拍照标定还没做好。计时测不出沿轨道的绝对位置，不能当作已完成标定。测量数据已保留：导出 DIS 预设后，在 DiscImageStudio 做精细标定，需要另一张同批空盘；然后再刻成品。这是 README 的 CD 路线。',
  'CD photo calibration is not ready on this page. Timing cannot determine the absolute along-track position, so calibration is still incomplete. The measurement is kept: export a DIS preset, then run fine calibration in DiscImageStudio on another blank from this batch before burning the picture. This is the README CD route.');
export function calibrationBudget(media) {
  const cd = media === 'cd';
  if (media === 'bd') return {
    items: [pair('BD 仍在试验中：耗盘数量未知。', 'BD is experimental: the disc budget is unknown.'), pair('分区测量约 2 分钟；刻录时间未知。', 'Zone measurement: about 2 minutes; burn time unknown.')],
    note:pair('刻好测量盘后才能检查光驱；暂无可靠的总用时预算。', 'The drive can only be checked after burning the measurement disc; no reliable total time is available.'),
    details:pair('两个半径仍需其他依据，不能套用 DVD 的预算。', 'The two radii still need other evidence. The DVD budget does not apply.')};
  return {
    items:[
      cd ? pair('至少 3 张同批空白盘：测量、精细标定、成品各一张。', 'At least 3 blanks from one batch: one to measure, one to fine-calibrate, one for the picture.') : pair('至少 2 张同批空白盘，可能 3 张：一张测量，一张刻图；图偏了就拍这张来精修，再刻第三张。', 'At least 2 blanks from one batch, maybe 3: one to measure, one for the picture; if the picture is off, photograph it to refine and burn a third.'),
      pair('生成测量文件：几十秒。', 'Make the measurement file: tens of seconds.'),
      cd ? pair('刻测量盘：约 11 分钟，依光驱而异。', 'Burn the measurement disc: about 11 minutes, depending on the drive.') : pair('刻测量盘：约 14 分钟。', 'Burn the measurement disc: about 14 minutes.'),
      pair('检查转速：1–3 分钟；测量盘面：约 5 分钟。', 'Check rotation: 1–3 minutes; measure the disc: about 5 minutes.'),
      cd ? pair('精细标定和刻成品：时间尚不确定，见详情。', 'Fine calibration and picture burn: time unknown; see Details.') : pair('刻成品：约 14 分钟，依速度和内容而异。', 'Burn the picture: about 14 minutes, depending on speed and content.')],
    note:pair('刻好测量盘后才能检查光驱；约一小时是目标，不是保证。', 'The drive can only be checked after the measurement burn; about an hour is a goal, not a promise.'),
    details:pair('以上为 README 与现有流程的估时，不是新测试。失败可能多耗盘。保留测量盘，同批盘可复用。' + (cd ? ' CD 的 11 分钟来自 GH70N、8 倍速。网页拍照标定尚未就绪，须导出 DIS 预设，在 DiscImageStudio 用另一张同批空盘精细标定，之后再刻成品。' : ''), 'These estimates come from the README and existing workflow, not new benchmarks. Failures may cost more discs. Keep the measurement disc for this batch.' + (cd ? ' The CD observation was 11 minutes at 8× on GH70N. Web photo calibration is unavailable: export a DIS preset and fine-calibrate in DiscImageStudio with another blank before burning the picture.' : ''))};
}
export function budgetHTML(media, lang) {
  const b = calibrationBudget(media);
  return `<section class="cal-budget"><ul>${b.items.map(x=>`<li>${x[lang]}</li>`).join('')}</ul><p>${b.note[lang]}</p><details><summary>${lang === 'zh' ? '详情' : 'Details'}</summary><p>${b.details[lang]}</p></details></section>`;
}
export const afterBurn = [
  pair('关掉房间的灯，把手机手电等小光源放在眼睛旁边。盘拿到约一米外，轻轻倾斜，避开灯和自己的倒影，慢慢转动；盘面暗下来时能看到图。彩虹扇面是沟槽，不是图片。看的是数据面，与预览相同。', 'Turn off the room lights and hold a small light, such as a phone torch, beside your eyes. Hold the disc about a metre away, tilt it away from reflections of the light and yourself, and turn it slowly. The picture shows when the surface goes dark. The rainbow fan is the grooves, not your picture. Look at the data side, as in the preview.'),
  pair('图案位置正确就完成了，以后同批盘可以复用这次测量。看不见图：先调整灯光，最常见的原因是光线。线条扭曲或断开：核对是否同批盘、同一台刻录机；若是，几何可能不准。用另一张空白盘刻网格测试，看看线是否笔直（在终端用 image --geo 加这次的测量路径，--output iso/grid.iso）。', 'If the picture is in the right place, you are done; reuse the measurement for later discs from this batch. No picture: adjust the light first; lighting is the most likely cause. Twisted or broken lines: check the batch and burner match the measurement. If they do, geometry may be off. Burn a grid on another blank to check for straight lines (in Terminal, use image --geo with this measurement’s path and --output iso/grid.iso).'),
  pair('刻录失败或中断：DVD+R、DVD-R、CD-R 不能再用，换一张空白盘；再次失败时换一个刻录速度，慢不一定更好。', 'If the burn failed or stopped, a DVD+R, DVD-R or CD-R cannot be reused; take a fresh blank. If it fails again, try another burn speed; slower is not always better.'),
];
// Why `calibrate` stopped (calibrate.py Stopped reasons), in words, with what to do next. burnStarted: the
// page saw the burn report a result, so the disc may be partly written. Unknown reasons are shown as they are.
export function stopReason(reason = '', {burnStarted = false} = {}) {
  const r = String(reason);
  let m;
  if (/the drive's speed is not steady/.test(r)) return pair('光驱转速不稳，多半是这张盘某一段难读，光驱在那里反复降速。页面会用固定的读速、避开那一段再测；还不行就换一个刻录速度另刻一张测量盘。', 'The drive changed speed, probably slowing down repeatedly on a hard-to-read part of this disc. The page will measure again at a fixed read speed, avoiding that band. If it still fails, burn another measurement disc at a different write speed.');
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
