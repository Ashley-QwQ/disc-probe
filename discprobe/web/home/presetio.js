// The sheet delegates all parsing, geometry and filesystem work to the shared core.
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

export function rowSummary(row) {
  const p = row.preset || {};
  return `${row.media.toUpperCase()} · ${p.id ?? '?'} · ${p.sectors ?? p.totalSectors ?? '?'} sectors · ` +
    `${p.innerRadiusMm ?? '?'}–${p.outerRadiusMm ?? '?'} mm · ` +
    `pitch ${p.pitchLinear ?? 0}, ${p.pitchQuadratic ?? 0}, ${p.pitchCubic ?? 0} · MID ${row.mid ?? '?'}`;
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
  sheet.innerHTML = `<button type="button" class="presetio-close" data-close>关闭 / Close</button>
    <h2 class="presetio-title" id="presetio-title" tabindex="-1">预设 · DiscImageStudio <small lang="en">/ Presets</small></h2>
    <div class="presetio-scene presetio-paper">
    <div class="presetio-tabs" role="tablist" aria-label="预设 / Presets">
      <button type="button" role="tab" id="presetio-tab-import" aria-controls="presetio-import" data-tab="1">导入 / Import</button>
      <button type="button" role="tab" id="presetio-tab-export" aria-controls="presetio-export" data-tab="-1">导出 / Export</button>
    </div>
    <div class="presetio-stage">
    ${art('base')}${layer('bag')}${art('upper')}${layer('sheets')}
    <div class="presetio-writing">
      <button type="button" data-move="-1">导出数据 <small lang="en">Export</small></button>
      <span class="presetio-tick" aria-hidden="true"></span>
      <button type="button" data-move="1">导入数据 <small lang="en">Import</small></button>
    </div>
    <div class="presetio-layer" data-layer="knob">${art('knob_shadow')}${art('knob')}
      <div class="presetio-knob" role="slider" tabindex="0" aria-label="导入或导出 / Import or export"
        aria-orientation="vertical" aria-valuemin="-1" aria-valuemax="1" aria-valuenow="0" aria-valuetext="空 / Idle"></div>
    </div>
    <span class="presetio-led" data-led="export" aria-hidden="true"></span><span class="presetio-led" data-led="import" aria-hidden="true"></span>
    <div class="presetio-layer presetio-document" data-layer="doc_paper">${art('doc_paper_shadow')}${art('doc_paper')}
    <article class="presetio-content" id="presetio-import" aria-labelledby="presetio-import-title" inert>
    <header><h3 id="presetio-import-title">导入 DIS 预设 <small lang="en">Import DIS presets</small></h3></header>
    <div class="presetio-drop"><label class="presetio-file"><input type="file" accept=".json,application/json"><span class="presetio-pick">选择文件 / Choose file</span><span class="presetio-hint" data-filename>或把 DIS 的 JSON 拖到这里 / or drop a DIS JSON here</span></label></div>
    <label>单个预设的盘种 / Standalone media <select data-media><option value="">自动识别 / Automatic (CD, DVD)</option><option value="cd">CD</option><option value="dvd">DVD</option><option value="bd">Blu-ray</option></select></label>
    <details class="presetio-manual"><summary>手动填写参数 / Type the parameters</summary>
      <form data-manual novalidate>
        <div class="presetio-fields">
        ${[['displayName', '名称 / Name', 'text'], ['media', '盘种 / Media', 'select'],
          ['innerRadiusMm', '内半径 / Inner radius (mm)', 'number'], ['outerRadiusMm', '外半径 / Outer radius (mm)', 'number'],
          ['sectors', '扇区数 / Sector count', 'number'], ['pitchLinear', '轨距线性项 / Pitch linear', 'number'],
          ['pitchQuadratic', '轨距二次项 / Pitch quadratic', 'number'], ['pitchCubic', '轨距三次项 / Pitch cubic', 'number']]
          .map(([name, label, type]) => `<label>${label}${type === 'select'
            ? `<select name="media"><option value="cd">CD</option><option value="dvd">DVD</option></select>`
            : `<input name="${name}" type="${type}" ${type === 'number' ? `step="${name === 'sectors' ? '1' : 'any'}"` : ''} ${name.startsWith('pitch') ? 'value="0"' : 'required'} aria-describedby="presetio-error-${name}">`}
            <small class="presetio-field-error" id="presetio-error-${name}" data-error="${name}"></small></label>`).join('')}
        </div>
        <p class="presetio-hint">轨距三项可不填，默认为 0。/ Pitch terms are optional; default 0.</p>
        <button type="submit" data-preview>核对参数 / Preview parameters</button>
      </form>
    </details>
    <div data-rows></div><div class="presetio-actions"><button type="button" data-import class="presetio-primary" disabled>导入 / Import</button></div>
    <p role="status" aria-live="polite" class="presetio-status"></p></article></div>
    <div class="presetio-layer presetio-document" data-layer="doc_envelope">${art('doc_envelope_shadow')}${art('doc_envelope')}
    <article class="presetio-content" id="presetio-export" aria-labelledby="presetio-export-title" inert>
    <header><h3 id="presetio-export-title">导出到 DIS <small lang="en">Export to DIS</small></h3></header>
    <label>选择 DP 预设 / Choose a DP preset<select data-presets></select></label>
    <div class="presetio-actions"><button type="button" data-install class="presetio-primary">写进 DiscImageStudio / Write to DiscImageStudio</button><button type="button" data-save>存成文件 / Save as file</button></div>
    </article></div></div></div>`;
  document.body.append(sheet);
  const $ = selector => sheet.querySelector(selector);
  const stage = $('.presetio-stage'), knob = $('.presetio-knob');
  const parts = Object.fromEntries([...sheet.querySelectorAll('[data-layer]')].map(el => [el.dataset.layer, el]));
  const contents = {import: $('#presetio-import'), export: $('#presetio-export')};
  const leds = {import: $('[data-led="import"]'), export: $('[data-led="export"]')};
  const status = $('.presetio-status');
  const rect = (el, [left, top, right, bottom]) => Object.assign(el.style,
    {left: `${left}px`, top: `${top}px`, width: `${right - left}px`, height: `${bottom - top}px`});
  rect(contents.import, desk.paper); rect(contents.export, desk.envelope);
  rect(knob, [desk.knob[0] - 48, desk.knob[1] - 48, desk.knob[0] + 48, desk.knob[1] + 48]);
  for (const [name, [x, y, radius]] of Object.entries(desk.leds)) {
    rect(leds[name], [x - radius * .65, y - radius * .65, x + radius * .65, y + radius * .65]);
    const label = $(`[data-move="${name === 'export' ? -1 : 1}"]`);
    label.style.top = `${y}px`; label.style.right = `${desk.width - desk.plateLeft + 70}px`;
    // the leader stops short of the plate (to the LED it read as reaching into the plate's depth)
    label.style.setProperty('--leader', `${70 - 12 - 18}px`);
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
    knob.setAttribute('aria-valuetext', value < 0 ? '导出 / Export' : value > 0 ? '导入 / Import' : '空 / Idle');
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
    compact = innerWidth < 820 || innerWidth / innerHeight < 1.2;
    sheet.dataset.compact = String(compact);
    scale = Math.max(innerWidth / desk.width, innerHeight / desk.height);
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
  let preview = null, upload = null, busy = false, revision = 0, lastFile = null, callbacks = {};
  function message(text, error = false) { status.textContent = text; status.dataset.error = String(error); }
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
      const option = document.createElement('option'); option.value = ''; option.textContent = '还没有预设 / No saved presets';
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
    busy = true; buttons(); message('处理中… / Working…');
    try { await action(); } catch (error) { message(`${error.message}\n请检查文件或选择后重试。/ Check the file or selection and retry.`, true); }
    finally { busy = false; buttons(); }
  }
  async function load(file) {
    if (!file) return;
    lastFile = file; $('[data-filename]').textContent = file.name;
    const current = ++revision;
    clearPreview(); clearFieldErrors();
    if (file.size > 2 * 1024 * 1024) { message('文件超过 2 MiB / File exceeds 2 MiB', true); return; }
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
    preview = upload = null; checkboxes.clear(); $('[data-rows]').replaceChildren(); buttons();
  }
  function clearFieldErrors() {
    for (const el of sheet.querySelectorAll('[data-error]')) el.textContent = '';
    for (const el of $('[data-manual]').elements) el.removeAttribute('aria-invalid');
  }
  function fieldErrors(issues) {
    for (const issue of issues) {
      const keys = /radii|RadiusMm/.test(issue) ? ['innerRadiusMm', 'outerRadiusMm']
        : /pitch/.test(issue) ? ['pitchLinear', 'pitchQuadratic', 'pitchCubic']
        : /sectors|totalSectors/.test(issue) ? ['sectors'] : /displayName|description/.test(issue) ? ['displayName'] : [];
      for (const key of keys) {
        $(`[data-error="${key}"]`).textContent = issue;
        $('[data-manual]').elements.namedItem(key).setAttribute('aria-invalid', 'true');
      }
    }
  }
  function showPreview(result, manual = false) {
      for (const row of result.entries) {
        const block = document.createElement('div'); block.className = 'presetio-row';
        const label = document.createElement('label'), box = document.createElement('input');
        box.type = 'checkbox'; box.disabled = !row.valid; box.checked = row.valid && !row.disabled;
        box.addEventListener('change', buttons); checkboxes.set(row.index, box);
        const name = document.createElement('strong'); name.textContent = row.preset?.displayName || '无效预设 / Invalid preset';
        label.append(box, name);
        const summary = document.createElement('p'); summary.className = 'presetio-data'; summary.textContent = rowSummary(row);
        if (row.valid && row.image_compatible === false) summary.textContent += ' · 仅存档，DP 不能用来做图 / Archive only; unavailable for DP drawing';
        const issues = document.createElement('ul');
        row.issues.forEach((issue, i) => { const li = document.createElement('li');
          const zh = row.issues_zh?.[i]; li.textContent = zh && zh !== issue ? `${zh} / ${issue}` : issue; issues.append(li); });
        if (row.comparison) {
          const li = document.createElement('li');
          li.textContent = `近似：角度 ≤ ${row.comparison.max_angle_error_deg.toPrecision(6)}°，半径 ≤ ${row.comparison.max_radius_error_mm.toPrecision(6)} mm / DP approximation`;
          issues.append(li);
        }
        block.append(label, summary, issues); $('[data-rows]').append(block);
        if (manual && !row.valid) fieldErrors(row.issues.map((issue, i) => {
          const zh = row.issues_zh?.[i]; return zh && zh !== issue ? `${zh} / ${issue}` : issue;
        }));
      }
      message(result.entries.length ? '核对参数并勾选要导入的预设。/ Review the values and select presets to import.' : '文件中没有预设 / No presets in this file');
  }
  $('[data-manual]').addEventListener('input', () => { ++revision; clearPreview(); clearFieldErrors(); message('参数已修改，请重新核对。/ Values changed; preview again.'); });
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
    await onImported?.(result);
    renderCatalogue(await request(fetcher));
    message(`已导入 / Imported: ${result.written.length}；重复项保留 / Duplicates kept: ${result.duplicates.length}`);
  }));
  for (const install of [true, false]) $(`[data-${install ? 'install' : 'save'}]`).addEventListener('click', () => run(async () => {
    const result = await request(fetcher, {operation: 'export', path: $('[data-presets]').value, install});
    if (install) message(`已写入，请重启 DIS。/ Written; restart DIS.\n${result.installation.path}\n备份 / Backup: ${result.installation.backup || '—'}`);
    else {
      const blob = new Blob([JSON.stringify(result.preset, null, 2) + '\n'], {type: 'application/json'});
      const url = URL.createObjectURL(blob), link = document.createElement('a'); link.href = url;
      link.download = 'dis-preset.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      message('已保存 DIS 预设 / Saved DIS preset');
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
    run(async () => { renderCatalogue(await request(fetcher)); message('选择文件或预设。/ Choose a file or preset.'); });
  }
  entry.addEventListener('click', () => open(entry));
  renderCatalogue(catalogue);
  current = {sheet, load, close, open};
  dispatchEvent(new Event('dp-presets-ready'));
  return current;
}
