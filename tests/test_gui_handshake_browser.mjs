// Real DOM startup checks using synthetic local responses; no device or network requests.
import {runBrowser, selectBrowser} from './browser.mjs';
import assert from 'node:assert/strict';
import {readFileSync, writeFileSync, mkdtempSync} from 'node:fs';
import {rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const edge = selectBrowser({legacy: ['HANDSHAKE_TEST_BROWSER']});
const dir = mkdtempSync(join(tmpdir(), 'discprobe-handshake-'));
const home = new URL('../discprobe/web/home/', import.meta.url);
const manifest = JSON.parse(readFileSync(new URL('../gui.json', home), 'utf8'));
const index = readFileSync(new URL('index.html', home), 'utf8');
const css = index.match(/<style>([\s\S]*?)<\/style>/)[1];
assert.ok(index.indexOf('await handshake();') < index.indexOf('let backendState'), 'handshake precedes business startup');
const fixture = join(dir, 'test.html');
writeFileSync(fixture, `<!doctype html><meta charset="utf-8"><pre id="result">PENDING</pre><script type="module">
import {handshake} from '${new URL('handshake.mjs', home)}';
const manifest=${JSON.stringify(manifest)}, css=${JSON.stringify(css)};
const check=(v,m)=>{if(!v)throw Error(m)};
try {
 for (const width of [390,1440]) for (const theme of ['light','dark']) for (const lang of ['zh','en']) {
  for (const scenario of ['current','major','required','templates','library-management','library-batch-details','grid-templates','offline']) {
   const optional = manifest.optional_capabilities.includes(scenario);
   const frame=document.createElement('iframe');frame.style.width=width+'px';frame.style.height='844px';document.body.append(frame);
   const doc=frame.contentDocument;
   doc.open();doc.write('<html data-handshake="pending"><head><style>'+css+'</style></head><body><button id="workflow">Start</button></body></html>');doc.close();
   doc.documentElement.dataset.lang=lang;doc.documentElement.dataset.theme=theme;
   const entry=doc.createElement('button');entry.dataset.capability=optional?scenario:'templates';doc.body.append(entry);
   const other=doc.createElement('button');other.dataset.capability='works';doc.body.append(other);
   const older={'templates':'1.0','library-management':'1.3','library-batch-details':'1.4','grid-templates':'1.4'};
   const core={api_version:scenario==='major'?'2.0':(older[scenario]??'1.5'),capabilities:[...manifest.required_capabilities,...manifest.optional_capabilities].filter(c=>c!==(scenario==='required'?'geo':scenario))};
   let started=false, calls=[];
   const fetcher=async (path,options)=>{calls.push(path);check(options.headers['X-Discprobe-Token']==='sample','session token preserved');if(scenario==='offline')throw Error('private technical detail');return {ok:true,json:async()=>path==='/gui.json'?manifest:core};};
   const promise=handshake(doc,fetcher,{protocol:'http:',search:'?token=sample'}).then(()=>{started=true;});
   // Flush the small promise chain without needing network or a wall-clock wait.
   for(let i=0;i<30;i++)await Promise.resolve();
   check(calls.includes('/api/version'),'version fetched');
   if(scenario==='current'||optional) {
    await promise;check(started&&doc.getElementById('workflow'),'compatible workflow starts');
    if(optional) {
     check(entry.hidden&&frame.contentWindow.getComputedStyle(entry).display==='none','optional entry hidden: '+scenario);
     check(!other.hidden&&frame.contentWindow.getComputedStyle(other).display!=='none','other optional entry visible');
     const later=doc.createElement('button');later.dataset.capability=scenario;doc.body.append(later);check(frame.contentWindow.getComputedStyle(later).display==='none','later entry hidden: '+scenario);
    } else {
     check(!entry.hidden&&!other.hidden,'current core shows optional entries');
    }
   } else {
    check(!started&&!doc.getElementById('workflow'),'incompatible workflow never starts');
    check(doc.body.children.length===1&&doc.getElementById('gui-compatibility'),'one sheet only');
    check(!doc.body.textContent.includes('private technical detail'),'no technical error');
    const sheet=doc.getElementById('gui-compatibility');check(sheet.getBoundingClientRect().width<=width,'sheet fits');
    check(doc.documentElement.scrollWidth<=doc.documentElement.clientWidth+1,'no page overflow');
   }
   frame.remove();
  }
 }
 document.getElementById('result').textContent='PASS: handshake DOM, themes, languages, widths and startup';
} catch(e) {document.getElementById('result').textContent='FAIL: '+e.message;}
</script>`);
try {
  const run = runBrowser(edge, join(dir,'profile'), ['--mute-audio','--no-sandbox','--allow-file-access-from-files','--virtual-time-budget=5000','--dump-dom',pathToFileURL(fixture).href],
    {disableGpu: true, encoding:'utf8',timeout:45000,windowsHide:true,maxBuffer:4*1024*1024});
  assert.ifError(run.error);
  const result=run.stdout.match(/<pre id="result">([\s\S]*?)<\/pre>/)?.[1];
  assert.match(result || run.stderr,/^PASS:/); console.log(result);
} finally {
  assert.ok(resolve(dir).startsWith(resolve(tmpdir()) + '\\discprobe-handshake-'));
  await rm(dir,{recursive:true,force:true,maxRetries:8,retryDelay:300});
}
