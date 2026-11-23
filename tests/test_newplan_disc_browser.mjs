// Real /api/disc reads through Disc Lab. No physical drive or burn job is used.
import assert from 'node:assert/strict';
import {execFileSync, spawn} from 'node:child_process';
import {once} from 'node:events';
import {mkdir, mkdtemp, readFile, rm, rmdir, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {delimiter, dirname, join, resolve} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {fileURLToPath} from 'node:url';

const repo = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const temp = await mkdtemp(join(tmpdir(), 'newplan-disc-'));
const shots = process.env.NEWPLAN_SHOTS;
const onlyStarter = process.env.NEWPLAN_STARTER_ONLY === '1';
if (shots) await mkdir(shots, {recursive: true});
const python = process.env.PYTHON ?? 'python';
const edge = process.env.KIT_TEST_BROWSER ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const profile = join(temp, 'edge');
const cases = [
  {key: 'blank', lang: 'zh', theme: 'light', words: /空白盘.*RITEKF1/, disc: {kind: 'DVD-R Sequential', blank: true, mid: 'RITEKF1'}},
  {key: 'rom', lang: 'en', theme: 'dark', words: /finalized \(DVD-ROM\).*Swap in a blank/, disc: {kind: 'DVD-ROM', blank: false, closed: true}},
  {key: 'written', lang: 'zh', theme: 'dark', words: /已经刻过，尚未封盘.*换一张空白盘/, disc: {blank: false, closed: false}},
  {key: 'rw', lang: 'en', theme: 'light', words: /rewritable disc has data.*Erase it/, disc: {blank: false, rewritable: true}},
  {key: 'empty', lang: 'en', theme: 'light', words: /No disc in the drive/, disc: {present: false, tray: 'empty'}},
  {key: 'tray-open', lang: 'zh', theme: 'dark', words: /光驱托盘开着/, disc: {present: false, tray: 'open'}},
];

async function waitFor(probe, name) {
  const end = Date.now() + Number(process.env.BROWSER_WAIT_MS ?? 40000);
  while (Date.now() < end) {
    const value = await probe();
    if (value) return value;
    await delay(50);
  }
  throw Error(name);
}
let socket, seq = 0, browser, setupScript;
const pending = new Map();
function cdp(method, params = {}) {
  const id = ++seq;
  const result = new Promise((resolve, reject) => pending.set(id, {resolve, reject}));
  socket.send(JSON.stringify({id, method, params}));
  return result;
}
async function evaluate(expression) {
  const result = await cdp('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
  assert.ok(!result.exceptionDetails, result.exceptionDetails?.exception?.description ?? result.exceptionDetails?.text);
  return result.result.value;
}
async function until(expression, name) {
  try { return await waitFor(() => evaluate(expression), name); }
  catch (error) {
    const state = await evaluate(`({mode: document.documentElement.dataset.mode, title: document.title,
      errors: window.ndErrors, text: document.body?.innerText.slice(-1500)})`);
    throw Error(name + ': ' + JSON.stringify(state), {cause: error});
  }
}
const viewport = (width, height) => cdp('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 1, mobile: false});
async function click(selector) {
  const point = await evaluate(`(() => {
    const rect = document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();
    return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};
  })()`);
  await cdp('Input.dispatchMouseEvent', {...point, type: 'mousePressed', button: 'left', clickCount: 1});
  await cdp('Input.dispatchMouseEvent', {...point, type: 'mouseReleased', button: 'left', clickCount: 1});
}
async function capture(name) {
  if (!shots || onlyStarter && !name.startsWith('starter-')) return;
  await evaluate('document.fonts.ready');
  const result = await cdp('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
  await writeFile(join(shots, name + '.png'), Buffer.from(result.data, 'base64'));
}
async function stop(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  const closed = once(child, 'exit');
  child.kill();
  await closed;
}

async function runScene(scenario, verify) {
  const {key, lang, theme} = scenario;
  const root = join(temp, key);
  const localTemp = join(root, 'tmp');
  const scratch = {TEMP: temp, TMP: temp, TMPDIR: temp};
  let server, failed = true;
  try {
    execFileSync(python, ['-B', '-X', 'utf8', 'tests/newplan_lab_fixture.py', root, key], {
      cwd: repo, env: {...process.env, ...scratch}, windowsHide: true,
    });
    const history = JSON.parse(await readFile(join(root, 'history.json'), 'utf8'));
    await mkdir(localTemp);
    const paths = [join(repo, 'disclab', 'boot'), repo];
    if (key === 'rom') paths.unshift(join(root, 'boot'));
    const env = {...process.env, TEMP: localTemp, TMP: localTemp,
      DISCPROBE_HOME: root, DISCPROBE_DISCLAB: root, DISCLAB_ROOT: repo, DISC_PROBE_NO_DRIVES: '0',
      PYTHONPATH: paths.join(delimiter), PYTHONIOENCODING: 'utf-8', DISCPROBE_PLAIN: '1'};
    server = spawn(python, ['-B', '-X', 'utf8', '-m', 'discprobe', 'webui', '--new-instance',
      '--local-only', '--port', '0'], {cwd: root, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe']});
    let stdout = '', stderr = '';
    server.stdout.on('data', data => stdout += data);
    server.stderr.on('data', data => stderr += data);
    const url = await waitFor(() => {
      if (server.exitCode !== null) throw Error(stderr);
      return stdout.match(/http:\/\/127\.0\.0\.1:\d+\/home\/\?token=[\w-]+/)?.[0];
    }, key + ': Lab server did not answer');
    assert.notEqual(new URL(url).port, '8765');
    const state = await fetch(new URL('/api/state', url)).then(r => r.json());
    assert.deepEqual(state.drives.map(drive => drive.id), ['X:']);
    if (setupScript) await cdp('Page.removeScriptToEvaluateOnNewDocument', {identifier: setupScript});
    ({identifier: setupScript} = await cdp('Page.addScriptToEvaluateOnNewDocument', {source: `
      localStorage.setItem('dp-theme', ${JSON.stringify(theme)});
      localStorage.setItem('dp-lang', ${JSON.stringify(lang)});
      localStorage.setItem('dp-batch', ${JSON.stringify(history)});
      localStorage.setItem('dp-disc-kind', '["dvd","+R"]');
      window.ndErrors = [];
      addEventListener('error', event => ndErrors.push(event.message));
      addEventListener('unhandledrejection', event => ndErrors.push(String(event.reason)));
    `}));
    for (let attempt = 0; ; attempt++) {
      const nav = await cdp('Page.navigate', {url});
      assert.equal(nav.errorText, undefined, key + ': navigating to Lab WebUI');
      const startup = await until(`location.origin === ${JSON.stringify(new URL(url).origin)} &&
        (document.documentElement.dataset.navigation === "ready" &&
        !document.getElementById("next").disabled ? "ready" : window.ndErrors?.[0])`, key + ': lobby missing');
      if (startup === 'ready') break;
      if (attempt || !startup.includes('Failed to fetch dynamically imported module')) throw Error(startup);
      console.warn(key + ': retrying lobby startup after a module load error');
    }
    await evaluate('document.getElementById("next").click()');
    await until(`document.documentElement.dataset.mode === "newplan" &&
      ${scenario.words}.test(document.querySelector(".np-disc-help")?.textContent)`, key + ': drive status missing');
    const final = await fetch(new URL('/api/state', url)).then(r => r.json());
    for (const [field, value] of Object.entries(scenario.disc)) assert.equal(final.drives[0].disc[field], value, key);
    const form = await evaluate(`({
      dial: document.querySelector('.np-face-text').textContent,
      batch: document.querySelector('.np-batch').placeholder,
      next: !document.getElementById('next').disabled,
      theme: document.documentElement.dataset.theme,
      lang: document.documentElement.lang.split('-')[0]
    })`);
    assert.deepEqual(form, {
      dial: key === 'blank' ? 'DVD-R' : 'DVD+R',
      batch: key === 'blank' ? 'RITEKF1 DVD-R' : 'History DVD+R',
      next: true, theme, lang,
    });
    await capture(`${key}-${theme}-${lang}-1440`);
    await click('.np-batch');
    const choices = await evaluate(`[...document.querySelector('.np-matches').children].map(row => ({
      name: row.firstElementChild.textContent, info: row.querySelector('small')?.textContent ?? ''
    }))`);
    const later = lang === 'en' ? 'Choose later' : '稍后再定';
    const calibrated = lang === 'en' ? 'Calibrated' : '已标定';
    assert.deepEqual(choices.map(row => row.name), ['History DVD+R', 'RITEKF1 DVD-R', later]);
    assert.ok(choices[0].info.includes(`${calibrated} · 2026-11-08`) &&
              choices[1].info.includes(`${calibrated} · 2026-11-07`));
    assert.equal(await evaluate('document.querySelector(".np-batch").getAttribute("aria-expanded")'), 'true');
    if (['blank', 'rom'].includes(key)) await capture(`batch-menu-${theme}-${lang}-1440`);
    await click('.np-batch-toggle');
    assert.equal(await evaluate('document.querySelector(".np-matches").hidden'), true);
    if (verify) await verify(url);
    assert.deepEqual(await evaluate('ndErrors'), []);
    console.log(`PASS ${key}: ${form.dial}, ${form.batch}, ${theme}/${lang}`);
    failed = false;
  } finally {
    if (server) await stop(server);
    assert.equal(dirname(resolve(root)), temp);
    if (!failed) await rm(root, {recursive: true, force: true, maxRetries: 8, retryDelay: 200});
    else console.error('Disc Lab failure fixture:', root);
  }
}

async function verifyDeferred(url) {
  await viewport(390, 844);
  assert.ok(await evaluate(`(() => {
    const note = document.querySelector('.np-disc-help').getBoundingClientRect();
    const next = document.getElementById('next').getBoundingClientRect();
    return note.left >= 0 && note.right <= innerWidth && note.bottom <= next.top;
  })()`), 'drive notice fits above Next on a 390 px viewport');
  await capture('rom-dark-en-390');
  await click('.np-batch-toggle');
  assert.ok(await evaluate(`(() => {
    const popup = document.querySelector('.np-matches');
    const box = popup.getBoundingClientRect();
    const next = document.getElementById('next').getBoundingClientRect();
    return !popup.hidden && box.left >= 0 && box.right <= innerWidth &&
      box.bottom <= next.top && popup.lastElementChild.textContent === 'Choose later';
  })()`), 'batch menu fits and the deferred option is present on a 390 px viewport');
  await capture('batch-menu-dark-en-390');
  await click('.np-matches [role="option"]:last-child');
  await viewport(1440, 900);
  assert.deepEqual(await evaluate(`[
    document.querySelector('.np-batch').value, document.querySelector('.np-batch').placeholder,
    document.getElementById('next').disabled
  ]`), ['', '', false]);
  await evaluate('document.getElementById("next").click()');
  await until('document.documentElement.dataset.mode === "design"', 'editor did not open');
  await until('/nominal range/.test(document.querySelector(".ed-batch-note")?.textContent)', 'nominal range notice missing');
  await evaluate('document.querySelector(".ws [data-a=sample]").click()');
  await capture('deferred-editor-dark-en-1440');
  const saved = await evaluate(`(async () => {
    const design = await import('./design.js'), actions = design.editorActions();
    const text = await actions.projectText();
    const data = JSON.parse(text);
    const state = await fetch('/api/state?media=dvd').then(r => r.json());
    const blocked = await design.makeBurnFile().then(() => '', error => error.message);
    return {batch: data.batch, deferred: data.batch_deferred, disc: data.disc, geo: data.geo,
      media: data.media, version: data.version, geometry: design.projectGeo(state),
      hasMeasuredRings: !!actions.state().rings?.length, blocked};
  })()`);
  assert.deepEqual(saved, {batch: null, deferred: true, disc: null, geo: null, media: 'dvd', version: 2,
    geometry: null, hasMeasuredRings: false, blocked: 'Choose a batch from the disc library before making a burn file.'});
  await evaluate('document.querySelector("#ed-files [data-a=save]").click()');
  const workId = await until(`(async () => {
    const plan = (await import('./design.js')).editorActions().state();
    return !plan.dirty && plan.work?.id;
  })()`, 'the deferred work was not saved');
  const stored = await fetch(new URL(`/api/works/${workId}/design`, url)).then(r => r.json());
  assert.equal(stored.batch_deferred, true);
  assert.equal(stored.batch, null);
  await evaluate('document.getElementById("next").click()');
  await until(`document.documentElement.dataset.mode === "preview" &&
    document.getElementById("next-text").textContent === "Next: choose a batch"`, 'preview did not offer batch selection');
  assert.match(await evaluate('document.querySelector(".pv-list").textContent'), /Choose a batch from the disc library/);
  await capture('deferred-preview-dark-en-1440');
  await evaluate('document.getElementById("next").click()');
  await until(`document.documentElement.dataset.home === "library" && !document.documentElement.dataset.mode &&
    document.documentElement.dataset.navigation === "ready"`, 'Next did not open the library');
  assert.deepEqual(await fetch(new URL('/api/state', url)).then(r => r.json()).then(s => s.jobs), []);
  await evaluate('document.getElementById("next").click()');
  await until('document.documentElement.dataset.mode === "design" && document.querySelector(".ed-batch-note").hidden',
    'selecting a batch did not return to the editor');
  const restored = await evaluate(`(async () => {
    const actions = (await import('./design.js')).editorActions();
    const current = JSON.parse(await actions.projectText());
    const saved = await fetch('/api/works/' + ${JSON.stringify(workId)} + '/design').then(r => r.text());
    await actions.openProject(new File([saved], 'Deferred.discdesign'));
    const reopened = JSON.parse(await actions.projectText());
    const result = {picked: !!current.batch && !current.batch_deferred, reopened: reopened.batch_deferred,
      batch: reopened.batch, layers: reopened.layers.length, note: document.querySelector('.ed-batch-note').hidden};
    await actions.openProject(new File([JSON.stringify({...current, version: 1})], 'Legacy.discdesign'));
    const legacy = JSON.parse(await actions.projectText());
    return {...result, legacy: legacy.batch === current.batch && !legacy.batch_deferred && legacy.layers.length === 1};
  })()`);
  assert.deepEqual(restored, {picked: true, reopened: true, batch: null, layers: 1, note: false, legacy: true});
  console.log('PASS deferred: save/reopen, nominal range, export rejected, preview selects a batch, no jobs');
}

async function verifyStarter({theme, lang}) {
  await evaluate('document.querySelector(".np-cal-go").click()');
  await until(`document.documentElement.dataset.mode === 'cal' && !document.getElementById('next').disabled`, 'starter calibration entry');
  await evaluate('document.getElementById("next").click()');
  await until('document.querySelectorAll("#starter-choice input").length === 2', 'starter source missing');
  assert.equal(await evaluate('document.querySelector("#starter-choice input:checked")?.value'), '', 'starter never selected by default');
  assert.match(await evaluate('document.querySelector("#starter-choice label:last-child").textContent'), /DISCLAB GH70N-LIKE.*24.49–57.1/);
  assert.match(await evaluate('document.getElementById("next-text").textContent'), /生成测量镜像|Make measurement image/);
  await capture(`starter-${theme}-${lang}-1440`);
  await viewport(390, 844);
  await evaluate(`document.getElementById('starter-choice').scrollIntoView({block:'center'})`);
  assert.ok(await evaluate(`(() => {const r = document.getElementById('starter-choice').getBoundingClientRect();
    return r.width > 100 && r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight;})()`),
  'starter choice fits the mobile viewport');
  await capture(`starter-${theme}-${lang}-390`);
  await evaluate(`(() => {document.querySelectorAll('#starter-choice input')[1].click();})()`);
  assert.match(await evaluate('document.getElementById("next-text").textContent'), /刻检查盘|Burn the check disc/);
  await viewport(1440, 900);
  console.log(`PASS starter ${theme}/${lang}: measurement default, explicit source, check-disc action`);
}

try {
  browser = spawn(edge, ['--headless=new', '--mute-audio', '--disable-gpu', '--disable-background-networking',
    '--disable-component-update', '--no-first-run', '--no-default-browser-check', '--no-proxy-server',
    '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1', '--remote-debugging-port=0',
    `--user-data-dir=${profile}`, 'about:blank'],
  {windowsHide: true, stdio: 'ignore', env: {...process.env, TEMP: temp, TMP: temp}});
  const port = await waitFor(async () => (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')
    .catch(() => '')).split(/\r?\n/)[0], 'Edge did not start');
  const pages = await fetch(`http://127.0.0.1:${port}/json/list`).then(r => r.json());
  socket = new WebSocket(pages.find(page => page.type === 'page').webSocketDebuggerUrl);
  await once(socket, 'open');
  socket.onmessage = ({data}) => {
    const message = JSON.parse(data), reply = pending.get(message.id);
    if (!reply) return;
    pending.delete(message.id);
    if (message.error) reply.reject(Error(JSON.stringify(message.error)));
    else reply.resolve(message.result);
  };
  await cdp('Page.enable');
  await viewport(1440, 900);
  await cdp('Emulation.setEmulatedMedia', {features: [{name: 'prefers-reduced-motion', value: 'reduce'}]});
  if (onlyStarter) {
    for (const theme of ['light','dark']) for (const lang of ['zh','en']) {
      const scenario = {...cases[0], theme, lang, words:lang === 'en' ? /blank disc.*RITEKF1/i : cases[0].words};
      await runScene(scenario, () => verifyStarter(scenario));
    }
  } else {
    for (const scenario of cases) await runScene(scenario, scenario.key === 'rom' ? verifyDeferred :
      scenario.key === 'blank' ? () => verifyStarter(scenario) : null);
  }
} finally {
  if (socket?.readyState === WebSocket.OPEN) {
    await Promise.race([cdp('Browser.close').catch(() => {}), delay(2000)]);
    socket.close();
  }
  if (browser) await stop(browser);
  assert.equal(dirname(resolve(profile)), temp);
  await rm(profile, {recursive: true, force: true, maxRetries: 8, retryDelay: 200});
  await rmdir(temp).catch(() => {}); // Keep failure fixtures only.
}
