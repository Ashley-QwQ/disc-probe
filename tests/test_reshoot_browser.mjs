// The shipped desktop workflow against Disc Lab, with the real reader and sampler.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {copyFileSync, createReadStream, existsSync, linkSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {delimiter, isAbsolute, join, relative, resolve} from 'node:path';
import {stopEdge, endProfileProcesses} from './edge_cleanup.mjs';

const root = resolve(import.meta.dirname, '..');
const base = resolve(process.env.RESHOOT_TEST_ROOT ?? join(tmpdir(), 'discprobe-reshoot'));
const shots = resolve(process.env.RESHOOT_SHOTS ?? join(base, 'shots'));
mkdirSync(base, {recursive:true}); mkdirSync(shots, {recursive:true});
const browserBin = process.env.PASTWORKS_TEST_BROWSER ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
assert.ok(existsSync(browserBin), browserBin);
const python = process.env.PYTHON ?? 'python';
const fixture = join(root, 'tests/reshoot_lab_fixture.py');
const profile = mkdtempSync(join(base, 'profile-'));
const cache = mkdtempSync(join(base, 'check-iso-'));
const delay = ms => new Promise(done => setTimeout(done, ms));
const proof = [];
const env = {...process.env, DISCPROBE_WORKERS:'2', OPENBLAS_NUM_THREADS:'1',
  OPENCV_FOR_THREADS_NUM:'2', PYTHONHASHSEED:'0', PYTHONDONTWRITEBYTECODE:'1'};
let browser, server, socket, seq = 0, origin, port;
const pending = new Map();

