// Edge/CDP: the same backend and UI for the tiny fixture and opt-in real-library evidence.
import assert from 'node:assert/strict';
import {readFile,writeFile,mkdir,rm} from 'node:fs/promises';
import {createServer} from 'node:http';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {resolve,extname,join,sep} from 'node:path';
import {tmpdir} from 'node:os';

const out=resolve(process.env.EDITOR_TEXLIB_OUT??join(tmpdir(),'editor-texlib-'+Date.now()));
await mkdir(out,{recursive:true});
const home=resolve('discprobe/web/home'),index=await readFile(join(home,'index.html'),'utf8');
const fixture=index.replace('data-handshake="pending"','data-handshake="fixture" data-motion="off" data-theme="light"')
  .replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,'').replace('<head>','<head><base href="/home/">')
  .replace('</body>',`<script type="module">
const d=await import('./design.js');const item={kind:'unset',name:'Texture library',mid:'',s:'none'};
d.start({$:id=>document.getElementById(id),lang:()=> 'zh',T:()=>({}),current:()=>({col:'dvd',item}),focusDisc:()=>null,reduce:true,nextWhy(){},state:()=>({})},{fly:false,newPlan:true,noDisc:true});
window.A=d.editorActions();window.ready=true;
</script></body>`);
const backend=spawn(process.env.PYTHON??'python',['-B','-X','utf8','tests/editor_texlib_server.py',join(out,'api')],{stdio:['ignore','pipe','pipe'],windowsHide:true});
let stdout='',stderr='';backend.stdout.on('data',b=>stdout+=b);backend.stderr.on('data',b=>stderr+=b);
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const until=async(fn,ms=90000)=>{const start=Date.now();while(Date.now()-start<ms){if(await fn())return;await pause(100);}throw Error('condition timed out: '+stderr);};
let server,edge,ws;
try{
  await until(()=>/^\d+/m.test(stdout));const port=Number(stdout.match(/^\d+/m)[0]);
  server=createServer(async(req,res)=>{try{
    if(req.url==='/fixture'){res.setHeader('Content-Type','text/html;charset=utf-8');res.end(fixture);return;}
    if(req.url.startsWith('/api/editor-')){const chunks=[];for await(const c of req)chunks.push(c);
      const r=await fetch(`http://127.0.0.1:${port}${req.url}`,{method:req.method,headers:{'Content-Type':'application/json'},body:req.method==='POST'?Buffer.concat(chunks):undefined});
      res.writeHead(r.status,{'Content-Type':r.headers.get('content-type')});res.end(Buffer.from(await r.arrayBuffer()));return;}
    if(req.url.startsWith('/api/')){res.writeHead(404);res.end();return;}
    const relative=decodeURIComponent(req.url.split('?')[0].replace(/^\/home\//,''));
    const file=relative.startsWith('/fonts/')?resolve(home,'..',relative.slice(1)):resolve(home,relative);
    if((!file.startsWith(home+sep)&&!file.startsWith(resolve(home,'../fonts')+sep))||/b[l]ind|faxnews|newplan|presetio|community|[\\/]news[\\/]/i.test(file))throw Error('excluded path');
    res.setHeader('Content-Type',({'.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.css':'text/css','.svg':'image/svg+xml','.woff2':'font/woff2'})[extname(file)]??'application/octet-stream');res.end(await readFile(file));
  }catch{res.writeHead(404);res.end();}}).listen(0,'127.0.0.1');await once(server,'listening');
  const profile=join(out,'edge-profile');
  edge=spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',['--headless=new','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{stdio:'ignore',windowsHide:true});
  let debug;await until(async()=>{try{debug=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split(/\r?\n/)[0];return true;}catch{return false;}});
  const pages=await(await fetch(`http://127.0.0.1:${debug}/json/list`)).json();ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await once(ws,'open');
  let seq=0;const pending=new Map(),errors=[];
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){pending.get(m.id)?.(m);pending.delete(m.id);}if(m.method==='Runtime.exceptionThrown')errors.push(m.params);};
  const send=(method,params={})=>new Promise((ok,fail)=>{const id=++seq,t=setTimeout(()=>fail(Error(method+' timeout')),90000);pending.set(id,m=>{clearTimeout(t);m.error?fail(Error(JSON.stringify(m.error))):ok(m.result);});ws.send(JSON.stringify({id,method,params}));});
  const run=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert.ok(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result?.value;};
  const shot=async name=>{const r=await send('Page.captureScreenshot',{format:'png'});await writeFile(join(out,name+'.png'),Buffer.from(r.data,'base64'));};
  await send('Runtime.enable');await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:`http://127.0.0.1:${server.address().port}/fixture`});
  await until(()=>run('window.ready&&A.editor.palette?.source==="texlib"&&A.editor.rigData'));
  await run(`A.editor.setRig({phone:'iphone17pro',height:'30'});A.editor.panelState().tab='colour';A.editor.right();`);
  await until(()=>run('A.editor.palette.source==="texlib"&&A.editor.poseLights&&document.querySelector("[data-ed-choice=viewMode]")'));
  // Wait for the selected pose's response, not the startup pose's catalog.
  await until(()=>run('A.editor.lightPose===JSON.stringify((()=>{const s=A.state(),b=s.scene.cam,c=[b[0],-s.lookY,b[2]],o=s.scene.flashOffset;return {camera:[c[0],-c[1],c[2]],flash:[c[0]+o[0],-c[1]+o[1],c[2]]};})())'));
  await until(()=>run('A.editor.appliedLightPose===A.editor.lightPose'));
  const counts=await run(`(()=>{const e=A.editor;return {all:e.palette.swatches.length,shown:document.querySelectorAll('.ed-shown button').length,materials:A.state().materials.length,camera:document.querySelector('[data-value=camera]').getAttribute('aria-pressed')};})()`);
  assert.equal(counts.camera,'true');assert(counts.materials<=256);assert(counts.all>=4);
  assert(await run('A.editor.palette.swatches.some(m=>m.id===A.editor.material)||A.state().materials.some(m=>m.id===A.editor.material)'),'active material remains available after changing palette source');
  const results={counts,errors};
  for(const theme of ['light','dark']){
    await run(`document.documentElement.dataset.theme='${theme}';A.editor.options.viewMode='held';A.editor.search='';A.editor.right();`);await shot(theme+'-held');
    await run(`document.querySelector('[data-ed-choice=viewMode][data-value=camera]').click()`);await shot(theme+'-camera');
    const changed=await run(`(()=>{const e=A.editor,m=e.palette.swatches.find(m=>m.y<.04||m.fades||m.stability==null||m.stability>15);if(!m)return null;e.search=m.name;e.material=m.id;e.right();document.querySelector('.ed-all').open=true;document.querySelector('.ed-material-detail').open=true;document.querySelector('.ed-all').scrollIntoView({block:'center'});return {id:m.id,title:document.querySelector('.ed-all button')?.title};})()`);
    if(changed){assert.match(changed.title,/手持时会变色|一斜就看不见/);await shot(theme+'-all-warning');results.filtered=changed;}
    for(const tested of [true,false]){
      const label=await run(`(()=>{const e=A.editor,m=e.palette.swatches.find(m=>m.tested===${tested});if(!m)return null;e.search=m.name;e.material=m.id;e.right();document.querySelector('.ed-material-detail').open=true;document.querySelector('.ed-material-detail').scrollIntoView({block:'center'});return document.querySelector('.ed-material-detail p').textContent;})()`);
      assert(label?.includes(tested?'实刻过':'模型预测'));await shot(theme+'-detail-'+(tested?'tested':'predicted'));
    }
  }
  results.softFill=await run(`(()=>{const e=A.editor,s=A.state(),m=e.palette.swatches.find(m=>m.stability>15||m.fades)||e.palette.swatches.at(-1);e.material=m.id;e.select({tool:'ring',inner:32,outer:46});e.options.target='mask';const before=s.materials.length;e.fill();const work=e.document(),copy=JSON.parse(JSON.stringify(work));return {added:s.materials.length-before,used:work.assignments.at(-1)?.material===m.id,pinned:copy.materials.find(v=>v.id===m.id)?.spec===m.spec};})()`);
  assert(results.softFill.used&&results.softFill.pinned,'filtered material can be filled and saved');
  results.limit=await run(`(()=>{const e=A.editor,s=A.state(),saved=s.materials,selected=e.material;let message='';const old=e.h.error;e.h.error=m=>message=m;s.materials=Array.from({length:256},(_,i)=>({id:'limit-'+i,spec:'A5',rgb:[0,0,0]}));e.material=e.palette.swatches[0].id;const n=s.assignments.length;e.fill();const result={message,count:s.materials.length,assignmentsUnchanged:s.assignments.length===n};s.materials=saved;e.material=selected;e.h.error=old;return result;})()`);
  assert.match(results.limit.message,/256/);assert.equal(results.limit.count,256);assert(results.limit.assignmentsUnchanged);
  // Exercise the dynamic browser table, including newly introduced specs.
  await run(`A.state().view='lamp';A.editor.invalidate();A.editor.h.draw();`);
  await until(()=>run('A.editor.lamp?.phase==="ready"'),90000);
  assert.equal(errors.length,0,JSON.stringify(errors));
  await writeFile(join(out,'browser-results.json'),JSON.stringify(results,null,2),'utf8');console.log(JSON.stringify(results));
  await run('A.editor.lamp?.dispose()');
}finally{
  ws?.close();edge?.kill();backend.kill();server?.close();
  if(edge)await once(edge,'exit').catch(()=>{});
  // The browser profile is disposable; logs, results and screenshots are evidence.
  const profile=join(out,'edge-profile');if(profile.startsWith(out+sep))await rm(profile,{recursive:true,force:true,maxRetries:10,retryDelay:100});
}
