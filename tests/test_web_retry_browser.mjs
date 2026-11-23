// Exercise calibration through the shipped page and its HTTP client, using headless Edge and CDP.
import assert from 'node:assert/strict';
import {spawn, execFileSync} from 'node:child_process';
import {existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync} from 'node:fs';
import {createServer} from 'node:http';
import {tmpdir} from 'node:os';
import {join, resolve, sep, extname} from 'node:path';

const base = process.env.WEB_RETRY_TEST_ROOT ?? tmpdir();
const profile = mkdtempSync(join(base, 'web-retry-edge-'));
const shots = process.env.WEB_RETRY_SHOTS;
const baseline = process.env.WEB_RETRY_BASELINE === '1';
const web = resolve('discprobe/web');
const drive = 'X:';
const disc = {present:true, media:'dvd', mid:'LAB-A', kind:'DVD-R', blank:false, sectors:131072, capacity_sectors:140000};
const blank = {...disc, blank:true, sectors:disc.capacity_sectors};
const advice = {media:'dvd', tried:['11080'], next_speed:'3324', lower_speeds:['3324', '5540']};
const pathFor = kind => 'results/' + kind + '-X-run';
const timing = (measurement, verdict = 'too_noisy') => ({path:pathFor('timing'), verdict, measurement});
const geo = (measurement, verdict = 'stopped_early') => ({path:pathFor('geo'), verdict, measurement});
const cases = {
  noisy: {timing:timing({rotation:'CAV', retry_kind:'noisy', speed_advice:advice})},
  clv: {timing:timing({rotation:'CLV', speed_advice:advice})},
  unknown: {timing:timing({rotation:'unknown', speed_advice:{...advice, next_speed:null}})},
  media: {timing:timing({stopped:'reads keep failing with medium errors (3/11/00)', retry_kind:'media', speed_advice:advice}, 'stopped_early')},
  slow: {timing:timing({stopped:'reads are far slower than expected', retry_kind:'slow', speed_advice:advice}, 'stopped_early')},
  rung: {geo:geo({span_mm:[28, 41], completion_status:'partial_readable', can_resume:true, retry_kind:'rung', failed_rung:6, retry_speed_advice:advice})},
  coverage: {geo:geo({span_mm:[28, 41], missing_mm:[[41, 55]], can_resume:true, retry_kind:'coverage'}, 'narrow_span')},
  burn: {},
  'burn-stall': {},
};
const options = {burn_speeds:['4', '8'], argv:['python', '-m', 'discprobe', 'calibrate', '--drive', drive],
  log_path:'.webui-jobs/j-seed/output.log'};
let labCases = process.env.WEB_RETRY_LAB_CASES;
const original = new Map();
if (baseline) {
  for (const asset of ['gui.json', 'home/api.js', 'home/calibrate.js', 'home/guidance.mjs']) {
    original.set(join(web, asset), execFileSync('git', ['show', 'fa26d74:discprobe/web/' + asset]));
  }
}
const started = [];
const preflight = [];
let scenario = 'noisy';
let blankInserted = false;
const discForCase = () => blankInserted ? blank : scenario.startsWith('burn') ? {...disc, closed:false}
  : scenario === 'noisy-cd' ? {...disc, media:'cd', kind:'CD-RW'} : disc;
const seedJob = () => ({id:'j-seed', drive, action:'calibrate', media:discForCase().media, disc:discForCase(), exit:null,
  args:scenario.startsWith('burn') ? {iso:'iso/measurement.iso'} : {sectors:140000}});
