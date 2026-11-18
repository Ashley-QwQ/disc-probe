// Shipped design page + real local layout endpoint. No optical devices.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {mkdtemp,mkdir,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {existsSync} from 'node:fs';
import {request} from 'node:http';
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const edge=process.env.KIT_TEST_BROWSER||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';

test('disc files: inner/outer, themes, invalid path, clearing, keyboard and LAN denial',{skip:!existsSync(edge),timeout:120000},async()=>{
  const dir=await mkdtemp(join(tmpdir(),'dp-disc-files-'));let server,browser,ws;
  try{
    server=spawn(process.env.PYTHON||'python',['-B','-m','tests.disc_files_server',dir],{stdio:['ignore','ignore','pipe'],windowsHide:true});
    let stderr='';server.stderr.on('data',d=>{stderr+=d;});
    const until=Date.now()+25000;let info;
    while(Date.now()<until){try{info=JSON.parse(await readFile(join(dir,'server-info.json'),'utf8'));break;}catch{}if(server.exitCode!==null)throw Error(stderr);await pause(100);}
    assert(info,stderr);
    const profile=join(dir,'profile');
    browser=spawn(edge,['--headless=new','--mute-audio','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'],{stdio:'ignore',windowsHide:true});
    let port;
    while(Date.now()<until){try{port=(await readFile(join(profile,'DevToolsActivePort'),'utf8')).split(/\r?\n/)[0];if(port)break;}catch{}await pause(100);}
    assert(port,'browser startup');
    const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await once(ws,'open');
    let seq=0;const pending=new Map(),errors=[];
    ws.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);if(m.id){pending.get(m.id)?.(m);pending.delete(m.id);}});
    const send=(method,params={})=>new Promise((ok,fail)=>{const id=++seq,t=setTimeout(()=>{pending.delete(id);fail(Error('CDP timeout '+method));},20000);pending.set(id,m=>{clearTimeout(t);m.error?fail(Error(JSON.stringify(m.error))):ok(m.result);});ws.send(JSON.stringify({id,method,params}));});
    const run=async expression=>{const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});assert(!r.exceptionDetails,JSON.stringify(r.exceptionDetails));return r.result?.value;};
    const wait=async expression=>{const end=Date.now()+25000;while(Date.now()<end){if(await run(expression))return;await pause(100);}throw Error('UI timeout '+expression+' '+await run('document.body.innerText'));};
    await send('Runtime.enable');await send('Page.enable');
    await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1080,deviceScaleFactor:1,mobile:false});
    await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-reduced-motion',value:'reduce'}]});
    await send('Page.navigate',{url:info.url+'/home/'});
    await wait('document.querySelector("#lobby-new") && document.documentElement.dataset.home==="lobby"');
    await pause(1000);
    await run('document.querySelector("#lobby-new").click()');
    await wait('document.documentElement.dataset.mode==="newplan"');
    await run('document.querySelector("#next").click()');
    await wait('document.documentElement.dataset.mode==="design" && document.querySelector("[data-files=folder]")');
    await pause(800);
    await run('document.querySelector("[data-a=sample]").click()');
    await wait('document.querySelector(".lay")');
    await run(`document.querySelector('[data-files=folder]').value=${JSON.stringify(info.folder)};document.querySelector('[data-files=folder]').dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('[data-files=writable]').value='2295104';document.querySelector('[data-files=writable]').dispatchEvent(new Event('input',{bubbles:true}));`);
    for(const where of ['inner','outer']){
      await run(`document.querySelector('[data-files=where]').value='${where}';document.querySelector('[data-files=where]').dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('[data-files=check]').click();`);
      await wait('document.querySelector("[data-files=status]").textContent.includes("2 个文件")');
      assert((await run('document.querySelector("[data-files=status]").textContent')).includes('图案'));
      for(const theme of ['paper','dark']){
        await run(`document.documentElement.dataset.theme='${theme}';document.querySelector('.disc-files-step').scrollIntoView({block:'nearest'});`);
        await pause(150);
        assert(await run('document.querySelector(".disc-files-step").scrollWidth <= document.querySelector(".col-l").clientWidth'));
        assert(await run('[...document.querySelectorAll(".disc-files-step input,.disc-files-step select,.disc-files-step button")].every(e=>!e.getBoundingClientRect().height||e.getBoundingClientRect().height>=44)'));
        if(process.env.DISC_FILES_SHOTS){await mkdir(resolve(process.env.DISC_FILES_SHOTS),{recursive:true});const shot=await send('Page.captureScreenshot',{format:'png'});await writeFile(join(resolve(process.env.DISC_FILES_SHOTS),`${where}-${theme}.png`),Buffer.from(shot.data,'base64'));}
      }
    }
    await run('document.querySelector("[data-files=folder]").focus()');
    assert.equal(await run('document.activeElement.dataset.files'),'folder');
    await run(`document.querySelector('[data-files=folder]').value='D:/does-not-exist-disc-files';document.querySelector('[data-files=folder]').dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('[data-files=check]').click();`);
    await wait('document.querySelector("[data-files=status]").textContent.includes("folder not found")');
    await run('document.querySelector("[data-files=clear]").click()');
    assert.equal(await run('document.querySelector("[data-files=folder]").value'),'');
    const body=JSON.stringify({folder:info.folder,writable_sectors:2000});
    const denied=await new Promise((ok,fail)=>{const req=request(info.url+'/api/files-layout',{method:'POST',headers:{'Content-Type':'application/json','Content-Length':Buffer.byteLength(body),Host:`192.168.1.2:${new URL(info.url).port}`}},res=>{res.resume();res.on('end',()=>ok(res.statusCode));});req.on('error',fail);req.end(body);});
    assert.equal(denied,403);
    // Small screens keep the local-only reason and controls inside their column.
    await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
    assert(await run('document.querySelector(".disc-files-step").scrollWidth <= document.querySelector(".col-l").clientWidth'));
    assert.deepEqual(errors,[]);
  }finally{
    ws?.close();browser?.kill();server?.kill();
    // Edge may briefly retain a profile lock. Leave any locked isolated temp artifact on D:.
    await pause(500);if(resolve(dir).startsWith(resolve(tmpdir())+'\\'))try{await rm(dir,{recursive:true,force:true});}catch{}
  }
});
