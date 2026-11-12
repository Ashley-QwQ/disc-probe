/** Standalone photo calibration UI. No uploads or drive operations.
 * Photos may be Files, URLs, or {src, name, label, file, ringsMm, rim} objects.
 * Optional rim: {cx, cy, radiusPx}, in original image pixels, supplied by the
 * host's rim detector (60 mm disc radius). Without it the guides are explicitly
 * an unregistered preview; this module does not implement the photo reader.
 * phoneQrSvg may be a host-generated SVG string; it is displayed as an inert
 * image, never inserted as markup. All callbacks receive independent arrays.
 */
import { deviceList } from './kit/devices.js';
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
    local: '照片只在这台电脑的浏览器里打开，不会上传。', shoot: '这样拍',
    shootNotes: ['关掉其他灯，只留一盏。', '整张盘都在画面里，四周留一点边。', '看得见彩色条纹就行，不用拍得好看。'],
    phoneAbove: '手机在正上方，放平', lamp: '一盏灯，在侧前方', avoidLight: '别在灯正下方', disc: '盘，数据面朝上',
    drop: '没有手机，或者照片已经在电脑里：把文件拖到这里。', add: '从电脑添加照片', addMore: '再加一张照片',
    photos: '照片', count: n => `${n} 张`, current: '正在对', alignment: '对齐', manual: '手动调整',
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
    local: 'Photos open only in this computer’s browser. Nothing is uploaded.', shoot: 'How to shoot',
    shootNotes: ['Turn off other lights; leave just one.', 'Keep the whole disc in frame, with a little margin.', 'The coloured bands should be visible. It needn’t look pretty.'],
    phoneAbove: 'Phone directly above, held level', lamp: 'One light, to the side', avoidLight: 'Avoid directly under the light', disc: 'Disc, data side up',
    drop: 'No phone, or the photo is already on your computer? Drop the file here.', add: 'Add a photo from this computer', addMore: 'Add another photo',
    photos: 'Photos', count: n => `${n} photo${n === 1 ? '' : 's'}`, current: 'Aligning', alignment: 'Alignment', manual: 'Manual adjustment',
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
  const t = {...words[en ? 'en' : 'zh']};
  if (opts.paperHost) {
    t.phoneOffline = en ? 'This computer is not reachable from your phone. Add a photo from this computer.' : '手机暂时连不到这台电脑，请从电脑添加照片。';
    t.local = en ? 'Photos are sent to this computer on your local network.' : '照片通过局域网发到这台电脑。';
    if (typeof opts.autoAlign === 'function') t.reader = en ? 'Auto-align reads the photo. If it is unclear, the reason is shown below.' : '自动对齐会读取照片；读不准时，会在下面说明原因。';
    if (opts.media === 'cd') {
      t.title = en ? 'Read the along-track constant from a photo' : '拍照，读出沿轨常数';
      t.why = () => en ? 'This drive and disc batch need a photo to read the along-track constant. Keep the whole target disc in frame.' : '这台光驱和这批盘还需要靠照片读出沿轨常数。把整张标靶盘拍进画面。';
    }
  }
  const abort = new win.AbortController(), ownedUrls = new Set();
  const initialRings = validRings(opts.ringsMm);
  const measured = Array.isArray(opts.measuredMm) && opts.measuredMm.length === 2 && opts.measuredMm.every(Number.isFinite)
    && opts.measuredMm[0] >= 24 && opts.measuredMm[1] <= 58 && opts.measuredMm[0] < opts.measuredMm[1] ? [...opts.measuredMm] : [24, 52];
  let destroyed = false, active = -1, photos = [], dragging = null, space = false, task = 0;
  let view = {cx: 0, cy: 0, pxPerMm: 1, zoom: 1, panX: 0, panY: 0};
  let focus = false, curves = true, enhance = false, tool = 'select', busy = false;
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
            <svg viewBox="0 0 380 235" class="pc-shoot-diagram" role="img" aria-label="${t.phoneAbove}; ${t.lamp}; ${t.disc}">
              <g class="pc-detail"><path d="M190 74v134M166 76l-22 132m70-132 24 132M236 206l78-116"/><path d="m56 72 28 25m0-25L56 97"/></g>
              <g class="pc-structure"><path d="M35 211h315M145 207h91l5 4H140zM304 89l32 24v98"/><rect x="163" y="62" width="55" height="12" rx="3"/><path d="m296 76 18 13-13 16-18-13z"/></g>
              <text x="112" y="45">${t.phoneAbove}</text><text x="245" y="61">${t.lamp}</text><text x="34" y="118">${t.avoidLight}</text><text x="128" y="232">${t.disc}</text>
            </svg><ul>${t.shootNotes.map(note => `<li>${note}</li>`).join('')}</ul></section></div>
          <div class="pc-drop"><p>${t.drop}</p>${button('add', t.add, 'upload')}</div>
        </div>
        <img class="pc-image" alt="${t.photo}" draggable="false" hidden>
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
        <div class="pc-after"><section><div class="pc-section-title"><h2>${t.photos}</h2><span class="pc-photo-count"></span></div><div class="pc-strip"></div></section>
          <section class="pc-add-section"><div class="pc-phone-small"></div>${button('add', t.add, 'upload', 'pc-wide')}</section>
          <section><div class="pc-section-title"><h2>${t.alignment}</h2><span class="pc-stamp">${t.manual}</span></div>
            <dl class="pc-summary"><div><dt>${t.rings}</dt><dd class="pc-ring-count"></dd></div><div><dt>${t.offset}</dt><dd class="pc-offset"></dd></div></dl>
            <p class="pc-registration"></p><p>${t.reader}</p>
            <div class="pc-actions">${typeof opts.autoAlign === 'function' ? button('auto', t.auto, 'auto', 'pc-primary') : ''}${button('reset', t.reset, 'reset')}</div>
            <details class="pc-radius-editor"><summary>${t.adjust}</summary><p>${t.radiusTip}</p><div></div></details>
          </section>
        </div>
        ${typeof opts.onSkip === 'function' ? button('skip', t.skip, null, 'pc-skip pc-wide') : ''}
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
  const deviceHosts = [];
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
    if (!small) { const steps = doc.createElement('ol'); for (const line of t.phoneSteps) { const li = doc.createElement('li'); li.textContent = line; steps.append(li); } text.append(steps); }
    block.append(text); node.append(block);
  }
  phoneBlock($('.pc-phone-empty'), false); phoneBlock($('.pc-phone-small'), true);
  for (const host of [$('.pc-phone-empty'), $('.pc-phone-small')]) {
    const devices = doc.createElement('div'); devices.hidden = true; devices.className = 'pc-devices';
    host.append(devices); deviceHosts.push(devices);
  }
  function setDevices(devices) {
    if (destroyed) return;
    for (const host of deviceHosts) {
      host.hidden = !Array.isArray(devices);
      if (host.hidden) continue;
      deviceList(host, devices, {lang:opts.lang, onDisconnect:opts.onDisconnect});
    }
  }
  function setPhoneLink(link) {
    if (destroyed) return;
    phoneUrl = safePhoneUrl(link.url); opts.phoneQrSvg = link.qr_svg;
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
    layout();
    if (focus) stage.focus({preventScroll:true}); else $('[data-pc="focus"]').focus();
  }
  function summary() {
    const p = selected(); if (!p) return;
    $('.pc-ring-count').textContent = t.ringCount(p.rings.length);
    $('.pc-offset').textContent = p.offsetMm === null ? t.unknown : `${p.offsetMm.toFixed(2)} mm`;
    $('.pc-registration').textContent = p.rim ? t.registered : t.unregistered;
    $('.pc-focus-readout').textContent = `${t.ringCount(p.rings.length)} · ${t.offset}: ${p.offsetMm === null ? t.unknown : p.offsetMm.toFixed(2) + ' mm'}`;
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
    overlay.append(guides);
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
    const zoom = `${Math.round(view.zoom * 100)}%`;
    $('.pc-zoom').textContent = zoom; $('.pc-minimap output').textContent = zoom;
    const mini = $('.pc-mini-image'), miniSvg = mini.querySelector('svg');
    // Minimap rectangle uses the same image-to-screen transform as the photo.
    miniSvg.setAttribute('viewBox', `0 0 ${p.width} ${p.height}`);
    const rect = miniSvg.querySelector('rect');
    for (const [key,val] of Object.entries({x:rim.cx-center.x/imageScale,y:rim.cy-center.y/imageScale,width:stage.clientWidth/imageScale,height:stage.clientHeight/imageScale})) rect.setAttribute(key,val);
    summary();
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
    photos.forEach((p,index) => {
      const b = doc.createElement('button'); b.type = 'button'; b.className = 'pc-thumb'; b.dataset.photo = index;
      b.setAttribute('aria-pressed',String(index === active)); b.title = p.name;
      const img = doc.createElement('img'); img.src = p.src; img.alt = p.name;
      const label = doc.createElement('span'); label.textContent = index === active ? t.current : p.label || p.name; b.append(img,label); strip.append(b);
      if (p.reason) { const reason = doc.createElement('small'); reason.className = 'pc-photo-reason'; reason.textContent = p.reason; b.append(reason); }
    });
    strip.insertAdjacentHTML('beforeend',button('add',t.addMore,'plus','pc-thumb-add pc-icon-only'));
    $('.pc-photo-count').textContent = t.count(photos.length);
  }
  function choose(index) {
    if (!photos[index]) return;
    cancelDrag(); task++; busy = false; active = index; root.classList.add('pc-has-photo');
    opts.paperHost?.classList.add('pc-has-photo');
    image.src = selected().src; image.hidden = false; $('.pc-photo-name').hidden = false;
    $('.pc-photo-name').textContent = `${selected().name}  ${index+1} / ${photos.length}`;
    $('.pc-mini-image img').src = selected().src;
    paintStrip(); radiusEditor(); syncButtons(); layout(true);
  }
  function syncButtons() {
    const use = $('[data-pc="use"]'); use.disabled = active < 0 || busy || typeof opts.onUse !== 'function';
    use.querySelector('span').textContent = active < 0 ? t.next : t.use;
    $('.pc-next-why').textContent = active < 0 ? t.first : typeof opts.onUse !== 'function' ? t.noUse : '';
    $('[data-pc="back"]').hidden = typeof opts.onBack !== 'function';
    for (const action of ['select','pan','curves','enhance']) $('[data-pc="'+action+'"]').setAttribute('aria-pressed',String(action === 'select' || action === 'pan' ? action === tool : action === 'curves' ? curves : enhance));
    const auto = $('[data-pc="auto"]'); if (auto) { auto.disabled = busy; auto.querySelector('span').textContent = busy ? t.busy : t.auto; }
    root.classList.toggle('pc-pan',tool === 'pan' || space);
    stage.setAttribute('aria-busy',String(busy));
    opts.onStateChange?.({canUse:!use.disabled, busy, focus});
  }
  function descriptor(p) { return {id:p.id,src:p.src,name:p.name,label:p.label,reason:p.reason,file:p.file,rim:p.rim ? {...p.rim} : null,ringsMm:[...p.rings]}; }
  async function addPhotos(values, {preserveSelection = false} = {}) {
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
      message('');
      if (preserveSelection && active >= 0) paintStrip(); else choose(photos.length-1);
    }
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
      case 'use': if (selected()) callHost(opts.onUse,descriptor(selected()),[...selected().rings]); break;
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
    const handle = event.target.closest('[data-ring]'), at = point(event);
    if ((space || tool === 'pan')) dragging = {kind:'pan',id:event.pointerId,point:at,start:at,panX:view.panX,panY:view.panY};
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
    if ((space || tool === 'pan') && !handle && ['ArrowUp','ArrowRight','ArrowDown','ArrowLeft'].includes(event.key)) {
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
    setPhoneLink,
    addPhotos,
    setPhotoId(photo, id) { const p = photos.find(p => photo.file ? p.file === photo.file : p.src === photo.src); if (p) p.id = id; },
    setReasons(perPhoto) { for (const p of photos) { const result = perPhoto.find(r => r.id === p.id); if (result) p.reason = result.reason || ''; } paintStrip(); },
    back() { if (focus) setFocus(false); else callHost(opts.onBack); },
    use() { if (selected() && !busy) return callHost(opts.onUse,descriptor(selected()),[...selected().rings]); },
    destroy() { if (destroyed) return; destroyed = true; task++; abort.abort(); resize.disconnect(); cancelDrag(); for (const url of ownedUrls) win.URL.revokeObjectURL(url); ownedUrls.clear(); paper.remove(); opts.paperHost?.classList.remove('pc-embedded-paper','pc-has-photo'); root.remove(); },
    state() { const p = selected(); return {mode:p ? 'aligning' : 'no-photo',lang:opts.lang === 'en' ? 'en' : 'zh',photos:photos.map(descriptor),activePhoto:active,ringsMm:p ? [...p.rings] : [...initialRings],measuredMm:[...measured],offsetMm:p?.offsetMm ?? null,rimRegistered:!!p?.rim,focus,zoom:view.zoom,pan:{x:view.panX,y:view.panY},curves,enhance,busy}; },
  };
}
