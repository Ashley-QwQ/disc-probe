// Actual DOM/events/assets in Edge, file URLs only. No server, backend, or device access.
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, writeFileSync, readFileSync } from 'node:fs';
import { rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';
const edge = process.env.PASTWORKS_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
assert.ok(existsSync(edge), 'Set PASTWORKS_TEST_BROWSER to a Chromium executable');
const dir = mkdtempSync(join(tmpdir(), 'discprobe-pastworks-'));
const preview = new URL('../discprobe/web/home/pastworks-preview.html', import.meta.url);
const screenshots = process.env.PASTWORKS_SCREENSHOTS;
const html = width => `<!doctype html><meta charset="utf-8"><iframe id="view" style="width:${width}px;height:900px;border:0" src="${preview}"></iframe><pre id="result">PENDING</pre>
<script type="module">
const frame = document.getElementById('view'), report = document.getElementById('result');
const check = (ok, msg) => { if (!ok) throw Error(msg); };
const wait = ms => new Promise(r => setTimeout(r, ms));
try {
  for (let i = 0; i < 160 && !frame.contentWindow.pastworksPreview; i++) await wait(25);
  const w = frame.contentWindow, d = frame.contentDocument, root = d.documentElement;
  const demo = w.pastworksPreview; check(demo, 'preview mounted');
  for (let i = 0; i < 160 && demo.page.state.phase === 'loading'; i++) await wait(25);
  demo.page.skip();
  const page = demo.page.page;
  check(demo.page.state.phase === 'idle', 'skip entry reaches idle');
  check(page.querySelectorAll('.pw-cell').length === 13, 'new-work cell plus twelve plans');
  check(page.querySelector('.pw-cell').classList.contains('pw-new'), 'new work is always first');
  check(page.querySelectorAll('.pw-depth').length === 3, 'three depth groups');
  check(page.querySelectorAll('[data-tumble]').length === 36, 'bounded, repeating background images');
  await wait(150);
  check([...page.querySelectorAll('[data-tumble]')].every(img => img.complete && img.naturalWidth === 640), 'all real tumble assets load');
  await Promise.all([...page.querySelectorAll('[data-envelope]')].map(img => img.decode()));
  check([...page.querySelectorAll('[data-envelope]')].every(img => img.naturalWidth === 1600 && img.getBoundingClientRect().width > 0 && w.getComputedStyle(img).visibility === 'visible'), 'cell envelope pictures load and occupy the cells');
  for (let i = 0; i < 80 && page.querySelectorAll('.pw-cell:not(.pw-new) .pw-disc[data-blank]').length; i++) await wait(25);
  check([...page.querySelectorAll('.pw-cell:not(.pw-new) .pw-disc')].every(img => img.src.startsWith('blob:')), 'library thumbnails come from the works routes');   // the new work's blank disc is a picture
  const thumbPlan = demo.fakePlans[1], cached = demo.thumbnail(thumbPlan, 128);
  check(demo.thumbnail(thumbPlan, 128) === cached, 'thumbnail cache reuses image');
  const brightness = thumbPlan.tone.bright; thumbPlan.tone.bright = 60;
  check(demo.thumbnail(thumbPlan, 128) !== cached, 'thumbnail cache invalidates for tone changes'); thumbPlan.tone.bright = brightness;
  const proPlan = { ...thumbPlan, pro: true, lookColour: true, lookY: 70,
    scene: { cam: [0,-70,330], lamp: [0,0,0], follows: true }, layers: thumbPlan.layers.map(L => ({...L, colour:'red'})) };
  check(demo.thumbnail(proPlan, 128) !== cached, 'thumbnail uses the same PRO colour overlay without an active editor');
  check(!thumbPlan.selected, 'thumbnail rendering does not select or mutate editor work');
  const before = page.querySelectorAll('.pw-cell')[1].querySelector('.pw-disc').src;
  const second = page.querySelectorAll('.pw-cell')[2].querySelector('.pw-disc').src;
  check(before !== second, 'different work layers produce different discs');
  const art = page.querySelectorAll('.pw-cell')[1].querySelector('.pw-envelope');
  check(art.children[0].dataset.envelope === 'back' && art.children[1].dataset.envelope === 'front' && art.children[2].className === 'pw-disc', 'disc drawn above both envelope layers');
  check(page.querySelector('.pw-paper').scrollWidth <= page.querySelector('.pw-paper').clientWidth + 1, 'paper has no horizontal overflow');
  check(page.querySelector('.pw-scroll').scrollWidth <= w.innerWidth + 1, 'viewport has no horizontal overflow');
  page.querySelector('.pw-sort [data-sort="name"]').click();   // the form's two sort words (no browser menu)
  check(page.querySelectorAll('.pw-cell-name')[1].textContent.replace(/^[0-9]+/, '') === '岸边', 'name sorting visible');   // after its catalogue number
  const cell = page.querySelectorAll('.pw-cell')[2]; cell.click();
  check(demo.page.state.focused && page.querySelector('.pw-scroll').inert, 'work focus removes hidden grid from keyboard');
  check(page.querySelector('.pw-details').textContent.includes('2026'), 'details show name/date');
  page.querySelector('.pw-focus-art').firstElementChild.getAnimations().forEach(a => a.finish());
  check(page.querySelector('.pw-focus-art').firstElementChild.getBoundingClientRect().width > cell.querySelector('.pw-envelope').getBoundingClientRect().width, 'selected envelope grows');
  w.dispatchEvent(new w.KeyboardEvent('keydown', { key:'Escape', bubbles:true, cancelable:true }));
  check(!demo.page.state.focused && demo.page.state.phase === 'idle', 'first Esc closes detail only');
  check(d.activeElement === cell, 'focus restored to work');
  cell.click(); d.getElementById('back').click(); check(!demo.page.state.focused, 'Back has same detail-first order');
  // Scroll only transforms the cached layers; thumbnails and layout are stable.
  const scroll = page.querySelector('.pw-scroll');
  const scrollTop = Math.min(300, scroll.scrollHeight - scroll.clientHeight); scroll.scrollTop = scrollTop; scroll.dispatchEvent(new w.Event('scroll'));
  for (let i=0; i<30 && Math.abs(demo.page.state.camera-scrollTop)>=1; i++) await wait(20);
  check(Math.abs(demo.page.state.camera - scrollTop) < 1, 'scroll drives the same camera: '+JSON.stringify({state:demo.page.state,scrollTop,actual:scroll.scrollTop,motion:root.dataset.motion,reduce:w.matchMedia('(prefers-reduced-motion: reduce)').matches}));
  const transforms = [...page.querySelectorAll('.pw-depth')].map(n => n.style.transform);
  check(new Set(transforms).size === 3, 'depth groups move at distinct speeds');
  d.getElementById('back').click(); check(demo.page.state.phase === 'exiting', 'Back reverses fall');
  demo.page.skip(); check(demo.page.state.phase === 'closed' && !root.dataset.mode, 'skip reverse returns to lobby');
  await demo.page.show([]); check(demo.page.state.visits === 2 && demo.page.state.phase === 'entering', 'second entry starts');
  w.dispatchEvent(new w.KeyboardEvent('keydown', { key:'Enter', bubbles:true, cancelable:true }));
  check(demo.page.state.phase === 'idle' && !demo.page.state.focused, 'Enter skips without opening a work');
  root.dataset.motion = 'off'; await wait(0);
  d.getElementById('theme').click(); await wait(100);
  check([...page.querySelectorAll('[data-tumble]')].every(img => img.src.includes('_dark.webp')), 'dark art swaps live');
  check(page.querySelector('[data-envelope]').src.includes('_dark.webp'), 'dark cell envelopes');
  page.querySelectorAll('.pw-cell')[1].click(); page.querySelector('.pw-open').click(); await wait(30);
  check(demo.page.state.phase === 'closed' && !d.querySelector('.preview-result').hidden, 'Open work calls integration callback');
  check(!d.getElementById('back').hidden, 'opening another mode preserves its back button');
  d.getElementById('return').click(); await wait(50);
  check(demo.page.state.phase === 'idle', 'motion off is a straight cut');
  page.querySelector('.pw-new').click(); await wait(20);
  check(d.querySelector('.preview-result h1').textContent.includes('新作品'), 'new-work action is connected');
  d.getElementById('return').click(); await wait(50); demo.page.back();
  check(demo.page.state.phase === 'closed', 'motion-off reverse is a straight cut');

  demo.page.back(); root.dataset.motion='on';
  await demo.page.show([]); demo.page.back(); demo.page.skip();
  check(demo.page.state.phase === 'closed', 'Esc/Back during entry reverses without stranding the page');
  // the library: filters, search, rename, failure with a reason, bin and undo, keyboard on cards
  root.dataset.motion = 'off';
  await demo.page.show([]); demo.page.skip(); await wait(30);
  check(demo.page.state.library && demo.page.state.phase === 'idle', 'library mode with a works client');
  const cells = () => [...page.querySelectorAll('.pw-cell')];
  const until = async (ok, msg) => { for (let i = 0; i < 80 && !ok(); i++) await wait(25); check(ok(), msg); };
  const key = (target, k, extra = {}) => target.dispatchEvent(new w.KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true, ...extra }));
  page.querySelector('[data-filter="status"] [data-value="failed"]').click();
  check(cells().length === 2 && cells()[1].querySelector('.pw-state-failed'), 'status filter');
  page.querySelector('[data-filter="status"] [data-value=""]').click();
  page.querySelector('[data-filter="media"] [data-value="cd"]').click();
  check(cells().length > 1 && cells().slice(1).every(c => c.querySelector('.pw-meta').textContent.startsWith('CD')), 'media filter');
  page.querySelector('[data-filter="media"] [data-value=""]').click();
  const search = page.querySelector('.pw-search input'); search.value = 'ＡＴＬＡＳ'; search.dispatchEvent(new w.Event('input'));
  check(cells().length === 3, 'search by name, width-folded');
  search.value = 'nothing like it'; search.dispatchEvent(new w.Event('input'));
  check(!page.querySelector('.pw-empty').hidden && page.querySelector('.pw-empty button:not([hidden])'), 'no match offers to clear filters');
  search.focus(); key(search, 'Escape');
  check(search.value === '' && cells().length === 13 && demo.page.state.phase === 'idle', 'Esc clears the search before leaving');
  cells()[0].focus(); key(cells()[0], 'ArrowRight'); check(d.activeElement === cells()[1], 'arrow keys move across the grid');
  const first = cells()[1], id = first.dataset.id, mock = demo.works.mock;
  key(first, 'F2');
  const input = page.querySelector('.pw-rename-input'); check(input && d.activeElement === input, 'F2 opens the name for editing');
  input.value = '新名字'; key(input, 'Enter');
  await until(() => mock.works.get(id).name === '新名字' && page.querySelector('.pw-rename')?.textContent === '新名字', 'rename reaches the library and the sheet');
  page.querySelector('.pw-act-failed').click();
  const form = page.querySelector('.pw-fail'); check(!form.hidden && d.activeElement === form.querySelector('textarea'), 'failure asks for a reason');
  form.requestSubmit(); await wait(40); check(mock.works.get(id).status !== 'failed', 'no reason, no failure mark');
  form.querySelector('textarea').value = '内圈没刻上'; form.requestSubmit();
  await until(() => mock.works.get(id).status === 'failed' && page.querySelector('.pw-d-reason'), 'marked failed with its reason');
  check(page.querySelector('.pw-d-reason').textContent.includes('内圈没刻上'), 'reason shown');
  check(page.querySelector('.pw-focus-art .pw-stamp-failed'), 'the bag up close is re-stamped');
  check(page.querySelector('.pw-d-log').textContent.includes('标成失败') && page.querySelector('.pw-d-log').textContent.includes('改名为'), 'record shows rename and mark');
  page.querySelector('.pw-act-bin').click();
  await until(() => !demo.page.state.focused && cells().length === 12 && mock.trash.has(id), 'bin leaves the grid');
  check(d.activeElement?.classList.contains('pw-cell'), 'focus stays on the grid after the bin');
  key(w, 'z', { ctrlKey: true });
  await until(() => cells().length === 13 && !mock.trash.has(id), 'Ctrl+Z restores from the bin');
  const victim = cells()[2], victimId = victim.dataset.id; victim.focus(); key(victim, 'Delete');
  await until(() => mock.trash.has(victimId) && !page.querySelector('.pw-status .pw-link').hidden, 'Delete on a card bins it, with an undo');
  page.querySelector('.pw-status .pw-link').click();
  await until(() => !mock.trash.has(victimId), 'the undo button restores it');
  const size = mock.works.size; cells()[1].click(); page.querySelector('.pw-d-actions .pw-act').click();
  await until(() => mock.works.size === size + 1 && !demo.page.state.focused, 'duplicate adds a work');
  // a core without works: this session's plans, said plainly; an empty library: the first step
  await demo.setMode({ noCore: true });
  let p2 = demo.page.page;
  check(!demo.page.state.library && p2.querySelectorAll('.pw-cell').length === 13, 'no works capability: in-memory plans');
  check(!p2.querySelector('.pw-note').hidden && p2.querySelector('.pw-note').textContent.includes('不保存作品'), 'says this core keeps no works');
  check(p2.querySelector('[data-filter="status"]').hidden && p2.querySelector('.pw-import').hidden, 'no library tools without a library');
  await demo.setMode({ empty: true });
  p2 = demo.page.page;
  check(p2.querySelectorAll('.pw-cell').length === 1 && p2.querySelector('.pw-empty').textContent.includes('第一步'), 'empty library says the first step');
  await demo.setMode({});
  report.textContent='PASS: archive DOM, assets, focus, callbacks, motion, keyboard and library management';
} catch (e) { report.textContent='FAIL: '+e.stack; }
</script>`;
const delay = ms => new Promise(r => setTimeout(r, ms));
let browserProcess, socket, id = 0;
const pending = new Map();
async function cdp(method, params = {}) {
  const call = ++id;
  const answer = new Promise((resolve, reject) => pending.set(call, { resolve, reject }));
  socket.send(JSON.stringify({ id: call, method, params }));
  return answer;
}
async function evaluate(expression) {
  const result = await cdp('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  assert.ok(!result.exceptionDetails, JSON.stringify(result.exceptionDetails)); return result.result.value;
}
try {
  // Bounded headless test process. Real time lets image.decode() finish; virtual-time dump-dom
  // can end before the full-size cell envelope textures decode and hide genuine visual defects.
  browserProcess = spawn(edge, ['--headless=new', '--disable-gpu', '--no-sandbox', '--no-first-run', '--no-default-browser-check',
    '--allow-file-access-from-files', '--remote-debugging-port=0', `--user-data-dir=${join(dir, 'profile')}`, 'about:blank'],
  { windowsHide: true, stdio: 'ignore' });
  browserProcess.on('error', error => { throw error; });
  const portFile = join(dir, 'profile', 'DevToolsActivePort');
  let port;
  for (let i = 0; i < 100 && !port; i++) {
    try {
      const [number, endpoint] = readFileSync(portFile, 'utf8').trim().split(/\r?\n/);
      if (/^\d+$/.test(number) && Number(number) > 0 && Number(number) <= 65535 && endpoint?.startsWith('/devtools/browser/')) port = number;
    } catch (error) {
      if (!['ENOENT', 'EBUSY', 'EPERM', 'EACCES'].includes(error.code)) throw error;
    }
    if (!port) await delay(100);
  }
  assert.ok(port, 'headless browser debugging endpoint ready and readable');
  const targets = await fetch(`http://127.0.0.1:${port}/json/list`).then(r => r.json());
  socket = new WebSocket(targets.find(t => t.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data); const callback = pending.get(message.id);
    if (callback) { pending.delete(message.id); if (message.error) callback.reject(Error(JSON.stringify(message.error))); else callback.resolve(message.result); }
  };
  await cdp('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'no-preference' }] });
  for (const width of [1440, 390]) {
    const fixture = join(dir, `fixture-${width}.html`); writeFileSync(fixture, html(width));
    await cdp('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1100, deviceScaleFactor: 1, mobile: false });
    await cdp('Page.navigate', { url: pathToFileURL(fixture).href });
    let report = 'PENDING';
    for (let i = 0; i < 200 && report === 'PENDING'; i++) { await delay(50); report = await evaluate("document.getElementById('result')?.textContent || 'PENDING'"); }
    assert.match(report, /^PASS:/, `${width}: ${report}`);
    console.log(`Past works browser integration passed (${width}px, file URLs)`);
  }
  const lobby = readFileSync(new URL('../discprobe/web/home/lobby.js', import.meta.url), 'utf8');
  assert.match(lobby, /lobby-open[\s\S]*?stopImmediatePropagation\(\)[\s\S]*?pastworks\.js[\s\S]*?capture: true/);
  const lobbyFixture = join(dir, 'lobby-entry.html');
  writeFileSync(lobbyFixture, `<!doctype html><meta charset="utf-8"><style>body{margin:0}.lobby{position:fixed;inset:0}.pw{--edge:20px;--row:52px;--foot:72px;--paper:#ebe7e0;--paper-2:#e4dfd7;--ink:#1d1b18;--ink-2:#5d5850;--font:system-ui}</style>
    <section id="lobby" class="lobby"><div id="lobby-art"></div><div class="lobby-greet"><p id="lobby-hello"></p><p id="lobby-recent"></p></div><button id="lobby-new"></button><button id="lobby-open"></button></section>
    <button id="theme"></button><button id="back" hidden>返回 / Back</button><pre id="result">PENDING</pre>
    <script type="module">
    const $=id=>document.getElementById(id), check=(v,m)=>{if(!v)throw Error(m)}, wait=ms=>new Promise(r=>setTimeout(r,ms));
    let legacy=0,newWorks=0; $('lobby-open').addEventListener('click',()=>legacy++);
    const api={$,lang:()=> 'zh',reduce:false,lobbyState:()=>null,toLobby(){document.documentElement.dataset.mode=''},newWork(){newWorks++;document.documentElement.dataset.mode='newplan';$('back').hidden=false}};
    try {
      await (await import('${new URL('../discprobe/web/home/lobby.js', import.meta.url)}')).init(api);
      $('lobby-open').click();
      for(let i=0;i<100&&!document.querySelector('.pw:not([hidden])');i++)await wait(20);
      check(document.documentElement.dataset.mode==='pastworks','real file-box entry opens archive');
      check(legacy===0,'legacy picker bubble handler is suppressed');
      document.documentElement.dataset.motion='off'; await wait(10);
      window.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
      const page=document.querySelector('.pw'); check(page.querySelectorAll('.pw-cell').length===1,'real empty session has one new-work cell');
      $('back').click();check(page.hidden,'real Back returns to lobby');check(document.activeElement===$('lobby-open'),'real Back restores file-box focus');
      $('lobby-open').click();for(let i=0;i<100&&page.hidden;i++)await wait(20);
      page.querySelector('.pw-new').click();await wait(20);
      check(newWorks===1&&document.documentElement.dataset.mode==='newplan'&&!$('back').hidden,'archive reuses api.newWork and preserves next mode controls');
      $('result').textContent='PASS: real lobby capture entry, return focus and new work';
    }catch(e){$('result').textContent='FAIL: '+e.stack}
    </script>`);
  await cdp('Page.navigate', { url: pathToFileURL(lobbyFixture).href });
  let lobbyReport = 'PENDING';
  for (let i = 0; i < 200 && lobbyReport === 'PENDING'; i++) { await delay(50); lobbyReport = await evaluate("document.getElementById('result')?.textContent || 'PENDING'"); }
  assert.match(lobbyReport, /^PASS:/, lobbyReport);
  console.log(lobbyReport);
  if (screenshots) {
    // Caller supplies an existing allowed directory, only PNGs are written there.
    // list and detail at desktop and phone width, both themes; the empty library and a core without works
    for (const [width, theme, view] of [[1440, 'paper', 'list'], [1440, 'paper', 'detail'], [1440, 'dark', 'list'], [390, 'dark', 'list'],
      [390, 'dark', 'detail'], [390, 'paper', 'list'], [1440, 'paper', 'empty'], [1440, 'paper', 'nocore']]) {
      await cdp('Emulation.setDeviceMetricsOverride', { width, height: width < 600 ? 844 : 900, deviceScaleFactor: 1, mobile: false });
      await cdp('Page.navigate', { url: preview.href });
      let ready = false;
      for (let i = 0; i < 100 && !ready; i++) { await delay(50); ready = await evaluate("!!window.pastworksPreview && pastworksPreview.page.state.phase !== 'loading'"); }
      assert.ok(ready, 'preview ready for visual capture');
      await evaluate(`(async () => { document.documentElement.dataset.theme='${theme}'; pastworksPreview.page.skip();
        if ('${view}' === 'empty' || '${view}' === 'nocore') { await pastworksPreview.setMode({ ${view === 'empty' ? 'empty' : 'noCore'}: true }); pastworksPreview.page.skip(); }
        await new Promise(r=>setTimeout(r,300));
        if ('${view}' === 'detail') { document.querySelectorAll('.pw-cell')[3].click(); await new Promise(r=>setTimeout(r,700)); }
        await Promise.all([...document.querySelectorAll('.pw img')].map(i=>i.decode().catch(()=>{})));
        await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))); })()`);
      const shot = await cdp('Page.captureScreenshot', { format: 'png' });
      writeFileSync(resolve(screenshots, `pastworks-${width}-${theme}-${view}.png`), Buffer.from(shot.data, 'base64'));
    }
  }
} finally {
  if (socket?.readyState === WebSocket.OPEN) { await cdp('Browser.close').catch(() => {}); socket.close(); }
  if (browserProcess) {
    const exited = () => browserProcess.exitCode !== null || browserProcess.signalCode !== null;
    const closed = new Promise(resolve => browserProcess.once('close', resolve));
    if (!exited()) {
      await Promise.race([closed, delay(2000)]);
      if (!exited()) {
        browserProcess.kill();
        await Promise.race([closed, delay(5000)]);
      }
    }
    assert.ok(exited(), 'fixture browser must exit before removing its profile');
  }
  assert.ok(resolve(dir).startsWith(resolve(tmpdir(), 'discprobe-pastworks-')));
  // Keep the event loop available while Chromium releases Windows profile handles.
  await rm(dir, { recursive: true, force: true, maxRetries: 8, retryDelay: 250 });
}
