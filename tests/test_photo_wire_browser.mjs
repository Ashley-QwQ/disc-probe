// Optional real-browser integration: intercepted fixtures, never the drive backend or a running server.
// Uses Node's built-in WebSocket/CDP, so the site keeps its zero-npm-dependency setup.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {existsSync,readFileSync} from 'node:fs';
import {mkdtemp,readFile,rm,writeFile} from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {join,resolve,dirname,extname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {once} from 'node:events';

const edge=process.env.PHOTO_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const testRoot=fileURLToPath(new URL('.',import.meta.url));
const home=new URL('../discprobe/web/home/',import.meta.url);
const calibrate=readFileSync(new URL('calibrate.js',home),'utf8');
const index=readFileSync(new URL('index.html',home),'utf8');
const html=`<!doctype html><html data-mode="cal" data-motion="off" class="cal-staged"><head><meta charset="utf-8"><base href="http://photo.test/">
<style>${index.match(/<style>([\s\S]*?)<\/style>/)[1]}</style><link rel="stylesheet" href="/photocal.css"></head>
<body><div class="top"><button id="back">Back</button></div><main id="cal" class="cal"></main>
<div class="bar"><div id="job" hidden><span id="job-name"></span><span id="job-time"></span></div><button id="next" class="next"><span id="next-text"></span></button></div>
<script type="module">
import {wire} from '/wire.js';
window.wire=wire; window.ready=true;
</script></body></html>`;
const moduleSource=`import {photoPage} from '/photocal.js';
import {budgetHTML,cdPhoto,measurementRecovery,recoveryKind,recoveryAction,recoveryCommands,remeasure,stopReason,photoSaveWords} from '/guidance.mjs';
const loadDisc={desk(){}}; const calchart={resultChart:()=>''}; const sfx={done(){},problem(){},failure(){}};
const floorLog=()=>({mount(){},start(){},end(){},title(){},progress(){},log(){}});
${calibrate.replace(/^import .*;.*$/gm,'')}
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fakeApi={lang:()=>window.lang||'zh',selectedDrive:()=>null,burnerLayer:document.body,nextWhy(){},jobProgress(){},backend:{mock:false,escapeHTML:esc,errorText:e=>e.message,
request:async(path,payload)=>{window.requests.push({path,payload}); if(window.missing&&path.includes(window.missing))throw Object.assign(new Error('Not found'),{status:404}); if(path.startsWith('/api/phone-link'))return {url:window.phone||null,qr_svg:null};if(path.startsWith('/api/photos'))return {photos:window.photos};return {};},
job:async(payload)=>{window.jobs.push(payload);return payload.action==='disexport'?{path:'presets/photo.json',photo_shift:{written:true,frames:2.5}}:window.photoResult;},state:async()=>({catalogue:{[flow.detected.media]:[{id:'saved',geo:flow.geo.path,name:'MID'}]}})}};
export const wire={
init({media='dvd',verdict='narrow_span',missing='',lang='zh',phone=null}={}){closePhoto();window.requests=[];window.jobs=[];window.photos=[];window.missing=missing;window.lang=lang;window.phone=phone;api=fakeApi;$=id=>document.getElementById(id);flow={realPhase:'review',geo:{path:'results/run-one',verdict,measurement:{span_mm:[28,48]}},timing:{verdict:'good'},detected:{media,kind:media,mid:'MID',capacity_sectors:300000},item:{row:media},preset:'presets/existing.json',warnEl:document.createElement('div')};discWentIn=true;st={show(on){document.body.dataset.stage=on;},set(){}};document.getElementById('back').onclick=back;document.getElementById('next').onclick=()=>realNext();paint();},
enter:enterPhoto,next:realNext,back,state:()=>flow,page:()=>photoUI?.page,ui:()=>photoUI,
photo:(id='p1')=>({id,name:id+'.svg',url:'/disc.svg'}),
};`;

test('photo flow in Chromium: paper, keys, polling, verdicts, upload and fallback', {skip:!existsSync(edge),timeout:60000}, async()=>{
  const dir=await mkdtemp(join(testRoot,'.photo-wire-browser-'));
  let browser, ws;
  let upload;
  try{
    browser=spawn(edge,['--headless=new','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${dir}`,'about:blank'],{stdio:'ignore',windowsHide:true});
    browser.on('error',()=>{});
    let port;
    for(let i=0;i<100;i++){try{port=(await readFile(join(dir,'DevToolsActivePort'),'utf8')).split('\n')[0];break;}catch{await new Promise(r=>setTimeout(r,100));}}
    assert.ok(port,'Headless browser did not start');
    const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`,{signal:AbortSignal.timeout(5000)})).json();
    const target=pages.find(p=>p.type==='page' && p.url==='about:blank');assert.ok(target,'No fixture tab');
    ws=new WebSocket(target.webSocketDebuggerUrl);await once(ws,'open');
    let seq=0;const pending=new Map(),exceptions=[];
    let paused;
    ws.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.method==='Fetch.requestPaused')paused?.(m.params);if(m.method==='Runtime.exceptionThrown')exceptions.push(m.params.exceptionDetails);if(m.id){pending.get(m.id)?.(m);pending.delete(m.id);}});
    const send=(method,params={})=>new Promise((ok,fail)=>{const id=++seq,timer=setTimeout(()=>{pending.delete(id);fail(new Error('CDP timeout: '+method));},5000);pending.set(id,m=>{clearTimeout(timer);m.error?fail(new Error(JSON.stringify(m.error))):ok(m.result);});ws.send(JSON.stringify({id,method,params}));});
    const run=async code=>{
      const r=await send('Runtime.evaluate',{expression:`(async()=>{${code}})()`,awaitPromise:true,returnByValue:true});
      if(r.exceptionDetails)throw new Error(r.exceptionDetails.exception.description);return r.result.value;
    };
    const waitFor=async code=>{for(let i=0;i<100;i++){if(await run(`return !!(${code});`))return;await new Promise(r=>setTimeout(r,30));}throw new Error('Timeout: '+code+' '+JSON.stringify(exceptions));};
    await send('Runtime.enable');
    await send('Page.enable');
    await send('Page.stopLoading');
    paused=async({requestId,request})=>{
      const path=new URL(request.url).pathname;let body,type='text/plain',status=200;
      if(path==='/'){body=html;type='text/html';}
      else if(path==='/wire.js'){body=moduleSource;type='text/javascript';}
      else if(path==='/disc.svg'){type='image/svg+xml';body='<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600"><rect width="600" height="600" fill="#555"/><circle cx="300" cy="300" r="255" fill="#aaa" stroke="#222"/><circle cx="300" cy="300" r="32" fill="#555"/></svg>';}
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
    assert.equal(await run(`return document.querySelector('#cal .pc-after').getBoundingClientRect().height>0;`),true);
    assert.equal(await run(`return document.querySelector('#cal .pc-before').getBoundingClientRect().height===0;`),true);
    assert.equal(await run(`const b=document.querySelector('#cal [data-pc="auto"]'),s=getComputedStyle(b);return s.color!==s.backgroundColor;`),true,'Auto-align text must be visible');
    await run(`document.querySelector('[data-pc="focus"]').click();document.querySelector('.pc-viewport').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));`);
    assert.equal(await run(`return wire.state().realPhase==='photo' && !wire.page().state().focus;`),true);
    await run(`const input=document.querySelector('#cal [data-radius]');input.focus();input.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));`);
    assert.equal(await run(`return wire.state().realPhase;`),'review');
    // Geometry stays unchanged on an unsure result; reasons appear under thumbnails and stamp.
    await run(`wire.enter();`);await waitFor("wire.page()?.state().photos.length===1");
    await run(`window.photoResult={verdict:'unsure',per_photo:[{id:'p1',verdict:'unsure',reason:'反光强'}],rings_mm:null,offset_mm:null,L_frames:null};await wire.next();`);
    assert.equal(await run(`return document.querySelector('.pc-photo-reason').textContent;`),'反光强');
    assert.equal(await run(`return document.querySelector('#cal').textContent.includes('再拍一张') && document.querySelector('#cal').textContent.includes('跳过，就用现在的结果');`),true);
    await run(`wire.back();wire.enter();`);await waitFor("wire.page()?.state().photos.length===1");
    await run(`await wire.next();`);
    assert.equal(await run(`return !wire.ui().skip.hidden && wire.ui().result.textContent.includes('反光强');`),true,'Cached unsure results keep their explanation and exits');
    // A successful auto-align has a signed offset and Next uses it without another photo job.
    await run(`wire.init({media:'cd',verdict:'good',phone:'http://lan/phone/token'});await wire.next();`);await waitFor("wire.ui()?.status==='ready'");
    await run(`await wire.page().addPhotos([wire.photo()]);window.photoResult={verdict:'ok',per_photo:[{id:'p1',verdict:'ok',reason:'清楚'}],rings_mm:[30,38,47,55],offset_mm:-0.12,L_frames:2.5};document.querySelector('#cal [data-pc="auto"]').click();`);
    await waitFor("wire.page()?.state().offsetMm===-0.12");
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
    assert.equal(await run(`return document.querySelector('.pc-photo-reason').textContent;`),'不是照片');
    // Check both themes and desktop/narrow layouts without a production server.
    for(const [width,theme,lang] of [[1440,'light','zh'],[760,'dark','en']]){
      await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
      await run(`wire.init({lang:${JSON.stringify(lang)}});document.documentElement.dataset.theme=${JSON.stringify(theme)};wire.enter();`);await waitFor("wire.ui()?.status==='ready'");
      await run(`await document.fonts.ready;const url=getComputedStyle(document.querySelector('#cal')).borderImageSource.match(/url\\(["']?(.*?)["']?\\)/)?.[1];if(url){const image=new Image();image.src=url;await image.decode().catch(()=>{});}await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));`);
      if(process.env.PHOTO_TEST_SHOTS){const shot=await send('Page.captureScreenshot',{format:'png'});await writeFile(join(resolve(process.env.PHOTO_TEST_SHOTS),`photo-wire-${width}-${theme}-empty.png`),Buffer.from(shot.data,'base64'));}
      await run(`await wire.page().addPhotos([wire.photo()]);`);
      const boxes=await run(`const v=document.querySelector('.pc-viewport').getBoundingClientRect(),p=document.querySelector('#cal').getBoundingClientRect();return {width:innerWidth,scroll:document.documentElement.scrollWidth,v:{x:v.x,y:v.y,right:v.right,bottom:v.bottom},p:{x:p.x,y:p.y,right:p.right,bottom:p.bottom}};`);
      assert.ok(boxes.scroll<=width,JSON.stringify(boxes));assert.ok(boxes.p.right<=width && boxes.v.right<=width,JSON.stringify(boxes));
      if(width>900)assert.ok(boxes.v.right<boxes.p.x);else assert.ok(boxes.v.bottom<boxes.p.y);
      if(process.env.PHOTO_TEST_SHOTS){const shot=await send('Page.captureScreenshot',{format:'png'});await writeFile(join(resolve(process.env.PHOTO_TEST_SHOTS),`photo-wire-${width}-${theme}.png`),Buffer.from(shot.data,'base64'));}
    }
    for(const missing of ['/api/phone-link','/api/photos']){
      await run(`wire.init({media:'cd',verdict:'good',missing:${JSON.stringify(missing)}});await wire.next();`);await waitFor("wire.ui()?.status==='unavailable'");
      assert.equal(await run(`return document.querySelector('.pc-phone-block')===null && document.querySelector('[data-pc="auto"]')===null && !document.querySelector('#next').disabled && document.querySelector('#cal').textContent.includes('DIS');`),true);
      await run(`wire.back();`);assert.equal(await run(`return wire.state().realPhase;`),'review');
    }
    await run(`wire.ui()&&wire.back();`);
  }finally{
    ws?.close();
    if(browser && browser.exitCode===null){browser.kill();await Promise.race([once(browser,'exit'),new Promise(r=>setTimeout(r,3000))]);}
    // Only remove the freshly created browser profile, after checking its absolute parent.
    assert.equal(dirname(resolve(dir)),resolve(testRoot));
    assert.ok(resolve(dir).startsWith(join(resolve(testRoot),'.photo-wire-browser-')));
    await rm(dir,{recursive:true,force:true,maxRetries:5,retryDelay:200});
  }
});
