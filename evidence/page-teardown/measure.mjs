// Run from the repository root with Node 22+ and the Disc Probe Python dependencies.
import assert from 'node:assert/strict';
import {execFile, execFileSync, spawn} from 'node:child_process';
import {once} from 'node:events';
import {existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync} from 'node:fs';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';
import {promisify} from 'node:util';
import {devToolsPortFile, launchBrowser, removeProfile, selectBrowser, stopBrowser} from '../../tests/browser.mjs';

const here = fileURLToPath(new URL('.', import.meta.url));
const tmp = resolve('D:/dp-dev/tmp/pageteardown');
const edge = selectBrowser({legacy: ['PAGEMEM_EDGE'], edgeOnly: true});
const python = process.env.PYTHON ?? 'python';
const system = fileURLToPath(new URL('windows.ps1', import.meta.url));
const queryWindows = promisify(execFile);
const workPath = '/home/pagemem-work.png';
const transparent = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg==';
const restricted = /[b][l][i][n][d]/i;
const allowedRasters = /\.(png|jpe?g|webp|gif|avif|bmp|ico|svg)(?:$|\?)/i;
const viewports = [[1366, 768], [390, 844]];
const cfgs = viewports.flatMap(([width, height], index) => ['light', 'dark'].flatMap((theme, i) =>
  Boolean(index ^ i) ? ['transparent', 'normal'].map(images => ({width, height, theme, images})) :
    ['normal', 'transparent'].map(images => ({width, height, theme, images}))));
const keyFor = ({width, height, theme, images}) => `${width}x${height}-${theme}-${images}`;
const options = process.argv.slice(2);
const run = options.find(arg => arg.startsWith('--run='))?.slice(6) ?? 'after';
assert.match(run, /^(before|after)$/);
const source = resolve(options.find(arg => arg.startsWith('--source='))?.slice(9) ?? '.');
assert.ok(!restricted.test(source), 'Restricted source path');
const selected = options.find(arg => arg.startsWith('--only='))?.slice(7);
const headless = options.includes('--headless');
const smoke = options.includes('--smoke');
const visual = options.includes('--visual');
const software = options.includes('--software');
const control = options.includes('--control');
const resume = options.includes('--resume');
const settle = smoke || visual ? 0 : 30_000;
assert.ok(options.every(arg => ['--headless', '--smoke', '--resume', '--visual', '--software', '--control'].includes(arg) || /^--(?:only|run|source)=/.test(arg)), 'Unknown option');
assert.ok(!software || visual, '--software is for screenshots only');
assert.ok(!control || (visual && !software), '--control is for hardware screenshots only');
assert.ok(!smoke || selected, '--smoke requires --only');
assert.ok(!selected || cfgs.some(cfg => keyFor(cfg) === selected), 'Unknown configuration');

async function until(read, label, timeout = 60_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = await read();
    if (value) return value;
    await delay(200);
  }
  throw Error(`Timed out: ${label}`);
}

async function windows(action, profile, pid) {
  const args = ['-NoProfile', '-NonInteractive', '-File', system, '-Action', action];
  if (profile) args.push('-Profile', profile, '-BrowserPid', String(pid));
  const {stdout:output} = await queryWindows('powershell.exe', args, {windowsHide:true, encoding:'utf8', timeout:30_000});
  if (output.trim()) return JSON.parse(output);
}

function loopback(port) {
  assert.match(String(port), /^\d+$/);
  assert.ok(+port > 1024 && +port < 65536 && +port !== 8765, 'Unsafe port');
  return `http://127.0.0.1:${port}`;
}

async function connect(url, handle) {
  const socket = new WebSocket(url);
  const waiting = new Map();
  let sequence = 0;
  await Promise.race([once(socket, 'open'), delay(10_000, undefined, {ref:false}).then(() => { throw Error('CDP connection timed out'); })]);
  socket.addEventListener('message', ({data}) => {
    const event = JSON.parse(data);
    waiting.get(event.id)?.(event);
    if (event.method) handle(event);
  });
  return {
    socket,
    command(method, params = {}, sessionId) {
      return new Promise((accept, reject) => {
        const id = ++sequence;
        const timer = setTimeout(() => { waiting.delete(id); reject(Error(`CDP timeout: ${method}`)); }, 15_000);
        waiting.set(id, event => {
          clearTimeout(timer);
          waiting.delete(id);
          if (event.error) reject(Error(`${method}: ${event.error.message}`));
          else accept(event.result);
        });
        socket.send(JSON.stringify({id, method, params, sessionId}));
      });
    },
  };
}

