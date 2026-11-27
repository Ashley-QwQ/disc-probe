/** Standalone photo calibration UI. No uploads or drive operations.
 * Photos may be Files, URLs, or {src, name, label, file, ringsMm, rim} objects.
 * Optional rim: {cx, cy, radiusPx}, in original image pixels, supplied by the
 * host's rim detector (60 mm disc radius). Without it the guides are explicitly
 * an unregistered preview; this module does not implement the photo reader.
 * phoneQrSvg may be a host-generated SVG string; it is displayed as an inert
 * image, never inserted as markup. All callbacks receive independent arrays.
 */
import { deviceList } from './kit/devices.js';
import { cdShootingTips, photoReasonWords, photoStage, shootingTips, sliderWords } from './photowords.mjs';
const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
export const DEFAULT_RINGS = Object.freeze([30, 38, 47, 55]);
export function ringHandles(radius) {
  return [45, 135, 225, 315].map(degrees => ({
    x: radius * Math.cos(degrees * Math.PI / 180),
    y: radius * Math.sin(degrees * Math.PI / 180), degrees,
  }));
}
export function mmToPx(point, view) {
  const scale = view.pxPerMm * view.zoom;
  return {x: view.cx + view.panX + point.x * scale, y: view.cy + view.panY + point.y * scale};
}
export function pxToMm(point, view) {
  const scale = view.pxPerMm * view.zoom;
  return {x: (point.x - view.cx - view.panX) / scale, y: (point.y - view.cy - view.panY) / scale};
}
export function zoomAt(view, point, factor) {
  const world = pxToMm(point, view);
  const zoom = clamp(view.zoom * factor, 0.25, 12);
  return {...view, zoom, panX: point.x - view.cx - world.x * view.pxPerMm * zoom,
    panY: point.y - view.cy - world.y * view.pxPerMm * zoom};
}
export function resizeRing(rings, index, radius) {
  if (!Number.isInteger(index) || index < 0 || index >= rings.length || !Number.isFinite(radius)) return [...rings];
  return rings.map((r, i) => i === index ? clamp(radius, 24, 58) : r);
}
/** Prefer above-right, then above-left/below; shrink on tiny viewports.
 * Returns null if there is no room outside the pointer's 18px hand clearance.
 */
export function magnifierPlacement(pointer, bounds, diameter = 164) {
  const gap = 24, margin = 8, size = Math.min(diameter, bounds.width - 16, bounds.height - 16);
  if (size < 32) return null;
  const candidates = [
    {x: pointer.x + gap, y: pointer.y - gap - size},
    {x: pointer.x - gap - size, y: pointer.y - gap - size},
    {x: pointer.x + gap, y: pointer.y + gap},
    {x: pointer.x - gap - size, y: pointer.y + gap},
  ];
  for (const candidate of candidates) {
    const x = clamp(candidate.x, margin, bounds.width - size - margin);
    const y = clamp(candidate.y, margin, bounds.height - size - margin);
    const dx = Math.max(x - pointer.x, 0, pointer.x - x - size);
    const dy = Math.max(y - pointer.y, 0, pointer.y - y - size);
    if (Math.hypot(dx, dy) >= 18) return {x, y, size};
  }
  return null;
}
export function photoKey(state, key) {
  if (key === 'Escape') {
    if (state.focus) return {...state, focus: false};
    if (state.dragging) return {...state, dragging: false};
    return {...state, action: 'back'};
  }
  if (key.toLowerCase() === 'f') return {...state, focus: !state.focus};
  return {...state};
}
function validRings(value, fallback = DEFAULT_RINGS) {
  return Array.isArray(value) && value.length && value.every(r => Number.isFinite(r) && r >= 24 && r <= 58)
    ? [...value] : [...fallback];
}
const words = {
  zh: {
    back: '上一步', prepare: '准备测量盘', speed: '测转速', geometry: '测几何', photo: '拍照', needed: '这次需要',
    title: '拍一张照，补上外圈', why: (a,b) => `光驱计时测到了 ${a}–${b} mm，这一段可以直接用。${b < 58 ? `最外面 ${+(58-b).toFixed(1)} mm 读到的点太少，范围偏窄。` : '可以用照片再检查条纹。'}`,
    measured: '实心：已测到', narrow: '斜线：范围偏窄', after: '拍了以后',
    afterBody: '照片留在这里，拖动方形把手，让同心圆对上照片里的条纹。',
    reader: '照片读取尚未接入；这里先保留照片和你调整的圆环。',
    skipTitle: '不拍也可以', skipBody: '继续用计时测量的结果。外圈的误差尚未估计，图案靠近边缘时请留意。',
    skip: '跳过，就用现在的结果', phone: '用手机扫，直接拍', phoneSmall: '手机扫码，直接拍',
    phoneOffline: '手机上传尚未接入，请从这台电脑添加照片。', openPhone: '打开手机拍照链接',
    phoneSteps: ['手机和电脑连同一个 Wi-Fi', '扫码，在手机上按“拍照”', '拍好后回到这里继续'],
    computerAddress: '电脑地址', phoneHelp: '手机打不开链接？',
    sharedWifi: '手机和电脑连同一个 Wi-Fi，不要用访客网络。',
    allowPrivateNetwork: 'Windows 可能拦住了连接：在 Windows 安全中心 → 防火墙和网络保护里看当前网络是“专用”还是“公用”。是“公用”时，在“允许应用通过防火墙”里给 Python 勾上“公用”（列表里没有就点“允许其他应用”添加 python.exe），或者把这个网络改成“专用”。',
    otherAddress: '试试上面的另一个地址。',
    local: '照片只在这台电脑的浏览器里打开，不会上传。', shoot: '这样拍',
    phoneAbove: '手机拍整张盘', lamp: '吸顶灯在身后', avoidLight: '盘上别有灯的白斑', disc: '盘朝你转 20–30°',
    drop: '没有手机，或者照片已经在电脑里：把文件拖到这里。', add: '从电脑添加照片', addMore: '再加一张照片',
    photos: '照片', count: n => `${n} 张`, current: '正在对', alignment: '对齐', manual: '手动调整', manualSummary: '手动调整',
    rings: '圆环', ringCount: n => `${n} 条参考圆`, offset: '平均偏差', unknown: '尚未测量',
    unregistered: '参考圆预览 · 盘缘识别尚未接入', registered: '盘缘位置由程序提供',
    auto: '自动对齐', busy: '正在对齐…', reset: '重来', use: '下一步：用这张照片', first: '先加一张照片',
    next: '下一步：对齐', select: '拖把手', pan: '拖动画面', out: '缩小', in: '放大', fit: '整张盘', curves: '曲线',
    enhance: '增强条纹', focus: '专注', focusMode: '专注模式', space: '空格', wheel: '滚轮', zoom: '缩放', exit: '退出',
    offsetShort: '偏', adjust: '调整半径', ring: '圆环半径', resetView: '点击小地图回到整张盘',
    badFile: '照片打不开。请换一张 JPEG、PNG 或 WebP 图片，再添加一次。',
    autoError: '自动对齐没有完成。可以重试，或继续拖动圆环。', autoInvalid: '自动对齐未返回有效的圆环和偏差，请重试。',
    noUse: '等待主页面接入“使用照片”', callbackError: '操作未完成，请重试。',
    loading: '正在打开照片…', radiusTip: '拖动把手，或用方向键每次调整 0.1 mm；Shift 每次调整 1 mm。',
  },
  en: {
    back: 'Back', prepare: 'Prepare test disc', speed: 'Measure speed', geometry: 'Measure geometry', photo: 'Photo', needed: 'Needed this time',
    title: 'A photo to fill in the outer edge', why: (a,b) => `Drive timing measured ${a}–${b} mm. That range is ready to use. ${b < 58 ? `The outer ${+(58-b).toFixed(1)} mm has too few readings.` : 'A photo can help check the bands.'}`,
    measured: 'Solid: measured', narrow: 'Hatched: narrow coverage', after: 'After taking the photo',
    afterBody: 'Keep the photo here. Drag the square handles to match the concentric rings to its bands.',
    reader: 'The photo reader is not connected yet; this page keeps your photo and adjusted rings.',
    skipTitle: 'You can skip the photo', skipBody: 'Use the timing results as they are. Outer-edge error has not been estimated; take care with artwork near the edge.',
    skip: 'Skip, use the current results', phone: 'Scan with your phone to take a photo', phoneSmall: 'Scan to take a photo',
    phoneOffline: 'Phone upload is not connected yet. Add a photo from this computer.', openPhone: 'Open the phone camera link',
    phoneSteps: ['Connect phone and computer to the same Wi-Fi', 'Scan, then tap “Take photo” on your phone', 'Return here after taking the photo'],
    computerAddress: 'Computer address', phoneHelp: "Phone can't open the link?",
    sharedWifi: 'Use the same Wi-Fi as this computer, not a guest network.',
    allowPrivateNetwork: 'Windows may have blocked the connection: in Windows Security → Firewall & network protection, check whether this network is Private or Public. If it is Public, tick Public for Python under “Allow an app through firewall” (if Python is not listed, use “Allow another app” to add python.exe), or switch the network to Private.',
    otherAddress: 'Try the other address above.',
    local: 'Photos open only in this computer’s browser. Nothing is uploaded.', shoot: 'How to shoot',
    phoneAbove: 'Phone on the whole disc', lamp: 'Ceiling lamp behind you', avoidLight: 'No white lamp glare on the disc', disc: 'Disc tilted 20–30° to you',
    drop: 'No phone, or the photo is already on your computer? Drop the file here.', add: 'Add a photo from this computer', addMore: 'Add another photo',
    photos: 'Photos', count: n => `${n} photo${n === 1 ? '' : 's'}`, current: 'Aligning', alignment: 'Alignment', manual: 'Manual adjustment', manualSummary: 'Adjust by hand',
    rings: 'Rings', ringCount: n => `${n} reference rings`, offset: 'Mean offset', unknown: 'Not measured',
    unregistered: 'Guide preview · rim detection not connected', registered: 'Disc rim supplied by the program',
    auto: 'Auto-align', busy: 'Aligning…', reset: 'Start over', use: 'Next: use this photo', first: 'Add a photo first',
    next: 'Next: align', select: 'Drag handles', pan: 'Pan image', out: 'Zoom out', in: 'Zoom in', fit: 'Whole disc', curves: 'Guides',
    enhance: 'Enhance bands', focus: 'Focus', focusMode: 'Focus mode', space: 'Space', wheel: 'Wheel', zoom: 'Zoom', exit: 'Exit',
    offsetShort: 'offset', adjust: 'Adjust radius', ring: 'Ring radius', resetView: 'Click the minimap to fit the whole disc',
    badFile: 'This photo could not be opened. Try adding a JPEG, PNG or WebP image.',
    autoError: 'Auto-align did not finish. Try again, or keep adjusting the rings.', autoInvalid: 'Auto-align did not return valid rings and an offset. Please retry.',
    noUse: 'Waiting for the host to connect “Use photo”', callbackError: 'The action did not finish. Please try again.',
    loading: 'Opening photo…', radiusTip: 'Drag a handle, or use arrow keys for 0.1 mm steps; hold Shift for 1 mm.',
  },
};
const paths = {
  back: 'm14 5-7 7 7 7', next: 'M19 6v7H6m4-4-4 4 4 4', plus: 'M12 5v14M5 12h14', minus: 'M5 12h14',
  select: 'm6 4 12 7-5 1.5L11 18z', pan: 'M8 12V6a1.5 1.5 0 0 1 3 0v5m0 0V4.5a1.5 1.5 0 0 1 3 0V11m0 0V6a1.5 1.5 0 0 1 3 0v8m0-4a1.5 1.5 0 0 1 3 0v5a6 6 0 0 1-6 6h-2a6 6 0 0 1-5-3l-3-5a1.5 1.5 0 0 1 2.5-1.6L8 13',
  fit: 'M4 4h16v16H4zM9 9h6v6H9z', eye: 'M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12zM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  contrast: 'M12 3v18m0-18a9 9 0 1 0 0 18m0-18a9 9 0 0 1 0 18M12 7h6.7M12 12h9M12 17h6.7',
  focus: 'M9 4H4v5m11-5h5v5M4 15v5h5m6 0h5v-5', upload: 'M12 16V5m-5 5 5-5 5 5M4 19h16',
  reset: 'm8 5-4 4 4 4M4 9h10a5 5 0 0 1 0 10h-3', auto: 'M5 19 16 8m-2-2 4 4m0-7v3m-1.5-1.5h3M6 5v2M5 6h2',
};
const icon = name => `<svg aria-hidden="true" viewBox="0 0 24 24" class="pc-icon"><path d="${paths[name]}"/></svg>`;

