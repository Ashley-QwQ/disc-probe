// Offline Edge evidence for A2. All artifacts/profiles stay outside the checkout.
// No application backend or optical device is used by this fixture.
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {existsSync, readFileSync, writeFileSync, mkdirSync, mkdtempSync} from 'node:fs';
import {rm} from 'node:fs/promises';
import {join, resolve, sep} from 'node:path';

const root = resolve(import.meta.dirname, '..');
const out = process.env.BRAND_MIXED_OUTPUT || 'D:/dp-dev/tmp/brand/mixed';
mkdirSync(out, {recursive:true});
const profile = mkdtempSync(join(out, 'edge-'));
const edge = process.env.EDGE || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const before = readFileSync(join(root, 'tests/fixtures/title-fonts-before.css'), 'utf8');
const titles = ['新作品', '光盘刻录', '刻录 DVD-R 16x', 'Disc Probe 盘库', 'BD 校准 2026', 'DISC-PROBE 1201'];
// Use actual title sizes/widths plus normal and fixed line heights. Main report
// uses 48px/800/118%/normal so metric changes cannot hide in a fixed line box.
const roles = [
  {id:'desktop', size:48, stretch:118, line:'normal', width:1340, height:900},
  {id:'phone', size:26, stretch:118, line:'34px', width:390, height:800},
  {id:'wide', size:34, stretch:125, line:'1', width:1000, height:800},
  {id:'normal-width', size:32, stretch:100, line:'1.08', width:1000, height:800},
];
const html = role => `<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<style>
@font-face {font-family:Archivo;src:url(/fonts/Archivo-VF-latin.woff2);font-weight:100 900;font-stretch:62% 125%;font-display:swap}
body {font-family:Archivo,"Microsoft YaHei UI",system-ui,sans-serif;margin:24px}
h1 {font-size:${role.size}px;font-weight:800;font-stretch:${role.stretch}%;line-height:${role.line};margin:16px 0;white-space:nowrap;width:max-content}
.baseline {display:inline-block;width:0;height:0;padding:0;margin:0;vertical-align:baseline}
</style><link rel="stylesheet" href="/fonts/titles.css">
<p>正文 Body 123 · ${role.id} · 800 / ${role.stretch}% / ${role.size}px / ${role.line}</p>
${titles.map((text,i) => `<h1 id="t${i}">${(text.match(/[\p{Script=Han}]+|[^\p{Script=Han}]+/gu)||[]).map((run,j)=>`<span class="run" data-script="${/\p{Script=Han}/u.test(run)?'han':'latin'}" id="r${i}-${j}">${run}<i class="baseline"></i></span>`).join('')}</h1>`).join('')}
<p id="body-check">正文保持原有字体、颜色和排版。</p></html>`;