const pageAssets = `(() => {
  const result = [];
  const forbidden = /[b][l][i][n][d]/i;
  const urlOf = value => {
    if (!value) return '';
    const url = new URL(value, location.href);
    if (url.origin !== location.origin || forbidden.test(decodeURIComponent(url.pathname))) return '';
    return url.pathname;
  };
  for (const node of document.querySelectorAll('*')) {
    const rect = node.getBoundingClientRect();
    for (const pseudo of [null, '::before', '::after']) {
      const css = getComputedStyle(node, pseudo);
      if (pseudo && ['none','normal'].includes(css.content)) continue;
      const tracked = [css.backgroundImage, css.maskImage, css.content];
      if (node.tagName === 'IMG' && !pseudo && node.naturalWidth) {
        const src = urlOf(node.currentSrc);
        if (src) result.push({src, kind:'img', width:rect.width, height:rect.height,
          intrinsic_width:node.naturalWidth, intrinsic_height:node.naturalHeight,
          size:css.objectFit, box_width:node.clientWidth, box_height:node.clientHeight});
      }
      for (const [index, value] of tracked.entries()) {
        for (const match of (value ?? '').matchAll(/url\\(["']?([^"')]+)["']?\\)/g)) {
          const src = urlOf(match[1]);
          if (!src) continue;
          const number = text => text.endsWith('px') ? parseFloat(text) : 0;
          const width = pseudo ? number(css.width) || rect.width : rect.width;
          const height = pseudo ? number(css.height) || rect.height : rect.height;
          result.push({src, width, height, box_width:pseudo ? width : node.clientWidth,
            box_height:pseudo ? height : node.clientHeight, kind:['background','mask','content'][index],
            size:[css.backgroundSize,css.maskSize,'auto'][index]});
        }
      }
    }
  }
  return result.filter(row => row.width > 0 && row.height > 0);
})()`;

