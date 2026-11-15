// Translate CLI jobs; Python owns the fit, independent checks and save gate.
import { node, words } from './kit/shared.js';

const REASONS = {
  independent_error_exceeded: '独立验证误差超限。请减小改动或重新测量；原结果未改。',
  need_4_unique_independent_checks: '独立检查点不足，请重新测量后再修正。',
  validation_overlaps_fit_or_fit_ids_missing: '验证数据与拟合数据没有可靠分离，请重新测量。',
  independent_checks_do_not_cover_range: '独立检查点未覆盖内、中、外圈，请补测。',
  stale_evidence: '测量证据已改变，请重新打开辅助修正。',
  'stale_automatic_result: reopen the editor': '自动结果已改变，请重新打开辅助修正。',
};
export const reasonWords = (reason, lang) => lang === 'en' ? reason : REASONS[reason] || `暂时不能修正，请检查测量文件并重新读取。原因：${reason}`;

export function curveEditor(host, {run, job, lang = 'zh', state = {}, onSaved = () => {}, onBusy = () => {}}) {
  const doc = host.ownerDocument, t = (zh, en) => words(lang, zh, en);
  const root = node(doc, 'details', 'cal-details curve-edit');
  root.open = !!state.open;
  root.append(node(doc, 'summary', '', t('辅助修正', 'Assisted correction')));
  const body = node(doc, 'div', 'curve-edit-body'); root.append(body); host.append(root);
  let pending = false;
  root.addEventListener('toggle', () => {
    state.open = root.open;
    if (root.open && !state.loaded && !pending) load();
  });
  function button(text, action) {
    const el = node(doc, 'button', 'placed', text); el.type = 'button';
    el.disabled = pending; el.addEventListener('click', action); return el;
  }
  function chart(plot) {
    if (!plot) return;
    const svg = doc.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 560 220'); svg.setAttribute('role', 'img');
    const title = doc.createElementNS(svg.namespaceURI, 'title');
    title.textContent = t('半径与 φ 曲线：实线自动，虚线重拟合', 'Radius and phi: solid automatic, dashed refitted'); svg.append(title);
    const r = plot.radius_mm, all = [...plot.automatic_deg, ...plot.candidate_deg];
    const min = Math.min(...all) - .1, max = Math.max(...all) + .1;
    const x = v => 58 + (v - r[0]) / (r.at(-1) - r[0]) * 480;
    const y = v => 168 - (v - min) / (max - min) * 146;
    function element(tag, attrs, text) {
      const el = doc.createElementNS(svg.namespaceURI, tag);
      for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
      if (text) el.textContent = text; svg.append(el);
    }
    element('path', {d:'M58 22V168H538', class:'curve-axis'});
    for (const [values, name] of [[plot.automatic_deg, 'curve-auto'], [plot.candidate_deg, 'curve-candidate']])
      element('polyline', {points:values.map((v, i) => `${x(r[i])},${y(v)}`).join(' '), class:name});
    element('text', {x:58,y:190}, r[0].toFixed(2));
    element('text', {x:538,y:190,'text-anchor':'end'}, r.at(-1).toFixed(2));
    element('text', {x:298,y:214,'text-anchor':'middle'}, t('半径 r / mm', 'Radius r / mm'));
    element('text', {x:4,y:16}, 'φ / °');
    element('text', {x:50,y:30,'text-anchor':'end'}, max.toFixed(2));
    element('text', {x:50,y:168,'text-anchor':'end'}, min.toFixed(2));
    body.append(svg, node(doc, 'p', 'curve-legend', t('实线：自动 φ　虚线：重拟合 φ', 'Solid: automatic phi · Dashed: refitted phi')));
  }
  function paint() {
    body.replaceChildren(); root.setAttribute('aria-busy', String(pending));
    if (!state.edit) {
      body.append(node(doc, 'p', '', state.message || t('读取本次自动曲线；参考环和沿轨常数保持原值。', 'Load this measurement’s automatic curve.')));
      body.append(button(pending ? t('读取中…', 'Loading…') : t('读取自动曲线', 'Load automatic curve'), load)); return;
    }
    body.append(node(doc, 'p', '', t('数据面看逆时针为正，φ 单位度。控制点拟合平滑偏移，半径范围沿用自动结果。', 'Phi is in degrees, counter-clockwise in data-side view. Controls fit a smooth offset within the automatic range.')));
    chart(state.result?.plot || state.plot);
    const table = node(doc, 'table', 'curve-controls'), heading = node(doc, 'tr'), thead = node(doc, 'thead');
    for (const text of [t('半径 / mm', 'Radius / mm'), t('φ 偏移 / °', 'Phi offset / °')]) heading.append(node(doc, 'th', '', text));
    thead.append(heading); table.append(thead);
    const tbody = node(doc, 'tbody'); table.append(tbody);
    state.edit.controls.forEach((point, index) => {
      const row = node(doc, 'tr'); row.append(node(doc, 'td', '', point.radius_mm.toFixed(3)));
      const cell = node(doc, 'td'), input = node(doc, 'input');
      input.type = 'number'; input.step = '0.05'; input.value = point.delta_deg;
      input.setAttribute('aria-label', t(`${point.radius_mm.toFixed(3)} mm 处的角度偏移`, `Angle offset at ${point.radius_mm.toFixed(3)} mm`));
      input.disabled = pending; input.dataset.control = index;
      input.addEventListener('input', () => {
        point.delta_deg = input.value === '' ? null : Number(input.value); state.validated = false;
        state.message = t('修改中：请重拟合并验证。虚线仍是上次计算。', 'Editing: refit and validate. Dashed curve is from the previous calculation.');
        status.textContent = state.message; status.dataset.passed = 'false'; save.disabled = true;
      });
      cell.append(input); row.append(cell); tbody.append(row);
    });
    body.append(table);
    const status = node(doc, 'p', 'curve-status', pending ? t('正在重拟合并检查独立数据…', 'Refitting and checking independent data…') : state.message || t('自动曲线已读取，尚未保存人工改动。', 'Automatic curve loaded. No manual edit saved.'));
    status.setAttribute('role', 'status'); status.dataset.passed = String(!!state.validated); body.append(status);
    const actions = node(doc, 'div', 'curve-actions'); actions.append(button(t('重拟合并验证', 'Refit and validate'), () => submit(false)));
    const save = button(t('保存修正', 'Save correction'), () => submit(true));
    save.disabled = pending || !state.validated; actions.append(save, button(t('重新读取', 'Reload'), load)); body.append(actions);
    const details = node(doc, 'details'); details.append(node(doc, 'summary', '', t('验证详情 / CLI', 'Validation details / CLI')));
    details.append(node(doc, 'pre', '', `python -m discprobe curve-edit --run ${JSON.stringify(run)}\n` + JSON.stringify(state.result?.validation || {}, null, 2))); body.append(details);
  }
  async function call(args) {
    try { return await job({action:'curve-edit', args:{run, ...args}}); }
    catch (error) { if (error.result?.validation) return error.result; throw error; }
  }
  async function load() {
    if (pending) return; pending = true; state.validated = false; onBusy(true); paint();
    try {
      const result = await call({}); state.loaded = true; state.edit = result.edit; state.result = result; state.plot = result.plot; state.validated = false;
      state.message = result.edit ? t('自动曲线已读取。改动后需重拟合并独立验证。', 'Automatic curve loaded. Edits require refitting and independent validation.') : reasonWords(result.validation?.reason || 'no_automatic_curve', lang);
    } catch (error) { state.message = t('读取失败，请检查后端并重试：', 'Could not load. Check the backend and retry: ') + error.message; }
    finally { pending = false; onBusy(false); paint(); }
  }
  async function submit(save) {
    if (pending || save && !state.validated) return;
    if (state.edit.controls.some(p => p.delta_deg === null || !Number.isFinite(p.delta_deg))) {
      state.message = t('每个偏移都需要有效数字。', 'Enter a finite number for every offset.'); state.validated = false; paint(); return;
    }
    pending = true; onBusy(true); paint();
    try {
      const {automatic, ...controls} = structuredClone(state.edit);
      const result = await call({edit_json:controls, ...(save ? {save:true} : {})});
      state.result = result; if (result.plot) state.plot = result.plot; state.validated = !!result.ok && !result.saved;
      const v = result.validation;
      state.message = result.saved ? t('修正已保存。继续保存测量以重新导出预设。', 'Correction saved. Save the measurement to export the preset again.') : result.ok
        ? t(`独立验证通过：${v.count} 点，RMS ${v.rms_deg.toFixed(3)}°，最大 ${v.max_deg.toFixed(3)}°。`, `Independent validation passed: ${v.count} points, RMS ${v.rms_deg.toFixed(3)}°, max ${v.max_deg.toFixed(3)}°.`)
        : reasonWords(v?.reason || 'unknown', lang);
      if (result.saved) onSaved(result);
    } catch (error) { state.validated = false; state.message = t('后端任务未完成，请重试：', 'Backend job did not finish. Retry: ') + error.message; }
    finally { pending = false; onBusy(false); paint(); }
  }
  paint(); if (state.open && !state.loaded) load();
  return {root, state};
}