let state = 'formal', role = roles[0];
const server = createServer((req,res)=>{
  const path = new URL(req.url,'http://localhost').pathname;
  res.setHeader('Cache-Control','no-store');
  if(path === '/') {res.setHeader('Content-Type','text/html;charset=utf-8');res.end(html(role));return;}
  if(path === '/fonts/titles.css') {
    res.setHeader('Content-Type','text/css;charset=utf-8');
    res.end(state.startsWith('before') ? before : readFileSync(join(root,'discprobe/web/fonts/titles.css'))); return;
  }
  // Exact allowlist: no directory traversal, repository scan, or backend API.
  if(['/fonts/Archivo-VF-latin.woff2','/fonts/SourceHanSansSC-Heavy-subset.woff2'].includes(path)) {
    res.setHeader('Content-Type','font/woff2');res.end(readFileSync(join(root,'discprobe/web',path)));return;
  }
  res.writeHead(404);res.end();
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const origin=`http://127.0.0.1:${server.address().port}`;
const child=spawn(edge,['--headless=new','--remote-debugging-port=0',`--user-data-dir=${profile}`,
  '--disable-gpu','--disable-background-networking','--no-first-run','--hide-scrollbars','about:blank'],
  {stdio:'ignore',windowsHide:true});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let ws,seq=0;
const pending=new Map(),evidence=[],failures=[];
const send=(method,params={})=>new Promise((resolve,reject)=>{
  const id=++seq;
  const timer=setTimeout(()=>{pending.delete(id);reject(Error(`CDP timeout: ${method}`));},20000);
  pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));
});
async function evaluate(expression) {
  const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
  assert.ok(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));return result.result.value;
}
async function fontsFor(selector) {
  const {root}=await send('DOM.getDocument');
  const {nodeId}=await send('DOM.querySelector',{nodeId:root.nodeId,selector});
  return (await send('CSS.getPlatformFontsForNode',{nodeId})).fonts;
}
try {
  for(let i=0;i<100&&!existsSync(join(profile,'DevToolsActivePort'));i++)await sleep(100);
  const port=readFileSync(join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];
  const tabs=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((r,j)=>{ws.addEventListener('open',r,{once:true});ws.addEventListener('error',j,{once:true});});
  ws.addEventListener('message',e=>{
    const m=JSON.parse(e.data);
    if(m.method==='Network.loadingFailed')failures.push({state,role:role.id,...m.params});
    const p=pending.get(m.id);if(!p)return;clearTimeout(p.timer);pending.delete(m.id);
    m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);
  });
  for(const method of ['Runtime.enable','DOM.enable','CSS.enable','Network.enable'])await send(method);
  await send('Network.setCacheDisabled',{cacheDisabled:true});
  const version=await send('Browser.getVersion');
  for(role of roles) {
    for(state of ['fallback','formal','before','before-fallback']) {
      const blocked=state.includes('fallback');
      await send('Network.setBlockedURLs',{urls:blocked?['*.woff2','*.ttf','*.otf']:[]});
      await send('Emulation.setDeviceMetricsOverride',{width:role.width,height:role.height,deviceScaleFactor:1,mobile:false});
      await send('Page.navigate',{url:`${origin}/?${role.id}-${state}`});
      let ready=false;
      for(let i=0;i<100;i++) {
        ready=await evaluate(`document.readyState==='complete' && !!document.querySelector('#t5')`);
        if(ready)break;await sleep(50);
      }
      assert.ok(ready);
      await evaluate('document.fonts.ready.then(()=>true)');
      const measurements=await evaluate(`(() => {
        const rect=r=>({x:r.x,y:r.y,width:r.width,height:r.height});
        return {bodyFamily:getComputedStyle(document.body).fontFamily,
          body:rect(document.querySelector('#body-check').getBoundingClientRect()),
          headings:[...document.querySelectorAll('h1')].map(h=>{
            const runs=[...h.querySelectorAll('.run')].map(s=>{
              const range=document.createRange();range.selectNodeContents(s.firstChild);
              const box=range.getBoundingClientRect();
              const baseline=s.querySelector('.baseline').getBoundingClientRect().top;
              return {text:s.firstChild.textContent,script:s.dataset.script,box:rect(box),baseline,
                baselineFromRunTop:baseline-box.top};
            });
            const han=runs.find(r=>r.script==='han'),latin=runs.find(r=>r.script==='latin');
            return {text:h.textContent,box:rect(h.getBoundingClientRect()),runs,
              baselineDelta:han&&latin?han.baseline-latin.baseline:null,
              runTopBaselineDelta:han&&latin?han.baselineFromRunTop-latin.baselineFromRunTop:null};
          })};
      })()`);
      const fonts=[];
      for(const id of ['#t0','#r2-0','#r2-1'])fonts.push({selector:id,fonts:await fontsFor(id)});
      const used=fonts.flatMap(x=>x.fonts);
      if(blocked) {
        assert.ok(!used.some(f=>/Archivo|Disc Title SC/.test(f.familyName)),JSON.stringify(used));
        if(state==='fallback') {
          assert.ok(used.some(f=>f.postScriptName==='Arial-Black'),JSON.stringify(used));
          assert.ok(used.some(f=>f.postScriptName==='MicrosoftYaHeiUI-Bold'),JSON.stringify(used));
        }
      } else {
        assert.ok(used.some(f=>f.familyName==='Disc Title SC'&&f.isCustomFont),JSON.stringify(used));
        assert.ok(used.some(f=>f.familyName.startsWith('Archivo')&&f.isCustomFont),JSON.stringify(used));
      }
      assert.ok(!measurements.bodyFamily.includes('Title'),'body font stack unchanged');
      for(const h of measurements.headings) {
        assert.ok(h.baselineDelta===null||Math.abs(h.baselineDelta)<0.02,'same-line alphabetic baseline');
      }
      evidence.push({state,role,...measurements,fonts});
      const {data}=await send('Page.captureScreenshot',{format:'png'});
      writeFileSync(join(out,`${role.id}-${state}.png`),Buffer.from(data,'base64'));
    }
  }
  // Explicit height roles and normal line-height both retain their line box on swap.
  for(const role of roles) {
    const a=evidence.find(e=>e.role.id===role.id&&e.state==='fallback');
    const b=evidence.find(e=>e.role.id===role.id&&e.state==='formal');
    for(let i=0;i<titles.length;i++) {
      assert.ok(Math.abs(a.headings[i].box.height-b.headings[i].box.height)<=1,'stable line-box height');
      const ah=a.headings[i],bh=b.headings[i];
      assert.ok(Math.abs(ah.runs[0].baseline-ah.box.y-(bh.runs[0].baseline-bh.box.y))<=1,
        'stable baseline position within title on swap');
      assert.ok(Math.abs(ah.box.width-bh.box.width)/bh.box.width<0.04,'bounded shaped-run width residual');
      // Exact em-width calibration for all covered Han; fractional pixel rounding allowed.
      if(i<2)assert.ok(Math.abs(a.headings[i].box.width-b.headings[i].box.width)<0.1,'stable Han advance');
    }
  }
  assert.ok(failures.some(f=>f.blockedReason==='inspector'),'web fonts really blocked');
  writeFileSync(join(out,'measurements.json'),JSON.stringify({version,
    baselineCommit:'9bb5f00',beforeCssSha256:createHash('sha256').update(before).digest('hex'),
    notes:'box = h1 max-content DOMRect; baselineDelta = Han minus Latin inline baseline markers; runTopBaselineDelta = baseline distance from each script Range top, not a glyph ink-center measurement.',
    failures,evidence},null,2));
  console.log(`PASS: ${roles.length} roles x 4 states x ${titles.length} titles; blocked font requests, platform faces, metrics and ${evidence.length} screenshots verified`);
} finally {
  ws?.close();child.kill();server.closeAllConnections();await new Promise(r=>server.close(r));
  for(const p of pending.values())clearTimeout(p.timer);
  await sleep(800);
  assert.ok(resolve(profile).startsWith(resolve(out)+sep));
  await rm(profile,{recursive:true,force:true,maxRetries:8,retryDelay:300});
}
