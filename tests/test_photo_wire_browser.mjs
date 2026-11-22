// Optional real-browser integration: intercepted fixtures, never the drive backend or a running server.
// Uses Node's built-in WebSocket/CDP, so the site keeps its zero-npm-dependency setup.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {existsSync,readFileSync} from 'node:fs';
import {mkdtemp,readFile,rm,writeFile} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {join,resolve,dirname,extname} from 'node:path';
import {tmpdir} from 'node:os';
import {once} from 'node:events';

const edge=process.env.PHOTO_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const testRoot=tmpdir();
const home=new URL('../discprobe/web/home/',import.meta.url);
const alignmentFixture=process.env.PHOTO_ALIGN_FIXTURE ? JSON.parse(readFileSync(process.env.PHOTO_ALIGN_FIXTURE,'utf8')) : null;
const calibrate=readFileSync(new URL('calibrate.js',home),'utf8');
const index=readFileSync(new URL('index.html',home),'utf8');
const html=`<!doctype html><html data-mode="cal" data-motion="off" class="cal-staged"><head><meta charset="utf-8"><base href="http://photo.test/">
<link rel="stylesheet" href="/kit/kit.css"><style>${index.match(/<style>([\s\S]*?)<\/style>/)[1]}</style><link rel="stylesheet" href="/photocal.css"></head>
<body><div class="top"><button id="back">Back</button></div><main id="cal" class="cal"></main>
<div class="bar"><div id="job" hidden><span id="job-name"></span><span id="job-time"></span><button id="job-cancel" type="button"></button></div><button id="next" class="next"><span id="next-text"></span></button></div>
<script type="module">
import {wire} from '/wire.js';
window.wire=wire; window.ready=true;
</script></body></html>`;
const moduleSource=`import {nextConfirm} from '/kit/nextconfirm.js';
import {expandBurnStop,closeBurnStop,paintStopButton,shortDiscWords,interruptedBurn} from '/burn-stop.js';
import {checkBurn,confirmBurn,checkingText,discText,failureText,keepDiscForReview,measurementGateText,recheckText} from '/burn-preflight.js';
import {ringButton} from '/kit/ringbutton.js';
import {flipNumber,flipValue} from '/kit/flipnum.js';
import {countdown,countdownText} from '/kit/countdown.mjs';
import {photoPage} from '/photocal.js';
import {curveEditor} from '/curve-edit.js';
import {adviceHTML,budgetHTML,cdPhoto,measurementRecovery,recoveryKind,recoveryAction,recoveryCommands,remeasure,stopReason,photoSaveWords} from '/guidance.mjs';
import {photoReasonWords,adoptionWords,applicationWords,sliderWords,seconds as photoSeconds} from '/photowords.mjs';
const hasCapability=()=>!!window.alignmentEnabled;
let clockNow=Date.now(); Date.now=()=>clockNow;
const realTimeout=window.setTimeout.bind(window);
window.setTimeout=(fn,ms,...args)=>{if(ms===25000){window.helpTimer=fn;window.helpBorn=Date.now();}return realTimeout(fn,ms,...args);};
const loadDisc={desk(){}}; const calchart={resultChart:()=>''}; const sfx={done(){},problem(){},failure(){}};
const floorLog=()=>({mount(){},start(){},end(){},title(){},progress(){},log(){}});
${calibrate.replace(/^import .*;.*$/gm,'')}
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function alignmentRequest(path,payload) {
  const res=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const result=await res.json();
  if(!res.ok)throw new Error(result.error);
  return result;
}
const fakeApi={lang:()=>window.lang||'zh',selectedDrive:()=>null,burnerLayer:document.body,nextWhy(){},jobProgress(){},backend:{mock:false,escapeHTML:esc,errorText:e=>e.message,
request:async(path,payload)=>{window.requests.push({path,payload}); if(window.missing&&path.includes(window.missing))throw Object.assign(new Error('Not found'),{status:404}); if(path.startsWith('/api/phone-link')){const address=new URL(path,location.href).searchParams.get('address')||'10.0.0.2';return {url:window.phone||null,qr_svg:'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"/>',addresses:['10.0.0.2','192.168.1.2'],address};}if(path==='/api/photo-alignment')return alignmentRequest(path,payload);if(path.startsWith('/api/photos'))return {photos:window.photos};if(path.endsWith('/disconnect')){window.devices=[];window.phone='http://lan/phone/new-token';return {disconnected:true};}if(path.startsWith('/api/phone-devices'))return {devices:window.devices||[]};return {};},
job:async(payload)=>{window.jobs.push(payload);if(payload.action!=='disexport')return window.photoResult;return window.alignmentEnabled?alignmentRequest('/align-preset',payload):{path:'presets/photo.json',photo_shift:{written:true,frames:2.5}};},state:async()=>({catalogue:{[flow.detected.media]:[{id:'saved',geo:flow.geo.path,name:'MID'}]}})}};
export const wire={
init({media='dvd',verdict='narrow_span',missing='',lang='zh',phone=null}={}){closePhoto();window.requests=[];window.jobs=[];window.photos=[];window.devices=[];window.photoResult={verdict:'unsure',per_photo:[]};window.missing=missing;window.lang=lang;window.phone=phone;api=fakeApi;$=id=>document.getElementById(id);flow={realPhase:'review',geo:{path:'results/run-one',verdict,measurement:{span_mm:[28,48]}},timing:{verdict:'good'},detected:{media,kind:media,mid:'MID',capacity_sectors:300000},item:{row:media},preset:'presets/existing.json',warnEl:document.createElement('div')};discWentIn=true;st={show(on){document.body.dataset.stage=on;},set(){},time(){}};document.getElementById('back').onclick=back;document.getElementById('next').onclick=()=>realNext();paint();},
phase(name,fraction=null){closePhoto();flow.realPhase=name;flow.iso='iso/test.iso';flow.burnInspection={disc:{present:true,blank:true,kind:'DVD-R'}};flow.job=name==='random'?{kind:'random',fraction}:null;paint();},enter:enterPhoto,next:realNext,back,state:()=>flow,page:()=>photoUI?.page,ui:()=>photoUI,
photo:(id='p1')=>({id,name:id+'.svg',url:'/disc.svg'}),
helpAfter(ms){clockNow=window.helpBorn+ms;window.helpTimer();},
};`;

