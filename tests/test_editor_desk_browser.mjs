// Card X: local-only Edge fixture, fit-follow and edge-fade regression for the selected wood desk.
import assert from 'node:assert/strict';
import {readFile, writeFile, mkdir, rm} from 'node:fs/promises';
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {resolve, extname, join, sep} from 'node:path';
import {tmpdir} from 'node:os';

const out=resolve(process.env.EDITOR_DESK_OUT??join(tmpdir(),'editor-desk'));
const shots=resolve(process.env.EDITOR_DESK_SHOTS??join(out,'after2'));
await mkdir(shots,{recursive:true});
const home=resolve('discprobe/web/home');
const index=await readFile(join(home,'index.html'),'utf8');
const fixture=index.replace('data-handshake="pending"','data-handshake="fixture" data-motion="off" data-theme="light"')
  .replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'').replace('<head>','<head><base href="/home/">')
  .replace('</body>',`<script type="module">
    import * as d from './design.js';
    const item={kind:'unset',name:'Card X',mid:'',s:'none'};
    const api={$:id=>document.getElementById(id),lang:()=> 'zh',T:()=>({}),current:()=>({col:'dvd',item}),focusDisc:()=>null,reduce:true,nextWhy(){},state:()=>({})};
    d.start(api,{fly:false,newPlan:true,noDisc:true});
    window.A=d.editorActions();window.D=d;window.homeApi=api;window.ready=true;
  </script></body>`);
