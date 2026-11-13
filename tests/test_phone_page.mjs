import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as words from '../discprobe/web/home/photowords.mjs';

const html=readFileSync(new URL('../discprobe/web/phone/index.html',import.meta.url),'utf8');
const source=html.match(/<script type="module">([\s\S]*?)<\/script>/)[1].replace(/^\s*import .*;$/m,'');
const jpegSource=source.slice(source.indexOf('async function jpegPhoto'),source.indexOf('// XMLHttpRequest'));
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

// ---- words: every reader status has an action and a reason in both languages; nothing is made up --------------
const py=readFileSync(new URL('../discprobe/photo.py',import.meta.url),'utf8');
for(const code of [...py.match(/REASONS = \{([\s\S]*?)\n\}/)[1].matchAll(/"([\w]+)":/g)].map(m=>m[1])) {
  const r=words.photoReasons[code];assert.ok(r,code);
  for(const lang of ['zh','en']){assert.ok(r.act[lang]&&r.why[lang],code+' '+lang);}
}
// The actions the task names map to the statuses that cause them.
assert.equal(words.photoReasons.no_rim.act.zh,'拍全盘');
assert.equal(words.photoReasons.too_few_votes.act.zh,'换光照');assert.match(words.photoReasons.too_few_votes.why.zh,/吸顶灯.*20–30°.*白色圆形反光/);
assert.equal(words.photoReasons.poor_angle_coverage.act.zh,'转一下盘');
assert.equal(words.photoReasons.poor_radius_coverage.act.zh,'补内外圈');
// A future status keeps the core's own reason, after a plain "retake".
assert.deepEqual(words.photoReasonWords({status:'out_of_focus',reason:'Tap to focus.'}),{zh:'重拍：Tap to focus.',en:'Retake: Tap to focus.'});
assert.deepEqual(words.photoReasonWords({verdict:'ok',status:'ok'}),words.photoReasons.ok.why);

// ---- stages and times come from the listing, in the computer's clock ---------------------------------------
const base={now:1100,read_at:1060,read_photos:['a'],analysis:{state:'done',photos:['a'],seconds:33,started_at:1027,finished_at:1060}};
let s=words.photoStage({id:'a',time:1000,verdict:'unsure',status:'no_rim'},base);
assert.equal(s.stage,'retake');assert.equal(s.act.zh,'拍全盘');assert.match(s.when.zh,/收到后 1 分 0 秒 读完（读取本身 33 秒）/);
s=words.photoStage({id:'a',time:1000,verdict:'ok',status:'ok'},base);assert.equal(s.stage,'ok');
s=words.photoStage({id:'b',time:1090},{now:1100,analysis:{state:'reading',photos:['b'],seconds:7}});assert.equal(s.stage,'reading');assert.match(s.why.zh,/已 7 秒/);
s=words.photoStage({id:'c',time:1090},{now:1100,analysis:{state:'reading',photos:['b'],seconds:7}});assert.equal(s.stage,'queued');
s=words.photoStage({id:'b',time:1090},{now:1100,analysis:{state:'failed',photos:['b'],seconds:7}});assert.equal(s.stage,'failed');
s=words.photoStage({id:'d',time:1090},{now:1100});assert.equal(s.stage,'waiting');assert.match(s.why.zh,/已 10 秒/);
assert.deepEqual(words.seconds(125),{zh:'2 分 5 秒',en:'2 min 5 s'});
// Never a live camera judgement.
for(const st of ['retake','ok','reading','queued','waiting'])assert.doesNotMatch(JSON.stringify(words.photoStage({id:'a',verdict:st==='ok'?'ok':st==='retake'?'unsure':undefined},{})),/实时|live/i);