function seedSnapshot() {
  if (scenario === 'burn-stall') return {exit:null, events:[{type:'step', name:'burn'},
    {type:'burn_speed', selected_speed_x:8, log_path:'iso/measurement.burn.jsonl'}]};
  if (scenario === 'noisy-cd') return {exit:1, diagnostics:options, events:[{type:'step', name:'timing'}],
    result:{ok:false, disc:discForCase(), sectors:140000, timing:timing({rotation:'CAV', retry_kind:'noisy',
      speed_advice:{media:'cd', next_speed:'2822', lower_speeds:['1411']}})}};
  if (labCases && existsSync(join(labCases, scenario + '-lab.json'))) {
    const actual = JSON.parse(readFileSync(join(labCases, scenario + '-lab.json'), 'utf8'));
    const part = actual.result;
    const match = {
      noisy:part?.measurement?.rotation === 'CAV' && part.measurement.retry_kind === 'noisy',
      clv:part?.measurement?.rotation === 'CLV',
      unknown:part?.measurement?.rotation === 'unknown',
      media:part?.measurement?.stopped?.includes('3/11/00'),
      slow:part?.measurement?.stopped?.includes('far slower'),
      rung:part?.measurement?.retry_kind === 'rung' && part.measurement.can_resume,
      coverage:part?.measurement?.missing_mm?.length > 0 && part.measurement.can_resume,
      burn:actual.events.some(e => e.type === 'burn_result' && e.result === 'failed'),
    }[scenario];
    if (match) {
      const events = actual.events.map(event => ({...event, job:'j-seed'}));
      if (scenario === 'burn') return {...actual, events};
      const kind = actual.action;
      return {...actual, events:[{type:'step',name:kind}, ...events], exit:1,
        result:{ok:false, reason:part.measurement.stopped, disc, sectors:140000, [kind]:part}};
    }
  }
  const name = scenario === 'burn' ? 'burn' : cases[scenario].geo ? 'geo' : 'timing';
  const events = [{type:'step', name}];
  if (name === 'burn') events.push({type:'burn_speed', selected_speed_x:16, log_path:'iso/measurement.burn.jsonl'},
    {type:'burn_result', result:'failed', reason:'write interrupted', log_path:'iso/measurement.burn.jsonl'});
  return {exit:1, events, diagnostics:options, result:{ok:false, reason:'Measurement incomplete', disc, sectors:140000, ...cases[scenario]}};
}

const types = {'.html':'text/html', '.js':'text/javascript', '.mjs':'text/javascript', '.json':'application/json',
  '.webp':'image/webp', '.png':'image/png', '.svg':'image/svg+xml', '.woff2':'font/woff2'};
