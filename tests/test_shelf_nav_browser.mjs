// Exercise the bundled library through real Edge inputs and an isolated, in-memory core.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { dirname, extname, join, resolve, sep } from 'node:path';
import { setTimeout as wait } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';

const web = fileURLToPath(new URL('../discprobe/web', import.meta.url));
const manifest = JSON.parse(await readFile(join(web, 'gui.json'), 'utf8'));
const edge = process.env.EDGE || process.env.KIT_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const temp = resolve(tmpdir());
const profile = await mkdtemp(join(temp, 'shelf-edge-'));
const mime = { '.html':'text/html; charset=utf-8', '.js':'text/javascript', '.mjs':'text/javascript',
  '.json':'application/json', '.css':'text/css', '.svg':'image/svg+xml', '.webp':'image/webp', '.woff2':'font/woff2' };
const cdPath = 'results/geo-H-20261104-140801';
const dvd = Array.from({length:10}, (_, i) => ({id:`dvd-${i+1}`, row:'dvd', kind:'disc',
  name:i === 9 ? 'LongUnbreakableName'.repeat(12) : i === 2 ? '' : `DVD batch ${i+1}`,
  mid:`DVD-MID-${i+1}`, s:['good','incomplete','none'][i%3], last:'2026-11-14',
  capacity_sectors:2295104, geo:`results/geo-dvd-${i+1}`}));
const legacy = {id:'cd-legacy', row:'cd', kind:'disc', media_kind:'CD-R', name:cdPath.split('/').at(-1), s:'good',
  last:'2026-11-04', drive:'GH70N', geo:`${cdPath}/summary.json`, sectors:359847, capacity_sectors:359849,
  along_track:{known:false}, history:[{kind:'calibrate',state:'ok',when:'2026-11-04'}]};
const confirmed = {...legacy, id:'cd-confirmed', name:'Confirmed CD', geo:'results/geo-cd-confirmed', along_track:{known:true}};
const catalogue = {dvd, cd:[legacy, confirmed], bd:[]};
const calls = [], fileErrors = [];
const checkJob = 'fixture-check-iso';

const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const send = data => { res.setHeader('Content-Type','application/json'); res.end(JSON.stringify(data)); };
  const reject = message => { res.statusCode = 404; send({error:message}); };
  let body;
  if (req.method === 'POST') {
    let raw = '';
    for await (const chunk of req) raw += chunk;
    body = JSON.parse(raw);
  }
  if (url.pathname.startsWith('/api/')) calls.push({path:url.pathname, query:Object.fromEntries(url.searchParams), body});
  switch (url.pathname) {
    case '/api/version': return send({api_version:'1.5', capabilities:[...manifest.required_capabilities, ...manifest.optional_capabilities]});
    case '/api/state': return send({version:'1.0.0-alpha', platform:'win32', catalogue, jobs:[], drives:[]});
    case '/api/events':
      res.writeHead(200, {'Content-Type':'text/event-stream'});
      return res.end(`retry: 30000\nevent: done\ndata: ${JSON.stringify({type:'done', job:checkJob, exit:0})}\n\n`);
    case '/api/phone-link': return send({addresses:[], url:null});
    case '/api/photos': return send({photos:[]});
    case '/api/phone-devices': return send({devices:[]});
    case '/api/community': return send({feed:[],count:0});
    case '/api/works': return send([]);
    case '/api/run': return body?.action === 'checkdisc' ? send({job:checkJob}) : reject('fixture cannot run jobs');
    case '/api/iso': return send({path:url.searchParams.get('path'), bytes:2048, sectors:1});
    case '/api/presets': return send(body ? {preset:{id:'legacy-export', displayName:body.name}} : {presets:[]});
    case '/api/catalogue':
      if (body?.id !== legacy.id) return reject('unknown fixture batch');
      legacy.name = body.name;
      return send({saved:true});
  }
  const path = resolve(web, '.' + decodeURIComponent(url.pathname), ...(url.pathname.endsWith('/') ? ['index.html'] : []));
  if (!path.startsWith(web + sep) || /b[l]ind/i.test(path)) return reject('unknown file');
  try {
    const data = await readFile(path);
    res.setHeader('Content-Type',mime[extname(path)] || 'application/octet-stream');
    res.end(data);
  } catch (error) {
    if (!url.pathname.startsWith('/api/') && url.pathname !== '/favicon.ico') fileErrors.push(url.pathname);
    reject(error.code);
  }
});
server.listen(0, '127.0.0.1');
await once(server, 'listening');
const {port} = server.address();
assert.notEqual(port, 8765);
const browser = spawn(edge, ['--headless=new', '--disable-gpu', '--disable-background-networking', '--disable-component-update',
  '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', '--mute-audio',
  '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1', `--user-data-dir=${profile}`, 'about:blank'],
  {stdio:'ignore', windowsHide:true});

