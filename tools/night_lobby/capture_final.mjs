// Capture the written lobby and three destinations reached by clicking actual lobby targets.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {rm} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../../',import.meta.url));
const final='F:/dp-archive/tmp/lobbypool/final',profile=join(final,'capture-edge'),fixture=join(final,'capture-fixture');
assert(!existsSync(profile)&&!existsSync(fixture));
const env={...process.env,TEMP:final,TMP:final,PYTHONDONTWRITEBYTECODE:'1'};
const server=spawn(process.env.PYTHON||'python',['-B','-X','utf8','tests/webguide_http_fixture.py',fixture],
  {cwd:root,env,stdio:['pipe','pipe','pipe'],windowsHide:true});
let output='',stderr='',browser,ws,seq=0;const pending=new Map(),records=[];
server.stdout.on('data',d=>output+=d);server.stderr.on('data',d=>stderr+=d);
const pause=ms=>new Promise(r=>setTimeout(r,ms));
function cdp(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>{pending.delete(id);reject(Error(method));},30000);
  pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const r=await cdp('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
  assert(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;}
async function until(expression){for(let i=0;i<600;i++){if(await evaluate(expression))return;await pause(100);}throw Error(expression);}
try{
  for(let i=0;i<300&&!output.includes('\n')&&server.exitCode===null;i++)await pause(100);
  assert(output.includes('\n'),stderr);const ports=JSON.parse(output.split('\n')[0]);
  browser=spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',[
    '--headless=new','--disable-gpu','--disable-background-networking','--no-first-run','--no-default-browser-check',
    '--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{env,stdio:'ignore',windowsHide:true});
  for(let i=0;i<300&&!existsSync(join(profile,'DevToolsActivePort'));i++)await pause(100);
  const port=readFileSync(join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];
  const tabs=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
  ws.onmessage=({data})=>{const m=JSON.parse(data),p=pending.get(m.id);if(p){clearTimeout(p.timer);pending.delete(m.id);
    m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}};
  await cdp('Page.enable');await cdp('Runtime.enable');await cdp('Network.enable');
  await cdp('Network.setCacheDisabled',{cacheDisabled:true});
  await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await cdp('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  await cdp('Page.addScriptToEvaluateOnNewDocument',{source:`
    localStorage.setItem('dp-theme','dark');localStorage.setItem('dp-lang','zh');localStorage.setItem('dp-motion','off');localStorage.setItem('dp-sound','off');
    window.captureErrors=[];window.captureCsp=[];window.captureLoad=crypto.randomUUID();
    addEventListener('error',e=>captureErrors.push(e.message));addEventListener('unhandledrejection',e=>captureErrors.push(String(e.reason)));
    addEventListener('securitypolicyviolation',e=>captureCsp.push(e.effectiveDirective));
    const NativeDate=Date;globalThis.Date=class extends NativeDate{constructor(...args){super(...(args.length?args:['2026-11-16T20:00:00Z']));}
    static now(){return new NativeDate('2026-11-16T20:00:00Z').getTime();}};`});
  const url='http://127.0.0.1:'+ports.dp+'/home/?mock#/lobby';
  async function lobby(){await cdp('Page.navigate',{url:'about:blank'});await cdp('Page.navigate',{url});
    await until(`document.documentElement.dataset.handshake==='ready'&&document.querySelector('.lb-layer[data-name="base"] img')?.complete&&document.querySelector('.lb-label[data-target]')?.textContent?.trim().length>0`);
    await evaluate(`Promise.all([...document.querySelectorAll('.lb-layer img')].map(i=>i.decode()))`);await evaluate('document.fonts.ready');await pause(400);}
  async function shot(name,click){await evaluate('document.fonts.ready');await pause(800);
    const state=await evaluate(`({theme:document.documentElement.dataset.theme,mode:document.documentElement.dataset.mode||'lobby',url:location.href,width:innerWidth,height:innerHeight,errors:captureErrors,csp:captureCsp})`);
    assert.equal(state.theme,'dark');assert.deepEqual(state.errors,[]);assert.deepEqual(state.csp,[]);
    writeFileSync(join(final,name+'.png'),Buffer.from((await cdp('Page.captureScreenshot',{format:'png'})).data,'base64'));
    records.push({name,clicked_from_lobby:click||null,...state});writeFileSync(join(final,'capture.json'),JSON.stringify(records,null,2)+'\n');console.log(name,state);}
  await lobby();await shot('lobby-dark');
  for(const route of [
    {name:'lobby-to-newplan-dark',selector:'#lobby-new',mode:'newplan'},
    {name:'lobby-to-faxnews-dark',selector:'.lb-hit[data-target="faxnews"]',mode:'faxnews'},
    {name:'lobby-to-pastworks-dark',selector:'#lobby-open',mode:'pastworks'},
  ]){await lobby();await evaluate(`document.querySelector(${JSON.stringify(route.selector)}).click()`);
    await until(`document.documentElement.dataset.mode===${JSON.stringify(route.mode)}`);await shot(route.name,route.selector);}
}finally{
  if(ws&&ws.readyState===1){await cdp('Browser.close').catch(()=>{});ws.close();}browser?.kill();server.stdin.end();await pause(1500);
  for(const p of [profile,fixture]){assert(resolve(p).startsWith(resolve(final)+'\\')||resolve(p).startsWith(resolve(final)+'/'));
    await rm(p,{recursive:true,force:true,maxRetries:5,retryDelay:500});}
}