const server = createServer(async (req, res) => {
  const route = decodeURIComponent(new URL(req.url, 'http://127.0.0.1').pathname);
  const json = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(data)); };
  if (route === '/api/events') return res.writeHead(204).end(); // Completed snapshots exercise the same follow path.
  const body = req.method === 'POST' ? JSON.parse((await Array.fromAsync(req)).join('')) : null;
  if (route === '/api/version') return json({api_version:'1.3', core_version:'test', capabilities:
    [...new Set(Object.values(JSON.parse(readFileSync(join(web, 'gui.json')))).filter(Array.isArray).flat())]});
  if (route === '/api/state') return json({drives:[{id:drive, name:'Disc Lab', disc:discForCase()}],
    jobs:[seedJob()], catalogue:{dvd:[], cd:[], bd:[]}, platform:'win32'});
  if (route === '/api/disc') return json({disc:discForCase()});
  if (route === '/api/burn-check') { preflight.push(body); return json({disc:blank, speeds_x:[4, 8, 16], gate:null}); }
  if (route === '/api/burn-token') { preflight.push(body); return json({token:'test-token'}); }
  if (route === '/api/run') {
    started.push(body);
    return json({job:'j-' + started.length});
  }
  if (route === '/api/jobs/j-seed') return json(seedSnapshot());
  if (route.startsWith('/api/jobs/')) {
    const job = started[Number(route.slice('/api/jobs/j-'.length)) - 1];
    if (!job) return json({});
    const result = job.action === 'info' ? {disc:discForCase()} : job.action === 'random' ? {path:job.args.output} : job.action === 'timing'
      ? timing({rotation:'CAV'}, 'good') : job.action === 'geo' ? geo({}, 'good')
      : {ok:true, disc, geo:geo({}, 'good')};
    return json({exit:0, result, events:[]});
  }
  if (route.startsWith('/api/')) return json({});
  const file = resolve(web, '.' + (route.endsWith('/') ? route + 'index.html' : route));
  if (file.startsWith(web + sep) && !/[bB][lL][iI][nN][dD]/.test(file)) {
    try {
      const bytes = original.get(file) ?? readFileSync(file);
      res.setHeader('Content-Type', types[extname(file)] ?? 'application/octet-stream');
      return res.end(bytes);
    } catch (error) {
      if (error.code !== 'ENOENT' && error.code !== 'EISDIR') throw error;
    }
  }
  res.writeHead(404).end();
});

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let browser, socket, seq = 0;
const pending = new Map();
const cdp = (method, params) => new Promise((resolve, reject) => {
  const id = ++seq;
  const timeout = setTimeout(() => { pending.delete(id); reject(Error('CDP timeout: ' + method)); }, 8000);
  pending.set(id, message => {
    clearTimeout(timeout);
    if (message.error) reject(Error(JSON.stringify(message.error)));
    else resolve(message.result);
  });
  socket.send(JSON.stringify({id, method, params}));
});
async function evaluate(expression) {
  const r = await cdp('Runtime.evaluate', {expression, awaitPromise:true, returnByValue:true});
  assert.ok(!r.exceptionDetails, JSON.stringify(r.exceptionDetails));
  return r.result.value;
}
async function until(check, label) {
  for (let i = 0; i < 250; i++) {
    if (await check()) return;
    await delay(40);
  }
  throw Error(label + '\n' + JSON.stringify(await evaluate(`({
    url:location.href, mode:document.documentElement?.dataset.mode, errors:window.retryErrors,
    content:document.querySelector('#cal')?.innerText, next:document.querySelector('#next-text')?.textContent
  })`)));
}
async function load(name, lang = 'en', theme = 'paper', width = 1440) {
  scenario = name;
  blankInserted = false;
  const themeSetting = theme === 'paper' ? 'light' : theme;
  await cdp('Emulation.setDeviceMetricsOverride', {width, height:width === 390 ? 844 : 1000, deviceScaleFactor:1, mobile:false});
  const {identifier} = await cdp('Page.addScriptToEvaluateOnNewDocument', {source:
    `localStorage.setItem('dp-lang', '${lang}');localStorage.setItem('dp-theme', '${themeSetting}');
    window.retryErrors=[];addEventListener('error', e=>retryErrors.push(e.message));
    addEventListener('unhandledrejection', e=>retryErrors.push(e.reason?.stack || String(e.reason)));`});
  await cdp('Page.navigate', {url:`http://127.0.0.1:${server.address().port}/home/?fixture=${name}&lang=${lang}&theme=${theme}&width=${width}`});
  const screen = name === 'burn-stall' ? 'document.querySelector("#job-cancel")?.textContent.length > 0'
    : name === 'burn' ? '/finish|完成/.test(document.querySelector("#cal h2")?.textContent)'
    : '!!document.querySelector("#cal .cal-stamp")';
  await until(() => evaluate(`new URLSearchParams(location.search).get('fixture') === '${name}' &&
    document.documentElement?.dataset.mode === 'cal' &&
    document.documentElement.dataset.theme === '${themeSetting}' &&
    document.documentElement.dataset.lang === '${lang}' && innerWidth === ${width} &&
    new URLSearchParams(location.search).get('width') === '${width}' &&
    (${screen})`), 'case: ' + name);
  await cdp('Page.removeScriptToEvaluateOnNewDocument', {identifier});
}
const click = selector => evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
async function shot(name) {
  await evaluate('document.fonts.ready');
  await delay(140);
  const png = await cdp('Page.captureScreenshot', {format:'png', captureBeyondViewport:false});
  writeFileSync(join(shots, name + '.png'), Buffer.from(png.data, 'base64'));
}

