import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as guidance from '../discprobe/web/home/guidance.mjs';

const html=readFileSync(new URL('../discprobe/web/phone/index.html',import.meta.url),'utf8');
const source=html.match(/<script type="module">([\s\S]*?)<\/script>/)[1].replace(/^\s*import .*;$/m,'');
const jpegSource=source.slice(source.indexOf('async function jpegPhoto'),source.indexOf('async function response'));
const file={name:'相片.HEIC',type:'image/heic'};
function encoder({bitmap=true, ignored=false, throws=false, imgFails=false, blob=true, nullBlob=false, width=6000, height=4000}={}) {
  const calls=[], closed=[], revoked=[];
  const canvas={width:0,height:0,getContext:()=>({drawImage(image,x,y,w,h){calls.push({w,h,image});}}),toDataURL:(type,q)=>{calls.push({type,q,fallback:true});return 'data:image/jpeg;base64,aGk=';}};
  if(blob)canvas.toBlob=(cb,type,q)=>{calls.push({type,q});cb(nullBlob?null:new Blob(['jpeg'],{type}));};
  class Image {naturalWidth=width;naturalHeight=height;set src(v){calls.push({img:v});queueMicrotask(()=>imgFails?this.onerror():this.onload());}}
  const context=vm.createContext({document:{createElement:()=>canvas},Image,Blob,Uint8Array,atob,URL:{createObjectURL:()=> 'blob:photo',revokeObjectURL:v=>revoked.push(v)}});
  if(bitmap)context.createImageBitmap=async(f,options)=>{
    assert.equal(f,file);if(throws)throw new Error('decoder unavailable');
    if(!ignored)assert.equal(options.imageOrientation,'from-image');
    return {width,height,close(){closed.push(true);}};
  };
  vm.runInContext(jpegSource+';globalThis.jpegPhoto=jpegPhoto;',context);
  return {run:()=>context.jpegPhoto(file),calls,closed,revoked,canvas};
}
for(const options of [{},{bitmap:false},{ignored:true},{throws:true},{blob:false},{nullBlob:true}]) {
  const x=encoder(options), result=await x.run();
  assert.equal(result.type,'image/jpeg');assert.equal(result.name,'相片.jpg');assert.equal(result.body.type,'image/jpeg');
  const size=x.calls.find(c=>c.w);assert.equal(size.w,4096);assert.equal(size.h,2730);
  assert.ok(size.w*size.h<16777216);
  assert.ok(x.calls.some(c=>c.type==='image/jpeg'&&c.q===.95));
  if(options.bitmap===false||options.ignored||options.throws)assert.deepEqual(x.revoked,['blob:photo']);
  assert.equal(x.canvas.width,1,'release large canvas backing storage');
}
for(const dimensions of [{width:100,height:50},{width:5000,height:5000},{width:3000,height:6000}]) {
  const x=encoder(dimensions);await x.run();const size=x.calls.find(c=>c.w);
  assert.ok(Math.max(size.w,size.h)<=4096);assert.ok(size.w*size.h<16777216);
  assert.ok(size.w<=dimensions.width&&size.h<=dimensions.height);
}
const fail=encoder({throws:true,imgFails:true});assert.equal((await fail.run()).body,file,'decode failure sends original');
assert.deepEqual(fail.revoked,['blob:photo']);
for(const status of ['ok','no_rim','weak_peak','duplicate_photo']) {
  assert.ok(guidance.photoReasons[status].zh);assert.ok(guidance.photoReasons[status].en);
}
assert.deepEqual(guidance.photoReasonWords({status:'out_of_focus',reason:'Tap to focus.'}),{zh:'Tap to focus.',en:'Tap to focus.'});
assert.equal(guidance.photoStateWords({}).en,'Reading');
assert.equal(guidance.photoStateWords({verdict:'ok'}).en,'Usable');
assert.match(guidance.photoStateWords({verdict:'unsure',status:'no_rim'}).en,/Retake:.*whole disc/);
assert.match(guidance.photoOverallWords([],null).zh,/还没收到照片/);
assert.match(guidance.photoOverallWords([{verdict:'ok'}],'unsure').zh,/能用 1 张。再拍 2 张/);
assert.match(guidance.photoOverallWords([{verdict:'ok'},{}],'unsure').zh,/正在读/);
assert.match(guidance.photoOverallWords([{verdict:'ok'},{verdict:'ok'}],'ok').en,/That's enough/);
assert.doesNotMatch(guidance.photoOverallWords([{verdict:'ok'},{}],'ok').en,/enough/);
// Every current server reason has one shared translation. A future code falls back unchanged.
const py=readFileSync(new URL('../discprobe/photo.py',import.meta.url),'utf8');
for(const code of [...py.match(/REASONS = \{([\s\S]*?)\n\}/)[1].matchAll(/"([\w]+)":/g)].map(m=>m[1]))assert.ok(guidance.photoReasons[code],code);

class Element {
  constructor(){this.children=[];this.textContent='';this.events={};this.classList={add(){},remove(){}};}
  append(...nodes){this.children.push(...nodes);}replaceChildren(){this.children=[];}
  addEventListener(name,fn){this.events[name]=fn;}click(){this.clicked=true;}
}
const nodes=Object.fromEntries(['config','status','error','sent','camera'].map(id=>[id,new Element()]));
nodes.config.textContent=JSON.stringify({run:'run-one',token:'phone-token'});
const shots=[{id:'mine',name:'mine.jpg',url:'/api/photos/run-one/mine'}, {id:'other',name:'other.jpg',url:'/api/photos/run-one/other'}];
const requests=[], timers=[];
const context=vm.createContext({...guidance,Blob,Uint8Array,atob,URLSearchParams,Set,console,
  document:{hidden:false,getElementById:id=>nodes[id],querySelectorAll:()=>[],createElement:()=>new Element(),createTextNode:t=>t},
  sessionStorage:{getItem:()=> '["mine"]',setItem(){}},
  fetch:async(path,opts)=>{requests.push({path,opts});return {ok:true,json:async()=>({photos:shots,verdict:'unsure'})};},
  setInterval:(fn,ms)=>timers.push({fn,ms}),
});
vm.runInContext(source+';globalThis.refresh=refresh;',context);
const flush=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};await flush();
assert.equal(timers[0].ms,2000);assert.equal(requests[0].opts.headers['X-Photo-Token'],'phone-token');
assert.equal(nodes.sent.children.length,1,'only this phone sends are shown');
assert.match(nodes.sent.children[0].children[1].textContent,/读取中.*Reading/);
shots[0].verdict='unsure';shots[0].status='no_rim';await context.refresh();
let item=nodes.sent.children[0];assert.match(item.children[1].textContent,/重拍.*whole disc/);
assert.equal(item.children[2].textContent,'重拍 / Retake');item.children[2].onclick();assert.equal(nodes.camera.clicked,true);
shots[0].verdict='ok';await context.refresh();assert.match(nodes.sent.children[0].children[1].textContent,/可以用.*Usable/);
assert.match(html, /capture="environment"/);assert.doesNotMatch(html, /:has\(|structuredClone|user-scalable=no|\bdvh\b/);
assert.match(html,/id="gallery"[^>]*type="file"[^>]*accept="image\/\*"/);
console.log('Phone JPEG paths, decoder/encoder fallbacks, scoped status polling and shared reasons passed');
