// Real CLI child + HTTP backend + shipped editor. Synthetic data, zero devices.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {existsSync, readFileSync} from 'node:fs';
import {mkdtemp, readFile, writeFile, rm, mkdir} from 'node:fs/promises';
import {join, resolve, dirname} from 'node:path';
import {tmpdir} from 'node:os';
import {spawn} from 'node:child_process';
import {once} from 'node:events';

const edge = process.env.KIT_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const home = new URL('../discprobe/web/home/', import.meta.url);
const index = readFileSync(new URL('index.html', home), 'utf8');
const source = readFileSync(new URL('curve-edit.js', home), 'utf8');
// Test the display scale without adding exports to the shipped module's API.
const {curveTicks} = await import('data:text/javascript;base64,' + Buffer.from(
  source.replace("'./kit/shared.js'", JSON.stringify(new URL('kit/shared.js', home).href)) + '\nexport {curveTicks};'
).toString('base64'));
const pause = ms => new Promise(done => setTimeout(done, ms));

test('curve display ticks: 3–5 nice steps, zero, bounds and finite labels', () => {
  for (const values of [[0,0], [.02,.1], [-5.1,-4.9,0], [1,1.5], [-1.5,-1], [-10,10], [-.001,.001], [100,300], [-800,-100]]) {
    const ticks = curveTicks(values);
    assert.ok(ticks.values.length >= 3 && ticks.values.length <= 5);
    assert.ok(ticks.values.includes(0));
    assert.ok(ticks.values[0] <= Math.min(...values));
    assert.ok(ticks.values.at(-1) >= Math.max(...values));
    const factor = ticks.step / 10 ** Math.floor(Math.log10(ticks.step));
    assert.ok([1,2,5].some(n => Math.abs(n - factor) < 1e-10));
    assert.ok(ticks.values.every(Number.isFinite));
  }
});
test('curve editing: real CLI rejection, save gate, keyboard and responsive layout', {skip:!existsSync(edge), timeout:90000}, async () => {
  const dir = await mkdtemp(join(tmpdir(), 'discprobe-curve-'));
  let browser, server, ws;
  const stop = async process => {
    if (process && process.exitCode === null) { process.kill(); await Promise.race([once(process, 'exit'), pause(3000)]); }
  };
  try {
    const html = `<!doctype html><html lang="zh" data-motion="off"><head><meta charset="utf-8">
      <style>${index.match(/<style>([\s\S]*?)<\/style>/)[1]}</style>
      <link rel="stylesheet" href="/home/kit/kit.css"><link rel="stylesheet" href="/home/curve-edit.css">
      <style>body{overflow:auto;display:block;padding:24px;box-sizing:border-box}main.cal{position:static!important;inset:auto!important;transform:none!important;width:min(100%,700px)!important;margin:0 auto;display:block!important;padding:0!important}h2{margin-bottom:16px!important}p{margin-block:12px}details summary{min-height:44px;cursor:pointer}</style>
      </head><body><main class="cal"><h2>测量结果</h2><p>合成数据验收 · 无光驱、无实盘</p><div id="editor"></div></main>
      <script type="module">import {curveEditor} from '/home/curve-edit.js';import {job} from '/home/api.js';
      window.editor=curveEditor(document.querySelector('#editor'),{run:'geo',job,state:{open:true}});</script></body></html>`;
    await writeFile(join(dir, 'fixture.html'), html, 'utf8');
    server = spawn(process.env.PYTHON || 'python', ['-B', '-m', 'tests.curve_edit_server', dir], {stdio:['ignore','ignore','pipe'],windowsHide:true});
    // tests is not required to be a package: use a path with the checkout on PYTHONPATH.
    let serverError = ''; server.stderr.on('data', data => { serverError += data; });
    const deadline = Date.now() + 25000;
    let url;
    while (Date.now() < deadline) {
      try { url = await readFile(join(dir, 'server-url.txt'), 'utf8'); break; } catch {}
      if (server.exitCode !== null) throw new Error(serverError);
      await pause(100);
    }
    assert.ok(url, serverError);
    const profile = join(dir, 'profile');
    browser = spawn(edge, ['--headless=new','--mute-audio','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check',
      '--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'], {stdio:'ignore',windowsHide:true});
    let port;
    while (Date.now() < deadline) {
      try { port = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).trim().split(/\r?\n/)[0]; if (port) break; } catch {}
      await pause(100);
    }
    assert.ok(port, 'browser startup');
    const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    ws = new WebSocket(pages.find(p => p.type === 'page').webSocketDebuggerUrl);
    await once(ws, 'open');
    let seq = 0; const pending = new Map();
    ws.addEventListener('message', event => { const m = JSON.parse(event.data); if (m.id) { pending.get(m.id)?.(m); pending.delete(m.id); } });
    const send = (method, params = {}) => new Promise((ok, fail) => {
      const id = ++seq, timer = setTimeout(() => {pending.delete(id);fail(new Error('CDP timeout: ' + method));}, 15000);
      pending.set(id, m => {clearTimeout(timer);m.error ? fail(new Error(JSON.stringify(m.error))) : ok(m.result);}); ws.send(JSON.stringify({id,method,params}));
    });
    const run = async expression => {
      const result = await send('Runtime.evaluate', {expression, returnByValue:true, awaitPromise:true});
      assert.ok(!result.exceptionDetails, JSON.stringify(result.exceptionDetails)); return result.result?.value;
    };
    const waitFor = async expression => {
      const until = Date.now() + 20000;
      while (Date.now() < until) { if (await run(expression)) return; await pause(100); }
      throw new Error('UI timeout: ' + expression + ': ' + await run('document.body.innerText'));
    };
    const shot = async name => {
      if (!process.env.F1_TEST_SHOTS) return;
      await mkdir(resolve(process.env.F1_TEST_SHOTS), {recursive:true});
      const result = await send('Page.captureScreenshot', {format:'png',captureBeyondViewport:true});
      await writeFile(join(resolve(process.env.F1_TEST_SHOTS), name + '.png'), Buffer.from(result.data, 'base64'));
    };
    const matrix = async state => {
      for (const theme of ['paper','dark']) for (const width of [1000,390]) {
        await send('Emulation.setDeviceMetricsOverride', {width,height:1250,deviceScaleFactor:1,mobile:false});
        await run(`document.documentElement.dataset.theme=${JSON.stringify(theme)}; new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))`);
        assert.ok(await run('document.documentElement.scrollWidth <= innerWidth'), `${state}/${theme}/${width}: page fits`);
        assert.ok(await run('document.querySelector(".curve-controls").scrollWidth <= document.querySelector(".curve-edit-body").clientWidth'), 'table fits without scrolling');
        assert.ok(await run('[...document.querySelectorAll("input,button,summary")].filter(e=>e.getBoundingClientRect().width).every(e=>e.getBoundingClientRect().height>=44)'), '44px controls');
        assert.ok(await run('[...document.querySelectorAll("svg text")].every(e=>{const b=e.getBBox(), v=e.ownerSVGElement.viewBox.baseVal; return b.x>=0 && b.x+b.width<=v.width && b.y>=0 && b.y+b.height<=v.height;})'), 'chart labels fit viewBox');
        const ticks = await run('[...document.querySelectorAll(".curve-y-tick")].map(e=>Number(e.textContent))');
        assert.ok(ticks.includes(0) && ticks.length >= 3 && ticks.length <= 5);
        assert.equal(await run('document.querySelectorAll(".curve-zero").length'), 1);
        assert.equal(await run('document.querySelectorAll("svg .curve-legend path").length'), 2);
        assert.equal(await run('document.querySelectorAll("svg .curve-legend text").length'), 2);
        assert.equal(await run('getComputedStyle(document.querySelector("svg text")).fontFamily === getComputedStyle(document.body).fontFamily'), true);
        assert.equal(await run('getComputedStyle(document.querySelector("[data-control]")).textAlign'), 'right');
        assert.ok(await run('document.querySelector(".curve-controls").getBoundingClientRect().width < document.querySelector(".curve-edit-body").clientWidth'), 'content-sized table');
        await shot(`${state}-${theme}-${width}`);
      }
      await send('Emulation.setDeviceMetricsOverride', {width:1000,height:1250,deviceScaleFactor:1,mobile:false});
      await run('document.documentElement.dataset.theme="paper"');
    };
    await send('Page.enable'); await send('Emulation.setDeviceMetricsOverride', {width:1000,height:1250,deviceScaleFactor:1,mobile:false});
    await send('Page.navigate', {url:url + '/curve-edit-fixture'});
    await waitFor('window.editor?.state?.loaded && document.querySelectorAll("[data-control]").length === 5');
    assert.equal(await run('document.querySelectorAll("polyline.curve-auto").length'), 1);
    assert.deepEqual(await run('[...document.querySelectorAll(".curve-x-tick")].map(e=>e.textContent)'), ['30','35','40','45','50','55']);
    assert.equal(await run('document.querySelectorAll("tr[data-modified=true]").length'), 0);
    assert.equal(await run('document.querySelector(".curve-save-help").hidden'), false);
    assert.ok(await run('document.querySelector(".curve-primary").classList.contains("kit-ring-button")'));
    assert.ok(await run('getComputedStyle(document.querySelector("polyline.curve-auto")).stroke !== getComputedStyle(document.querySelector("polyline.curve-candidate")).stroke'));
    assert.ok(await run('parseFloat(getComputedStyle(document.querySelector("polyline.curve-candidate")).strokeWidth) > parseFloat(getComputedStyle(document.querySelector("polyline.curve-auto")).strokeWidth)'));
    assert.equal(await run('[...document.querySelectorAll("button")].find(b=>b.textContent==="保存修正").disabled'), true);
    await matrix('automatic');
    const original = await readFile(join(dir, 'geo', 'correction.json'));
    await run(`document.querySelector('[data-control]').value='1';document.querySelector('[data-control]').dispatchEvent(new Event('input',{bubbles:true}));`);
    assert.match(await run('document.querySelector(".curve-status").textContent'), /改了 1 个点/);
    await run(`document.querySelector('[data-control]').value='0';document.querySelector('[data-control]').dispatchEvent(new Event('input',{bubbles:true}));`);
    assert.equal(await run('document.querySelectorAll("tr[data-modified=true]").length'), 0);
    await run(`document.querySelectorAll('[data-control]').forEach(input=>{input.value='-5';input.dispatchEvent(new Event('input',{bubbles:true}));});`);
    assert.match(await run('document.querySelector(".curve-status").textContent'), /改了 5 个点，还没验证/);
    assert.equal(await run('document.querySelectorAll("tr[data-modified=true]").length'), 5);
    await matrix('editing');
    await run(`[...document.querySelectorAll('button')].find(b=>b.textContent==='重拟合并验证').click()`);
    await waitFor('document.querySelector(".curve-edit").getAttribute("aria-busy")==="false" && window.editor.state.result.validation.reason==="independent_error_exceeded"');
    assert.equal(await run('window.editor.state.validated'), false);
    // A wider radius domain uses 10 mm ticks; failures without metrics retain their reason.
    const extra = await run(`(async()=>{
      const {curveEditor}=await import('/home/curve-edit.js');
      const host=document.createElement('div');document.body.append(host);
      const fixture=curveEditor(host,{run:'geo',state:{open:true,loaded:true,edit:{controls:[{radius_mm:20,delta_deg:0}]},plot:{radius_mm:[20,60,100],automatic_deg:[0,0,0],candidate_deg:[0,0,0]}},job:async()=>({ok:false,validation:{reason:'need_4_unique_independent_checks'}})});
      const ticks=[...host.querySelectorAll('.curve-x-tick')].map(e=>Number(e.textContent));
      host.querySelector('.curve-primary').click();
      await new Promise(resolve=>setTimeout(resolve,0));
      const message=host.querySelector('.curve-status').textContent;
      host.remove();return {ticks,message};
    })()`);
    assert.deepEqual(extra.ticks, [20,30,40,50,60,70,80,90,100]);
    assert.match(extra.message, /独立检查点不足/);
    assert.doesNotMatch(extra.message, /undefined|NaN|RMS/);
    assert.deepEqual(await readFile(join(dir, 'geo', 'correction.json')), original);
    assert.match(await run('document.querySelector(".curve-status").textContent'), /独立验证没通过：RMS 6\.25°（上限 0\.5°），最大 6\.25°（上限 1°）。原结果没有改。/);
    assert.equal(await run('document.querySelector(".curve-status").dataset.failed'), 'true');
    await matrix('validation-failed');
    await run(`document.querySelector('[data-control]').focus()`);
    assert.equal(await run('document.activeElement.type'), 'number');
    await run(`document.querySelectorAll('[data-control]').forEach(input=>{input.value='1.25';input.dispatchEvent(new Event('input',{bubbles:true}));});[...document.querySelectorAll('button')].find(b=>b.textContent==='重拟合并验证').click();`);
    await waitFor('window.editor.state.validated && document.querySelector(".curve-edit").getAttribute("aria-busy")==="false"');
    assert.match(await run('document.querySelector(".curve-status").textContent'), /独立验证通过：RMS 0°，最大 0°。可以保存。/);
    assert.equal(await run('document.querySelector(".curve-save-help").hidden'), true);
    await matrix('validation-passed');
    await run(`[...document.querySelectorAll('button')].find(b=>b.textContent==='保存修正').click()`);
    await waitFor('window.editor.state.result.saved && document.querySelector(".curve-edit").getAttribute("aria-busy")==="false"');
    assert.ok(existsSync(join(dir, 'geo', 'correction.automatic.json')));
    assert.notDeepEqual(await readFile(join(dir, 'geo', 'correction.json')), original);
    assert.ok(await run('window.editor.state.result.validation.rms_deg < 1e-10'));
    await run(`document.querySelector('[data-control]').value='2';document.querySelector('[data-control]').dispatchEvent(new Event('input',{bubbles:true}));`);
    assert.equal(await run('window.editor.state.validated'), false);
    console.log('Real CLI/browser: automatic, editing, rejection, valid save, 390px/1000px; synthetic only');
  } finally {
    ws?.close(); await stop(browser); await stop(server);
    assert.equal(dirname(resolve(dir)), resolve(tmpdir()));
    assert.ok(resolve(dir).startsWith(join(resolve(tmpdir()), 'discprobe-curve-')));
    await rm(dir, {recursive:true,force:true,maxRetries:5,retryDelay:200});
  }
});