async function removeTemp(path) {
  if (!existsSync(path)) return;
  const entry = relative(realpathSync(base), realpathSync(path));
  assert.ok(entry && !entry.startsWith('..') && !isAbsolute(entry), path);
  try { rmSync(path, {recursive:true, force:true, maxRetries:4, retryDelay:250}); }
  catch (error) {
    if (process.platform !== 'win32' || error.code !== 'EPERM') throw error;
    await command(path, 'clean', base);
  }
}
function processFor(lab, task, ...args) {
  const params = [fixture, task, lab, ...args.map(String)];
  const activeEnv = task === 'serve' ? {...env, DISCPROBE_DISCLAB:lab, DISCLAB_ROOT:root,
    PYTHONPATH:[join(root, 'disclab/boot'), root, env.PYTHONPATH].filter(Boolean).join(delimiter),
    DISCPROBE_HOME:lab, DISCPROBE_PLAIN:'1', PYTHONIOENCODING:'utf-8'} : env;
  const child = spawn(python, ['-X', 'utf8', '-B', ...params], {cwd:root, env:activeEnv, windowsHide:true, stdio:['ignore','pipe','pipe']});
  let log = '';
  child.stdout.on('data', b => { log += b; });
  child.stderr.on('data', b => { log += b; });
  const done = new Promise((done, reject) => {
    child.once('error', reject);
    child.once('close', code => done({code, log}));
  });
  return {child, done, output:() => log};
}
async function command(lab, task, ...args) {
  const {code, log} = await processFor(lab, task, ...args).done;
  assert.equal(code, 0, log);
  process.stdout.write(log);
  return log;
}
async function waitFor(fn, message, timeout = 60000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = await fn();
    if (value) return value;
    await delay(100);
  }
  throw Error(message);
}
function cdp(method, params = {}) {
  const id = ++seq;
  return new Promise((done, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(Error('CDP timeout: ' + method)); }, 15000);
    pending.set(id, {done, reject, timer});
    socket.send(JSON.stringify({id,method,params}));
  });
}
async function js(expression) {
  const result = await cdp('Runtime.evaluate', {expression, awaitPromise:true, returnByValue:true});
  assert.ok(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
async function pageHas(expression, message, timeout) {
  try { await waitFor(() => js(expression), message, timeout); }
  catch (error) {
    throw Error(error.message + ': ' + JSON.stringify(await js('({mode:document.documentElement.dataset.mode,errors:window.reshootErrors,text:document.body.innerText.slice(-3000)})')));
  }
}
async function size(width) {
  await cdp('Emulation.setDeviceMetricsOverride', {width, height:width === 390 ? 844 : 900, deviceScaleFactor:1, mobile:false});
}
async function capture() {
  for (const lang of ['zh','en']) {
    await js(`if (document.documentElement.dataset.lang !== '${lang}') document.getElementById('lang').click()`);
    for (const theme of ['paper','dark']) {
      await js(`document.documentElement.dataset.theme='${theme}'`);
      for (const width of [1440,390]) {
        await size(width);
        await js('document.fonts.ready'); await delay(150);
        assert.ok(await js('document.querySelector("#photo-burn-select").getBoundingClientRect().right <= innerWidth + 1'));
        const result = await cdp('Page.captureScreenshot', {format:'png', captureBeyondViewport:false});
        writeFileSync(join(shots, `reshoot-${theme}-${lang}-${width}.png`), Buffer.from(result.data, 'base64'));
      }
    }
  }
  await size(1440);
}
async function start(lab, preferred = 0) {
  const ready = join(lab, 'ready.json');
  rmSync(ready, {force:true});
  server = processFor(lab, 'serve', preferred);
  const record = await waitFor(() => {
    try { return JSON.parse(readFileSync(ready, 'utf8')); } catch { return null; }
  }, 'webui did not start');
  port = record.port; origin = `http://127.0.0.1:${port}`;
}
async function stop() {
  if (!server) return;
  server.child.kill();
  await server.done;
  server = null;
}
async function api(path, payload) {
  const reply = await fetch(origin + path, payload === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload),
  });
  const out = await reply.json();
  if (!reply.ok) throw Object.assign(Error(JSON.stringify(out)), {status:reply.status, code:out.code});
  return out;
}
async function job(payload, timeout = 240000) {
  const {job:id} = await api('/api/run', payload);
  const final = await waitFor(async () => {
    const snapshot = await api('/api/jobs/' + id);
    return snapshot.exit === null ? null : snapshot;
  }, `job did not finish: ${payload.action}`, timeout);
  assert.equal(final.exit, 0, JSON.stringify(final.events.slice(-8)));
  return final;
}
async function burn(iso) {
  const request = {action:'burn', drive:'X:', media:'dvd', args:{iso, speed:8}};
  const {token} = await waitFor(async () => {
    try {
      const checked = await api('/api/burn-check', request);
      assert.equal(checked.gate, null, JSON.stringify(checked));
      return await api('/api/burn-token', request);
    }
    catch (error) { if (error.code === 'drive_busy') return null; throw error; }
  }, 'virtual drive remained busy');
  const result = await job({...request, burn_token:token});
  const event = result.events.find(e => e.type === 'burn_result');
  assert.equal(event?.result, 'completed');
  assert.equal(event?.verification?.differing, 0);
  assert.match(event.disc_id, /^C\d{4}-\d{4}$/);
  assert.match(event.burn_record, /^[a-f0-9]{64}$/);
  return event;
}
async function hash(path) {
  const digest = createHash('sha256');
  for await (const chunk of createReadStream(path)) digest.update(chunk);
  return digest.digest('hex');
}
async function library() {
  await cdp('Page.navigate', {url:origin + '/home/#/library'});
  await pageHas('document.documentElement.dataset.navigation === "ready" && document.getElementById("library-check-photo")?.hidden === false', 'library entry visible');
}
async function enter() { await js('document.getElementById("library-check-photo").click()'); }
async function reload() {
  await delay(300); // allow the existing navigation snapshot to commit to IndexedDB
  await cdp('Page.reload');
  await pageHas('document.documentElement.dataset.navigation === "ready" && !!document.querySelector("#photo-burn-confirmed")', 'selected burn restored');
}

