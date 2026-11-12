// Real DOM startup checks using synthetic local responses; no device or network requests.
import assert from 'node:assert/strict';
import {readFileSync, writeFileSync, mkdtempSync, existsSync} from 'node:fs';
import {rm} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {tmpdir} from 'node:os';
import {join, resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const edge = process.env.HANDSHAKE_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
assert.ok(existsSync(edge), 'Set HANDSHAKE_TEST_BROWSER to Chromium');
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
  for (const scenario of ['current','major','required','optional','offline']) {
   const frame=document.createElement('iframe');frame.style.width=width+'px';frame.style.height='844px';document.body.append(frame);
   const doc=frame.contentDocument;
   doc.open();doc.write('<html data-handshake="pending"><head><style>'+css+'</style></head><body><button id="workflow">Start</button><button data-capability="templates">Template</button></body></html>');doc.close();
   doc.documentElement.dataset.lang=lang;doc.documentElement.dataset.theme=theme;
   const core={api_version:scenario==='major'?'2.0':'1.0',capabilities:[...manifest.required_capabilities,...manifest.optional_capabilities].filter(c=>scenario==='required'?c!=='geo':scenario==='optional'?c!=='templates':true)};
   let started=false, calls=[];
   const fetcher=async (path,options)=>{calls.push(path);check(options.headers['X-Discprobe-Token']==='sample','session token preserved');if(scenario==='offline')throw Error('private technical detail');return {ok:true,json:async()=>path==='/gui.json'?manifest:core};};
   const promise=handshake(doc,fetcher,{protocol:'http:',search:'?token=sample'}).then(()=>{started=true;});
   // Flush the small promise chain without needing network or a wall-clock wait.
   for(let i=0;i<30;i++)await Promise.resolve();
   check(calls.includes('/api/version'),'version fetched');
   if(['current','optional'].includes(scenario)) {
    await promise;check(started&&doc.getElementById('workflow'),'compatible workflow starts');
    if(scenario==='optional') {
     const button=doc.querySelector('[data-capability]');check(button.hidden&&frame.contentWindow.getComputedStyle(button).display==='none','optional entry hidden');
     const later=doc.createElement('button');later.dataset.capability='templates';doc.body.append(later);check(frame.contentWindow.getComputedStyle(later).display==='none','later entry hidden');
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
  const run = spawnSync(edge, ['--headless=new','--disable-gpu','--disable-background-networking','--no-first-run','--no-default-browser-check',
    '--allow-file-access-from-files',`--user-data-dir=${join(dir,'profile')}`,'--virtual-time-budget=5000','--dump-dom',pathToFileURL(fixture).href],
    {encoding:'utf8',timeout:45000,windowsHide:true,maxBuffer:4*1024*1024});
  assert.ifError(run.error);
  const result=run.stdout.match(/<pre id="result">([\s\S]*?)<\/pre>/)?.[1];
  assert.match(result || run.stderr,/^PASS:/); console.log(result);
} finally {
  assert.ok(resolve(dir).startsWith(resolve(tmpdir()) + '\\discprobe-handshake-'));
  await rm(dir,{recursive:true,force:true,maxRetries:8,retryDelay:300});
}