const server=createServer(async(req,res)=>{try{
  if(req.url==='/fixture'){res.setHeader('Content-Type','text/html;charset=utf-8');res.end(fixture);return;}
  if(req.url.startsWith('/api/')){res.writeHead(404);res.end();return;}
  const relative=decodeURIComponent(req.url.split('?')[0].replace(/^\/home\//,''));
  const file=relative.startsWith('/fonts/')?resolve(home,'..',relative.slice(1)):resolve(home,relative);
  if((!file.startsWith(home+sep)&&!file.startsWith(resolve(home,'../fonts')+sep))||/b[l]ind/i.test(file))throw Error('outside fixture');
  res.setHeader('Content-Type',({'.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.woff2':'font/woff2'})[extname(file)]??'application/octet-stream');
  const body=await readFile(file);
  res.end(body);
}catch{res.writeHead(404);res.end();}}).listen(0,'127.0.0.1');
await once(server,'listening');
const profile=join(out,'edge-desk-'+Date.now());
const edge=spawn(process.env.KIT_TEST_BROWSER??'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',[
  '--headless=new','--disable-background-networking','--no-first-run','--no-default-browser-check',
  '--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{stdio:'ignore',windowsHide:true});
const pause=ms=>new Promise(r=>setTimeout(r,ms));
let ws,seq=0;const pending=new Map(),errors=[],checks=[],measurements=[];
try{
  let port;
  for(let i=0;i<200;i++){try{port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split(/\r?\n/)[0];break;}catch{await pause(50);}}
  assert.ok(port,'Edge starts');
  const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await once(ws,'open');
  ws.onmessage=({data})=>{const m=JSON.parse(data);if(m.id){pending.get(m.id)?.(m);pending.delete(m.id);}if(m.method==='Runtime.exceptionThrown')errors.push(m.params);};
  const send=(method,params={})=>new Promise((ok,fail)=>{const id=++seq;const timer=setTimeout(()=>fail(Error(method+' timeout')),30000);pending.set(id,m=>{clearTimeout(timer);m.error?fail(Error(JSON.stringify(m.error))):ok(m.result);});ws.send(JSON.stringify({id,method,params}));});
  const run=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert.ok(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result?.value;};
  const check=async(name,expression)=>{assert.equal(await run(expression),true,name);checks.push(name);};
  const frame=()=>run('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
  const shot=async name=>{await frame();await pause(180);const r=await send('Page.captureScreenshot',{format:'png'});await writeFile(join(shots,name+'.png'),Buffer.from(r.data,'base64'));};
  const load=async(width,height)=>{
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
    await send('Page.navigate',{url:`http://127.0.0.1:${server.address().port}/fixture`});
    for(let i=0;i<200;i++){if(await run('window.ready&&A.editor.palette'))break;await pause(50);}
    await run('document.fonts.ready');await frame();
  };
  const fitEquals=`(()=>{const e=A.editor,v=e.h.view(),r=e.h.dom().cv.getBoundingClientRect(),expected=Math.max(1,Math.min(r.width-64,r.height-160))*.92/120;return Math.abs(v.s-expected)<1e-8&&Math.abs(v.cx-(r.left+r.width/2+20))<1e-8&&Math.abs(v.cy-(r.top+64+(r.height-160)/2))<1e-8;})()`;
  await send('Runtime.enable');await send('Page.enable');
  await load(1440,1000);
  // ResizeObserver must follow every size during an entrance, with no timing guess.
  await run(`A.editor.h.dom().cv.style.right='650px';A.editor.h.dom().cv.style.bottom='500px'`);await frame();
  await check('entrance small container fits',fitEquals);
  await run(`A.editor.h.dom().cv.style.right='';A.editor.h.dom().cv.style.bottom=''`);await frame();
  await check('entrance expanded container fits',fitEquals);
  await run(`(()=>{const e=A.editor,v=e.h.view();e.h.dom().canvas.dispatchEvent(new WheelEvent('wheel',{ctrlKey:true,deltaY:-20,clientX:v.cx,clientY:v.cy,bubbles:true,cancelable:true}));window.manualScale=v.s;})()`);
  await send('Emulation.setDeviceMetricsOverride',{width:1220,height:750,deviceScaleFactor:1,mobile:false});await frame();
  await check('user zoom survives window resize','Math.abs(A.editor.h.view().s-manualScale)<1e-8');
  await run(`dispatchEvent(new KeyboardEvent('keydown',{key:'0',bubbles:true}))`);await frame();
  await check('zero restores fit',fitEquals);
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});await frame();
  await check('zero restores resize following',fitEquals);
  for(const key of ['1','+','-']){
    await run(`dispatchEvent(new KeyboardEvent('keydown',{key:'${key}',bubbles:true}));window.manualScale=A.editor.h.view().s;A.editor.h.dom().cv.style.right='500px'`);await frame();
    await check(key+' exits fit follow','Math.abs(A.editor.h.view().s-manualScale)<1e-8');
    await run(`A.editor.h.dom().zoom.click();A.editor.h.dom().cv.style.right=''`);await frame();
    await check('zoom number restores fit after '+key,fitEquals);
  }
  // Touchpad pan and hand drag also exit follow; an outside drag must never draw/select.
  await run(`(()=>{const e=A.editor,v=e.h.view();e.h.dom().canvas.dispatchEvent(new WheelEvent('wheel',{deltaX:5,deltaY:.1,clientX:v.cx,clientY:v.cy,bubbles:true,cancelable:true}));window.manualScale=v.s;})()`);
  await run(`A.editor.h.dom().cv.style.right='500px'`);await frame();
  await check('touchpad pan exits fit follow','Math.abs(A.editor.h.view().s-manualScale)<1e-8');
  await run(`A.editor.h.dom().zoom.click();A.editor.h.dom().cv.style.right=''`);await frame();
  const pointer=async(type,x,y,button='left')=>send('Input.dispatchMouseEvent',{type,x,y,button,buttons:type==='mouseReleased'?0:1,clickCount:type==='mouseMoved'?0:1});
  const point=await run(`(()=>{const r=A.editor.h.dom().cv.getBoundingClientRect();return {x:r.left+80,y:r.top+90};})()`);
  await run(`A.editor.h.tool('pan');window.manualScale=A.editor.h.view().s;window.oldCX=A.editor.h.view().cx;`);
  await pointer('mousePressed',point.x,point.y);await pointer('mouseMoved',point.x+30,point.y+20);await pointer('mouseReleased',point.x+30,point.y+20);
  await run(`A.editor.h.dom().cv.style.right='500px'`);await frame();
  await check('hand drag exits fit follow','Math.abs(A.editor.h.view().s-manualScale)<1e-8');
  await run(`A.editor.h.dom().zoom.click();A.editor.h.dom().cv.style.right='';A.editor.h.tool('rectangle')`);await frame();
  const pinch=await run(`(()=>{const v=A.editor.h.view();window.beforePinch=v.s;return {x:v.cx,y:v.cy};})()`);
  const touches=(span)=>[{x:pinch.x-span,y:pinch.y,id:1},{x:pinch.x+span,y:pinch.y,id:2}];
  await send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:touches(40)});
  await send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:touches(65)});
  await send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await frame();
  await check('two fingers zoom without committing selection','A.editor.h.view().s>beforePinch*1.2&&!A.editor.drag&&A.state().selections.length===0');
  await run(`window.manualScale=A.editor.h.view().s;A.editor.h.dom().cv.style.right='500px'`);await frame();
  await check('pinch exits fit follow','Math.abs(A.editor.h.view().s-manualScale)<1e-8');
  await run(`A.editor.h.dom().zoom.click();A.editor.h.dom().cv.style.right=''`);await frame();
  const outside=await run(`(()=>{const r=A.editor.h.dom().cv.getBoundingClientRect();return {x:r.left+80,y:r.top-12};})()`);
  await run(`window.oldCX=A.editor.h.view().cx;window.oldLayers=A.state().layers.length;window.oldMasks=A.state().selections.length;window.oldHistory=A.state().past.length`);
  await pointer('mousePressed',outside.x,outside.y);await pointer('mouseMoved',outside.x+40,outside.y+3);await pointer('mouseReleased',outside.x+40,outside.y+3);
  await check('outside gap pans without drawing or selection',`Math.abs(A.editor.h.view().cx-oldCX-40)<.01&&A.state().layers.length===oldLayers&&A.state().selections.length===oldMasks&&A.state().past.length===oldHistory&&!A.editor.drag`);
  await check('panel receives outside clicks',`(()=>{const p=A.editor.h.dom().right,r=p.getBoundingClientRect();return p.contains(document.elementFromPoint(r.left+20,r.top+20))&&getComputedStyle(p).backgroundColor!=='rgba(0, 0, 0, 0)';})()`);
  await run(`D.start(homeApi,{plan:A.state(),fly:false})`);await frame();
  await check('enter editor resets following',fitEquals);
  await run(`dispatchEvent(new KeyboardEvent('keydown',{key:'1',bubbles:true}));D.useBatch(homeApi,A.state(),{kind:'unset',name:'CD',mid:'',s:'none'},'cd')`);await frame();
  await check('change media resets following',fitEquals);
  await run(`(async()=>{const text=await A.projectText();dispatchEvent(new KeyboardEvent('keydown',{key:'1',bubbles:true}));await A.openProject(new File([text],'fit.discdesign',{type:'application/json'}));})()`);await frame();
  await check('open project resets following',fitEquals);
  await run(`(()=>{const e=A.editor,v=e.h.view(),d=e.h.dom();d.canvas.dispatchEvent(new WheelEvent('wheel',{ctrlKey:true,deltaY:-12,clientX:v.cx,clientY:v.cy,bubbles:true,cancelable:true}));})()`);await frame();
  await check('desk grain follows zoom and pan',`(()=>{const v=A.editor.h.view(),d=A.editor.h.dom().desk;return Math.abs(parseFloat(d.style.backgroundSize)-80*v.s)<.001&&Math.abs(parseFloat(d.style.backgroundPosition)-v.cx)<.001;})()`);
  await check('wood desk is the shipped default',`getComputedStyle(A.editor.h.dom().desk).backgroundImage.includes('editor-desk-b-')`);
  await check('header and footer retain transparent backgrounds',`[document.querySelector('header'),document.querySelector('footer'),A.editor.h.dom().ws.querySelector('.ws-title')].every(el=>getComputedStyle(el).backgroundColor==='rgba(0, 0, 0, 0)')`);
  // Measure the composed CSS mask, not just its declared style. Hide chrome in this disposable fixture.
  await run(`(()=>{const d=A.editor.h.dom(),style=document.createElement('style');style.textContent='.cv > :not(.ed-surface),.ed-panel-shadow,.ed-disc-shadow,header,footer,.ws>.col,.ws>.filebtns,.ws>.ws-title{visibility:hidden!important}';document.head.append(style);d.desk.style.backgroundImage='none';d.desk.style.backgroundColor='rgb(200,200,200)';const g=d.canvas.getContext('2d');g.setTransform(1,0,0,1,0,0);g.fillStyle='#000';g.fillRect(0,0,d.canvas.width,d.canvas.height);})()`);
  const masked=await send('Page.captureScreenshot',{format:'png'});
  const opacity=await run(`(async()=>{const image=new Image();image.src='data:image/png;base64,${masked.data}';await image.decode();const c=document.createElement('canvas');c.width=image.width;c.height=image.height;const g=c.getContext('2d');g.drawImage(image,0,0);const r=A.editor.h.dom().cv.getBoundingClientRect(),pixel=(x,y)=>[...g.getImageData(x,y,1,1).data];return {outside:pixel(20,500),inside:pixel(r.left+100,r.top+80),header:pixel(500,r.top-42),footer:pixel(500,r.bottom+42),topFade:pixel(20,r.top-16+24),bottomFade:pixel(20,r.bottom+16-24)};})()`);
  const near=(value,expected)=>value.slice(0,3).every(n=>Math.abs(n-expected)<=2);
  assert.ok(near(opacity.outside,130)&&near(opacity.inside,0),JSON.stringify(opacity));
  assert.ok(near(opacity.header,200)&&near(opacity.footer,200),JSON.stringify(opacity));
  assert.ok(near(opacity.topFade,165)&&near(opacity.bottomFade,165),JSON.stringify(opacity));
  checks.push('outside pixels have 35% opacity; inside pixels remain fully opaque',
    'canvas pixels are fully transparent under header and footer',
    'both 48 px fades have half strength at their midpoint');
  const candidate='B';
  for(const [width,height] of [[1440,1000],[1220,750]]){
    await load(width,height);
    for(const theme of ['light','dark']){
      await run(`document.documentElement.dataset.theme='${theme}';A.editor.h.fit();A.editor.h.draw()`);
      await check(candidate+' '+theme+' '+width+' initial fits',fitEquals);
      await shot(`${candidate}-${theme}-${width}x${height}-initial`);
      if(!await run('A.state().layers.length'))await run(`(async()=>{const c=document.createElement('canvas');c.width=c.height=512;const g=c.getContext('2d');g.fillStyle='#eee';g.fillRect(0,0,512,512);g.fillStyle='#28383c';g.fillRect(32,40,420,360);g.fillStyle='#bc8e5d';g.beginPath();g.arc(355,150,72,0,7);g.fill();await A.importFiles([new File([await new Promise(r=>c.toBlob(r))],'desk-sample.png',{type:'image/png'})]);A.state().layers[0].width=145;A.editor.h.tool('pan');A.editor.h.changed();})()`);
      await run(`A.editor.h.fit()`);await frame();
      const p=await run(`(()=>{const r=A.editor.h.dom().cv.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()`);
      await pointer('mousePressed',p.x,p.y);await pointer('mouseMoved',p.x+145,p.y-120);await pointer('mouseReleased',p.x+145,p.y-120);
      await shot(`${candidate}-${theme}-${width}x${height}-overflow`);
      const sample=await run(`(()=>{const e=A.editor,v=e.h.view(),d=e.h.dom();return {variant:'${candidate}',theme:'${theme}',width:${width},height:${height},view:{...v},focus:d.cv.getBoundingClientRect().toJSON(),mask:getComputedStyle(d.surface).maskImage,background:getComputedStyle(d.desk).backgroundImage,backgroundSize:d.desk.style.backgroundSize,backgroundPosition:d.desk.style.backgroundPosition,panel:getComputedStyle(d.right).backgroundColor,shadow:d.shadow.style.boxShadow};})()`);
      measurements.push(sample);
      await run(`A.state().layers=[];A.state().selected=null;A.editor.h.changed();A.editor.h.rebuild()`);
    }
  }
  assert.equal(errors.length,0,JSON.stringify(errors));
  await writeFile(join(out,'desk-check.json'),JSON.stringify({checks,opacity,measurements,errors},null,2),'utf8');
  console.log(JSON.stringify({checks:checks.length,screenshots:8,errors:errors.length,out,shots}));
}finally{
  ws?.close();edge.kill();server.close();
  await pause(750);
  assert.ok(profile.startsWith(out+sep));
  await rm(profile,{recursive:true,force:true,maxRetries:5,retryDelay:200});
}
