// Real HTTP, real Disc Lab practice and shipped UI. All output and Edge profiles stay on D:.
import assert from 'node:assert/strict';
import {tmpdir} from 'node:os';
import {existsSync,mkdirSync,mkdtempSync,readFileSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {spawn,spawnSync} from 'node:child_process';

const base=process.env.RW_DISCS_TEST_ROOT??join(tmpdir(),'discprobe-rwdiscs');mkdirSync(base,{recursive:true});
const dir=mkdtempSync(join(base,'browser-')),lab=join(dir,'lab'),shots=join(base,'shots');mkdirSync(shots,{recursive:true});
const edge=process.env.PASTWORKS_TEST_BROWSER??'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
assert.ok(existsSync(edge));
const delay=ms=>new Promise(r=>setTimeout(r,ms));
let server,browser,socket,seq=0,origin,output='';const pending=new Map(),checks=[];
const cdp=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
async function evaluate(expression){const r=await cdp('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});assert.ok(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;}
async function until(expression,message){const deadline=Date.now()+Number(process.env.BROWSER_WAIT_MS||60000);while(Date.now()<deadline){let ok=false;try{ok=await evaluate(expression);}catch{}if(ok)return;await delay(50);}throw Error(message+': '+JSON.stringify(await evaluate('({errors:window.bcErrors,text:document.body.innerText.slice(-3000)})')));}
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
  server=spawn(process.env.PYTHON??'python',['-X','utf8','-B',fixture,lab],{windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env,TEMP:base,TMP:base,RW_DISC_TEST_MEDIA:'dvd-rw'}});
  server.stdout.on('data',b=>output+=b);server.stderr.on('data',b=>output+=b);
  let ready;for(let i=0;i<300&&!ready;i++){try{ready=JSON.parse(readFileSync(join(lab,'ready.json'),'utf8'));}catch{}if(!ready)await delay(100);}assert.ok(ready,output);
  origin=`http://127.0.0.1:${ready.port}`;
  let live=false;for(let i=0;i<300&&!live;i++){try{live=(await fetch(origin+'/api/state')).ok;}catch{}if(!live)await delay(100);}assert.ok(live,output);
  await request('/api/burn-speeds?drive=X%3A&media=dvd');
  const token=await request('/api/burn-token');
  const job=await request('/api/run',{action:'calibrate',media:'dvd',drive:'X:',args:{iso:'iso/stop.iso',speed:'4x',burn_speed:4},burn_token:token.token});
  browser=spawn(edge,['--headless=new','--mute-audio','--disable-gpu','--disable-background-networking','--disable-component-update','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${join(dir,'profile')}`,'about:blank'],{windowsHide:true,stdio:'ignore'});
  let port;for(let i=0;i<100&&!port;i++){try{port=readFileSync(join(dir,'profile','DevToolsActivePort'),'utf8').split(/\r?\n/)[0];}catch{}if(!port)await delay(100);}assert.ok(port);
  const targets=await fetch(`http://127.0.0.1:${port}/json/list`).then(r=>r.json());
  socket=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  socket.onmessage=({data})=>{const m=JSON.parse(data),p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}};
  await cdp('Page.enable');await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await cdp('Page.addScriptToEvaluateOnNewDocument',{source:`localStorage.setItem('dp-lang','zh');window.bcErrors=[];addEventListener('error',e=>bcErrors.push(e.message));addEventListener('unhandledrejection',e=>bcErrors.push(String(e.reason)));`});
  await cdp('Page.navigate',{url:origin+'/home/'});
  await until(`document.documentElement.dataset.mode==='cal' && document.querySelector('#job-cancel').textContent==='停止刻录'`,'live calibration attached in burn phase');

  // Let the first write reach about 40%; the two reading locks put the stop near halfway.
  for(let i=0;i<500;i++){const j=await request('/api/jobs/'+job.job);if(j.events.some(e=>e.type==='progress'&&e.fraction>=.4))break;assert.equal(j.exit,null,JSON.stringify(j.events.slice(-5)));await delay(100);}
  for(const theme of ['paper','dark']){
    await evaluate(`document.documentElement.dataset.theme=${JSON.stringify(theme)}`);
    await click('#job-cancel');
    await check(`document.querySelector('.burn-stop-risk').textContent==='停止后这次刻录作废，要擦掉才能重新刻。'`,'rewritable stop risk '+theme);
    await shot('rw-stop-'+theme);
    await until(`document.querySelector('.burn-stop .kit-slide-knob').getAttribute('aria-disabled')==='false'`,'lock elapsed');
    if(theme==='paper')await click('.burn-stop-keep');
  }
  await drag();
  await until(`document.querySelector('#cal').textContent.includes('你在刻录时点了停止')`,'stopped result');
  await check(`document.querySelector('#next-text').textContent==='擦除后重新刻'`,'RW recovery button');
  for(const theme of ['paper','dark']){
    await evaluate(`document.documentElement.dataset.theme=${JSON.stringify(theme)}`);await shot('rw-cancelled-'+theme);
  }
  let stopped=await request('/api/jobs/'+job.job);
  for(let i=0;i<150&&stopped.exit===null;i++){
    await delay(100);
    stopped=await request('/api/jobs/'+job.job);
  }
  writeFileSync(join(dir,'cancelled-job.json'),JSON.stringify(stopped,null,2));
  assert.notEqual(stopped.exit,null,'cancelled job has exited before reloading');
  assert.equal(stopped.cancellation.by,'user');
  assert.ok(stopped.cancellation.fraction>=.4 && stopped.cancellation.fraction<=.75);checks.push('DVD-RW is stopped near halfway');
  await cdp('Page.navigate',{url:origin+'/home/'});
  await until(`document.querySelector('#next-text').textContent==='擦除后重新刻'`,'reload retains RW recovery');
  await until(`document.documentElement.dataset.navigation==='ready'`,'navigation ready after reload');
  // Prewarming can briefly unhide the other page; it must never own calibration's Next.
  await evaluate(`if(document.querySelector('.np'))document.querySelector('.np').hidden=false`);
  await click('#next');
  await evaluate(`if(document.querySelector('.np'))document.querySelector('.np').hidden=true`);
  await until(`document.querySelector('#next-text').textContent==='滑动确认擦除后重刻'`,'erase confirmation uses start slider');
  await check(`document.querySelector('#cal').textContent.includes('盘上的内容会被清掉')`,'destructive copy visible before erase');
  await check(`document.querySelector('.next-confirm .kit-slide-label').textContent==='滑动确认擦除后重刻'`,'erase action is visible on the slider');
  for(const theme of ['paper','dark']){
    await evaluate(`document.documentElement.dataset.theme=${JSON.stringify(theme)}`);await shot('rw-erase-slider-'+theme);
  }
  let all=await request('/api/state');assert.equal(all.jobs.length,1);checks.push('opening erase confirmation starts no job');
  await evaluate(`document.querySelector('.next-confirm .kit-slide-knob').focus()`);
  await key('keyDown',' ');await delay(1150);await key('keyUp',' ');
  await until(`document.querySelector('#cal h2').textContent==='正在擦除光盘'`,'real erase progress');
  for(const theme of ['paper','dark']){
    await evaluate(`document.documentElement.dataset.theme=${JSON.stringify(theme)}`);await shot('rw-erase-progress-'+theme);
  }
  await check(`!document.querySelector('#cal-ruler .step:first-child .tick')`,'measurement step not checked during erasing');
  let completed,redo;
  for(let i=0;i<900;i++){
    all=await request('/api/state');redo=all.jobs.find(j=>j.id!==job.job);
    if(redo){const detail=await request('/api/jobs/'+redo.id);if(detail.events.some(e=>e.type==='burn_result'&&e.result==='completed')){completed=detail;break;}}
    await delay(100);
  }
  assert.ok(completed,'rewrite completed');
  const eraseIndex=completed.events.findIndex(e=>e.type==='erase_result'&&e.result==='completed');
  const burnIndex=completed.events.findIndex(e=>e.type==='burn_speed');
  assert.ok(eraseIndex>=0 && burnIndex>eraseIndex);checks.push('real erase completes before rewrite starts');
  assert.equal(completed.events[eraseIndex].disc.blank,true);checks.push('erase returns virtual disc to blank');
  assert.ok(completed.events.some(e=>e.type==='burn_result'&&e.result==='completed'));checks.push('virtual rewrite completed');
  writeFileSync(join(dir,'rewrite-job.json'),JSON.stringify(completed,null,2));
  if(completed.exit===null)await request('/api/jobs/'+redo.id+'/cancel',{}); // only the read-only measurement after the completed write
  for(let i=0;i<200;i++){if((await request('/api/jobs/'+redo.id)).exit!==null)break;await delay(100);}await delay(600);
  // Exercise the shipped burn page too; this adapter only records UI calls.
  await evaluate(`(async()=>{
    const burn=await import('./burn.js'),backend=await import('./api.js');window.rwBurnCalls=[];window.rwStops=0;
    const api={backend,lang:()=> 'zh',reduce:true,$:id=>document.getElementById(id),meta:await fetch('rows.json').then(r=>r.json()),cam:document.querySelector('.cam'),burnerLayer:document.querySelector('.layer.burner'),focusDrive(){},placeDisc(){},setTray(){},nextWhy(){}};
    burn.start(api,{media:'dvd',item:{name:'DVD-RW'},iso:{path:'iso/stop.iso',sectors:524288,bytes:1073741824},drive:{id:'X:',name:'Disc Lab',speeds:[4],rewritable:true},discIn:true,back(){},
      burn(onProgress,opts){rwBurnCalls.push(opts);window.rwProgress=onProgress;return {cancel(){rwStops++;onProgress({status:'cancelled'})}}}});
  })()`);
  await click('.burn-consent input');
  await evaluate(`document.querySelector('.next-confirm .kit-slide-knob').focus()`);await key('keyDown',' ');await delay(1150);await key('keyUp',' ');
  await until(`rwBurnCalls.length===1`,'burn page starts after slider confirmation');
  await click('.burn-actions [data-a="cancel"]');
  await check(`document.querySelector('.burn-stop-risk').textContent.includes('要擦掉才能重新刻')`,'burn page uses RW stop risk');
  await until(`document.querySelector('.burn-stop .kit-slide-knob')?.getAttribute('aria-disabled')==='false'`,'burn page stop unlocks');await drag();
  await check(`document.querySelector('.burn-actions [data-a="retry"]').textContent==='擦除后重新刻'`,'burn page has RW recovery action');
  await click('.burn-actions [data-a="retry"]');
  await check(`!document.querySelector('.burn-consent input').checked && document.querySelector('.burn-warning').textContent.includes('盘上的内容会被清掉')`,'burn page requires fresh erase consent');
  await check(`rwBurnCalls.length===1`,'burn page recovery button starts no erase');
  await click('.burn-consent input');
  await evaluate(`document.querySelector('.next-confirm .kit-slide-knob').focus()`);await key('keyDown',' ');await delay(1150);await key('keyUp',' ');
  await check(`rwBurnCalls.length===2 && rwBurnCalls[1].erase===true`,'burn page slider sends explicit erase option');
  await evaluate(`rwProgress({erasing:true,progress:.8});rwProgress({erasing:false,progress:0});rwProgress({progress:.1})`);
  await check(`document.querySelector('.burn-timing') && !document.querySelector('.burn-result h2').textContent.includes('擦除')`,'burn page returns from erasing to writing');
  await check(`bcErrors.length===0`,'no browser errors');
  writeFileSync(join(dir,'checks.json'),JSON.stringify(checks,null,2));
  console.log(JSON.stringify({passed:checks.length,dir,shots},null,2));
}finally{
  writeFileSync(join(dir,'practice.log'),output);writeFileSync(join(dir,'checks.json'),JSON.stringify(checks,null,2));
  socket?.close();browser?.kill();
  if(server?.pid)spawnSync('taskkill',['/PID',String(server.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
}