async function measure(config, output, imageBody) {
  const {width, height, theme, images} = config;
  const key = keyFor(config);
  const disks = await windows('disks');
  assert.ok(disks.length === 2 && disks.every(disk => disk.Free >= 5_000_000_000),
    `D/F disk space below 5 GB: ${JSON.stringify(disks)}`);
  const dir = mkdtempSync(join(tmp, 'run-'));
  const lab = join(dir, 'lab');
  const local = join(dir, 'local');
  mkdirSync(local);
  const env = {...process.env, LOCALAPPDATA:local, DISCPROBE_HOME:lab, TEMP:tmp, TMP:tmp,
    DISCPROBE_WORKERS:'2', PYTHONDONTWRITEBYTECODE:'1', PYTHONIOENCODING:'utf-8'};
  for (const name of ['RUNJOB_MEMORY', 'DISCPROBE_TEXLIB', 'DISCPROBE_DISCLAB', 'DISC_PROBE_NO_DRIVES', 'PYTHONPATH']) delete env[name];
  const server = spawn(python, ['-X','utf8','-B',join(source, 'tests/running_job_lab_fixture.py'),lab], {cwd:source, env, windowsHide:true});
  let log = '', browser, cdp, listening, session, fault, done = false;
  server.on('error', error => { fault = error; });
  server.stdout.on('data', bytes => { log += bytes; });
  server.stderr.on('data', bytes => { log += bytes; });
  const samples = [], stills = {}, urls = new Map(), imageResponses = new Map(), exceptions = [];
  const persist = () => writeFileSync(join(output, `${key}.json`), JSON.stringify({config, headless, samples, stills, exceptions, done}, null, 2) + '\n');
  try {
    const port = await until(() => {
      if (fault || server.exitCode !== null) throw fault ?? Error(`Lab exited with ${server.exitCode}`);
      return log.match(/^http:\/\/127\.0\.0\.1:(\d+)\/home\/\?token=[A-Za-z0-9_-]+\r?$/m)?.[1];
    }, 'isolated Disc Lab port');
    listening = loopback(port);
    const answers = JSON.parse(readFileSync(join(lab, 'answers.json'), 'utf8'));
    const state = JSON.parse(readFileSync(join(lab, 'state.json'), 'utf8'));
    const discCapacity = answers.discs[state.drives['X:'].tray].capacity;
    const request = async path => {
      const response = await fetch(listening + path, {redirect:'error', signal:AbortSignal.timeout(4_000)});
      assert.ok(response.ok, `${path}: HTTP ${response.status}`);
      return response.json();
    };
    await until(() => request('/api/state').catch(() => null), 'isolated lab HTTP ready');
    browser = launchBrowser(edge, undefined, [
      '--disable-sync',
      '--disable-component-update',
      '--disable-features=msEdgeSidebarV2,msEdgeShopping,msEdgeRewards,CalculateNativeWinOcclusion',
      '--disable-backgrounding-occluded-windows',
      '--mute-audio', '--remote-debugging-port=0',
      '--proxy-server=127.0.0.1:9', `--proxy-bypass-list=<-loopback>;127.0.0.1:${port}`,
      '--force-device-scale-factor=1', '--window-position=0,0', `--window-size=${width},${height}`,
      ...(software ? ['--disable-lcd-text'] : []),
      'about:blank',
    ], {env, headless, disableGpu:software, windowsHide:headless, stdio:'ignore'});
    const portFile = devToolsPortFile(browser);
    const profile = dirname(portFile);
    browser.on('error', error => { fault = error; });
    const debugPort = await until(() => {
      if (fault || browser.exitCode !== null) throw fault ?? Error(`Edge exited with ${browser.exitCode}`);
      try { return readFileSync(portFile, 'utf8').split(/\r?\n/)[0]; } catch {}
    }, 'private Edge CDP port', 30_000);
    const debug = loopback(debugPort);
    const version = await fetch(debug + '/json/version', {signal:AbortSignal.timeout(4000)}).then(r => r.json());
    assert.equal(new URL(version.webSocketDebuggerUrl).host, new URL(debug).host);
    cdp = await connect(version.webSocketDebuggerUrl, event => {
      const {method, params, sessionId} = event;
      if (sessionId !== session) return;
      if (method === 'Runtime.exceptionThrown') exceptions.push(params.exceptionDetails.exception?.description ?? params.exceptionDetails.text);
      if (method === 'Page.javascriptDialogOpening' && params.type === 'beforeunload') {
        cdp.command('Page.handleJavaScriptDialog', {accept:true}, session).catch(() => {});
      }
      if (method === 'Fetch.requestPaused') {
        const {requestId, resourceType, request} = params;
        const url = new URL(request.url);
        const path = decodeURIComponent(url.pathname);
        const action = url.origin !== listening || restricted.test(path) ?
          ['Fetch.failRequest', {requestId, errorReason:'BlockedByClient'}] :
          (path === workPath || (images === 'transparent' && resourceType === 'Image')) ?
            ['Fetch.fulfillRequest', {requestId, responseCode:200, responseHeaders:[{name:'Content-Type', value:'image/png'}],
              body:images === 'transparent' ? transparent : imageBody}] : ['Fetch.continueRequest', {requestId}];
        cdp.command(...action, session).catch(error => { fault = error; });
      }
      if (method === 'Network.responseReceived') {
        const url = new URL(params.response.url);
        if (url.origin === listening && !restricted.test(decodeURIComponent(url.pathname)) &&
            (params.type === 'Image' || allowedRasters.test(url.pathname) || params.response.mimeType.startsWith('image/'))) {
          imageResponses.set(params.requestId, {src:url.pathname, type:params.type,
            mime:params.response.mimeType, status:params.response.status});
        }
      }
      if (method === 'Network.loadingFinished' && imageResponses.has(params.requestId)) {
        const asset = imageResponses.get(params.requestId);
        urls.set(asset.src, {...asset, encoded_bytes:params.encodedDataLength});
        imageResponses.delete(params.requestId);
      }
    });
    const pages = await until(async () => {
      const {targetInfos} = await cdp.command('Target.getTargets');
      const pages = targetInfos.filter(target => target.type === 'page');
      return pages.length && pages;
    }, 'Edge created a page');
    const {targetId} = pages.find(page => page.url === 'about:blank') ?? pages[0];
    for (const page of pages) {
      if (page.targetId !== targetId) await cdp.command('Target.closeTarget', {targetId:page.targetId});
    }
    ({sessionId:session} = await cdp.command('Target.attachToTarget', {targetId, flatten:true}));
    const command = (method, params) => cdp.command(method, params, session);
    const evaluate = async expression => {
      const reply = await command('Runtime.evaluate', {expression, returnByValue:true, awaitPromise:true});
      if (reply.exceptionDetails) throw Error(reply.result.description ?? reply.exceptionDetails.text);
      return reply.result.value;
    };
    const waitPage = (expression, label) => until(() => evaluate(expression), label);
    const click = selector => evaluate(`(() => {const node = document.querySelector(${JSON.stringify(selector)});
      if (!node || node.disabled) throw Error('Cannot click ' + ${JSON.stringify(selector)}); node.click();})()`);
    const inMode = mode => `document.documentElement.dataset.mode === ${JSON.stringify(mode)}`;
    const inHome = home => `!document.documentElement.dataset.mode && document.documentElement.dataset.home === ${JSON.stringify(home)}`;
    const ready = `document.documentElement.dataset.navigation === 'ready'`;
    const at = view => `${ready} && location.hash === '#/${view}'`;
    const {windowId} = await cdp.command('Browser.getWindowForTarget', {targetId});
    if (!headless) await cdp.command('Browser.setWindowBounds', {windowId, bounds:{left:0, top:0, width, height}});
    await command('Page.enable');
    await command('Network.enable');
    await command('Runtime.enable');
    await command('Fetch.enable', {patterns:[{urlPattern:'*'}]});
    await command('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor:1, mobile:false});
    await command('Page.addScriptToEvaluateOnNewDocument', {source:`if (location.origin === ${JSON.stringify(listening)}) {
      localStorage.setItem('dp-theme', ${JSON.stringify(theme)}); localStorage.setItem('dp-lang','zh');
      ${visual ? `localStorage.setItem('dp-motion', 'off'); localStorage.setItem('dp-sound', 'off');
        const NativeDate = Date;
        window.Date = class extends NativeDate {
          constructor(...args) { super(...(args.length ? args : ['2026-11-23T15:00:00-05:00'])); }
        };
        let seed = 251; Math.random = () => ((seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 2 ** 32);` : ''}
    }`});
    const {auxAttributes, devices} = (await cdp.command('SystemInfo.getInfo')).gpu;
    const meta = {edge:version.Browser, user_agent:version['User-Agent'], browser_pid:browser.pid,
      gpu_renderer:auxAttributes.glRenderer, gpu_devices:devices};
    await command('Page.navigate', {url:'about:blank'});
    await waitPage(`location.href === 'about:blank'`, 'blank page loaded');

    const shotDir = join(tmp, control ? 'shots-control' : software ? 'shots-software' : 'shots', run, key);
    if (visual) mkdirSync(shotDir, {recursive:true});
    const shot = async name => {
      const {data} = await command('Page.captureScreenshot', {format:'png', captureBeyondViewport:false});
      writeFileSync(join(shotDir, `${name}.png`), Buffer.from(data, 'base64'));
    };
    const recordedLobby = `(() => {
      const hello = document.querySelector('#lobby-hello').textContent.trim();
      const checked = document.querySelector('#lobby-disc-time').textContent.trim();
      const recent = document.querySelector('#lobby-recent button')?.textContent.trim() ?? '';
      if (document.querySelector('#drivebar').dataset.state !== 'recorded' ||
          document.querySelector('#lobby-disc-actions').hidden || document.querySelector('#lobby-disc-check').disabled ||
          !hello.endsWith('\u5df2\u5199\u8fc7') || !checked.endsWith('\u521a\u521a')) return null;
      return {hello, checked, recent};
    })()`;
    async function still(name, progress = null) {
      if (!visual) return;
      await evaluate(`(async () => {
        await document.fonts.ready;
        await Promise.race([Promise.allSettled([...document.images].filter(i => i.src && i.getClientRects().length).map(i => i.decode())),
          new Promise(resolve => setTimeout(resolve, 1000))]);
        document.activeElement?.blur?.();
      })()`);
      await delay(name === 'return' ? 1800 : 650);
      const lobby = name === 'lobby' || name === 'return';
      if (lobby) {
        // A new drive check can start while the scene is settling. The heading,
        // read time and draft must agree on both sides of the actual capture.
        const checkedShot = capture => until(async () => {
          const state = await evaluate(recordedLobby);
          if (!state || (name === 'return' && state.recent !== 'PT sample')) return false;
          await delay(250);
          if (JSON.stringify(await evaluate(recordedLobby)) !== JSON.stringify(state)) return false;
          await shot(capture);
          if (JSON.stringify(await evaluate(recordedLobby)) !== JSON.stringify(state)) return false;
          return state;
        }, `${name}: recorded disc and heading are stable during capture`);
        stills[`${name}Disc`] = await checkedShot(name);
        if (control && name === 'return') {
          stills.returnRepeats = {};
          for (const [index, wait] of [600, 1800].entries()) {
            await delay(wait);
            const capture = `return-repeat-${index + 1}`;
            stills.returnRepeats[capture] = await checkedShot(capture);
          }
        }
      }
      stills[name] = await evaluate(`({scrollWidth:document.documentElement.scrollWidth, scrollHeight:document.documentElement.scrollHeight,
        width:innerWidth, height:innerHeight, active:document.activeElement?.id, title:document.title,
        animations:document.getAnimations().filter(animation => animation.playState === 'running').length})`);
      if (name === 'geometry') {
        stills.geometry.progress = progress;
        // Keep the header bounds. On desktop its center also contains the progress rail.
        stills.geometry.header = await evaluate(`(() => {
          const r = document.querySelector('.top').getBoundingClientRect();
          return [0, 0, innerWidth, Math.ceil(r.bottom)];
        })()`);
      }
      if (!lobby) await shot(name);
    }
    async function frames(name, expression, count = 10) {
      await waitPage(expression, `${name} starts`);
      for (let i = 0; i < count; i++) {
        await shot(`${name}-${String(i).padStart(2, '0')}`);
        if (i + 1 < count) await delay(45);
      }
    }
    const motion = value => click(`#set-menu [data-motion="${value}"]`);

    async function sample(scene, geometry = null) {
      if (visual) {
        const progress = await geometry?.();
        if (scene !== 'blank') await still(scene, progress);
        return;
      }
      let start;
      const visible = `document.visibilityState === 'visible'`;
      for (let attempt = 0; attempt < 3; attempt++) {
        if (!await evaluate(visible)) await command('Page.bringToFront');
        await waitPage(visible, 'measurement tab is visible');
        start = performance.now();
        console.log(key, scene, 'settling');
        await delay(settle);
        if (await evaluate(visible)) break;
        console.log(key, scene, 'tab hidden, restarting the idle interval');
        if (attempt === 2) throw Error('Measurement tab cannot stay visible');
      }
      if (fault) throw fault;
      const {processInfo} = await cdp.command('SystemInfo.getProcessInfo');
      const native = await windows('edge', profile, browser.pid);
      const idleSeconds = (performance.now() - start) / 1000;
      const types = new Map(processInfo.map(p => [p.id, p.type]));
      assert.ok(native.rows.some(p => p.process_type === 'browser'));
      assert.ok(native.rows.some(p => p.process_type === 'renderer'));
      const omitted = processInfo.filter(p => !native.rows.some(row => row.pid === p.id));
      const heap = await command('Runtime.getHeapUsage');
      const dom = await command('Memory.getDOMCounters');
      const viewport = await evaluate(`({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,
        visible:document.visibilityState, screen_width:screen.width, screen_height:screen.height,
        reduced_motion:matchMedia('(prefers-reduced-motion: reduce)').matches,
        theme:document.documentElement.dataset.theme || '', mode:document.documentElement.dataset.mode || '',
        home:document.documentElement.dataset.home || ''})`);
      assert.deepEqual([viewport.width, viewport.height, viewport.dpr, viewport.visible], [width, height, 1, 'visible']);
      if (scene !== 'blank') assert.equal(viewport.theme, theme);
      const {bounds} = await cdp.command('Browser.getWindowBounds', {windowId});
      const geo = geometry ? await geometry() : null;
      const assets = [...urls.values()];
      const displayed = scene === 'blank' ? [] : await evaluate(pageAssets);
      if (scene === 'editor') {
        const layer = await evaluate(`(async () => {
          const plan = (await import('./design.js')).editorActions().state();
          const layer = plan.layers.find(row => row.file?.name === 'pagemem-work.png');
          const disc = document.querySelector('.ed-disc-shadow').getBoundingClientRect().width;
          return {width:layer.width * disc / 120, height:layer.width * layer.h / layer.w * disc / 120,
            intrinsic_width:layer.w, intrinsic_height:layer.h};
        })()`);
        assert.deepEqual([layer.intrinsic_width, layer.intrinsic_height], images === 'normal' ? [1600,1600] : [1,1]);
        displayed.push({src:workPath, kind:'editor-canvas', size:'', ...layer});
      }
      samples.push({scene, time:native.time, idle_seconds:idleSeconds,
        meta, viewport, bounds, geometry:geo, heap, dom, omitted, assets, displayed,
        processes:native.rows.map(row => ({...row, cdp_type:types.get(row.pid) ?? ''}))});
      persist();
      console.log(key, scene, 'sampled', native.rows.length, 'Edge processes');
    }

    await sample('blank');
    await command('Page.navigate', {url:listening + '/home/'});
    await waitPage(`${at('lobby')} && ${inHome('lobby')}`, 'lobby loaded');
    await sample('lobby');
    if (visual) {
      for (const [mode, entry, content] of [
        ['pastworks', '#lobby-open', '.pw-grid'], ['presets', '#presetio-entry', '.presetio-stage'],
        ['faxnews', '.lb-hit[data-target="faxnews"]', '.fx-notice'],
      ]) {
        await waitPage(`!!document.querySelector(${JSON.stringify(entry)}) && !document.querySelector(${JSON.stringify(entry)}).hidden`, `${mode} entry available`);
        await click(entry);
        await waitPage(`${inMode(mode)} && !!document.querySelector(${JSON.stringify(content)})`, `${mode} visible`);
        await still(mode);
        await click('#back');
        await waitPage(`${at('lobby')} && ${inHome('lobby')}`, `${mode} closed`);
      }
    }
    await click('#library');
    await waitPage(`${at('library')} && ${inHome('library')}`, 'library opened');
    await sample('library');
    await click('#back');
    await waitPage(`${at('lobby')} && ${inHome('lobby')}`, 'library returned to lobby');
    await click('#next');
    await waitPage(`${at('newplan')} && ${inMode('newplan')} && !!document.querySelector('#np-batch')`, 'New Work opened');
    if (visual) await evaluate(`(() => {
      const name = document.querySelector('.np-name'); name.value = 'PT sample';
      name.dispatchEvent(new Event('input', {bubbles:true}));
    })()`);
    await still('newplan');
    await evaluate(`(() => {const batch = document.querySelector('#np-batch');
      batch.value = 'DLABR01'; batch.dispatchEvent(new Event('input', {bubbles:true}));
    })()`);
    await waitPage(`document.querySelector('.np-cal-go')?.offsetWidth > 0`, 'New Work calibration button');
    if (visual) await motion('on');
    await click('.np-cal-go');
    if (visual) {
      await frames('envelope', `document.querySelector('.np')?.classList.contains('filing')`);
      await waitPage(`${inMode('cal')} && !document.documentElement.classList.contains('pan-in') && !document.querySelector('.np-card-env')`, 'calibration entrance completes');
      await motion('off');
      await still('calibration');
      await motion('on');
    }
    await waitPage(`${inMode('cal')} && !document.querySelector('#next').disabled`, 'initial calibration inspection');
    await click('#next');
    await waitPage(`!!document.querySelector('#measurement-confirm')`, 'recorded DVD confirmed by inspection');
    if (visual) {
      await frames('load-disc', `!document.querySelector('.ld')?.hidden && !!document.querySelector('.ld-world [data-file="tray"]')?.currentSrc`);
      await motion('off');
    }
    await click('#measurement-confirm');
    await evaluate(`(() => {const capacity = document.querySelector('#real-capacity');
      if (capacity) { capacity.value = ${JSON.stringify(String(discCapacity))}; capacity.dispatchEvent(new Event('input')); }
    })()`);
    await waitPage(`!document.querySelector('#next').disabled`, 'measurement is available');
    await click('#next');
    const active = await until(async () => {
      const state = await request('/api/state');
      return state.jobs.find(job => job.action === 'calibrate' && job.exit === null);
    }, 'live calibration job');
    const job = () => request('/api/jobs/' + active.id);
    const geoStart = state => state.events.findIndex(event => event.type === 'step' && event.name === 'geo');
    await until(async () => {
      if (existsSync(join(lab, 'midpoint'))) return true;
      const state = await job();
      assert.equal(state.exit, null, JSON.stringify(state.result));
    }, 'Disc Lab reached the geometry midpoint', 150_000);
    await waitPage(`${inMode('cal')} && document.querySelector('#job-name').textContent.trim() === '\u6d4b\u51e0\u4f55'`, 'geometry view active');
    await sample('geometry', async () => {
      const state = await job();
      const start = geoStart(state);
      assert.ok(start >= 0 && state.exit === null, 'Geometry ended before the sample');
      const last = state.events.slice(start).findLast(event => event.type === 'progress');
      assert.ok(last?.fraction >= .48 && last.fraction <= .55, 'Geometry sample must be near halfway');
      return last.fraction;
    });
    writeFileSync(join(lab, 'continue'), '');
    await until(async () => {
      const state = await job();
      if (state.exit === null) return false;
      assert.equal(state.exit, 0, JSON.stringify(state.result));
      return true;
    }, 'measurement completed', 150_000);
    await waitPage(`${inMode('cal')} && !document.querySelector('#next').disabled &&
      document.querySelector('#next-text').textContent.trim() === '\u4fdd\u5b58\u6d4b\u91cf'`, 'visible measurement result');
    await click('#back');
    await waitPage(`(${at('newplan')} && ${inMode('newplan')}) || (${at('lobby')} && ${inHome('lobby')})`, 'calibration left');
    if (await evaluate(inHome('lobby'))) await click('#lobby-new');
    await waitPage(`${at('newplan')} && ${inMode('newplan')} && document.querySelector('.np-sheet')?.offsetWidth > 0 && !document.querySelector('#next').disabled`, 'New Work can open editor');
    await click('#next');
    await waitPage(`${inMode('design')} && document.querySelector('canvas.main')?.offsetWidth > 0`, 'editor opened');
    await evaluate(`(async () => {
      const response = await fetch(${JSON.stringify(workPath)});
      if (!response.ok) throw Error('Could not load test artwork');
      const transfer = new DataTransfer();
      transfer.items.add(new File([await response.blob()], 'pagemem-work.png', {type:'image/png'}));
      const input = document.querySelector('.f-img');
      input.files = transfer.files; input.dispatchEvent(new Event('change', {bubbles:true}));
    })()`);
    await waitPage(`(async () => (await import('./design.js')).editorActions().state().layers.some(row => row.file?.name === 'pagemem-work.png'))()`, 'artwork imported');
    await sample('editor');
    if (visual) {
      await click('#next');
      await waitPage(`${inMode('preview')} && !!document.querySelector('.pv canvas')?.width`, 'preview opened');
      await still('preview');
      await click('#back');
      await waitPage(`${at('design')} && ${inMode('design')}`, 'preview returns to editor');
      await click('[data-ed-tool="shape"]');
      const [x0, y0, x1, y1] = await evaluate(`(() => {
        const r = document.querySelector('.ed-disc-shadow').getBoundingClientRect();
        return [r.left + .72*r.width, r.top + .43*r.height, r.left + .83*r.width, r.top + .55*r.height];
      })()`);
      await command('Input.dispatchMouseEvent', {type:'mousePressed', x:x0, y:y0, button:'left', buttons:1, clickCount:1});
      await command('Input.dispatchMouseEvent', {type:'mouseMoved', x:x1, y:y1, button:'left', buttons:1});
      await command('Input.dispatchMouseEvent', {type:'mouseReleased', x:x1, y:y1, button:'left', clickCount:1});
      await waitPage(`(async () => (await import('./design.js')).editorActions().state().layers.some(row => row.shape?.type === 'rectangle'))()`, 'rectangle drawn in the editor');
      await command('Input.dispatchMouseEvent', {type:'mouseMoved', x:1, y:1});
    }
    const designState = `(async () => {
      const actions = (await import('./design.js')).editorActions();
      return {dirty:actions.state().dirty, text:await actions.projectText(),
        thumbnails:[...document.querySelectorAll('.lays canvas')].map(canvas => canvas.toDataURL())};
    })()`;
    const draft = visual ? await evaluate(designState) : null;
    await waitPage(ready, 'navigation ready before leaving the editor');
    await click('#back');
    await waitPage(`${at('lobby')} && ${inHome('lobby')}`, 'editor returned to lobby');
    await sample('return');
    if (visual) {
      const recent = '#lobby-recent button';
      await waitPage(`!!document.querySelector(${JSON.stringify(recent)})`, 'recent draft shown in lobby');
      await click(recent);
      await waitPage(`${inMode('design')} && document.querySelector('canvas.main')?.offsetWidth > 0`, 'draft reopened');
      assert.ok(draft.dirty);
      assert.deepEqual(await evaluate(designState), draft);
      await still('reopen');
    }
    done = true;
    persist();
  } catch (error) {
    if (cdp && session) {
      const state = await cdp.command('Runtime.evaluate', {returnByValue:true,
        expression:`({mode:document.documentElement.dataset.mode, home:document.documentElement.dataset.home,
        navigation:document.documentElement.dataset.navigation, hash:location.hash,
        next:document.querySelector('#next-text')?.textContent, cal:document.querySelector('#cal')?.innerText,
        newwork:document.querySelector('.np-disc-help')?.textContent})`}, session).catch(() => null);
      console.error(key, state?.result.value, exceptions);
    }
    throw error;
  } finally {
    try {
      await stopBrowser(browser, cdp?.socket);
    } finally {
      try {
        if (server.pid && server.exitCode === null && server.signalCode === null) {
          assert.notEqual(server.pid, 12472);
          execFileSync('taskkill.exe', ['/PID', String(server.pid), '/T', '/F'], {windowsHide:true, stdio:'ignore'});
          await Promise.race([once(server, 'exit'), delay(3000)]);
        }
        if (existsSync(lab)) removeProfile(lab, dir);
        if (existsSync(local)) removeProfile(local, dir);
      } finally {
        writeFileSync(join(dir, 'server.log'), log.replace(/token=[A-Za-z0-9_-]+/g, 'token=[redacted]'));
      }
    }
    if (done) console.log(key, 'complete');
  }
}

assert.equal(process.platform, 'win32');
mkdirSync(tmp, {recursive:true});
process.env.TEMP = process.env.TMP = tmp;
const output = join(tmp, run, control ? 'visual-control' : software ? 'visual-software' : visual ? 'visual' : smoke ? 'smoke' : 'samples');
mkdirSync(output, {recursive:true});
const artwork = join(tmp, 'pagemem-work.png');
execFileSync(python, ['-X','utf8','-B',join(here, 'artwork.py'),artwork], {windowsHide:true});
const imageBody = readFileSync(artwork).toString('base64');
for (const config of cfgs.filter(config => selected ? keyFor(config) === selected : config.images === 'normal' && (visual || config.width === 1366))) {
  const previous = join(output, `${keyFor(config)}.json`);
  if (resume && !visual && existsSync(previous)) {
    const data = JSON.parse(readFileSync(previous, 'utf8'));
    if (data.done && data.samples.length === 6 && data.headless === headless) continue;
  }
  await measure(config, output, imageBody);
}
