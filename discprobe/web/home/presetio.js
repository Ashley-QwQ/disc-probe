// The sheet delegates all parsing, geometry and filesystem work to the shared core.
const STR = {
  zh: {
    close: '关闭', title: '预设 · DiscImageStudio', tabs: '预设', import: '导入', export: '导出',
    importData: '导入数据', exportData: '导出数据', slider: '导入或导出', idle: '空',
    importTitle: '导入 DIS 预设', exportTitle: '导出到 DIS', chooseFile: '选择文件',
    drop: '或把 DIS 的 JSON 拖到这里', standalone: '单个预设的盘种', automatic: '自动识别（CD、DVD）',
    bluRay: '蓝光', manual: '手动填写参数', displayName: '名称', media: '盘种',
    innerRadiusMm: '内半径（mm）', outerRadiusMm: '外半径（mm）', sectors: '扇区数',
    pitchLinear: '轨距线性项', pitchQuadratic: '轨距二次项', pitchCubic: '轨距三次项',
    pitchHint: '轨距三项可不填，默认为 0。', preview: '核对参数', choosePreset: '选择 DP 预设',
    install: '写进 DiscImageStudio', save: '存成文件', noneSaved: '还没有预设', working: '处理中…',
    failure: reason => `${chineseDetail(reason) ?? '预设操作失败。'}\n请检查文件或选择后重试。`,
    tooLarge: '文件超过 2 MiB',
    invalid: '无效预设', archive: '仅存档，DP 不能用来做图',
    summary: count => `${count} 个扇区`, pitch: '轨距',
    approximation: (angle, radius) => `近似：角度 ≤ ${angle}°，半径 ≤ ${radius} mm`,
    review: '核对参数并勾选要导入的预设。', emptyFile: '文件中没有预设',
    edited: '参数已修改，请重新核对。', choose: '选择文件或预设。', saved: '已保存 DIS 预设',
    imported: (written, duplicates) => `已导入：${written}；重复项保留：${duplicates}`,
    installed: ({path, backup}) => `已写入，请重启 DIS。\n${path}\n备份：${backup || '—'}`,
    invalidIssue: '预设参数无效。', warning: '请核对该预设的参数。',
  },
  en: {
    close: 'Close', title: 'Presets · DiscImageStudio', tabs: 'Presets', import: 'Import', export: 'Export',
    importData: 'Import', exportData: 'Export', slider: 'Import or export', idle: 'Idle',
    importTitle: 'Import DIS presets', exportTitle: 'Export to DIS', chooseFile: 'Choose file',
    drop: 'or drop a DIS JSON here', standalone: 'Standalone media', automatic: 'Automatic (CD, DVD)',
    bluRay: 'Blu-ray', manual: 'Type the parameters', displayName: 'Name', media: 'Media',
    innerRadiusMm: 'Inner radius (mm)', outerRadiusMm: 'Outer radius (mm)', sectors: 'Sector count',
    pitchLinear: 'Pitch linear', pitchQuadratic: 'Pitch quadratic', pitchCubic: 'Pitch cubic',
    pitchHint: 'Pitch terms are optional and default to 0.', preview: 'Preview parameters', choosePreset: 'Choose a DP preset',
    install: 'Write to DiscImageStudio', save: 'Save as file', noneSaved: 'No saved presets', working: 'Working…',
    failure: reason => `${reason || 'Preset operation failed.'}\nCheck the file or selection and retry.`,
    tooLarge: 'File exceeds 2 MiB',
    invalid: 'Invalid preset', archive: 'Archive only. Unavailable for DP drawing',
    summary: count => `${count} sectors`, pitch: 'pitch',
    approximation: (angle, radius) => `Approximation: angle ≤ ${angle}°, radius ≤ ${radius} mm`,
    review: 'Review the values and select presets to import.', emptyFile: 'No presets in this file',
    edited: 'Values changed. Preview again.', choose: 'Choose a file or preset.', saved: 'Saved DIS preset',
    imported: (written, duplicates) => `Imported: ${written}. Duplicates kept: ${duplicates}`,
    installed: ({path, backup}) => `Written. Restart DIS.\n${path}\nBackup: ${backup || '—'}`,
  },
};
// v1 supplies Chinese for exact dictionary hits; interpolated validation messages can be returned in English.
const ZH_DETAIL = new Map([
  ['preset must be an object', '预设必须是对象。'],
  ['id __manual__ is reserved by DIS', 'DIS 保留了预设 ID __manual__。'],
  ['conflicting sector fields', '扇区数字段相互冲突。'],
  ['BD needs outer <= 60 mm and totalSectors a multiple of 32 <= 12219392', 'BD 的外半径须不超过 60 mm，总扇区数须为 32 的倍数且不超过 12219392。'],
  ['invertMapping must be a boolean', '反转映射选项必须为布尔值。'],
  ['geometry exceeds DP numerical range', '几何参数超出 DP 的数值范围。'],
  ['ambiguous standalone DVD/BD preset; pass --media dvd or --media bd', '无法区分单个 DVD/BD 预设，请选择盘种。'],
  ['cannot identify media; use a catalog or --media', '无法识别盘种，请选择盘种或使用预设库文件。'],
  ['media must be cd, dvd or bd', '盘种必须是 CD、DVD 或 BD。'],
  ['preset file must be UTF-8 text <= 2 MiB', '预设文件须为不超过 2 MiB 的 UTF-8 文本。'],
  ['nonfinite JSON number', 'JSON 数值必须是有限数。'],
  ['file must hold a preset object or a DIS catalog', '文件须包含一个预设对象或一个 DIS 预设库。'],
  ['unsupported schemaVersion; expected 2, 3 or 4', '预设文件格式版本须为 2、3 或 4。'],
  ['legacy BD parameters document is not a catalog preset; export its catalog entry', '旧版 BD 参数文件无法作为预设导入，请导出预设库中的对应项目。'],
  ['invalid filename', '文件名无效。'],
  ['choose a DP preset', '请选择一个 DP 预设。'],
  ['DP preset must be an object', 'DP 预设须为对象。'],
  ['preset must be a JSON file inside the workspace', '预设须为工作目录中的 JSON 文件。'],
  ['presets folder must stay inside workspace', '预设目录须位于工作目录内。'],
  ['selection must contain preset indexes', '请选择要导入的预设。'],
  ['selection contains repeated indexes', '所选预设有重复项。'],
  ['selection contains a refused preset', '所选预设中有无效项。'],
]);
const ZH_FIELDS = {
  id: 'ID', displayName: '名称', description: '说明', sectors: '扇区数', totalSectors: '总扇区数',
  displayNameResourceKey: '名称资源键', descriptionResourceKey: '说明资源键', contributor: '贡献者',
  channelBitLengthNm: '通道位长', linearVelocityMmPerSecond: '线速度',
  cdPresets: 'CD 预设', dvdPresets: 'DVD 预设', bluRayPresets: '蓝光预设', source: '来源', fit: '拟合参数',
};
const ZH_PATTERNS = [
  [/^(\w+) must be a positive integer <= (\d+)$/, (field, limit) => `${ZH_FIELDS[field]}须为不超过 ${limit} 的正整数。`],
  [/^(\w+) must be (null or )?nonblank text$/, (field, optional) => `${ZH_FIELDS[field]}须为${optional ? '空值或' : ''}非空文本。`],
  [/^usableSectors must be positive, <= total, and a multiple of (\d+)$/, n => `可用扇区数须为正数、不超过总扇区数，且为 ${n} 的倍数。`],
  [/^(channelBitLengthNm|linearVelocityMmPerSecond) must be finite and positive$/, field => `${ZH_FIELDS[field]}须为有限正数。`],
  [/^Unknown fields retained; geometry use and DIS installation refused: (.+)$/, fields => `未知字段已保留，不能用于几何或安装到 DIS：${fields}`],
  [/^DIS rejects unknown fields; save as file instead: (.+)$/, fields => `DIS 不接受这些未知字段，请存成文件：${fields}`],
  [/^invalid JSON: .*?line (\d+) column (\d+)/s, (line, column) => `JSON 无效（第 ${line} 行，第 ${column} 列）。`],
  [/^invalid JSON:/, () => 'JSON 无效。'],
  [/^(cdPresets|dvdPresets|bluRayPresets) must be a list$/, field => `${ZH_FIELDS[field]}须为列表。`],
  [/^disabled (cd|dvd|bd) ids must be a text list$/, media => `停用的 ${media.toUpperCase()} 预设 ID 须为文本列表。`],
  [/^DP (source|fit) must be an object$/, field => `DP 的${ZH_FIELDS[field]}须为对象。`],
  [/^preset '(.+)' is already in .+ with different values;/s, id => `DIS 中已有参数不同的同名 ID：${id}。`],
  [/^(.+) has no DiscImageStudio schemaVersion \(2, 3 or 4\)$/s, path => `${path} 的 DiscImageStudio 预设格式版本须为 2、3 或 4。`],
  [/^(.+) is not valid JSON:/s, path => `${path} 不是有效的 JSON。`],
  [/^(.+) does not hold a DiscImageStudio preset object$/s, path => `${path} 未包含 DiscImageStudio 预设对象。`],
  [/^cannot (read|write|back up) (.+?): /s, (action, path) => `无法${{read: '读取', write: '写入', 'back up': '备份'}[action]} ${path}。`],
  [/^HTTP (\d+)$/, status => `请求失败（HTTP ${status}）。`],
];
function chineseDetail(issue) {
  if (ZH_DETAIL.has(issue)) return ZH_DETAIL.get(issue);
  for (const [pattern, format] of ZH_PATTERNS) {
    const match = pattern.exec(issue);
    if (match) return format(...match.slice(1));
  }
  return null;
}

