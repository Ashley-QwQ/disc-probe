// Real HTTP, real Disc Lab practice and shipped UI. All output and Edge profiles stay on D:.
import assert from 'node:assert/strict';
import {existsSync,mkdirSync,mkdtempSync,readFileSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {spawn,spawnSync} from 'node:child_process';

const base=process.env.BURN_CANCEL_TEST_ROOT??'D:/dp-dev/tmp/burncancel';mkdirSync(base,{recursive:true});
const dir=mkdtempSync(join(base,'browser-')),lab=join(dir,'lab'),shots=join(base,'shots');mkdirSync(shots,{recursive:true});
const edge=process.env.PASTWORKS_TEST_BROWSER??'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
assert.ok(existsSync(edge));
const delay=ms=>new Promise(r=>setTimeout(r,ms));
let server,browser,socket,seq=0,origin,output='';const pending=new Map(),checks=[];
const cdp=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
async function evaluate(expression){const r=await cdp('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});assert.ok(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;}
async function until(expression,message){for(let i=0;i<400;i++){if(await evaluate(expression))return;await delay(50);}throw Error(message+': '+JSON.stringify(await evaluate('({errors:window.bcErrors,text:document.body.innerText.slice(-3000)})')));}
async function check(expression,message){assert.ok(await evaluate(expression),message);checks.push(message);}
async function shot(name){await evaluate('document.fonts.ready');await delay(120);const r=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});writeFileSync(join(shots,name+'.png'),Buffer.from(r.data,'base64'));}
async function request(path,body){const r=await fetch(origin+path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const data=await r.json();assert.ok(r.ok,JSON.stringify(data));return data;}
const click=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
const key=async(type,value)=>cdp('Input.dispatchKeyEvent',{type,key:value,code:value===' '?'Space':value,windowsVirtualKeyCode:value==='Enter'?13:value==='Escape'?27:value===' '?32:35});
async function drag(complete=true){
  const r=await evaluate(`(()=>{const k=document.querySelector('.burn-stop .kit-slide-knob').getBoundingClientRect(),t=document.querySelector('.burn-stop .kit-slide-track').getBoundingClientRect();return {x:k.x+k.width/2,y:k.y+k.height/2,end:t.right-k.width/2-4};})()`);
  await cdp('Input.dispatchMouseEvent',{type:'mousePressed',x:r.x,y:r.y,button:'left',clickCount:1});
  await cdp('Input.dispatchMouseEvent',{type:'mouseMoved',x:complete?r.end:r.x+20,y:r.y,button:'left',buttons:1});
  await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',x:complete?r.end:r.x+20,y:r.y,button:'left',clickCount:1});
}
try{
  const fixture=resolve('tests/burn_cancel_lab_fixture.py');
  server=spawn(process.env.PYTHON??'python',['-X','utf8','-B',fixture,lab],{windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env,TEMP:base,TMP:base}});
  server.stdout.on('data',b=>output+=b);server.stderr.on('data',b=>output+=b);
  let ready;for(let i=0;i<300&&!ready;i++){try{ready=JSON.parse(readFileSync(join(lab,'ready.json'),'utf8'));}catch{}if(!ready)await delay(100);}assert.ok(ready,output);
  origin=`http://127.0.0.1:${ready.port}`;
  let live=false;for(let i=0;i<300&&!live;i++){try{live=(await fetch(origin+'/api/state')).ok;}catch{}if(!live)await delay(100);}assert.ok(live,output);
  await request('/api/burn-speeds?drive=X%3A&media=dvd');
  const token=await request('/api/burn-token');
  const job=await request('/api/run',{action:'calibrate',media:'dvd',drive:'X:',args:{iso:'iso/stop.iso',speed:'4x',burn_speed:4},burn_token:token.token});
  browser=spawn(edge,['--headless=new','--disable-gpu','--disable-background-networking','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${join(dir,'profile')}`,'about:blank'],{windowsHide:true,stdio:'ignore'});
  let port;for(let i=0;i<100&&!port;i++){try{port=readFileSync(join(dir,'profile','DevToolsActivePort'),'utf8').split(/\r?\n/)[0];}catch{}if(!port)await delay(100);}assert.ok(port);
  const targets=await fetch(`http://127.0.0.1:${port}/json/list`).then(r=>r.json());
  socket=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  socket.onmessage=({data})=>{const m=JSON.parse(data),p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}};
  await cdp('Page.enable');await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  // Windows Server turns animation effects off, which headless Edge reports as reduced motion; start from no preference.
  await cdp('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'no-preference'}]});
  await cdp('Page.addScriptToEvaluateOnNewDocument',{source:`localStorage.setItem('dp-lang','zh');window.bcErrors=[];addEventListener('error',e=>bcErrors.push(e.message));addEventListener('unhandledrejection',e=>bcErrors.push(String(e.reason)));`});
  await cdp('Page.navigate',{url:origin+'/home/'});
  await until(`document.documentElement.dataset.mode==='cal' && document.querySelector('#job-cancel').textContent==='停止刻录'`,'live calibration attached in burn phase');
  await shot('stop-button');
  // Reopening is independent: Esc, external click and Continue never send cancellation.
  for(const method of ['escape','outside','keep']){
    await click('#job-cancel');await until(`!!document.querySelector('.burn-stop')`,'stop expanded');
    await check(`document.querySelector('.burn-stop .burn-stop-count')?.textContent==='3'`,'fresh three-second lock, counted on the knob '+method);
    await check(`(()=>{const p=document.querySelector('.burn-stop').getBoundingClientRect(),b=document.querySelector('.job-bar').getBoundingClientRect();return p.bottom<=b.top;})()`,'panel opens above the progress bar '+method);
    await drag();
    await evaluate(`document.querySelector('.burn-stop .kit-slide-knob').focus()`);
    const held=method==='outside'?' ':'Enter';
    await key('keyDown',held);await delay(1150);await key('keyUp',held);
    assert.equal((await request('/api/jobs/'+job.job)).cancellation,null);
    if(method==='escape'){await key('keyDown','Escape');await key('keyUp','Escape');}
    if(method==='outside'){await cdp('Input.dispatchMouseEvent',{type:'mousePressed',x:720,y:450,button:'left',clickCount:1});await cdp('Input.dispatchMouseEvent',{type:'mouseReleased',x:720,y:450,button:'left',clickCount:1});}
    if(method==='keep')await click('.burn-stop-keep');
    await until(`!document.querySelector('.burn-stop')`,'disclosure dismissed '+method);
    assert.equal((await request('/api/jobs/'+job.job)).cancellation,null);checks.push(method+' dismisses without cancelling');
  }
  for(const theme of ['paper','dark']){
    await evaluate(`document.documentElement.dataset.theme=${JSON.stringify(theme)}`);
    await click('#job-cancel');
    await shot('slider-locked-'+theme);
    await check(`getComputedStyle(document.querySelector('.burn-stop-risk')).animationName==='burn-stop-risk'`,'risk flashes '+theme);
    await cdp('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
    await check(`getComputedStyle(document.querySelector('.burn-stop-risk')).animationName==='none'`,'reduced motion keeps red without flashing '+theme);
    await cdp('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'no-preference'}]});
    await until(`document.querySelector('.burn-stop .kit-slide-knob').getAttribute('aria-disabled')==='false'`,'three-second lock elapsed');
    await check(`!document.querySelector('.burn-stop .burn-stop-count') && !!document.querySelector('.burn-stop .kit-slide-knob svg')`,'unlocked knob shows the arrow again '+theme);
    await check(`document.querySelector('.burn-stop [role="status"]').getAttribute('aria-live')==='assertive'`,'risk announced '+theme);
    await shot('slider-ready-'+theme);
    if(theme==='paper')await click('.burn-stop-keep');
  }
  // The stop button stays visible as the anchor; pressing it again folds the panel without cancelling.
  await click('#job-cancel');await until(`!document.querySelector('.burn-stop')`,'stop button folds the panel');
  assert.equal((await request('/api/jobs/'+job.job)).cancellation,null);checks.push('stop button toggles the panel closed');
  await click('#job-cancel');await until(`document.querySelector('.burn-stop .kit-slide-knob')?.getAttribute('aria-disabled')==='false'`,'reopened lock elapsed');
  await drag(false);assert.equal((await request('/api/jobs/'+job.job)).cancellation,null);checks.push('partial drag never cancels');
  await delay(350); // Allow the existing slider's reset transition to return the knob home.
  await drag();
  await until(`document.querySelector('#cal').textContent.includes('你在刻录时点了停止')`,'cancelled burn result');
  await check(`document.querySelector('#next-text').textContent==='换一张空白盘重新刻' && !document.querySelector('#next').disabled`,'main action replaces the blank and burns again');
  await check(`!document.querySelector('#cal-ruler .step:first-child .tick')`,'measurement disc step is not checked');
  await check(`/约 [0-9]+%/.test(document.querySelector('#cal').textContent)`,'cancelled result includes recorded percentage');
  await shot('cancelled-result');
  const snapshot=await request('/api/jobs/'+job.job);assert.equal(snapshot.cancellation.by,'user');assert.equal(snapshot.cancellation.phase,'burn');
  assert.ok(snapshot.events.some(e=>e.type==='cancelled'&&e.by==='user'));checks.push('real HTTP snapshot preserves user cancellation');
  writeFileSync(join(dir,'cancelled-job.json'),JSON.stringify(snapshot,null,2));
  await cdp('Page.navigate',{url:origin+'/home/'});
  await until(`document.querySelector('#cal').textContent.includes('你在刻录时点了停止')`,'reload restores the cancelled result');
  await check(`document.querySelector('#next-text').textContent==='换一张空白盘重新刻'`,'reload keeps the safe retry action');
  // A fresh page uses the same API snapshot, replaying provenance after a finished job.
  await evaluate(`window.bcJob=${JSON.stringify(job.job)}`);
  await evaluate(`(async()=>{const backend=await import('./api.js');window.bcReplay=[];try{await backend.follow(bcJob,e=>bcReplay.push(e))}catch{}})()`);
  await check(`bcReplay.some(e=>e.type==='cancelled'&&e.by==='user')`,'finished follow replays user cancellation');
  const short=spawnSync(process.env.PYTHON??'python',['-X','utf8','-B',fixture,lab,'--short'],{windowsHide:true,encoding:'utf8'});assert.equal(short.status,0,short.stderr);
  // The home page refreshes the tray after a finished write. Wait for that read-only child,
  // then perform one serialized read so info cannot race it for the virtual drive.
  let tray;
  for(let i=0;i<100;i++){
    const r=await fetch(origin+'/api/disc',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({drive:'X:'})});
    if(r.status===409){await delay(100);continue;}assert.ok(r.ok,await r.clone().text());tray=await r.json();break;
  }
  assert.equal(tray?.disc?.sectors,576);
  await click('#next');await click('#next');
  await until(`document.querySelector('#cal').textContent.includes('576 扇区，约 1 MB')`,'finalized 576-sector disc rejected');
  await check(`document.querySelector('#cal').textContent.includes('多半是刻录中途停了') && document.querySelector('#next-text').textContent==='换一张空白盘重新刻'`,'short disc has cause and blank-disc recovery');
  await shot('short-576-disc');
  const direct=await request('/api/run',{action:'calibrate',drive:'X:',media:'dvd',args:{}});
  let core;for(let i=0;i<200;i++){core=await request('/api/jobs/'+direct.job);if(core.exit!==null)break;await delay(100);}
  assert.notEqual(core.exit,null);assert.notEqual(core.exit,0);assert.deepEqual(core.events.filter(e=>e.type==='step').map(e=>e.name),['check']);
  assert.match(core.result.reason,/576 sectors, about 1 MB/);checks.push('real Disc Lab 576-sector check never launches rotation');
  writeFileSync(join(dir,'short-disc-job.json'),JSON.stringify(core,null,2));
  // The burn-page button uses the same disclosure. Read-back remains immediate.
  await evaluate(`(async()=>{
    const burn=await import('./burn.js'),backend=await import('./api.js');window.bcBurnProgress=null;window.bcBurnStops=0;
    const api={backend,lang:()=> 'zh',reduce:true,$:id=>document.getElementById(id),meta:await fetch('rows.json').then(r=>r.json()),cam:document.querySelector('.cam'),burnerLayer:document.querySelector('.layer.burner'),
      focusDrive(){},placeDisc(){},setTray(){},nextWhy(){}};
    burn.start(api,{media:'dvd',item:{name:'停止按钮测试'},iso:{path:'iso/stop.iso',sectors:262144,bytes:536870912},drive:{id:'X:',name:'Disc Lab',speeds:[4]},discIn:true,back(){},
      burn(onProgress){window.bcBurnProgress=onProgress;return {cancel(){bcBurnStops++;onProgress({status:'cancelled'})}}}});
  })()`);
  await click('.burn-consent input');
  await evaluate(`document.querySelector('.next-confirm .kit-slide-knob').focus()`);await key('keyDown',' ');await delay(1150);await key('keyUp',' ');
  await until(`!!window.bcBurnProgress`,'Space holds the start slider');
  await click('.burn-actions [data-a="cancel"]');await check(`!!document.querySelector('.burn-stop') && bcBurnStops===0`,'burn page expands shared locked slider');
  await key('keyDown','Escape');await key('keyUp','Escape');
  await evaluate(`bcBurnProgress({verifying:true})`);await click('.burn-actions [data-a="cancel"]');
  await check(`bcBurnStops===1 && !document.querySelector('.burn-stop')`,'read-back stop is immediate');
  await check(`bcErrors.length===0`,'no browser errors');
  writeFileSync(join(dir,'checks.json'),JSON.stringify(checks,null,2));writeFileSync(join(dir,'practice.log'),output);
  console.log(JSON.stringify({passed:checks.length,dir,shots},null,2));
}finally{
  writeFileSync(join(dir,'practice.log'),output);writeFileSync(join(dir,'checks.json'),JSON.stringify(checks,null,2));
  socket?.close();browser?.kill();
  if(server?.pid)spawnSync('taskkill',['/PID',String(server.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
}
