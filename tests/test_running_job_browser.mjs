// Headless Edge against the shipped HTTP service and a recorded Disc Lab DVD.
import assert from 'node:assert/strict';
import {spawn, spawnSync} from 'node:child_process';
import {existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {dirname, join, resolve} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {endProfileProcesses, removeProfile, stopEdge} from './edge_cleanup.mjs';

const root = process.env.RUNJOB_TEST_ROOT ?? join(tmpdir(), 'discprobe-running-job');
const memory = process.env.RUNJOB_MEMORY;
const idle = process.env.RUNJOB_IDLE;
const shots = process.env.RUNJOB_SHOTS;
const edge = process.env.PASTWORKS_TEST_BROWSER ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
mkdirSync(root, {recursive:true});
const dir = mkdtempSync(join(root, 'scenario-'));
const lab = join(dir, 'lab');
const profile = join(dir, 'edge');
const pending = new Map();
let browser, server, socket, origin, output = '', seq = 0;

function cdp(method, params = {}, sessionId) {
  return new Promise((resolve, reject) => {
    const id = ++seq;
    const timer = setTimeout(() => { pending.delete(id); reject(Error(method + ' timed out')); }, 15000);
    pending.set(id, msg => {
      clearTimeout(timer);
      msg.error ? reject(Error(JSON.stringify(msg.error))) : resolve(msg.result);
    });
    socket.send(JSON.stringify({id, method, params, sessionId}));
  });
}

async function until(read, label, ms = 45000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    const value = await read();
    if (value) return value;
    await delay(100);
  }
  throw Error(label);
}

async function request(path, body, expected = 200) {
  const response = await fetch(origin + path, body === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body),
  });
  const data = await response.json();
  assert.equal(response.status, expected, JSON.stringify(data));
  return data;
}

