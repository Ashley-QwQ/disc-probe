// Real home DOM/assets with a mock backend; no server, hardware or burn confirmation.
// WAAPI timelines are paused and scrubbed. Polling below is only for module/asset readiness.
import assert from 'node:assert/strict';
import {readFileSync, writeFileSync, mkdtempSync, existsSync} from 'node:fs';
import {rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {spawn} from 'node:child_process';

const home = new URL('../discprobe/web/home/', import.meta.url);
const source = readFileSync(new URL('index.html', home), 'utf8');
const manifest = JSON.parse(readFileSync(new URL('../gui.json', home), 'utf8'));
const edge = process.env.KIT_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
assert.ok(existsSync(edge), 'Set KIT_TEST_BROWSER to Chromium');
const dir = mkdtempSync(join(tmpdir(), 'discprobe-motion-'));
const fixture = join(dir, 'motion.html');
const bootstrap = `<base href="${home}"><script>
localStorage.setItem('dp-motion','off');localStorage.setItem('dp-sound','off');
window.errors=[];window.calls=[];window.flights=[];
addEventListener('error',e=>errors.push(e.message));addEventListener('unhandledrejection',e=>errors.push(String(e.reason)));
const nativeFetch=window.fetch.bind(window);
window.fetch=async(path,opts)=>{
  const url=new URL(path,document.baseURI);
  if(url.pathname.includes('/api/')) {
    calls.push({path:String(path),method:opts?.method||'GET'});
    if(String(path)==='/api/presets'&&!opts?.body)return {ok:true,json:async()=>({version:1,presets:[]})};
    throw Error('Unexpected backend call: '+path);
  }
  if(url.protocol!=='file:')throw Error('Unexpected network: '+url);
  return nativeFetch(path,opts);
};
window.EventSource=class {addEventListener(){} close(){}};
window.testHandshake=async path=>({ok:true,json:async()=>path==='/gui.json'?${JSON.stringify(manifest)}:
  {api_version:'1.0',capabilities:${JSON.stringify([...manifest.required_capabilities,...manifest.optional_capabilities])}}});
const animate=Element.prototype.animate;
Element.prototype.animate=function(frames,options){
  const a=animate.call(this,frames,options);
  if(window.scrub && [560,760,1300,1000,420].includes(options?.duration)) {a.pause();a.currentTime=0;}
  flights.push({el:this,a,frames,options});return a;
};
window.finishFlights=()=>flights.filter(f=>f.a.playState!=='idle').forEach(f=>f.a.finish());
window.setMotion=value=>document.querySelector('[data-motion="'+value+'"]').click();
window.esc=()=>{document.activeElement?.blur();dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));};
</script>`;
let html = source.replace('<head>', '<head>'+bootstrap)
  .replace('await handshake();','await handshake(document,window.testHandshake,{protocol:"http:",search:""});');
const tail = html.lastIndexOf('</script>');
html = html.slice(0,tail)+'\nwindow.motionTest={api,newplan:await import("./newplan.js")};\n'+html.slice(tail);
writeFileSync(fixture, html);
const pause = ms=>new Promise(r=>setTimeout(r,ms));
let browser, socket, seq=0;
const pending=new Map();
async function cdp(method,params={}) {
  const id=++seq;
  const result=new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},15000);
    pending.set(id,{resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});
  });
  socket.send(JSON.stringify({id,method,params}));return result;
}
async function evaluate(code) {
  const r=await cdp('Runtime.evaluate',{expression:`(async()=>{${code}})()`,awaitPromise:true,returnByValue:true});
  assert.ok(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;
}
const check=async(expr,message)=>assert.ok(await evaluate('return '+expr),message);
async function until(expr,message) {
  for(let i=0;i<200;i++){if(await evaluate('return '+expr))return;await pause(25);}
  assert.fail(message+': '+await evaluate('return JSON.stringify({errors,mode:document.documentElement.dataset.mode,flights:flights.map(f=>[f.el.id||f.el.className,f.options.duration,f.a.playState])})'));
}
async function open() {
  await cdp('Page.navigate',{url:pathToFileURL(fixture).href+'?mock'});
  await until('!!window.motionTest','fixture ready');
  await evaluate('await motionTest.newplan.prepare(motionTest.api);window.scrub=true;window.flights=[];');
}
async function newWork(fly=false) {
  await evaluate(`setMotion('${fly?'on':'off'}');await motionTest.newplan.start(motionTest.api,${fly?'{from:document.getElementById("lobby-new")}':'{}'});`);
}
async function calibrate() {
  await newWork();
  await evaluate(`document.querySelector('.np-batch').value='Motion test DVD-R';
    document.querySelector('.np-batch').dispatchEvent(new Event('input'));
    setMotion('on');flights=[];document.querySelector('.np-cal-go').click();
    dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));`);
  await until('flights.some(f=>f.el.classList.contains("np")&&f.options.duration===760)','pan ready');
}
try {
  browser=spawn(edge,['--headless=new','--disable-gpu','--disable-background-networking','--no-sandbox','--no-first-run','--no-default-browser-check',
    '--allow-file-access-from-files','--remote-debugging-port=0',`--user-data-dir=${join(dir,'profile')}`,'about:blank'],{windowsHide:true,stdio:'ignore'});
  let port;
  for(let i=0;i<100&&!port;i++) {
    try {port=readFileSync(join(dir,'profile','DevToolsActivePort'),'utf8').split(/\r?\n/)[0];}
    catch(e){if(!['ENOENT','EBUSY','EPERM','EACCES'].includes(e.code))throw e;}
    if(!port)await pause(100);
  }
  assert.ok(port,'CDP ready');
  assert.ok(![8772,8795,8798,8812,8813,8841,8863].includes(+port));
  const targets=await fetch(`http://127.0.0.1:${port}/json/list`).then(r=>r.json());
  socket=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  socket.onmessage=({data})=>{const m=JSON.parse(data),p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}};
  await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await cdp('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  await open();

  // 2, 7: halfway opacity and exact-frame reversal; the second Esc cannot add or restart anything.
  await newWork(true);
  await evaluate(`window.push=flights.filter(f=>f.el.id==='lobby-art'||f.el.classList.contains('lobby-greet')||f.el.classList.contains('np'));
    push.forEach(f=>{f.a.pause();f.a.currentTime=f.options.duration/2;});
    window.before={transform:getComputedStyle(document.querySelector('.np')).transform,opacity:getComputedStyle(document.querySelector('.np')).opacity,
      origin:document.getElementById('lobby-art').style.transformOrigin,count:flights.length};`);
  await check('+before.opacity>.3 && +before.opacity<.9','7: opacity halfway through push has a real fade');
  await evaluate('esc();esc();window.afterPush={transform:getComputedStyle(document.querySelector(".np")).transform,opacity:getComputedStyle(document.querySelector(".np")).opacity};await Promise.all(push.map(f=>f.a.ready));push.forEach(f=>f.a.pause());');
  assert.deepEqual(await evaluate(`return {count:flights.length,rates:push.map(f=>f.a.playbackRate),
    transform:afterPush.transform,opacity:afterPush.opacity,
    origin:document.getElementById('lobby-art').style.transformOrigin}`),
    await evaluate('return {...before,rates:push.map(()=>-1)}'),'2: one reversal from the current frame and original origin');
  await evaluate('finishFlights();');
  await until('!document.documentElement.dataset.mode && document.querySelector(".np").hidden','reverse reaches lobby');
  await newWork(true);await evaluate('finishFlights();');
  await until('!document.getElementById("lobby").classList.contains("leaving")','push complete');
  await evaluate('flights=[];esc();flights.filter(f=>f.el.classList.contains("np")).forEach(f=>{f.a.pause();f.a.currentTime=260;});');
  await check('+getComputedStyle(document.querySelector(".np")).opacity>.3 && +getComputedStyle(document.querySelector(".np")).opacity<.9','7: ordinary pull-back fade spans more than the final frames');
  await evaluate('finishFlights();');await until('!document.documentElement.dataset.mode','ordinary pull-back complete');

  // 1: Back owns the running pan; all later card/ruler steps must stay cancelled.
  for (const key of ['button','escape']) {
    await open();await calibrate();
    await evaluate(`window.pan=flights.filter(f=>f.options.duration===760);pan.forEach(f=>{f.a.pause();f.a.currentTime=380;});
      window.panBefore=pan.map(f=>getComputedStyle(f.el).transform+'|'+getComputedStyle(f.el).translate);
      ${key==='button'?'document.getElementById("back").click();':'esc();'}window.panAfter=pan.map(f=>getComputedStyle(f.el).transform+'|'+getComputedStyle(f.el).translate);await Promise.all(pan.map(f=>f.a.ready));pan.forEach(f=>f.a.pause());`);
    assert.deepEqual(await evaluate('return pan.map((f,i)=>({rate:f.a.playbackRate,before:panBefore[i],after:panAfter[i]}))'),
      await evaluate('return pan.map((f,i)=>({rate:-1,before:panBefore[i],after:panBefore[i]}))'),'1: pan reverses without a jump via '+key);
    await evaluate('finishFlights();');
    await until('document.documentElement.dataset.mode==="newplan"','pan returns to form');
    await check('document.getElementById("cal").hidden && !document.documentElement.classList.contains("cal-staged") && !document.documentElement.classList.contains("pan-in") && !flights.some(f=>f.options.duration===1300)','1: no stale calibration/card/ruler after '+key);
  }

  // 6: reverse the existing cardOut, never build a second envelope or additive card animation.
  await open();await calibrate();await evaluate('finishFlights();');
  await until('flights.some(f=>f.options.duration===1300)','cardOut ready');
  await evaluate(`window.card=flights.filter(f=>f.options.duration===1300);card.forEach(f=>{f.a.pause();f.a.currentTime=600;});
    window.parts=card.filter(f=>f.el.id!=='cal').map(f=>f.el);window.cardCount=flights.length;esc();esc();await Promise.all(card.map(f=>f.a.ready));card.forEach(f=>f.a.pause());`);
  assert.deepEqual(await evaluate('return {count:flights.filter(f=>[1000,1300].includes(f.options.duration)).length,parts:parts.map(p=>p.isConnected),rates:card.map(f=>f.a.playbackRate)}'),
    {count:3,parts:[true,true],rates:[-1,-1,-1]},'6: same single envelope reverses during extraction');
  await evaluate('finishFlights();');
  await until('flights.filter(f=>f.options.duration===760).length>3','return pan ready');
  await evaluate('finishFlights();');await until('document.documentElement.dataset.mode==="newplan"','card return complete');
  await check('parts.every(p=>!p.isConnected) && document.getElementById("cal").hidden','6: reversed envelope cleaned up');

  // 3, 4: force system reduce while the explicit site setting wins in JS and CSS.
  await open();
  await evaluate(`setMotion('on');document.documentElement.dataset.theme='dark';
    const {flipNumber}=await import('./kit/flipnum.js');const el=document.createElement('span');el.id='test-flip';el.textContent='12';document.body.append(el);
    window.flip=flipNumber(el);flip.set('13');el.getAnimations({subtree:true}).forEach(a=>{a.pause();a.currentTime=120;});
    const link=document.createElement('link');link.rel='stylesheet';link.href=new URL('./photocal.css',document.baseURI);document.head.append(link);await new Promise(r=>link.onload=r);
    window.pc=document.createElement('div');pc.className='pc-page';pc.innerHTML='<span style="transition:opacity 1s linear">photo</span>';document.body.append(pc);
    const ring=document.createElement('div');ring.className='kit-ring-button';ring.dataset.kitProgress='indeterminate';ring.innerHTML='<span class="kit-ring-meter"></span>';document.body.append(ring);
    const knob=document.createElement('div');knob.className='kit-slide-knob';knob.style.transition='transform 1s linear';document.body.append(knob);
    const style=document.createElement('style');style.textContent='.pc-page span::before{content:"photo";transition:opacity 1s linear}';document.head.append(style);`);
  await check('matchMedia("(prefers-reduced-motion: reduce)").matches && document.querySelector("#test-flip .kit-flip-previous") && getComputedStyle(document.querySelector(".kit-ring-meter")).animationName==="kit-turn" && getComputedStyle(document.querySelector(".kit-slide-knob")).transitionDuration==="1s" && getComputedStyle(pc.firstChild).transitionDuration==="1s" && getComputedStyle(pc.firstChild,"::before").transitionDuration==="1s"','3: forced on still rolls numbers and animates kit/photo under system reduce');
  await evaluate('setMotion("off");flip.set("14");');
  await check('!document.querySelector("#test-flip .kit-flip-previous") && getComputedStyle(document.querySelector(".kit-ring-meter")).animationName==="none"','3: explicit off has immediate end states');
  await evaluate('delete document.documentElement.dataset.motion;');
  await check('getComputedStyle(document.querySelector(".kit-ring-meter")).animationName==="none" && getComputedStyle(document.querySelector(".kit-slide-knob")).transitionDuration==="0s" && getComputedStyle(pc.firstChild).transitionDuration==="0s" && getComputedStyle(pc.firstChild,"::before").transitionDuration==="0s"','3: standalone CSS falls back to system reduce');
  await evaluate('document.getElementById("lobby").classList.add("pw-box-flight");');
  await check('getComputedStyle(document.getElementById("lobby"),"::after").backgroundColor==="rgb(0, 0, 0)"','4: shade stays black in dark theme');

  // 5: incoming design may start at zero opacity; the old desk remains until it is fully in.
  await open();await newWork();
  await evaluate(`setMotion('on');flights=[];document.getElementById('next').click();
    dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));`);
  await until('flights.some(f=>f.el.classList.contains("ws")&&f.options.duration===420)','design entrance ready');
  for(const t of [0,105,210,419]) {
    await evaluate(`flights.filter(f=>f.el.classList.contains('ws')).forEach(f=>{f.a.pause();f.a.currentTime=${t};});`);
    await check('!document.querySelector(".np").hidden && +getComputedStyle(document.querySelector(".np")).opacity===1 && document.querySelector(".np").classList.contains("leaving")','5: desk remains under design at '+t+'ms, bag stays dropped');
  }
  await evaluate('finishFlights();');await until('document.querySelector(".np").hidden','desk hides after entrance');
  await check('+getComputedStyle(document.querySelector(".ws")).opacity===1 && document.documentElement.dataset.mode==="design"','5: design visible when desk hides');

  // 8: actual setTray implementation with a non-mock backend, plus the real burn-page arrival.
  // It has no hardware API. Any unexpected backend request above fails the test.
  const setTraySource=source.slice(source.indexOf('  function setTray('),source.indexOf('  // ---- Settings:'));
  await open();
  await evaluate(`setMotion('off');
    window.visualTray=new Function('backend','burnerLayer',${JSON.stringify('let trayOpen=false,trayDisc=true,trayTimer=0;const reduce=true;'+setTraySource+';return {setTray,read:()=>trayOpen};')})({mock:false},motionTest.api.burnerLayer);
    const api=Object.create(motionTest.api);api.backend={mock:false};api.setTray=visualTray.setTray;
    window.burn=await import('./burn.js');burn.start(api,{media:'dvd',item:{name:'Test'},iso:{path:'mock.iso',bytes:32768,sectors:16},drive:{id:'FAKE',speeds:[4,8]}});`);
  await until('visualTray.read() && motionTest.api.burnerLayer.classList.contains("open")','8: pictured tray opens for non-mock backend');
  await check('calls.every(c=>c.path==="/api/presets" && c.method==="GET") && errors.length===0','8: no drive calls or browser errors');
  console.log('PASS: motion audit 1–8, paused/scrubbed WAAPI, Back/Esc, forced motion and visual-only tray');
} finally {
  if(socket?.readyState===WebSocket.OPEN){await cdp('Browser.close').catch(()=>{});socket.close();}
  if(browser?.exitCode===null){await Promise.race([new Promise(r=>browser.once('close',r)),pause(2000)]);if(browser.exitCode===null)browser.kill();}
  await rm(dir,{recursive:true,force:true,maxRetries:8,retryDelay:250});
}