async function scenario(burnCount) {
  const prepared = burnCount === 1 && process.env.RESHOOT_PREPARED_LAB;
  const lab = prepared ? realpathSync(prepared) : mkdtempSync(join(base, `lab-${burnCount}-`));
  const entry = relative(realpathSync(base), realpathSync(lab));
  assert.ok(entry && !entry.startsWith('..') && !isAbsolute(entry), lab);
  const logName = join(base, `reshoot-${burnCount}.log`);
  let transcript = '';
  try {
    transcript += prepared ? 'Check ISO SHA-256: ' + await hash(join(lab, 'iso/check.iso')) + '\n'
      : await command(lab, 'prepare', ...(burnCount === 2 ? [cache] : []));
    const {run, iso} = JSON.parse(readFileSync(join(lab, 'fixture.json'), 'utf8'));
    await start(lab);
    if (burnCount === 1) {
      await library(); await enter();
      await pageHas('!!document.querySelector("#photo-burn-again") && document.getElementById("next").disabled', 'no completed burn gives a Burn button');
      await cdp('Page.navigate', {url:'about:blank'});
    }
    const events = [];
    for (let i = 0; i < burnCount; i++) {
      if (i) await command(lab, 'tray', i);
      events.push(await burn(iso));
    }
    const before = /Check ISO SHA-256: (\w+)/.exec(transcript)[1];
    assert.equal(await hash(join(lab, iso)), before);
    if (burnCount === 1) {
      linkSync(join(lab, iso), join(cache, 'check.iso'));
      copyFileSync(join(lab, 'iso/check.image.json'), join(cache, 'check.image.json'));
      copyFileSync(join(lab, 'iso/check.iso.verification.json'), join(cache, 'check.iso.verification.json'));
      copyFileSync(join(lab, 'check-arrow.png'), join(cache, 'check-arrow.png'));
    }
    await cdp('Page.navigate', {url:'about:blank'});
    const previousPort = port;
    await stop(); await start(lab, previousPort);
    const rows = (await api('/api/photo-burns?run=' + run)).burns;
    assert.deepEqual(rows.map(r => r.id), events.toReversed().map(e => e.burn_record));
    assert.equal(rows[0].path, 'Disc Lab');
    await library(); await enter();
    if (burnCount === 1) {
      await pageHas(`document.querySelector("#photo-burn-number")?.value === ${JSON.stringify(rows[0].disc_id)}`, 'single burn and its number selected');
    } else {
      await pageHas('document.querySelector("#photo-burn-select")?.options.length === 3', 'two completed burns listed');
      await capture();
      const ids = await js('Array.from(document.querySelector("#photo-burn-select").options).map(o => o.value)');
      assert.deepEqual(ids, ['', rows[0].id, rows[1].id]);
      await js(`const s = document.querySelector("#photo-burn-select"); s.value=${JSON.stringify(rows[0].id)}; s.dispatchEvent(new Event("change",{bubbles:true}));`);
      await js(`const n = document.querySelector("#photo-burn-number"); n.value="marked-second"; n.dispatchEvent(new Event("input",{bubbles:true}));`);
    }
    const discId = burnCount === 1 ? rows[0].disc_id : 'marked-second';
    await js('document.getElementById("next").click()');
    await pageHas('!!document.querySelector("#photo-burn-confirmed")', 'photo page shows the confirmed burn');
    if (burnCount === 2) {
      await delay(300);
      await stop(); await start(lab, previousPort);
    }
    await reload();
    await pageHas(`document.querySelector(".pc-disc-id input")?.value === ${JSON.stringify(discId)}`, 'edited number survives refresh');
    transcript += await command(lab, 'shoot', burnCount - 1);
    const files = JSON.parse(readFileSync(join(lab, 'camera.json'), 'utf8'));
    const {root:document} = await cdp('DOM.getDocument');
    const {nodeId} = await cdp('DOM.querySelector', {nodeId:document.nodeId, selector:'.pc-file'});
    assert.ok(nodeId);
    await cdp('DOM.setFileInputFiles', {nodeId, files});
    const photoPath = join(lab, 'results', run, 'photo.json');
    const photo = await waitFor(() => {
      try { return JSON.parse(readFileSync(photoPath, 'utf8')); } catch { return null; }
    }, 'photo job did not write a result', 240000);
    const reading = photo.photos.map(p => [p.status, p.L_mm, p.c_deg]);
    transcript += 'Simulated photo readings: ' + JSON.stringify(reading) + '\n';
    assert.equal(photo.verdict, 'ok', JSON.stringify(reading));
    assert.equal(photo.burn_record.id, rows[0].id);
    const output = 'iso/picture.iso';
    const final = await job({action:'image', media:'dvd', args:{
      geo:'results/' + run, picture:'picture.png', output, diameter_mm:56, r_max:28,
    }});
    assert.ok(!JSON.stringify(final.events).includes('Photo L not applied'));
    assert.ok(JSON.stringify(final.events).includes('Photo L used:'));
    const {photo_l:decision} = JSON.parse(readFileSync(join(lab, 'iso/picture.image.json'), 'utf8'));
    assert.ok(decision.written, JSON.stringify(decision));
    const p = decision.provenance;
    assert.equal(p.disc_id, discId);
    assert.deepEqual(p.burn_path, {burner:rows[0].burner, path:rows[0].path, mode:rows[0].mode});
    assert.equal(p.burn_record.id, rows[0].id);
    assert.equal(p.burn_record.time, rows[0].time);
    assert.equal(p.burn_record.disc_id_overridden, burnCount === 2);
    proof.push({burnCount, photos:reading, L_mm:decision.L_mm, photo_l:p, checkISO:before, pictureISO:await hash(join(lab, output))});
    assert.deepEqual(await js('window.reshootErrors'), []);
    if (burnCount === 1) writeFileSync(join(shots, 'check-disc-arrow.png'), readFileSync(join(lab, 'check-arrow.png')));
  } catch (error) {
    transcript += '\n' + error.stack + '\n' + (server?.output() || '');
    throw error;
  } finally {
    await cdp('Page.navigate', {url:'about:blank'}).catch(() => {});
    await stop();
    writeFileSync(logName, transcript);
    await removeTemp(lab);
  }
}

