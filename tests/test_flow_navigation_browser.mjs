// Real HTTP/CSP and browser history, virtual core only. Screenshots go to FLOWNAV_SHOTS or the system temp folder.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtempSync, readFileSync, writeFileSync, mkdirSync, rmSync} from 'node:fs';
import {join, resolve} from 'node:path';
import {tmpdir} from 'node:os';

const dir = mkdtempSync(join(tmpdir(), 'flow-nav-'));
const shots = process.env.FLOWNAV_SHOTS ?? join(tmpdir(), 'discprobe-flownav-shots'); mkdirSync(shots, {recursive:true});
const server = spawn(process.env.PYTHON || 'python', ['-B', '-X', 'utf8', 'tests/webguide_http_fixture.py', join(dir, 'data')],
  {stdio:['pipe','pipe','pipe'], windowsHide:true});
let out = '', err = '', browser, socket, seq = 0;
const requests = new Map(), networkErrors = [];
server.stdout.on('data', d => out += d); server.stderr.on('data', d => err += d);
const pause = ms => new Promise(r => setTimeout(r, ms)), pending = new Map();
async function cdp(method, params = {}) {
  const id = ++seq;
  const result = new Promise((resolve,reject) => {
    const timer = setTimeout(() => {pending.delete(id); reject(Error(method));}, 20000);
    pending.set(id, {resolve: r => {clearTimeout(timer);resolve(r);}, reject: e => {clearTimeout(timer);reject(e);}});
  });
  socket.send(JSON.stringify({id, method, params})); return result;
}
async function evaluate(expression) {
  const r = await cdp('Runtime.evaluate', {expression, awaitPromise:true, returnByValue:true});
  assert(!r.exceptionDetails, JSON.stringify(r.exceptionDetails)); return r.result.value;
}
async function until(expression) {
  const deadline = Date.now() + Number(process.env.BROWSER_WAIT_MS || 60000);
  while(Date.now() < deadline) {let ok = false; try {ok = await evaluate(expression);} catch {} if(ok) return; await pause(25);}
  throw Error('Timed out: '+expression+'; '+await evaluate('JSON.stringify({url:location.href, mode:document.documentElement.dataset.mode, errors:window.navErrors, body:document.body.innerText.slice(-1000)})'));
}
const shot = async name => writeFileSync(join(shots, name+'.png'), Buffer.from((await cdp('Page.captureScreenshot', {format:'png'})).data,'base64'));
async function reload() {
  const previous = await evaluate('navLoad');
  await cdp('Page.reload');
  await until('window.navLoad && window.navLoad!=='+JSON.stringify(previous)+' && document.readyState==="complete"');
}
try {
  for(let i=0;i<400&&!out.includes('\n')&&server.exitCode===null;i++)await pause(25);
  assert(out.includes('\n'), err); const ports=JSON.parse(out.split('\n')[0]);
  const profile=join(dir,'edge');
  browser=spawn(process.env.KIT_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',[
    '--headless=new','--mute-audio','--disable-gpu','--disable-background-networking','--no-first-run','--no-default-browser-check',
    '--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'], {stdio:'ignore',windowsHide:true});
  let port;
  for(let i=0;i<300;i++){try{port=readFileSync(join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];break;}catch{await pause(25);}}
  assert(port,'Edge did not start');
  const tabs=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  socket=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j;});
  socket.onmessage=({data})=>{const m=JSON.parse(data),p=pending.get(m.id);
    if(m.method==='Network.requestWillBeSent')requests.set(m.params.requestId,m.params.request.url);
    if(m.method==='Network.loadingFailed')networkErrors.push({url:requests.get(m.params.requestId),error:m.params.errorText});
    if(p){pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}};
  await cdp('Page.enable'); await cdp('Runtime.enable');await cdp('Network.enable');
  await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await cdp('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  await cdp('Page.addScriptToEvaluateOnNewDocument',{source:`
    window.navLoad=crypto.randomUUID();window.navErrors=[];window.navCsp=[];
    addEventListener('error',e=>navErrors.push(e.message));addEventListener('unhandledrejection',e=>navErrors.push(String(e.reason)));
    addEventListener('securitypolicyviolation',e=>navCsp.push(e.effectiveDirective));
    localStorage.setItem('dp-lang','zh');localStorage.setItem('dp-motion','off');localStorage.setItem('dp-sound','off');
    const nativeFetch=fetch; window.fetch=(path,...args)=>{
      if(String(path)==='/api/version'&&sessionStorage.getItem('nav-offline'))return Promise.reject(Error('test offline'));
      return nativeFetch(path,...args);
    };`});
  const home='http://127.0.0.1:'+ports.dp+'/home/?mock';
  async function open(url, ready) {await cdp('Page.navigate',{url});await until('location.href.startsWith('+JSON.stringify(url.split('#')[0])+') && ('+ready+')');}
  await open(home, 'location.hash==="#/lobby"');
  await evaluate('sessionStorage.setItem("nav-offline","1")'); await reload();
  await until('document.documentElement.dataset.handshake==="failed"');
  for (const theme of ['light','dark']) {
    await evaluate('document.documentElement.dataset.theme='+JSON.stringify(theme)); await shot('retry-'+theme);
  }
  assert.match(await evaluate('document.getElementById("gui-compatibility").innerText'),/重试/);
  await evaluate('sessionStorage.removeItem("nav-offline");document.querySelector("#gui-compatibility button").click()');
  await until('document.documentElement.dataset.handshake==="ready" && !!document.getElementById("next") && location.hash==="#/lobby"');
  await pause(400);
  assert.deepEqual(await evaluate('navErrors'), []);
  for (const theme of ['light','dark']) {
    await evaluate('document.documentElement.dataset.theme='+JSON.stringify(theme));
    await evaluate('document.getElementById("next").click()');await until('location.hash==="#/newplan"');
    await evaluate('document.querySelector(".np-name").value="导航保留表单";document.querySelector(".np-name").dispatchEvent(new Event("input",{bubbles:true}))');
    await evaluate('document.querySelector(".np-batch").value="导航批次";document.querySelector(".np-batch").dispatchEvent(new Event("input",{bubbles:true}))');
    await pause(300); await evaluate('history.back()'); await until('location.hash==="#/lobby" && !document.documentElement.dataset.mode');
    await shot('back-'+theme); await evaluate('history.forward()');
    await until('document.documentElement.dataset.mode==="newplan" && document.querySelector(".np-name").value==="导航保留表单"');
    assert.equal(await evaluate('document.querySelector(".np-batch").value'), '导航批次');
    await shot('forward-'+theme); await pause(300); await reload();
    await until('document.documentElement.dataset.mode==="newplan" && document.querySelector(".np-name").value==="导航保留表单"');
    assert.equal(await evaluate('document.querySelector(".np-batch").value'), '导航批次');
    await evaluate('document.getElementById("next").click()');await until('location.hash==="#/design"');
    await evaluate('document.querySelector(\'[data-a="sample"]\').click()');
    await until('!document.querySelector(".empty-c").classList.contains("on")');
    await pause(600); await evaluate('history.back()'); await until('document.documentElement.dataset.mode==="newplan"');
    await evaluate('history.forward()');await until('document.documentElement.dataset.mode==="design"');
    assert.equal(await evaluate('!document.querySelector(".empty-c").classList.contains("on")'), true);
    await pause(500); await reload();await until('document.documentElement.dataset.mode==="design" && !document.querySelector(".empty-c").classList.contains("on")');
    await until('!document.getElementById("next").disabled');
    await evaluate('document.getElementById("next").click()');await until('location.hash==="#/preview"');
    await evaluate('history.back()');await until('document.documentElement.dataset.mode==="design"');
    await evaluate('history.forward()');await until('document.documentElement.dataset.mode==="preview"');
    await pause(400);await reload();await until('document.documentElement.dataset.mode==="preview" && document.documentElement.dataset.navigation==="ready"');
    await evaluate('document.getElementById("back").click()');await until('document.documentElement.dataset.mode==="design" && document.documentElement.dataset.navigation==="ready"');
    await evaluate('document.getElementById("back").click()');await until('location.hash==="#/lobby"');
  }
  await open(home+'#/library', 'document.documentElement.dataset.home==="library" && location.hash==="#/library"');
  await pause(300); await reload();await until('document.documentElement.dataset.home==="library" && location.hash==="#/library"');
  assert.deepEqual(await evaluate('navErrors'), []);assert.deepEqual(await evaluate('navCsp'), []);
  // Exercise the live state path (no hardware provider), including a change while a form owns the page.
  await open('http://127.0.0.1:'+ports.dp+'/home/?nav-library#/library', 'document.documentElement.dataset.home==="library" && location.hash==="#/library"');
  await evaluate(`{
    const native=fetch;window.navStateReads=0;window.navCatalogueName='旧盘状态';
    window.fetch=async(path,...args)=>{
      const r=await native(path,...args);if(path!=='/api/state')return r;
      navStateReads++;const j=await r.json();j.catalogue.dvd=[{id:'nav-test-batch',row:'dvd',kind:'disc',name:navCatalogueName,mid:'NAV',s:navCatalogueName==='旧盘状态'?'unknown':'good'}];
      return new Response(JSON.stringify(j),{headers:{'Content-Type':'application/json'}});
    };dispatchEvent(new Event('dp-catalogue-changed'));
  }`);
  await until('document.getElementById("name").textContent.includes("旧盘状态")');
  await evaluate('document.getElementById("back").click()'); await until('location.hash==="#/lobby"');
  await evaluate('document.getElementById("next").click()'); await until('document.documentElement.dataset.mode==="newplan"');
  await evaluate('navCatalogueName="最新盘状态";dispatchEvent(new Event("dp-catalogue-changed"))');
  await evaluate('document.getElementById("back").click()');await until('!document.documentElement.dataset.mode');
  await evaluate('document.getElementById("library").click()');
  await until('document.documentElement.dataset.home==="library" && document.getElementById("name").textContent.includes("最新盘状态")');
  assert(await evaluate('navStateReads>=2'));
  assert.deepEqual(await evaluate('navErrors'), []);assert.deepEqual(await evaluate('navCsp'), []);
  await open('http://127.0.0.1:'+ports.lab+'/', '!!document.querySelector(".lb-world") && !document.getElementById("next").disabled');
  await pause(400);
  console.log('LAB scene state',await evaluate('JSON.stringify({errors:navErrors,images:[...document.querySelectorAll(".lb-layer>img")].map(i=>({src:i.src,w:i.naturalWidth})),size:document.querySelector(".lb-world").getBoundingClientRect().toJSON()})'));
  // Controlled job response goes through the real run/watch/error UI, with no disk-filling command.
  await evaluate(`{
    const native=fetch;window.fetch=async(path,options)=>{
      if(path==='/api/run')return new Response(JSON.stringify({job:'nav-disk-full'}),{headers:{'Content-Type':'application/json'}});
      if(path==='/api/job/nav-disk-full')return new Response(JSON.stringify({id:'nav-disk-full',state:'failed',argv:['step','checkdisc'],
        log:'OSError: [Errno 28] No space left on device',result:{errors:[{message:'exit code 1'}]},t0:Date.now()/1000,t1:Date.now()/1000}),{headers:{'Content-Type':'application/json'}});
      const r=await native(path,options);
      if(path==='/api/status'){
        const j=await r.json();j.outputs.status.current='checkdisc';
        j.outputs.status.flow.forEach((s,i)=>{s.done=i<6;s.current=s.key==='checkdisc'});
        return new Response(JSON.stringify(j),{headers:{'Content-Type':'application/json'}});
      }
      return r;
    };
  }`);
  // Refresh is owned by the app's normal polling; a read-only status paint occurs within 8 seconds.
  await until('document.getElementById("next").innerText.includes("生成检查盘")');
  for (const theme of ['paper','dark']) {
    await evaluate(`if(document.documentElement.dataset.theme!==${JSON.stringify(theme)})document.getElementById('theme').click()`);
    await until('[...document.querySelectorAll(".lb-layer>img")].every(i=>i.complete&&i.naturalWidth>0)');
    await shot('lab-desk-'+theme);
    await until('!document.getElementById("next").disabled');
    await evaluate('document.getElementById("next").click()');await until('document.documentElement.dataset.mode==="burner"');
    await until('[...document.querySelectorAll("#hero img")].length>0 && [...document.querySelectorAll("#hero img")].every(i=>i.complete&&i.naturalWidth>0)');
    await evaluate('document.getElementById("next").click()');
    await until('document.getElementById("toast").innerText.includes("磁盘空间不足")');
    await until('document.getElementById("job").hidden');
    assert.equal(await evaluate('document.getElementById("toast").getAttribute("role")'),'alert');
    await shot('lab-error-'+theme);
    await evaluate('document.getElementById("back").click()');await until('!document.documentElement.dataset.mode');
  }
  assert.deepEqual(await evaluate('navErrors'), []); assert.deepEqual(await evaluate('navCsp'), []);
  console.log('Flow navigation: retry recovery, CSP, back/forward with form and image state, refresh, deep library link, two themes; screenshots saved.');
} catch (error) {
  console.error('Fixture stderr:', err.slice(-6000));
  console.error('Network errors:',JSON.stringify(networkErrors));
  throw error;
} finally {
  socket?.close();browser?.kill();if(browser&&browser.exitCode===null)await new Promise(r=>browser.once('exit',r));
  server.stdin.end();if(server.exitCode===null)await new Promise(r=>server.once('exit',r));
  assert.equal(resolve(dir,'..'),resolve(tmpdir()));rmSync(dir,{recursive:true,force:true,maxRetries:5,retryDelay:200});
}