export async function request(fetcher, payload) {
  const response = await fetcher('/api/presets', payload ? {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
  } : {});
  const data = await response.json();
  if (!response.ok) throw Error(data.error || `HTTP ${response.status}`);
  return data;
}

export function selectedIndexes(rows, checked) {
  return rows.filter(row => row.valid && checked.has(row.index)).map(row => row.index);
}

export function rowSummary(row, strings = STR.en) {
  const p = row.preset || {};
  return `${row.media.toUpperCase()} · ${p.id ?? '?'} · ${strings.summary(p.sectors ?? p.totalSectors ?? '?')} · ` +
    `${p.innerRadiusMm ?? '?'}–${p.outerRadiusMm ?? '?'} mm · ` +
    `${strings.pitch} ${p.pitchLinear ?? 0}, ${p.pitchQuadratic ?? 0}, ${p.pitchCubic ?? 0} · MID ${row.mid ?? '?'}`;
}

// the lobby's letter tray (target "fax") opens the same sheet; null when the server has no preset routes
let current = null;
export const ready = () => !!current;
export function open(from, options) { if (!current) return false; current.open(from, options); return true; }

// Scene-pixel coordinates from presetio/desk/desk.json. Kept local so this sheet
// also works from file URLs; the browser test checks these against the art metadata.
const desk = {
  width: 2560, height: 1440, knob: [2092, 539.8], travel: 187.2, plateLeft: 1984.7,
  leds: {export: [2022.4, 358.97, 9.9], import: [2022.4, 744.75, 9.9]},
  paper: [1090.05, 220.75, 1791.85, 1219.25], envelope: [1087.15, 595.19, 1794.75, 1366.75],
  // whole pictures (desk.json *_rect_px): the flights scale about their centres and leave the frame by their edges
  items: {sheets: [211.6, 150.4, 826.4, 998.4], bag: [188.2, 266.6, 853.7, 1188.5],
          doc_paper: [1020.5, 152.5, 1861.5, 1287.3], doc_envelope: [1011.8, 108.7, 1870.2, 1812.1]}
};
const stateName = value => value < 0 ? 'export' : value > 0 ? 'import' : 'idle';
const translate = y => `translateY(${y}px)`;

