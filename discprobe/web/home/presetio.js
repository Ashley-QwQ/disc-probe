// The sheet delegates all parsing, geometry and filesystem work to the shared core.
import { hasCapability } from "./handshake.mjs";
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
export function open(from) { if (!current) return false; current.open(from); return true; }

// Scene-pixel coordinates from presetio/desk/desk.json. Kept local so this sheet
// also works from file URLs; the browser test checks these against the art metadata.
const desk = {
  width: 2560, height: 1440, knob: [2092, 539.8], travel: 187.2, plateLeft: 1984.7,
  leds: {export: [2022.4, 358.97, 9.9], import: [2022.4, 744.75, 9.9]},
  paper: [1090.05, 220.75, 1791.85, 1219.25], envelope: [1087.15, 595.19, 1794.75, 1366.75]
};
const stateName = value => value < 0 ? 'export' : value > 0 ? 'import' : 'idle';
const translate = y => `translateY(${y}px)`;

export async function init(entry, fetcher = fetch) {
  let catalogue;
  entry.hidden = true;
  if (!hasCapability('presets-io')) return null;          // the handshake says this core has no /api/presets
  try { catalogue = await request(fetcher); } catch { return null; } // old server: no dead entry
  if (catalogue.version !== 1) return null;
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

  let value = 0, scale = 1, compact = false, playing = [], generation = 0, drag = null;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const instant = () => compact || reduced.matches || document.documentElement.dataset.motion === 'off';
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
    for (const name of ['doc_paper', 'doc_envelope']) $(`[data-art="${name}_shadow"]`).style.transform = 'none';
    sheet.dataset.playing = 'false'; announce();
  }
  function finish() {
    ++generation;
    // Finish the whole scheduled move, including delayed legs, before a new one.
    for (const animation of playing) animation.finish();
    settle();
    for (const animation of playing) animation.cancel();
    playing = [];
  }
  function move(next, releasePoint = null) {
    const from = value;
    // A drag already moved the knob's underlying style; preserve that release point.
    finish(); value = next; announce();
    if (instant()) { settle(); return; }
    const release = releasePoint ?? parts.knob.style.transform;
    parts.knob.style.transform = release;
    for (const content of Object.values(contents)) {
      if (content.contains(document.activeElement)) knob.focus({preventScroll: true});
      content.inert = true;
    }
    sheet.dataset.playing = 'true';
    const token = generation;
    const animate = (el, frames, delay, duration, easing = 'ease-out') => {
      const animation = el.animate(frames, {delay, duration, easing, fill: 'forwards'});
      playing.push(animation);
    };
    const slide = (el, a, b, delay, duration, easing) => animate(el,
      [{transform: typeof a === 'string' ? a : translate(a)}, {transform: typeof b === 'string' ? b : translate(b)}], delay, duration, easing);
    const fade = (el, a, b, delay, duration) => animate(el, [{opacity: a}, {opacity: b}], delay, duration);
    const accelerating = 'cubic-bezier(.55,0,.8,.2)', landing = 'cubic-bezier(.16,1,.3,1)';
    const reverseLanding = 'cubic-bezier(.7,0,.84,0)', reverseAcceleration = 'cubic-bezier(.2,.8,.45,1)';
    const liftedShadow = 'translate(-18px, 24px) scale(1.035)';
    let time = 0, start = release;
    if (from && from !== next) {
      const name = stateName(from), doc = from < 0 ? 'doc_envelope' : 'doc_paper';
      const source = from < 0 ? 'bag' : 'sheets';
      slide(parts.knob, start, 0, 0, 220); start = translate(0);
      fade(leds[name], 1, 0, 0, 150);
      fade(contents[name], 1, 0, 220, 180);
      // Reverse the flight timeline: document first, source returning 380ms later.
      slide(parts[doc], 0, from < 0 ? desk.height : -desk.height, 400, 760, reverseLanding);
      animate($(`[data-art="${doc}_shadow"]`), [{transform: 'none'}, {transform: liftedShadow}], 400, 760, reverseLanding);
      slide(parts[source], from < 0 ? desk.height : -desk.height, 0, 780, 520, reverseAcceleration);
      time = 1300;
    }
    if (next && from !== next) {
      const name = stateName(next), doc = next < 0 ? 'doc_envelope' : 'doc_paper';
      const source = next < 0 ? 'bag' : 'sheets';
      slide(parts.knob, start, next * desk.travel, time, 220);
      fade(leds[name], 0, 1, time + 220, 150);
      slide(parts[source], 0, next < 0 ? desk.height : -desk.height, time + 220, 520, accelerating);
      slide(parts[doc], next < 0 ? desk.height : -desk.height, 0, time + 360, 760, landing);
      const shadow = $(`[data-art="${doc}_shadow"]`);
      shadow.style.transform = liftedShadow;
      animate(shadow, [{transform: liftedShadow}, {transform: 'none'}], time + 360, 760, landing);
      fade(contents[name], 0, 1, time + 1120, 180);
    } else if (from === next) {
      slide(parts.knob, start, next * desk.travel, 0, 220);
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
  reduced.addEventListener('change', () => { if (instant()) finish(); });
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
    finish(); knob.setPointerCapture(event.pointerId); knob.focus({preventScroll: true});
    drag = {id: event.pointerId, y: event.clientY, start: value * desk.travel, offset: value * desk.travel};
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
  let preview = null, upload = null, busy = false, revision = 0, lastFile = null;
  function message(text, error = false) { status.textContent = text; status.dataset.error = String(error); }
  function buttons() {
    $('[data-import]').disabled = busy || !preview || !selectedIndexes(preview.entries,
      new Set([...checkboxes].filter(([, box]) => box.checked).map(([i]) => i))).length;
    for (const name of ['install', 'save']) $(`[data-${name}]`).disabled = busy || !$('[data-presets]').value;
    $('input[type=file]').disabled = busy; $('[data-media]').disabled = busy;
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
    preview = upload = null; checkboxes.clear(); $('[data-rows]').replaceChildren(); buttons();
    if (file.size > 2 * 1024 * 1024) { message('文件超过 2 MiB / File exceeds 2 MiB', true); return; }
    await run(async () => {
      const text = await file.text();
      const payload = {operation: 'preview', text, filename: file.name, media: $('[data-media]').value || null};
      const result = await request(fetcher, payload);
      if (current !== revision) return;
      preview = result; upload = payload;
      for (const row of result.entries) {
        const block = document.createElement('div'); block.className = 'presetio-row';
        const label = document.createElement('label'), box = document.createElement('input');
        box.type = 'checkbox'; box.disabled = !row.valid; box.checked = row.valid && !row.disabled;
        box.addEventListener('change', buttons); checkboxes.set(row.index, box);
        const name = document.createElement('strong'); name.textContent = row.preset?.displayName || '无效预设 / Invalid preset';
        label.append(box, name);
        const summary = document.createElement('p'); summary.className = 'presetio-data'; summary.textContent = rowSummary(row);
        const issues = document.createElement('ul');
        row.issues.forEach((issue, i) => { const li = document.createElement('li');
          const zh = row.issues_zh?.[i]; li.textContent = zh && zh !== issue ? `${zh} / ${issue}` : issue; issues.append(li); });
        if (row.comparison) {
          const li = document.createElement('li');
          li.textContent = `近似：角度 ≤ ${row.comparison.max_angle_error_deg.toPrecision(6)}°，半径 ≤ ${row.comparison.max_radius_error_mm.toPrecision(6)} mm / DP approximation`;
          issues.append(li);
        }
        block.append(label, summary, issues); $('[data-rows]').append(block);
      }
      message(result.entries.length ? '核对参数并勾选要导入的预设。/ Review the values and select presets to import.' : '文件中没有预设 / No presets in this file');
    });
  }
  $('input[type=file]').addEventListener('change', event => load(event.target.files[0]));
  $('[data-media]').addEventListener('change', () => load(lastFile));
  const drop = $('.presetio-drop');
  drop.addEventListener('dragover', event => { event.preventDefault(); drop.dataset.over = 'true'; });
  drop.addEventListener('dragleave', () => { drop.dataset.over = 'false'; });
  drop.addEventListener('drop', event => { event.preventDefault(); drop.dataset.over = 'false'; if (!busy) load(event.dataTransfer.files[0]); });
  $('[data-import]').addEventListener('click', () => run(async () => {
    const selected = selectedIndexes(preview.entries, new Set([...checkboxes].filter(([, box]) => box.checked).map(([i]) => i)));
    const result = await request(fetcher, {...upload, operation: 'import', selected});
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
  function close() { finish(); drag = null; sheet.hidden = true; (opener?.isConnected ? opener : entry).focus(); }
  $('[data-close]').addEventListener('click', close);
  sheet.addEventListener('keydown', event => { event.stopPropagation(); if (event.key === 'Escape') { event.preventDefault(); close(); } });
  let opener = entry;
  function open(from = entry) {
    finish(); value = 0; opener = from; sheet.hidden = false; layout(); $('#presetio-title').focus();
    run(async () => { renderCatalogue(await request(fetcher)); message('选择文件或预设。/ Choose a file or preset.'); });
  }
  entry.addEventListener('click', () => open(entry));
  renderCatalogue(catalogue);
  current = {sheet, load, close, open};
  return current;
}
