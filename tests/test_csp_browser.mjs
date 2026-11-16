// Actual HTTP response policies in Edge, including phone + Lab. Loopback only.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtempSync,readFileSync,rmSync,readdirSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';

const dir=mkdtempSync(join(tmpdir(),'discprobe-csp-'));
const server=spawn(process.env.PYTHON||'python',['-B','-X','utf8','tests/webguide_http_fixture.py',join(dir,'data')],{stdio:['pipe','pipe','pipe'],windowsHide:true});
const pause=ms=>new Promise(r=>setTimeout(r,ms));
let serverOut='',serverError='',browser,socket,seq=0;
server.stdout.on('data',data=>serverOut+=data);server.stderr.on('data',data=>serverError+=data);
const pending=new Map();
const policies={};
async function cdp(method,params={}) {
  const id=++seq;
  const promise=new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},15000);
    pending.set(id,{resolve:v=>{clearTimeout(timer);resolve(v)},reject:e=>{clearTimeout(timer);reject(e)}});
  });
  socket.send(JSON.stringify({id,method,params}));return promise;
}
async function evaluate(expression) {
  const result=await cdp('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
  assert(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result.value;
}
async function until(expression) {
  for(let i=0;i<400;i++){if(await evaluate(expression))return;await pause(25);}
  throw Error('Timed out: '+expression+'; '+await evaluate('JSON.stringify(window.runtimeErrors)'));
}
function pages(dir) {
  return readdirSync(dir,{withFileTypes:true}).filter(e=>!/b[l]ind/i.test(e.name)).flatMap(e=>e.isDirectory()?pages(join(dir,e.name)):/\.html$/.test(e.name)?[join(dir,e.name)]:[]);
}
try {
  for(let i=0;i<400&&!serverOut.includes('\n')&&server.exitCode===null;i++)await pause(25);
  assert(serverOut.includes('\n'),serverError);const ports=JSON.parse(serverOut.split('\n')[0]);
  const profile=join(dir,'edge');
  browser=spawn(process.env.KIT_TEST_BROWSER||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',[
    '--headless=new','--disable-gpu','--disable-background-networking','--no-sandbox','--no-first-run','--no-default-browser-check',
    '--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:['ignore','ignore','pipe'],windowsHide:true});
  let port;
  for(let i=0;i<300;i++){try{port=readFileSync(join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];break;}catch{await pause(25);}}
  assert(port,'Edge did not start');
  const tabs=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  socket=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((res,rej)=>{socket.onopen=res;socket.onerror=rej});
  socket.onmessage=({data})=>{
    const msg=JSON.parse(data),p=pending.get(msg.id);
    if(msg.method==='Page.javascriptDialogOpening')cdp('Page.handleJavaScriptDialog',{accept:true}).catch(()=>{});
    if(p){pending.delete(msg.id);msg.error?p.reject(Error(JSON.stringify(msg.error))):p.resolve(msg.result)}
  };
  await cdp('Page.enable');await cdp('Runtime.enable');
  await cdp('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  await cdp('Page.addScriptToEvaluateOnNewDocument',{source:`
window.violations=[];window.runtimeErrors=[];
window.workerFrames=[];
const NativeWorker=window.Worker;
window.Worker=class extends NativeWorker{constructor(...args){super(...args);this.addEventListener('message',e=>{if(e.data.type==='frame')workerFrames.push({size:e.data.size,k:e.data.k})})}};
addEventListener('securitypolicyviolation',e=>violations.push({directive:e.effectiveDirective,uri:e.blockedURI}));
addEventListener('error',e=>runtimeErrors.push(e.message));addEventListener('unhandledrejection',e=>runtimeErrors.push(String(e.reason)));
`});
  const home='http://127.0.0.1:'+ports.dp;
  async function open(url,ready='document.readyState==="complete"') {
    const response=await fetch(url);policies[new URL(url).pathname]=response.headers.get('content-security-policy');
    await response.arrayBuffer();
    await cdp('Page.navigate',{url});await until('location.href==='+JSON.stringify(url)+' && '+ready);await pause(350);
  }
  await open(home+'/home/?mock','document.documentElement.dataset.handshake==="ready"');
  assert.deepEqual(await evaluate('runtimeErrors'),[]);
  await evaluate('const script=document.createElement("script");script.textContent="window.unapprovedScriptRan=true";document.body.append(script)');
  await until('violations.length===1');
  assert.equal(await evaluate('!!window.unapprovedScriptRan'),false,'unhashed inline scripts are blocked');
  assert.equal(await evaluate('violations[0].directive'),'script-src-elem');await evaluate('violations=[]');
  const scheme=await evaluate('document.querySelector(\'meta[name="color-scheme"]\').content');assert.equal(scheme,'light dark');
  await evaluate('document.getElementById("theme").click()');
  await until('document.querySelector(\'meta[name="color-scheme"]\').content===document.documentElement.dataset.theme');
  await evaluate('document.getElementById("next").click()');await until('document.documentElement.dataset.mode==="newplan"');
  await evaluate('document.querySelector(".np-name").value="CSP test";document.getElementById("next").click()');
  await until('document.documentElement.dataset.mode==="design"');
  await evaluate('document.querySelector(\'[data-a="sample"]\').click()');
  await until('!document.querySelector(".empty-c").classList.contains("on")');
  await evaluate('document.querySelector(\'[data-v="lamp"]\').click()');
  await until('workerFrames.length>0');
  assert.deepEqual(await evaluate('violations'),[],'desktop design/lamp CSP');
  // Test the real observer/worker suspension while a page remains foreground.
  const workerCheck=await evaluate(`(async()=>{
    const {observeActivity}=await import('./kit/shared.js'),{LampPreview}=await import('./design/editor-lamp.mjs');
    const c=document.createElement('canvas');c.style.cssText='position:fixed;top:0;width:32px;height:32px';document.body.append(c);
    const p=new LampPreview(),arg={rev:1,document:()=>({layers:[],materials:[],annulus_mm:[24,58]}),pose:{camera:[0,70,330],flash:[-44,90,330]},screen:200};
    let active;const dispose=observeActivity(c,v=>{active=v;if(!v)p.pause();});
    await new Promise(r=>setTimeout(r,80));p.view(arg);const old=p.worker;c.style.top='200vh';
    await new Promise(r=>setTimeout(r,100));const stopped=!active&&!p.worker;
    c.style.top='0';await new Promise(r=>setTimeout(r,100));if(active)p.view(arg);
    const resumed=active&&!!p.worker&&p.worker!==old;dispose();p.dispose();c.remove();return {stopped,resumed};
  })()`);
  assert.deepEqual(workerCheck,{stopped:true,resumed:true});
  assert.deepEqual(await evaluate('violations'),[]);
  // Native light dismissal and the Safari fallback both retain the cancel result.
  for (const fallback of [false,true]) {
    await evaluate(`(async()=>{const {askConflict}=await import('./pastworks/save.mjs');
      window.dialogResult='pending';askConflict({name:'CSP',doc:${fallback ? "{head:document.head,body:document.body,createElement:document.createElement.bind(document),defaultView:{HTMLDialogElement:class{}}}" : 'document'}}).then(r=>dialogResult=r);
      return document.querySelector('.pw-conflict').getAttribute('closedby');})()`);
    assert.equal(await evaluate('document.querySelector(".pw-conflict").getAttribute("closedby")'),'any');
    if(fallback) await evaluate('document.querySelector(".pw-conflict").dispatchEvent(new MouseEvent("click",{bubbles:true}))');
    else {
      for(const type of ['mousePressed','mouseReleased'])await cdp('Input.dispatchMouseEvent',{type,x:5,y:5,button:'left',clickCount:1});
    }
    await until('dialogResult!=="pending"');assert.equal(await evaluate('dialogResult'),null);
  }

  await cdp('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await open(home+ports.phone,'!!document.getElementById("camera")');
  assert.deepEqual(await evaluate('runtimeErrors'),[],'phone runtime');assert.deepEqual(await evaluate('violations'),[],'phone CSP');
  await cdp('Emulation.clearDeviceMetricsOverride');
  await open('http://127.0.0.1:'+ports.lab+'/','!!document.querySelector(".lb-world") && !document.getElementById("next").disabled');
  assert.deepEqual(await evaluate('runtimeErrors'),[],'Lab runtime');assert.deepEqual(await evaluate('violations'),[],'Lab CSP');
  await evaluate('document.getElementById("theme").click()');
  assert.equal(await evaluate('document.querySelector(\'meta[name="color-scheme"]\').content'),await evaluate('document.documentElement.dataset.theme==="dark"?"dark":"light"'));

  // All shipped HTML routes execute with their real policy. Developer previews may
  // need a run/project argument; only CSP violations are asserted for those routes.
  const web=resolve('discprobe/web'),all=pages(web);
  for(const page of all) {
    const path=page.slice(web.length).replaceAll('\\','/');
    if(path==='/phone/index.html')continue; // served with a real token above
    await open(home+path+(path.endsWith('/index.html')?'?mock':''));
    assert.deepEqual(await evaluate('violations'),[],path);
  }
  const {writeFileSync}=await import('node:fs');
  if(process.env.CSP_HEADERS_OUT)writeFileSync(process.env.CSP_HEADERS_OUT,JSON.stringify(policies,null,2));
  console.log(`CSP HTTP: ${all.length-1} static HTML routes + token phone + Lab, zero policy violations; desktop theme/design/lamp, dialog native/fallback, mobile viewport, off-screen worker stop/resume passed`);
} finally {
  socket?.close();browser?.kill();
  if(browser&&browser.exitCode===null)await new Promise(r=>browser.once('exit',r));
  server.stdin.end();if(server.exitCode===null)await new Promise(r=>server.once('exit',r));
  assert.equal(resolve(dir,'..'),resolve(tmpdir()));
  rmSync(dir,{recursive:true,force:true,maxRetries:5,retryDelay:200});
}
