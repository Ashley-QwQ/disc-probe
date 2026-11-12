// Display advice follows guide.py after_timing, after_geo, after_geo_stop and AFTER_BURN.
// These are instructions, never a substitute for a core verdict or a measurement.
const pair = (zh, en) => ({zh, en});
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
  if (m.completion_status && m.completion_status !== 'target_reached') return pair(
    `测量只完成了一部分。实测范围为 ${JSON.stringify(m.coverage?.measured_intervals_mm || m.span_mm || [])} mm；范围外属于外推，局部误差小不能证明整盘可用。`,
    `Partial measurement. Measured radii: ${JSON.stringify(m.coverage?.measured_intervals_mm || m.span_mm || [])} mm. Outside is extrapolation; small local error does not validate the whole disc.`);
  if (m.correction && ['good','usable'].includes(part.verdict)) return pair(
    '盘的轨距会变化，已自动加密测量并保存平滑角度修正，生成图片时会自动使用。详情有重复读数误差、独立检查、耗时及测点稀疏区；范围外仍是外推。DIS 预设可能无法复现这条曲线，导出前须检查转换误差。',
    'Track pitch varies. Extra points were measured and a smooth angle correction was saved; images use it automatically. Details contain repeat errors, independent checks, time and thin areas. Outside measured radii is extrapolation. A DIS preset may not reproduce the curve: check conversion error.');