let socket, sequence = 0;
const requests = new Map();
function cdp(method, params = {}) {
  const id = ++sequence;
  return new Promise((ok, fail) => {
    const timeout = setTimeout(() => { requests.delete(id); fail(Error(`${method} timed out`)); }, 12000);
    requests.set(id, reply => { clearTimeout(timeout); reply.error ? fail(Error(reply.error.message)) : ok(reply.result); });
    socket.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression) {
  const reply = await cdp('Runtime.evaluate', {expression, returnByValue:true, awaitPromise:true});
  assert.ok(!reply.exceptionDetails, reply.exceptionDetails?.exception?.description);
  return reply.result.value;
}
async function until(check, message = check) {
  for (let i=0; i<240; i++) {
    const found = await (typeof check === 'string' ? evaluate(check) : check());
    if (found) return found;
    await wait(40);
  }
  assert.fail(`Timed out: ${message}`);
}
async function point(selector) {
  return evaluate(`(() => {
    const e=document.querySelector(${JSON.stringify(selector)});
    e.scrollIntoView({block:'nearest'});
    const r=e.getBoundingClientRect();
    return {x:Math.round(r.left+r.width/2), y:Math.round(r.top+r.height/2)};
  })()`);
}
async function click(selector) {
  const p = await point(selector);
  for (const type of ['mousePressed', 'mouseReleased']) await cdp('Input.dispatchMouseEvent', {type, ...p, button:'left', clickCount:1});
}
async function key(key, windowsVirtualKeyCode) {
  for (const type of ['keyDown', 'keyUp']) await cdp('Input.dispatchKeyEvent', {type, key, code:key, windowsVirtualKeyCode});
}
async function selection(index, title) {
  const info = await evaluate(`({current:[...document.querySelectorAll('.shelf-batch[aria-current="true"]')].map(e=>+e.dataset.index),
    title:document.querySelector('#name').title, count:document.querySelector('#batch-position').textContent})`);
  assert.deepEqual(info.current,[index]);
  assert.equal(info.title,title);
  assert.match(info.count,new RegExp(`^Batch ${index+1} of `));
}
async function navigate(width, motion) {
  await cdp('Emulation.setDeviceMetricsOverride', {width,height:width === 390 ? 844 : 900,deviceScaleFactor:1,mobile:false});
  await cdp('Emulation.setEmulatedMedia', {features:[{name:'prefers-reduced-motion',value:motion}]});
  await cdp('Emulation.setTouchEmulationEnabled', {enabled:width === 390});
  const url = `http://127.0.0.1:${port}/home/?case=${sequence}#/library`;
  await cdp('Page.navigate',{url});
  await until(`location.href===${JSON.stringify(url)} && document.documentElement?.dataset.navigation==='ready' && document.querySelectorAll('.shelf-batch').length===10`);
}

try {
  const debug = await until(async () => (await readFile(join(profile,'DevToolsActivePort'),'utf8').catch(()=>'' )).split(/\r?\n/)[0], 'Edge CDP port');
  assert.notEqual(debug,'8765');
  const pages = await fetch(`http://127.0.0.1:${debug}/json/list`).then(r=>r.json());
  socket = new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
  await once(socket,'open');
  socket.onmessage = ({data}) => { const reply=JSON.parse(data); requests.get(reply.id)?.(reply); requests.delete(reply.id); };
  await cdp('Page.enable');
  await cdp('Emulation.setFocusEmulationEnabled',{enabled:true});
  await cdp('Page.addScriptToEvaluateOnNewDocument',{source:`
    localStorage.setItem('dp-theme','dark'); localStorage.setItem('dp-lang','en'); localStorage.setItem('dp-sound','off');
    window.shelfErrors=[]; addEventListener('error',e=>shelfErrors.push(e.message));
    addEventListener('unhandledrejection',e=>shelfErrors.push(String(e.reason)));
  `});
  await navigate(1440,'reduce');
  await selection(0,'DVD batch 1');
  assert.equal(await evaluate(`document.querySelectorAll('.shelf-batch').length`),10);
  assert.equal(await evaluate(`document.querySelector('#batch-prev').disabled`),true);
  assert.match(await evaluate(`document.querySelector('.shelf-batch[data-index="1"]').innerText`), /DVD · Incomplete measurement · Last calibrated: 2026-11-14/);
  assert.match(await evaluate(`document.querySelector('.shelf-batch[data-index="2"]').innerText`), /DVD-MID-3.*Not calibrated/s);
  await click('.shelf-batch[data-index="2"]');
  await selection(2,'DVD-MID-3');
  await key('ArrowLeft',37);
  await selection(1,'DVD batch 2');
  assert.equal(await evaluate(`document.activeElement.dataset.index`),'1');
  await click('#batch-next');
  await selection(2,'DVD-MID-3');
  await click('#batch-prev');
  await selection(1,'DVD batch 2');
  const wheel = await point('#batch-position');
  await cdp('Input.dispatchMouseEvent',{type:'mouseWheel',...wheel,deltaX:0,deltaY:92});
  await until(`document.querySelector('.shelf-batch[aria-current]')?.dataset.index==='2'`);
  await selection(2,'DVD-MID-3');
  await click('.shelf-batch[data-index="9"]');
  await selection(9,dvd[9].name);
  await key('ArrowRight',39);
  await selection(9,dvd[9].name);
  assert.equal(await evaluate(`document.querySelector('#batch-next').disabled && !document.querySelector('.batch-copy-leaving') && !document.querySelector('#batch-copy').getAnimations().length`),true);
  assert.equal(await evaluate(`(() => {const n=document.querySelector('#name'),s=getComputedStyle(n);
    return n.clientHeight<=2*parseFloat(s.lineHeight)+1 && n.scrollWidth<=n.clientWidth;})()`),true);

  await click('.kind[data-col="cd"]');
  await selection(0,'CD-R · GH70N · 11-04');
  assert.equal(await evaluate(`document.querySelector('#next-text').textContent`),'Calibrate with photos');
  assert.match(await evaluate(`document.querySelector('#why').textContent`), /Radial lines may twist/);
  assert.equal(await evaluate(`document.querySelector('#left').parentElement.hidden && document.querySelector('#batch-history').hidden`),true);
  await click('#library-more summary');
  assert.match(await evaluate(`document.querySelector('#batch-source').textContent`), /geo-H-20261104-140801/);
  await click('#library-rename');
  await evaluate(`document.querySelector('#batch-new-name').value='Imported CD renamed'`);
  await click('#batch-name-save');
  await until(`document.querySelector('#name').title==='Imported CD renamed'`);
  await selection(0,'Imported CD renamed');
  await click('#library-export');
  await until(`document.querySelector('#library-feedback').textContent==='DIS preset exported.'`);
  assert.deepEqual(calls.find(r=>r.path==='/api/presets' && r.body)?.body,
    {operation:'export', path:`${cdPath}/summary.json`, name:'Imported CD renamed', sectors:359849});
  await click('#next');
  await until(`document.documentElement.classList.contains('cal-photo') && document.querySelector('.pc-paper')`);
  assert.ok(calls.some(({path,query})=>path==='/api/photos' && query.run==='geo-H-20261104-140801'));
  await click('#back');
  await until(`!document.documentElement.dataset.mode && document.querySelector('#next-text').textContent==='Calibrate with photos'`);
  await click('#library-design');
  await until(`document.documentElement.dataset.mode==='design'`);
  await navigate(1440,'reduce');
  await click('.kind[data-col="cd"]');
  await click('.shelf-batch[data-index="1"]');
  assert.equal(await evaluate(`document.querySelector('#next-text').textContent`),'Next: open a work');
  assert.match(await evaluate(`document.querySelector('#why').textContent`), /Ready to design and burn/);
  await click('#next');
  await until(`document.documentElement.dataset.mode==='design'`);

  await navigate(1440,'reduce');
  await click('#library-check');
  await until(`document.documentElement.dataset.mode==='burn' && document.querySelector('.burn-panel')`);
  assert.equal(calls.find(r=>r.path==='/api/run')?.body.args.geo,dvd[0].geo);
  await click('#back');
  await until(`!document.documentElement.dataset.mode && document.querySelector('#next-text').textContent==='Next: open a work'`);
  await click('.kind[data-col="bd"]');
  assert.equal(await evaluate(`document.querySelector('#batch-list').hidden && !document.querySelector('#library-calibrate').hidden`),true);
  assert.equal(await evaluate(`document.querySelector('#batch-position').textContent`),'0 batches');

  await navigate(390,'reduce');
  assert.equal(await evaluate(`document.documentElement.scrollWidth`),390);
  const frame = await evaluate(`(()=>{const r=document.querySelector('.stage').getBoundingClientRect();return {x:Math.round(r.left+0.74*r.width), y:Math.round(r.top+r.height/2)};})()`);
  for (const [type, touchPoints] of [['touchStart',[frame]], ['touchMove',[{...frame,x:frame.x-116}]], ['touchEnd',[]]]) {
    await cdp('Input.dispatchTouchEvent',{type,touchPoints});
  }
  await until(`document.querySelector('.shelf-batch[aria-current]')?.dataset.index==='1'`);
  await selection(1,'DVD batch 2');
  const clearFooter = await evaluate(`document.querySelector('.shelf-main').getBoundingClientRect().bottom < document.querySelector('#next').getBoundingClientRect().top`);
  assert.equal(clearFooter,true);

  await navigate(1440,'no-preference');
  const transition = await evaluate(`(() => {
    document.querySelector('#batch-next').click();
    const old=document.querySelector('.batch-copy-leaving'), active=document.querySelector('#batch-copy');
    return {old:old?.querySelector('.name').textContent, now:active.querySelector('.name').textContent,
      exit:old?.getAnimations()[0]?.effect.getKeyframes().at(-1).transform,
      enter:active.getAnimations()[0]?.effect.getKeyframes()[0].transform, opacity:+getComputedStyle(active).opacity,
      a11y:old?.getAttribute('aria-hidden')};
  })()`);
  assert.deepEqual(transition,{old:'DVD batch 1', now:'DVD batch 2', exit:'translateX(18px)', enter:'translateX(-18px)', opacity:0, a11y:'true'});
  await click('#batch-prev');
  await selection(0,'DVD batch 1');
  await until(`!document.querySelector('.batch-copy-leaving') && !document.querySelector('#batch-copy').getAnimations().length`);
  assert.deepEqual(await evaluate('window.shelfErrors'),[]);
  assert.deepEqual(fileErrors,[]);
  assert.ok(calls.filter(call=>call.path==='/api/run').every(call=>call.body.action==='checkdisc'));
  console.log('Library: 10 rows, direct selection, arrows, wheel, touch, direction, reduced motion, CD photo/rename/export, and DVD check-disc hand-off.');
} finally {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({id:++sequence,method:'Browser.close'}));
    socket.close();
  }
  if (browser.exitCode === null) {
    await Promise.race([once(browser,'exit'),wait(2500)]);
    if (browser.exitCode === null) browser.kill();
  }
  server.closeAllConnections();
  server.close();
  assert.equal(dirname(resolve(profile)),temp);
  await rm(profile,{recursive:true,force:true,maxRetries:8,retryDelay:200});
}
