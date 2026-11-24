// Local-only browser acceptance and before/after performance capture. No backend or devices.
import {devToolsPortFile, launchBrowser, removeProfile, selectBrowser, stopBrowser} from '../tests/browser.mjs';
import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir,mkdtemp} from 'node:fs/promises';
import {createServer} from 'node:http';
import {execFileSync} from 'node:child_process';
import {once} from 'node:events';
import {resolve,extname,join,sep} from 'node:path';
const phase=process.argv[2]??'after',out=resolve(process.env.W245_OUT??'D:/dp-dev/tmp/editor');
const browser=selectBrowser();
await mkdir(join(out,'shots'),{recursive:true});
const home=resolve('discprobe/web/home'),index=await readFile(join(home,'index.html'),'utf8');
const fixture=index.replace('data-handshake="pending"','data-handshake="fixture" data-motion="off" data-theme="light"').replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'').replace('<head>','<head><base href="/home/">').replace('</body>',`<script type="module">
const d=await import('./design.js');
const item={kind:'unset',name:'W245',mid:'',s:'none'};
d.start({$:id=>document.getElementById(id),lang:()=> 'zh',T:()=>({}),current:()=>({col:'dvd',item}),focusDisc:()=>null,reduce:true,nextWhy(){},state:()=>({})},{fly:false,newPlan:true,noDisc:true});
window.A=d.editorActions();window.ready=true;
</script></body>`);
const server=createServer(async(req,res)=>{try{
  if(req.url==='/fixture'){res.setHeader('Content-Type','text/html;charset=utf-8');res.end(fixture);return;}
  if(req.url.startsWith('/api/')){res.writeHead(404);res.end();return;}
  const relative=decodeURIComponent(req.url.split('?')[0].replace(/^\/home\//,'')),file=relative.startsWith('/fonts/')?resolve(home,'..',relative.slice(1)):resolve(home,relative);
  if((!file.startsWith(home+sep)&&!file.startsWith(resolve(home,'../fonts')+sep))||/b[l]ind/i.test(file))throw Error('outside fixture');
  res.setHeader('Content-Type',({'.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.css':'text/css','.svg':'image/svg+xml','.woff2':'font/woff2'})[extname(file)]??'application/octet-stream');
  const original=['design.js','design.css','design/editor-ui.mjs','design/editor-controls.mjs'].includes(relative)&&phase==='before';
  res.end(original?execFileSync('git',['show',`${process.env.W245_BASE??'731b199'}:discprobe/web/home/${relative}`],{maxBuffer:4e6}):await readFile(file));
}catch{res.writeHead(404);res.end();}}).listen(0,'127.0.0.1');await once(server,'listening');
const profile=await mkdtemp(join(out,'profile-'));
const edge=launchBrowser(browser, profile, ['--mute-audio','--remote-debugging-port=0','about:blank'],{stdio:'ignore',windowsHide:true});
const pause=ms=>new Promise(r=>setTimeout(r,ms));let ws;
try{
 let port;for(let i=0;i<100;i++){try{port=(await readFile(devToolsPortFile(edge),'utf8')).split(/\r?\n/)[0];break;}catch{await pause(100);}}
 const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await once(ws,'open');
 let seq=0;const pending=new Map(),errors=[];
 ws.onmessage=event=>{const m=JSON.parse(event.data);if(m.id){pending.get(m.id)?.(m);pending.delete(m.id);}if(m.method==='Runtime.exceptionThrown')errors.push(m.params);};
 const send=(method,params={})=>new Promise((ok,fail)=>{const id=++seq;const t=setTimeout(()=>fail(Error(method+' timeout')),60000);pending.set(id,m=>{clearTimeout(t);m.error?fail(Error(JSON.stringify(m.error))):ok(m.result);});ws.send(JSON.stringify({id,method,params}));});
 const run=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert.ok(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result?.value;};
 const shot=async name=>{const r=await send('Page.captureScreenshot',{format:'png'});await writeFile(join(out,'shots',name+'.png'),Buffer.from(r.data,'base64'));};
 await send('Runtime.enable');await send('Performance.enable');await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:`http://127.0.0.1:${server.address().port}/fixture`});
 for(let i=0;i<100;i++){if(await run('window.ready&&A.editor.palette'))break;await pause(100);}
 await run(`(async()=>{const c=document.createElement('canvas');c.width=c.height=1024;const g=c.getContext('2d');const grad=g.createLinearGradient(0,0,1024,1024);grad.addColorStop(0,'#111');grad.addColorStop(1,'#eee');g.fillStyle=grad;g.fillRect(0,0,1024,1024);g.fillStyle='#fff';g.fillRect(400,50,200,900);const b=await new Promise(r=>c.toBlob(r));await A.importFiles([new File([b],'风景.png',{type:'image/png'})]);const l=A.state().layers[0];l.width=120;A.editor.h.changed();A.editor.h.tool('pan');document.querySelector('[data-v="burn"]').click();})()`);await pause(500);
 const results={phase,browser:await send('Browser.getVersion'),viewport:[1440,1000,1],frames:[],errors};
 for(const um of process.env.W245_SKIP_PERF?[]:[20,10]){
  await run(`A.state().cell=${um}/1000;A.editor.h.fit();A.editor.h.changed()`);await pause(600);
  for(const kind of ['pan','zoom']){
   const origin=await run(`(()=>{const r=A.editor.h.dom().canvas.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()`);
   if(kind==='pan')await send('Input.dispatchMouseEvent',{type:'mousePressed',x:origin.x,y:origin.y,button:'left',clickCount:1});
   const before=await send('Performance.getMetrics');
   const frames=await run(`new Promise(resolve=>{const c=A.editor.h.dom().canvas,r=c.getBoundingClientRect(),ts=[];let n=0,last;const tick=t=>{if(last!==undefined)ts.push(t-last);last=t;if(n===48){resolve(ts);return;}const x=r.left+r.width/2,y=r.top+r.height/2;if('${kind}'==='zoom')c.dispatchEvent(new WheelEvent('wheel',{clientX:x,clientY:y,deltaY:n<24?-3:3,ctrlKey:true,bubbles:true,cancelable:true}));else c.dispatchEvent(new PointerEvent('pointermove',{pointerId:1,pointerType:'mouse',buttons:1,clientX:x+3*(n<24?n+1:47-n),clientY:y,bubbles:true}));n++;requestAnimationFrame(tick);};requestAnimationFrame(tick);})`);
   const after=await send('Performance.getMetrics'),sorted=[...frames].sort((a,b)=>a-b),metric=m=>Object.fromEntries(m.metrics.map(v=>[v.name,v.value]));const a=metric(after),b=metric(before);
   if(kind==='pan')await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:origin.x,y:origin.y,button:'left',clickCount:1});
   results.frames.push({um,kind,n:frames.length,median:sorted[Math.floor(sorted.length/2)],p95:sorted[Math.ceil(sorted.length*.95)-1],max:sorted.at(-1),frames,taskDuration:a.TaskDuration-b.TaskDuration,scriptDuration:a.ScriptDuration-b.ScriptDuration});await pause(600);
  }
 }
 results.restingHashes=await run(`(async()=>{const e=A.editor,hashes={};for(const theme of ['light','dark']){document.documentElement.dataset.theme=theme;for(const cell of [.02,.01]){A.state().cell=cell;e.invalidate();const c=e.preview(420),px=c.getContext('2d').getImageData(0,0,420,420).data;hashes[theme+'-'+cell]=[...new Uint8Array(await crypto.subtle.digest('SHA-256',px))].map(n=>n.toString(16).padStart(2,'0')).join('');}}document.documentElement.dataset.theme='light';e.invalidate();e.h.draw();return hashes;})()`);
 // Baseline questions are verified on the shipped UI, before editing it.
 results.questions=await run(`(()=>{const s=A.state(),e=A.editor;e.h.tool('rectangle');e.select({tool:'rectangle',a:[-50,-20],b:[-20,20]});const old=s.layers.length;e.h.dom().canvas.focus();e.h.dom().canvas.dispatchEvent(new KeyboardEvent('keydown',{key:'Delete',bubbles:true}));const removed=s.layers.length<old;A.undo();return {deleteRemovedLayer:removed,legacySelectionBarVisible:!!document.querySelector('.fbar[data-mode="sel"]:not([hidden])'),tool:e.tool,stateTool:s.tool};})()`);
 await writeFile(join(out,phase+'.json'),JSON.stringify(results,null,2),'utf8');
 if(phase==='after'){
  // Frozen from 731b199's light-theme preview() on this fixture and burn grids. Since 2026-11-16 the disc is drawn
  // the same in both themes (the dark theme used to swap light and dark, which read as an inverted picture).
  const expected=browser.shell
    ? '315994a3c1e780f54c7769adb3e6c3d924db55aff226c0f32c6978a67087a186'
    : 'f0fe1afe07f50976046a0ef3ef00cf517abdcfcc9cd741b21e899cdaf5e0cc36';
  for(const [key,hash] of Object.entries(results.restingHashes))assert.equal(hash,expected,'resting RGBA equals 731b199 light: '+key);
  const {verify}=await import('./editor_w245_verify.mjs');results.acceptance=await verify({run,shot,pause,send});
 }
 await writeFile(join(out,phase+'.json'),JSON.stringify(results,null,2),'utf8');console.log(JSON.stringify({...results,frames:results.frames.map(({frames,...r})=>r)}));assert.equal(errors.length,0,JSON.stringify(errors));
}finally{await stopBrowser(edge,ws);server.close();removeProfile(profile,out);}