// ---- adoption: adopted / provisional / disagree / none ------------------------------------------------------
assert.equal(words.adoptionWords({state:'adopted',n_agree:2,spread_mm:.012}).title.zh,'已采用');
assert.match(words.adoptionWords({state:'adopted',n_agree:2,spread_mm:.012}).body.zh,/2 张不同角度的照片读数一致，采用它们的中位数/);
assert.match(words.adoptionWords({state:'provisional'}).body.zh,/临时 L，尚未采用.*再拍一张不同角度.*不用重刻/);
assert.match(words.adoptionWords({state:'disagree',spread_mm:.4}).body.zh,/对不上.*0.400 mm.*不用重刻/);
assert.equal(words.adoptionWords({},[]).title.zh,'还没有照片');
assert.equal(words.adoptionWords({},[{id:'a'}]).title.zh,'等待读取');
assert.equal(words.adoptionWords({},[{id:'a',verdict:'unsure'}]).title.zh,'还没有可用的');
// The majority rule: outliers are named and get a retake; a two-camp tie names nobody.
{
  const outliers=[{id:'x',name:'IMG_7912.jpeg',L_mm:.3175}];
  const adopted=words.adoptionWords({state:'adopted',agreeing_count:3,ok_count:4,required_count:3,outliers});
  assert.match(adopted.body.zh,/4 张可用照片里 3 张读数一致.*中位数.*这几张和多数不一致.*建议转盘重拍：IMG_7912\.jpeg/);
  const split=words.adoptionWords({state:'split',agreeing_count:3,ok_count:6,required_count:4,outliers});
  assert.equal(split.title.zh,'分成两派');assert.match(split.body.zh,/两组读数分成了两派（各 3 张）.*请再拍几张不同角度/);
  assert.doesNotMatch(split.body.zh,/IMG_7912/,'a tie names no outlier');
  assert.match(words.adoptionWords({state:'disagree',agreeing_count:3,ok_count:6,required_count:4,outliers}).body.zh,/最多 3 张读数一致，没到 6 张可用照片的三分之二（4 张）.*IMG_7912/);
  assert.equal(words.adoptionWords({state:'disagree',ok_count:2}).title.zh,'两张不一致');
  assert.equal(words.photoStage({id:'x',verdict:'ok',status:'ok'},{adoption:{state:'adopted',outliers}}).stage,'outlier');
  assert.equal(words.photoStage({id:'x',verdict:'ok',status:'ok'},{adoption:{state:'split'},outliers}).stage,'ok');
  assert.equal(words.photoStage({id:'y',verdict:'ok',status:'ok'},{adoption:{state:'adopted',outliers}}).stage,'ok');
  const many=words.outlierWords([1,2,3,4,5].map(i=>({id:'p'+i,name:'n'+i})));assert.match(many.zh,/n1、n2、n3 等 5 张/);
}
// The computer page that starts reads: open, closed, or moved to another run.
assert.equal(words.deskWords({photos:[{id:'a'}],desk_age:2}).state,'open');
assert.equal(words.deskWords({photos:[{id:'a'}],desk_age:40}).state,'closed');
assert.equal(words.deskWords({photos:[{id:'a'}],desk_age:null}).state,'closed');
assert.equal(words.deskWords({photos:[{id:'a',verdict:'ok'}],desk_age:40}).state,'open','nothing waits: nothing to say');
assert.match(words.deskWords({desk_elsewhere:true}).words.zh,/另一次标定.*不会挂到新的上/);
assert.ok(words.shootingTips.some(t=>/背对/.test(t.zh))&&words.shootingTips.some(t=>/白色圆形反光/.test(t.zh)));
// The core's two-pose rule: provisional shows its value as provisional, refusals say which check failed.
assert.match(words.adoptionWords({state:'provisional',provisional_mm:-2.1234}).body.zh,/临时 L −2.123 mm，尚未采用.*转一下盘/);
assert.doesNotMatch(words.adoptionWords({state:'provisional'}).body.zh,/L 0|0\.000/,'no value is never shown as zero');
for (const reason of ['same_pose','duplicate_photo','unknown_spread_or_pose','unknown_photo_input','group_not_ok']) {
  const w=words.adoptionWords({state:'refused',reason});assert.equal(w.title.zh,'不采用');assert.ok(w.body.zh&&w.body.en,reason);
}
assert.match(words.adoptionWords({state:'refused',reason:'same_pose'}).body.zh,/10°/);
// Applied to pictures only through the core's gate; every refusal it can give has words.
const py2=readFileSync(new URL('../discprobe/photo.py',import.meta.url),'utf8');
for (const code of new Set([...py2.matchAll(/(?:refused|no)\("([A-Za-z_]+)/g)].map(m=>m[1]))) assert.ok(words.applicationReasons[code],code);
assert.match(words.applicationWords({written:true,L_mm:-2.12,frames:-12.985,sectors:-.33,disc_id:'T1'},'cd').words.zh,/−2.120 mm · -12.98 frames（标靶盘 T1）/);
assert.match(words.applicationWords({written:true,L_mm:.5,frames:3,sectors:.012},'dvd').words.en,/\+0.500 mm · 0.012 sectors/);
assert.doesNotMatch(words.applicationWords({written:true,L_mm:.5,frames:3,sectors:.012},'dvd').words.en,/frames/,'DVD never in CD frames');
assert.match(words.applicationWords({written:false,reason:'unknown_disc'}).words.zh,/标靶盘号/);
assert.match(words.applicationWords({written:false,reason:'unknown_burn_path'}).words.zh,/不能说已修正/);
assert.match(words.photoLWords({written:true,L_mm:1,sectors:.5,reader_version:'v1'},'dvd',{reopened:true}).zh,/沿用此 ISO 已保存的 L \+1.000 mm/);
assert.match(words.photoLWords({written:false,reason:'opted_out'}).zh,/没有用照片 L：.*不用照片修正/);

// ---- the page itself, with a small DOM ----------------------------------------------------------------------
class Element {
  constructor(tag){this.tagName=tag;this.children=[];this.textContent='';this.events={};this.dataset={};this.style={};this.hidden=false;this.disabled=false;
    const set=new Set();this.classList={add:c=>set.add(c),remove:c=>set.delete(c),toggle:(c,on)=>on?set.add(c):set.delete(c),contains:c=>set.has(c)};}
  append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}
  addEventListener(name,fn){this.events[name]=fn;}setAttribute(k,v){this[k]=v;}click(){this.clicked=true;}
  closest(){return this.parent||new Element('label');}
  get innerText(){return [this.textContent,...this.children.map(c=>typeof c==='string'?c:c.innerText)].join(' ');}
}
const ids=['config','link','title','lede','chip','gallery-text','shutter-text','tips-title','diagram','d-lamp','d-phone','d-disc','photos-title','count','foot',
  'run','disc','overall','problem','tips','tip-list','empty','sent','camera','gallery'];
// The page in a small DOM, for a phone set to `language`. `answer` is what the computer replies next.
function mount(language) {
  const nodes=Object.fromEntries(ids.map(id=>[id,new Element('div')]));
  nodes.camera.parent=new Element('label');nodes.gallery.parent=new Element('label');
  nodes.config.textContent=JSON.stringify({run:'run-one',token:'phone-token'});
  const state={answer:{status:200,body:{photos:[],adoption:{state:'none'},now:1000,desk_age:1}}}, requests=[];
  const context=vm.createContext({...words,Blob,Uint8Array,atob,URLSearchParams,Set,Map,JSON,Math,Number,Date,console,
    document:{hidden:false,documentElement:{},getElementById:id=>nodes[id],querySelectorAll:()=>[nodes.camera,nodes.gallery],createElement:t=>new Element(t),addEventListener(){}},
    navigator:{onLine:true,language},addEventListener(){},
    sessionStorage:{getItem:()=> '[]',setItem(){}},URL:{createObjectURL:()=> 'blob:x',revokeObjectURL(){}},
    fetch:async(path,opts)=>{requests.push({path,opts});const a=state.answer;if(a.status===0)throw new TypeError('Failed to fetch');return {ok:a.status<300,status:a.status,statusText:'x',json:async()=>a.body};},
    setTimeout:()=>0,clearTimeout(){},setInterval(){},
  });
  vm.runInContext(source+';globalThis.poll=poll;globalThis.render=render;',context);
  return {nodes,context,state,requests};
}
const flush=async()=>{for(let i=0;i<20;i++)await Promise.resolve();};
{
  const {nodes,context,state,requests}=mount('zh-CN');await flush();
  assert.equal(requests[0].opts.headers['X-Photo-Token'],'phone-token');
  assert.equal(requests[0].path,'/api/photos?run=run-one');
  assert.equal(nodes.title.textContent,'拍标靶盘');assert.equal(nodes.chip.textContent,'把整张盘放进圈里');assert.equal(nodes['shutter-text'].textContent,'拍照并发送');
  assert.equal(nodes.link.textContent,'已连上你的电脑');assert.equal(nodes.link.dataset.state,'ok');
  assert.match(nodes.run.innerText,/run-one/,'the page names the run the photos belong to');
  assert.equal(nodes.disc.hidden,true,'no disc number declared yet');
  assert.equal(nodes['tip-list'].children.length,words.shootingTips.length);
  assert.doesNotMatch(nodes['tip-list'].innerText,/ceiling/,'one language at a time');
  assert.match(nodes.overall.innerText,/还没有照片/);
  // Photos from every device of this run are listed; their stage and time are shown.
  state.answer.body={photos:[{id:'a',name:'a.jpg',url:'/api/photos/run-one/a',time:990,verdict:'unsure',status:'too_few_votes'},{id:'b',name:'b.jpg',url:'/api/photos/run-one/b',time:995}],
    adoption:{state:'none'},now:1000,read_at:999,read_photos:['a'],analysis:{state:'reading',photos:['a','b'],seconds:4},desk_age:1,disc_id:'T1'};
  await context.poll();
  assert.equal(nodes.disc.hidden,false);assert.match(nodes.disc.textContent,/标靶盘：T1/);
  assert.equal(nodes.count.textContent,'电脑已收到 2 张');
  assert.equal(nodes.sent.children.length,2);
  const [newest,older]=nodes.sent.children;
  assert.equal(newest.dataset.stage,'reading');assert.equal(older.dataset.stage,'retake');
  assert.match(older.innerText,/换光照/);assert.match(older.innerText,/重拍/);assert.doesNotMatch(older.innerText,/Retake/);
  assert.equal(nodes.empty.hidden,true);
  // The computer's photo step is closed: say so instead of "reading".
  state.answer.body={...state.answer.body,analysis:null,desk_age:60};await context.poll();
  assert.match(nodes.overall.innerText,/拍照”这一步没打开/);
  // The run moved on: the old link never joins the new run.
  state.answer.body={...state.answer.body,desk_elsewhere:true};await context.poll();
  assert.match(nodes.overall.innerText,/另一次标定/);
  // Server not reachable: a fix list and a retry; uploads stay possible once it is back.
  state.answer={status:0};await context.poll();
  assert.equal(nodes.problem.hidden,false);assert.match(nodes.problem.innerText,/连不上电脑/);assert.match(nodes.problem.innerText,/重试/);
  assert.equal(nodes.link.textContent,'连不上电脑');assert.equal(nodes.link.dataset.state,'bad');
  assert.equal(nodes.camera.disabled,false);
  // Expired link: blocks uploads with the way back.
  state.answer={status:403,body:{error:'invalid or expired photo token'}};await context.poll();
  assert.match(nodes.problem.innerText,/链接已经失效/);assert.equal(nodes.camera.disabled,true);assert.equal(nodes.overall.hidden,true);
  assert.equal(nodes.link.textContent,'链接已失效');
}
{
  // A phone set to English reads English only.
  const {nodes,context,state}=mount('en-GB');await flush();
  assert.equal(nodes.title.textContent,'Photograph the target disc');assert.equal(nodes['shutter-text'].textContent,'Take and send');
  assert.equal(nodes.link.textContent,'Connected to your computer');
  assert.match(nodes['tip-list'].innerText,/ceiling lamp/);assert.doesNotMatch(nodes['tip-list'].innerText,/吸顶灯/);
  state.answer.body={photos:[{id:'a',name:'a.jpg',url:'/x',time:990,verdict:'unsure',status:'no_rim'}],adoption:{state:'none'},now:1000,desk_age:1};
  await context.poll();
  assert.match(nodes.sent.children[0].innerText,/Show the whole disc/);assert.match(nodes.sent.children[0].innerText,/Retake/);
  assert.doesNotMatch(nodes.sent.children[0].innerText,/拍全盘/);
}
assert.match(html,/capture="environment"/);assert.doesNotMatch(html,/:has\(|structuredClone|user-scalable=no|\bdvh\b/);
assert.match(html,/id="gallery"[^>]*type="file"[^>]*accept="image\/\*"[^>]*multiple/);
assert.match(html,/prefers-color-scheme: dark/);assert.match(html,/prefers-reduced-motion/);
console.log('Phone JPEG paths, reasons as actions, stages with times, adoption states, recovery exits and one language passed');
