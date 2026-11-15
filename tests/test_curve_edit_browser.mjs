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
const pause = ms => new Promise(done => setTimeout(done, ms));
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
    browser = spawn(edge, ['--headless=new','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check',
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
    await send('Page.enable'); await send('Emulation.setDeviceMetricsOverride', {width:1000,height:1250,deviceScaleFactor:1,mobile:false});
    await send('Page.navigate', {url:url + '/curve-edit-fixture'});
    await waitFor('window.editor?.state?.loaded && document.querySelectorAll("[data-control]").length === 5');
    assert.equal(await run('document.querySelectorAll(".curve-auto").length'), 1);
    assert.equal(await run('[...document.querySelectorAll("button")].find(b=>b.textContent==="保存修正").disabled'), true);
    await shot('automatic');
    const original = await readFile(join(dir, 'geo', 'correction.json'));
    await run(`document.querySelectorAll('[data-control]').forEach(input=>{input.value='-5';input.dispatchEvent(new Event('input',{bubbles:true}));});`);
    assert.match(await run('document.querySelector(".curve-status").textContent'), /修改中/);
    await shot('editing');
    await run(`[...document.querySelectorAll('button')].find(b=>b.textContent==='重拟合并验证').click()`);
    await waitFor('document.querySelector(".curve-edit").getAttribute("aria-busy")==="false" && window.editor.state.result.validation.reason==="independent_error_exceeded"');
    assert.equal(await run('window.editor.state.validated'), false);
    assert.deepEqual(await readFile(join(dir, 'geo', 'correction.json')), original);
    await shot('validation-failed');
    for (const [width, height] of [[390,1100],[1000,1250]]) {
      await send('Emulation.setDeviceMetricsOverride', {width,height,deviceScaleFactor:1,mobile:false});
      assert.ok(await run('document.documentElement.scrollWidth <= innerWidth'), 'no horizontal overflow');
      assert.ok(await run('[...document.querySelectorAll("input,button,summary")].filter(e=>e.getBoundingClientRect().width).every(e=>e.getBoundingClientRect().height>=44)'), '44px controls');
      await run(`document.querySelector('[data-control]').focus()`);
      assert.equal(await run('document.activeElement.type'), 'number');
      if (width === 390) await shot('validation-failed-mobile');
    }
    await run(`document.querySelectorAll('[data-control]').forEach(input=>{input.value='1.25';input.dispatchEvent(new Event('input',{bubbles:true}));});[...document.querySelectorAll('button')].find(b=>b.textContent==='重拟合并验证').click();`);
    await waitFor('window.editor.state.validated && document.querySelector(".curve-edit").getAttribute("aria-busy")==="false"');
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
