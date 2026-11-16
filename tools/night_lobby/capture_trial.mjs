// Local fixture + headless Edge. Only base is substituted in the second capture.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {readFileSync, writeFileSync, existsSync, mkdirSync} from 'node:fs';
import {join, resolve} from 'node:path';
import {rm} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const trial = process.env.LOBBY_TRIAL || 'F:/dp-archive/tmp/lobbypool/trial';
const profile = join(trial, 'edge-profile');
const fixture = join(trial, 'capture-fixture');
assert(!existsSync(profile) && !existsSync(fixture), 'Use fresh disposable capture folders');
const env = {...process.env, TEMP:trial, TMP:trial, PYTHONDONTWRITEBYTECODE:'1'};
const server = spawn(process.env.PYTHON || 'python', ['-B','-X','utf8','tests/webguide_http_fixture.py',fixture],
  {cwd:root,env,stdio:['pipe','pipe','pipe'],windowsHide:true});
let output='', errors='', browser, ws, seq=0, replacement=false;
const substitutions=[];
const pending = new Map(), evidence=[];
server.stdout.on('data',d=>output+=d); server.stderr.on('data',d=>errors+=d);
const pause=ms=>new Promise(r=>setTimeout(r,ms));
function cdp(method,params={}) {
  const id=++seq;
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(Error(method));},20000);
    pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));
  });
}
async function evaluate(expression) {
  const r=await cdp('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
  assert(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;
}
async function until(expression) {
  for(let i=0;i<600;i++) {if(await evaluate(expression))return;await pause(100);}
  throw Error('Timeout '+expression);
}
try {
  for(let i=0;i<300&&!output.includes('\n')&&server.exitCode===null;i++)await pause(100);
  assert(output.includes('\n'),errors);
  const ports=JSON.parse(output.split('\n')[0]);
  browser=spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',[
    '--headless=new','--disable-gpu','--disable-background-networking','--no-first-run',
    '--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],
    {stdio:'ignore',windowsHide:true,env});
  for(let i=0;i<300&&!existsSync(join(profile,'DevToolsActivePort'));i++)await pause(100);
  const port=readFileSync(join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];
  const tabs=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
  ws.onmessage=({data})=>{
    const m=JSON.parse(data), p=pending.get(m.id);
    if(p){clearTimeout(p.timer);pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}
    if(m.method==='Fetch.requestPaused') {
      const id=m.params.requestId;
      if(replacement) {substitutions.push(m.params.request.url);cdp('Fetch.fulfillRequest',{requestId:id,responseCode:200,
        responseHeaders:[{name:'Content-Type',value:'image/webp'},{name:'Cache-Control',value:'no-store'}],
        body:readFileSync(join(trial,'base_trial_dark.webp')).toString('base64')}).catch(e=>errors+=String(e));}
      else cdp('Fetch.continueRequest',{requestId:id}).catch(e=>errors+=String(e));
    }
  };
  await cdp('Page.enable'); await cdp('Runtime.enable'); await cdp('Network.enable');
  await cdp('Network.setCacheDisabled',{cacheDisabled:true});
  await cdp('Fetch.enable',{patterns:[{urlPattern:'*/home/lobby/base_dark.webp*',requestStage:'Request'}]});
  await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await cdp('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  await cdp('Page.addScriptToEvaluateOnNewDocument',{source:`
    localStorage.setItem('dp-theme','dark');localStorage.setItem('dp-lang','zh');
    localStorage.setItem('dp-motion','off');localStorage.setItem('dp-sound','off');
    window.trialErrors=[];window.trialCsp=[];window.trialLoad=crypto.randomUUID();
    addEventListener('error',e=>trialErrors.push(e.message));
    addEventListener('unhandledrejection',e=>trialErrors.push(String(e.reason)));
    addEventListener('securitypolicyviolation',e=>trialCsp.push(e.effectiveDirective));
    // Fixed time for matching lobby status and greeting in both captures.
    const NativeDate=Date;globalThis.Date=class extends NativeDate {
      constructor(...args){super(...(args.length?args:['2026-11-16T20:00:00Z']));}
      static now(){return new NativeDate('2026-11-16T20:00:00Z').getTime();}
    };`});
  const url='http://127.0.0.1:'+ports.dp+'/home/?mock#/lobby';
  for(const name of ['lobby_old_dark','lobby_trial_dark']) {
    replacement=name.includes('trial');
    if(replacement) {
      for(let i=0;i<1800&&!existsSync(join(trial,'paper-check.json'));i++)await pause(1000);
      assert(existsSync(join(trial,'paper-check.json')),'No paper check');
    }
    if(replacement) {
      const previous=await evaluate('trialLoad');
      await cdp('Page.reload',{ignoreCache:true});
      await until('window.trialLoad && trialLoad!=='+JSON.stringify(previous));
    } else await cdp('Page.navigate',{url});
    await until(`document.documentElement.dataset.handshake==='ready' && document.querySelector('.lb-layer[data-name="base"] img')?.complete && document.querySelector('.lb-label[data-target]')?.textContent?.trim().length>0`);
    await evaluate(`Promise.all([...document.querySelectorAll('.lb-layer img')].map(i=>i.decode()))`);
    await evaluate('document.fonts.ready');
    await pause(700);
    const state=await evaluate(`({theme:document.documentElement.dataset.theme,mode:document.documentElement.dataset.mode||'lobby',url:location.href,errors:trialErrors,csp:trialCsp,width:innerWidth,height:innerHeight,base:[document.querySelector('.lb-layer[data-name="base"] img').naturalWidth,document.querySelector('.lb-layer[data-name="base"] img').naturalHeight],layerTransforms:[...document.querySelectorAll('.lb-layer')].map(e=>({name:e.dataset.name,translate:getComputedStyle(e).translate})),worldTransform:getComputedStyle(document.querySelector('.lb-world')).transform})`);
    assert.equal(state.theme,'dark');assert.deepEqual(state.errors,[]);assert.deepEqual(state.csp,[]);
    writeFileSync(join(trial,name+'.png'),Buffer.from((await cdp('Page.captureScreenshot',{format:'png'})).data,'base64'));
    if(replacement)assert(substitutions.length>0,'Trial base response must actually be replaced');
    evidence.push({name,base_replaced_only:replacement,substitutions:[...substitutions],...state});
    writeFileSync(join(trial,'capture.json'),JSON.stringify(evidence,null,2)+'\n');
    console.log(name,JSON.stringify(state));
  }
  assert.equal(evidence[0].worldTransform,evidence[1].worldTransform);
  assert.deepEqual(evidence[0].layerTransforms,evidence[1].layerTransforms);
} finally {
  if(ws&&ws.readyState===1){await cdp('Browser.close').catch(()=>{});ws.close();}
  browser?.kill();server.stdin.end();
  await pause(1500);
  for(const p of [profile,fixture]) {
    assert(resolve(p).startsWith(resolve(trial)+'/')||resolve(p).startsWith(resolve(trial)+'\\'));
    await rm(p,{recursive:true,force:true,maxRetries:3,retryDelay:500});
  }
}
