// File-only browser integration with mocked API: no product server or drives.
import assert from 'node:assert/strict';
import {existsSync, readFileSync, writeFileSync, mkdtempSync, mkdirSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';

const browser = process.env.KIT_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
if (!existsSync(browser)) {
  throw Error('presetio browser requires Chromium; set KIT_TEST_BROWSER');
}
const dir = mkdtempSync(join(tmpdir(), 'discprobe-presetio-'));
const home = new URL('../discprobe/web/home/', import.meta.url);
const index = readFileSync(new URL('index.html', home), 'utf8');
const style = index.match(/<style>([\s\S]*?)<\/style>/)[1];
const metadata = JSON.parse(readFileSync(new URL('presetio/desk/desk.json', home), 'utf8'));
const screenshotDir = resolve('.impeccable/review'); mkdirSync(screenshotDir, {recursive: true});
const fixture = join(dir, 'sheet.html');
const html = `<!doctype html><html data-home="library" data-motion="off"><meta charset="utf-8"><base href="${home.href}">
<style>${style}</style><link rel="stylesheet" href="${new URL('presetio.css', home)}">
<body><button id="entry">预设导入导出 / Presets</button><pre id="result" hidden>PENDING</pre>
<script type="module">
import {init} from '${new URL('presetio.js', home)}';
const art = ${JSON.stringify(metadata)};
const params = new URL(location.href).searchParams;
const root = document.documentElement;
root.dataset.theme = params.get('theme') || 'paper';
const check=(x,m)=>{if(!x)throw Error(m)};
const near=(a,b,m)=>check(Math.abs(a-b)<.03,m+': '+a+' != '+b);
const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve()};
const waitFor=async(predicate,message)=>{for(let i=0;i<200;i++){if(predicate())return;await new Promise(r=>setTimeout(r,10))}throw Error(message)};
const calls=[], downloads=[];
const row={index:0,media:'cd',valid:true,disabled:false,status:'nominal',mid:null,
  preset:{id:'cd-80',displayName:'标准 CD · <script> literal',sectors:359849,innerRadiusMm:24.5,outerRadiusMm:56.8},
  issues:['L unknown; DIS has no along-track constant.','Nominal, not calibrated.'],
  issues_zh:['L 未知；DIS 没有沿轨常数。','标称值，未经标定。'],comparison:{max_angle_error_deg:.0005,max_radius_error_mm:.000000003}};
let failExport=false, reduce=false, preferenceChanged;
const nativeMatchMedia=window.matchMedia.bind(window);
window.matchMedia=query=>query==='(prefers-reduced-motion: reduce)'?{
  get matches(){return reduce},addEventListener(type,fn){preferenceChanged=fn}
}:nativeMatchMedia(query);
const api=async(url,opts)=>{
  check(url==='/api/presets','only the existing API route');
  const p=opts?.body?JSON.parse(opts.body):null;calls.push(p);
  if(failExport&&p?.operation==='export')return{ok:false,status:400,json:async()=>({error:'Mock export failed'})};
  const data=!p?{version:1,presets:[{path:'presets/cd.json',name:'CD · 保存的预设 / Saved preset'}]}:
    p.operation==='preview'?{entries:[row,{...row,index:1,valid:false,preset:{displayName:'无效参数 / Invalid values'},issues:['sectors must be positive'],issues_zh:['扇区数必须为正数'],comparison:null}]}:
    p.operation==='import'?{written:[{index:0,path:'presets/cd.json'}],duplicates:[]}:
    {preset:row.preset,installation:{path:'temporary DiscImageStudio/disc-presets.json',backup:'temporary backup.bak'}};
  return{ok:true,json:async()=>data};
};
try {
  const ui=await init(document.getElementById('entry'),api);check(ui,'mounted');
  const sheet=ui.sheet, $=s=>sheet.querySelector(s);
  const knob=$('[role=slider]'), stage=$('.presetio-stage');
  const compact=innerWidth<820||innerWidth/innerHeight<1.2;
  const k=Math.max(innerWidth/2560,innerHeight/1440);
  const y=el=>new DOMMatrix(getComputedStyle(el).transform).m42;
  const part=name=>$('[data-layer="'+name+'"]');
  const choose=name=>$(compact?'[data-tab="'+(name==='export'?-1:1)+'"]':'[data-move="'+(name==='export'?-1:1)+'"]').click();
  const key=key=>knob.dispatchEvent(new KeyboardEvent('keydown',{key,bubbles:true,cancelable:true}));
  const endState=name=>{
    check(sheet.dataset.state===name,'state '+name);
    check(sheet.dataset.playing==='false','settled '+name);
    if(!compact){
      near(y(part('bag')),name==='export'?1440:0,'bag '+name);
      near(y(part('sheets')),name==='import'?-1440:0,'sheets '+name);
      near(y(part('doc_paper')),name==='import'?0:-1440,'paper '+name);
      near(y(part('doc_envelope')),name==='export'?0:1440,'envelope '+name);
      near(y(part('knob')),name==='export'?-art.knob.travel_px:name==='import'?art.knob.travel_px:0,'knob '+name);
    }
    for(const mode of ['import','export']){
      near(Number(getComputedStyle($('[data-led="'+mode+'"]')).opacity),name===mode?1:0,'LED '+mode);
      check($('#presetio-'+mode).inert===(name!==mode),'inactive content inert '+mode);
    }
    check(knob.getAttribute('aria-valuetext').includes(name==='idle'?'Idle':name==='import'?'Import':'Export'),'slider accessible text');
  };
  const checkGeometry=()=>{
    check(sheet.dataset.compact===String(compact),'layout breakpoint');
    if(!compact){
      const box=stage.getBoundingClientRect();
      near(new DOMMatrix(getComputedStyle(stage).transform).a,k,'cover scale');
      near(box.width,2560*k,'scene width');near(box.height,1440*k,'scene height');
      near(box.x,(innerWidth-box.width)/2,'centred x');near(box.y,(innerHeight-box.height)/2,'centred y');
    }
    for(const [mode,rect] of [['import',art.doc_paper_text_rect_px],['export',art.doc_envelope_text_rect_px]]){
      const content=$('#presetio-'+mode);
      near(parseFloat(content.style.left),rect[0],'text left '+mode);near(parseFloat(content.style.top),rect[1],'text top '+mode);
      near(parseFloat(content.style.width),rect[2]-rect[0],'text width '+mode);near(parseFloat(content.style.height),rect[3]-rect[1],'text height '+mode);
    }
    near(parseFloat(knob.style.left)+parseFloat(knob.style.width)/2,art.knob.centre_px[0],'knob centre x');
    near(parseFloat(knob.style.top)+parseFloat(knob.style.height)/2,art.knob.centre_px[1],'knob centre y');
    for(const [name,led] of Object.entries(art.leds)){
      const el=$('[data-led="'+name+'"]');
      near(parseFloat(el.style.left)+parseFloat(el.style.width)/2,led.centre_px[0],'LED x '+name);
      near(parseFloat(el.style.top)+parseFloat(el.style.height)/2,led.centre_px[1],'LED y '+name);
      near(parseFloat($('[data-move="'+(name==='export'?-1:1)+'"]').style.top),led.centre_px[1],'writing height');
    }
  };
  document.getElementById('entry').click();
  await waitFor(()=>!$('input[type=file]').disabled,'sheet ready');
  checkGeometry();endState(compact?'import':'idle');
  check(getComputedStyle($('[data-import]')).color!==getComputedStyle($('[data-import]')).backgroundColor,'disabled import label stays legible');
  if(params.get('exercise')==='yes'){
    if(!compact){
      key('ArrowUp');endState('export');key('ArrowDown');endState('idle');key('ArrowDown');endState('import');
      key('ArrowUp');endState('idle');key('ArrowUp');key('ArrowUp');endState('export');key('ArrowDown');
      // Synthetic pointers cannot own native capture. Verify the capture protocol while
      // running the real handlers, as in the other file-only browser tests.
      let captured=null,captures=0;
      knob.setPointerCapture=id=>{captured=id;captures++};knob.hasPointerCapture=id=>captured===id;
      knob.releasePointerCapture=id=>{check(captured===id,'release captured pointer');captured=null};
      const pointer=(type,clientY,id=7)=>knob.dispatchEvent(new PointerEvent(type,{pointerId:id,button:0,clientX:999,clientY,bubbles:true,cancelable:true}));
      pointer('pointerdown',300);pointer('pointermove',300-art.knob.travel_px*k*.55);
      near(y(part('knob')),-art.knob.travel_px*.55,'drag follows scaled y only');
      pointer('pointerup',300);endState('export');check(captures===1&&captured===null,'capture and release');
      key('ArrowDown');pointer('pointerdown',300);pointer('pointermove',300-art.knob.travel_px*k*.2);pointer('pointerup',300);endState('idle');
      pointer('pointerdown',300);pointer('pointermove',-9000);near(y(part('knob')),-art.knob.travel_px,'clamped up');
      pointer('pointercancel',-9000);endState('idle');
      pointer('pointerdown',300);pointer('pointermove',9000);near(y(part('knob')),art.knob.travel_px,'clamped down');
      pointer('lostpointercapture',9000);endState('idle');
      // Inspect real WAAPI timings with a controlled animation clock; no wall-clock sleeps.
      root.dataset.motion='on';await flush();choose('export');
      let animations=sheet.getAnimations({subtree:true});check(animations.length>=6,'motion uses WAAPI');
      const animationFor=el=>animations.find(a=>a.effect.target===el);
      near(animationFor(part('bag')).effect.getTiming().duration,520,'tray flight duration');
      near(animationFor(part('bag')).effect.getTiming().delay,220,'tray starts after snap');
      near(animationFor(part('doc_envelope')).effect.getTiming().delay,360,'document starts 140ms later');
      near(animationFor(part('doc_envelope')).effect.getTiming().duration,760,'document flight duration');
      near(animationFor($('#presetio-export')).effect.getTiming().delay,1120,'content waits for landing');
      near(animationFor($('#presetio-export')).effect.getTiming().duration,180,'content fade duration');
      check(animationFor($('[data-art=doc_envelope_shadow]')).effect.getKeyframes()[0].transform.includes('-18px'),'shadow lifted in flight');
      for(const a of animations){a.pause();a.currentTime=300}
      check(y(part('bag'))>0,'tray moves before document');near(y(part('doc_envelope')),1440,'document still waiting');
      check(Number(getComputedStyle($('[data-led=export]')).opacity)>0,'LED fades after knob arrives');
      let finished=0;for(const a of animations){const native=a.finish.bind(a);a.finish=()=>{finished++;native()}}
      choose('import');check(finished===animations.length,'new request finishes every previous animation');
      animations=sheet.getAnimations({subtree:true});
      const outgoing=animations.find(a=>a.effect.target===part('doc_envelope'));
      const incoming=animations.find(a=>a.effect.target===part('doc_paper'));
      check(outgoing&&incoming&&incoming.effect.getTiming().delay>outgoing.effect.getTiming().delay+outgoing.effect.getTiming().duration,'cross-mode routes through idle');
      near(animations.find(a=>a.effect.target===part('bag')).effect.getTiming().delay,780,'reverse document precedes returning bag');
      check(outgoing.effect.getTiming().easing==='cubic-bezier(0.7, 0, 0.84, 0)','document reverses landing curve');
      check(animations.find(a=>a.effect.target===part('bag')).effect.getTiming().easing==='cubic-bezier(0.2, 0.8, 0.45, 1)','source reverses acceleration curve');
      for(const a of animations)a.finish();await flush();endState('import');
      key('ArrowUp');for(const a of sheet.getAnimations({subtree:true}))a.finish();await flush();endState('idle');
      // The snap starts exactly where a small drag was released.
      pointer('pointerdown',300);pointer('pointermove',300+art.knob.travel_px*k*.2);pointer('pointerup',300);
      animations=sheet.getAnimations({subtree:true});near(new DOMMatrix(animations[0].effect.getKeyframes()[0].transform).m42,art.knob.travel_px*.2,'snap starts at release point');
      for(const a of animations)a.finish();await flush();endState('idle');
      choose('export');reduce=true;preferenceChanged();endState('export');check(!sheet.getAnimations({subtree:true}).length,'reduced motion finishes flight');
      choose('import');endState('import');reduce=false;
      choose('export');root.dataset.motion='off';await flush();endState('export');check(!sheet.getAnimations({subtree:true}).length,'motion off finishes flight');
      key('ArrowDown');endState('idle');choose('import');endState('import');
    }else{
      const tabs=$('.presetio-tabs');check(getComputedStyle(tabs).display==='flex','compact tabs visible');
      choose('export');endState('export');
      tabs.dispatchEvent(new KeyboardEvent('keydown',{key:'Home',bubbles:true,cancelable:true}));endState('import');
      check(document.activeElement===$('[data-tab="1"]'),'tab keyboard focus');
      check($('#presetio-import').getAttribute('role')==='tabpanel','tab panel semantics');
    }
    // Import from its paper: drop, media re-preview, valid selection and literal untrusted text.
    choose('import');
    const transfer=new DataTransfer();transfer.items.add(new File(['{}'],'中文 💿.json',{type:'application/json'}));
    $('.presetio-drop').dispatchEvent(new DragEvent('drop',{dataTransfer:transfer,bubbles:true,cancelable:true}));
    await waitFor(()=>sheet.querySelectorAll('input[type=checkbox]').length===2&&!$('[data-media]').disabled,'drop preview ready');
    const media=$('[data-media]');media.value='cd';media.dispatchEvent(new Event('change'));
    await waitFor(()=>calls.some(p=>p?.operation==='preview'&&p.media==='cd'&&p.filename==='中文 💿.json')&&!media.disabled,'media re-preview');
    const boxes=sheet.querySelectorAll('input[type=checkbox]');
    check(boxes[0].checked&&boxes[1].disabled,'valid and refused selections');
    check($('strong').textContent.includes('<script>')&&!$('script'),'untrusted name remains literal text');
    if(!compact)check($('#presetio-import').scrollHeight>$('#presetio-import').clientHeight,'long preview scrolls inside text rect');
    $('[data-import]').scrollIntoView({block:'nearest'});$('[data-import]').click();
    await waitFor(()=>$('.presetio-status').textContent.includes('Imported: 1')&&!media.disabled,'import finishes');
    check(calls.some(p=>p?.operation==='import'&&p.selected.join()==='0'),'only valid selected row imported');
    boxes[0].checked=false;boxes[0].dispatchEvent(new Event('change'));check($('[data-import]').disabled,'empty selection disabled');
    boxes[0].checked=true;boxes[0].dispatchEvent(new Event('change'));
    // Export from the envelope, including error recovery and the actual download contents.
    choose('export');check($('#presetio-export').contains($('.presetio-status')),'status follows the active document');
    $('[data-install]').click();await waitFor(()=>$('.presetio-status').textContent.includes('backup.bak')&&!$('[data-install]').disabled,'install backup feedback');
    check(calls.some(p=>p?.operation==='export'&&p.install===true),'install delegates to the API');
    failExport=true;$('[data-install]').click();await waitFor(()=>$('.presetio-status').dataset.error==='true'&&!$('[data-install]').disabled,'export failure recovers controls');
    failExport=false;
    const nativeClick=HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click=function(){downloads.push({href:this.href,name:this.download})};
    $('[data-save]').click();await waitFor(()=>downloads.length===1&&!$('[data-save]').disabled,'save finishes');
    HTMLAnchorElement.prototype.click=nativeClick;
    check(downloads[0].name==='dis-preset.json','download filename');
    const saved=await(await fetch(downloads[0].href)).json();check(saved.id===row.preset.id,'download contains exported preset');
    check(calls.some(p=>p?.operation==='export'&&p.install===false),'save delegates without install');
    choose('import');check(boxes[0].checked&&$('#presetio-import').contains($('.presetio-status')),'selection and status survive switching');
    ui.close();check(sheet.hidden&&document.activeElement.id==='entry','close restores opener focus');
    document.getElementById('entry').click();await waitFor(()=>!$('input[type=file]').disabled,'reopen ready');endState(compact?'import':'idle');
    sheet.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));check(sheet.hidden,'Escape closes');
    document.getElementById('entry').click();await waitFor(()=>!$('input[type=file]').disabled,'second reopen ready');
    // Resize the real iframe window; cover scale and compact mode recompute together.
    const frame=window.frameElement;
    const originalWidth=frame.style.width;
    // Flush layout and deliver resize explicitly: virtual time can defer native resize events.
    frame.style.width=compact?'1440px':'390px';frame.getBoundingClientRect();window.dispatchEvent(new Event('resize'));
    await waitFor(()=>sheet.dataset.compact===String(!compact),'resize changes layout');
    frame.style.width=originalWidth;frame.getBoundingClientRect();window.dispatchEvent(new Event('resize'));
    await waitFor(()=>sheet.dataset.compact===String(compact),'resize restores layout');checkGeometry();
    // Theme changes repaint every layer with no stale/missing tray URLs.
    const theme=root.dataset.theme;root.dataset.theme=theme==='dark'?'paper':'dark';await flush();
    check([...sheet.querySelectorAll('[data-art]')].every(img=>img.src.endsWith('_'+root.dataset.theme+'.webp')),'live theme updates all layers');
    root.dataset.theme=theme;await flush();
  }
  const final=params.get('state')||'idle';
  if(final==='idle'&&!compact){ui.close();document.getElementById('entry').click();await waitFor(()=>!$('input[type=file]').disabled,'final idle')}
  else choose(final==='export'?'export':'import');
  endState(compact&&final==='idle'?'import':final);
  // Review captures use fresh, scroll-reset documents and decoded artwork.
  for(const el of Object.values({import:$('#presetio-import'),export:$('#presetio-export')}))el.scrollTop=0;
  sheet.scrollTop=0;
  await waitFor(()=>[...sheet.querySelectorAll('[data-art]')].every(img=>img.complete&&img.naturalWidth),'all desk assets loaded');
  check([...sheet.querySelectorAll('[data-art]')].every(img=>img.naturalWidth===2560&&img.naturalHeight===1440),'all desk assets load');
  if(root.dataset.theme==='dark'){
    const luminance=rgb=>{
      const c=rgb.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);
      return c[0]*.2126+c[1]*.7152+c[2]*.0722;
    };
    const canvas=document.createElement('canvas'),context=canvas.getContext('2d',{willReadFrequently:true});
    let compactPaper;
    if(compact){
      compactPaper=new Image();compactPaper.src=new URL('newplan/paper_dark.webp',document.baseURI).href;
      await waitFor(()=>compactPaper.complete&&compactPaper.naturalWidth,'compact paper loaded');
    }
    for(const mode of ['import','export']){
      const image=compact?compactPaper:$('[data-art="doc_'+(mode==='import'?'paper':'envelope')+'"]');
      const bounds=compact?[120,120,image.naturalWidth-120,image.naturalHeight-120]:mode==='import'?art.doc_paper_text_rect_px:art.doc_envelope_text_rect_px;
      const [left,top,right,bottom]=bounds.map(Math.round);canvas.width=right-left;canvas.height=bottom-top;
      context.drawImage(image,left,top,canvas.width,canvas.height,0,0,canvas.width,canvas.height);
      const pixels=context.getImageData(0,0,canvas.width,canvas.height).data;
      let brightest=0;
      for(let i=0;i<pixels.length;i+=4)brightest=Math.max(brightest,luminance([pixels[i],pixels[i+1],pixels[i+2]]));
      const content=$('#presetio-'+mode);
      for(const text of [content,content.querySelector('label'),content.querySelector('h3 small')]){
        const ink=getComputedStyle(text).color.match(/[\\d.]+/g).slice(0,3).map(Number);
        const ratio=(luminance(ink)+.05)/(brightest+.05);
        check(ratio>=4.5,'dark '+mode+' paper contrast '+ratio);
      }
    }
  }
  check(sheet.scrollWidth<=sheet.clientWidth+1,'no horizontal overflow');
  document.getElementById('result').textContent='PASS: presetio browser '+innerWidth+'x'+innerHeight+' '+final+' '+root.dataset.theme;
}catch(e){document.getElementById('result').textContent='FAIL: '+e.stack}
<\/script></body></html>`;
writeFileSync(fixture, html);
try {
  const cases=[];
  for(const theme of ['paper','dark'])for(const state of ['idle','export','import'])
    cases.push({width:1440,height:900,theme,state,exercise:theme==='paper'&&state==='idle'});
  cases.push({width:1920,height:1080,theme:'paper',state:'idle',exercise:true});
  cases.push({width:390,height:900,theme:'paper',state:'import',exercise:true});
  cases.push({width:390,height:900,theme:'dark',state:'export',exercise:true});
  cases.push({width:900,height:1000,theme:'paper',state:'import',exercise:true});
  for(const [i,c] of cases.entries()){
    const url=new URL(pathToFileURL(fixture));
    for(const [key,value] of Object.entries(c))url.searchParams.set(key,key==='exercise'?(value?'yes':'no'):value);
    const wrapper=join(dir,'view-'+i+'.html');
    // A fixed-size iframe gives an exact CSS viewport, including mobile Chromium
    // windows whose top-level width has a larger minimum.
    writeFileSync(wrapper,'<!doctype html><html><meta charset="utf-8"><style>html,body{margin:0;overflow:hidden}iframe{display:block;border:0}</style><body><iframe style="width:'+c.width+'px;height:'+c.height+'px" src="'+url.href+'"></iframe><pre id="result" hidden>PENDING</pre><script>setInterval(()=>{const r=document.querySelector("iframe").contentDocument?.getElementById("result");if(r)document.getElementById("result").textContent=r.textContent},20)<\/script></body></html>');
    const screenshot=join(screenshotDir,'desk-'+c.state+'-'+c.theme+'-'+c.width+'.png');
    const result=spawnSync(browser,['--headless=new','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check',
      '--allow-file-access-from-files','--user-data-dir='+join(dir,'profile-'+i),'--window-size='+Math.max(500,c.width)+','+c.height,
      '--force-device-scale-factor=1','--hide-scrollbars','--virtual-time-budget=6000','--dump-dom','--screenshot='+screenshot,pathToFileURL(wrapper).href],
      {encoding:'utf8',timeout:30000,maxBuffer:4*1024*1024,windowsHide:true});
    assert.ifError(result.error);
    const report=result.stdout.match(/<pre id="result"[^>]*>([\s\S]*?)<\/pre>/)?.[1];
    assert.match(report||result.stderr,/^PASS: presetio browser/);
    console.log(report+' (mock API, file URL)');
  }
}finally{
  const target=resolve(dir),tempRoot=resolve(tmpdir());
  assert.equal(resolve(target,'..'),tempRoot);assert.ok(target.startsWith(join(tempRoot,'discprobe-presetio-')));
  rmSync(target,{recursive:true,force:true,maxRetries:5,retryDelay:200});
}