export async function init(entry, fetcher = fetch) {
  let catalogue;
  entry.hidden = true;
  try { catalogue = await request(fetcher); } catch { return null; } // old server: no dead entry
  if (catalogue.version !== 1) return null;
  const { pushLobby } = await import('./lobby.js');
  entry.hidden = false;
  const sheet = document.createElement('section');
  sheet.className = 'presetio'; sheet.hidden = true;
  sheet.setAttribute('aria-labelledby', 'presetio-title');
  const artUrl = name => new URL(`./presetio/desk/desk_${name}_${document.documentElement.dataset.theme === 'dark' ? 'dark' : 'paper'}.webp`, import.meta.url).href;
  const art = name => `<img data-art="${name}" src="${artUrl(name)}" alt="" draggable="false" aria-hidden="true">`;
  const layer = name => `<div class="presetio-layer" data-layer="${name}">${art(`${name}_shadow`)}${art(name)}</div>`;
  sheet.innerHTML = `<button type="button" class="presetio-close" data-close data-text="close"></button>
    <div class="presetio-scene presetio-paper">
    <h2 class="presetio-title" id="presetio-title" tabindex="-1" data-text="title"></h2>
    <div class="presetio-tabs" role="tablist" data-label="tabs">
      <button type="button" role="tab" id="presetio-tab-import" aria-controls="presetio-import" data-tab="1" data-text="import"></button>
      <button type="button" role="tab" id="presetio-tab-export" aria-controls="presetio-export" data-tab="-1" data-text="export"></button>
    </div>
    <div class="presetio-stage">
    ${art('base')}${layer('bag')}${art('upper')}${layer('sheets')}
    <div class="presetio-writing">
      <button type="button" data-move="-1" data-text="exportData"></button>
      <span class="presetio-tick" aria-hidden="true"></span>
      <button type="button" data-move="1" data-text="importData"></button>
    </div>
    <div class="presetio-layer" data-layer="knob">${art('knob_shadow')}${art('knob')}
      <div class="presetio-knob" role="slider" tabindex="0" data-label="slider"
        aria-orientation="vertical" aria-valuemin="-1" aria-valuemax="1" aria-valuenow="0"></div>
    </div>
    <span class="presetio-led" data-led="export" aria-hidden="true"></span><span class="presetio-led" data-led="import" aria-hidden="true"></span>
    <div class="presetio-layer presetio-document" data-layer="doc_paper">${art('doc_paper_shadow')}${art('doc_paper')}
    <article class="presetio-content" id="presetio-import" aria-labelledby="presetio-import-title" inert>
    <header><h3 id="presetio-import-title" data-text="importTitle"></h3></header>
    <div class="presetio-drop"><label class="presetio-file"><input type="file" accept=".json,application/json"><span class="presetio-pick" data-text="chooseFile"></span><span class="presetio-hint" data-filename></span></label></div>
    <label><span data-text="standalone"></span><select data-media><option value="" data-text="automatic"></option><option value="cd">CD</option><option value="dvd">DVD</option><option value="bd" data-text="bluRay"></option></select></label>
    <details class="presetio-manual"><summary data-text="manual"></summary>
      <form data-manual novalidate>
        <div class="presetio-fields">
        ${[['displayName', 'text'], ['media', 'select'], ['innerRadiusMm', 'number'], ['outerRadiusMm', 'number'],
          ['sectors', 'number'], ['pitchLinear', 'number'], ['pitchQuadratic', 'number'], ['pitchCubic', 'number']]
          .map(([name, type]) => `<label><span data-text="${name}"></span>${type === 'select'
            ? `<select name="media"><option value="cd">CD</option><option value="dvd">DVD</option></select>`
            : `<input name="${name}" type="${type}" ${type === 'number' ? `step="${name === 'sectors' ? '1' : 'any'}"` : ''} ${name.startsWith('pitch') ? 'value="0"' : 'required'} aria-describedby="presetio-error-${name}">`}
            <small class="presetio-field-error" id="presetio-error-${name}" data-error="${name}"></small></label>`).join('')}
        </div>
        <p class="presetio-hint" data-text="pitchHint"></p>
        <button type="submit" data-preview data-text="preview"></button>
      </form>
    </details>
    <div data-rows></div><div class="presetio-actions"><button type="button" data-import class="presetio-primary" data-text="import" disabled></button></div>
    <p role="status" aria-live="polite" class="presetio-status"></p></article></div>
    <div class="presetio-layer presetio-document" data-layer="doc_envelope">${art('doc_envelope_shadow')}${art('doc_envelope')}
    <article class="presetio-content" id="presetio-export" aria-labelledby="presetio-export-title" inert>
    <header><h3 id="presetio-export-title" data-text="exportTitle"></h3></header>
    <label><span data-text="choosePreset"></span><select data-presets></select></label>
    <div class="presetio-actions"><button type="button" data-install class="presetio-primary" data-text="install"></button><button type="button" data-save data-text="save"></button></div>
    </article></div></div></div>`;
  document.body.append(sheet);
  const $ = selector => sheet.querySelector(selector);
  const stage = $('.presetio-stage'), knob = $('.presetio-knob');
  const parts = Object.fromEntries([...sheet.querySelectorAll('[data-layer]')].map(el => [el.dataset.layer, el]));
  const contents = {import: $('#presetio-import'), export: $('#presetio-export')};
  const leds = {import: $('[data-led="import"]'), export: $('[data-led="export"]')};
  const status = $('.presetio-status');
  const language = () => document.documentElement.dataset.lang === 'zh' ? 'zh' : 'en';
  const T = () => STR[language()];
  const rect = (el, [left, top, right, bottom]) => Object.assign(el.style,
    {left: `${left}px`, top: `${top}px`, width: `${right - left}px`, height: `${bottom - top}px`});
  rect(contents.import, desk.paper); rect(contents.export, desk.envelope);
  rect(knob, [desk.knob[0] - 48, desk.knob[1] - 48, desk.knob[0] + 48, desk.knob[1] + 48]);
  for (const [name, [x, y, radius]] of Object.entries(desk.leds)) {
    rect(leds[name], [x - radius * .65, y - radius * .65, x + radius * .65, y + radius * .65]);
    $(`[data-move="${name === 'export' ? -1 : 1}"]`).style.top = `${y}px`;
  }
  Object.assign($('.presetio-tick').style, {left: `${desk.plateLeft - 30}px`, top: `${desk.knob[1]}px`});
  const paintDesk = () => {
    for (const img of sheet.querySelectorAll('[data-art]'))
      img.src = artUrl(img.dataset.art);
  };
  paintDesk();

  let value = 0, scale = 1, compact = false, playing = [], generation = 0, drag = null, frozen = new Map();
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  // The page's own setting decides: index.html resolves "auto" from the system into data-motion, and a person who
  // forced motion on while their system asks for less still gets it (the system flag alone must not win).
  const instant = () => compact || document.documentElement.dataset.motion === 'off';
  function announce() {
    sheet.dataset.state = stateName(value);
    knob.setAttribute('aria-valuenow', value);
    knob.setAttribute('aria-valuetext', T()[stateName(value)]);
    for (const [name, led] of Object.entries(leds)) led.dataset.active = String(name === stateName(value));
    for (const tab of sheet.querySelectorAll('[data-tab]')) {
      const selected = Number(tab.dataset.tab) === value;
      tab.setAttribute('aria-selected', selected); tab.tabIndex = selected ? 0 : -1;
    }
  }
  function settle() {
    const active = stateName(value);
    parts.knob.style.transform = translate(value * desk.travel);
    parts.bag.style.transform = translate(value < 0 ? desk.height : 0);
    parts.sheets.style.transform = translate(value > 0 ? -desk.height : 0);
    parts.doc_paper.style.transform = translate(value > 0 ? 0 : -desk.height);
    parts.doc_envelope.style.transform = translate(value < 0 ? 0 : desk.height);
    for (const [name, content] of Object.entries(contents)) {
      content.style.opacity = name === active ? '1' : '0'; content.inert = name !== active;
      leds[name].style.opacity = name === active ? '1' : '0';
      content.setAttribute('role', compact ? 'tabpanel' : 'region');
    }
    if (value) contents[active].append(status);
    for (const name of ['doc_paper', 'doc_envelope', 'bag', 'sheets']) $(`[data-art="${name}_shadow"]`).style.transform = 'none';
    sheet.dataset.playing = 'false'; announce();
  }
  function finish() {
    ++generation;
    // Finish the whole scheduled move, including delayed legs, before a new one.
    for (const animation of playing) animation.finish();
    settle();
    for (const animation of playing) animation.cancel();
    playing = [];
    frozen.clear();
  }
  function freeze() {
    ++generation;
    // Commit the displayed frame before cancelling, including delayed legs and their shadows.
    const sampled = new Map(frozen);
    const targets = playing.length || frozen.size ? new Set([
      ...Object.values(parts), ...Object.values(contents), ...Object.values(leds),
      ...sheet.querySelectorAll('[data-art$="_shadow"]')]) : new Set();
    for (const el of targets) {
      const style = getComputedStyle(el);
      sampled.set(el, {transform: style.transform, opacity: style.opacity});
    }
    for (const [el, style] of sampled) Object.assign(el.style, style);
    playing.forEach(a => a.cancel()); playing = [];
    frozen = sampled; return sampled;
  }
  function move(next, releasePoint = null) {
    if (next === value && playing.length && releasePoint === null) return;
    const from = value;
    // A drag already moved the knob's underlying style; preserve that release point.
    const sampled = freeze(); frozen = new Map(); value = next; announce();
    if (instant()) { settle(); return; }
    const release = releasePoint ?? parts.knob.style.transform;
    parts.knob.style.transform = release;
    for (const content of Object.values(contents)) {
      if (content.contains(document.activeElement)) knob.focus({preventScroll: true});
      content.inert = true;
    }
    sheet.dataset.playing = 'true';
    const token = generation;
    const animated = new Set();
    const animate = (el, frames, delay, duration, easing = 'linear') => {
      const first = !animated.has(el); animated.add(el);
      if (first && sampled.has(el)) {
        frames = frames.map((frame, i) => i ? frame : {...frame,
          ...Object.fromEntries(Object.keys(frame).filter(key => key in sampled.get(el)).map(key => [key, sampled.get(el)[key]]))});
      }
      const animation = el.animate(frames, {delay, duration, easing, fill: first ? 'both' : 'forwards'});
      playing.push(animation);
    };
    const fade = (el, a, b, delay, duration) => animate(el, [{opacity: a}, {opacity: b}], delay, duration, 'ease-out');
    // The flights (the person's design, 800 ms one way): the thing in the tray lifts off (grows a little, its shadow
    // drifts away as it rises), then flies out of the frame accelerating; only when it is fully out does the document
    // fly in from the other side, decelerating, and land (shrinks back, shadow comes home). Transforms only:
    // each layer is one composited picture (will-change in presetio.css), nothing repaints while it moves.
    const OUT = 360, IN = 440, LIFT = 1.06, H = desk.height;
    const lifted = 'translate(-26px, 34px) scale(1.04)';
    const exit = (name, up) => up ? -(desk.items[name][3] + 80) : H - desk.items[name][1] + 80;
    const origin = name => { const [l, t, r, b] = desk.items[name]; parts[name].style.transformOrigin = `${(l + r) / 2}px ${(t + b) / 2}px`; };
    const shadowOf = name => parts[name].querySelector(`[data-art="${name}_shadow"]`);
    function flyOut(name, up, at) {               // lift, then away
      origin(name);
      const dy = exit(name, up);
      animate(parts[name], [
        {transform: 'translateY(0px) scale(1)', easing: 'cubic-bezier(.3,0,.4,1)'},
        {transform: `translateY(${up ? -14 : 14}px) scale(${LIFT})`, offset: .28, easing: 'cubic-bezier(.5,0,.9,.5)'},
        {transform: `translateY(${dy}px) scale(${LIFT})`}], at, OUT);
      animate(shadowOf(name), [{transform: 'none', easing: 'ease-out'}, {transform: lifted, offset: .28}, {transform: lifted}], at, OUT);
    }
    function flyIn(name, fromTop, at) {           // in from outside, slow down, settle onto the desk
      origin(name);
      const dy = exit(name, fromTop);
      animate(parts[name], [
        {transform: `translateY(${dy}px) scale(${LIFT})`, easing: 'cubic-bezier(.12,.7,.3,1)'},
        {transform: `translateY(${fromTop ? 10 : -10}px) scale(${LIFT})`, offset: .72, easing: 'cubic-bezier(.4,0,.2,1)'},
        {transform: 'translateY(0px) scale(1)'}], at, IN);
      animate(shadowOf(name), [{transform: lifted}, {transform: lifted, offset: .72, easing: 'cubic-bezier(.4,0,.2,1)'}, {transform: 'none'}], at, IN);
    }
    let time = 0, start = release;
    if (from && from !== next) {                  // put the open document back: it leaves, the tray's paper returns
      const name = stateName(from), doc = from < 0 ? 'doc_envelope' : 'doc_paper', source = from < 0 ? 'bag' : 'sheets';
      animate(parts.knob, [{transform: start}, {transform: translate(0)}], 0, 220, 'cubic-bezier(.3,0,.2,1)'); start = translate(0);
      fade(leds[name], 1, 0, 0, 150);
      fade(contents[name], 1, 0, 0, 120);
      flyOut(doc, from > 0, 60);                  // the sheet goes back up, the envelope back down
      flyIn(source, from > 0, 60 + OUT);          // the sheets drop back in from above, the bag rises back from below
      time = 60 + OUT + IN;
    }
    if (next && from !== next) {
      const name = stateName(next), doc = next < 0 ? 'doc_envelope' : 'doc_paper', source = next < 0 ? 'bag' : 'sheets';
      animate(parts.knob, [{transform: start}, {transform: translate(next * desk.travel)}], time, 220, 'cubic-bezier(.3,0,.2,1)');
      fade(leds[name], 0, 1, time + 180, 150);
      flyOut(source, next > 0, time);             // import: the tray's sheets fly up; export: the bag drops out
      flyIn(doc, next > 0, time + OUT);           // import: the sheet comes down from above; export: the envelope up
      fade(contents[name], 0, 1, time + OUT + IN - 80, 160);
    } else if (from === next) {
      animate(parts.knob, [{transform: start}, {transform: translate(next * desk.travel)}], 0, 220, 'cubic-bezier(.3,0,.2,1)');
    }
    Promise.all(playing.map(animation => animation.finished)).then(() => {
      if (token === generation) finish();
    }).catch(() => {}); // finish() cancels completed animations after committing their styles.
  }
  function layout() {
    finish();
    const aspect = innerWidth / innerHeight;
    scale = Math.max(innerWidth / desk.width, innerHeight / desk.height);
    // Reserve the right gutter and keep the upper label below the shared toolbar after cropping.
    const labelTop = (innerHeight - desk.height * scale) / 2 + (desk.leds.export[1] - 32) * scale;
    const toolbarBottom = document.querySelector('.top')?.getBoundingClientRect().bottom ?? 0;
    compact = innerWidth < 820 || aspect < 1.5 || aspect > 2.4 || labelTop < toolbarBottom + 8;
    sheet.dataset.compact = String(compact);
    stage.style.transform = `translate(-50%, -50%) scale(${scale})`;
    if (compact && !value) value = 1; // The compact card always opens on a usable tab.
    settle();
  }
  window.addEventListener('resize', layout);
  new MutationObserver(records => {
    if (records.some(record => record.attributeName === 'data-theme')) paintDesk();
    if (instant()) finish();
  }).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme', 'data-motion']});

  for (const label of sheet.querySelectorAll('[data-move], [data-tab]'))
    label.addEventListener('click', () => move(Number(label.dataset.move ?? label.dataset.tab)));
  $('.presetio-tabs').addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 1 : event.key === 'End' ? -1 : -value;
    move(next); $(`[data-tab="${next}"]`).focus();
  });
  knob.addEventListener('keydown', event => {
    if (!['ArrowUp', 'ArrowDown'].includes(event.key)) return;
    event.preventDefault(); move(Math.max(-1, Math.min(1, value + (event.key === 'ArrowUp' ? -1 : 1))));
  });
  knob.addEventListener('pointerdown', event => {
    if (event.button !== 0 || drag) return;
    freeze(); knob.setPointerCapture(event.pointerId); knob.focus({preventScroll: true});
    const start = new DOMMatrix(getComputedStyle(parts.knob).transform).m42;
    drag = {id: event.pointerId, y: event.clientY, start, offset: start};
    event.preventDefault();
  });
  knob.addEventListener('pointermove', event => {
    if (!drag || drag.id !== event.pointerId) return;
    drag.offset = Math.max(-desk.travel, Math.min(desk.travel, drag.start + (event.clientY - drag.y) / scale));
    parts.knob.style.transform = translate(drag.offset);
  });
  function release(event, cancelled = false) {
    if (!drag || drag.id !== event.pointerId) return;
    const next = cancelled ? value : Math.abs(drag.offset) > desk.travel * .4 ? Math.sign(drag.offset) : 0;
    const id = drag.id; drag = null;
    if (knob.hasPointerCapture(id)) knob.releasePointerCapture(id);
    move(next, parts.knob.style.transform);
  }
  knob.addEventListener('pointerup', event => release(event));
  knob.addEventListener('pointercancel', event => release(event, true));
  knob.addEventListener('lostpointercapture', event => release(event, true));
  layout();
  const checkboxes = new Map();
  const previewText = new Map();
  let preview = null, upload = null, busy = false, revision = 0, lastFile = null, callbacks = {};
  let notice = null;
  function paintMessage() {
    const text = notice && T()[notice.key];
    status.textContent = typeof text === 'function' ? text(...notice.args) : text ?? '';
  }
  function message(key, ...args) {
    notice = {key, args};
    status.dataset.error = String(key === 'failure' || key === 'tooLarge');
    paintMessage();
  }
  function paintLanguage() {
    const t = T();
    for (const el of sheet.querySelectorAll('[data-text]')) el.textContent = t[el.dataset.text];
    for (const el of sheet.querySelectorAll('[data-label]')) el.setAttribute('aria-label', t[el.dataset.label]);
    knob.setAttribute('aria-valuetext', t[stateName(value)]);
    if (!lastFile) $('[data-filename]').textContent = t.drop;
    for (const [el, format] of previewText) el.textContent = format(t);
    paintMessage();
  }
  function textFor(el, format) {
    previewText.set(el, format);
    el.textContent = format(T());
  }
  function buttons() {
    $('[data-import]').disabled = busy || !preview || !selectedIndexes(preview.entries,
      new Set([...checkboxes].filter(([, box]) => box.checked).map(([i]) => i))).length;
    for (const name of ['install', 'save']) $(`[data-${name}]`).disabled = busy || !$('[data-presets]').value;
    $('input[type=file]').disabled = busy; $('[data-media]').disabled = busy;
    for (const field of $('[data-manual]').elements) field.disabled = busy;
  }
  function renderCatalogue(data) {
    catalogue = data;
    $('[data-presets]').replaceChildren();
    if (!data.presets.length) {
      const option = document.createElement('option'); option.value = ''; option.dataset.text = 'noneSaved'; option.textContent = T().noneSaved;
      $('[data-presets]').append(option);
    }
    for (const item of data.presets) {
      const option = document.createElement('option'); option.value = item.path; option.textContent = item.name;
      $('[data-presets]').append(option);
    }
    buttons();
  }
  async function run(action) {
    if (busy) return;
    busy = true; buttons(); message('working');
    try { await action(); } catch (error) { message('failure', error.message); }
    finally { busy = false; buttons(); }
  }
  async function load(file) {
    if (!file) return;
    lastFile = file; $('[data-filename]').textContent = file.name;
    const current = ++revision;
    clearPreview(); clearFieldErrors();
    if (file.size > 2 * 1024 * 1024) { message('tooLarge'); return; }
    await run(async () => {
      const text = await file.text();
      const payload = {operation: 'preview', text, filename: file.name, media: $('[data-media]').value || null};
      const result = await request(fetcher, payload);
      if (current !== revision) return;
      preview = result; upload = payload;
      showPreview(result);
    });
  }
  function clearPreview() {
    preview = upload = null; checkboxes.clear(); previewText.clear(); $('[data-rows]').replaceChildren(); buttons();
  }
  function clearFieldErrors() {
    for (const el of sheet.querySelectorAll('.presetio-field-error')) el.textContent = '';
    for (const el of $('[data-manual]').elements) el.removeAttribute('aria-invalid');
  }
  function localizedIssue(row, index) {
    const issue = row.issues[index];
    if (language() === 'en') return issue;
    const translated = row.issues_zh?.[index];
    if (translated && translated !== issue) return translated;
    return chineseDetail(issue) ?? (row.valid ? STR.zh.warning : STR.zh.invalidIssue);
  }
  function fieldError(row, index) {
    const issue = row.issues[index];
    const keys = /radii|RadiusMm/.test(issue) ? ['innerRadiusMm', 'outerRadiusMm']
      : /pitch/.test(issue) ? ['pitchLinear', 'pitchQuadratic', 'pitchCubic']
      : /sectors|totalSectors/.test(issue) ? ['sectors'] : /displayName|description/.test(issue) ? ['displayName'] : [];
    for (const key of keys) {
      textFor($(`[data-error="${key}"]`), () => localizedIssue(row, index));
      $('[data-manual]').elements.namedItem(key).setAttribute('aria-invalid', 'true');
    }
  }
  function showPreview(result, manual = false) {
    for (const row of result.entries) {
      const block = document.createElement('div'); block.className = 'presetio-row';
      const label = document.createElement('label'), box = document.createElement('input');
      box.type = 'checkbox'; box.disabled = !row.valid; box.checked = row.valid && !row.disabled;
      box.addEventListener('change', buttons); checkboxes.set(row.index, box);
      const name = document.createElement('strong');
      textFor(name, t => row.preset?.displayName || t.invalid);
      label.append(box, name);
      const summary = document.createElement('p'); summary.className = 'presetio-data';
      textFor(summary, t => rowSummary(row, t) + (row.valid && row.image_compatible === false ? ` · ${t.archive}` : ''));
      const issues = document.createElement('ul');
      row.issues.forEach((_, i) => {
        const li = document.createElement('li');
        textFor(li, () => localizedIssue(row, i)); issues.append(li);
        if (manual && !row.valid) fieldError(row, i);
      });
      if (row.comparison) {
        const li = document.createElement('li');
        const angle = row.comparison.max_angle_error_deg.toPrecision(6);
        const radius = row.comparison.max_radius_error_mm.toPrecision(6);
        textFor(li, t => t.approximation(angle, radius)); issues.append(li);
      }
      block.append(label, summary, issues); $('[data-rows]').append(block);
    }
    message(result.entries.length ? 'review' : 'emptyFile');
  }
  $('[data-manual]').addEventListener('input', () => { ++revision; clearPreview(); clearFieldErrors(); message('edited'); });
  $('[data-manual]').addEventListener('submit', event => {
    event.preventDefault();
    if (busy) return;
    const fields = event.currentTarget.elements, media = fields.namedItem('media').value;
    const name = fields.namedItem('displayName').value.trim();
    const preset = {id: `user-custom-${crypto.randomUUID()}`, displayName: name, description: name};
    for (const key of ['innerRadiusMm', 'outerRadiusMm', 'sectors', 'pitchLinear', 'pitchQuadratic', 'pitchCubic']) {
      const raw = fields.namedItem(key).value.trim();
      const number = raw === '' ? (key.startsWith('pitch') ? 0 : null) : Number(raw);
      preset[key === 'sectors' && media === 'dvd' ? 'totalSectors' : key] = number;
    }
    const current = ++revision;
    clearPreview(); clearFieldErrors();
    // CD counts are signed 64-bit integers in DIS. Preserve their digits past JS's safe-integer range;
    // the core still owns validation, including the upper bound and fractional/empty input refusal.
    const count = fields.namedItem('sectors').value.trim(), sectorKey = media === 'cd' ? 'sectors' : 'totalSectors';
    let text = JSON.stringify(preset);
    if (/^[+-]?\d+$/.test(count)) {
      delete preset[sectorKey];
      text = JSON.stringify(preset).slice(0, -1) + `,"${sectorKey}":${BigInt(count)}}`;
    }
    const payload = {operation: 'preview', text, filename: 'manual-dis-preset.json', media};
    run(async () => {
      const result = await request(fetcher, payload);
      if (current !== revision) return;
      preview = result; upload = payload; showPreview(result, true);
    });
  });
  $('input[type=file]').addEventListener('change', event => load(event.target.files[0]));
  $('[data-media]').addEventListener('change', () => load(lastFile));
  const drop = $('.presetio-drop');
  drop.addEventListener('dragover', event => { event.preventDefault(); drop.dataset.over = 'true'; });
  drop.addEventListener('dragleave', () => { drop.dataset.over = 'false'; });
  drop.addEventListener('drop', event => { event.preventDefault(); drop.dataset.over = 'false'; if (!busy) load(event.dataTransfer.files[0]); });
  $('[data-import]').addEventListener('click', () => run(async () => {
    const onImported = callbacks.onImported;
    const selected = selectedIndexes(preview.entries, new Set([...checkboxes].filter(([, box]) => box.checked).map(([i]) => i)));
    const result = await request(fetcher, {...upload, operation: 'import', selected});
    globalThis.dispatchEvent(new Event('dp-catalogue-changed'));
    await onImported?.(result);
    renderCatalogue(await request(fetcher));
    message('imported', result.written.length, result.duplicates.length);
  }));
  for (const install of [true, false]) $(`[data-${install ? 'install' : 'save'}]`).addEventListener('click', () => run(async () => {
    const result = await request(fetcher, {operation: 'export', path: $('[data-presets]').value, install});
    if (install) message('installed', result.installation);
    else {
      const blob = new Blob([JSON.stringify(result.preset, null, 2) + '\n'], {type: 'application/json'});
      const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url;
      link.download = 'dis-preset.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      message('saved');
    }
  }));
  // The site's own "上一步" (index.html #back, top left) is this page's way out, as on every other page; it is lifted
  // above the sheet while it is open, and given back as it was on close.
  const back = document.getElementById('back');
  let backWasHidden = true, modeBefore = '';
  let pageFlight = null, entrance = null, closing = false;
  function endPageFlight() {
    pageFlight?.push?.done(); pageFlight?.anims.forEach(a => a.cancel()); pageFlight = null;
    sheet.style.willChange = '';
  }
  function closed() {
    endPageFlight(); closing = false;
    finish(); drag = null; sheet.hidden = true;
    delete document.documentElement.dataset.presetio;
    document.documentElement.dataset.mode = modeBefore;
    if (back) back.hidden = backWasHidden;
    const onClose = callbacks.onClose; callbacks = {};
    onClose?.();
    (opener?.isConnected ? opener : entry).focus();
  }
  function watchPageFlight(flight, done) {
    Promise.all(flight.anims.map(a => a.finished)).catch(() => {}).then(() => { if (pageFlight === flight) done(); });
  }
  function close() {
    if (sheet.hidden || closing) return;
    closing = true;
    if (document.documentElement.dataset.motion === 'off' || !entrance) { closed(); return; }
    if (pageFlight) {
      pageFlight.anims.forEach(a => a.reverse());
      watchPageFlight(pageFlight, closed); return;
    }
    const push = entrance.lobby ? pushLobby(entrance.lobby, true) : null;
    sheet.style.willChange = 'transform, opacity';
    const a = sheet.animate([...entrance.frames].reverse(), {duration: entrance.duration, easing: 'cubic-bezier(.5,0,.9,.5)', fill: 'both'});
    pageFlight = {push, anims: [a, ...(push?.anims ?? [])]};
    watchPageFlight(pageFlight, closed);
  }
  new MutationObserver(() => {
    if (document.documentElement.dataset.motion !== 'off' || !pageFlight) return;
    pageFlight.anims.forEach(a => a.finish());
    if (closing) closed(); else endPageFlight();
  }).observe(document.documentElement, {attributes: true, attributeFilter: ['data-motion']});
  back?.addEventListener('click', event => {
    if (sheet.hidden) return;
    event.preventDefault(); event.stopImmediatePropagation(); close();
  }, {capture: true});
  $('[data-close]').addEventListener('click', close);
  sheet.addEventListener('keydown', event => { event.stopPropagation(); if (event.key === 'Escape') { event.preventDefault(); close(); } });
  let opener = entry;
  function open(from = entry, options = {}) {
    if (!sheet.hidden) return;
    callbacks = options; closing = false;
    const tray = document.querySelector('#lobby-art [data-target="fax"].lb-hit');
    const r = !document.documentElement.dataset.mode ? tray?.getBoundingClientRect() : null;
    const x = r?.width ? r.left + r.width / 2 : innerWidth / 2, y = r?.width ? r.top + r.height / 2 : innerHeight / 2;
    const lobby = r?.width ? {origin: `${x}px ${y}px`, to: `translate(${innerWidth / 2 - x}px, ${innerHeight / 2 - y}px) scale(3.5)`} : null;
    entrance = document.documentElement.dataset.motion === 'off' ? null : {
      lobby, duration: lobby ? 760 : 220,
      frames: lobby ? [{transform: `translate(${x - innerWidth / 2}px, ${y - innerHeight / 2}px) scale(.18)`, opacity: 0}, {transform: 'none', opacity: 1}]
        : [{opacity: 0}, {opacity: 1}]
    };
    finish(); value = [-1, 1].includes(options.state) ? options.state : 0; opener = from; sheet.hidden = false;
    $('.presetio-manual').open = !!options.manual;
    if (options.state === 1 || options.manual) { clearPreview(); clearFieldErrors(); }
    $('[data-manual]').elements.namedItem('media').value = options.media === 'cd' ? 'cd' : 'dvd';
    document.documentElement.dataset.presetio = 'open';
    // a page of its own, like new work: the header folds the wordmark to "DP" beside 上一步 (index.html keys it on
    // data-mode); the mode it came from comes back on close
    modeBefore = document.documentElement.dataset.mode || ''; document.documentElement.dataset.mode = 'presets';
    if (back) { backWasHidden = back.hidden; back.hidden = false; }
    layout(); $('#presetio-title').focus();
    if (entrance) {
      const push = entrance.lobby ? pushLobby(entrance.lobby) : null;
      sheet.style.willChange = 'transform, opacity';
      const a = sheet.animate(entrance.frames, {duration: entrance.duration, easing: 'cubic-bezier(.2,.8,.2,1)', fill: 'both'});
      pageFlight = {push, anims: [a, ...(push?.anims ?? [])]};
      watchPageFlight(pageFlight, () => { if (!closing) endPageFlight(); });
    }
    if (options.manual) $('.presetio-manual').scrollIntoView({block: 'start'});
    run(async () => { renderCatalogue(await request(fetcher)); message('choose'); });
  }
  entry.addEventListener('click', () => open(entry));
  renderCatalogue(catalogue);
  paintLanguage();
  addEventListener('dp-lang', paintLanguage);
  current = {sheet, load, close, open};
  dispatchEvent(new Event('dp-presets-ready'));
  return current;
}