async function tab({lang = 'en', theme = 'paper', width = 1440, reduce = true} = {}) {
  const themeSetting = theme === 'paper' ? 'light' : 'dark';
  const {targetId} = await cdp('Target.createTarget', {url:'about:blank'});
  const {sessionId} = await cdp('Target.attachToTarget', {targetId, flatten:true});
  const command = (method, params) => cdp(method, params, sessionId);
  const evaluate = async expression => {
    const reply = await command('Runtime.evaluate', {expression, awaitPromise:true, returnByValue:true});
    assert.ok(!reply.exceptionDetails, JSON.stringify(reply.exceptionDetails));
    return reply.result.value;
  };
  await command('Page.enable');
  await command('Emulation.setDeviceMetricsOverride', {width, height:width === 390 ? 844 : 1000, deviceScaleFactor:1, mobile:false});
  await command('Page.addScriptToEvaluateOnNewDocument', {source:
    `localStorage.setItem('dp-lang',${JSON.stringify(lang)}); localStorage.setItem('dp-theme',${JSON.stringify(themeSetting)}); localStorage.setItem('dp-motion',${JSON.stringify(reduce ? 'off' : 'on')});`});
  await command('Page.navigate', {url:origin + '/home/'});
  await until(() => evaluate(`document.documentElement?.dataset.lang === ${JSON.stringify(lang)} &&
    document.documentElement.dataset.theme === ${JSON.stringify(themeSetting)} && innerWidth === ${width}`),
  'requested language, theme and viewport loaded');
  return {
    command, evaluate,
    wait: (expression, label) => until(() => evaluate(expression), label),
    click: selector => evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`),
    close: () => cdp('Target.closeTarget', {targetId}),
  };
}

const navigationReady = `document.documentElement.dataset.navigation === 'ready'`;
const inCal = `document.documentElement.dataset.mode === 'cal'`;
const inLobby = `!document.documentElement.dataset.mode && document.documentElement.dataset.home === 'lobby'`;
const inLibrary = `!document.documentElement.dataset.mode && document.documentElement.dataset.home === 'library'`;
const inGeometry = `${inCal} && ['Geometry', '测几何'].includes(document.querySelector('#job-name').textContent)`;
const reopen = `!document.querySelector('#next').disabled && ['Return to calibration', '回到校准'].includes(document.querySelector('#next-text').textContent)`;

async function screenshot(page, name) {
  if (!shots) return;
  mkdirSync(shots, {recursive:true});
  await page.evaluate('document.fonts.ready.then(() => true)');
  const image = await page.command('Page.captureScreenshot', {format:'png', captureBeyondViewport:false});
  writeFileSync(join(shots, name + '.png'), Buffer.from(image.data, 'base64'));
}

async function library(page) {
  await page.click('#library');
  await page.wait(inLibrary, 'disc library opened');
  await page.click('.kind[data-col="dvd"]');
  const item = await page.evaluate(`!!document.querySelector('.shelf-batch')`);
  assert.ok(item, 'Disc Lab has a catalogue row during geometry');
  await page.click('.shelf-batch');
}

async function checks(id, page) {
  const job = '/api/jobs/' + id;
  const geometry = await request(job);
  assert.equal(geometry.exit, null);
  assert.ok(geometry.events.some(e => e.type === 'step' && e.name === 'geo'));
  await page.command('Page.reload');
  await page.wait(`${navigationReady} && ${inGeometry}`, 'refresh reattaches to the same geometry job');
  await page.close();

  const looks = shots ? [1440, 390].flatMap(width => ['paper', 'dark'].flatMap(theme =>
    ['en', 'zh'].map(lang => ({width, theme, lang})))) : [{width:1440, theme:'paper', lang:'en'}];
  let active;
  for (const look of looks) {
    const suffix = `${look.theme}-${look.lang}-${look.width}`;
    const reopened = await tab(look);
    await reopened.wait(`${navigationReady} && ${inGeometry}`, 'fresh tab reattaches to running geometry');
    await reopened.click('#back');
    await reopened.wait(`${inLobby} && ${reopen}`, 'lobby primary action returns to calibration');
    assert.ok(await reopened.evaluate(`!document.querySelector('#job-name').disabled`), 'job strip is actionable');
    await screenshot(reopened, 'return-' + suffix);
    await reopened.click('#job-name');
    await reopened.wait(`${navigationReady} && ${inGeometry}`, 'job strip returns to geometry progress');
    await reopened.click('#back');
    await reopened.wait(`${inLobby} && ${reopen}`, 'lobby entry remains available after returning');
    await library(reopened);
    assert.equal(await reopened.evaluate(`document.querySelector('#status').dataset.s`), 'measuring',
      'open geometry must appear as an active batch, not an incomplete measurement');
    await reopened.evaluate(`document.querySelector('#library-more').open = true`);
    assert.ok(await reopened.evaluate(`['#library-rename','#library-delete'].every(s => {
      const button = document.querySelector(s);
      return button.disabled && !button.hidden && !!button.getAttribute('title');
    })`), 'active row disables rename and delete and explains why');
    await screenshot(reopened, 'library-' + suffix);
    if (look.width === 390 && shots) {
      await reopened.evaluate(`document.querySelector('#library-delete').scrollIntoView({block:'nearest'})`);
      await screenshot(reopened, 'library-actions-' + suffix);
    }
    const row = (await request('/api/catalogue')).dvd.find(row => row.s === 'measuring');
    assert.ok(row.measurement_progress.fraction >= .48);
    const preview = await request('/api/library', {operation:'preview', id:row.id});
    const refused = await request('/api/library', {operation:'delete', id:row.id, revision:preview.revision, with_works:false}, 409);
    assert.equal(refused.code, 'measurement_running');
    assert.equal((await request('/api/catalogue', {id:row.id, name:'Cannot rename yet'}, 409)).code, 'measurement_running');
    await reopened.click('#back');
    await reopened.wait(`${inLobby} && ${reopen}`, 'library back returns to lobby');
    await reopened.click('#next');
    await reopened.wait(`${navigationReady} && ${inGeometry}`, 'primary action returns to geometry progress');
    if (look !== looks.at(-1)) await reopened.close();
    else active = reopened;
  }
  await active.click('#back');
  await active.wait(inLobby, 'return to lobby while measurement is still live');
  await library(active);
  writeFileSync(join(lab, 'continue'), '');
  const result = await until(async () => {
    const state = await request(job);
    return state.exit === null ? null : state;
  }, 'the DVD calibration completes', 150000);
  assert.equal(result.exit, 0, JSON.stringify(result.result));
  const completed = (await request('/api/catalogue')).dvd;
  assert.ok(completed.some(row => ['good','usable'].includes(row.s)), JSON.stringify(completed));
  await active.wait(`['good','usable'].includes(document.querySelector('#status').dataset.s) &&
    !document.querySelector('#library-delete').disabled && !document.querySelector('#library-rename').disabled`,
  'the catalogue refreshes and enables the buttons after completion');
  await active.close();
  console.log('Verified reload, fresh tab, return to geometry, live catalogue, API refusals and completion.');
}

async function measure(id, cal) {
  const view = process.env.RUNJOB_MEMORY_VIEW ?? 'calibration';
  assert.ok(['calibration', 'lobby'].includes(view));
  if (view === 'lobby') {
    await cal.click('#back');
    await cal.wait(inLobby, 'lobby sample returns from calibration');
  }
  const rows = [];
  const job = '/api/jobs/' + id;
  const timed = Date.now();
  let minute = 0;
  let images;
  for (;;) {
    const state = await request(job);
    const start = state.events.findIndex(e => e.type === 'step' && e.name === 'geo');
    const geometry = start < 0 ? [] : state.events.slice(start);
    const events = geometry.filter(e => e.type === 'progress').length;
    if (start >= 0 && (minute === 0 || events >= minute * 240 || state.exit !== null)) {
      await delay(140);
      const raw = await cal.command('Runtime.getHeapUsage');
      await cal.command('HeapProfiler.collectGarbage');
      const heap = await cal.command('Runtime.getHeapUsage');
      const dom = await cal.command('Memory.getDOMCounters');
      const counts = await cal.evaluate(`[document.querySelectorAll('*').length,
        document.querySelectorAll('canvas').length, document.images.length,
        document.querySelectorAll('.cal-chart circle').length]`);
      if (!images && minute >= 2) images = await cal.evaluate(`[...new Map([...document.images]
        .filter(image => image.currentSrc && image.naturalWidth)
        .map(image => [image.currentSrc, {asset:new URL(image.currentSrc).pathname,
          rgbaBytes:image.naturalWidth * image.naturalHeight * 4}])).values()]
        .sort((a,b) => b.rgbaBytes - a.rgbaBytes)`);
      rows.push([view, minute, Math.round((Date.now() - timed) / 100) / 10, events,
        raw.usedSize, heap.usedSize, dom.nodes, ...counts, geometry.filter(e => e.type === 'geo_point').length]);
      writeFileSync(join(lab, 'memory-sample-' + minute), '');
      minute += 1;
    }
    if (state.exit !== null) {
      assert.equal(state.exit, 0, JSON.stringify(state.result));
      assert.ok(events >= 4800, `expected at least 4800 geometry progress events, got ${events}`);
      assert.deepEqual(rows.slice(0, 21).map(row => row[3]),
        Array.from({length:21}, (_, i) => i * 240), 'sampled every equivalent minute');
      break;
    }
    await delay(80);
  }
  mkdirSync(dirname(memory), {recursive:true});
  writeFileSync(memory, 'view,minute,wall_seconds,progress_events,raw_heap_bytes,gc_heap_bytes,cdp_dom_nodes,elements,canvases,images,chart_circles,geo_points\n' +
    rows.map(row => row.join(',')).join('\n') + '\n');
  writeFileSync(memory.replace(/\.csv$/, '-images.json'), JSON.stringify(images, null, 2));
  await cal.close();
  console.log(`Profiled ${rows.length} samples in ${memory}`);
}

async function captureIdle() {
  const page = await tab();
  await page.wait(`${navigationReady} && ${inLobby}`, 'idle launch stays in the lobby');
  const snapshot = await request('/api/state');
  const labels = [await page.evaluate(`document.querySelector('#next-text').textContent`)];
  await page.click('#library');
  await page.wait(inLibrary, 'idle library opens');
  labels.push(await page.evaluate(`document.querySelector('#status').textContent.trim()`));
  await page.click('#library-calibrate');
  await page.wait(inCal, 'idle calibration opens the initial inspection');
  labels.push(await page.evaluate(`[document.querySelector('#cal h2').textContent, document.querySelector('#next-text').textContent]`));
  assert.deepEqual((await request('/api/state')).jobs, []);
  writeFileSync(idle, JSON.stringify({jobs:snapshot.jobs, catalogue:snapshot.catalogue, labels}, null, 2) + '\n');
  await page.close();
}

try {
  server = spawn(process.env.PYTHON ?? 'python', ['-X','utf8','-B',resolve('tests/running_job_lab_fixture.py'),lab],
    {windowsHide:true, env:{...process.env,TEMP:root,TMP:root}});
  server.stdout.on('data', bytes => output += bytes);
  server.stderr.on('data', bytes => output += bytes);
  const port = await until(() => output.match(/PORT (\d+)/)?.[1], 'Disc Lab reported its server port');
  assert.notEqual(+port, 8765);
  origin = 'http://127.0.0.1:' + port;
  await until(() => fetch(origin + '/api/state').then(r => r.ok).catch(() => false), 'Disc Lab HTTP ready');
  browser = spawn(edge, ['--headless=new','--mute-audio','--disable-gpu','--disable-background-networking',
    '--no-first-run','--no-default-browser-check','--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'],
  {windowsHide:true, stdio:'ignore'});
  const debugPort = await until(() => {
    try { return readFileSync(join(profile,'DevToolsActivePort'),'utf8').split(/\r?\n/)[0]; } catch {}
  }, 'Edge debugging ready');
  assert.notEqual(+debugPort, 8765);
  const debug = await fetch(`http://127.0.0.1:${debugPort}/json/version`).then(r => r.json());
  socket = new WebSocket(debug.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  socket.onmessage = ({data}) => {
    const msg = JSON.parse(data), receive = pending.get(msg.id);
    if (receive) { pending.delete(msg.id); receive(msg); }
  };
  if (idle) await captureIdle();
  else {
    const {job} = await request('/api/run', {action:'calibrate', drive:'X:', media:'dvd', args:{}});
    const first = await tab({reduce:!memory});
    await first.wait(`${navigationReady} && ${inCal}`, 'calibration opens');
    if (memory) await measure(job, first);
    else {
      await until(async () => {
        if (existsSync(join(lab, 'midpoint'))) return true;
        const state = await request('/api/jobs/' + job);
        assert.equal(state.exit, null, JSON.stringify(state.result));
        return false;
      }, 'DVD geometry reaches its midpoint', 150000);
      await first.wait(inGeometry, 'first tab shows geometry progress');
      await checks(job, first);
    }
  }
} finally {
  writeFileSync(join(dir, 'server.log'), output);
  await stopEdge(browser, socket);
  if (existsSync(profile)) { endProfileProcesses(profile); removeProfile(profile, dir); }
  if (server?.pid && server.exitCode === null) {
    if (process.platform === 'win32') spawnSync('taskkill', ['/PID', String(server.pid), '/T', '/F'], {windowsHide:true, stdio:'ignore'});
    else server.kill();
  }
  // Resolve and verify the one fixture folder before recursive cleanup.
  if (existsSync(lab)) removeProfile(lab, dir);
}
