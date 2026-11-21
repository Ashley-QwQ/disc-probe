const pickLanguage = (lang, zh, en) => lang === 'en' ? en : zh;

export const gateText = (gate, lang) => gate?.[lang === 'en' ? 'en' : 'zh'] || '';
export const measurementGateText = (gate, lang) => gate?.code === 'other_batch'
  ? pickLanguage(lang, `这张盘是 ${gate.actual_mid}，测量镜像是按 ${gate.expected_mid} 这批盘准备的。换回同批空白盘，或确认后用这张盘测另一批。`,
    `This disc is ${gate.actual_mid}. The measurement image was prepared for ${gate.expected_mid}. Insert a blank from that batch, or confirm to measure the new batch.`)
  : gateText(gate, lang);
export const recheckText = lang => pickLanguage(lang, '重新检查光驱里的盘', 'Check the disc in the drive again');
export const checkingText = lang => pickLanguage(lang, '正在检查光驱里的盘…', 'Checking the disc in the drive…');
export const otherBatchConsent = lang => pickLanguage(lang, '我知道图案可能对不上，仍要用这批盘刻录。',
  'I understand the picture may be misaligned. Burn on this batch anyway.');
export const keepDiscForReview = gate => ['close_failed', 'read_back_failed'].includes(gate?.code);

export function discText(disc, lang) {
  if (!disc) return '';
  if (disc.tray === 'open') return pickLanguage(lang, '托盘开着', 'Tray open');
  if (disc.tray === 'empty') return pickLanguage(lang, '光驱里没有盘', 'No disc in the drive');
  if (!disc.present) return pickLanguage(lang, '盘状态未知', 'Disc state unknown');
  const state = disc.blank === true ? pickLanguage(lang, '空白盘', 'Blank disc')
    : disc.closed === true ? pickLanguage(lang, '已封盘', 'Finalized')
    : disc.blank === false && disc.closed === false ? pickLanguage(lang, '已有内容，尚未封盘', 'Recorded, still open')
    : disc.blank === false ? pickLanguage(lang, '已有内容', 'Recorded') : pickLanguage(lang, '状态未知', 'State unknown');
  return [disc.kind, disc.mid, disc.rewritable && pickLanguage(lang, '可擦写', 'Rewritable'), state].filter(Boolean).join(' · ');
}

export async function checkBurn(backend, request) {
  for (const delay of [200, 450, 900]) {
    try { return await backend.request('/api/burn-check', request); }
    catch (error) {
      if (error.code !== 'drive_busy') throw error;
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
  return backend.request('/api/burn-check', request);
}

export async function confirmBurn(backend, request, confirmed, lang) {
  const {gate} = await checkBurn(backend, request);
  if (gate && (gate.code !== 'other_batch' ||
      gate.actual_mid !== confirmed?.actual_mid || gate.expected_mid !== confirmed?.expected_mid))
    throw Object.assign(new Error(gateText(gate, lang)), {burnGate: gate});
  if (confirmed && !gate) throw Object.assign(new Error(), {code:'disc_changed'});
  const payload = gate ? {...request, args:{...request.args, confirmed_mid:gate.actual_mid}} : request;
  const {token} = await backend.request('/api/burn-token', payload);
  return {...payload, burn_token:token};
}

export function failureText(error, lang, {started = false, readBack = false} = {}) {
  const gate = gateText(error?.burnGate, lang);
  if (gate) return gate;
  if (error?.code === 'disc_changed')
    return pickLanguage(lang, '光驱里的盘变了。重新检查光盘，再确认刻录。', 'The disc in the drive changed. Check it and confirm again.');
  if (error?.code === 'drive_busy')
    return pickLanguage(lang, '光驱正忙或光盘状态已改变。等当前操作结束，再检查光盘。',
      'The drive is busy or the disc state changed. Wait for the current operation, then check again.');
  if (error?.status === 404)
    return pickLanguage(lang, '找不到光驱、镜像或刻录检查服务。检查光驱连接，确认镜像仍在，并使用最新版核心。',
      'The drive, image, or burn check is unavailable. Check the drive connection, verify the image is still present, and use the current core.');
  if (error instanceof TypeError)
    return pickLanguage(lang, '连接不到本机服务。恢复连接后重新检查光盘。', 'Cannot reach the local service. Reconnect, then check the disc again.');
  const reason = error?.message?.trim();
  const next = readBack
    ? pickLanguage(lang, '先重新读取这张盘，再决定是否重刻。', 'Re-read this disc before deciding whether to burn another.')
    : started
      ? pickLanguage(lang, '检查光驱连接和这张盘的状态，再决定是否换盘重刻。', 'Check the drive connection and the state of this disc before deciding whether to burn another.')
      : pickLanguage(lang, '检查光驱连接和光盘，再重新确认。', 'Check the drive connection and the disc, then confirm again.');
  return [reason || pickLanguage(lang, '这次刻录没有完成。', 'This burn did not finish.'), next].join(' ');
}