try {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  assert.notEqual(server.address().port, 8765);
  const edge = process.env.WEB_RETRY_EDGE ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
  browser = spawn(edge, ['--headless=new', '--mute-audio', '--disable-gpu', '--disable-background-networking',
    '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', '--user-data-dir=' + profile,
    'about:blank'], {windowsHide:true, stdio:'ignore'});
  const activePort = join(profile, 'DevToolsActivePort');
  for (let i = 0; i < 200 && !existsSync(activePort); i++) await delay(50);
  const port = Number(readFileSync(activePort, 'utf8').split(/\r?\n/)[0]);
  assert.notEqual(port, 8765);
  const targets = await fetch(`http://127.0.0.1:${port}/json/list`).then(response => response.json());
  socket = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  socket.onmessage = ({data}) => {
    const message = JSON.parse(data);
    const complete = pending.get(message.id);
    if (pending.delete(message.id)) complete(message);
  };
  await cdp('Page.enable');
  await cdp('Emulation.setEmulatedMedia', {features:[{name:'prefers-reduced-motion', value:'reduce'}]});
  if (shots) {
    mkdirSync(shots, {recursive:true});
    for (const name of (process.env.WEB_RETRY_CASES?.split(',') ?? Object.keys(cases))) {
      for (const [lang, theme, width] of [['zh','paper',1440], ['en','dark',1440], ['en','paper',390], ['zh','dark',390]]) {
        await load(name, lang, theme, width);
        await shot([baseline ? 'before' : 'after', name, lang, theme, width].join('-'));
      }
    }
  }
  if (!baseline) {
    labCases = null;
    await verifyActions();
  }
} finally {
  if (socket?.readyState === WebSocket.OPEN) {
    await Promise.race([cdp('Browser.close').catch(() => {}), delay(2000)]);
    socket.close();
  }
  server.closeAllConnections();
  server.close();
  if (browser && browser.exitCode === null) {
    const exit = new Promise(resolve => browser.once('exit', resolve));
    browser.kill();
    await Promise.race([exit, delay(1500)]);
  }
  rmSync(profile, {recursive:true, force:true, maxRetries:12, retryDelay:150});
}

