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

// Display bounds only; the CLI still owns fitting and validation.
function curveTicks(values) {
  const lo = Math.min(0, ...values) - .1, hi = Math.max(0, ...values) + .1;
  const power = 10 ** Math.floor(Math.log10((hi - lo) / 3)), choices = [];
  for (const scale of [.1, 1, 10]) for (const factor of [1, 2, 5]) {
    const step = power * scale * factor;
    const first = Math.floor(lo / step), last = Math.ceil(hi / step), count = last - first + 1;
    if (count >= 3 && count <= 5) choices.push({step, first, count, span:(count - 1) * step});
  }
  const best = choices.sort((a, b) => a.span - b.span || Math.abs(a.count - 4) - Math.abs(b.count - 4))[0];
  return {step:best.step, values:Array.from({length:best.count}, (_, i) => Number(((best.first + i) * best.step).toPrecision(12)))};
}
const tickText = (value, step) => value.toFixed(Math.max(0, -Math.floor(Math.log10(step))));
const metricText = value => Number(value.toFixed(3)).toString();

export function curveEditor(host, {run, job, lang = 'zh', state = {}, onSaved = () => {}, onBusy = () => {}}) {
  const doc = host.ownerDocument, t = (zh, en) => words(lang, zh, en);
  const root = node(doc, 'details', 'cal-details curve-edit');
  root.open = !!state.open;
  root.append(node(doc, 'summary', '', t('辅助修正', 'Assisted correction')));
  const body = node(doc, 'div', 'curve-edit-body'); root.append(body); host.append(root);
  let pending = false, failed = false;
  root.addEventListener('toggle', () => {
    state.open = root.open;
    if (root.open && !state.loaded && !pending) load();
  });
  function button(text, action) {
    const el = node(doc, 'button', 'kit-ring-button', text); el.type = 'button';
    el.disabled = pending; el.addEventListener('click', action); return el;
  }
  function chart(plot) {
    if (!plot) return;
    const svg = doc.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 560 280'); svg.setAttribute('role', 'img');
    const title = doc.createElementNS(svg.namespaceURI, 'title');
    title.textContent = t('半径与 φ 曲线：实线自动，虚线重拟合', 'Radius and phi: solid automatic, dashed refitted'); svg.append(title);
    const r = plot.radius_mm, all = [...plot.automatic_deg, ...plot.candidate_deg];
    const ticks = curveTicks(all), min = ticks.values[0], max = ticks.values.at(-1);
    const x = v => 68 + (v - r[0]) / (r.at(-1) - r[0]) * 470;
    const y = v => 216 - (v - min) / (max - min) * 148;
    function element(tag, attrs, text) {
      const el = doc.createElementNS(svg.namespaceURI, tag);
      for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
      if (text) el.textContent = text; svg.append(el);
    }
    element('path', {d:'M68 68V216H538', class:'curve-axis'});
    for (const value of ticks.values) {
      element('path', {d:`M62 ${y(value)}H68`, class:'curve-axis'});
      element('text', {x:58,y:y(value),'text-anchor':'end','dominant-baseline':'middle',class:'curve-y-tick'}, tickText(value, ticks.step));
    }
    element('path', {d:`M68 ${y(0)}H538`,class:'curve-zero'});
    const radiusStep = r.at(-1) - r[0] <= 40 ? 5 : 10;
    for (let value = Math.ceil(r[0] / radiusStep) * radiusStep; value <= r.at(-1); value += radiusStep) {
      element('path', {d:`M${x(value)} 216v6`,class:'curve-axis'});
      element('text', {x:x(value),y:242,'text-anchor':'middle',class:'curve-x-tick'}, tickText(value, radiusStep));
    }
    for (const [values, name] of [[plot.automatic_deg, 'curve-auto'], [plot.candidate_deg, 'curve-candidate']])
      element('polyline', {points:values.map((v, i) => `${x(r[i])},${y(v)}`).join(' '), class:name});
    element('text', {x:303,y:272,'text-anchor':'middle',class:'curve-axis-title'}, t('半径 / mm', 'Radius / mm'));
    element('text', {x:4,y:24,class:'curve-axis-title'}, t('φ 偏转 / °', 'φ deflection / °'));
    const legend = doc.createElementNS(svg.namespaceURI, 'g'); legend.setAttribute('class', 'curve-legend');
    for (const [name, label, at] of [['curve-auto', t('自动 φ', 'Auto φ'), 20], ['curve-candidate', t('重拟合 φ', 'Refit φ'), 46]]) {
      element('path', {d:`M414 ${at}h32`,class:name}); legend.append(svg.lastChild);
      element('text', {x:456,y:at,'dominant-baseline':'middle'}, label); legend.append(svg.lastChild);
    }
    svg.append(legend); body.append(svg);
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
    for (const text of [t('半径 / mm', 'Radius / mm'), t('φ 偏移', 'Phi offset')]) {
      const th = node(doc, 'th', '', text); th.scope = 'col'; heading.append(th);
    }
    thead.append(heading); table.append(thead);
    const tbody = node(doc, 'tbody'); table.append(tbody);
    state.edit.controls.forEach((point, index) => {
      const row = node(doc, 'tr'); row.dataset.modified = String(point.delta_deg !== 0);
      row.append(node(doc, 'td', '', point.radius_mm.toFixed(3)));
      const cell = node(doc, 'td'), input = node(doc, 'input');
      input.type = 'number'; input.step = '0.05'; input.value = point.delta_deg;
      input.setAttribute('aria-label', t(`${point.radius_mm.toFixed(3)} mm 处的角度偏移`, `Angle offset at ${point.radius_mm.toFixed(3)} mm`));
      input.disabled = pending; input.dataset.control = index;
      input.addEventListener('input', () => {
        point.delta_deg = input.value === '' ? null : Number(input.value); state.validated = false;
        const count = state.edit.controls.filter(p => p.delta_deg !== 0).length;
        state.message = t(`改了 ${count} 个点，还没验证。图里虚线是上次的计算。`, `${count} points changed, not validated yet. Dashed curve is from the previous calculation.`);
        row.dataset.modified = String(point.delta_deg !== 0); failed = false;
        status.textContent = state.message; status.dataset.passed = 'false'; status.dataset.failed = 'false'; save.disabled = true; saveHelp.hidden = false;
      });
      const unit = node(doc, 'span', 'curve-unit', '°'); unit.setAttribute('aria-hidden', 'true');
      cell.append(input, unit); row.append(cell); tbody.append(row);
    });
    body.append(table);
    const status = node(doc, 'p', 'curve-status', pending ? t('正在重拟合并检查独立数据…', 'Refitting and checking independent data…') : state.message || t('自动曲线已读取，尚未保存人工改动。', 'Automatic curve loaded. No manual edit saved.'));
    status.setAttribute('role', 'status'); status.dataset.passed = String(!!state.validated); status.dataset.failed = String(failed && !pending); body.append(status);
    const actions = node(doc, 'div', 'curve-actions');
    const refit = button(t('重拟合并验证', 'Refit and validate'), () => submit(false)); refit.classList.add('curve-primary'); actions.append(refit);
    const save = button(t('保存修正', 'Save correction'), () => submit(true));
    const saveGroup = node(doc, 'div', 'curve-save');
    const saveHelp = node(doc, 'small', 'curve-save-help', t('先通过验证才能保存', 'Pass validation before saving'));
    save.disabled = pending || !state.validated; saveHelp.hidden = !save.disabled;
    saveGroup.append(save, saveHelp);
    const reload = button(t('重新读取', 'Reload'), load); reload.className = 'kit-text-button';
    actions.append(saveGroup, reload); body.append(actions);
    const details = node(doc, 'details'); details.append(node(doc, 'summary', '', t('验证详情 / CLI', 'Validation details / CLI')));
    details.append(node(doc, 'pre', '', `python -m discprobe curve-edit --run ${JSON.stringify(run)}\n` + JSON.stringify(state.result?.validation || {}, null, 2))); body.append(details);
  }
  async function call(args) {
    try { return await job({action:'curve-edit', args:{run, ...args}}); }
    catch (error) { if (error.result?.validation) return error.result; throw error; }
  }
  async function load() {
    if (pending) return; pending = true; failed = false; state.validated = false; onBusy(true); paint();
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
      failed = !result.ok;
      state.message = result.saved ? t('修正已保存。继续保存测量以重新导出预设。', 'Correction saved. Save the measurement to export the preset again.') : result.ok
        ? t(`独立验证通过：RMS ${metricText(v.rms_deg)}°，最大 ${metricText(v.max_deg)}°。可以保存。`, `Independent validation passed: RMS ${metricText(v.rms_deg)}°, max ${metricText(v.max_deg)}°. Ready to save.`)
        : v?.reason === 'independent_error_exceeded'
          ? t(`独立验证没通过：RMS ${metricText(v.rms_deg)}°（上限 ${metricText(v.rms_limit_deg)}°），最大 ${metricText(v.max_deg)}°（上限 ${metricText(v.max_limit_deg)}°）。原结果没有改。`, `Independent validation failed: RMS ${metricText(v.rms_deg)}° (limit ${metricText(v.rms_limit_deg)}°), max ${metricText(v.max_deg)}° (limit ${metricText(v.max_limit_deg)}°). Original result unchanged.`)
          : reasonWords(v?.reason || 'unknown', lang);
      if (result.saved) onSaved(result);
    } catch (error) { state.validated = false; state.message = t('后端任务未完成，请重试：', 'Backend job did not finish. Retry: ') + error.message; }
    finally { pending = false; onBusy(false); paint(); }
  }
  paint(); if (state.open && !state.loaded) load();
  return {root, state};
}