export function photoPage(host, opts = {}) {
  if (!host || typeof host.append !== 'function') throw new TypeError('photoPage requires a host element');
  const doc = host.ownerDocument, win = doc.defaultView, en = opts.lang === 'en';
  const lang = en ? 'en' : 'zh', cd = opts.media === 'cd';
  const t = {...words[lang]};
  const tips = cd ? cdShootingTips : shootingTips;
  const slider = key => sliderWords[key][lang];
  // the hand-guided reading (pcal_assist): the person checks or fixes the registration and picks the arrow;
  // the program scans and reads. A person can never pass a photo, only steer the reading.
  const G = en ? {
    title: 'If the automatic read fails: calibrate by hand', why: 'Two checks only you can make; the program does the searching and the reading. A photo that cannot be read this way needs retaking.',
    start: 'Start with the selected photo',
    s1: '1 · Rings', s1how: 'Do the thin green circles lie on the fine rings burned on the disc, all the way round?',
    ringsOk: 'They match', ringsClick: 'No, I will mark them', ringsNone: 'The program did not find the disc in this photo: mark it.',
    clickHow: 'Zoom in and click the outermost burned ring about 8 times, spread all round; Shift-click the centre.',
    register: 'Fit the rings', clear: 'Clear clicks', reset: 'Use the program\u2019s fit',
    locked: '\u2713 The rings lock onto the disc.', notLocked: 'The rings do not lock: the scale may be off, and L with it. Click the outermost ring again, more carefully.',
    s2: '2 · Where is the arrow', s2how: 'The program finds the likeliest positions and draws each as an arrow outline A\u2013D. Pick the one on the real 12 o\u2019clock arrow.',
    find: 'Let the program look', onArrow: k => `${k} sits on the arrow`, noArrow: 'Cannot see the arrow: use the strongest',
    s3: '3 · Reading', save: 'Use this reading',
    ok: (L, f) => `Read: L = ${L} mm${f ? ` (${f} frames)` : ''}. Another photo from a different angle must agree before it counts.`,
    okUnlocked: 'Read, but the rings did not lock, so it cannot be used. Fit the rings again.',
    retake: s => ({too_few_votes: 'Too few places show the pattern. This photo does not have enough signal; retake it.', poor_angle_coverage: 'The pattern shows on one side only. Turn the disc and take another.'}[s] || 'The parts of the photo disagree. Retake it.'),
    busy: 'Working\u2026', clicks: n => `${n} on the ring`, hubSet: ' · centre set', saved: 'Saved.', legacy: 'Sliders (for debugging)'
  } : {
    title: '自动读不出时：手动校准', why: '你只做两件人眼擅长的检查，搜索和读数都由程序做。这样也读不出的照片，就需要重拍。',
    start: '用选中的这张开始',
    s1: '1 · 套圈', s1how: '看照片上的绿色细圈，是不是整圈都压在盘上刻出来的细环上。',
    ringsOk: '对上了', ringsClick: '没对上，我来点', ringsNone: '程序没在这张照片里找到盘，请你来标。',
    clickHow: '放大照片，沿最外圈刻出来的细环点 8 下左右，绕一整圈分散开；按住 Shift 点一下盘心。',
    register: '重新套圈', clear: '清空点', reset: '用程序的定位',
    locked: '\u2713 细环锁住了。', notLocked: '细环没锁住：比例可能不准，读出的 L 也会跟着偏。再仔细点一遍最外圈细环。',
    s2: '2 · 找箭头', s2how: '程序找出最可能的几个位置，各画成一个箭头轮廓 A\u2013D。选压在盘上真实 12 点箭头上的那个。',
    find: '让程序找', onArrow: k => `${k} 压在箭头上`, noArrow: '看不到箭头，用最强的',
    s3: '3 · 读取', save: '用这个结果',
    ok: (L, f) => `读出来了：L = ${L} mm${f ? `（${f} 帧）` : ''}。还要另一张不同角度的照片读出一致的数，才算数。`,
    okUnlocked: '读出来了，但细环没锁住，不能用。请重新套圈。',
    retake: s => ({too_few_votes: '能读出条纹的地方太少。这张照片信号不够，人工也补不出来，请重拍。', poor_angle_coverage: '读出条纹的地方只在盘的一边。转一下盘，再拍一张。'}[s] || '照片各处读出的位置对不上，请重拍。'),
    busy: '正在算\u2026', clicks: n => `已点 ${n} 下`, hubSet: ' · 已点盘心', saved: '已保存。', legacy: '滑块（调试用）'
  };
  const sliderEnabled = typeof opts.manualAlignment === 'function' && typeof opts.onManualSaved === 'function';
  if (opts.paperHost) {
    t.phoneOffline = en ? 'This computer is not reachable from your phone. Add a photo from this computer.' : '手机暂时连不到这台电脑，请从电脑添加照片。';
    t.local = en ? 'Photos are sent to this computer on your local network.' : '照片通过局域网发到这台电脑。';
    if (typeof opts.autoAlign === 'function') t.reader = en ? 'Auto-align reads the photo. If it is unclear, the reason is shown below.' : '自动对齐会读取照片；读不准时，会在下面说明原因。';
    if (cd) {
      t.title = en ? 'Read the along-track constant from a photo' : '拍照，读出沿轨常数';
      t.why = () => en ? 'This drive and disc batch need a photo to read the along-track constant. Keep the whole target disc in frame.' : '这台光驱和这批盘还需要靠照片读出沿轨常数。把整张标靶盘拍进画面。';
    } else if (opts.purpose === 'check') {
      // DVD: the drive's timing already gives a usable geometry; the photo checks it, and corrects it when it is off.
      t.title = en ? 'Check the measurement with photos' : '拍照检查测量结果';
      t.why = () => en ? 'The drive’s timing is not always exact. Photos of the check disc read the along-track constant; if it disagrees with the measurement, the photo’s value corrects it. Keep the whole check disc in frame.'
        : '光驱计时测出的位置不一定完全准。给检查盘拍几张照，照片会读出沿轨常数；和测量对不上时，就用照片的值修正。把整张检查盘拍进画面。';
    }
  }
  if (opts.automaticRead) {
    t.afterBody = en ? 'Photos are read together automatically. Turn the disc between shots.' : '照片会一起自动读取。每张之间转动一下盘。';
    t.reader = en ? 'Keep the whole disc in frame. If a photo needs retaking, its reason appears below.' : '把整张盘拍进画面。需要重拍时，原因会显示在下面。';
  }
  const abort = new win.AbortController(), ownedUrls = new Set();
  const initialRings = validRings(opts.ringsMm);
  const measured = Array.isArray(opts.measuredMm) && opts.measuredMm.length === 2 && opts.measuredMm.every(Number.isFinite)
    && opts.measuredMm[0] >= 24 && opts.measuredMm[1] <= 58 && opts.measuredMm[0] < opts.measuredMm[1] ? [...opts.measuredMm] : [24, 52];
  let destroyed = false, active = -1, photos = [], dragging = null, space = false, task = 0;
  let view = {cx: 0, cy: 0, pxPerMm: 1, zoom: 1, panX: 0, panY: 0};
  let focus = false, curves = true, enhance = false, tool = 'select', busy = false;
  let manual = null, scoreTimer, recognized = null, recognizeKey = 0;
  let guided = null;   // {photo, token, lines, clicking, clicks, hub, cands, chosen, result, xf}
  // Privacy veil for screenshots: blurs everything on screen except the disc the reader registered. Display only;
  // the photo itself is untouched. Remembered in this browser.
  let privacy = false;
  try { privacy = win.localStorage.getItem('discprobe-photo-privacy') === '1'; } catch { /* storage unavailable */ }
  const root = doc.createElement('section');
  root.className = 'pc-page'; root.lang = opts.lang === 'en' ? 'en' : 'zh-CN';
  root.setAttribute('aria-label', t.title);
  const button = (action, label, glyph, cls = '') => `<button type="button" data-pc="${action}" class="pc-button ${cls}" title="${label}">${glyph ? icon(glyph) : ''}<span>${label}</span></button>`;
  root.innerHTML = `
    <header class="pc-header">${button('back', t.back, 'back', 'pc-back')}<b class="pc-wordmark">disc-probe</b>
      <ol class="pc-steps" aria-label="${t.geometry}"><li>${t.prepare}</li><li>${t.speed}</li><li>${t.geometry}</li><li aria-current="step">${t.photo}<small>${t.needed}</small></li></ol>
    </header>
    <div class="pc-content">
      <div class="pc-viewport" tabindex="0" aria-label="${t.drop}">
        <div class="pc-empty">
          <div class="pc-empty-columns"><section class="pc-phone-empty"></section><section class="pc-shoot"><h2>${t.shoot}</h2>
            <ul>${tips.map(tip => `<li>${tip[lang]}</li>`).join('')}</ul>
            ${cd ? '' : `<svg viewBox="0 0 380 235" class="pc-shoot-diagram" role="img" aria-label="${t.phoneAbove}; ${t.lamp}; ${t.disc}">
              <g class="pc-detail"><path d="M66 46l18 18M66 46v24M66 46 48 64" stroke-dasharray="3 4"/><path d="M174 100 300 150M174 108l122 66" stroke-dasharray="2 5"/><path d="M258 196h96M332 196a26 26 0 0 0-4-17"/></g>
              <g class="pc-structure"><path d="M20 26h345M20 214h345M66 26v12M52 38h28l-5 9H57z"/><rect x="156" y="84" width="16" height="32" rx="3"/><path d="M258 196 345 165" stroke-width="3"/></g>
              <text x="20" y="96">${t.lamp}</text><text x="128" y="138">${t.phoneAbove}</text><text x="196" y="60">${t.avoidLight}</text><text x="214" y="232">${t.disc}</text>
            </svg>`}</section></div>
          <div class="pc-drop"><p>${t.drop}</p>${button('add', t.add, 'upload')}</div>
        </div>
        <img class="pc-image" alt="${t.photo}" draggable="false" hidden>
        <img class="pc-image-sharp" alt="" aria-hidden="true" draggable="false" hidden>
        <svg class="pc-overlay" aria-label="${t.radiusTip}"></svg>
        <div class="pc-photo-name pc-float" hidden></div>
        ${button('focus', `${t.focus}  F`, 'focus', 'pc-focus-button pc-float')}
        <div class="pc-toolbar pc-float" role="toolbar" aria-label="${t.alignment}">
          ${button('select', t.select, 'select', 'pc-icon-only')}${button('pan', t.pan, 'pan', 'pc-icon-only')}
          <i></i>${button('out', t.out, 'minus', 'pc-icon-only')}<output class="pc-zoom"></output>${button('in', t.in, 'plus', 'pc-icon-only')}
          ${button('fit', t.fit, 'fit')}<i></i>${button('curves', t.curves, 'eye')}${button('enhance', t.enhance, 'contrast')}
        </div>
        <div class="pc-shortcuts pc-float"><b>${t.focusMode}</b><span><kbd>${t.space}</kbd> ${t.pan}</span><span><kbd>${t.wheel}</kbd> ${t.zoom}</span>${button('exit', `${t.exit} Esc`)}</div>
        <button type="button" data-pc="fit" class="pc-minimap pc-float" title="${t.resetView}" aria-label="${t.resetView}"><span class="pc-mini-image"><img alt=""><svg aria-hidden="true" preserveAspectRatio="none"><rect/></svg></span><output></output></button>
        <div class="pc-focus-readout pc-float"></div>
        <div class="pc-loupe" hidden><canvas width="328" height="328"></canvas><span></span></div>
      </div>
      <aside class="pc-paper">
        <h1>${t.title}</h1><p class="pc-why"></p><svg class="pc-range" viewBox="0 0 344 54" role="img" aria-label="${t.measured}; ${t.narrow}"></svg>
        <p class="pc-range-key">${t.measured}　 ${t.narrow}</p>
        <div class="pc-before"><section><h2>${t.after}</h2><p>${t.afterBody}</p><p>${t.reader}</p></section><section><h2>${t.skipTitle}</h2><p>${t.skipBody}</p></section></div>
        <div class="pc-after">
        <section><div class="pc-section-title"><h2>${t.photos}</h2><span class="pc-photo-count"></span></div><div class="pc-strip"></div></section>
          <section class="pc-add-section"><div class="pc-phone-small"></div></section>
          <details class="pc-more"><summary>${en ? 'More' : '更多'}</summary>
          ${button('add', t.add, 'upload', 'pc-wide')}
${sliderEnabled ? `<details class="pc-advanced"><summary>${G.title}</summary><p class="pc-advanced-why">${G.why}</p>
          <section class="pc-guided" aria-live="polite">
            <div class="pc-guided-row">${button('g-open', G.start, null, 'pc-small')}</div>
            <div class="pc-guided-step" data-step="1" hidden><h3>${G.s1}</h3><p>${G.s1how}</p>
              <p class="pc-guided-ring"></p>
              <div class="pc-guided-row">${button('g-ok', G.ringsOk, null, 'pc-small')}${button('g-click', G.ringsClick, null, 'pc-small')}</div>
              <div class="pc-guided-clicking" hidden><p>${G.clickHow} <b class="pc-guided-count"></b></p>
                <div class="pc-guided-row">${button('g-register', G.register, null, 'pc-small')}${button('g-clear', G.clear, null, 'pc-small')}${button('g-reset', G.reset, null, 'pc-small')}</div></div>
            </div>
            <div class="pc-guided-step" data-step="2" hidden><h3>${G.s2}</h3><p>${G.s2how}</p>
              <div class="pc-guided-row">${button('g-find', G.find, null, 'pc-small')}</div><div class="pc-guided-cands"></div></div>
            <div class="pc-guided-step" data-step="3" hidden><h3>${G.s3}</h3><p class="pc-guided-result"></p>
              <div class="pc-guided-row">${button('g-save', G.save, null, 'pc-small')}</div></div>
            <p class="pc-guided-msg" role="status"></p>
          </section>
          <details class="pc-slider-legacy"><summary>${G.legacy}</summary><section class="pc-slider-panel" data-capability="photo-manual-alignment">
          ${button('align', slider('open'), null, 'pc-wide')}
          <div class="pc-slider-controls" hidden>
            <p>${slider('hint')}</p>
            <label><span>${slider('offset')} <output></output></span><input type="range" data-align-value="L_mm"></label>
            <label><span>${slider('angle')} <output></output></span><input type="range" data-align-value="c_deg" min="0" max="360" step="0.05"></label>
            <p class="pc-slider-score" role="status"></p>
          </div>
          <p class="pc-slider-message" role="status"></p>
        </section></details></details>` : ''}
          <section>${opts.automaticRead ? `<details class="pc-manual"><summary>${t.manualSummary}</summary>` : ''}<div class="pc-section-title"><h2>${t.alignment}</h2><span class="pc-stamp">${t.manual}</span></div>
            <dl class="pc-summary"><div><dt>${t.rings}</dt><dd class="pc-ring-count"></dd></div><div><dt>${t.offset}</dt><dd class="pc-offset"></dd></div></dl>
            <p class="pc-registration"></p><p>${t.reader}</p>
            <div class="pc-actions">${typeof opts.autoAlign === 'function' ? button('auto', t.auto, 'auto', 'pc-primary') : ''}${button('reset', t.reset, 'reset')}</div>
            <details class="pc-radius-editor"><summary>${t.adjust}</summary><p>${t.radiusTip}</p><div></div></details>
            ${opts.automaticRead ? '</details>' : ''}
          </section>
          </details>
        </div>
        ${typeof opts.onSkip === 'function' ? `<button type="button" data-pc="skip" class="pc-button pc-skip pc-wide">${t.skip}</button>` : ''}
      </aside>
    </div>
    <footer class="pc-footer"><p class="pc-local">${t.local}</p><span class="pc-next-why"></span>${button('use', t.next, 'next', 'pc-primary pc-next')}</footer>
    <p class="pc-message" role="status" aria-live="polite"></p>
    <input class="pc-file" type="file" accept="image/*" multiple hidden>`;
  host.append(root);
  // The calibration flow already owns a paper card and fixed-corner navigation.
  const paper = root.querySelector('.pc-paper');
  if (opts.paperHost) { opts.paperHost.replaceChildren(paper); opts.paperHost.classList.add('pc-embedded-paper'); root.classList.add('pc-embedded'); }
  const $ = selector => root.querySelector(selector) || paper.querySelector(selector);
  const on = (node, event, fn, extra = {}) => {
    node.addEventListener(event, fn, {...extra, signal: abort.signal});
    if (node === root && opts.paperHost) paper.addEventListener(event, fn, {...extra, signal: abort.signal});
  };
  const stage = $('.pc-viewport'), image = $('.pc-image'), overlay = $('.pc-overlay'), loupe = $('.pc-loupe');
  if (opts.automaticRead) {
    root.classList.add('pc-automatic');
    on($('.pc-manual'), 'toggle', event => root.classList.toggle('pc-manual-open', event.target.open));
    // Folding "More" puts its tools away too: the ring guides and toolbar only show while "Adjust by hand" is open
    // and in view, and an open manual alignment is closed.
    if ($('.pc-advanced')) on($('.pc-advanced'), 'toggle', event => { if (!event.target.open) guidedClose(); });
    on($('.pc-more'), 'toggle', event => {
      if (event.target.open) return;
      guidedClose();
      const adjust = $('.pc-manual'); if (adjust?.open) adjust.open = false;
      root.classList.remove('pc-manual-open');
      if (manual) { closeAlignment(); syncButtons(); paint(); }
    });
  }
  const message = text => { if (!destroyed) $('.pc-message').textContent = text; };
  const selected = () => photos[active];
  const objectUrl = blob => { const url = win.URL.createObjectURL(blob); ownedUrls.add(url); return url; };
  const safeUrl = value => {
    try { const url = new URL(value, doc.baseURI); return ['http:', 'https:', 'blob:', 'data:', 'file:'].includes(url.protocol) ? url.href : ''; }
    catch { return ''; }
  };
  const safePhoneUrl = value => {
    if (!value) return '';
    try { const url = new URL(value, doc.baseURI); return ['http:', 'https:'].includes(url.protocol) ? url.href : ''; } catch { return ''; }
  };
  let phoneUrl = safePhoneUrl(opts.phoneUrl);
  let phoneShown = Date.now(), phoneOpened = false, helpTimer;
  const deviceHosts = [];
  function updatePhoneHelp() {
    for (const host of [$('.pc-phone-empty'), $('.pc-phone-small')]) {
      const help = host.querySelector('.pc-phone-help');
      if (help) help.hidden = phoneOpened || Date.now() - phoneShown < 25000;
    }
  }
  function startPhoneHelp() {
    win.clearTimeout(helpTimer);
    helpTimer = win.setTimeout(() => { if (!destroyed) updatePhoneHelp(); }, 25000);
  }
  function phoneBlock(node, small) {
    if (!phoneUrl) {
      const p = doc.createElement('p'); p.className = 'pc-phone-offline'; p.textContent = t.phoneOffline;
      const link = doc.createElement('button'); link.type = 'button'; link.className = 'pc-text-button'; link.dataset.pc = 'add'; link.textContent = t.add;
      node.append(p, link); return;
    }
    const block = doc.createElement('div'); block.className = 'pc-phone-block';
    if (typeof opts.phoneQrSvg === 'string' && /<svg[\s>]/i.test(opts.phoneQrSvg)) {
      const qr = doc.createElement('img'); qr.className = 'pc-qr'; qr.alt = t.openPhone;
      qr.src = objectUrl(new win.Blob([opts.phoneQrSvg], {type: 'image/svg+xml'})); block.append(qr);
    }
    const text = doc.createElement('div'), heading = doc.createElement('h2'), link = doc.createElement('a');
    heading.textContent = small ? t.phoneSmall : t.phone; link.textContent = phoneUrl; link.href = phoneUrl; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.title = t.openPhone;
    text.append(heading, link);
    const addresses = opts.addresses || [];
    if (addresses.length > 1) {
      const label = doc.createElement('label'); label.className = 'pc-address'; label.textContent = t.computerAddress;
      const select = doc.createElement('select'); select.setAttribute('aria-label', label.textContent);
      for (const address of addresses) { const option = doc.createElement('option'); option.value = option.textContent = address; select.append(option); }
      select.value = opts.address || new URL(phoneUrl).hostname;
      on(select, 'change', async () => {
        select.disabled = true;
        try { await opts.onAddress?.(select.value); } catch (error) { message(error.message); }
        finally { select.disabled = false; }
      });
      label.append(select); text.append(label);
    }
    const help = doc.createElement('details'); help.className = 'pc-phone-help'; help.hidden = true;
    const summary = doc.createElement('summary'); summary.textContent = t.phoneHelp; help.append(summary);
    const advice = [t.sharedWifi, t.allowPrivateNetwork];
    if (addresses.length > 1) advice.push(t.otherAddress);
    for (const line of advice) { const p = doc.createElement('p'); p.textContent = line; help.append(p); }
    text.append(help);
    if (!small) { const steps = doc.createElement('ol'); for (const line of t.phoneSteps) { const li = doc.createElement('li'); li.textContent = line; steps.append(li); } text.append(steps); }
    block.append(text); node.append(block);
  }
  phoneBlock($('.pc-phone-empty'), false); phoneBlock($('.pc-phone-small'), true);
  if (phoneUrl) startPhoneHelp();
  for (const host of [$('.pc-phone-empty'), $('.pc-phone-small')]) {
    const devices = doc.createElement('div'); devices.hidden = true; devices.className = 'pc-devices';
    host.append(devices); deviceHosts.push(devices);
  }
  function setDevices(devices) {
    if (destroyed) return;
    const phones = Array.isArray(devices) ? devices.filter(device => device.kind === 'phone' && !device.thisDevice) : null;
    phoneOpened = phones === null || phones.length > 0;
    updatePhoneHelp();
    for (const host of deviceHosts) {
      deviceList(host, phones ?? [], {lang:opts.lang, onDisconnect:opts.onDisconnect});
      host.hidden = !phones?.length;
    }
    const small = $('.pc-phone-small');
    small.classList.toggle('pc-phone-connected', !!phones?.length);
    let toggle = small.querySelector('.pc-phone-toggle');
    if (phones?.length && !toggle) {
      toggle = doc.createElement('button'); toggle.type = 'button'; toggle.className = 'pc-text-button pc-phone-toggle';
      toggle.textContent = en ? 'Show the QR code' : '显示二维码';
      on(toggle, 'click', () => { const open = small.classList.toggle('pc-phone-show'); toggle.textContent = open ? (en ? 'Hide the QR code' : '收起二维码') : (en ? 'Show the QR code' : '显示二维码'); });
      small.append(toggle);
    } else if (!phones?.length && toggle) { toggle.remove(); small.classList.remove('pc-phone-show'); }
  }
  function setPhoneLink(link) {
    if (destroyed) return;
    phoneUrl = safePhoneUrl(link.url); opts.phoneQrSvg = link.qr_svg;
    opts.addresses = link.addresses || []; opts.address = link.address;
    phoneShown = Date.now(); phoneOpened = false; startPhoneHelp();
    for (const [i, selector] of ['.pc-phone-empty', '.pc-phone-small'].entries()) {
      const host = $(selector);
      for (const img of host.querySelectorAll('.pc-qr')) {
        if (ownedUrls.has(img.src)) { win.URL.revokeObjectURL(img.src); ownedUrls.delete(img.src); }
      }
      host.replaceChildren(); phoneBlock(host, !!i); host.append(deviceHosts[i]);
    }
  }
  $('.pc-why').textContent = t.why(...measured);
  const svgNode = (name, attrs = {}) => { const n = doc.createElementNS('http://www.w3.org/2000/svg', name); for (const [k,v] of Object.entries(attrs)) n.setAttribute(k, v); return n; };
  const range = $('.pc-range'), rx = n => 4 + (n - 24) / 34 * 336;
  range.append(svgNode('rect', {x:4,y:6,width:336,height:10,class:'pc-range-unmeasured'}));
  for (let x = 4; x < 340; x += 5) {
    // Each hatch segment stays within the unmeasured span, without SVG IDs
    // that could collide when several module instances share a document.
    const radius = 24 + (x - 4) / 336 * 34;
    if (radius < measured[0] || radius > measured[1]) range.append(svgNode('path', {d:`M${x} 16l${Math.min(5,340-x)} -10`,class:'pc-range-hatch'}));
  }
  range.append(svgNode('rect', {x:rx(measured[0]),y:6,width:rx(measured[1])-rx(measured[0]),height:10,class:'pc-range-measured'}));
  for (let n = 24; n <= 58; n += 2) range.append(svgNode('path', {d:`M${rx(n)} 18v${n%8 === 0 || n === 58 ? 9 : 5}`,class:'pc-detail'}));
  for (const n of [...new Set([24, 32, 40, 48, ...measured, 58])]) { const text = svgNode('text', {x:rx(n), y:43, 'text-anchor':n === 24 ? 'start' : n === 58 ? 'end' : 'middle'}); text.textContent = n; range.append(text); }
  function cancelDrag(restore = false) {
    const previous = dragging; dragging = null;
    if (previous && restore && previous.kind === 'ring') selected().rings = previous.before;
    if (previous && stage.hasPointerCapture(previous.id)) stage.releasePointerCapture(previous.id);
    loupe.hidden = true; root.classList.remove('pc-dragging');
  }
  function layout(reset = false) {
    const bounds = stage.getBoundingClientRect();
    const reserve = focus ? 40 : 96;
    view = {...view, cx: bounds.width / 2, cy: (bounds.height - reserve) / 2 + (focus ? 20 : 8), pxPerMm: Math.max(0.1, Math.min(bounds.width - 56, bounds.height - reserve - 40) / 128)};
    if (reset) view = {...view, zoom:1, panX:0, panY:0};
    paint();
  }
  function setFocus(value) {
    if (active < 0 || value === focus) return;
    cancelDrag(); focus = value; root.classList.toggle('pc-is-focus', focus);
    if (opts.paperHost) doc.documentElement.classList.toggle('pc-photo-focus', focus);
    layout();
    if (focus) stage.focus({preventScroll:true}); else $('[data-pc="focus"]').focus();
  }
  function summary() {
    const p = selected(); if (!p) return;
    $('.pc-ring-count').textContent = t.ringCount(p.rings.length);
    $('.pc-offset').textContent = p.offsetMm === null ? t.unknown : `${p.offsetMm.toFixed(2)} mm`;
    $('.pc-registration').textContent = p.rim ? t.registered : t.unregistered;
    $('.pc-focus-readout').textContent = manual?.data ? `L ${manual.L_mm.toFixed(3)} mm · ${manual.c_deg.toFixed(2)}°`
      : `${t.ringCount(p.rings.length)} · ${t.offset}: ${p.offsetMm === null ? t.unknown : p.offsetMm.toFixed(2) + ' mm'}`;
    paper.querySelectorAll('.pc-radius-editor input').forEach((input, i) => { if (doc.activeElement !== input) input.value = p.rings[i].toFixed(1); });
  }
  function paint() {
    const p = selected(); if (!p || destroyed) return;
    const scale = view.pxPerMm * view.zoom, rim = p.rim || {cx:p.width/2, cy:p.height/2, radiusPx: Math.min(p.width,p.height)*0.43};
    const imageScale = scale * 60 / rim.radiusPx;
    const center = mmToPx({x:0,y:0}, view);
    image.style.width = `${p.width * imageScale}px`; image.style.height = `${p.height * imageScale}px`;
    image.style.transform = `translate(${center.x-rim.cx*imageScale}px, ${center.y-rim.cy*imageScale}px)`;
    image.classList.toggle('pc-enhanced', enhance);
    overlay.replaceChildren(); overlay.setAttribute('viewBox', `0 0 ${stage.clientWidth} ${stage.clientHeight}`);
    const guides = svgNode('g', {class:'pc-guides'});
    for (const radius of [24,58,60]) guides.append(svgNode('circle', {cx:center.x,cy:center.y,r:radius*scale,class:'pc-disc-outline'}));
    const guideAngle = 142 * Math.PI / 180;
    guides.append(svgNode('path', {d:`M${center.x+24*scale*Math.cos(guideAngle)} ${center.y+24*scale*Math.sin(guideAngle)}L${center.x+58*scale*Math.cos(guideAngle)} ${center.y+58*scale*Math.sin(guideAngle)}`,class:'pc-disc-outline'}));
    for (const radius of [24,40,58]) {
      const x = center.x + radius*scale*Math.cos(guideAngle), y = center.y+radius*scale*Math.sin(guideAngle);
      const label = svgNode('text', {x:x-8,y:y-5,class:'pc-scale-label'}); label.textContent = `${radius}${radius === 58 ? ' mm' : ''}`; guides.append(label);
    }
    if (curves) p.rings.forEach((radius, index) => {
      guides.append(svgNode('circle', {cx:center.x,cy:center.y,r:radius*scale,class:'pc-ring-outline'}));
      guides.append(svgNode('circle', {cx:center.x,cy:center.y,r:radius*scale,class:'pc-ring'}));
      ringHandles(radius).forEach((handle, h) => {
        const point = mmToPx(handle, view), held = dragging?.kind === 'ring' && dragging.index === index && dragging.handle === h;
        const group = svgNode('g', {class:`pc-handle${held ? ' pc-held' : ''}`, 'data-ring':index, 'data-handle':h, tabindex:'0', role:'slider', 'aria-label':`${t.ring} ${index+1}`, 'aria-valuemin':24, 'aria-valuemax':58, 'aria-valuenow':radius.toFixed(1), 'aria-valuetext':`${radius.toFixed(1)} mm`});
        group.append(svgNode('rect',{x:point.x-22,y:point.y-22,width:44,height:44,class:'pc-handle-hit'}));
        if (held) group.append(svgNode('circle',{cx:point.x,cy:point.y,r:11,class:'pc-handle-halo'}));
        group.append(svgNode('rect',{x:point.x-3.5,y:point.y-3.5,width:7,height:7,class:'pc-handle-square'}));
        guides.append(group);
      });
    });
    if (manual?.data) {
      if (curves) {
        const path = prediction(p, imageScale, center.x-rim.cx*imageScale, center.y-rim.cy*imageScale);
        overlay.append(svgNode('path', {d:path, class:'pc-prediction-outline', 'aria-hidden':'true'}),
          svgNode('path', {d:path, class:'pc-prediction', 'aria-hidden':'true'}));
      }
    } else if (recognized) {
      const left = center.x-rim.cx*imageScale, top = center.y-rim.cy*imageScale;
      overlay.append(svgNode('path', {d:evidencePath(p, imageScale, left, top, recognized.data), class:'pc-evidence', 'aria-hidden':'true'}));
      if (recognized.read) {
        const path = prediction(p, imageScale, left, top, recognized);
        overlay.append(svgNode('path', {d:path, class:'pc-recognized-outline', 'aria-hidden':'true'}),
          svgNode('path', {d:path, class:'pc-recognized-line', 'aria-hidden':'true'}));
      }
    } else if (!guided) overlay.append(guides);
    if (dragging?.kind === 'ring') {
      const point = dragging.point, radius = p.rings[dragging.index];
      const text = `r ${radius.toFixed(1)} mm · ${t.offsetShort} ${p.offsetMm === null ? '—' : p.offsetMm.toFixed(1)} mm`;
      const width = text.length * 7.5 + 20;
      const x = clamp(point.x + 18, 12, Math.max(12, stage.clientWidth-width-12));
      const y = clamp(point.y + 18, 8, stage.clientHeight-36);
      const chip = svgNode('g', {class:'pc-drag-chip'});
      chip.append(svgNode('rect', {x,y,width,height:28,rx:8}));
      const label = svgNode('text', {x:x+10,y:y+19,class:'pc-drag-label'});
      label.textContent = text; chip.append(label); overlay.append(chip);
      drawLoupe(point, rim, imageScale);
    }
    if (guided && guided.photo === p.id) paintGuided(p, imageScale, center.x-rim.cx*imageScale, center.y-rim.cy*imageScale);
    paintVeil(p, imageScale);
    const zoom = `${Math.round(view.zoom * 100)}%`;
    $('.pc-zoom').textContent = zoom; $('.pc-minimap output').textContent = zoom;
    const mini = $('.pc-mini-image'), miniSvg = mini.querySelector('svg');
    // Minimap rectangle uses the same image-to-screen transform as the photo.
    miniSvg.setAttribute('viewBox', `0 0 ${p.width} ${p.height}`);
    const rect = miniSvg.querySelector('rect');
    for (const [key,val] of Object.entries({x:rim.cx-center.x/imageScale,y:rim.cy-center.y/imageScale,width:stage.clientWidth/imageScale,height:stage.clientHeight/imageScale})) rect.setAttribute(key,val);
    summary();
  }
  // ---- hand-guided reading: drawing and steps
  function paintGuided(p, scale, left, top) {
    const L = guided.lines, w = L?.width || p.width, h = L?.height || p.height;
    const sx = p.width / w * scale, sy = p.height / h * scale;
    guided.xf = {left, top, sx, sy};
    const pt = ([x, y]) => `${(left + x*sx).toFixed(1)},${(top + y*sy).toFixed(1)}`;
    const line = (pts, close) => 'M' + pts.map(pt).join('L') + (close ? 'Z' : '');
    const g = svgNode('g', {class:'pc-guided-layer', 'aria-hidden':'true'});
    if (guided.result?.cells) for (const cell of guided.result.cells) g.append(svgNode('path', {d:line(cell.poly, true), class:'pc-evidence'}));
    if (L?.registered) {
      g.append(svgNode('path', {d:line(L.rim), class:'pc-guided-rim'}));
      for (const ring of L.rings) g.append(svgNode('path', {d:line(ring), class:'pc-guided-ring-line'}));
    }
    (guided.cands || []).forEach((c, i) => {
      if (guided.chosen !== undefined && guided.chosen !== i) return;
      g.append(svgNode('path', {d:line(c.arrow, true), class:'pc-guided-arrow'}));
      const cx = w / 2, cy = h / 2, far = c.arrow.reduce((a, b) => (Math.hypot(b[0]-cx, b[1]-cy) > Math.hypot(a[0]-cx, a[1]-cy) ? b : a));
      const label = svgNode('text', {x:(left + far[0]*sx + 8).toFixed(1), y:(top + far[1]*sy - 8).toFixed(1), class:'pc-guided-arrow-label'});
      label.textContent = 'ABCD'[i]; g.append(label);
    });
    for (const c of guided.clicks || []) g.append(svgNode('circle', {cx:(left + c[0]*sx).toFixed(1), cy:(top + c[1]*sy).toFixed(1), r:4, class:'pc-guided-click'}));
    if (guided.hub) g.append(svgNode('path', {d:`M${left + guided.hub[0]*sx - 7} ${top + guided.hub[1]*sy}h14M${left + guided.hub[0]*sx} ${top + guided.hub[1]*sy - 7}v14`, class:'pc-guided-hub'}));
    overlay.append(g);
  }
  function guidedStep(n) {
    for (const el of root.querySelectorAll('.pc-guided-step')) el.hidden = +el.dataset.step > n;
  }
  function guidedMsg(text) { const m = $('.pc-guided-msg'); if (m) m.textContent = text || ''; }
  function guidedRing() {
    const L = guided?.lines, el = $('.pc-guided-ring');
    if (!el) return;
    el.textContent = !L ? '' : !L.registered ? G.ringsNone : L.ring_locked ? G.locked : G.notLocked;
    el.dataset.locked = String(!!L?.ring_locked);
  }
  async function guidedCall(action, values = {}) {
    return opts.manualAlignment(action, descriptor(selected()), {token: guided.token, ...values});
  }
  async function guidedOpen() {
    const p = selected(); if (!p?.id || !sliderEnabled) return;
    if (manual) closeAlignment();
    recognized = null; root.classList.remove('pc-recognized');
    guided = {photo: p.id, clicks: [], hub: null};
    root.classList.add('pc-aligning'); guidedStep(1); guidedMsg(G.busy);
    try {
      const prep = await opts.manualAlignment('prepare', descriptor(p));
      if (!guided || guided.photo !== p.id) return;
      guided.token = prep.token;
      guided.lines = await guidedCall('lines');
      guidedMsg('');
      if (!guided.lines.registered) guidedClicking(true);
    } catch (error) { guidedMsg(error.message); }
    guidedRing(); paint();
  }
  function guidedClose() {
    if (!guided) return;
    guided = null; root.classList.remove('pc-aligning', 'pc-guided-clicking');
    guidedStep(0); guidedMsg('');
    const box = $('.pc-guided-cands'); if (box) box.replaceChildren();
    if (selected()) { recognize(); paint(); }
  }
  function guidedClicking(on) {
    if (!guided) return;
    guided.clicking = on; root.classList.toggle('pc-guided-clicking', on);
    const box = $('.pc-guided-clicking'); if (box) box.hidden = !on;
    guidedCount();
  }
  function guidedCount() {
    const el = $('.pc-guided-count'); if (el && guided) el.textContent = G.clicks(guided.clicks.length) + (guided.hub ? G.hubSet : '');
    const reg = $('[data-pc="g-register"]'); if (reg && guided) reg.disabled = guided.clicks.length < 5 || !guided.hub;
  }
  function guidedClick(event, at) {
    const xf = guided?.xf; if (!xf) return false;
    const x = (at.x - xf.left) / xf.sx, y = (at.y - xf.top) / xf.sy;
    if (event.shiftKey) guided.hub = [x, y]; else guided.clicks.push([x, y]);
    guidedCount(); paint(); return true;
  }
  async function guidedAction(name) {
    if (name === 'g-open') return guidedOpen();
    if (!guided) return;
    try {
      if (name === 'g-ok') { guidedClicking(false); guidedStep(2); }
      else if (name === 'g-click') { guidedClicking(true); }
      else if (name === 'g-clear') { guided.clicks = []; guided.hub = null; guidedCount(); paint(); }
      else if (name === 'g-reset') { guidedMsg(G.busy); guided.lines = await guidedCall('reset'); guided.clicks = []; guided.hub = null; guided.cands = guided.result = null; delete guided.chosen; guidedMsg(''); guidedRing(); guidedCount(); guidedStep(1); paint(); }
      else if (name === 'g-register') {
        guidedMsg(G.busy);
        guided.lines = await guidedCall('register', {clicks: guided.clicks, hub: guided.hub});
        guided.cands = guided.result = null; delete guided.chosen;
        guidedMsg(''); guidedRing(); paint();
        if (guided.lines.ring_locked) { guidedClicking(false); guidedStep(2); }
      } else if (name === 'g-find') {
        guidedMsg(G.busy);
        guided.cands = (await guidedCall('candidates')).candidates; guided.result = null; delete guided.chosen;
        const box = $('.pc-guided-cands'); box.replaceChildren();
        guided.cands.forEach((c, i) => {
          const b = doc.createElement('button'); b.type = 'button'; b.className = 'pc-button pc-small'; b.dataset.pc = 'g-pick'; b.dataset.index = i;
          b.textContent = G.onArrow('ABCD'[i]); box.append(b);
        });
        if (guided.cands.length) { const b = doc.createElement('button'); b.type = 'button'; b.className = 'pc-text-button'; b.dataset.pc = 'g-pick'; b.dataset.index = 0; b.textContent = G.noArrow; box.append(b); }
        guidedMsg(''); paint();
      } else if (name === 'g-save') {
        guidedMsg(G.busy);
        const result = await guidedCall('save_read');
        guidedMsg(G.saved);
        await opts.onManualSaved?.(result);
      }
    } catch (error) { guidedMsg(error.message); }
  }
  async function guidedPick(index) {
    if (!guided?.cands) return;
    guided.chosen = index; guidedMsg(G.busy); paint();
    try {
      const r = guided.result = await guidedCall('read', {index});
      guidedStep(3);
      const L = Number.isFinite(r.L_mm) ? r.L_mm.toFixed(3) : '\u2014', f = Number.isFinite(r.frames) ? r.frames.toFixed(1) : '';
      const out = $('.pc-guided-result');
      out.textContent = r.status === 'ok' ? (r.trusted ? G.ok(L, f) : G.okUnlocked) : G.retake(r.status);
      out.dataset.status = r.trusted ? 'ok' : 'retake';
      $('[data-pc="g-save"]').disabled = !r.trusted;
      guidedMsg('');
    } catch (error) { guidedMsg(error.message); }
    paint();
  }
  // Privacy: the photo underneath is blurred (CSS); a second, sharp copy on top is clipped to the registered disc.
  function paintVeil(p, scale) {
    const sharp = $('.pc-image-sharp');
    root.classList.toggle('pc-privacy', privacy);
    const data = manual?.data || recognized?.data;
    if (!privacy || !data?.H) { sharp.hidden = true; return; }       // no registration yet: the whole photo stays blurred
    if (sharp.src !== image.src) sharp.src = image.src;
    sharp.style.width = image.style.width; sharp.style.height = image.style.height; sharp.style.transform = image.style.transform;
    sharp.classList.toggle('pc-enhanced', enhance);
    const {H, width, height} = data, sx = p.width / width * scale, sy = p.height / height * scale;
    // the disc from its edge (61 mm) in to its clear hub (17 mm): the hub is transparent, so it stays blurred too
    const ring = r => {
      const pts = [];
      for (let i = 0; i < 96; i++) {
        const a = i / 96 * 2 * Math.PI, x = r * Math.cos(a), y = r * Math.sin(a), z = H[2][0]*x + H[2][1]*y + H[2][2];
        pts.push(`${(sx*(H[0][0]*x + H[0][1]*y + H[0][2])/z).toFixed(1)} ${(sy*(H[1][0]*x + H[1][1]*y + H[1][2])/z).toFixed(1)}`);
      }
      return `M${pts.join(' L')} Z`;
    };
    sharp.style.clipPath = `path(evenodd, "${ring(61)} ${ring(17)}")`;
    sharp.hidden = false;
  }
  // The cells where the reader found the pattern: one filled wedge per vote, in the disc plane through H.
  function evidencePath(p, scale, left, top, data) {
    const {H, width, height, evidence = [], evidence_half_span: half = Math.PI / 12} = data;
    const sx = p.width / width * scale, sy = p.height / height * scale;
    const xy = (r, angle) => {
      const x = r * Math.cos(angle), y = r * Math.sin(angle);
      const z = H[2][0]*x + H[2][1]*y + H[2][2];
      return `${(left + sx*(H[0][0]*x + H[0][1]*y + H[0][2])/z).toFixed(2)},${(top + sy*(H[1][0]*x + H[1][1]*y + H[1][2])/z).toFixed(2)}`;
    };
    const parts = [];
    for (const [a0, lo, hi] of evidence) {
      const steps = 16, pts = [];
      for (let i = 0; i <= steps; i++) pts.push(xy(hi, a0 - half + 2*half*i/steps));
      for (let i = steps; i >= 0; i--) pts.push(xy(lo, a0 - half + 2*half*i/steps));
      parts.push('M' + pts.join('L') + 'Z');
    }
    return parts.join('');
  }
  function prediction(p, scale, left, top, src = manual) {
    const {H, width, height, bands, rings} = src.data;
    const sx = p.width / width * scale, sy = p.height / height * scale;
    const c = src.c_deg * Math.PI / 180;
    const xy = (r, angle) => {
      const x = r * Math.cos(angle), y = r * Math.sin(angle);
      const z = H[2][0]*x + H[2][1]*y + H[2][2];
      const px = left + sx*(H[0][0]*x + H[0][1]*y + H[0][2])/z;
      const py = top + sy*(H[1][0]*x + H[1][1]*y + H[1][2])/z;
      return `${px.toFixed(2)},${py.toFixed(2)}`;
    };
    const parts = [];
    const trace = (steps, point) => {
      for (let i = 0; i <= steps; i++) parts.push((i ? 'L' : 'M') + point(i/steps));
    };
    for (const r of rings) trace(100, f => xy(r, f*2*Math.PI));
    for (const [lo,hi,angles] of bands) for (const angle of angles) {
      trace(Math.ceil(hi-lo), f => {
        const r = lo + f*(hi-lo);
        return xy(r, angle + c + src.L_mm/r);
      });
    }
    return parts.join('');
  }
  function alignmentMessage(key) {
    $('.pc-slider-message').textContent = key ? slider(key) : '';
  }
  function closeAlignment() {
    if (!sliderEnabled) return;
    const scrollTop = manual?.scrollTop;
    manual = null; win.clearTimeout(scoreTimer);
    root.classList.remove('pc-aligning');
    if (recognized) root.classList.add('pc-recognized');
    $('.pc-slider-controls').hidden = true;
    const toggle = $('[data-pc="align"]');
    toggle.querySelector('span').textContent = toggle.title = slider('open');
    toggle.setAttribute('aria-expanded', 'false');
    alignmentMessage(null);
    const scrollBox = opts.paperHost || paper;
    scrollBox.classList.remove('pc-slider-open');
    if (scrollTop !== undefined) scrollBox.scrollTop = scrollTop;
  }
  function sliderValue(input) {
    input.previousElementSibling.querySelector('output').textContent = input.dataset.alignValue === 'L_mm'
      ? `${input.valueAsNumber.toFixed(3)} mm` : `${input.valueAsNumber.toFixed(2)}°`;
    input.setAttribute('aria-valuetext', input.previousElementSibling.querySelector('output').textContent);
  }
  function queueScore() {
    const state = manual, key = ++state.scoreKey, label = $('.pc-slider-score');
    label.textContent = slider('checking');
    label.classList.remove('pc-slider-weak');
    win.clearTimeout(scoreTimer);
    scoreTimer = win.setTimeout(async () => {
      try {
        const result = await opts.manualAlignment('score', state.photo, {
          token:state.data.token, L_mm:state.L_mm, c_deg:state.c_deg,
        });
        if (destroyed || manual !== state || key !== state.scoreKey) return;
        label.textContent = sliderWords.score(result.agreeing, result.cells)[en ? 'en' : 'zh']
          + (result.weak ? ' · ' + slider('weak') : '');
        label.classList.toggle('pc-slider-weak', result.weak);
      } catch {
        if (!destroyed && manual === state && key === state.scoreKey) label.textContent = slider('scoreError');
      }
    }, 160);
  }
  async function toggleAlignment() {
    if (manual) { closeAlignment(); syncButtons(); paint(); return; }
    if (!selected()?.id) { alignmentMessage('unavailable'); return; }
    cancelDrag();
    root.classList.remove('pc-recognized');
    guidedClose();
    for (const fold of [$('.pc-more'), $('.pc-advanced'), $('.pc-slider-legacy')]) if (fold) fold.open = true;
    const state = manual = {photo:descriptor(selected()), scoreKey:0};
    const toggle = $('[data-pc="align"]');
    toggle.querySelector('span').textContent = toggle.title = slider('close');
    toggle.setAttribute('aria-expanded', 'true');
    alignmentMessage('loading'); syncButtons();
    try {
      const data = await opts.manualAlignment('prepare', state.photo);
      if (destroyed || manual !== state) return;
      state.data = data;
      const offset = $('[data-align-value="L_mm"]'), angle = $('[data-align-value="c_deg"]');
      for (const [key,value] of Object.entries(data.range_mm)) offset[key] = value;
      offset.value = data.L_mm; angle.value = data.c_deg;
      for (const input of [offset,angle]) { state[input.dataset.alignValue] = input.valueAsNumber; sliderValue(input); }
      curves = true;
      root.classList.add('pc-aligning');
      const controls = $('.pc-slider-controls');
      controls.hidden = false;
      const scrollBox = opts.paperHost || paper;
      state.scrollTop = scrollBox.scrollTop;
      scrollBox.classList.add('pc-slider-open');
      win.requestAnimationFrame(() => {
        if (destroyed || manual !== state) return;
        const bounds = scrollBox.getBoundingClientRect();
        const top = toggle.getBoundingClientRect().top;
        if (win.innerWidth <= 900 || top < bounds.top || controls.getBoundingClientRect().bottom > bounds.bottom) {
          scrollBox.scrollTop += top - bounds.top - 8;
        }
      });
      alignmentMessage(null); syncButtons(); paint(); queueScore();
    } catch {
      if (!destroyed && manual === state) { closeAlignment(); alignmentMessage('unavailable'); syncButtons(); }
    }
  }
  async function saveAlignment() {
    const state = manual;
    if (!state?.data || state.saving) return;
    state.saving = true; alignmentMessage('saving'); syncButtons();
    try {
      const result = await opts.manualAlignment('save', state.photo, {
        token:state.data.token, L_mm:state.L_mm, c_deg:state.c_deg,
      });
      if (!destroyed && manual === state) await opts.onManualSaved(result);
    } catch {
      if (!destroyed && manual === state) alignmentMessage('saveError');
    } finally {
      if (!destroyed && manual === state) { state.saving = false; syncButtons(); }
    }
  }
  function drawLoupe(point, rim, imageScale) {
    const place = magnifierPlacement(point,{width:stage.clientWidth,height:stage.clientHeight});
    if (!place) { loupe.hidden = true; return; }
    loupe.hidden = false; loupe.style.left = `${place.x}px`; loupe.style.top = `${place.y}px`; loupe.style.width = `${place.size}px`;
    const canvas = loupe.querySelector('canvas'), ctx = canvas.getContext('2d'), p = selected();
    const center = mmToPx({x:0,y:0},view), sourceX = rim.cx+(point.x-center.x)/imageScale, sourceY = rim.cy+(point.y-center.y)/imageScale;
    const sample = place.size / (4*imageScale);
    ctx.clearRect(0,0,328,328); ctx.fillStyle = win.getComputedStyle(root).getPropertyValue('--paper-2'); ctx.fillRect(0,0,328,328);
    ctx.filter = enhance ? 'contrast(1.65)' : 'none';
    ctx.drawImage(p.image,sourceX-sample/2,sourceY-sample/2,sample,sample,0,0,328,328); ctx.filter = 'none';
    ctx.strokeStyle = win.getComputedStyle(root).getPropertyValue('--ink'); ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(164,0); ctx.lineTo(164,328); ctx.moveTo(0,164); ctx.lineTo(328,164); ctx.stroke();
    loupe.querySelector('span').textContent = '4×';
  }
  function radiusEditor() {
    const box = $('.pc-radius-editor > div'); box.replaceChildren();
    selected().rings.forEach((radius,i) => {
      const label = doc.createElement('label'); label.textContent = `${t.ring} ${i+1}`;
      const input = doc.createElement('input'); input.type = 'number'; input.min = '24'; input.max = '58'; input.step = '0.1'; input.value = radius.toFixed(1); input.dataset.radius = i;
      label.append(input, ' mm'); box.append(label);
    });
  }
  function paintStrip() {
    const strip = $('.pc-strip'); strip.replaceChildren();
    const mark = {ok: '✓', outlier: '≠', retake: '!', failed: '!', reading: '…', queued: '…', waiting: '…'};
    photos.forEach((p,index) => {
      const b = doc.createElement('button'); b.type = 'button'; b.className = 'pc-thumb'; b.dataset.photo = index;
      b.setAttribute('aria-pressed',String(index === active));
      const frame = doc.createElement('span'); frame.className = 'pc-thumb-frame';
      const img = doc.createElement('img'); img.src = p.src; img.alt = p.name; frame.append(img);
      if (p.stage) {
        const badge = doc.createElement('i'); badge.className = 'pc-thumb-badge'; badge.dataset.stage = p.stage.stage;
        badge.textContent = mark[p.stage.stage] || '·'; badge.setAttribute('aria-hidden', 'true'); frame.append(badge);
      }
      b.append(frame);
      const number = en ? `Photo ${index+1}` : `第 ${index+1} 张`;
      b.setAttribute('aria-label', p.stage ? `${number}: ${p.stage.act[lang]}` : number);
      b.title = p.stage ? `${number} · ${p.stage.act[lang]}
${p.stage.why[lang]}` : number;
      strip.append(b);
    });
    strip.insertAdjacentHTML('beforeend',button('add',t.addMore,'plus','pc-thumb-add pc-icon-only'));
    $('.pc-photo-count').textContent = t.count(photos.length);
  }
  function choose(index) {
    if (!photos[index] || manual?.saving) return;
    if (index === active && manual) return;
    closeAlignment();
    guidedClose();
    cancelDrag(); task++; busy = false; active = index; root.classList.add('pc-has-photo');
    opts.paperHost?.classList.add('pc-has-photo');
    image.src = selected().src; image.hidden = false; $('.pc-photo-name').hidden = false;
    nameChip();
    $('.pc-mini-image img').src = selected().src;
    paintStrip(); radiusEditor(); syncButtons(); layout(true); recognize();
  }
  // What the reader found on the selected photo, drawn on it in green: the target's rings and pattern edges at the
  // reader's own along-track constant and rotation. Only for photos it read; nothing to adjust here.
  async function recognize() {
    const p = selected(), want = active, key = ++recognizeKey;
    recognized = null; root.classList.remove('pc-recognized'); nameChip();
    if (!sliderEnabled || !p?.id || !['ok', 'outlier', 'retake'].includes(p.stage?.stage)) return;
    try {
      const data = await opts.manualAlignment('prepare', descriptor(p));
      if (destroyed || want !== active || key !== recognizeKey || !data?.H) return;
      recognized = {data, L_mm: data.L_mm, c_deg: data.c_deg, read: ['ok', 'outlier'].includes(p.stage?.stage)};
      root.classList.add('pc-recognized'); nameChip(); paint();
    } catch { /* no registration for this photo: it stays as it is; its status is on the chip */ }
  }
  function nameChip() {
    const p = selected(), chip = $('.pc-photo-name');
    if (!p) return;
    const n = active + 1, head = en ? `Photo ${n} of ${photos.length}` : `第 ${n} 张，共 ${photos.length} 张`;
    const stageName = p.stage?.stage;
    let tail = '';
    if (stageName === 'ok') tail = recognized ? (en ? `Read: L = ${recognized.L_mm.toFixed(3)} mm` : `读出来了：L = ${recognized.L_mm.toFixed(3)} mm`) : (en ? 'Read' : '读出来了');
    else if (stageName === 'outlier') tail = en ? 'Read, but outside the majority' : '读出来了，但和多数不一致';
    else if (p.stage) {
      const found = recognized?.data?.evidence?.length;
      tail = p.stage.act[lang] + (Number.isFinite(found) ? (en ? ` · pattern found in ${found} place${found === 1 ? '' : 's'}` : ` · 读到 ${found} 处条纹`) : '');
    }
    chip.textContent = tail ? `${head} · ${tail}` : head;
    chip.dataset.state = stageName || '';
  }
  function syncButtons() {
    const use = $('[data-pc="use"]');
    use.disabled = manual ? !manual.data || !!manual.saving : active < 0 || busy || typeof opts.onUse !== 'function';
    use.querySelector('span').textContent = manual ? slider('save') : active < 0 ? t.next : t.use;
    $('.pc-next-why').textContent = active < 0 ? t.first : typeof opts.onUse !== 'function' ? t.noUse : '';
    $('[data-pc="back"]').hidden = typeof opts.onBack !== 'function';
    for (const action of ['select','pan','curves','enhance']) $('[data-pc="'+action+'"]').setAttribute('aria-pressed',String(action === 'select' || action === 'pan' ? action === tool : action === 'curves' ? curves : enhance));
    const auto = $('[data-pc="auto"]'); if (auto) { auto.disabled = busy; auto.querySelector('span').textContent = busy ? t.busy : t.auto; }
    root.classList.toggle('pc-pan',tool === 'pan' || space);
    stage.setAttribute('aria-busy',String(busy));
    if (sliderEnabled) {
      const toggle = $('[data-pc="align"]');
      toggle.disabled = !!manual?.saving;
      if (!manual) toggle.setAttribute('aria-expanded', 'false');
      for (const input of paper.querySelectorAll('[data-align-value]')) input.disabled = !!manual?.saving;
    }
    opts.onStateChange?.({canUse:!use.disabled, busy, focus, manual:!!manual, manualSaving:!!manual?.saving});
  }
  function descriptor(p) { return {id:p.id,src:p.src,name:p.name,label:p.label,reason:p.reason,file:p.file,rim:p.rim ? {...p.rim} : null,ringsMm:[...p.rings]}; }
  async function addPhotos(values, {preserveSelection = false} = {}) {
    let added = false;
    for (const value of values) {
      if (destroyed) return;
      let src, file = null, name, label = '', rim = null, rings = initialRings;
      if (value instanceof win.Blob) file = value;
      else if (value && typeof value === 'object') { file = value.file instanceof win.Blob ? value.file : null; src = value.src || value.url; name = value.name; label = value.label || ''; rim = value.rim; rings = validRings(value.ringsMm,initialRings); }
      else src = value;
      if (file) { if (file.type && !file.type.startsWith('image/')) { message(t.badFile); continue; } src = objectUrl(file); name ||= file.name; }
      src = safeUrl(src); if (!src) { message(t.badFile); continue; }
      message(t.loading);
      const photoImage = new win.Image();
      const ok = await new Promise(resolve => { photoImage.onload = () => resolve(true); photoImage.onerror = () => resolve(false); photoImage.src = src; });
      if (destroyed) return;
      if (!ok || !photoImage.naturalWidth) { if (ownedUrls.has(src)) { win.URL.revokeObjectURL(src); ownedUrls.delete(src); } message(t.badFile); continue; }
      const width = photoImage.naturalWidth, height = photoImage.naturalHeight;
      if (!rim || ![rim.cx,rim.cy,rim.radiusPx].every(Number.isFinite) || rim.radiusPx <= 0 || rim.cx < 0 || rim.cy < 0 || rim.cx > width || rim.cy > height) rim = null;
      photos.push({id:value?.id,src,file,name:name || `${t.photo} ${photos.length+1}`,label,reason:value?.reason || '',rim:rim ? {...rim} : null,rings:[...rings],baseline:[...rings],offsetMm:null,image:photoImage,width,height});
      added = true;
      message('');
      if (preserveSelection && active >= 0) paintStrip(); else choose(photos.length-1);
    }
    if (added) opts.onPhotos?.();
  }
  async function runAuto() {
    if (busy || !selected() || typeof opts.autoAlign !== 'function') return;
    cancelDrag(); const token = ++task, p = selected(); busy = true; message(''); syncButtons();
    try {
      const result = await opts.autoAlign(descriptor(p), [...p.rings]);
      if (destroyed || token !== task) return;
      const rings = validRings(result?.rings,[]);
      if (!rings.length || !Number.isFinite(result?.offsetMm)) throw new Error('invalid');
      p.rings = rings; p.offsetMm = result.offsetMm; radiusEditor(); paint();
    } catch (error) { if (token === task) message(error?.message === 'invalid' ? t.autoInvalid : t.autoError); }
    finally { if (!destroyed && token === task) { busy = false; syncButtons(); } }
  }
  function changeRing(index, radius) {
    const p = selected(); p.rings = resizeRing(p.rings,index,radius); p.offsetMm = null;
    // Invalidate a pending host result so it cannot overwrite a manual adjustment.
    task++; busy = false; syncButtons(); paint();
  }
  async function callHost(callback, ...args) {
    const using = callback === opts.onUse;
    if (using && busy) return;
    if (using) { busy = true; syncButtons(); }
    try { await callback?.(...args); } catch { message(t.callbackError); }
    finally { if (!destroyed && using) { busy = false; syncButtons(); } }
  }
  on(root,'click',event => {
    const photoButton = event.target.closest('[data-photo]'); if (photoButton) { choose(+photoButton.dataset.photo); return; }
    const b = event.target.closest('[data-pc]'); if (!b || b.disabled) return;
    switch (b.dataset.pc) {
      case 'add': $('.pc-file').click(); break;
      case 'back': callHost(opts.onBack); break;
      case 'skip': callHost(opts.onSkip); break;
      case 'use': if (manual) saveAlignment(); else if (selected()) callHost(opts.onUse,descriptor(selected()),[...selected().rings]); break;
      case 'align': toggleAlignment(); break;
      case 'g-open': case 'g-ok': case 'g-click': case 'g-clear': case 'g-reset': case 'g-register': case 'g-find': case 'g-save': guidedAction(b.dataset.pc); break;
      case 'g-pick': guidedPick(+b.dataset.index); break;
      case 'focus': setFocus(true); break;
      case 'exit': setFocus(false); break;
      case 'select': case 'pan': tool = b.dataset.pc; syncButtons(); break;
      case 'fit': layout(true); break;
      case 'in': case 'out': view = zoomAt(view,{x:stage.clientWidth/2,y:stage.clientHeight/2},b.dataset.pc === 'in' ? 1.2 : 1/1.2); paint(); break;
      case 'curves': cancelDrag(); curves = !curves; syncButtons(); paint(); break;
      case 'enhance': enhance = !enhance; syncButtons(); paint(); break;
      case 'auto': runAuto(); break;
      case 'reset': if (selected()) { cancelDrag(); task++; busy = false; selected().rings = [...selected().baseline]; selected().offsetMm = null; radiusEditor(); syncButtons(); layout(true); } break;
    }
  });
  if (sliderEnabled) {
    for (const input of paper.querySelectorAll('[data-align-value]')) {
      on(input, 'input', () => {
        manual[input.dataset.alignValue] = input.valueAsNumber;
        sliderValue(input); paint(); queueScore();
      });
      on(input, 'keydown', event => {
        const direction = {ArrowRight:1, ArrowUp:1, ArrowLeft:-1, ArrowDown:-1}[event.key];
        if (!direction || !event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) return;
        event.preventDefault(); input.stepUp(direction * 10);
        input.dispatchEvent(new win.Event('input'));
      });
    }
  }
  on(root,'change',event => {
    if (event.target.matches('.pc-file')) { addPhotos([...event.target.files]); event.target.value = ''; }
    if (event.target.matches('[data-radius]')) { changeRing(+event.target.dataset.radius,event.target.value === '' ? NaN : +event.target.value); event.target.value = selected().rings[+event.target.dataset.radius].toFixed(1); }
  });
  const point = event => { const r = stage.getBoundingClientRect(); return {x:event.clientX-r.left,y:event.clientY-r.top}; };
  on(stage,'dragover',event => { event.preventDefault(); if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'; root.classList.add('pc-drop-over'); });
  on(stage,'dragleave',event => { if (!stage.contains(event.relatedTarget)) root.classList.remove('pc-drop-over'); });
  on(stage,'drop',event => { event.preventDefault(); root.classList.remove('pc-drop-over'); addPhotos([...(event.dataTransfer?.files || [])]); });
  on(stage,'wheel',event => { if (!selected() || event.target.closest('.pc-toolbar,.pc-shortcuts')) return; event.preventDefault(); cancelDrag(); view = zoomAt(view,point(event),Math.exp(-clamp(event.deltaY,-300,300)*0.002)); paint(); },{passive:false});
  on(stage,'pointerdown',event => {
    if (event.button !== 0 || !selected() || event.target.closest('button,.pc-toolbar,.pc-loupe')) return;
    if (guided?.clicking && !space && tool !== 'pan') { event.preventDefault(); guidedClick(event, point(event)); return; }
    const handle = event.target.closest('[data-ring]'), at = point(event);
    if ((manual?.data || space || tool === 'pan')) dragging = {kind:'pan',id:event.pointerId,point:at,start:at,panX:view.panX,panY:view.panY};
    else if (handle) dragging = {kind:'ring',id:event.pointerId,index:+handle.dataset.ring,handle:+handle.dataset.handle,point:at,before:[...selected().rings]};
    else return;
    event.preventDefault(); stage.focus({preventScroll:true}); stage.setPointerCapture(event.pointerId); root.classList.add('pc-dragging'); paint();
  });
  on(stage,'pointermove',event => {
    if (!dragging || dragging.id !== event.pointerId) return;
    dragging.point = point(event);
    if (dragging.kind === 'pan') { view.panX = dragging.panX + dragging.point.x-dragging.start.x; view.panY = dragging.panY + dragging.point.y-dragging.start.y; paint(); }
    else { const mm = pxToMm(dragging.point,view); changeRing(dragging.index,Math.hypot(mm.x,mm.y)); }
  });
  on(stage,'pointerup',event => { if (dragging?.id === event.pointerId) { cancelDrag(); paint(); } });
  on(stage,'pointercancel',() => { cancelDrag(true); paint(); });
  on(stage,'lostpointercapture',() => { if (dragging) { dragging = null; loupe.hidden = true; root.classList.remove('pc-dragging'); paint(); } });
  on(root,'keydown',event => {
    const target = event.target;
    if (event.key !== 'Escape' && (target.matches('input,textarea,select') || target.isContentEditable) || event.ctrlKey || event.metaKey || event.altKey) return;
    if (focus && event.key === 'Tab') {
      const nodes = [...stage.querySelectorAll('button:not([disabled]),[data-ring]')].filter(n => n.getClientRects().length);
      const first = nodes[0], last = nodes.at(-1);
      if (event.shiftKey && (target === first || target === stage)) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && target === last) { event.preventDefault(); first?.focus(); }
    }
    if (event.key === ' ' && active >= 0 && !target.closest('button')) { event.preventDefault(); space = true; syncButtons(); }
    if (event.key.toLowerCase() === 'f' && !event.repeat) { event.preventDefault(); event.stopPropagation(); setFocus(!focus); }
    if (event.key === 'Escape') {
      event.preventDefault(); event.stopPropagation(); const next = photoKey({focus,dragging:!!dragging},event.key);
      if (focus) setFocus(next.focus);
      else if (dragging) { cancelDrag(true); paint(); }
      else callHost(opts.onBack);
    }
    const handle = target.closest('[data-ring]');
    if (handle && ['ArrowUp','ArrowRight','ArrowDown','ArrowLeft'].includes(event.key)) {
      event.preventDefault(); const index = +handle.dataset.ring, h = handle.dataset.handle;
      changeRing(index,selected().rings[index]+(event.key === 'ArrowUp' || event.key === 'ArrowRight' ? 1 : -1)*(event.shiftKey ? 1 : 0.1));
      overlay.querySelector(`[data-ring="${index}"][data-handle="${h}"]`)?.focus();
    }
    if ((manual?.data || space || tool === 'pan') && !handle && ['ArrowUp','ArrowRight','ArrowDown','ArrowLeft'].includes(event.key)) {
      event.preventDefault(); view.panX += event.key === 'ArrowRight' ? 24 : event.key === 'ArrowLeft' ? -24 : 0;
      view.panY += event.key === 'ArrowDown' ? 24 : event.key === 'ArrowUp' ? -24 : 0; paint();
    }
  });
  on(win,'keyup',event => { if (event.key === ' ') { space = false; syncButtons(); } });
  on(win,'blur',() => { space = false; cancelDrag(true); syncButtons(); paint(); });
  const resize = new win.ResizeObserver(() => layout()); resize.observe(stage);
  syncButtons();
  const ready = addPhotos(opts.photos || []).then(() => { if (!destroyed && Number.isInteger(opts.activePhoto)) choose(opts.activePhoto); });
  return {
    ready,
    setDevices,
    setPrivacy(on) {
      privacy = !!on;
      try { win.localStorage.setItem('discprobe-photo-privacy', privacy ? '1' : '0'); } catch { /* storage unavailable */ }
      if (destroyed) return;
      root.classList.toggle('pc-privacy', privacy);
      // the veil needs the reader's registration of the selected photo; fetch it if this photo has none yet
      if (privacy && selected() && !recognized && !manual) recognize();
      if (selected()) paint();
    },
    privacy: () => privacy,
    setPhoneLink,
    addPhotos,
    setPhotoId(photo, id) { const p = photos.find(p => photo.file ? p.file === photo.file : p.src === photo.src); if (p) p.id = id; },
    setReasons(perPhoto) { for (const p of photos) { const result = perPhoto.find(r => r.id === p.id); if (result) { const reason = photoReasonWords(result); p.reason = reason.zh === reason.en ? reason.en : reason[en ? 'en' : 'zh']; } } paintStrip(); },
    // The server's listing: each photo's stage (received, queued, reading, read) with times, never a camera-time guess.
    setListing(listing) {
      let changed = false;
      for (const p of photos) {
        const row = (listing?.photos || []).find(r => r.id === p.id);
        const stage = row ? photoStage(row, listing) : null;
        const key = stage ? stage.stage + stage.act.zh : '';
        if (key !== (p.stage ? p.stage.stage + p.stage.act.zh : '')) changed = true;
        p.stage = stage;
      }
      if (changed && !destroyed) { paintStrip(); if (!manual && selected() && (selected().stage?.stage === 'ok' || selected().stage?.stage === 'outlier') !== !!recognized) recognize(); else nameChip(); }
    },
    setReadResult(result) { if (result.verdict !== 'ok') return; for (const p of photos) { p.offsetMm = result.offset_mm; if (result.rings_mm) p.rings = [...result.rings_mm]; } if (selected()) { radiusEditor(); paint(); } },
    back() { if (focus) setFocus(false); else callHost(opts.onBack); },
    use() { if (manual) return saveAlignment(); if (selected() && !busy) return callHost(opts.onUse,descriptor(selected()),[...selected().rings]); },
    destroy() { if (destroyed) return; destroyed = true; win.clearTimeout(helpTimer); win.clearTimeout(scoreTimer); if (opts.paperHost) doc.documentElement.classList.remove('pc-photo-focus'); task++; abort.abort(); resize.disconnect(); cancelDrag(); for (const url of ownedUrls) win.URL.revokeObjectURL(url); ownedUrls.clear(); paper.remove(); opts.paperHost?.classList.remove('pc-embedded-paper','pc-has-photo','pc-slider-open'); root.remove(); },
    state() { const p = selected(); return {mode:p ? 'aligning' : 'no-photo',lang:opts.lang === 'en' ? 'en' : 'zh',photos:photos.map(descriptor),activePhoto:active,ringsMm:p ? [...p.rings] : [...initialRings],measuredMm:[...measured],offsetMm:p?.offsetMm ?? null,rimRegistered:!!p?.rim,focus,zoom:view.zoom,pan:{x:view.panX,y:view.panY},curves,enhance,busy}; },
  };
}
