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
const colourWork=process.env.EDITOR_COLOUR_WORK && resolve(process.env.EDITOR_COLOUR_WORK);
if(colourWork && /b[l]ind/i.test(colourWork))throw Error('excluded work path');
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
    if(req.url==='/fixture-work'&&colourWork){res.setHeader('Content-Type','application/json');res.end(await readFile(colourWork));return;}
    if(req.url.startsWith('/api/editor-')){const chunks=[];for await(const c of req)chunks.push(c);
      const r=await fetch(`http://127.0.0.1:${port}${req.url}`,{method:req.method,headers:{'Content-Type':'application/json'},body:req.method==='POST'?Buffer.concat(chunks):undefined});
      res.writeHead(r.status,{'Content-Type':r.headers.get('content-type')});res.end(Buffer.from(await r.arrayBuffer()));return;}
    if(req.url.startsWith('/api/')){res.writeHead(404);res.end();return;}
    const relative=decodeURIComponent(req.url.split('?')[0].replace(/^\/home\//,''));
    const file=relative.startsWith('/fonts/')?resolve(home,'..',relative.slice(1)):resolve(home,relative);
    if((!file.startsWith(home+sep)&&!file.startsWith(resolve(home,'../fonts')+sep))||
      /b[l]ind/i.test(file)||/faxnews|newplan|presetio|community|(?:^|[\\/])news[\\/]/i.test(relative))throw Error('excluded path');
    res.setHeader('Content-Type',({'.js':'text/javascript','.mjs':'text/javascript','.json':'application/json','.css':'text/css','.svg':'image/svg+xml','.woff2':'font/woff2'})[extname(file)]??'application/octet-stream');res.end(await readFile(file));
  }catch{res.writeHead(404);res.end();}}).listen(0,'127.0.0.1');await once(server,'listening');
  const profile=join(out,'edge-profile');
  edge=spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',['--headless=new','--mute-audio','--disable-background-networking','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{stdio:'ignore',windowsHide:true});
  let debug;await until(async()=>{try{debug=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split(/\r?\n/)[0];return true;}catch{return false;}});
  const pages=await(await fetch(`http://127.0.0.1:${debug}/json/list`)).json();ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await once(ws,'open');
  let seq=0;const pending=new Map(),errors=[];
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){pending.get(m.id)?.(m);pending.delete(m.id);}if(m.method==='Runtime.exceptionThrown')errors.push(m.params);};
  const send=(method,params={})=>new Promise((ok,fail)=>{const id=++seq,t=setTimeout(()=>fail(Error(method+' timeout')),90000);pending.set(id,m=>{clearTimeout(t);m.error?fail(Error(JSON.stringify(m.error))):ok(m.result);});ws.send(JSON.stringify({id,method,params}));});
  const run=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert.ok(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result?.value;};
  const shot=async name=>{const r=await send('Page.captureScreenshot',{format:'png'});await writeFile(join(out,name+'.png'),Buffer.from(r.data,'base64'));};
  await send('Runtime.enable');await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:`http://127.0.0.1:${server.address().port}/fixture`});
  const colourOnly=process.env.EDITOR_COLOUR_ONLY==='1';
  await until(()=>run(colourOnly?'window.ready&&A.editor.palette&&A.editor.rigData':'window.ready&&A.editor.palette?.source==="texlib"&&A.editor.rigData'));
  if(!colourOnly){
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
  }
  // Exercise the normal file-input and fill buttons, with the same API that the editor uses.
  const source=process.env.EDITOR_COLOUR_PICTURE;
  if(source && /b[l]ind/i.test(resolve(source)))throw Error('excluded picture path');
  const input=source ? (await readFile(source)).toString('base64') : null;
  await run(`(async()=>{
    const s=A.state();s.assignments=[];s.activeMask=null;s.view='proj';s.scene.rig={};A.editor.invalidate();
    let blob;
    if (${JSON.stringify(input)}) blob=await (await fetch('data:image/png;base64,'+${JSON.stringify(input)})).blob();
    else {const c=document.createElement('canvas');c.width=c.height=150;const g=c.getContext('2d');
      ['#c43d26','#e0a042','#5f8f53','#327a99','#d39e86'].forEach((rgb,i)=>{g.fillStyle=rgb;g.fillRect(i*30,0,30,150);});
      blob=await new Promise(resolve=>c.toBlob(resolve));}
    const file=new File([blob],'Illustration.png',{type:'image/png'}),dt=new DataTransfer(),picker=document.querySelector('.f-img');
    dt.items.add(file);picker.files=dt.files;picker.dispatchEvent(new Event('change',{bubbles:true}));
  })()`);
  await until(()=>run('A.state().layers.some(l=>l.name==="Illustration.png"||l.name==="Illustration")'));
  await run(`document.querySelector('[data-ed-tab=colour]').click();document.querySelector('[data-value=colour]').click();`);
  assert(await run(`document.querySelector('[data-ed-action=fill]').disabled&&document.querySelector('[data-ed-action=fill]').textContent.includes('先选手机和拍摄高度')`));
  const height=process.env.EDITOR_COLOUR_HEIGHT??'21';
  await run(`document.querySelector('[data-ed-rig=phone][data-value=iphone17pro]').click();document.querySelector('[data-ed-rig=height][data-value="'+${JSON.stringify(height)}+'"]').click();`);
  await until(()=>run('A.editor.colourPalette&&document.querySelector("[data-ed-action=fill]:not(:disabled)")'));
  const toggle='document.querySelector("[data-ed=directionArrow]")';
  const fill='document.querySelector("[data-ed-action=fill]").click()';
  const snapshot=()=>run(`(()=>{
    const d=A.editor.document(), arrows=d.layers.filter(l=>l.shape?.directionArrow);
    const colour=d.assignments.find(a=>a.colour), arrow=arrows[0];
    const spec=d.materials.find(m=>m.id===d.assignments.find(a=>a.layer===arrow?.id)?.material)?.spec;
    return {arrows:arrows.length, filled:!!colour, above:!!arrow&&d.layers[d.layers.indexOf(arrow)-1]?.id===colour?.layer,
      spec:spec??null, name:arrow?.name??null, tip:arrow?-(arrow.y-arrow.height/2):null};
  })()`);
  const arrowEvidence=process.env.EDITOR_ARROW_EVIDENCE;
  async function arrowShots(variant){
    if(!arrowEvidence)return;
    await mkdir(arrowEvidence,{recursive:true});
    for(const [theme,name] of [['light','paper'],['dark','night']]){
      await run(`document.documentElement.dataset.theme='${theme}';`);
      await pause(200);
      const r=await send('Page.captureScreenshot',{format:'png'});
      await writeFile(join(arrowEvidence,`${name}-${variant}.png`),Buffer.from(r.data,'base64'));
    }
  }
  assert(await run(toggle+'.checked'),'the checkbox defaults to checked');
  assert.deepEqual(await run(`(()=>{const {width,height}=${toggle}.getBoundingClientRect();return [width,height];})()`),[16,16]);
  await run(toggle+'.click();'+fill);
  assert.deepEqual(await snapshot(),{arrows:0,filled:true,above:false,spec:null,name:null,tip:null});
  await arrowShots('unchecked');
  await run('A.undo()');
  assert.equal((await snapshot()).filled,false);
  await run(toggle+'.click();'+fill);
  const arrow=await snapshot();
  assert.deepEqual({...arrow,tip:Math.round(arrow.tip*10)/10},
    {arrows:1,filled:true,above:true,spec:'RND',name:'方向箭头',tip:52.8});
  await arrowShots('checked');
  await run(fill);
  assert.deepEqual(await snapshot(),arrow,'reapplying colour keeps a single arrow');
  await run('A.undo()');
  assert.deepEqual(await snapshot(),arrow);
  await run('A.undo()');
  assert.deepEqual(await snapshot(),{arrows:0,filled:false,above:false,spec:null,name:null,tip:null});
  await run('A.state().ring=[40.21,50];'+fill);
  assert.equal((await snapshot()).arrows,0,'the arrow is omitted if its tail would cross the hub');
  assert.equal((await snapshot()).filled,true);
  assert(await run('document.querySelector(".toast.on")?.textContent.includes("可刻环带太窄")'));
  await run('A.undo();A.state().ring=[40.2,50];'+fill);
  assert.equal((await snapshot()).tip,49.5,'the tip moves inside the measured rim');
  await run('A.undo();delete A.state().ring;'+fill);
  assert.deepEqual(await snapshot(),arrow);
  const candidates=await run(`(()=>{const d=A.editor.document(),c=d.assignments.find(a=>a.colour)?.colour;return c?.materials.every(id=>d.materials.some(m=>m.id===id))?c.materials.length:0;})()`);
  assert.equal(candidates,58);
  assert(await run(`document.querySelector('.ed-colour-estimate + details').textContent.includes('用 6 张色卡盘实拍校准的模型')`));
  assert(await run(`(()=>{const text=document.querySelector('.ed-colour-estimate + details').textContent;
    return text.includes('手机角度偏一两度')&&text.includes('正对闪光灯的那条带看不到图');})()`));
  const evidence=process.env.EDITOR_COLOUR_EVIDENCE;
  if(evidence)await mkdir(evidence,{recursive:true});
  const capture=async name=>{
    if(!evidence)return;
    const r=await send('Page.captureScreenshot',{format:'png'});
    await writeFile(join(evidence,name+'.png'),Buffer.from(r.data,'base64'));
  };
  await run(`document.documentElement.dataset.theme='light';document.querySelector('.ed-colour-estimate + details').open=true;`);
  await pause(200);
  await capture('paper-colour');
  await run(`document.documentElement.dataset.theme='dark';`);
  await capture('night-colour');
  const started=Date.now();
  const status=await run(`(()=>{document.querySelector('.ws .viewsw [data-v=lamp]').click();return {note:document.querySelector('.ws .ed-view-note').textContent,view:A.state().view};})()`);
  assert.match(status.note,/正在按机位预测颜色/,JSON.stringify({status,errors}));
  await until(async()=>{
    const state=await run('({phase:A.editor.colourRenderer?.phase,error:A.editor.colourRenderer?.error})');
    assert.notEqual(state.phase,'error',state.error);
    assert.equal(errors.length,0,JSON.stringify(errors));
    return state.phase==='ready';
  },180000);
  const predictSeconds=(Date.now()-started)/1000;
  assert(await run(`document.querySelector('.ws .ed-view-note').textContent.includes('预览用斜线标出')`));
  const frame=await run(`(()=>{const p=A.editor.colourRenderer.frame;return {w:p.image.width,h:p.image.height,view:p.view};})()`);
  assert.equal(frame.view,'lamp');assert(frame.w>=200&&frame.w===frame.h);
  for(const [theme,name] of [['light','paper'],['dark','night']]){
    await run(`document.documentElement.dataset.theme='${theme}';A.editor.h.draw();`);
    await pause(150);await capture(name+'-prediction');
    assert(await run(`(()=>{const b=document.querySelector('[data-colour-compare]');if(b.hidden)return false;b.click();return b.getAttribute('aria-pressed')==='true';})()`));
    await pause(150);await capture(name+'-comparison');
    await run(`document.querySelector('[data-colour-compare]').click();`);
  }
  await run(`document.querySelector('[data-v=burn]').click();`);
  await until(()=>run('A.editor.colourRenderer?.phase==="ready"&&A.editor.colourRenderer.frame?.view==="burn"'));
  const reopened=await run(`(async()=>{
    document.querySelector('[data-v=proj]').click();
    const text=${!!colourWork}?await (await fetch('/fixture-work')).text():await A.projectText();
    await A.openProject(new File([text],'colour-work.json',{type:'application/json'}));
    const d=A.editor.document();return {candidates:d.assignments.find(a=>a.colour)?.colour.materials.length,
      rig:d.scene?.rig,lookY:A.state().lookY};
  })()`);
  assert.deepEqual(reopened,{candidates,rig:{phone:'iphone17pro',height},lookY:28.45});
  if(!colourWork){
    assert.deepEqual(await snapshot(),arrow,'the saved document retains the editable arrow');
    const refilling=await run(`(()=>{
      const e=A.editor,s=A.state(),id=s.assignments.find(a=>a.colour).layer;
      e.h.dom().left.querySelector('.lay[data-id="'+id+'"]').click();
      return s.selected===id&&!document.querySelector('[data-ed-action=fill]').disabled;
    })()`);
    assert(refilling,'the picture can be selected in the reopened layer list');
    await run(fill);
    assert.deepEqual(await snapshot(),arrow,'reopening retains the arrow identity');
    const pixels=await run(`(async()=>{
      const d=A.editor.document();
      await A.openProject(new File([JSON.stringify(d)],'portable-work.json',{type:'application/json'}));
      const layer=A.state().layers.find(l=>l.shape?.directionArrow);
      const i=layer.px.data.findIndex((v,i)=>i%4===3&&v===255);
      return [...layer.px.data.slice(i-3,i+1)];
    })()`);
    assert.deepEqual(pixels,[128,128,128,255],'opening a shape-only arrow keeps its display colour');
    assert.deepEqual(await snapshot(),arrow,'opening a shape-only arrow keeps its geometry');
    const edits=await run(`(()=>{
      const s=A.state(),l=s.layers.find(l=>l.shape?.directionArrow),{left,bar}=A.editor.h.dom();
      const row=()=>left.querySelector('.lay[data-id="'+l.id+'"]');
      row().click();
      const x=bar.querySelector('[data-k=x]');
      x.value='1.5';x.dispatchEvent(new Event('input',{bubbles:true}));
      row().querySelector('[data-a=vis]').click();
      const hidden=!l.visible;
      row().querySelector('[data-a=vis]').click();
      bar.querySelector('[data-a=del]').click();
      return {moved:l.x,hidden,removed:!s.layers.includes(l)&&!s.assignments.some(a=>a.layer===l.id)};
    })()`);
    assert.deepEqual(edits,{moved:1.5,hidden:true,removed:true},'the arrow uses the ordinary layer controls');
  }
  assert.equal(errors.length,0,JSON.stringify(errors));
  const result={candidates,frame,predictSeconds,asBurned:true,comparison:true,reopened,arrow,undo:true,duplicate:false,errors:errors.length};
  await writeFile(join(out,'colour-browser-results.json'),JSON.stringify(result,null,2),'utf8');console.log(JSON.stringify(result));
  await run('A.editor.colourRenderer?.dispose()');
}finally{
  ws?.close();edge?.kill();backend.kill();server?.close();
  if(edge)await once(edge,'exit').catch(()=>{});
  // The browser profile is disposable; logs, results and screenshots are evidence.
  const profile=join(out,'edge-profile');if(profile.startsWith(out+sep))await rm(profile,{recursive:true,force:true,maxRetries:10,retryDelay:100});
}
