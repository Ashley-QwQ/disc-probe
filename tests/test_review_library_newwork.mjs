// Full home-page DOM on loopback with synthetic core responses. No product server or devices.
import {devToolsPortFile, launchBrowser, selectBrowser, stopBrowser} from './browser.mjs';
import {serveBrowserFixture} from './browser_fixtures.mjs';
import assert from 'node:assert/strict';
import {readFileSync, writeFileSync, mkdtempSync, mkdirSync} from 'node:fs';
import {rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {hasBatch, geoChoice} from '../discprobe/web/home/design/export-rules.mjs';

const home = new URL('../discprobe/web/home/', import.meta.url);
const index = readFileSync(new URL('index.html', home), 'utf8');
const manifest = JSON.parse(readFileSync(new URL('../gui.json', home), 'utf8'));
const edge = selectBrowser({legacy: ['KIT_TEST_BROWSER']});
const dir = mkdtempSync(join(tmpdir(), 'discprobe-review-'));
const shots = resolve(process.env.REVIEW_SHOTS_DIR || '.impeccable/review-fixes'); mkdirSync(shots, {recursive:true});
const discShots = resolve(process.env.DISC_FIELD_SHOTS_DIR || '.impeccable/disc-field'); mkdirSync(discShots, {recursive:true});
const ownShots = resolve(process.env.OWN_PARAMS_SHOTS_DIR || '.impeccable/own-params'); mkdirSync(ownShots, {recursive:true});
const communityFeed=JSON.parse(readFileSync(new URL('faxnews/community.json',home),'utf8'));
const bootstrap = `<base href="/home/"><script>
localStorage.setItem('dp-lang','zh');localStorage.setItem('dp-motion','off');localStorage.setItem('dp-sound','off');
window.reviewErrors=[];addEventListener('error',e=>reviewErrors.push(e.message));addEventListener('unhandledrejection',e=>reviewErrors.push(String(e.reason)));
window.reviewCalls=[];
const nativeFetch=window.fetch.bind(window);
window.fetch=async (path,opts)=>{
 const url=new URL(path,document.baseURI);
 if(url.pathname.includes('/api/')) {
   const payload=opts?.body?JSON.parse(opts.body):null;
   reviewCalls.push({path:String(path),method:opts?.method||'GET',payload});
   if(String(path)==='/api/community')return {ok:true,text:async()=>JSON.stringify({feed:${JSON.stringify(communityFeed)},date:${JSON.stringify(communityFeed.date)},count:${communityFeed.count},from:'bundled'})};
   if(String(path)==='/api/presets')return {ok:true,json:async()=>!payload?({version:1,presets:[]}):
     ({entries:window.reviewImportRows||[],written:payload.operation==='import'?(window.reviewImportRows||[]).map(r=>({index:r.index,path:'presets/'+r.preset.id+'.json'})):[],duplicates:[]})};
   throw Error('Unexpected core access: '+path);
 }
 if(url.origin!==location.origin)throw Error('No external network in this test: '+url);
 return nativeFetch(url,opts);
};
window.EventSource=class {addEventListener(){} close(){}};
window.reviewHandshake=async path=>({ok:true,json:async()=>path==='/gui.json'?${JSON.stringify(manifest)}:{api_version:'1.0',capabilities:${JSON.stringify([...manifest.required_capabilities,...manifest.optional_capabilities])}.filter(c=>!location.search.includes('no-presets')||c!=='presets-io')}});
</script>`;
let html = index.replace('<head>', '<head>'+bootstrap)
  .replace('await handshake();', 'await handshake(document, window.reviewHandshake, {protocol:"http:",search:""});');
const tail = html.lastIndexOf('</script>');
html = html.slice(0,tail) + '\nwindow.review={api,DATA,render,newplan:await import("./newplan.js")};\n' + html.slice(tail);
const server = await serveBrowserFixture(new Map([['/fixture', ['text/html; charset=utf-8', html]]]));
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
  writeFileSync(join(own==='disc'?discShots:own?ownShots:shots,name+'.png'),Buffer.from(data,'base64'));
}
async function open(extra='') {
  await cdp('Page.navigate',{url:server.origin+'/fixture?mock&'+extra});
  await until('!!window.review','home fixture ready');
}
try {
  browser=launchBrowser(edge, join(dir,'profile'), ['--mute-audio','--no-sandbox','--remote-debugging-port=0','about:blank'],{disableGpu: true, windowsHide:true,stdio:'ignore'});
  let port;
  for(let i=0;i<100&&!port;i++) {
    try {port=readFileSync(devToolsPortFile(browser),'utf8').split(/\r?\n/)[0];}catch(e){if(!['ENOENT','EBUSY','EPERM','EACCES'].includes(e.code))throw e;}
    if(!port)await delay(100);
  }
  assert.ok(port,'CDP endpoint ready');
  assert.ok(![8772,8795,8798,8812,8813,8841,8863].includes(Number(port)),'test uses an ephemeral port');
  const targets=await fetch(`http://127.0.0.1:${port}/json/list`).then(r=>r.json());
  socket=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  socket.onmessage=({data})=>{const msg=JSON.parse(data),cb=pending.get(msg.id);if(cb){pending.delete(msg.id);msg.error?cb.reject(Error(JSON.stringify(msg.error))):cb.resolve(msg.result);}};
  await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await cdp('Emulation.setFocusEmulationEnabled',{enabled:true});
  // Force the system preference off: explicit page motion-on must still animate.
  await cdp('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  await open();
  await evaluate('document.getElementById("library").click()');
  await until('document.querySelectorAll(".layer.solid .disc").length>=8','shelf loaded');
  await check('document.querySelectorAll(".kinds .kind").length===3 && !document.querySelector(".kinds [data-col=drive]") && document.querySelector(".tools [data-col=drive]")','kinds are separate from header drive entry');
  await check('getComputedStyle(document.querySelector(".kinds")).transform==="none" && document.getElementById("batch-position").textContent==="第 1 批，共 7 批"','horizontal kinds and readable count');
  await check('document.querySelector(".facts dd").id==="left" && getComputedStyle(document.getElementById("sectors")).fontFamily.includes("mono")','remaining first, sectors mono in details');
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
  await check('document.getElementById("name").textContent.includes("DVD‑RW") && !document.querySelector(".batch-copy-leaving")','system reduced motion keeps the caption still');
  for(const theme of ['paper','dark']) {
    await evaluate(`document.documentElement.dataset.theme=${JSON.stringify(theme)}`);
    await shot('library-'+theme);
  }
  await evaluate(`for(const kind of ['dvd','cd','bd'])review.DATA[kind].forEach((it,i)=>{if(!it.kind)it.id=kind+'-'+i});
    window.disc={present:true,media:'dvd',kind:'DVD-R Sequential',mid:'MCC 004 · AZO',sectors:2297888,blank:true};
    review.api.driveDisc=()=>disc;review.api.readDisc=async()=>({...disc});
    document.documentElement.dataset.motion='off';await review.newplan.start(review.api);`);
  await until('document.querySelector(".np-disc-help").textContent.includes("光驱里认出")','recognised drive');
  await check('!document.querySelector(".np-choice") && !document.querySelector(".np-dial").inert && getComputedStyle(document.querySelector(".np-dial")).visibility==="visible" && document.querySelector(".np-face-text").textContent==="DVD-R"','dial always available, starts from drive');
  const typeBatch=async name=>evaluate(`document.querySelector('.np-batch').value=${JSON.stringify(name)};document.querySelector('.np-batch').dispatchEvent(new Event('input'));`);
  const batchKey=async key=>evaluate(`document.querySelector('.np-batch').dispatchEvent(new KeyboardEvent('keydown',{key:${JSON.stringify(key)},bubbles:true,cancelable:true}));`);
  for(const theme of ['paper','dark']) {
    await evaluate(`document.documentElement.dataset.theme=${JSON.stringify(theme)};await review.newplan.start(review.api);`);
    await check('document.querySelector(".np-batch").value==="" && document.querySelector(".np-batch").placeholder==="Verbatim DVD-R 16x" && document.querySelectorAll(".np-tab").length===2','grey suggested field with Tab cap');
    await check('document.querySelector(".np-cal-text").textContent==="已标定 · 2026-11-07" && document.querySelector(".np-left").textContent==="还剩 37 / 50 张"','measured sentence and counts');
    await check('document.querySelector(".np-community").hidden','a batch DP has measured gets no community hint');
    await shot('recognised-library-'+theme,'disc');
    await evaluate('document.querySelector(".np-name").focus();document.querySelector(".np-batch").focus()');
    const popup = await evaluate(`(() => {
      const input = document.querySelector('.np-batch'), box = document.querySelector('.np-matches');
      const rows = [...box.children], batches = review.DATA.dvd.filter(it => it.kind !== 'new');
      return {value: input.value, open: input.getAttribute('aria-expanded'), count: batches.length,
        rows: rows.map(row => row.textContent), active: document.activeElement?.className, errors: reviewErrors};
    })()`);
    assert.ok(popup.value === '' && popup.open === 'true' && popup.rows.length === popup.count + 1 &&
      popup.rows[0].includes('已标定 · 2026-11-07') && popup.rows[1].includes('已标定 · 2026-11-02') &&
      popup.rows[2].includes('TDK') && popup.rows.at(-1) === '稍后再定',
      'focusing an empty combobox lists the whole DVD family, calibrated first with dates: '+JSON.stringify(popup));
    await batchKey('Tab');
    await check('document.querySelector(".np-batch").value==="Verbatim DVD-R 16x"','Tab accepts');
    await typeBatch('我的新批次');await batchKey('Escape');
    // a new batch never borrows a measured batch's geometry through a shared maker code
    await check(`const r=await import('./design/export-rules.mjs');const it=review.newplan.currentItem();
      const cat=[{id:'b-same-mid',mid:it.readMid||'RITEKF1',s:'good',geo:'results/geo-same/summary.json'}];
      return it.id.startsWith('new:') && !('mid' in it) && r.hasBatch(it) && r.geoChoice({item:it},cat,'results/geo-same/summary.json').source==='none';`,'new batch: own id, no mid, geoChoice none despite a same-MID measured batch');
    await check('document.querySelector(".np-cal-text").textContent==="这批还没有参数：可以先画；要刻之前标定一次，或者带上已有参数" && document.querySelector(".np-cal-go").textContent==="标定这批" && !document.querySelector(".np-own").hidden && document.querySelector(".np-library").hidden && document.querySelector(".np-disc-help").textContent.includes("MCC 004 · AZO")','new batch status, links and MID');
    await until('!document.querySelector(".np-community").hidden','community hint for an unmeasured batch');
    await check('((n)=>n.textContent.includes("同 MID") && !n.textContent.includes("容量相同") && n.textContent.includes("不是 DP 测的") && n.textContent.includes("这批盘还没确认") && n.querySelector("a").href.startsWith("https://github.com/"))(document.querySelector(".np-community"))','MID hint (not capacity) with provenance and source link');
    await shot('new-batch-typed-'+theme,'disc');
    await typeBatch('');
    await check('document.querySelector(".np-cal-text").textContent==="没选盘：画好后要刻时再选" && document.querySelector(".np-cal-go").hidden && document.querySelector(".np-library").hidden && document.querySelector(".np-batch").placeholder===""','empty field sentence and no batch');
    await shot('empty-field-'+theme,'disc');
    await typeBatch('rItEk');
    await check(`Array.from(document.querySelectorAll('.np-matches [role=option] > span'), row => row.textContent).join('|')
      === 'Ritek DVD+RW 4x|Maxell DVD-R 16x|Ritek DVD-R 8x|稍后再定'`,'case-insensitive name and MID filtering within the DVD family');
    await shot('suggestion-list-'+theme,'disc');
    await batchKey('ArrowDown');await batchKey('ArrowDown');await batchKey('Enter');
    await check('document.querySelector(".np-batch").value==="Maxell DVD-R 16x" && document.querySelector(".np-matches").hidden','arrows and Enter pick');
    await evaluate('document.querySelector(".np-batch-toggle").click()');
    await check('document.querySelector(".np-matches").textContent.includes("Verbatim DVD+R 16x")','arrow reopens the full list with a filled input');
    await batchKey('ArrowUp');await batchKey('Enter');
    await check('review.newplan.currentItem()===null && document.querySelector(".np-matches").hidden','keyboard can choose later and clear the selection');
    await evaluate(`document.querySelector('.np-batch').click();
      [...document.querySelector('.np-matches').children].find(row => row.firstChild.textContent === 'Verbatim DVD+R 16x').click();`);
    await check('document.querySelector(".np-face-text").textContent==="DVD+R" && document.querySelector(".np-batch").value==="Verbatim DVD+R 16x"','pick another DVD subtype through the list');
    await typeBatch('vErBaTiM');await evaluate('document.querySelector(".np-matches [role=option]").click()');
    await check('document.querySelector(".np-batch").value==="Verbatim DVD-R 16x"','click picks');
    await check('getComputedStyle(document.querySelector(".np-dial-clip")).position==="absolute" && document.querySelector(".np-dial").getBoundingClientRect().top>=document.querySelector(".np-sheet").getBoundingClientRect().top-2','dial hangs from sheet edge');
    await check('document.getElementById("next-text").textContent==="下一步：放进图片"','Next always adds a picture');
  }
  await evaluate('document.querySelector(".np-library").click()');
  await until('location.hash==="#/library" && document.documentElement.dataset.navigation==="ready" && document.documentElement.dataset.mode==="" && document.getElementById("name").textContent.includes("Verbatim")','batch link opens exact batch');
  await evaluate('document.getElementById("back").click()');
  // The form can be visible before the asynchronous browser Back has finished.
  await until('document.documentElement.dataset.mode==="newplan" && !document.querySelector(".np").hidden && location.hash==="#/newplan" && document.documentElement.dataset.navigation==="ready"','library Back returns to form');
  await evaluate('document.querySelector(".np-library").click()');
  await until('location.hash==="#/library" && document.documentElement.dataset.navigation==="ready" && document.documentElement.dataset.mode==="" && document.documentElement.dataset.home==="library" && !document.getElementById("next").disabled',
    'batch library is ready to choose');
  // Choose and confirm the actual library item in the same browser event turn.
  await check(`(()=>{const index=review.DATA.dvd.findIndex(row=>row.name==='TDK DVD-R 16x');
    if(index<0)return false;
    review.api.goTo('dvd',index);
    if(review.api.current().item!==review.DATA.dvd[index])return false;
    document.getElementById('next').click();return true;})()`,'TDK batch selected in library');
  await until('document.documentElement.dataset.mode==="newplan" && document.querySelector(".np-batch").value.includes("TDK")','library can return another chosen batch');
  await evaluate('document.querySelector(".np-batch").value="TDK DVD-R 16x";document.querySelector(".np-batch").dispatchEvent(new Event("input"));document.getElementById("next").click()');
  await until('document.documentElement.dataset.mode==="design"','an uncalibrated batch still goes on to drawing (calibration is a link, not a gate)');
  await evaluate(`await review.newplan.start(review.api);document.querySelector('.np-name').value='我的作品';
    window.reviewImportRows=['cd','dvd','dvd','dvd'].map((media,index)=>({index,media,valid:true,disabled:false,
      image_compatible:index!==3,issues:[],preset:{id:'own-'+index,displayName:'DIS '+media.toUpperCase()+' '+index,
        innerRadiusMm:25,outerRadiusMm:58,...(media==='cd'?{sectors:359849}:{totalSectors:2295104})}}));
    review.api.syncState=async()=>{for(const row of reviewImportRows){if(!review.DATA[row.media].some(it=>it.id==='preset:'+row.preset.id))
      review.DATA[row.media].push({id:'preset:'+row.preset.id,name:row.preset.displayName,imported:true,
        image_compatible:row.image_compatible,s:row.image_compatible?'imported':'unknown',
        geo:row.image_compatible?'presets/'+row.preset.id+'.json':null});}};`);
  await typeBatch('我的新批次'); await batchKey('Escape');
  await until('!document.querySelector(".np-own").hidden','numbers links available');
  await shot('newwork-link',true);
  await evaluate('document.querySelector(".np-import").click()');
  await until('document.querySelector(".presetio").dataset.state==="import"&&!document.querySelector(".presetio input[type=file]").disabled','new-work link opens import lever down');
  await evaluate('document.getElementById("back").click()');
  await check('document.documentElement.dataset.mode==="newplan"&&document.querySelector(".np-name").value==="我的作品"','Back restores form before import');
  await evaluate(`document.querySelector('.np-batch').value='';document.querySelector('.np-batch').dispatchEvent(new Event('input'));
    document.querySelector('.np-import').click();`);
  await until('!document.querySelector(".presetio input[type=file]").disabled','empty selection detour ready');
  await evaluate(`document.querySelector('.presetio').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));`);
  await until('document.documentElement.dataset.mode==="newplan" && document.querySelector(".np-batch").value===""',
    'Empty field survives closing without an import');
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
  await until('document.querySelector(".presetio-status").textContent.includes("已导入：4")','imports complete');
  await evaluate('document.getElementById("back").click()');
  await check('document.documentElement.dataset.mode==="newplan"&&document.querySelector(".np-batch").value==="DIS DVD 1"&&document.querySelector(".np-name").value==="我的作品"','first imported preset of current kind selected, name kept');
  await check('/^参数来自 DIS 预设“.+”：不是 DP 测的，没有实测范围（DIS 只给标称半径），这批盘还没确认$/.test(document.querySelector(".np-cal-text").textContent)&&document.querySelector(".np-cal-go").hidden','import has its own unmeasured status without calibration nag');
  await evaluate('document.querySelector(".np-batch").focus()');
  await check('!document.querySelector(".np-matches").hidden && document.querySelector(".np-matches").textContent.includes("DIS DVD 1") && !document.querySelector(".np-matches").textContent.includes("DIS DVD 3")','archive-only batch not offered as geometry');
  await batchKey('Escape');
  await shot('imported-selected',true);
  await evaluate('document.querySelector(".np-library").click();document.getElementById("back").click()');
  await check('document.querySelector(".np-batch").value==="DIS DVD 1"','imported selection survives library detour');
  await evaluate('document.getElementById("next").click()');
  await until('document.documentElement.dataset.mode==="design"','imported preset continues to drawing');
  await check('document.body.textContent.includes("DIS DVD 1")','drawing header keeps imported batch');
  await evaluate(`await review.newplan.start(review.api);
    document.querySelector('[data-kind=cd]').dispatchEvent(new MouseEvent('click',{bubbles:true}));
    const batch=document.querySelector('.np-batch');batch.value='DIS CD 0';batch.dispatchEvent(new Event('input'));`);
  await check('document.querySelector(".np-cal-text").textContent.includes("沿轨常数未知")&&document.querySelector(".np-cal-go").hidden','CD import leaves along-track constant unknown');
  // New page keeps route tests isolated from animation/session tests.
  await open();
  await evaluate('await review.newplan.start(review.api);await import(new URL("design.js",document.baseURI));document.querySelector("[data-motion=on]").click()');
  await until('document.querySelector(".np-disc-help").textContent.includes("光驱里认出")','read completed');
  await evaluate('window.bagStart=performance.now();document.getElementById("next").click()');
  await check('getComputedStyle(document.querySelector(".np")).getPropertyValue("--bag-file").trim()==="640ms" && getComputedStyle(document.querySelector(".np")).getPropertyValue("--bag-drop").trim()==="360ms"','first bag is one second even with system reduced motion');
  await until('document.documentElement.dataset.mode==="design"','first bag finishes');
  await check('performance.now()-bagStart>=950 && document.querySelector(".ws-title .work-bag + .pname") && document.querySelector(".work-bag title").textContent.includes("Saved in past works")','full first animation and bag icon');
  await until('document.querySelector(".np").hidden','design entrance has taken over the desk');
  await evaluate('await review.newplan.start(review.api);window.bagStart=performance.now();document.getElementById("next").click()');
  await check('getComputedStyle(document.querySelector(".np")).getPropertyValue("--bag-file").trim()==="256ms"','repeat bag shortened');
  await until('document.documentElement.dataset.mode==="design"','repeat finishes');
  await until('document.querySelector(".np").hidden','repeat design entrance complete');
  for(const event of ['enter','click','off']) {
    await evaluate('await review.newplan.start(review.api);document.querySelector("[data-motion=on]").click();window.bagStart=performance.now();document.getElementById("next").click()');
    await delay(50);
    await evaluate(event==='enter'?'dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true}))':event==='click'?'document.querySelector(".np-sheet").click()':'document.documentElement.dataset.motion="off"');
    await until('document.documentElement.dataset.mode==="design"',event+' skips bag');
    await check('performance.now()-bagStart<380','skip is immediate: '+event);
    await until('document.querySelector(".np").hidden','design handoff completes after skip: '+event);
  }
  await evaluate('await review.newplan.start(review.api);document.documentElement.dataset.motion="off";window.bagStart=performance.now();document.getElementById("next").click()');
  await until('document.documentElement.dataset.mode==="design"','motion off finishes');
  await check('performance.now()-bagStart<250','motion off is instant');
  await check('reviewErrors.length===0','no browser errors: '+JSON.stringify(await evaluate('reviewErrors')));
  await open('no-presets');
  await check('document.getElementById("presetio-entry").hidden && !reviewCalls.some(c=>c.path==="/api/presets")','missing presets capability hides entry without request');
  await evaluate('review.api.heldDisc=()=>"";review.api.readDisc=async()=>({present:true,media:"dvd",kind:"DVD-ROM",mid:"UNKNOWN"});await review.newplan.start(review.api)');
  await until('document.querySelector(".np-disc-help").textContent.includes("只读盘")','ROM disc explained');
  await check('!document.querySelector(".np-batch").placeholder.includes("UNKNOWN") && getComputedStyle(document.querySelector(".np-dial")).visibility==="visible"','ROM cannot suggest a batch; dial stays available');
  await evaluate(`localStorage.setItem('dp-disc-kind', '["dvd","+R"]');
    review.api.readDisc=async()=>({present:true,media:"dvd",kind:"DVD-R",mid:"UNKNOWN",blank:null,closed:null});
    await review.newplan.start(review.api);`);
  await until('document.querySelector(".np-disc-help").textContent.includes("没读出光驱里这张盘是不是空白的")','unknown blank status explained');
  await check('document.querySelector(".np-face-text").textContent==="DVD+R" && !document.querySelector(".np-batch").placeholder.includes("UNKNOWN")',
    'unknown blank status does not change the dial or recommend the loaded disc');
  await evaluate('review.api.readDisc=async()=>({present:true,media:"dvd",kind:"DVD-RAM",mid:"UNKNOWN",blank:true});await review.newplan.start(review.api)');
  await until('document.querySelector(".np-disc-help").textContent.includes("DVD-RAM")','blank unsupported profile displayed');
  await check('document.querySelector(".np-face-text").textContent==="DVD+R" && !document.querySelector(".np-batch").placeholder.includes("UNKNOWN")',
    'DVD-RAM does not match the DVD-R dial option');
  await evaluate('review.api.readDisc=async()=>({present:false,tray:"empty"});await review.newplan.start(review.api)');
  await until('!document.querySelector(".np-disc-help").textContent.includes("正在读")','read finished');
  await check('document.querySelector(".np-own").hidden && getComputedStyle(document.querySelector(".np-dial")).visibility==="visible"','missing capability hides parameter links; dial stays visible');
  // Narrow layout and English remain usable without changing the artwork.
  await cdp('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  await evaluate('document.getElementById("lang").click()');
  await check('document.querySelector(".np-batch").getBoundingClientRect().right<=innerWidth && document.querySelector(".np-batch").getBoundingClientRect().left>=0','mobile controls stay on paper');
  await check('reviewCalls.every(c=>c.path==="/api/presets" || c.path==="/api/community" && c.method==="GET")','only mocked preset and community reads, no device commands');
  console.log('PASS: library/new-work DOM, suggestions, keyboard, routing, parameters, motion, capability gate; eight disc-field 1440×900 screenshots');
} finally {
  await stopBrowser(browser,socket);
  await server.close();
  assert.ok(resolve(dir).startsWith(resolve(tmpdir(), 'discprobe-review-')));
  await rm(dir,{recursive:true,force:true,maxRetries:8,retryDelay:250});
}