test('photo flow in Chromium: paper, keys, polling, verdicts, upload and fallback', {skip:!existsSync(edge),timeout:60000}, async()=>{
  const dir=await mkdtemp(join(testRoot,'.photo-wire-browser-'));
  let browser, ws;
  let upload;
  try{
    browser=spawn(edge,['--headless=new','--mute-audio','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${dir}`,'about:blank'],{stdio:'ignore',windowsHide:true});
    browser.on('error',()=>{});
    let port;
    for(let i=0;i<100;i++){try{port=(await readFile(join(dir,'DevToolsActivePort'),'utf8')).split('\n')[0];break;}catch{await new Promise(r=>setTimeout(r,100));}}
    assert.ok(port,'Headless browser did not start');
    const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`,{signal:AbortSignal.timeout(5000)})).json();
    const target=pages.find(p=>p.type==='page' && p.url==='about:blank');assert.ok(target,'No fixture tab');
    ws=new WebSocket(target.webSocketDebuggerUrl);await once(ws,'open');
    let seq=0;const pending=new Map(),exceptions=[];
    let paused;
    const intercepts=new Set(),interceptErrors=[];
    ws.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.method==='Fetch.requestPaused'){const task=Promise.resolve().then(()=>paused?.(m.params)).catch(error=>interceptErrors.push(error)).finally(()=>intercepts.delete(task));intercepts.add(task);}if(m.method==='Runtime.exceptionThrown')exceptions.push(m.params.exceptionDetails);if(m.id){pending.get(m.id)?.(m);pending.delete(m.id);}});
    const send=(method,params={})=>new Promise((ok,fail)=>{const id=++seq,timer=setTimeout(()=>{pending.delete(id);fail(new Error('CDP timeout: '+method));},5000);pending.set(id,m=>{clearTimeout(timer);m.error?fail(new Error(JSON.stringify(m.error))):ok(m.result);});ws.send(JSON.stringify({id,method,params}));});
    const run=async code=>{
      const r=await send('Runtime.evaluate',{expression:`(async()=>{${code}})()`,awaitPromise:true,returnByValue:true});
      if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception.description);return r.result.value;
    };
    const waitFor=async(code,tries=100)=>{for(let i=0;i<tries;i++){if(await run(`return !!(${code});`))return;await new Promise(r=>setTimeout(r,30));}throw new Error('Timeout: '+code+' '+JSON.stringify(exceptions));};
    await send('Runtime.enable');
    await send('Page.enable');
    await send('Page.stopLoading');
    let manualDecision;
    paused=async({requestId,request})=>{
      const path=new URL(request.url).pathname;let body,type='text/plain',status=200;
      if(path==='/'){body=html;type='text/html';}
      else if(path==='/phone/fixture'){body=readFileSync(new URL('../discprobe/web/phone/index.html',import.meta.url),'utf8').replace('__PHOTO_CONFIG__',JSON.stringify({run:'run-one',token:'fixture-token'}));type='text/html';}
      else if(path==='/home/guidance.mjs'||path==='/home/photowords.mjs'){body=await readFile(new URL(path.slice(6),home));type='text/javascript';}
      else if(path==='/api/photos'&&request.method==='GET'){type='application/json';body=JSON.stringify({verdict:'unsure',photos:[{id:'mine',name:'相片-'+ 'long-name-'.repeat(20)+'.jpg',url:'/disc.svg',verdict:'unsure',status:'no_rim'}]});}
      else if(path==='/wire.js'){body=moduleSource;type='text/javascript';}
      else if(path==='/disc.svg'){type='image/svg+xml';body='<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600"><rect width="600" height="600" fill="#555"/><circle cx="300" cy="300" r="255" fill="#aaa" stroke="#222"/><circle cx="300" cy="300" r="32" fill="#555"/></svg>';}
      else if(path==='/api/photo-alignment'){
        const payload=JSON.parse(request.postData), weak=Math.abs(payload.L_mm+2.2)>.3;
        type='application/json';
        if(alignmentFixture){
          const res=await fetch(alignmentFixture.origin+path,{method:'POST',headers:{'Content-Type':type},body:request.postData});
          status=res.status;body=await res.text();
        }else{
          body=JSON.stringify(payload.action==='prepare'
            ? {token:'registered',H:[[4,0,300],[0,4,300],[.002,0,1]],width:600,height:600,bands:[[28,36,[0,1,2,3,4,5]],[40,55,[0,1,2,3,4,5]]],rings:[27,39,56.5],L_mm:-2.2,c_deg:34.4,range_mm:{min:-10,max:10,step:.025}}
            : payload.action==='score' ? {agreeing:weak?0:6,cells:66,weak}
              : {written:true,L_mm:payload.L_mm,origin:'manual-slider'});
        }
        if(payload.action==='save'&&status===200)manualDecision=JSON.parse(body);
      }
      else if(path==='/align-preset'){
        type='application/json';
        if(alignmentFixture){
          const res=await fetch(alignmentFixture.origin+'/api/run',{method:'POST',headers:{'Content-Type':type},body:request.postData});
          const start=await res.json();
          if(!res.ok){status=res.status;body=JSON.stringify(start);}
          else {
            for(let i=0;i<100;i++){
              const job=await(await fetch(alignmentFixture.origin+'/api/jobs/'+start.job)).json();
              if(job.exit!==null){status=job.exit===0?200:422;body=JSON.stringify(job.result??{error:JSON.stringify(job)});break;}
              await new Promise(r=>setTimeout(r,50));
            }
          }
        }else body=JSON.stringify({path:'presets/manual.json',photo_shift:manualDecision});
      }
      else if(alignmentFixture&&alignmentFixture.rows.some(row=>row.url===path)){
        const res=await fetch(alignmentFixture.origin+path);
        status=res.status;type=res.headers.get('content-type');body=Buffer.from(await res.arrayBuffer());
      }
      else if(path==='/api/photos'&&request.method==='POST'){
        const headers=Object.fromEntries(Object.entries(request.headers).map(([k,v])=>[k.toLowerCase(),v]));upload={filename:headers['x-filename'],token:headers['x-discprobe-token']};
        type='application/json';body=JSON.stringify({id:'uploaded',name:'上传.png',url:'/disc.svg'});
      }else{try{const target=new URL('.'+path,home);if(!target.href.startsWith(home.href))throw new Error('outside');body=await readFile(target);type=extname(path)==='.css'?'text/css':/\.(js|mjs)$/.test(path)?'text/javascript':'application/octet-stream';}catch{status=404;body='Not found';}}
      await send('Fetch.fulfillRequest',{requestId,responseCode:status,responseHeaders:[{name:'Content-Type',value:type},{name:'Access-Control-Allow-Origin',value:'*'}],body:Buffer.from(body).toString('base64')});
    };
    await send('Fetch.enable',{patterns:[{urlPattern:'http://photo.test/*'}]});
    await send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
    const nav=await send('Page.navigate',{url:'http://photo.test/?token=session-test'});assert.equal(nav.errorText,undefined,JSON.stringify(nav));
    await waitFor('window.ready').catch(async e=>{throw new Error(e.message+' '+await run(`return document.body.innerText.slice(0,500)+' '+location.href;`));});
    await run(`wire.init();document.querySelector('#real-photo').click();`);await waitFor("wire.ui()?.status==='ready'");
    assert.equal(await run(`return document.querySelector('#cal .pc-paper')!==null && document.querySelector('.cal-photo-host .pc-viewport')!==null;`),true);
    assert.equal(await run(`return document.querySelector('#cal-ruler [aria-current]').textContent.includes('拍照');`),true);
    assert.equal(await run(`return document.querySelector('[data-pc="auto"]')!==null;`),true);
    assert.equal(await run(`return document.querySelector('.pc-phone-block')===null;`),true,'No LAN link means no phone block');
    await run(`window.photos=[wire.photo()];`);await waitFor("wire.page()?.state().photos.length===1");
    assert.equal(await run(`return document.querySelector('.pc-manual').open;`),false,'manual editor is folded');
    await run(`document.querySelector('.pc-manual').open=true;`);
    assert.equal(await run(`return document.querySelector('#cal .pc-after').getBoundingClientRect().height>0;`),true);
    assert.equal(await run(`return document.querySelector('#cal .pc-before').getBoundingClientRect().height===0;`),true);
    assert.equal(await run(`const b=document.querySelector('#cal [data-pc="auto"]'),s=getComputedStyle(b);return s.color!==s.backgroundColor;`),true,'Auto-align text must be visible');
    await run(`document.querySelector('[data-pc="focus"]').click();document.querySelector('.pc-viewport').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));`);
    assert.equal(await run(`return wire.state().realPhase==='photo' && !wire.page().state().focus;`),true);
    await run(`const input=document.querySelector('#cal [data-radius]');input.focus();input.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));`);
    assert.equal(await run(`return wire.state().realPhase;`),'review');
    // Actual paper device rows, protected computer, token rotation and old-server fallback.
    await run(`wire.init({phone:'http://lan/phone/old-token'});window.devices=[{id:'phone1',name:'iPhone Safari',kind:'phone',first_seen:Date.now()-120000,last_seen:Date.now(),photos_sent:2}];wire.enter();`);
    await waitFor("document.querySelector('.pc-phone-empty .kit-text-button')");
    assert.equal(await run(`return document.querySelectorAll('.pc-phone-empty .kit-devices li').length;`),2);
    assert.equal(await run(`return document.querySelectorAll('.pc-phone-empty .kit-devices button').length;`),1);
    await run(`document.querySelector('.pc-phone-empty .kit-text-button').click();`);
    await waitFor("document.querySelector('.pc-phone-empty a')?.href==='http://lan/phone/new-token'");
    assert.equal(await run(`return document.querySelectorAll('.pc-phone-empty .kit-devices button').length;`),0);
    assert.equal(await run(`return document.querySelector('.pc-phone-help').hidden;`),true);
    await run(`wire.helpAfter(24999);`);assert.equal(await run(`return document.querySelector('.pc-phone-help').hidden;`),true);
    await run(`wire.helpAfter(25001);`);assert.equal(await run(`return document.querySelector('.pc-phone-help').hidden;`),false);
    const helpText=await run(`return document.querySelector('.pc-phone-help').textContent;`);assert.match(helpText,/Windows 可能拦住了连接/);assert.doesNotMatch(helpText,/Windows may have blocked/,'help shows only the page language');
    await run(`const select=document.querySelector('.pc-address select');select.value='192.168.1.2';select.dispatchEvent(new Event('change'));`);
    await waitFor("sessionStorage.getItem('discprobe-phone-address')==='192.168.1.2'");
    await run(`wire.back();wire.enter();`);await waitFor("wire.ui()?.status==='ready'");
    assert.equal(await run(`return document.querySelector('.pc-address select').value;`),'192.168.1.2','address persists for session');
    await run(`wire.init({missing:'/api/phone-devices'});wire.enter();`);await waitFor("wire.ui()?.devicesUnavailable");
    assert.equal(await run(`return wire.ui().status==='ready' && [...document.querySelectorAll('.pc-devices')].every(n=>n.hidden);`),true);
    await run(`wire.back();wire.init();wire.enter();`);await waitFor("wire.ui()?.status==='ready'");
    await run(`await wire.page().addPhotos([wire.photo()]);`);
    // Geometry stays unchanged on an unsure result; reasons appear under thumbnails and stamp.
    await run(`wire.enter();`);await waitFor("wire.page()?.state().photos.length===1");
    await run(`window.photoResult={verdict:'unsure',per_photo:[{id:'p1',verdict:'unsure',reason:'反光强'}],rings_mm:null,offset_mm:null,L_frames:null};await wire.next();`);
    assert.equal(await run(`return document.querySelector('.pc-photo-reason').textContent;`),'重拍：反光强');
    assert.equal(await run(`return document.querySelector('#cal').textContent.includes('再拍一张') && document.querySelector('#cal').textContent.includes('跳过，就用现在的结果');`),true);
    await run(`wire.back();wire.enter();`);await waitFor("wire.page()?.state().photos.length===1");
    await run(`await wire.next();`);
    assert.equal(await run(`return !wire.ui().skip.hidden && wire.ui().result.textContent.includes('反光强');`),true,'Cached unsure results keep their explanation and exits');
    // A successful auto-align has a signed offset and Next uses it without another photo job.
    await run(`wire.init({media:'cd',verdict:'good',phone:'http://lan/phone/token'});await wire.next();`);await waitFor("wire.ui()?.status==='ready'");
    await run(`window.photoResult={verdict:'ok',per_photo:[{id:'p1',verdict:'ok',status:'ok'},{id:'p2',verdict:'ok',status:'ok'}],rings_mm:[30,38,47,55],offset_mm:-0.12,L_frames:2.5};window.photos=[wire.photo(),wire.photo('p2')];`);
    // New photos arrive with the next 2 s listing poll, then the 1.5 s read debounce: allow for both under load.
    await waitFor("wire.page()?.state().offsetMm===-0.12",300);
    assert.deepEqual(await run(`return window.jobs.find(j=>j.action==='photo').args.photos;`),['p1','p2']);
    await run(`await wire.next();`);
    assert.equal(await run(`return wire.state().realPhase;`),'saved');
    assert.equal(await run(`return window.jobs.filter(j=>j.action==='photo').length;`),1);
    assert.equal(await run(`return document.querySelector('#cal').textContent.includes('L = 2.5 frames');`),true);
    assert.equal(await run(`return document.querySelector('#cal').textContent.includes('沿轨常数已写入') && !document.querySelector('#cal').textContent.includes('尚未写入预设');`),true);
    // Local file uploads carry the session token and become the job's photo id.
    await run(`wire.init();wire.enter();`);await waitFor("wire.ui()?.status==='ready'");
    await run(`const canvas=document.createElement('canvas');canvas.width=canvas.height=600;const img=await new Promise(r=>canvas.toBlob(r,'image/png'));await wire.page().addPhotos([new File([img],'上传.png',{type:'image/png'})]);window.photoResult={verdict:'rejected',per_photo:[{id:'uploaded',verdict:'rejected',reason:'不是照片'}]};await wire.next();`);
    assert.equal(upload.token,'session-test');assert.equal(upload.filename,encodeURIComponent('上传.png'));
    assert.equal(await run(`return window.jobs[0].args.photos[0];`),'uploaded');
    assert.equal(await run(`return document.querySelector('.pc-photo-reason').textContent;`),'重拍：不是照片');
    // Check both themes and desktop/narrow layouts without a production server.
    for(const [width,theme,lang] of [[1440,'light','zh'],[760,'dark','en'],[390,'light','zh']]){
      await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
      await run(`wire.init({lang:${JSON.stringify(lang)},phone:'http://lan/phone/test-fixture'});window.devices=[{id:'test-phone',name:'iPhone Safari',kind:'phone',first_seen:Date.now()-120000,last_seen:Date.now(),photos_sent:3}];document.documentElement.dataset.theme=${JSON.stringify(theme)};wire.enter();`);await waitFor("wire.ui()?.status==='ready'");
      await run(`await document.fonts.ready;const url=getComputedStyle(document.querySelector('#cal')).borderImageSource.match(/url\\(["']?(.*?)["']?\\)/)?.[1];if(url){const image=new Image();image.src=url;await image.decode().catch(()=>{});}await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));`);
      if(process.env.PHOTO_TEST_SHOTS){const shot=await send('Page.captureScreenshot',{format:'png'});await writeFile(join(resolve(process.env.PHOTO_TEST_SHOTS),`photo-wire-${width}-${theme}-empty.png`),Buffer.from(shot.data,'base64'));}
      await run(`await wire.page().addPhotos([wire.photo()]);`);
      const boxes=await run(`const v=document.querySelector('.pc-viewport').getBoundingClientRect(),p=document.querySelector('#cal').getBoundingClientRect();return {width:innerWidth,scroll:document.documentElement.scrollWidth,v:{x:v.x,y:v.y,right:v.right,bottom:v.bottom},p:{x:p.x,y:p.y,right:p.right,bottom:p.bottom}};`);
      assert.ok(boxes.scroll<=width,JSON.stringify(boxes));assert.ok(boxes.p.right<=width && boxes.v.right<=width,JSON.stringify(boxes));
      if(width>900)assert.ok(boxes.v.right<boxes.p.x);else assert.ok(boxes.v.bottom<boxes.p.y);
      if(process.env.PHOTO_TEST_SHOTS){const shot=await send('Page.captureScreenshot',{format:'png'});await writeFile(join(resolve(process.env.PHOTO_TEST_SHOTS),`photo-wire-${width}-${theme}.png`),Buffer.from(shot.data,'base64'));}
      // The actual calibration paint swaps Next only for the burn phase.
      await run(`wire.phase('burn');`);
      assert.equal(await run(`return document.querySelector('#next').hidden && document.querySelector('.next-confirm .kit-slide-knob').getAttribute('aria-disabled')==='false';`),true);
      const sliderBox=await run(`const b=document.querySelector('.next-confirm').getBoundingClientRect();return {left:b.left,right:b.right,bottom:b.bottom,width:innerWidth};`);
      assert.ok(sliderBox.left>=0&&sliderBox.right<=width&&sliderBox.bottom<=900,JSON.stringify(sliderBox));
      if(process.env.PHOTO_TEST_SHOTS){const shot=await send('Page.captureScreenshot',{format:'png'});await writeFile(join(resolve(process.env.PHOTO_TEST_SHOTS),`kit-wire-${width}-${theme}-slide.png`),Buffer.from(shot.data,'base64'));}
      await run(`wire.phase('random');`);
      assert.equal(await run(`return !document.querySelector('#next').hidden && !document.querySelector('.next-confirm') && document.querySelector('#next').dataset.kitProgress==='indeterminate';`),true);
      await run(`wire.phase('random',.62);`);
      assert.equal(await run(`return document.querySelector('.kit-ring-fill').style.strokeDashoffset;`),'38');
      const colours=await run(`const b=document.querySelector('#next'),f=document.querySelector('.kit-ring-fill');return {bg:getComputedStyle(b).backgroundColor,fg:getComputedStyle(b).color,ring:getComputedStyle(f).stroke};`);
      assert.notEqual(colours.bg,colours.fg);assert.equal(colours.ring,colours.fg);
      if(process.env.PHOTO_TEST_SHOTS){const shot=await send('Page.captureScreenshot',{format:'png'});await writeFile(join(resolve(process.env.PHOTO_TEST_SHOTS),`kit-wire-${width}-${theme}-ring.png`),Buffer.from(shot.data,'base64'));}

    }
    const startAlignment=async (lang='zh', photo=0)=>{
      await run(`wire.init({verdict:'good',lang:${JSON.stringify(lang)}});window.alignmentEnabled=true;window.photos=${JSON.stringify(alignmentFixture?.rows ?? [{id:'p1',name:'target.svg',url:'/disc.svg',verdict:'unsure'}])};if(${!!alignmentFixture}){wire.state().geo.path=${JSON.stringify(alignmentFixture?.geo ?? '')};wire.state().detected.capacity_sectors=2295104;}wire.enter();`);
      await waitFor("wire.page()?.state().photos.length && document.querySelector('[data-pc=align]')");
      await run(`document.querySelector('[data-photo="${photo}"]').click();`);
    };
    await startAlignment();
    assert.equal(await run(`return !!document.querySelector(".pc-prediction");`),false);
    await run(`document.querySelector('[data-pc=align]').click();`);
    await waitFor("document.querySelector('.pc-prediction')",160);
    const valueOf=field=>run(`return document.querySelector('[data-align-value="${field}"]').valueAsNumber;`);
    const pathOf=()=>run(`return document.querySelector('.pc-prediction').getAttribute('d');`);
    const initial=await valueOf('L_mm'), angle=await valueOf('c_deg'), pathBefore=await pathOf();
    await run(`document.querySelector('[data-align-value="L_mm"]').focus();`);
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});
    assert.ok(Math.abs(await valueOf('L_mm')-initial-.025)<1e-8);
    assert.notEqual(await pathOf(),pathBefore);
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39,modifiers:8});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39,modifiers:8});
    assert.ok(Math.abs(await valueOf('L_mm')-initial-.275)<1e-8);
    const anglePath=await pathOf();
    await run(`document.querySelector('[data-align-value="c_deg"]').focus();`);
    await send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowLeft',code:'ArrowLeft',windowsVirtualKeyCode:37,modifiers:8});
    await send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowLeft',code:'ArrowLeft',windowsVirtualKeyCode:37,modifiers:8});
    assert.ok(Math.abs(await valueOf('c_deg')-angle+.5)<1e-8);
    assert.notEqual(await pathOf(),anglePath);
    const track=await run(`const r=document.querySelector('[data-align-value="L_mm"]').getBoundingClientRect();return {left:r.left,width:r.width,y:r.top+r.height/2};`);
    const dragFrom=track.left+track.width*.42, dragTo=track.left+track.width*.54;
    await send('Input.dispatchMouseEvent',{type:'mousePressed',x:dragFrom,y:track.y,button:'left',buttons:1,clickCount:1});
    await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:dragTo,y:track.y,button:'left',buttons:1});
    await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:dragTo,y:track.y,button:'left',buttons:0,clickCount:1});
    assert.ok(await valueOf('L_mm')>0,'pointer drag moves the native range control');
    const set=(l,c)=>run(`for(const [field,value] of Object.entries({L_mm:${l},c_deg:${c}})){const input=document.querySelector('[data-align-value="'+field+'"]');input.value=value;input.dispatchEvent(new Event('input'));}`);
    await set(initial+2,angle);
    await waitFor("document.querySelector('.pc-slider-score').classList.contains('pc-slider-weak')");
    const misaligned=await run(`return document.querySelector('.pc-slider-score').textContent;`);
    assert.equal(await run(`return document.querySelector('#next').disabled;`),false,'weak score still permits saving');
    await set(initial,angle);
    await waitFor("document.querySelector('.pc-slider-score').textContent.includes(' / ') && !document.querySelector('.pc-slider-weak')");
    const aligned=await run(`return document.querySelector('.pc-slider-score').textContent;`);
    if(alignmentFixture)console.log(JSON.stringify({photo:alignmentFixture.rows[0].name,initial,angle,aligned,misaligned}));
    await run(`await wire.next();`);
    await waitFor("wire.state().realPhase==='saved'",160).catch(async error=>{
      throw new Error(error.message+' '+await run(`return JSON.stringify({notice:wire.state().photoNotice,phase:wire.state().realPhase,jobs:window.jobs});`));
    });
    assert.equal(await run(`return wire.state().savedPhotoShift.origin;`),'manual-slider');
    assert.equal(manualDecision.L_mm,initial);
    if(alignmentFixture){
      await startAlignment('en',1);
      await run(`document.querySelector('[data-pc=align]').click();`);
      await waitFor("document.querySelector('.pc-slider-score')?.textContent.includes(' / ')",160);
      const second=await valueOf('L_mm'), rotation=await valueOf('c_deg');
      await set(second+.025,rotation);
      await waitFor("document.querySelector('.pc-slider-score')?.textContent.includes(' / ')");
      const plus=await run(`return document.querySelector('.pc-slider-score').textContent;`);
      await set(second+2,rotation);
      await waitFor("document.querySelector('.pc-slider-score').classList.contains('pc-slider-weak')");
      const away=await run(`return document.querySelector('.pc-slider-score').textContent;`);
      console.log(JSON.stringify({photo:alignmentFixture.rows[1].name,initial:second,selected:second+.025,angle:rotation,aligned:plus,misaligned:away}));
    }
    if(process.env.PHOTO_ALIGN_SHOTS){
      for(const width of [1440,390])for(const theme of ['light','dark'])for(const lang of ['zh','en']){
        await send('Emulation.setDeviceMetricsOverride',{width,height:width===390?844:900,deviceScaleFactor:1,mobile:false});
        await startAlignment(lang);
        await run(`document.documentElement.dataset.theme=${JSON.stringify(theme)};document.querySelector('[data-pc=align]').click();`);
        await waitFor("document.querySelector('.pc-slider-score')?.textContent.includes(' / ')",160);
        const geometry=await run(`await document.fonts.ready;const q=s=>document.querySelector(s);await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));const box=s=>{const b=q(s).getBoundingClientRect();return [b.left,b.top,b.right,b.bottom];};return {view:box('.pc-viewport'),L:box('[data-align-value=L_mm]'),c:box('[data-align-value=c_deg]'),score:box('.pc-slider-score'),paper:box('#cal'),scroll:document.documentElement.scrollWidth,height:innerHeight};`);
        console.log(JSON.stringify({width,theme,lang,...geometry}));
        assert.ok(geometry.scroll<=width&&geometry.L[0]>=0&&geometry.L[2]<=width);
        assert.ok(geometry.L[1]>=geometry.paper[1]&&geometry.score[3]<=geometry.paper[3],JSON.stringify(geometry));
        const shot=await send('Page.captureScreenshot',{format:'png'});
        await writeFile(join(resolve(process.env.PHOTO_ALIGN_SHOTS),`manual-${width}-${theme}-${lang}.png`),Buffer.from(shot.data,'base64'));
      }
    }
    await run(`wire.init();window.alignmentEnabled=false;`);
    for(const missing of ['/api/phone-link','/api/photos']){
      await run(`wire.init({media:'cd',verdict:'good',missing:${JSON.stringify(missing)}});await wire.next();`);await waitFor("wire.ui()?.status==='unavailable'");
      assert.equal(await run(`return document.querySelector('.pc-phone-block')===null && document.querySelector('[data-pc="auto"]')===null && !document.querySelector('#next').disabled && document.querySelector('#cal').textContent.includes('DIS');`),true);
      await run(`wire.back();`);assert.equal(await run(`return wire.state().realPhase;`),'review');
    }
    await run(`wire.ui()&&wire.back();`);
    // The real phone HTML, with token-scoped listing fixtures and no backend/server.
    await run(`sessionStorage.setItem('discprobe-phone-run-one','["mine"]');`);
    await send('Page.navigate',{url:'http://photo.test/phone/fixture'});
    await waitFor("document.querySelector('#sent button')");
    for(const [width,height] of [[375,812],[812,375],[820,1180],[1180,820]]){
      await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
      const layout=await run(`return {scroll:document.documentElement.scrollWidth,width:innerWidth,targets:[...document.querySelectorAll('input,button,a,summary')].filter(n=>n.getBoundingClientRect().width).map(n=>{const b=n.getBoundingClientRect();return {tag:n.tagName,w:b.width,h:b.height};})};`);
      assert.ok(layout.scroll<=width,JSON.stringify(layout));
      assert.ok(layout.targets.length>=4);for(const target of layout.targets)assert.ok(target.w>=44&&target.h>=44,JSON.stringify({width,height,target}));
      if(process.env.PHOTO_TEST_SHOTS){const shot=await send('Page.captureScreenshot',{format:'png'});await writeFile(join(resolve(process.env.PHOTO_TEST_SHOTS),`phone-${width}x${height}.png`),Buffer.from(shot.data,'base64'));}
    }
    // Stop the phone's poll before closing CDP, then drain intercepted requests.
    await send('Page.navigate',{url:'about:blank'});
    await send('Fetch.disable');
    await Promise.all([...intercepts]);
    assert.deepEqual(interceptErrors,[],'fixture requests must complete before teardown');
  }finally{
    ws?.close();
    if(browser && browser.exitCode===null){browser.kill();await Promise.race([once(browser,'exit'),new Promise(r=>setTimeout(r,3000))]);}
    // Only remove the freshly created browser profile, after checking its absolute parent.
    assert.equal(dirname(resolve(dir)),resolve(testRoot));
    assert.ok(resolve(dir).startsWith(join(resolve(testRoot),'.photo-wire-browser-')));
    await rm(dir,{recursive:true,force:true,maxRetries:5,retryDelay:200});
  }
});
