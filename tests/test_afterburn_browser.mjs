// Real Disc Lab burn and HTTP persistence; a small ISO keeps the run bounded. No physical devices.
import assert from 'node:assert/strict';
import {tmpdir} from 'node:os';
import {existsSync,readFileSync,writeFileSync,mkdirSync,mkdtempSync,realpathSync,rmSync} from 'node:fs';
import {dirname,join,resolve} from 'node:path';
import {spawn,spawnSync} from 'node:child_process';
import {stopEdge,endProfileProcesses,PROFILE_RM} from './edge_cleanup.mjs';

const base=process.env.AFTERBURN_TEST_ROOT ?? join(tmpdir(),'discprobe-afterburn');mkdirSync(base,{recursive:true});
const dir=mkdtempSync(join(base,'browser-')), shots=join(base,'shots');mkdirSync(shots,{recursive:true});
const checkShots=process.env.CHECKBURN_SHOTS ?? shots;mkdirSync(checkShots,{recursive:true});
const edge=process.env.PASTWORKS_TEST_BROWSER ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
assert.ok(existsSync(edge));
const delay=ms=>new Promise(r=>setTimeout(r,ms));
let server,browser,socket,seq=0;const pending=new Map(), results=[];
function cdp(method,params={}){const id=++seq;const p=new Promise((resolve,reject)=>pending.set(id,{resolve,reject}));socket.send(JSON.stringify({id,method,params}));return p;}
async function evaluate(expression){const r=await cdp('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});assert.ok(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result.value;}
async function until(expression,message){const deadline=Date.now()+Number(process.env.BROWSER_WAIT_MS||60000);while(Date.now()<deadline){let ok=false;try{ok=await evaluate(expression);}catch{}if(ok)return;await delay(50);}throw Error(message+': '+JSON.stringify(await evaluate('({mode:document.documentElement.dataset.mode,errors:window.abErrors,text:document.body.innerText.slice(-3000)})')));}
async function check(expression,message){assert.ok(await evaluate(expression),message);results.push(message);}
async function shot(name, folder=shots){await evaluate('document.fonts.ready');await delay(150);const r=await cdp('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});writeFileSync(join(folder,name+'.png'),Buffer.from(r.data,'base64'));}
try{
  const fixture=resolve('tests/afterburn_lab_fixture.py');
  server=spawn(process.env.PYTHON ?? 'python',['-X','utf8','-B',fixture,join(dir,'lab')],{windowsHide:true,stdio:['ignore','pipe','pipe']});
  let output='';server.stdout.on('data',b=>output+=b);server.stderr.on('data',b=>output+=b);
  let ready;
  for(let i=0;i<300&&!ready;i++){try{ready=JSON.parse(readFileSync(join(dir,'lab','ready.json'),'utf8'));}catch{}if(!ready)await delay(100);}
  assert.ok(ready,output);
  const origin=`http://127.0.0.1:${ready.port}`;
  browser=spawn(edge,['--headless=new','--mute-audio','--disable-gpu','--disable-background-networking','--no-first-run','--no-default-browser-check',
    '--remote-debugging-port=0',`--user-data-dir=${join(dir,'profile')}`,'about:blank'],{windowsHide:true,stdio:'ignore'});
  let port;for(let i=0;i<100&&!port;i++){try{port=readFileSync(join(dir,'profile','DevToolsActivePort'),'utf8').split(/\r?\n/)[0];}catch{}if(!port)await delay(100);}
  assert.ok(port,'browser ready');
  const targets=await fetch(`http://127.0.0.1:${port}/json/list`).then(r=>r.json());
  socket=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  socket.onmessage=({data})=>{const m=JSON.parse(data),p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}};
  await cdp('Page.enable');
  await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await cdp('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
  await cdp('Page.addScriptToEvaluateOnNewDocument',{source:`localStorage.setItem('dp-lang','zh');window.abErrors=[];addEventListener('error',e=>abErrors.push(e.message));addEventListener('unhandledrejection',e=>abErrors.push(String(e.reason)));`});
  await cdp('Page.navigate',{url:origin+'/home/'});
  await until('document.querySelector(".lb-world")','home mounted');
  // Bootstrap the existing burn component with a tiny finished ISO. The real home API is private;
  // this adapter only supplies scene callbacks and the shipped HTTP client. Core jobs are genuine.
  await evaluate(`(async()=>{
    const backend=await import('./api.js'),burn=await import('./burn.js');
    window.abApi={backend,lang:()=>document.documentElement.lang==='en'?'en':'zh',reduce:true,
      $:id=>document.getElementById(id),meta:await fetch('rows.json').then(r=>r.json()),cam:document.querySelector('.cam'),burnerLayer:document.querySelector('.layer.burner'),
      focusDrive(){},placeDisc(v){this.burnerLayer.classList.toggle('has-disc',v)},setTray(v){this.burnerLayer.classList.toggle('open',v)},
      toLobby(){document.documentElement.dataset.mode='';document.getElementById('back').hidden=true},nextWhy(){}};
    const info=await backend.request('/api/iso?path=iso/review.iso');
    let speeds;for(let i=0;i<40&&!speeds;i++){try{speeds=await backend.request('/api/burn-speeds?drive=X%3A&media=dvd')}catch(e){if(e.status!==409)throw e;await new Promise(r=>setTimeout(r,100));}}
    if(!speeds)throw Error('virtual drive remained busy');
    const work=${JSON.stringify(ready.work)};
    burn.start(abApi,{media:'dvd',item:{name:'刻后流程 · Disc Lab'},iso:info,drive:{id:'X:',name:'Disc Lab X:',speeds:speeds.speeds_x},discIn:true,
      swap:async()=>{},back(){},done:()=>abApi.toLobby(),
      burn(onProgress,{speed}){let id; (async()=>{try{
        const request={action:'burn',drive:'X:',media:'dvd',args:{iso:'iso/review.iso',speed}};
        const token=await backend.request('/api/burn-token', request);
        await backend.job({...request,work,burn_token:token.token},e=>{
          if(e.type==='started')id=e.job;if(e.type==='progress')onProgress({progress:e.fraction,elapsed:e.elapsed_s,remaining:e.eta_s});
          if(e.type==='burn_result')onProgress({burnResult:e});});onProgress({status:'success',progress:1});
      }catch(e){onProgress({status:'failed',error:e.message});}})();return {cancel(){if(id)backend.cancel(id)}};}});
  })()`);
  await evaluate(`document.querySelector('.burn-consent input').click()`);
  await evaluate(`document.querySelector('.kit-slide-knob').focus()`);
  await cdp('Input.dispatchKeyEvent',{type:'keyDown',key:'End',code:'End',windowsVirtualKeyCode:35});await delay(1200);
  await cdp('Input.dispatchKeyEvent',{type:'keyUp',key:'End',code:'End',windowsVirtualKeyCode:35});
  await until(`document.querySelector('.burn-page[data-state="success"]') && document.getElementById('next-text').textContent.includes('结果怎么样')`,'virtual burn completed');
  await check(`document.getElementById('next-text').textContent.includes('结果怎么样')`,'finished burn offers post-burn review');
  await evaluate(`document.getElementById('next').click()`);
  await until(`document.documentElement.dataset.mode==='afterburn' && document.querySelector('.ab-disc').complete`,'review opened');
  await check(`document.querySelectorAll('[data-choice]').length===4`,'four result choices');
  const panel = `document.querySelector('.after-burn details[data-capability="checkburn"]')`;
  await check(`!!${panel} && !${panel}.open`, 'checklist starts closed');
  for (const lang of ['zh', 'en']) {
    if (lang === 'en') await evaluate(`document.getElementById('lang').click()`);
    for (const theme of ['paper', 'dark']) {
      await evaluate(`document.documentElement.dataset.theme=${JSON.stringify(theme)}`);
      await shot(`checkburn-entry-${theme}-${lang}`,checkShots);
      await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:1240,deviceScaleFactor:1,mobile:false});
      await evaluate(`${panel}.querySelector('summary').click()`);
      await until(`${panel}.querySelectorAll('dt').length===6`,'core returns all six checks');
      const status = lang === 'zh' ? '已排除' : 'Ruled out';
      await check(`${panel}.querySelector('dd strong').textContent===${JSON.stringify(status)}`,'saved read-back is marked matched');
      const article = await evaluate(`(async () => {
        const node = ${panel}.querySelector('.ab-learn');
        node.scrollIntoView({block:'center',behavior:'instant'});
        const page = await fetch(node.href);
        return {path: new URL(node.href).pathname,status: page.status,label: node.textContent};
      })()`);
      assert.deepEqual(article, {path:'/home/learn/how-disc-images-work' + (lang==='zh'?'.zh':'') + '.html',
        status:200,label:lang==='zh'?'光盘怎么变成图':'How a disc becomes a picture'});
      await shot(`learn-checkburn-${theme}-${lang}`,checkShots);
      await evaluate(`${panel}.querySelector('h2').scrollIntoView({block:'start',behavior:'instant'})`);
      const bounds = await evaluate(`(() => {
        const sheet = document.querySelector('.ab-sheet').getBoundingClientRect();
        return {top:sheet.top,bottom:sheet.bottom,first:${panel}.querySelector('h2').getBoundingClientRect().top,
          last:${panel}.querySelector('dd:last-child').getBoundingClientRect().bottom};
      })()`);
      assert.ok(bounds.first >= bounds.top - 1 && bounds.last <= bounds.bottom + 1, JSON.stringify(bounds));
      results.push('all six checks fit screenshot');
      await shot(`checkburn-list-${theme}-${lang}`,checkShots);
      await evaluate(`${panel}.querySelector('summary').click();document.querySelector('.ab-sheet').scrollTop=0`);
      await cdp('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
    }
  }
  await evaluate(`document.getElementById('lang').click();${panel}.querySelector('summary').click()`);
  await evaluate(`${panel}.querySelector('.burn-actions button').click()`);
  await until(`${panel}.textContent.includes('随机数据')`,'optional live check reads the current random ISO in the virtual drive');
  await evaluate(`${panel}.querySelector('dd button').click()`);
  await until(`document.querySelector('.startguide:not([hidden]) .sg-anim svg')`,'checklist opens the light diagram');
  await evaluate(`(async()=>{(await import('./guide.js')).close();${panel}.querySelector('summary').click();})()`);
  for(const choice of ['correct','invisible','distorted','gaps']){
    for(const theme of ['paper','dark']){
      await evaluate(`document.documentElement.dataset.theme=${JSON.stringify(theme)};document.querySelector('[data-choice="${choice}"]').click()`);
      await until(`!document.querySelector('[data-choice="${choice}"]').disabled && document.querySelector('[data-choice="${choice}"]').getAttribute('aria-pressed')==='true'`,'observation saved');
      await shot(choice+'-'+theme);
    }
    await check(`!!document.querySelector('.ab-branch')`,'branch '+choice+' has next actions');
    if(choice==='invisible'){
      await evaluate(`document.querySelector('.ab-branch button').click()`);
      await until(`!!document.querySelector('.sg-sheet:not([hidden])') || !!document.querySelector('#sg-title')`,'lighting guide opens');
      await check(`!!document.querySelector('.sg-anim svg')`,'lighting guide includes diagram');
      await evaluate(`(async()=>{(await import('./guide.js')).close()})()`);
    }
    if(choice==='distorted'){
      await evaluate(`document.querySelector('.ab-branch button').click()`);
      await until(`!!document.querySelector('.ab-measurement')`,'saved measurement opens');
      await check(`document.querySelector('.ab-measurement').textContent.includes('geo-X-20261115-010101')`,'measurement is the linked run');
    }
  }
  // Preview is safe to view: Next returns to this report, never another burn confirmation.
  await evaluate(`Array.from(document.querySelectorAll('.after-burn .burn-actions button')).find(b=>b.textContent.includes('本次预览')).click()`);
  await until(`document.documentElement.dataset.mode==='preview'`,'saved preview opened');
  await check(`document.getElementById('next-text').textContent.includes('返回刻录报告')`,'saved preview next returns to report');
  await evaluate(`document.getElementById('next').click()`);
  await until(`document.documentElement.dataset.mode==='afterburn'`,'return from preview');
  // A fresh navigation drops every module's memory. The real lobby reads the core's works.
  await cdp('Page.navigate',{url:origin+'/home/'});
  await until(`Array.from(document.querySelectorAll('#lobby button')).some(b=>b.textContent.includes('刻录报告和预览'))`,'reopened lobby has a report entry');
  await shot('reopened-entry');
  await evaluate(`Array.from(document.querySelectorAll('#lobby button')).find(b=>b.textContent.includes('刻录报告和预览')).click()`);
  await until(`document.documentElement.dataset.mode==='afterburn'`,'reopened review');
  await check(`document.querySelector('[data-choice="gaps"]').getAttribute('aria-pressed')==='true'`,'saved observation restored after reopening');
  await check(`document.querySelector('.burn-checks').textContent.includes('抽样')`,'read-back report restored');
  await evaluate(`document.getElementById('next').click();document.getElementById('lobby-open').click()`);
  await until(`!!document.querySelector('.pw-cell[data-id="${ready.work}"]')`,'works library opens');
  await evaluate(`document.querySelector('.pw-cell[data-id="${ready.work}"]').click()`);
  await until(`Array.from(document.querySelectorAll('.pw-act')).some(b=>b.textContent.includes('查看刻后结果'))`,'work detail has review entry');
  await evaluate(`Array.from(document.querySelectorAll('.pw-act')).find(b=>b.textContent.includes('查看刻后结果')).click()`);
  await until(`document.documentElement.dataset.mode==='afterburn'`,'review from work detail');
  await check(`document.querySelector('[data-choice="gaps"]').getAttribute('aria-pressed')==='true'`,'work detail restores its saved burn review');
  await evaluate(`document.getElementById('lang').click()`);
  await check(`document.querySelector('.after-burn h1').textContent==='How did it look?'`,'English review uses translated copy');
  await cdp('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  await shot('mobile-night');
  await check(`document.querySelector('.ab-sheet').getBoundingClientRect().right<=innerWidth`,'mobile sheet stays in viewport');
  await check(`abErrors.length===0`,'no uncaught browser errors after reopening');
  const state=await fetch(origin+'/api/works/'+ready.work+'/after-burn').then(r=>r.json());
  assert.equal(state.record.report.verification.differing,0);assert.equal(state.record.report.verification.unreadable,0);
  assert.ok(state.record.report.verification.ok>0);assert.equal(state.record.report.disc_state.disc.disc_status,'complete');
  writeFileSync(join(base,'browser-results.json'),JSON.stringify({checks:results.length,results,work:ready.work,dir,report:state.record.report},null,2));
  console.log(`PASS: ${results.length} Disc Lab/browser checks; ${shots}`);
}finally{
  await stopEdge(browser,socket);
  endProfileProcesses(join(dir,'profile'));
  if(server?.exitCode===null)spawnSync('taskkill',['/PID',String(server.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});
  if (dirname(realpathSync(dir)) === realpathSync(base)) {
    rmSync(dir,PROFILE_RM);
  }
}