try {
  browser = spawn(browserBin, ['--headless=new', '--disable-gpu', '--mute-audio', '--disable-background-networking',
    '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'],
  {windowsHide:true, stdio:'ignore'});
  const debugPort = await waitFor(() => {
    try { return readFileSync(join(profile, 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0]; } catch { return null; }
  }, 'headless test browser did not start');
  const targets = await fetch(`http://127.0.0.1:${debugPort}/json/list`).then(r => r.json());
  socket = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl);
  await new Promise((done,reject) => { socket.onopen = done; socket.onerror = reject; });
  socket.onmessage = ({data}) => {
    const msg = JSON.parse(data), request = pending.get(msg.id);
    if (!request) return;
    pending.delete(msg.id);
    clearTimeout(request.timer);
    if (msg.error) request.reject(Error(JSON.stringify(msg.error))); else request.done(msg.result);
  };
  await cdp('Page.enable'); await size(1440);
  await cdp('Emulation.setEmulatedMedia', {features:[{name:'prefers-reduced-motion', value:'reduce'}]});
  await cdp('Page.addScriptToEvaluateOnNewDocument', {source:`
    window.reshootErrors=[];
    addEventListener('error', e => { if (e.message) reshootErrors.push(e.message); });
    addEventListener('unhandledrejection', e => reshootErrors.push(String(e.reason)));
  `});
  for (const count of [1,2]) await scenario(count);
  console.log('reshoot: 2 Disc Lab scenarios, 8 UI screenshots, 1 alignment-arrow preview');
} finally {
  await stop();
  await stopEdge(browser, socket);
  endProfileProcesses(profile);
  await removeTemp(profile);
  await removeTemp(cache);
  if (proof.length) writeFileSync(join(base, 'reshoot-evidence.json'), JSON.stringify(proof, null, 2));
}
