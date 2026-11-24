import {runBrowser, selectBrowser} from './browser.mjs';
import assert from 'node:assert/strict';
import {readFileSync, readdirSync, writeFileSync, mkdtempSync, rmSync} from 'node:fs';
import {join, resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {pathToFileURL, fileURLToPath} from 'node:url';
import vm from 'node:vm';
import {observeActivity, dataURLBlob} from '../discprobe/web/home/kit/shared.js';
import {LampPreview} from '../discprobe/web/home/design/editor-lamp.mjs';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
const source = name => readFileSync(join(root, 'discprobe/web/home', name), 'utf8');
// Extract the actual handlers, so changing an entry's behavior changes this test.
function body(text, marker) {
  let start = text.indexOf(marker); assert(start >= 0, marker);
  start = text.indexOf('{', start + marker.length);
  let depth = 1, end = start + 1;
  for (; depth; end++) { assert(end < text.length, marker); if (text[end] === '{') depth++; if (text[end] === '}') depth--; }
  return text.slice(start + 1, end - 1);
}
const entries = [
  ['calibration name', 'calibrate.js', '$("newname")?.addEventListener("keydown", (e) =>', 'e', 'const next=hit;'],
  ['layer rename', 'design.js', 'inp.addEventListener("keydown", (ev) =>', 'ev', 'const done=hit;'],
  ['mask rename', 'design/editor-controls.mjs', 'input.onkeydown=e=>', 'e', 'const finish=hit;'],
  ['fax source', 'faxnews.js', 'input.addEventListener("keydown", (e) =>', 'e', 'const go=hit;'],
  ['new work name', 'newplan.js', 'W.name.addEventListener("keydown", (e) =>', 'e', 'const next=hit;'],
  ['batch suggestions', 'newplan.js', 'W.batch.addEventListener("keydown", (e) =>', 'e', 'const W={batchMenu:{hidden:false}},state={active:0,matches:[{}]},pickBatch=hit,hideMatches=()=>{};'],
  ['terminal command', 'terminal.js', 'function key(e)', 'e', 'const W={input:{value:"test"}},enter=hit;'],
  ['library rename', 'pastworks.js', 'input.addEventListener("keydown", (k) =>', 'k', 'const finish=hit;'],
  ['mask list', 'design/editor-controls.mjs', '  listKey(e)', 'e', '', '{maskClick:hit}'],
  ['layer list', 'design/editor-ui.mjs', '  layerKey(e)', 'e', '', '{s:{layers:[{id:"row"}]}}'],
  ['canvas drawing', 'design/editor-ui.mjs', '  key(e)', 'e', '', '{h:{dom:()=>({canvas:input}),draw(){}},tool:"pen",pointer:hit}'],
  ['return animation', 'newplan.js', 'const skip = e =>', 'e', 'const returning={disc:{abort:hit},anims:[],skipped:false},W={classList:{add(){},remove(){}}};'],
  ['filing animation', 'newplan.js', 'const skip = (e) =>', 'e', 'let skipped=false,timer=0;const wake=hit,W={classList:{add(){}}};'],
  ['library animation', 'pastworks.js', 'function keydown(e)', 'e', 'const active=()=>true,typing=()=>false,undoing=null,phase="loading",flight=true,search={},skip=hit; const back=()=>{};'],
];
let assertions = '';
for (const [name, file, marker, event, setup, ctx] of entries) {
  const callback = body(source(file), marker);
  const nodeKind = name.includes('list') || name.includes('animation') ? 'div' : name === 'canvas drawing' ? 'canvas' : 'input';
  assertions += `{
    let count=0;const hit=()=>count++,input=document.createElement('${nodeKind}');document.body.append(input);
    input.closest=selector=>['input','button,input','#back'].includes(selector)?null:input;
    input.dataset.id='row';input.click=hit;
    ${setup}
    const listener=(function(${event}){${callback}}).bind(${ctx || 'null'});
    input.addEventListener('keydown',listener);
    for(const options of [{isComposing:true},{keyCode:229},{}]){
      if(options.keyCode===229)input.dispatchEvent(new CompositionEvent('compositionend'));
      count=0;input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true,...options}));
      check(count===(!options.isComposing&&options.keyCode!==229?1:0),${JSON.stringify(name)}+' '+JSON.stringify(options)+' count='+count);
    }
    input.remove();
  }\n`;
}

// Every raw Enter decision must be the shared guard or an explicit, local exception.
let raw = 0;
function audit(dir) {
  for (const item of readdirSync(dir, {withFileTypes:true})) {
    if (/b[l]ind/i.test(item.name)) continue;
    const path = join(dir,item.name);
    if (item.isDirectory()) audit(path);
    else if (/\.(?:js|mjs|html)$/.test(item.name)) {
      let code=readFileSync(path,'utf8');
      if(path.endsWith('.html'))code=[...code.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map(m=>m[1]).join('\n');
      const lines = code.split('\n');
      for (let i=0;i<lines.length;i++) {
        const line=lines[i];
        // Deliberately broad: also catches switch/case, aliases and array membership.
        const decision=/['"](?:Enter|NumpadEnter)['"]|\bkeyCode\s*={2,3}\s*13\b/.test(line);
        if (!decision || /^\s*\/\//.test(line)) continue;
        raw++;
        assert(line.startsWith('export const isActionEnter =') && path.endsWith(join('kit','shared.js')) || /ime-enter-exempt:/.test(line+'\n'+(lines[i-1]||'')), path+':'+(i+1)+' must use isActionEnter or explain its exception');
      }
    }
  }
}
audit(join(root,'discprobe/web')); audit(join(root,'disclab/web'));

// Test visibility + intersection together, including unsupported IntersectionObserver and cleanup.
const events=new Map(), visibility=[], observers=[];
const doc={hidden:false,addEventListener:(n,f)=>events.set(n,f),removeEventListener:n=>events.delete(n),
  defaultView:{IntersectionObserver:class{constructor(cb){this.cb=cb;observers.push(this);}observe(){}disconnect(){this.disconnected=true;}}}};
const dispose=observeActivity({ownerDocument:doc}, active=>visibility.push(active));
observers[0].cb([{isIntersecting:false}]);doc.hidden=true;events.get('visibilitychange')();
observers[0].cb([{isIntersecting:true}]);doc.hidden=false;events.get('visibilitychange')();
assert.deepEqual(visibility,[true,false,true]);dispose();assert(observers[0].disconnected);assert.equal(events.size,0);
doc.defaultView={};const fallback=[];const stop=observeActivity({ownerDocument:doc},v=>fallback.push(v));
doc.hidden=true;events.get('visibilitychange')();assert.deepEqual(fallback,[true,false]);stop();
assert.equal(await dataURLBlob('data:text/plain;base64,SGk=').text(),'Hi');
assert.equal(await dataURLBlob('data:text/plain,%E4%B8%AD').text(),'\u4e2d');

// The Lab's real polling closures: hiding cancels both timers, resuming overlaps
// neither a pending job request nor a slow status request.
const labSource=readFileSync(join(root,'disclab/web/lab.js'),'utf8'),timers=new Map();
let timerId=0,jobCalls=0,statusCalls=0,answerJob,answerStatus;
const lab=vm.createContext({
  setTimeout:fn=>{timers.set(++timerId,fn);return timerId},clearTimeout:id=>timers.delete(id),clearInterval:id=>timers.delete(id),
  api:()=>{jobCalls++;return new Promise(r=>answerJob=r)},refresh:()=>{statusCalls++;return new Promise(r=>answerStatus=r)},
  paintJob(){},paint(){},toast(){},errText(){},tr(){},Date,
});
vm.runInContext(`
let job=null,lastJob=null,jobTimer=0,resumeJob=null,jobPolling=false,pageActive=true,lookTimer=0,resumeLook=null,holdT=null,looking=false;
function watch(id){${body(labSource,'function watch(id)')}}
async function look(){${body(labSource,'const look = async () =>')}}
resumeLook=look;
function activity(active){${body(labSource,'observeActivity(document.body, active =>')}}
globalThis.start=()=>watch('fake');globalThis.activity=activity;globalThis.look=look;
globalThis.resume=()=>resumeJob?.();
globalThis.clearJob=()=>{job=null;resumeJob=null;};
`,lab);
lab.start();assert.equal(timers.size,1);lab.activity(false);assert.equal(timers.size,0);
await lab.resume();assert.equal(jobCalls,0);
lab.activity(true);assert.equal(jobCalls,1);assert.equal(statusCalls,0,'job polling owns refresh while a job runs');
lab.activity(false);lab.activity(true);assert.equal(jobCalls,1);assert.equal(statusCalls,0);
answerJob({state:'running'});for(let i=0;i<8;i++)await Promise.resolve();
assert.equal(timers.size,2);lab.activity(false);assert.equal(timers.size,0);
lab.clearJob();lab.activity(true);assert.equal(statusCalls,1);
lab.activity(false);lab.activity(true);assert.equal(statusCalls,1,'slow status never overlaps on visibility changes');
answerStatus();for(let i=0;i<8;i++)await Promise.resolve();assert.equal(timers.size,1);lab.activity(false);assert.equal(timers.size,0);

// Suspension actually stops worker CPU and ignores a bitmap decoding across pause/resume.
const workers=[];let decode;
const lamp=new LampPreview({worker:()=>{const w={postMessage(){},terminate(){this.dead=true;}};workers.push(w);return w;},bitmap:()=>new Promise(r=>decode=r)});
const args={rev:1,document:()=>({}),pose:{},screen:200};lamp.view(args);
const old=workers[0].onmessage;
const pending=lamp.message({type:'frame',id:1,rev:1,pose:{},size:200,k:1,image:{}});
lamp.pause();assert(workers[0].dead);assert.equal(lamp.inflight,null);
lamp.view(args);const image={close(){this.closed=true;}};decode(image);await pending;
assert(image.closed);assert.equal(lamp.shown,null);old({data:{type:'error',rev:1,error:'stale'}});assert.notEqual(lamp.phase,'error');lamp.dispose();

const edge=selectBrowser({legacy: ['KIT_TEST_BROWSER']});
const dir=mkdtempSync(join(tmpdir(),'discprobe-ime-'));
try {
  const fixture=join(dir,'ime.html');
  writeFileSync(fixture,`<!doctype html><html><head><meta charset="utf-8"></head><body><pre id="result">PENDING</pre><script type="module">
import {isActionEnter} from '${pathToFileURL(join(root,'discprobe/web/home/kit/shared.js')).href}';
const check=(ok,msg)=>{if(!ok)throw Error(msg)};
try{${assertions}document.getElementById('result').textContent='PASS: 14 entries x 3 synthetic KeyboardEvents';}
catch(e){document.getElementById('result').textContent='FAIL: '+e.stack;}
</script></body></html>`);
  const r=runBrowser(edge, join(dir,'profile'), ['--mute-audio','--no-sandbox','--allow-file-access-from-files',
    '--virtual-time-budget=5000','--dump-dom',pathToFileURL(fixture).href],{disableGpu: true, encoding:'utf8',timeout:30000,windowsHide:true});
  assert.ifError(r.error);
  const report=r.stdout.match(/<pre id="result">([\s\S]*?)<\/pre>/)?.[1];
  assert.equal(report,'PASS: 14 entries x 3 synthetic KeyboardEvents');
  console.log(`IME: 14 real handlers x 3 KeyboardEvents; ${raw} raw Enter decisions audited; activity conjunction/fallback/disposal; worker pause/decode race; data URL decode passed`);
} finally { assert.equal(resolve(dir,'..'),resolve(tmpdir()));rmSync(dir,{recursive:true,force:true,maxRetries:5,retryDelay:200}); }