async function verifyActions() {
  const sent = (action, args) => ({action, media:'dvd', drive, args});
  const retry = async (name, selector, speed) => {
    await load(name);
    started.length = 0;
    if (selector === '#real-lower-read') await evaluate(`document.querySelector('#real-lower-read-speed').value = '${speed}'`);
    await click(selector);
    await until(() => started.length >= 2, 'retry sent rotation then geometry');
    assert.deepEqual(started, [sent('timing', speed ? {speed} : {}), sent('geo', {speed:'keep'})]);
  };
  for (const name of ['noisy','clv','media','slow','rung']) {
    await retry(name, '#real-suggested-speed', 3324);
    await retry(name, '#real-lower-read', 5540);
  }
  await load('noisy-cd');
  started.length = 0;
  await click('#real-suggested-speed');
  await until(() => started.length === 2, 'CD suggestion uses its kB/s value');
  assert.deepEqual(started, [
    {...sent('timing', {speed:2822}), media:'cd'}, {...sent('geo', {speed:'keep'}), media:'cd'},
  ]);
  await load('unknown');
  assert.equal(await evaluate('!!document.querySelector("#real-suggested-speed")'), false);
  await retry('unknown', '#next', null);
  for (const name of ['rung','coverage']) {
    await load(name);
    started.length = 0;
    await click('#next');
    await until(() => started.length > 0, 'resume job was sent');
    assert.equal(started.length, 1);
    const {preset, ...args} = started[0].args;
    assert.match(preset, /^presets\/calibration-\d+\.json$/);
    assert.deepEqual({...started[0], args}, sent('calibrate', {
      mid:'LAB-A', resume:pathFor('geo'), speed:'4x', avoid_mm:[], sectors:140000,
    }));
  }
  await load('media');
  assert.match(await evaluate('document.querySelector("#cal").textContent'), /discprobe checkburn --drive "X:"/);
  assert.match(await evaluate('document.querySelector("#cal").textContent'), /rear USB 3\.0/);
  await evaluate(`Object.defineProperty(navigator, 'clipboard', {value:{writeText(text){window.copiedDiag=text;}}});`);
  await cdp('Page.setDownloadBehavior', {behavior:'allow', downloadPath:profile});
  await click('#real-copy-diagnostics');
  await click('#real-download-diagnostics');
  const diagnosticText = await evaluate('window.copiedDiag');
  const download = join(profile, 'disc-probe-diagnostics.txt');
  await until(() => existsSync(download), 'diagnostic text downloaded');
  assert.match(diagnosticText, /3\/11\/00/);
  assert.match(diagnosticText, /Command run: python -m discprobe calibrate --drive X:/);
  assert.match(diagnosticText, /Job log: .webui-jobs\/j-seed\/output.log/);
  assert.equal(readFileSync(download, 'utf8'), diagnosticText);
  await load('media');
  started.length = 0;
  blankInserted = true;
  await click('#next');
  await until(() => started.length === 1 && evaluate('document.querySelector("#next-text").textContent === "Make measurement image"'),
    'media recovery checks the replacement disc');
  await click('#next');
  await until(() => evaluate('!!document.querySelector("#real-burn-speed")'), 'write speeds offered for replacement measurement disc');
  assert.deepEqual(started[0], sent('info', {}));
  assert.match(started[1].args.output, /^iso\/dvd-measurement-\d+\.iso$/);
  assert.deepEqual(started[1], {action:'random', media:'dvd', args:{sectors:137200, output:started[1].args.output}});
  await load('burn');
  started.length = preflight.length = 0;
  blankInserted = true;
  await click('#next');
  await click('#next');
  await until(() => evaluate('!!document.querySelector("#real-name") || document.querySelector("#cal h2").textContent.includes("blank")'), 'replacement blank checked');
  await click('#next');
  await until(() => evaluate('!!document.querySelector("#real-burn-speed")'), 'write-speed options from fresh preflight');
  assert.deepEqual(await evaluate(`[...document.querySelector('#real-burn-speed').options].map(option => option.value)`), ['', '4', '8']);
  await evaluate(`(() => {const select=document.querySelector('#real-burn-speed');select.value='4';
    select.dispatchEvent(new Event('change'));document.querySelector('.next-confirm .kit-slide-knob').focus();})()`);
  assert.deepEqual(started.map(p => p.action), ['info']);
  await cdp('Input.dispatchKeyEvent', {type:'keyDown', key:' ', code:'Space', windowsVirtualKeyCode:32});
  await delay(1150);
  await cdp('Input.dispatchKeyEvent', {type:'keyUp', key:' ', code:'Space', windowsVirtualKeyCode:32});
  await until(() => started.length > 1, 'confirmed lower-speed burn');
  const {preset, ...args} = started[1].args;
  assert.match(preset, /^presets\/calibration-\d+\.json$/);
  assert.deepEqual({...started[1], args}, {...sent('calibrate',
    {iso:'iso/measurement.iso', mid:'LAB-A', burn_speed:4, speed:'4x', avoid_mm:[], sectors:140000}), burn_token:'test-token'});
  assert.ok(preflight.slice(-2).every(p => p.args.burn_speed === 4));
  assert.deepEqual(await evaluate('window.retryErrors'), []);
  await load('burn-stall');
  await until(() => evaluate(`document.querySelector('#cal').textContent.includes('If progress stops moving')`), 'stalled burn guidance');
  assert.equal(await evaluate('document.querySelector("#job-cancel").disabled'), false);
  console.log('Web retry passed: 12 read retries, 2 continuations, copy and export, and guarded write-speed retry.');
}
