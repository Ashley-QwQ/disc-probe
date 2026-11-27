// Shipped design page + real local layout endpoint. No optical devices.
import {devToolsPortFile, launchBrowser, selectBrowser, stopBrowser} from './browser.mjs';
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {spawn, spawnSync} from 'node:child_process';
import {once} from 'node:events';
import {mkdtemp,mkdir,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve,sep} from 'node:path';
import {request} from 'node:http';
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const edge=selectBrowser({legacy: ['KIT_TEST_BROWSER']});

test('findings 1 and 6: portable work import, confirmed ISO contents and inert DOM',{skip:!edge,timeout:170000},async(testCase)=>{
  const dir=await mkdtemp(join(tmpdir(),'dp-disc-files-'));let server,browser,ws;
  try{
    const geo=join(dir,'results','geo-H-20261107-101500');
    await mkdir(geo,{recursive:true});
    await writeFile(join(geo,'summary.json'),JSON.stringify({
      fit:{media:'dvd',u:180000,v:1000,bit_nm_assumed:133.3,capacity_sectors:4096,
        measured_span_mm:[23,45],angle_sigma_measured_span_deg:.1,chi2_per_dof:1},
      identity:{disc:'TEST-DVD',drive:'Fake drive'},setup:{last_lba:4095},
    }));
    await writeFile(join(geo,'targets.csv'),'header\n'+'point\n'.repeat(10));
    server=spawn(process.env.PYTHON||'python',['-B','-m','tests.disc_files_server',dir],{stdio:['ignore','ignore','pipe'],windowsHide:true});
    let stderr='';server.stderr.on('data',d=>{stderr+=d;});
    const until=Date.now()+25000;let info;
    while(Date.now()<until){try{info=JSON.parse(await readFile(join(dir,'server-info.json'),'utf8'));break;}catch{}if(server.exitCode!==null)throw Error(stderr);await pause(100);}
    assert(info,stderr);
    const profile=join(dir,'profile');
    browser=launchBrowser(edge, profile, ['--mute-audio','--no-sandbox','--remote-debugging-port=0','about:blank'],{disableGpu: true, stdio:'ignore',windowsHide:true});
    let port;
    while(Date.now()<until){try{port=(await readFile(devToolsPortFile(browser),'utf8')).split(/\r?\n/)[0];if(port)break;}catch{}await pause(100);}
    assert(port,'browser startup');
    const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await once(ws,'open');
    let seq=0;const pending=new Map(),errors=[];
    ws.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);if(m.id){pending.get(m.id)?.(m);pending.delete(m.id);}});
    const send=(method,params={})=>new Promise((ok,fail)=>{const id=++seq,t=setTimeout(()=>{pending.delete(id);fail(Error('CDP timeout '+method));},65000);pending.set(id,m=>{clearTimeout(t);m.error?fail(Error(JSON.stringify(m.error))):ok(m.result);});ws.send(JSON.stringify({id,method,params}));});
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
    await run(`const batch = document.querySelector('.np-batch'); batch.value = 'TEST-DVD';
      batch.dispatchEvent(new Event('input')); document.querySelector('#next').click();`);
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
    await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1080,deviceScaleFactor:1,mobile:false});
    const source=join(dir,'export source'), marker='finding-1-local-fixture-228de4a23';
    await mkdir(source);
    await writeFile(join(source,'fixture-local.txt'),marker);
    const markup='id"><span data-finding-marker>';
    await testCase.test('finding_6_layer_id_and_text',async()=>{
      const checked=await run(`(async()=>{
        window.finding6Calls=0; window.finding6Hook=()=>window.finding6Calls++;
        const observer=new MutationObserver(records=>{
          for(const record of records) for(const node of record.addedNodes)
            if(node.nodeType===1&&(node.matches('[data-finding-marker]')||node.querySelector('[data-finding-marker]'))) window.finding6Hook();
        });
        observer.observe(document.querySelector('.col-l'),{childList:true,subtree:true});
        const editor=await import('/home/design.js'), actions=editor.editorActions(), work=JSON.parse(await actions.projectText());
        work.layers[0].id=${JSON.stringify(markup)}; work.layers[0].name=work.layers[0].id;
        work.assignments=[{layer:work.layers[0].id,material:work.materials[1].id}];
        work.files={folder:${JSON.stringify(source)},where:'inner',layout:{file_count:1,file_bytes:${Buffer.byteLength(marker)}},token:'stale-token'};
        await actions.openProject(new File([JSON.stringify(work)],'imported.discdesign'));
        const row=document.querySelector('.lay'), doc=JSON.parse(await actions.projectText());
        observer.disconnect();
        return {calls:window.finding6Calls, label:row.querySelector('.ed-layer-label').textContent, id:row.dataset.id,
          controls:row.querySelector('[data-a="more"]').getAttribute('aria-controls'),
          assigned:String(doc.assignments[0].layer), markers:document.querySelectorAll('[data-finding-marker]').length, files:doc.files};
      })()`);
      assert.equal(checked.calls,0);
      assert.equal(checked.markers,0);
      assert.equal(checked.label,markup);
      assert.match(checked.id,/^[A-Za-z0-9_-]{1,64}$/);
      assert.equal(checked.assigned,checked.id);
      assert.equal(checked.controls,'ed-layer-actions-'+checked.id);
      assert.deepEqual(checked.files,{count:1,bytes:Buffer.byteLength(marker),where:'inner'});
    });
    await testCase.test('finding_1_directory_requires_one_export_confirmation',async()=>{
      const exportImage=()=>run(`(async()=>{const design=await import('/home/design.js');return design.makeBurnFile();})()`);
      const readIso=(name,hasFiles)=>{
        const check=spawnSync(process.env.PYTHON||'python',['-B','-c',
          'from pathlib import Path; from discprobe.iso_read import read_tree; import json, sys; p=Path(sys.argv[1]); print(json.dumps([read_tree(p,joliet=False,hashes=True), read_tree(p,hashes=True) if sys.argv[3]=="yes" else {}, sys.argv[2].encode() in p.read_bytes()]))',
          join(dir,name),marker,hasFiles?'yes':'no'],{encoding:'utf8',windowsHide:true});
        assert.equal(check.status,0,check.stderr);
        return JSON.parse(check.stdout);
      };
      assert.equal(await run('document.querySelector("[data-files=folder]").value'),'');
      const without=await exportImage();
      const [primary,,found]=readIso(without.path,false);
      assert(!Object.keys(primary).some(name=>name.includes('FIXTURE')||name.includes('fixture')));
      assert.equal(found,false);
      await run(`document.querySelector('[data-files=folder]').value=${JSON.stringify(source)};document.querySelector('[data-files=folder]').dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('[data-files=check]').click();`);
      await wait('document.querySelector("[data-files=list]").textContent.includes("fixture-local.txt")');
      const refusal=()=>run(`import('/home/design.js').then(design=>design.makeBurnFile()).then(()=>'',error=>error.message)`);
      assert.match(await refusal(),/确认随盘文件清单/);
      await run('document.querySelector("[data-files=confirm]").click()');
      await wait('document.querySelector("[data-files=status]").textContent.includes("已确认一次导出")');
      const withFiles=await exportImage();
      const [,joliet,foundAfter]=readIso(withFiles.path,true);
      assert.equal(foundAfter,true);
      assert.equal(joliet['fixture-local.txt'].bytes,Buffer.byteLength(marker));
      assert.match(await refusal(),/确认随盘文件清单/);
    });
    assert.deepEqual(errors,[]);
  }finally{
    await stopBrowser(browser,ws);
    server?.kill();
    if(resolve(dir).startsWith(resolve(tmpdir())+sep))await rm(dir,{recursive:true,force:true,maxRetries:8,retryDelay:200});
  }
});
