import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as guidance from '../discprobe/web/home/guidance.mjs';
import * as photowords from '../discprobe/web/home/photowords.mjs';

// Execute the actual flow with a small host and a photo-page adapter. No drive, server or timers run.
const source = readFileSync(new URL('../discprobe/web/home/calibrate.js',import.meta.url),'utf8');
const strip = source.replace(/^import .*;.*$/gm,'').replace(/^export /gm,'');
const escapeHTML = v => String(v ?? '').replace(/[&<>"']/g,c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function fixture({media='dvd', verdict='narrow_span', missing, failJob, photoVerdict='ok', phone=null, photos=[], gate, savedShift={written:true,frames:2.5}}={}) {
  const nodes = new Map(), timers = new Map(), calls = [], show = [], pages = [];
  class Element {
    constructor() { this.dataset={}; this.hidden=false; this.disabled=false; this.style={removeProperty(){}}; this.children=[]; this.events={}; this.textContent=''; this.html=''; }
    classList={add(){},remove(){},toggle(){}};
    set innerHTML(v) { this.html=v; for(const m of v.matchAll(/id="([^"]+)"/g)) nodes.set(m[1],new Element()); }
    get innerHTML() { return this.html; }
    append(...children) { this.children.push(...children); for(const child of children) if(child?.id) nodes.set(child.id,child); }
    before() {}
    remove() { this.removed=true; }
    replaceChildren(...children) { this.children=children; }
    setAttribute(k,v) { this[k]=v; }
    addEventListener(k,fn) { this.events[k]=fn; }
    querySelector(s) { if(s==='.pc-paper') return this.paper ||= new Element(); return null; }
  }
  for(const id of ['cal','next','next-text','job','job-name','job-time','back']) nodes.set(id,new Element());
  const root = new Element(); root.dataset.mode='cal';
  const document = {documentElement:root,body:new Element(),createElement:()=>new Element(),getElementById:id=>nodes.get(id)||null};
  const geo = {path:'results/run-one',verdict,measurement:{span_mm:[28,48]}};
  const f = {realPhase:'review',geo,timing:{verdict:'good'},detected:{media,kind:media,mid:'MID',capacity_sectors:300000},item:{row:media},left:3,warnEl:new Element()};
  const api = {lang:()=> 'zh',selectedDrive:()=> 'FAKE:',burnerLayer:new Element(),nextWhy(){},jobProgress(){},
    backend:{mock:false,escapeHTML,errorText:e=>e.message,
      request:async (path,payload)=>{
        calls.push({path,payload});
        if(path.includes(missing || 'NEVER')) throw Object.assign(new Error('Not found'),{status:404});
        if(path.startsWith('/api/phone-link')) return {url:phone,qr_svg:null};
        if(path.startsWith('/api/photos')) return {photos};
        if(path.startsWith('/api/phone-devices')) return {devices:[{id:'phone1',name:'iPhone',first_seen:1000,last_seen:2000,photos_sent:2}]};
        return {};
      },
      job:async payload=>{
        calls.push(payload);
        if(failJob) throw Object.assign(new Error('Not found'),{status:404});
        if(payload.action==='disexport') return {path:'presets/test.json',photo_shift:savedShift};
        if(gate) await gate();
        return {verdict:photoVerdict,path:'results/run-one',per_photo:[{id:'p1',verdict:photoVerdict,reason:'反光强 <script>'}],rings_mm:[30,38,47,55],offset_mm:-0.12,L_frames:2.5};
      },
      state:async()=>({catalogue:{[media]:[{id:'saved',geo:geo.path,name:'MID'}]}}),
    }};
  let opts;
  const context = vm.createContext({...guidance,...photowords,photoSeconds:photowords.seconds,document,location:{search:''},URLSearchParams,console,
    flipValue:el=>el.textContent,nextConfirm:(btn,options={})=>{btn.hidden=!!options.active;btn.confirmOptions=options;},ringButton:()=>({progress(){},done(){},destroy(){}}),
    setTimeout:(fn,ms)=>{const id=timers.size+1;timers.set(id,{fn,ms});return id;},clearTimeout:id=>timers.delete(id),clearInterval(){},performance,
    loadDisc:{desk(){}},calchart:{resultChart:()=>''},sfx:{done(){},problem(){},failure(){}},
    floorLog:()=>({mount(){},start(){},end(){},title(){}}),
    photoPage:(host,o)=>{
      opts=o;
      const visible=[...o.photos];
      const p={reasons:[],destroy(){this.destroyed=true;},state:()=>({photos:visible,focus:false}),setReasons(v){this.reasons=v;},setPhotoId(){},
        setDevices(values){p.devices=values;},setPhoneLink(value){p.link=value;},addPhotos:async values=>{p.added=values;visible.push(...values);if(values.length)o.onPhotos?.();},back(){o.onBack();},use:()=>o.onUse({id:'p1'},[30,38,47,55])};
      o.paperHost.paper=new Element(); o.onStateChange({canUse:true}); pages.push(p); return p;
    },
  });
  vm.runInContext(strip+`; globalThis.wire={set(a,f){api=a;$=id=>document.getElementById(id);flow=f;discWentIn=true;st={show:v=>globalThis.shows.push(v),set(){}};},paint:realPaint,next:realNext,save:realSave,back,enterPhoto,closePhoto,photoRun,photoStamp,pollPhotos,queuePhotoRead,readPhoto,getUI:()=>photoUI};`,context);
  context.shows=show; context.wire.set(api,f);
  return {wire:context.wire,f,geo,nodes,calls,timers,pages,show,opts:()=>opts};
}
const flush=async()=>{for(let i=0;i<20;i++) await Promise.resolve();};

{
  const x=fixture();x.wire.enterPhoto();await flush();
  assert.equal(x.pages[0].devices[0].thisDevice,true);
  assert.equal(x.pages[0].devices[1].since,1000);
  assert.equal(x.pages[0].devices[1].sent,2);
  await x.opts().onDisconnect('phone1');await flush();
  assert.ok(x.calls.some(c=>c.path==='/api/phone-devices/phone1/disconnect'));
  assert.ok(x.pages[0].link,'rotation refreshes the link');
  x.wire.closePhoto();
}
{
  const x=fixture({missing:'/api/phone-devices'});x.wire.enterPhoto();await flush();
  assert.equal(x.wire.getUI().status,'ready','old server keeps photo work available');
  assert.equal(x.pages[0].devices,null,'unsupported devices piece hides');
  x.wire.closePhoto();
}

// The narrow-span action supplements the existing recovery action and returns to the same result.
{
  const x=fixture(); x.wire.paint();
  assert.match(x.nodes.get('cal').innerHTML,/拍一张照，补上外圈/);
  assert.match(x.nodes.get('next-text').textContent,/重测|测量/);
  x.nodes.get('real-photo').events.click(); await flush();
  assert.equal(x.f.realPhase,'photo'); assert.equal(x.show.at(-1),false);
  assert.match(x.nodes.get('cal-ruler')?.innerHTML || '', /拍照/); // ruler owns the photo segment
  assert.equal(x.opts().paperHost,x.nodes.get('cal'));
  assert.equal(typeof x.opts().autoAlign,'function');
  assert.equal(x.opts().phoneUrl,null);
  assert.equal([...x.timers.values()].find(t=>t.ms===2000)?.ms,2000);
  x.opts().onSkip();
  assert.equal(x.f.realPhase,'review'); assert.equal(x.f.geo,x.geo);
  assert.equal(x.show.at(-1),true); assert.equal(x.timers.size,0);
}
// A usable CD reaches photo through the existing Next button; DVD still uses the old save path.
for(const media of ['cd','dvd']) {
  const x=fixture({media,verdict:'good'}); x.wire.paint(); await x.wire.next(); await flush();
  assert.equal(x.f.realPhase,media==='cd'?'photo':'saved');
  if(media==='cd') { x.wire.back(); assert.equal(x.f.realPhase,'review'); }
}
for(const missing of ['/api/phone-link','/api/photos']) {
  for(const media of ['cd','dvd']) {
    const x=fixture({media,missing}); x.wire.enterPhoto(); await flush();
    assert.equal(x.pages.length,0,'404 must never expose phone or auto-align controls');
    assert.equal(x.wire.getUI().status,'unavailable');
    assert.match(x.nodes.get('cal').innerHTML,/照片暂不可用/);
    assert.equal(x.nodes.get('next').disabled,false,'Fallback always has a working exit');
    assert.equal(x.timers.size,0);
    if(media==='cd') assert.match(x.nodes.get('cal').innerHTML,/DIS/);
    await x.wire.next();
    assert.equal(x.f.realPhase,media==='cd'?'saved':'review');
  }
}
// Contract arguments pass through realJob; auto-align maps signed offsets and Next reuses its result.
{
  const x=fixture({media:'cd',phone:'http://lan/phone/token',photos:[{id:'p1',url:'/api/photos/run-one/p1'}]});
  x.wire.enterPhoto(); await flush();
  assert.equal(x.opts().phoneUrl,'http://lan/phone/token');
  const mapped=await x.opts().autoAlign({id:'p1'},[30,38,47,55]);
  assert.equal(mapped.offsetMm,-0.12);
  assert.deepEqual(JSON.parse(JSON.stringify(x.calls.find(c=>c.action==='photo').args)),{run:'run-one',media:'cd',photos:['p1'],rings_mm:[30,38,47,55],burner:null,burn_path:null,burn_mode:null});
  assert.equal(x.pages[0].reasons[0].reason,'反光强 <script>');
  assert.match(x.wire.getUI().result.innerHTML,/已采用/,'two agreeing photos: adopted');
  // Reasons are escaped; an unknown status keeps the core's own reason after a plain action.
  assert.match(x.wire.photoStamp({verdict:'unsure',per_photo:[{id:'p1',verdict:'unsure',reason:'反光强 <script>'}]}),/重拍：反光强 &lt;script&gt;/);
  // Adopted, then the core's own application gate: applied with its value, or why not.
  assert.match(x.wire.photoStamp({verdict:'ok',per_photo:[],adoption:{state:'adopted'},application:{written:true,L_mm:-2.12,frames:-12.98,disc_id:'T1'}}),/出图会用 L −2.120 mm · -12.98 frames（标靶盘 T1）/);
  assert.match(x.wire.photoStamp({verdict:'ok',per_photo:[],adoption:{state:'adopted'},application:{written:false,reason:'unknown_disc'}}),/<dd class="act">没填标靶盘号/);
  // Repeated advice is said once, with how many photos it applies to.
  assert.match(x.wire.photoStamp({verdict:'unsure',per_photo:[{id:'a',verdict:'unsure',status:'no_rim'},{id:'b',verdict:'unsure',status:'no_rim'}]}),/2 张 · 拍全盘/);
  // The two-photo rule: a single photo is provisional and a disagreement is said, neither is "usable".
  for (const [state, words] of [['provisional',/暂定.*再拍一张不同角度/s],['disagree',/两张不一致.*不用重刻/s],['refused',/不采用/s]]) {
    const html=x.wire.photoStamp({verdict:'ok',per_photo:[{id:'p1',verdict:'ok',status:'ok'}],adoption:{state,spread_mm:.31,reason:'same_pose'}});
    assert.match(html,words); assert.match(html,new RegExp(`data-adoption="${state}"`)); assert.doesNotMatch(html,/已采用/);
  }
  await x.wire.next();
  assert.equal(x.f.realPhase,'saved'); assert.equal(x.f.photoResult.L_frames,2.5);
  assert.equal(x.calls.filter(c=>c.action==='photo').length,1);
  assert.match(x.nodes.get('cal').innerHTML,/L = 2.5 frames/);
  assert.match(x.nodes.get('cal').innerHTML,/沿轨常数已写入/);
  assert.doesNotMatch(x.nodes.get('cal').innerHTML,/尚未写入预设|CD photo calibration is not ready/);
  const save=x.calls.find(c=>c.action==='disexport');
  assert.equal(save.args.photo,'results/run-one/photo.json');
  assert.equal(save.args.reading_drive,'FAKE:');
  assert.equal(save.args.L_frames,undefined);
}
// A browser result never overrules the decision returned by saving.
{
  const x=fixture({media:'cd',savedShift:{written:false,reason:'no_photo'}});
  x.f.preset='presets/previous.json';
  await x.wire.save();
  const save=x.calls.find(c=>c.action==='disexport');
  assert.ok(save,'recheck the selected drive even when reusing a preset without a new photo');
  assert.equal(save.args.reading_drive,'FAKE:');
  assert.equal(save.args.photo,undefined);
  assert.equal(x.f.savedPhotoShift.reason,'no_photo');
}
for (const reason of ['different_run','different_drive','verdict_not_ok','missing_L']) {
  const x=fixture({media:'cd',savedShift:{written:false,reason}});
  x.f.preset='presets/previous.json';
  x.wire.enterPhoto(); await flush(); await x.wire.next();
  assert.equal(x.f.realPhase,'saved');
  assert.ok(x.calls.some(c=>c.action==='disexport'),'an existing preset must be re-exported for photo L');
  assert.match(x.nodes.get('cal').innerHTML,/沿轨常数没写进去/);
  assert.doesNotMatch(x.nodes.get('cal').innerHTML,/沿轨常数已写入|尚未写入预设/);
}
for(const photoVerdict of ['unsure','rejected']) {
  const x=fixture({photoVerdict}); x.wire.enterPhoto(); await flush(); await x.wire.next();
  const u=x.wire.getUI();
  assert.equal(x.f.realPhase,'photo'); assert.equal(x.f.geo,x.geo);
  assert.equal(u.retry.hidden,false); assert.equal(u.skip.hidden,false);
  for(const label of ['意思','对你的图','现在']) assert.match(u.result.innerHTML,new RegExp(label));
  u.skip.onclick(); assert.equal(x.f.realPhase,'review');
  assert.ok(!x.calls.some(c=>c.action==='disexport'));
}
{
  const x=fixture({failJob:true}); x.wire.enterPhoto(); await flush(); await x.wire.next();
  assert.equal(x.wire.getUI().status,'unavailable');
  assert.equal(x.pages[0].destroyed,true); assert.equal(x.timers.size,0);
}
// Late initial responses cannot reopen a closed page or restart its timer.
{
  const x=fixture(); x.wire.enterPhoto(); x.wire.back(); await flush();
  assert.equal(x.f.realPhase,'review'); assert.equal(x.pages.length,0); assert.equal(x.timers.size,0);
}
{
  const x=fixture();
  assert.equal(x.wire.photoRun({geo:{path:'D:\\results\\a run\\'}}),'a run');
  assert.equal(x.wire.photoRun({}),null);
}
console.log('Photo routing, contract jobs, polling lifecycle, verdicts, saved L and 404 fallback passed');

async function fire(x,ms) {
  const entry=[...x.timers].find(([id,t])=>t.ms===ms);assert.ok(entry,`Missing ${ms} timer`);
  x.timers.delete(entry[0]);entry[1].fn();await flush();
}
{
  const photos=[{id:'p1',url:'/1'}], x=fixture({photos});x.wire.enterPhoto();await flush();
  assert.equal(x.calls.filter(c=>c.action==='photo').length,0,'arrival waits for debounce');
  assert.equal(x.opts().automaticRead,true);
  assert.equal(typeof x.opts().onAddress,'function');
  photos.push({id:'p2',url:'/2'});await x.wire.pollPhotos(x.wire.getUI());await flush();
  assert.equal([...x.timers.values()].filter(t=>t.ms===1500).length,1,'burst resets one debounce');
  x.f.burnCheck={result:'completed',burner:'WRITER:',burn_path:'IMAPI',burn_mode:'mode2form1; physical interleave unknown'};
  await fire(x,1500);
  const jobs=x.calls.filter(c=>c.action==='photo');assert.equal(jobs.length,1);
  assert.deepEqual(Array.from(jobs[0].args.photos),['p1','p2']);assert.equal(jobs[0].args.rings_mm,null,'default reader design, no manual ring guesses');
  assert.equal(jobs[0].args.burner,'WRITER:');assert.equal(jobs[0].args.burn_path,'IMAPI');
  assert.equal(jobs[0].args.burn_mode,'mode2form1; physical interleave unknown');
  assert.equal(x.nodes.get('next').disabled,false);x.wire.closePhoto();
}
{
  let release;const photos=[{id:'p1',url:'/1'}];
  const x=fixture({photos,gate:()=>new Promise(resolve=>{release=resolve;})});x.wire.enterPhoto();await flush();await fire(x,1500);
  assert.equal(x.calls.filter(c=>c.action==='photo').length,1);
  photos.push({id:'p2',url:'/2'},{id:'p3',url:'/3'});await x.wire.pollPhotos(x.wire.getUI());await fire(x,1500);
  assert.equal(x.calls.filter(c=>c.action==='photo').length,1,'never overlap photo jobs');
  release();await flush();await fire(x,1500);
  const jobs=x.calls.filter(c=>c.action==='photo');assert.equal(jobs.length,2);
  assert.deepEqual(Array.from(jobs[1].args.photos),['p1','p2','p3'],'new arrivals rerun the whole run');
  release();await flush();x.wire.closePhoto();
}
{
  const x=fixture({media:'cd',photos:[{id:'server-readable',url:'/unsupported.heic'}]});
  x.wire.enterPhoto();await flush();
  x.pages[0].state=()=>({photos:[],activePhoto:-1});
  await fire(x,1500);await x.wire.next();
  assert.equal(x.f.realPhase,'saved','a missing browser thumbnail must not block a server-readable photo');
}
