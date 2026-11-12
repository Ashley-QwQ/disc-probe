// DOM/event integration in headless Edge. File URLs only: no server, backend or drives.
// Synthetic pointer capture and a deterministic animation clock exercise the actual handlers.
import assert from 'node:assert/strict';
import { existsSync, readFileSync, mkdtempSync, writeFileSync } from 'node:fs';
import { readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawn } from 'node:child_process';

async function browserReport(edge, fixture, profile, size) {
  const deadline=Date.now()+30000;
  const browser=spawn(edge,['--headless=new','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check',
    '--allow-file-access-from-files','--remote-debugging-port=0',`--user-data-dir=${profile}`,`--window-size=${size}`,'about:blank'],
    {stdio:['ignore','ignore','pipe'],windowsHide:true});
  let stderr='',spawnError,ws,seq=0;
  const pending=new Map();
  browser.stderr.on('data',chunk=>{stderr=(stderr+chunk).slice(-8192);});
  const exited=new Promise(done=>{
    browser.once('exit',(code,signal)=>done({code,signal}));
    browser.once('error',error=>{spawnError=error;done({error});});
  });
  const pause=ms=>new Promise(done=>setTimeout(done,ms));
  const waitExit=async ms=>{
    let timer;
    try{return await Promise.race([exited,new Promise(done=>{timer=setTimeout(()=>done(null),ms);})]);}
    finally{clearTimeout(timer);}
  };
  const send=(method,params={},timeout=Math.max(1,Math.min(5000,deadline-Date.now())))=>new Promise((ok,fail)=>{
    const id=++seq,timer=setTimeout(()=>{pending.delete(id);fail(new Error('CDP timeout: '+method));},timeout);
    pending.set(id,message=>{clearTimeout(timer);message.error?fail(new Error(JSON.stringify(message.error))):ok(message.result);});
    ws.send(JSON.stringify({id,method,params}));
  });
  try {
    let port;
    while(Date.now()<deadline) {
      if(spawnError)throw spawnError;
      try {
        const [value,endpoint]=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).trim().split(/\r?\n/);
        if(/^\d+$/.test(value)&&endpoint?.startsWith('/devtools/browser/')){port=value;break;}
      }catch(error){if(!['ENOENT','EBUSY','EACCES','EPERM'].includes(error.code))throw error;}
      await pause(100);
    }
    assert.ok(port,'Headless browser did not start: '+stderr);
    const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`,{signal:AbortSignal.timeout(Math.max(1,Math.min(5000,deadline-Date.now())))})).json();
    const target=pages.find(page=>page.type==='page'&&page.url==='about:blank');
    assert.ok(target,'No fixture tab');
    ws=new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((ok,fail)=>{
      const timer=setTimeout(()=>fail(new Error('CDP connection timeout')),Math.max(1,Math.min(5000,deadline-Date.now())));
      ws.addEventListener('open',()=>{clearTimeout(timer);ok();},{once:true});
      ws.addEventListener('error',()=>{clearTimeout(timer);fail(new Error('CDP connection failed'));},{once:true});
    });
    ws.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){pending.get(message.id)?.(message);pending.delete(message.id);}});
    await send('Page.enable');
    await send('Page.bringToFront');
    await send('Page.navigate',{url:pathToFileURL(fixture).href});
    await send('Emulation.setVirtualTimePolicy',{policy:'pauseIfNetworkFetchesPending',budget:6000});
    while(Date.now()<deadline) {
      const result=await send('Runtime.evaluate',{expression:"document.getElementById('result')?.textContent",returnByValue:true});
      if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));
      const report=result.result?.value;
      if(report&&report!=='PENDING')return report;
      await pause(30);
    }
    throw new Error('UI kit did not finish within 30000 ms: '+stderr);
  }finally{
    // Close this profile through CDP: dump-dom can finish all assertions yet
    // leave Edge waiting during its own shutdown, causing spawnSync ETIMEDOUT.
    let closeError;
    if(ws?.readyState===WebSocket.OPEN&&browser.exitCode===null)try{
      await send('Emulation.setVirtualTimePolicy',{policy:'advance'},3000);
      await send('Page.navigate',{url:'about:blank'},3000);
      await send('Browser.close',{},3000);
    }catch(error){closeError=error;}
    ws?.close();
    const closed=await waitExit(Math.max(3000,deadline-Date.now()));
    if(!closed){browser.kill();await waitExit(3000);throw new Error('The UI kit browser did not close');}
    if(closed.error)throw closed.error;
    if(closeError&&closed.code!==0)throw closeError;
    assert.equal(closed.code,0,'UI kit browser exit: '+JSON.stringify(closed)+' '+stderr);
  }
}

const edge = process.env.KIT_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
if (!existsSync(edge)) {
  console.log('UI kit browser integration SKIPPED: set KIT_TEST_BROWSER to a Chromium executable');
} else {
  const dir = mkdtempSync(join(tmpdir(), 'discprobe-kit-'));
  const kit = new URL('../discprobe/web/home/kit/', import.meta.url);
  const html = `<!doctype html><html data-motion="on"><head><meta charset="utf-8">
    <link rel="stylesheet" href="${new URL('kit.css', kit)}">
    <style>:root{--ink:#1d1b18;--ink-2:#5d5850;--paper:#ebe7e0;--paper-2:#e4dfd7;--rule:#cfc9bf;--rule-strong:#a9a297;--copper:#a8693c;--font:system-ui;--mono:monospace}body{margin:24px}#slide{width:320px}iframe{width:100%;height:900px;border:0}</style>
    </head><body><div id="flip">62%</div><div id="bars"></div><div id="devices"></div><div id="slide"></div><button id="ring"><b>处理照片</b></button>
    <iframe id="preview" style="width:__PREVIEW_WIDTH__px" src="${new URL('kit-preview.html', kit)}"></iframe><pre id="result">PENDING</pre>
    <script type="module">
    import {flipNumber,flipWatch,flipValue} from '${new URL('flipnum.js', kit)}';
    import {statusBars} from '${new URL('statusbars.js', kit)}';
    import {deviceList} from '${new URL('devices.js', kit)}';
    import {slideConfirm} from '${new URL('slideconfirm.js', kit)}';
    import {ringButton} from '${new URL('ringbutton.js', kit)}';
    import {nextConfirm} from '${new URL('nextconfirm.js', kit)}';
    const check=(condition,message)=>{if(!condition)throw Error(message)};
    const $=id=>document.getElementById(id);
    const flush=async()=>{await Promise.resolve();await Promise.resolve();await Promise.resolve()};
    try {
      // The rolling test controls this preference; the preview still reads the real system setting.
      const nativeMatchMedia=window.matchMedia.bind(window);
      window.matchMedia=query=>query==='(prefers-reduced-motion: reduce)'?{matches:false,addEventListener(){},removeEventListener(){}}:nativeMatchMedia(query);
      const flip=flipNumber($('flip')); const first=$('flip').querySelector('.kit-flip-cell');
      flip.set('63%'); check($('flip').querySelector('.kit-flip-cell')===first,'unchanged digit DOM identity');
      check($('flip').querySelectorAll('.kit-flip-previous').length===1,'only one changed character rolls');
      flip.set('9%');const suffix=$('flip').querySelector('.kit-flip-cell:last-child');flip.set('10%');
      check($('flip').querySelector('.kit-flip-cell:last-child')===suffix,'suffix survives width change');
      document.documentElement.dataset.motion='off'; await flush(); flip.set('约 4 分钟');
      check($('flip').textContent==='约 4 分钟'&&!$('flip').children.length,'motion off is a plain text swap');
      document.documentElement.dataset.motion='on'; await flush();
      const watched=document.createElement('output');document.body.append(watched);watched.textContent='09';
      const watcher=flipWatch(watched);check(flipWatch(watched)===watcher,'watch mounts once');
      watched.textContent='10';await flush();check(flipValue(watched)==='10','ordinary textContent rolls');
      check(watched.querySelectorAll('.kit-flip-previous').length===2,'both digits carry');
      await new Promise(resolve=>setTimeout(resolve,280));await flush();
      check(flipValue(watched)==='10','animation cleanup never feeds back');
      watched.firstChild && (watched.textContent='11');await flush();
      document.documentElement.dataset.motion='off';await flush();
      watched.textContent='5 s';await flush();check(watched.textContent==='5 s'&&!watched.children.length,'watched reduced motion');
      document.documentElement.dataset.motion='on';await flush();check(flipValue(watched)==='5 s','motion toggles preserve value');
      watched.textContent='4 s';document.documentElement.dataset.motion='off';await flush();
      check(watched.textContent==='4 s','a motion toggle cannot overwrite a pending assignment');
      document.documentElement.dataset.motion='on';await flush();
      watcher.destroy();watched.textContent='plain';await flush();check(!watched.children.length,'watch cleanup');
      const next=document.createElement('button');next.textContent='Next';document.body.append(next);let burns=0;
      nextConfirm(next,{active:true,disabled:true,done:()=>burns++});
      check(next.hidden&&next.nextElementSibling.querySelector('.kit-slide-knob').getAttribute('aria-disabled')==='true','Next replaced with disabled slider');
      nextConfirm(next,{active:true,disabled:false,done:()=>burns++});
      next.nextElementSibling.querySelector('.kit-slide-knob').click();check(burns===0,'click never burns');
      nextConfirm(next);check(!next.hidden&&!document.querySelector('.next-confirm'),'normal Next restored');
      const bars=statusBars($('bars'),[{state:'ok',label:'正常',when:'2026-11-11'},{state:'needs',label:'复查',when:'2026-11-10'},{state:'bad',label:'未知',when:null}]);
      let buttons=$('bars').querySelectorAll('button'); check(buttons.length===3,'one bar per event');
      buttons[0].focus();check(!$('bars').querySelector('[role=tooltip]').hidden,'focus tooltip');
      check($('bars').querySelector('[role=tooltip]').textContent.includes('2026'),'tooltip date');
      buttons[0].dispatchEvent(new KeyboardEvent('keydown',{key:'End',bubbles:true}));check(document.activeElement===buttons[2],'End reaches last event');
      buttons[2].dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));check($('bars').querySelector('[role=tooltip]').hidden,'Escape hides tooltip');
      buttons[1].dispatchEvent(new PointerEvent('pointerenter'));check(!$('bars').querySelector('[role=tooltip]').hidden,'hover tooltip');
      const tooltip=$('bars').querySelector('[role=tooltip]');
      check(tooltip.getBoundingClientRect().bottom+12>=buttons[1].getBoundingClientRect().top,'tooltip hover bridge reaches the strip');
      buttons[1].dispatchEvent(new PointerEvent('pointerleave',{relatedTarget:tooltip}));
      check(!tooltip.hidden,'tooltip remains open when pointer enters its content');
      buttons[1].dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));check(tooltip.hidden,'Escape dismisses hovered tooltip');
      buttons[1].dispatchEvent(new PointerEvent('pointerleave'));bars.update([], {lang:'en'});
      check($('bars').textContent.includes('0 events, 0 need attention'),'status update and language');
      let resolve, reject, calls=0;
      const data=[{id:'here',name:'本机',kind:'computer',since:Date.now(),sent:0,thisDevice:true},{id:'other',name:'手机',kind:'phone',since:Date.now()-180000,sent:2}];
      const list=deviceList($('devices'),data,{onDisconnect:()=>{calls++;return new Promise((a,b)=>{resolve=a;reject=b})}});
      check($('devices').querySelectorAll('button').length===1,'current device has no disconnect');
      let disconnect=$('devices').querySelector('button');disconnect.focus();disconnect.click();
      check($('devices').querySelectorAll('li').length===2,'pending disconnect retains row');
      check(document.activeElement.getAttribute('aria-busy')==='true','pending disconnect keeps focus');
      $('devices').querySelector('button').click();check(calls===1,'pending action cannot duplicate');
      reject(Error('offline'));await flush();check($('devices').querySelector('[role=alert]'),'disconnect error is visible');
      check(document.activeElement.dataset.deviceId==='other','error keeps focus for retry');
      $('devices').querySelector('button').click();resolve();await flush();
      check($('devices').querySelectorAll('li').length===1,'successful disconnect removes row');
      check($('devices').contains(document.activeElement),'focus recovered after disconnect');
      list.update([], {lang:'en'});check($('devices').textContent.includes('No devices connected.'),'empty device state');
      const lifecycle=document.createElement('button');lifecycle.innerHTML='<span>Next</span>';document.body.append(lifecycle);
      const labelNode=lifecycle.firstChild;const badge=ringButton(lifecycle);badge.progress(null);badge.destroy();
      check(lifecycle.firstChild===labelNode&&!lifecycle.hasAttribute('aria-busy'),'ring teardown preserves label and state');
      check(ringButton(lifecycle)!==badge,'ring remount after teardown');
      const oldBold=$('ring').querySelector('b');const ring=ringButton($('ring'));
      check($('ring').querySelector('b')===oldBold,'original button label nodes preserved');
      ring.progress(1.5);check(document.getElementById($('ring').getAttribute('aria-describedby')).textContent==='进度 100%','clamped accessible progress description');
      ring.progress(null);check(document.getElementById($('ring').getAttribute('aria-describedby')).textContent==='正在处理，进度未知','indeterminate has no made-up value');
      ring.done();check($('ring').textContent.includes('已完成'),'done announced');ring.reset();
      check(!$('ring').hasAttribute('aria-busy')&&$('ring').querySelector('.kit-ring-badge').hidden,'reset restores busy state');
      check(ringButton($('ring'))===ring,'ring attachment is idempotent');
      const queue=new Map();let frameId=0;
      window.requestAnimationFrame=fn=>{queue.set(++frameId,fn);return frameId};window.cancelAnimationFrame=id=>queue.delete(id);
      const advance=ms=>{const batch=[...queue.values()];queue.clear();batch.forEach(fn=>fn(performance.now()+ms))};
      let confirms=0;const slide=slideConfirm($('slide'),{done:()=>confirms++});
      const knob=$('slide').querySelector('[role=slider]');knob.focus();
      const key=(type,key,extra={})=>knob.dispatchEvent(new KeyboardEvent(type,{key,bubbles:true,cancelable:true,...extra}));
      key('keydown','Enter');advance(2000);check(confirms===0,'Enter alone does not confirm');
      key('keydown','ArrowRight');advance(500);key('keyup','ArrowRight');advance(2000);check(confirms===0,'early keyboard release cancels');
      key('keydown','End');advance(1001);check(confirms===1,'one-second hold confirms');advance(2000);check(confirms===1,'callback exactly once');
      slide.reset();knob.focus();key('keydown','End');knob.blur();advance(2000);check(confirms===1,'blur cancels hold');
      knob.focus();key('keydown','End');slide.setDisabled(true);advance(2000);check(confirms===1,'disable cancels hold');
      check(knob.getAttribute('aria-disabled')==='true'&&knob.tabIndex===-1,'disabled semantics');
      slide.setDisabled(false);knob.focus();key('keydown','End');key('keydown','Escape');advance(2000);check(confirms===1,'Escape cancels hold');
      knob.focus();key('keydown','End');advance(1001);check(confirms===2,'reenabled control accepts a fresh keyboard hold');slide.reset();
      let captured=false;knob.setPointerCapture=()=>{captured=true};knob.hasPointerCapture=()=>captured;knob.releasePointerCapture=()=>{captured=false};
      const pointer=(type,x)=>knob.dispatchEvent(new PointerEvent(type,{pointerId:7,isPrimary:true,button:0,clientX:x,bubbles:true,cancelable:true}));
      pointer('pointerdown',20);pointer('pointermove',80);pointer('pointerup',80);check(confirms===2,'partial drag springs back');
      check(knob.getAttribute('aria-valuenow')==='0','partial drag reset');
      pointer('pointerdown',20);pointer('pointermove',1000);pointer('pointercancel',1000);check(confirms===2,'pointer cancellation does not confirm');
      pointer('pointerdown',20);pointer('pointermove',1000);pointer('pointerup',1000);check(confirms===3,'end drag confirms exactly once');
      pointer('pointerup',1000);check(confirms===3,'extra pointerup cannot confirm twice');
      slide.reset();$('slide').setAttribute('aria-disabled','true');await flush();knob.focus();key('keydown','End');advance(2000);check(confirms===3,'external disabled attribute respected');
      slide.destroy();flip.destroy();
      const preview=$('preview');if(preview.contentDocument.readyState!=='complete')await new Promise(resolve=>preview.addEventListener('load',resolve,{once:true}));
      const pdoc=preview.contentDocument;check(pdoc.querySelectorAll('.kit-preview-theme').length===2,'both themes mount');
      const sheets=pdoc.querySelectorAll('.kit-preview-theme');
      check(preview.contentWindow.getComputedStyle(sheets[0]).backgroundColor!==preview.contentWindow.getComputedStyle(sheets[1]).backgroundColor,'theme token isolation');
      const overflow=()=>check(pdoc.documentElement.scrollWidth<=preview.clientWidth+1,'preview has no horizontal page overflow');overflow();
      sheets[0].querySelector('[data-action=increase]').click();check(sheets[0].querySelector('[data-number=percent]').textContent.includes('63%'),'preview number control');
      sheets[0].querySelector('[data-action=status-needs]').click();check(sheets[0].querySelectorAll('.kit-status-event').length===13,'preview add status');
      sheets[0].querySelector('[data-action=device-clear]').click();check(sheets[0].querySelector('[data-devices]').textContent.includes('还没有设备连上'),'preview clear devices');
      sheets[0].querySelector('[data-action=device-add]').click();check(sheets[0].querySelectorAll('.kit-device-row').length===1,'preview add device');
      sheets[0].querySelector('[data-action=progress-wait]').click();check(sheets[0].querySelector('[data-ring]').dataset.kitProgress==='indeterminate','preview wait progress');
      sheets[0].querySelector('[data-action=progress-reset]').click();check(!sheets[0].querySelector('[data-ring]').dataset.kitProgress,'preview reset progress');
      pdoc.getElementById('language').click();check(pdoc.documentElement.lang==='en','preview English toggle');overflow();
      pdoc.documentElement.dataset.motion='on';pdoc.getElementById('motion').click();await flush();check(pdoc.documentElement.dataset.motion==='off','preview motion toggle');
      $('result').textContent='PASS: UI kit DOM, cancellation, focus and bilingual preview';
    } catch(error) { $('result').textContent='FAIL: '+error.stack; }
    </script></body></html>`;
  const fixture = join(dir, 'fixture.html');
  try {
    for (const size of ['1360,1000', '390,844']) {
      // Edge's outer headless window has a minimum width; the iframe sets the actual test viewport.
      writeFileSync(fixture, html.replace('__PREVIEW_WIDTH__', size.startsWith('390') ? '390' : '1280'));
      const report=await browserReport(edge,fixture,join(dir,`profile-${size}`),size);
      assert.match(report, /^PASS: UI kit/, `${size}: ${report}`);
      console.log(`UI kit browser integration passed (${size}; file URLs, synthetic events)`);
    }
    // Exact tokens are a requirement; the live index belongs to other concurrent jobs.
    const index = readFileSync(new URL('../discprobe/web/home/index.html', import.meta.url), 'utf8');
    const preview = readFileSync(new URL('kit-preview.html', kit), 'utf8');
    for (const selector of [':root', ':root[data-theme="dark"]']) {
      const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const block = index.match(new RegExp(`^  ${escaped} \\{[\\s\\S]*?^  \\}`, 'm'))?.[0];
      assert.ok(block && preview.includes(block), `Preview must copy the ${selector} token block`);
    }
  } finally {
    // Only the verified OS temporary directory created above is removed.
    assert.equal(dirname(resolve(dir)),resolve(tmpdir()));
    assert.ok(resolve(dir).startsWith(join(resolve(tmpdir()),'discprobe-kit-')));
    await rm(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
}
