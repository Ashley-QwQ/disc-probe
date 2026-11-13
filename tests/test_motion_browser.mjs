// Real home DOM/assets with a mock backend; no server, hardware or burn confirmation.
// WAAPI timelines are paused and scrubbed. Polling below is only for module/asset readiness.
import assert from 'node:assert/strict';
import {readFileSync, writeFileSync, mkdtempSync, mkdirSync, existsSync} from 'node:fs';
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
  if(window.scrub && [560,760,1300,1000,420,1900,600].includes(options?.duration)) {a.pause();a.currentTime=0;}
  flights.push({el:this,a,frames,options});return a;
};
window.finishFlights=()=>flights.filter(f=>f.a.playState!=='idle').forEach(f=>f.a.finish());
const nativeRAF=window.requestAnimationFrame.bind(window),nativeCancelRAF=window.cancelAnimationFrame.bind(window);
window.rafQueue=new Map();let rafId=0;
window.requestAnimationFrame=fn=>window.manualRAF?(rafQueue.set(--rafId,fn),rafId):nativeRAF(fn);
window.cancelAnimationFrame=id=>id<0?rafQueue.delete(id):nativeCancelRAF(id);
window.tickRAF=now=>{const jobs=[...rafQueue.values()];rafQueue.clear();jobs.forEach(fn=>fn(now));};
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
const screenshots=process.env.MOTION_SCREENSHOTS;
if(screenshots)mkdirSync(screenshots,{recursive:true});
async function screenshot(name) {
  if(!screenshots)return;
  const {data}=await cdp('Page.captureScreenshot',{format:'png'});
  writeFileSync(join(screenshots,name+'.png'),Buffer.from(data,'base64'));
}
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

  // 18: keep the previous page's words until the push/pan reaches its destination.
  const lobbyNext=await evaluate('return document.getElementById("next-text").textContent');
  await newWork(true);
  for (const t of [0,380,759]) {
    await evaluate(`flights.filter(f=>f.el.classList.contains('np')).forEach(f=>f.a.currentTime=${t});`);
    assert.equal(await evaluate('return document.getElementById("next-text").textContent'),lobbyNext,'18: lobby label until push arrives at '+t);
  }
  await evaluate('finishFlights();');await until('!document.getElementById("lobby").classList.contains("leaving")','18: pushed');
  const planNext=await evaluate('return document.getElementById("next-text").textContent');
  assert.notEqual(planNext,lobbyNext,'18: new work label changes at arrival');
  await evaluate(`document.querySelector('.np-batch').value='Label test';document.querySelector('.np-batch').dispatchEvent(new Event('input'));
    flights=[];document.querySelector('.np-cal-go').click();dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));`);
  await until('flights.some(f=>f.options.duration===760)','18: pan ready');
  await evaluate('flights.filter(f=>f.options.duration===760).forEach(f=>f.a.currentTime=379);');
  assert.equal(await evaluate('return document.getElementById("next-text").textContent'),planNext,'18: plan label halfway through pan');
  await evaluate('finishFlights();');await until('flights.some(f=>f.options.duration===1300)','18: calibration arrived');
  assert.notEqual(await evaluate('return document.getElementById("next-text").textContent'),planNext,'18: calibration label at arrival');

  // 19: actual mock-disc entry/drop uses only transform; the dormant gallery rule also excludes layout.
  await open();await calibrate();await evaluate('finishFlights();');
  await until('flights.some(f=>f.options.duration===1300)','19: calibration');await evaluate('finishFlights();');
  await evaluate(`window.flyer=document.querySelector('.flyer');`);
  await until('!!document.getElementById("removed")','19: mock foreign disc identified');
  await evaluate('document.getElementById("removed").click();');
  await until('flyer.classList.contains("on") && !flyer.classList.contains("up")','19: new disc entry');
  await until('flyer.classList.contains("on")','19: flyer entry');
  await check('!flyer.style.left && !flyer.style.top && flyer.style.transform.includes("translate(") && getComputedStyle(flyer).transitionProperty==="transform, opacity"','19: flyer translates rather than animating coordinates');
  await evaluate(`flyer.classList.add('drop');window.gallery=document.createElement('button');gallery.className='gallery';motionTest.api.cam.append(gallery);`);
  await check('getComputedStyle(flyer).transitionProperty==="transform" && getComputedStyle(gallery).transitionProperty==="transform, opacity"','19: drop and gallery transitions exclude left/top');

  // 20: both labels turn in opposite directions, keys crossfade, rapid retarget and motion-off clean up.
  await open();await newWork();
  await evaluate(`setMotion('on');flights=[];document.querySelector('.np-key[data-kind="cd"]').dispatchEvent(new MouseEvent('click',{bubbles:true}));`);
  await check('document.querySelectorAll(".np-face-text").length===2 && document.querySelectorAll(".np-ring2").length===2','20: outgoing label and keys retained');
  await evaluate(`window.dial=flights.filter(f=>[380,120].includes(f.options.duration));dial.forEach(f=>{f.a.pause();f.a.currentTime=f.options.duration/2;});`);
  await check('dial.length===4 && dial[0].frames[1].transform==="rotate(70deg)" && dial[1].frames[0].transform==="rotate(-70deg)" && dial.slice(2).every(f=>+getComputedStyle(f.el).opacity>.4 && +getComputedStyle(f.el).opacity<.6)','20: opposing turns and 120ms outer-key crossfade');
  await screenshot('dial-two-labels');
  await evaluate(`document.querySelector('.np-key[data-kind="bd"]').dispatchEvent(new MouseEvent('click',{bubbles:true}));`);
  await check('document.querySelectorAll(".np-face-text").length===2','20: retarget leaves only one outgoing copy');
  await evaluate('setMotion("off");');
  await check('document.querySelectorAll(".np-face-text").length===1 && document.querySelectorAll(".np-ring2").length===1 && flights.filter(f=>[380,120].includes(f.options.duration)).every(f=>f.a.playState==="idle")','20: off cancels dial motion and removes copies');
  await evaluate(`document.querySelector('.np-key[data-kind="dvd"]').dispatchEvent(new MouseEvent('click',{bubbles:true}));`);
  await check('document.querySelectorAll(".np-face-text").length===1 && flights.filter(f=>[380,120].includes(f.options.duration)).every(f=>f.a.playState==="idle")','20: off never creates dial motion');

  // 21,24: hold the first preview state request; design must stay opaque throughout readiness and fade-in.
  await evaluate('document.getElementById("next").click();');await until('document.documentElement.dataset.mode==="design"','21: design');
  await evaluate(`window.design=await import('./design.js');document.querySelector('.ws [data-a="sample"]').click();
    setMotion('on');window.testFetch=window.fetch;window.previewWait=null;
    window.fetch=(path,...args)=>String(path).startsWith('/api/state?')?new Promise(r=>previewWait=()=>r({ok:true,json:async()=>({})})):testFetch(path,...args);
    window.designSheet=document.querySelector('.ws:not(.pv)');getComputedStyle(designSheet).opacity;
    document.getElementById('next').click();`);
  await until('!!previewWait','21: first preview module loaded, state pending');
  await check('document.documentElement.dataset.mode==="design" && designSheet.classList.contains("on") && +getComputedStyle(designSheet).opacity===1','21: no empty page while loading');
  await evaluate('previewWait();');await until('document.documentElement.dataset.mode==="preview"','21: preview starts');
  await evaluate(`window.previewSheet=document.querySelector('.ws.pv');getComputedStyle(previewSheet).opacity;
    window.previewFade=previewSheet.getAnimations();previewFade.forEach(a=>a.pause());`);
  for (const t of [0,90,180,359]) {
    await evaluate(`previewFade.forEach(a=>a.currentTime=${t});`);
    await check('+getComputedStyle(designSheet).opacity===1 || +getComputedStyle(previewSheet).opacity===1','21: an opaque sheet backs preview at '+t+'ms');
  }
  await screenshot('preview-backed-by-design');
  await evaluate('previewFade.forEach(a=>a.finish());');await until('!designSheet.classList.contains("on")','21: design hides after preview arrives');
  await evaluate(`setMotion('off');document.getElementById('back').click();window.dot=document.querySelector('.ws:not(.pv) .dirty');dot.classList.remove('on');getComputedStyle(dot).opacity;dot.classList.add('on');`);
  await check('getComputedStyle(dot).transitionDuration==="0s" && +getComputedStyle(dot).opacity===1 && !dot.getAnimations().length','24: dirty dot instant with motion off');
  await evaluate('setMotion("on");');
  await check('getComputedStyle(dot).transitionDuration==="0.2s"','24: dot still fades with motion on');

  // 22: real stage with an entirely fake backend job, never a drive. Scrub its rAF load backwards on Back.
  for (const skip of [false,true]) {
    await open();await newWork();
    await evaluate(`motionTest.api.backend={...motionTest.api.backend,mock:false,
      job:async req=>{if(req.action!=='info')throw Error('Forbidden action '+req.action);return {disc:{present:true,media:'dvd',kind:'DVD-R',blank:false,sectors:2000000}};}};
      motionTest.api.selectedDrive=()=> 'FAKE';
      document.querySelector('.np-batch').value='Reverse load test';document.querySelector('.np-batch').dispatchEvent(new Event('input'));
      setMotion('on');flights=[];document.querySelector('.np-cal-go').click();dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));`);
    await until('flights.some(f=>f.options.duration===760)','22: live pan');await evaluate('finishFlights();');
    await until('flights.some(f=>f.options.duration===1300)','22: live card');await evaluate('finishFlights();');
    await until('!document.querySelector(".np").classList.contains("filing")','22: live settled');
    await evaluate('document.getElementById("next").click();');
    await until('!!document.querySelector("#measurement-confirm")','22: fake written-disc info returned');
    // Pose the final frame before beginning the reverse. All forward and reverse sprites are real assets.
    await evaluate(`window.load=await import('./loaddisc.js');setMotion('off');await load.desk(false);
      window.anchor=document.querySelector('.cs-art');await load.pose(anchor,1080);setMotion('on');
      window.manualRAF=true;window.startTray=document.querySelector('.ld-world .ld-g img[data-file="tray"]').parentElement.style.transform;
      window.spriteState=()=>[...document.querySelectorAll('.ld-world .ld-g')].map(e=>e.style.transform+'|'+e.style.opacity);
      window.endPose=spriteState();flights=[];esc();`);
    await until('rafQueue.size>0 && flights.some(f=>f.options.duration===1000)','22: reverse and card started');
    await evaluate('tickRAF(0);tickRAF(160);window.midReverse=spriteState();');
    await check('midReverse.some((v,i)=>v!==endPose[i]) && document.querySelector(".cal-stage").style.visibility==="hidden"','22: load actually reverses under the hidden stage');
    await check('[...motionTest.api.burnerLayer.querySelectorAll(".tray.full")].every(el=>getComputedStyle(el).visibility==="hidden")','22: library tray cannot show through the reverse scene');
    if (!skip) await screenshot('disc-load-reversed');
    if (skip) {
      await evaluate('document.body.click();');
      await until('document.documentElement.dataset.mode==="newplan" && !document.querySelector(".np").classList.contains("unfiling")','22: skip cancels disc, card and pan');
      await check('rafQueue.size===0 && document.querySelector(".ld").hidden && document.getElementById("cal").hidden','22: skip cleans reverse sprites and rAF');
    } else {
      await evaluate('tickRAF(1080);window.reverseStart=spriteState();');
      await evaluate('await load.pose(anchor,0);window.expectedStart=spriteState();');
      assert.deepEqual(await evaluate('return reverseStart'),await evaluate('return expectedStart'),'22: reverse lands on forward frame zero');
      await evaluate('finishFlights();');await until('flights.some(f=>f.options.duration===760)','22: return pan after reverse');
      await evaluate('finishFlights();');await until('document.documentElement.dataset.mode==="newplan"','22: reverse return');
      await evaluate('document.body.click();');
    }
    await evaluate('window.manualRAF=false;rafQueue.clear();');
  }

  // 23: resizing finishes push and archive clocks, in both directions, at the new layout.
  for (const reversing of [false,true]) {
    await open();await newWork(true);
    await evaluate('flights.forEach(f=>{f.a.pause();f.a.currentTime=f.options.duration/2;});');
    if (reversing) await evaluate('esc();');
    await cdp('Emulation.setDeviceMetricsOverride',{width:reversing?1440:1280,height:900,deviceScaleFactor:1,mobile:false});
    await until(reversing?'!document.documentElement.dataset.mode':'!document.getElementById("lobby").classList.contains("leaving")','23: push finishes on resize');
    await check('!document.querySelector(".np").getAnimations().length && !document.getElementById("lobby-art").getAnimations().length','23: no stale push keyframes');
  }
  await open();
  await evaluate(`window.pw=await import('./pastworks.js');window.resizeArchive=pw.createPastWorks(motionTest.api);setMotion('on');flights=[];window.resizedShow=resizeArchive.show();`);
  await until('resizeArchive.state.phase==="entering"','23: archive entering');
  await cdp('Emulation.setDeviceMetricsOverride',{width:1280,height:800,deviceScaleFactor:1,mobile:false});
  await until('resizeArchive.state.phase==="idle"','23: archive finishes on resize');
  await evaluate('resizeArchive.back();');
  await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await until('resizeArchive.state.phase==="closed"','23: archive reverse finishes on resize');
  await evaluate('resizeArchive.destroy();');
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

  // 9: Escape and the actual Back button cancel bagging; neither may advance to design/calibration.
  for(const calibration of [false,true]) for(const escape of [false,true]) {
    await open();await newWork();
    await evaluate(`setMotion('on');
      ${calibration ? `document.querySelector('.np-batch').value='Bag cancellation';document.querySelector('.np-batch').dispatchEvent(new Event('input'));document.querySelector('.np-cal-go').click();` : `document.getElementById('next').click();`}
      ${escape ? 'esc();' : 'document.getElementById("back").click();'}`);
    await check('document.documentElement.dataset.mode==="newplan" && !document.querySelector(".np").hidden && !document.querySelector(".np").classList.contains("filing") && !document.querySelector(".np").classList.contains("leaving")','9: Back undoes the bag and stays in new work');
    await evaluate('await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);');
    await check('document.documentElement.dataset.mode==="newplan" && document.getElementById("cal").hidden','9: cancelled continuation stays cancelled');
    // Prove the form accepts the next action after cancelling.
    await evaluate('setMotion("off");document.getElementById("next").click();');
    await until('document.documentElement.dataset.mode==="design"','9: cancelled form is usable');
  }

  // 10: independent source-art disc marker follows the actual lobby image, including hover lift.
  // At the push's last frame it must meet the incoming top-view disc, in centre and visible width.
  for(const [width,height] of [[1440,900],[1600,900],[390,844]]) {
    await cdp('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
    await open();
    await evaluate(`const img=document.querySelector('.lb-layer[data-name="newplan"] img');
      window.discMarker=document.createElement('i');Object.assign(discMarker.style,{position:'absolute',left:img.style.left,top:img.style.top,width:img.style.width,height:img.style.height,pointerEvents:'none'});img.after(discMarker);
      window.sourceDisc=()=>{const r=discMarker.getBoundingClientRect(),s=r.width/703;return {x:r.left+288*s,y:r.top+275*s,d:250*s};};`);
    await newWork(true);
    const alignment=await evaluate(`flights.filter(f=>f.el.id==='lobby-art').forEach(f=>{f.a.pause();f.a.currentTime=f.options.duration;});
      flights.filter(f=>f.el.classList.contains('np')).forEach(f=>{f.a.pause();f.a.currentTime=0;});
      const lobby=sourceDisc(),np=document.querySelector('.np'),s=Math.max(innerWidth,innerHeight*16/9)/2560;
      const x=(innerWidth-2560*s)/2+512*s,y=(innerHeight-1440*s)/2+720*s;
      const m=new DOMMatrix(getComputedStyle(np).transform),o=getComputedStyle(np).transformOrigin.split(' ').map(parseFloat);
      return {distance:Math.hypot(lobby.x-(o[0]+(x-o[0])*m.a+m.e),lobby.y-(o[1]+(y-o[1])*m.d+m.f)),ratio:lobby.d/(414.6*s*m.a)};`);
    assert.ok(alignment.distance<10 && Math.abs(alignment.ratio-1)<.05,'10: aligned disc at '+width+'x'+height+': '+JSON.stringify(alignment));
    await screenshot('drive-push-'+width);
    await evaluate('finishFlights();');
  }
  await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});

  // 11: idle preparation covers both pages, with no drive hover. A warm click starts in this turn.
  await open();
  await until('!!document.querySelector(".pw")','11: lobby idle preloads past works');
  await evaluate(`setMotion('on');flights=[];window.warmStart=motionTest.newplan.start(motionTest.api,{from:document.getElementById('lobby-new')});
    for(let i=0;i<12;i++)await Promise.resolve();window.warmPush=flights.some(f=>f.el.id==='lobby-art');`);
  await check('warmPush','11: prepared push starts without waiting for the 600ms fallback');
  await evaluate('await warmStart;finishFlights();');

  // 12: click/Enter skips each return leg, including extraction after the camera has arrived.
  for(const leg of ['card','pan','sheet']) {
    await open();await calibrate();await evaluate('finishFlights();');
    await until('flights.some(f=>f.options.duration===1300)','return setup cardOut');
    await evaluate('finishFlights();');
    await until('!document.querySelector(".np").classList.contains("filing")','calibration settled');
    await evaluate('flights=[];esc();');
    await until('flights.some(f=>f.options.duration===1000)','12: card return ready');
    if(leg!=='card') {
      await evaluate('finishFlights();');
      await until('flights.some(f=>f.options.duration===760)','12: camera return ready');
    }
    if(leg==='sheet') {
      await evaluate('finishFlights();');
      await until('document.documentElement.dataset.mode==="newplan"','12: extracting');
      await evaluate('document.querySelector(".np").getAnimations({subtree:true}).forEach(a=>{a.pause();a.currentTime=100;});');
    }
    await evaluate(leg==='pan' ? `dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));` : `document.body.click();`);
    await until('document.documentElement.dataset.mode==="newplan" && !document.querySelector(".np").classList.contains("unfiling")','12: skip reopens form at once');
    await check('document.getElementById("cal").hidden && !document.documentElement.classList.contains("cal-staged") && !document.querySelector(".np").classList.contains("filing") && !document.querySelector(".np").getAnimations({subtree:true}).length','12: all return legs and envelope parts cleaned');
  }

  // 13: the envelope leaves at 150 ms, before extraction has finished; no front crossing the cleared sheet.
  await open();await calibrate();await evaluate('finishFlights();');
  await until('flights.some(f=>f.options.duration===1300)','13: calibration card');
  await evaluate('finishFlights();');await until('!document.querySelector(".np").classList.contains("filing")','13: settled');
  await evaluate('flights=[];esc();');await until('flights.some(f=>f.options.duration===1000)','13: tuck');
  await evaluate('finishFlights();');await until('flights.some(f=>f.options.duration===760)','13: pan');
  await evaluate('finishFlights();');await until('document.documentElement.dataset.mode==="newplan"','13: extraction');
  await evaluate(`window.extraction=document.querySelector('.np').getAnimations({subtree:true});extraction.forEach(a=>a.pause());`);
  for(const t of [150,300,500,650,759]) {
    const clear=await evaluate(`extraction.forEach(a=>a.currentTime=${t});
      const np=document.querySelector('.np'),sheet=np.querySelector('.np-sheet').getBoundingClientRect(),front=np.querySelector('.np-env-front').getBoundingClientRect();
      const slot=front.top+front.height*(421.21/2494);return {cleared:sheet.bottom<=slot,frontBelow:front.top>sheet.bottom,delay:extraction.find(a=>a.effect.target.classList.contains('np-env-front'))?.effect.getTiming().delay};`);
    assert.equal(clear.delay,150,'13: envelope drops early');
    assert.ok(!clear.cleared||clear.frontBelow,'13: front cannot cover the cleared sheet at '+t+'ms');
    if(t===500)await screenshot('sheet-return-500');
  }
  await evaluate('document.body.click();');

  // 14: presets fly from the lobby tray; a mid-entry close reverses the same frames.
  await open();await until('!!document.querySelector(".presetio")','presets ready');
  await evaluate(`setMotion('on');flights=[];window.presets=await import('./presetio.js');
    presets.open(document.querySelector('.lb-hit[data-target="fax"]'));`);
  await check('flights.some(f=>f.el.id==="lobby-art" && f.options.duration===560) && flights.some(f=>f.el.classList.contains("presetio") && f.options.duration===760 && f.frames[0].transform.includes("scale(.18)"))','14: lobby push and tray entrance');
  await evaluate(`window.deskFlight=flights.filter(f=>f.el.id==='lobby-art'||f.el.classList.contains('presetio')||f.el.classList.contains('lobby-greet'));
    deskFlight.forEach(f=>{f.a.pause();f.a.currentTime=f.options.duration/2;});window.deskBefore=getComputedStyle(document.querySelector('.presetio')).transform;
    document.querySelector('.presetio [data-close]').click();window.deskAfter=getComputedStyle(document.querySelector('.presetio')).transform;
    await Promise.all(deskFlight.map(f=>f.a.ready));deskFlight.forEach(f=>f.a.pause());`);
  await check('deskBefore===deskAfter && deskFlight.every(f=>f.a.playbackRate===-1)','14: mid-entry close reverses without a snap');
  await screenshot('presets-mid-reversal');
  await evaluate('finishFlights();');await until('document.querySelector(".presetio").hidden','14: close restores lobby');
  await evaluate(`flights=[];presets.open();finishFlights();`);
  await until('!document.getElementById("lobby").classList.contains("leaving")','14: full entrance complete');
  await evaluate('flights=[];document.querySelector(".presetio [data-close]").click();');
  await check('flights.some(f=>f.el.classList.contains("presetio")&&f.frames.at(-1).transform.includes("scale(.18)"))','14: settled desk reverses toward tray');
  await evaluate('finishFlights();');await until('document.querySelector(".presetio").hidden','14: ordinary close');
  await evaluate('setMotion("off");flights=[];presets.open();document.querySelector(".presetio [data-close]").click();');
  await check('document.querySelector(".presetio").hidden && !flights.length && !document.documentElement.dataset.mode','14: motion off cuts to clean end states');

  // 16: every moving layer (including the knob, shadow and content) holds its displayed frame on retarget.
  await evaluate(`presets.open();setMotion('on');document.querySelector('.presetio [data-move="-1"]').click();
    const sheet=document.querySelector('.presetio');window.lever=sheet.getAnimations({subtree:true});lever.forEach(a=>{a.pause();a.currentTime=300;});
    window.leverBefore=lever.map(a=>({el:a.effect.target,transform:getComputedStyle(a.effect.target).transform,opacity:getComputedStyle(a.effect.target).opacity}));
    document.querySelector('.presetio [data-move="1"]').click();
    window.leverHeld=leverBefore.every(s=>s.transform===getComputedStyle(s.el).transform && s.opacity===getComputedStyle(s.el).opacity);
    sheet.getAnimations({subtree:true}).forEach(a=>{a.pause();a.currentTime=0;});`);
  await check('leverHeld && lever.every(a=>a.playState==="idle")','16: second lever move starts from displayed transforms and opacity');
  await evaluate('document.querySelector(".presetio").getAnimations({subtree:true}).forEach(a=>a.finish());setMotion("off");document.querySelector(".presetio [data-close]").click();');

  // 15,17: the lobby push runs on WAAPI at 4.5x; off never waits for the slow works list.
  await open();
  await evaluate(`window.pw=await import('./pastworks.js');await pw.prepare(motionTest.api);
    window.slowList=null;window.archive=pw.createPastWorks(motionTest.api,{works:{list:()=>new Promise(r=>slowList=r)}});
    window.loadStarted=performance.now();await archive.show();window.loadElapsed=performance.now()-loadStarted;`);
  await check('loadElapsed<300 && document.documentElement.dataset.mode==="pastworks" && archive.state.phase==="idle"','17: motion off opens within 300ms despite pending list');
  await evaluate('slowList([]);archive.back();setMotion("on");flights=[];window.showArchive=archive.show();');
  await until('flights.some(f=>f.el.id==="lobby-art" && f.options.duration===600)','15: composited archive push');
  await evaluate(`window.archivePush=flights.find(f=>f.el.id==='lobby-art');archivePush.a.pause();archivePush.a.currentTime=120;
    window.archiveScale=new DOMMatrix(getComputedStyle(archivePush.el).transform).a;`);
  await check('archiveScale<=4.5 && archiveScale>=4 && document.getElementById("lobby-art").style.willChange==="transform" && !archive.page.style.getPropertyValue("--pw-lift") && !archive.page.style.getPropertyValue("--pw-hole")','15: bounded push with direct layer opacity');
  await evaluate('archive.skip();archive.back();archive.skip();archive.destroy();');
  await check('!document.getElementById("lobby-art").style.willChange && !document.querySelector(".pw-box-shade") && errors.length===0','15: promotion and shade cleaned after exit');

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
  console.log('PASS: motion audit 1–24, paused/scrubbed WAAPI and rAF, labels, transform flights, dial, preview readiness, reverse load, resize, motion-off and prior interruption regressions');
} finally {
  if(socket?.readyState===WebSocket.OPEN){await cdp('Browser.close').catch(()=>{});socket.close();}
  if(browser?.exitCode===null){await Promise.race([new Promise(r=>browser.once('close',r)),pause(2000)]);if(browser.exitCode===null)browser.kill();}
  await rm(dir,{recursive:true,force:true,maxRetries:8,retryDelay:250});
}
