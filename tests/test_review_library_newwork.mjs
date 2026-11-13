// Full home-page DOM with file assets and synthetic core responses. No product server or devices.
import assert from 'node:assert/strict';
import {existsSync, readFileSync, writeFileSync, mkdtempSync, mkdirSync} from 'node:fs';
import {rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {spawn} from 'node:child_process';

const home = new URL('../discprobe/web/home/', import.meta.url);
const index = readFileSync(new URL('index.html', home), 'utf8');
const manifest = JSON.parse(readFileSync(new URL('../gui.json', home), 'utf8'));
const edge = process.env.KIT_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
assert.ok(existsSync(edge), 'Set KIT_TEST_BROWSER to Chromium');
const dir = mkdtempSync(join(tmpdir(), 'discprobe-review-'));
const shots = resolve('.impeccable/review-fixes'); mkdirSync(shots, {recursive:true});
const ownShots = resolve('.impeccable/own-params'); mkdirSync(ownShots, {recursive:true});
const fixture = join(dir, 'review.html');
const bootstrap = `<base href="${home}"><script>
localStorage.setItem('dp-lang','zh');localStorage.setItem('dp-motion','off');localStorage.setItem('dp-sound','off');
window.reviewErrors=[];addEventListener('error',e=>reviewErrors.push(e.message));addEventListener('unhandledrejection',e=>reviewErrors.push(String(e.reason)));
window.reviewCalls=[];
const nativeFetch=window.fetch.bind(window);
window.fetch=async (path,opts)=>{
 const url=new URL(path,document.baseURI);
 if(url.pathname.includes('/api/')) {
   const payload=opts?.body?JSON.parse(opts.body):null;
   reviewCalls.push({path:String(path),method:opts?.method||'GET',payload});
   if(String(path)==='/api/presets')return {ok:true,json:async()=>!payload?({version:1,presets:[]}):
     ({entries:window.reviewImportRows||[],written:payload.operation==='import'?(window.reviewImportRows||[]).map(r=>({index:r.index,path:'presets/'+r.preset.id+'.json'})):[],duplicates:[]})};
   throw Error('Unexpected core access: '+path);
 }
 if(url.protocol!=='file:')throw Error('No network in this test: '+url);
 return nativeFetch(path,opts);
};
window.EventSource=class {addEventListener(){} close(){}};
window.reviewHandshake=async path=>({ok:true,json:async()=>path==='/gui.json'?${JSON.stringify(manifest)}:{api_version:'1.0',capabilities:${JSON.stringify([...manifest.required_capabilities,...manifest.optional_capabilities])}.filter(c=>!location.search.includes('no-presets')||c!=='presets-io')}});
</script>`;
let html = index.replace('<head>', '<head>'+bootstrap)
  .replace('await handshake();', 'await handshake(document, window.reviewHandshake, {protocol:"http:",search:""});');
const tail = html.lastIndexOf('</script>');
html = html.slice(0,tail) + '\nwindow.review={api,DATA,render,newplan:await import("./newplan.js")};\n' + html.slice(tail);
writeFileSync(fixture, html);
const delay = ms => new Promise(r=>setTimeout(r,ms));
let browser, socket, seq=0; const pending=new Map();
async function cdp(method,params={}) {
  const id=++seq, reply=new Promise((resolve,reject)=>pending.set(id,{resolve,reject}));
  socket.send(JSON.stringify({id,method,params})); return reply;
}
async function evaluate(expression) {
  if (expression.includes('await ')) expression = `(async()=>{${expression}})()`;
  const result=await cdp('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
  assert.ok(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result.value;
}
async function until(expression,message) {
  for(let i=0;i<200;i++){if(await evaluate(expression))return;await delay(50);}
  assert.fail(message+': '+JSON.stringify(await evaluate('({errors:reviewErrors,mode:document.documentElement.dataset.mode})')));
}
async function check(expression,message) {assert.ok(await evaluate(expression),message);}
async function shot(name, own=false) {
  await evaluate('document.fonts.ready'); await delay(100);
  const {data}=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  writeFileSync(join(own?ownShots:shots,name+'.png'),Buffer.from(data,'base64'));
}
async function open(extra='') {
  await cdp('Page.navigate',{url:pathToFileURL(fixture).href+'?mock&'+extra});
  await until('!!window.review','home fixture ready');
}
try {
  browser=spawn(edge,['--headless=new','--disable-gpu','--disable-background-networking','--no-sandbox','--no-first-run','--no-default-browser-check',
    '--allow-file-access-from-files','--remote-debugging-port=0',`--user-data-dir=${join(dir,'profile')}`,'about:blank'],{windowsHide:true,stdio:'ignore'});
  let port;
  for(let i=0;i<100&&!port;i++) {
    try {port=readFileSync(join(dir,'profile','DevToolsActivePort'),'utf8').split(/\r?\n/)[0];}catch(e){if(!['ENOENT','EBUSY','EPERM','EACCES'].includes(e.code))throw e;}
    if(!port)await delay(100);
  }
  assert.ok(port,'CDP endpoint ready');
  assert.ok(![8772,8795,8798,8812,8841,8863].includes(Number(port)),'test uses an ephemeral port');
  const targets=await fetch(`http://127.0.0.1:${port}/json/list`).then(r=>r.json());
  socket=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  socket.onmessage=({data})=>{const msg=JSON.parse(data),cb=pending.get(msg.id);if(cb){pending.delete(msg.id);msg.error?cb.reject(Error(JSON.stringify(msg.error))):cb.resolve(msg.result);}};
  await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  // Force the system preference off: explicit page motion-on must still animate.
  await cdp('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  await open();
  await evaluate('document.getElementById("library").click()');
  await until('document.querySelectorAll(".layer.solid .disc").length>=8','shelf loaded');
  await check('document.querySelectorAll(".kinds .kind").length===3 && !document.querySelector(".kinds [data-col=drive]") && document.querySelector(".tools [data-col=drive]")','kinds are separate from header drive entry');
  await check('getComputedStyle(document.querySelector(".kinds")).transform==="none" && getComputedStyle(document.querySelector(".counter")).transform!=="none"','horizontal kinds and slanted count');
  await check('document.querySelector(".facts dd").id==="left" && parseFloat(getComputedStyle(document.getElementById("left")).fontSize)>parseFloat(getComputedStyle(document.getElementById("sectors")).fontSize) && getComputedStyle(document.getElementById("sectors")).fontFamily.includes("mono")','remaining first/larger, sectors small mono');
  await check('!document.querySelector("button.gallery") && document.querySelector(".disc.is-in-drive").style.transform.includes("-20px")','dead gallery removed; inserted disc pulls forward');
  await until('document.querySelector(".layer.ghost path")','background outlines loaded');
  await check('[...document.querySelectorAll(".layer.ghost path")].every(p=>p.classList.contains("iso-edge") && getComputedStyle(p).fill==="none") && [...document.querySelectorAll(".layer.ghost:not([data-depth=\\"0\\"])")].every(g=>+getComputedStyle(g).opacity<=.08)','background is outline-only at most eight percent');
  await check('getComputedStyle(document.querySelector(".stage")).maskImage.includes("60%")','text-column mask');
  await check('getComputedStyle(document.querySelector(".sheen")).display==="none"','meaningless selected rainbow hidden');
  await until('!document.getElementById("presetio-entry").hidden','presets entry available');
  await check('getComputedStyle(document.getElementById("presetio-entry")).position==="static" && document.getElementById("presetio-entry").textContent==="预设导入导出"','presets inline and translated');
  await evaluate('document.getElementById("lang").click()');
  await check('document.getElementById("presetio-entry").textContent==="Presets"','presets English');
  await evaluate('document.getElementById("lang").click();review.api.goTo("dvd",6)');
  await check('document.getElementById("name").textContent.includes("DVD‑RW") && !document.getElementById("name").textContent.includes("DVD-RW")','hyphen cannot break after instant fill');
  await evaluate('document.documentElement.dataset.motion="on";document.querySelector("[data-motion=on]").click();review.api.goTo("dvd",0);review.api.goTo("dvd",6)');
  await until('!document.getElementById("name").querySelector(".roll")','rolling name settled');
  await check('document.getElementById("name").textContent.includes("DVD‑RW") && parseFloat(document.getElementById("name").style.fontStretch)===100','roll reset retains no-break and shrinks to normal width before wrap');
  for(const theme of ['paper','dark']) {
    await evaluate(`document.documentElement.dataset.theme=${JSON.stringify(theme)}`);
    console.log(await evaluate('JSON.stringify({counter:document.querySelector(".counter").getBoundingClientRect().toJSON(),count:document.querySelector(".count").getBoundingClientRect().toJSON(),idx:document.getElementById("idx").getBoundingClientRect().toJSON(),style:getComputedStyle(document.querySelector(".counter")).cssText})'));
    await shot('library-'+theme);
  }
  await evaluate('document.documentElement.dataset.motion="off";await review.newplan.start(review.api)');
  await until('document.querySelector("[data-opt=auto]").textContent.includes("自动认出")','recognised: the auto choice names the disc');
  await check('document.querySelector(".np-dial").dataset.open==="false" && document.querySelector("[data-opt=auto]").getAttribute("aria-checked")==="true" && document.querySelector("[data-opt=manual]").getAttribute("aria-checked")==="false"','auto ticked, dial put away by default');
  await check('document.getElementById("next-text").textContent==="下一步：放进图片" && getComputedStyle(document.querySelector(".np-batch")).appearance==="none"','calibrated Next and styled native select');
  for(const theme of ['paper','dark']) {
    await evaluate(`document.documentElement.dataset.theme=${JSON.stringify(theme)}`);
    await shot('newwork-'+theme+'-closed');
    await evaluate('document.querySelector("[data-opt=manual]").click()');
    await check('document.querySelector(".np-dial").dataset.open==="true" && document.querySelector("[data-opt=manual]").getAttribute("aria-checked")==="true" && document.querySelector("[data-opt=auto]").getAttribute("aria-checked")==="false" && document.activeElement.classList.contains("np-key")','manual ticks itself, unticks auto, slides the dial in with keyboard focus');
    await check('getComputedStyle(document.querySelector(".np-dial-clip")).position==="absolute" && document.querySelector(".np-dial").getBoundingClientRect().top >= document.querySelector(".np-sheet").getBoundingClientRect().top - 2','the dial hangs from the sheet top edge, out of the flow (no jump)');
    await shot('newwork-'+theme+'-open');
    await evaluate('document.activeElement.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}));document.querySelector(".np-batch").value="1";document.querySelector(".np-batch").dispatchEvent(new Event("change"))');
    await check('document.querySelector(".np-dial").dataset.open==="false" && document.getElementById("next-text").textContent==="下一步：放进图片" && document.querySelector(".np-cal-text").textContent.includes("一小时") && document.querySelector(".np-cal-text").textContent.includes("3 张")','uncalibrated Next, consistent up-front budget, Esc collapses');
    await shot('newwork-'+theme+'-uncalibrated');
    await evaluate('document.querySelector(".np-batch").value="0";document.querySelector(".np-batch").dispatchEvent(new Event("change"))');
  }
  await evaluate('document.querySelector(".np-library").click()');
  await check('document.documentElement.dataset.mode==="" && document.documentElement.dataset.home==="library" && document.getElementById("name").textContent.includes("Verbatim")','batch link opens exact batch');
  await evaluate('document.getElementById("back").click()');
  await check('document.documentElement.dataset.mode==="newplan" && !document.querySelector(".np").hidden','library Back returns to form');
  await evaluate('document.querySelector(".np-library").click();review.api.goTo("dvd",1);document.getElementById("next").click()');
  await check('document.documentElement.dataset.mode==="newplan" && document.querySelector(".np-batch").selectedOptions[0].textContent.includes("TDK")','library can return another chosen batch');
  await evaluate('document.querySelector(".np-batch").value="1";document.querySelector(".np-batch").dispatchEvent(new Event("change"));document.getElementById("next").click()');
  await until('document.documentElement.dataset.mode==="design"','an uncalibrated batch still goes on to drawing (calibration is a link, not a gate)');
  await evaluate(`await review.newplan.start(review.api);document.querySelector('.np-name').value='我的作品';
    window.reviewImportRows=['cd','dvd','dvd','dvd'].map((media,index)=>({index,media,valid:true,disabled:false,
      image_compatible:index!==3,issues:[],preset:{id:'own-'+index,displayName:'DIS '+media.toUpperCase()+' '+index,
        innerRadiusMm:25,outerRadiusMm:58,...(media==='cd'?{sectors:359849}:{totalSectors:2295104})}}));
    review.api.syncState=async()=>{for(const row of reviewImportRows){if(!review.DATA[row.media].some(it=>it.id==='preset:'+row.preset.id))
      review.DATA[row.media].push({id:'preset:'+row.preset.id,name:row.preset.displayName,imported:true,
        image_compatible:row.image_compatible,s:row.image_compatible?'imported':'unknown',
        geo:row.image_compatible?'presets/'+row.preset.id+'.json':null});}};`);
  await until('!document.querySelector(".np-own").hidden','numbers links available');
  await shot('newwork-link',true);
  await evaluate('document.querySelector(".np-import").click()');
  await until('document.querySelector(".presetio").dataset.state==="import"&&!document.querySelector(".presetio input[type=file]").disabled','new-work link opens import lever down');
  await evaluate('document.getElementById("back").click()');
  await check('document.documentElement.dataset.mode==="newplan"&&document.querySelector(".np-name").value==="我的作品"','Back restores form before import');
  await evaluate(`document.querySelector('.np-batch').value='';document.querySelector('.np-batch').dispatchEvent(new Event('change'));
    document.querySelector('.np-import').click();`);
  await until('!document.querySelector(".presetio input[type=file]").disabled','empty selection detour ready');
  await evaluate(`document.querySelector('.presetio').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));`);
  await check('document.querySelector(".np-batch").value===""','Decide later survives closing without an import');
  await evaluate('document.querySelector(".np-type").click()');
  await until('document.querySelector(".presetio-manual").open&&!document.querySelector("[data-preview]").disabled','manual entry opens import paper');
  await check('document.querySelector("[data-manual]").elements.media.value==="dvd"','manual entry defaults to current kind');
  await evaluate(`const form=document.querySelector('[data-manual]');
    for(const [key,value]of Object.entries({displayName:'我的 DVD',innerRadiusMm:25,outerRadiusMm:58,sectors:2295104}))form.elements.namedItem(key).value=value;
    document.querySelector('.presetio-manual').scrollIntoView({block:'start'});`);
  await shot('manual-form',true);
  await evaluate(`document.querySelector('.presetio').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
    document.querySelector('.np-import').click();`);
  await until('!document.querySelector(".presetio input[type=file]").disabled','import ready');
  await evaluate(`const transfer=new DataTransfer();transfer.items.add(new File(['{}'],'batch.json',{type:'application/json'}));
    document.querySelector('.presetio-drop').dispatchEvent(new DragEvent('drop',{dataTransfer:transfer,bubbles:true,cancelable:true}));`);
  await until('!document.querySelector("[data-import]").disabled','DIS preview ready');
  await check('document.querySelector("[data-rows]").textContent.includes("仅存档")','archive-only preview says it cannot draw');
  await evaluate('document.querySelector("[data-import]").click()');
  await until('document.querySelector(".presetio-status").textContent.includes("Imported: 4")','imports complete');
  await evaluate('document.getElementById("back").click()');
  await check('document.documentElement.dataset.mode==="newplan"&&document.querySelector(".np-batch").selectedOptions[0].textContent==="DIS DVD 1"&&document.querySelector(".np-name").value==="我的作品"','first imported preset of current kind selected, name kept');
  await check('document.querySelector(".np-cal-text").textContent==="参数来自 DIS（未经 DP 实测）"&&document.querySelector(".np-cal-go").hidden','import has its own unmeasured status without calibration nag');
  await check('![...document.querySelector(".np-batch").options].some(o=>o.textContent==="DIS DVD 3")','archive-only batch not offered as geometry');
  await shot('imported-selected',true);
  await evaluate('document.querySelector(".np-library").click();document.getElementById("back").click()');
  await check('document.querySelector(".np-batch").selectedOptions[0].textContent==="DIS DVD 1"','imported selection survives library detour');
  await evaluate('document.getElementById("next").click()');
  await until('document.documentElement.dataset.mode==="design"','imported preset continues to drawing');
  await check('document.body.textContent.includes("DIS DVD 1")','drawing header keeps imported batch');
  await evaluate(`await review.newplan.start(review.api);document.querySelector('[data-opt=manual]').click();
    document.querySelector('[data-kind=cd]').dispatchEvent(new MouseEvent('click',{bubbles:true}));
    const batch=document.querySelector('.np-batch');batch.value=[...batch.options].find(o=>o.textContent==='DIS CD 0').value;batch.dispatchEvent(new Event('change'));`);
  await check('document.querySelector(".np-cal-text").textContent.includes("沿轨常数仍未知")&&document.querySelector(".np-cal-go").hidden','CD import leaves along-track constant unknown');
  // New page keeps route tests isolated from animation/session tests.
  await open();
  await evaluate('await review.newplan.start(review.api);await import(new URL("design.js",document.baseURI));document.querySelector("[data-motion=on]").click()');
  await until('document.querySelector("[data-opt=auto]").textContent.includes("自动认出")','read completed');
  await evaluate('window.bagStart=performance.now();document.getElementById("next").click()');
  await check('getComputedStyle(document.querySelector(".np")).getPropertyValue("--bag-file").trim()==="640ms" && getComputedStyle(document.querySelector(".np")).getPropertyValue("--bag-drop").trim()==="360ms"','first bag is one second even with system reduced motion');
  await until('document.documentElement.dataset.mode==="design"','first bag finishes');
  await check('performance.now()-bagStart>=950 && document.querySelector(".ws-title .work-bag + .pname") && document.querySelector(".work-bag title").textContent.includes("Saved in past works")','full first animation and bag icon');
  await evaluate('await review.newplan.start(review.api);window.bagStart=performance.now();document.getElementById("next").click()');
  await check('getComputedStyle(document.querySelector(".np")).getPropertyValue("--bag-file").trim()==="256ms"','repeat bag shortened');
  await until('document.documentElement.dataset.mode==="design"','repeat finishes');
  for(const event of ['enter','click','off']) {
    await evaluate('await review.newplan.start(review.api);document.querySelector("[data-motion=on]").click();window.bagStart=performance.now();document.getElementById("next").click()');
    await delay(50);
    await evaluate(event==='enter'?'dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true}))':event==='click'?'document.querySelector(".np-sheet").click()':'document.documentElement.dataset.motion="off"');
    await until('document.documentElement.dataset.mode==="design"',event+' skips bag');
    await check('performance.now()-bagStart<380','skip is immediate: '+event);
  }
  await evaluate('await review.newplan.start(review.api);document.documentElement.dataset.motion="off";window.bagStart=performance.now();document.getElementById("next").click()');
  await until('document.documentElement.dataset.mode==="design"','motion off finishes');
  await check('performance.now()-bagStart<250','motion off is instant');
  await check('reviewErrors.length===0','no browser errors: '+JSON.stringify(await evaluate('reviewErrors')));
  await open('no-presets');
  await check('document.getElementById("presetio-entry").hidden && !reviewCalls.some(c=>c.path==="/api/presets")','missing presets capability hides entry without request');
  await evaluate('review.api.heldDisc=()=>"";review.api.readDisc=async()=>({present:true,media:"dvd",kind:"DVD-ROM",mid:"UNKNOWN"});await review.newplan.start(review.api)');
  await until('document.querySelector(".np-disc-help").textContent.includes("盘库里还没有")','a new batch is said under the select');
  await check('document.querySelector("[data-opt=auto]").getAttribute("aria-checked")==="true" && !document.querySelector("[data-opt=auto]").disabled && document.querySelector("[data-opt=auto]").textContent.includes("DVD-R") && document.querySelector(".np-dial").dataset.open==="false"','a disc of a known kind in a new batch is still recognised (no contradiction with the line under it)');
  await check('!document.querySelector(".np-disc-help").textContent.includes("DVD-ROM")','the disc is named as the page names kinds, not by its drive profile');
  await evaluate('review.api.readDisc=async()=>({present:false});await review.newplan.start(review.api)');
  await until('document.querySelector(".np-dial").dataset.open==="true"','no disc: the dial slides in');
  await check('document.querySelector(".np-own").hidden','missing preset capability hides new-work links too');
  await check('document.querySelector("[data-opt=manual]").getAttribute("aria-checked")==="true" && document.querySelector("[data-opt=auto]").disabled','nothing to recognise: auto is greyed, manual ticked');
  // Narrow layout and English remain usable without changing the artwork.
  await cdp('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  await evaluate('document.getElementById("lang").click()');
  await check('document.querySelector(".np-batch").getBoundingClientRect().right<=innerWidth && document.querySelector(".np-choice").getBoundingClientRect().left>=0','mobile controls stay on paper');
  await check('reviewCalls.every(c=>c.path==="/api/presets")','only mocked preset requests, no device commands');
  console.log('PASS: library/new-work DOM, keyboard, routing, budgets, motion, capability gate; eight 1440×900 screenshots');
} finally {
  if(socket?.readyState===WebSocket.OPEN){await cdp('Browser.close').catch(()=>{});socket.close();}
  if(browser){const closed=new Promise(r=>browser.once('close',r));if(browser.exitCode===null){await Promise.race([closed,delay(2000)]);if(browser.exitCode===null){browser.kill();await Promise.race([closed,delay(5000)]);}}}
  assert.ok(resolve(dir).startsWith(resolve(tmpdir(), 'discprobe-review-')));
  await rm(dir,{recursive:true,force:true,maxRetries:8,retryDelay:250});
}
