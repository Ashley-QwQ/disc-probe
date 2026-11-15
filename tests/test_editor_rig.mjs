// Pose first, colour second (walk W3): the colour panel stays locked until a phone and a height are chosen; every
// phone x height (and every custom distance x height) has a palette; the swatches follow the chosen pose.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {Editor} from '../discprobe/web/home/design/editor-ui.mjs';
import {materialPose} from '../discprobe/web/home/design/editor-materials.mjs';
import {decodeSet,setKey,rigReady,rigScene,customMM,rigSteps,hueOf,example} from '../discprobe/web/home/design/editor-rig.mjs';

const read=f=>JSON.parse(fs.readFileSync(new URL('../discprobe/web/home/design/'+f,import.meta.url),'utf8'));
const data=read('pose-swatches.json'),custom=read('pose-swatches-custom.json'),palette=read('swatches.json');
const ids=Object.values(palette.swatches).map(m=>m.id);

// the data: same material order as the palette; the agreed heights; the measured phone; the custom grid
assert.deepEqual(data.order,ids);assert.deepEqual(custom.order,ids);
assert.deepEqual(data.heights.map(h=>h.ruler_cm),[21,30,40,50,70]);
assert.equal(data.heights[0].camera_z_mm,206.5);assert.equal(data.heights[0].status,'photo-checked');
assert.deepEqual(data.phones.map(p=>[p.id,p.flash_mm,p.verified]),[['iphone17pro',47.9,true]]);
assert.equal(data.model.delta_scale,.93);assert.equal(data.model.focal_px,3126);
for(const d of [data,custom]){assert.match(d.sets_sha256,/^[0-9a-f]{64}$/);assert.match(d.source.palette_sha256,/^[0-9a-f]{64}$/);assert.match(d.model.table_sha256,/^[0-9a-f]{64}$/);}

// every pose loads a full palette with some colour in it, and the palette changes with the pose
const keys=[...data.phones.flatMap(p=>data.heights.map(h=>[{phone:p.id,height:h.id},data])),
  ...custom.flash_mm.flatMap(mm=>data.heights.map(h=>[{phone:'custom',flash_mm:mm,height:h.id},custom]))];
const seen=new Set();
for(const [rig,file] of keys){const k=setKey(rig,data);assert(k,`no key for ${JSON.stringify(rig)}`);const set=file.sets[k];assert(set,`no set ${k}`);
  assert.equal(set.rgb.length,ids.length*6);assert.equal(set.dark.length,Math.ceil(ids.length/4));
  const lights=decodeSet(data.order,set);assert.equal(Object.keys(lights).length,255);
  const shown=Object.values(lights).filter(l=>!l.dark);if(file===data||rig.height!=='70')assert(shown.length>0,`${k}: nothing shows colour`);
  assert(Object.values(lights).every(l=>l.rgb.every(c=>Number.isInteger(c)&&c>=0&&c<=255)));
  assert.equal(set.camera[1],data.rig.lens_offset_mm);assert.equal(set.camera[2],data.heights.find(h=>h.id===rig.height).camera_z_mm);
  seen.add(set.rgb+set.dark);}
// neighbours can round to the same 8-bit colours (iPhone's 47.9 mm next to the 48 mm grid point); heights never do
assert(seen.size>=keys.length*.95,'the palette changes with the pose');
assert.equal(new Set(data.heights.map(h=>data.sets['iphone17pro@'+h.id].rgb)).size,data.heights.length);
assert.deepEqual(data.sets['iphone17pro@21'].flash,[0,76.35,206.5]);

// hue as colorsys; custom distances round to the whole-mm grid; partial poses are not ready
assert.equal(Math.round(hueOf([255,0,0])),0);assert.equal(Math.round(hueOf([0,0,255])),240);assert.equal(Math.round(hueOf([255,0,255])),300);
assert.equal(customMM(31.6,data),32);assert.equal(customMM(9.4,data),null);assert.equal(customMM('',data),null);
for(const rig of [{},{phone:'iphone17pro'},{height:'21'},{phone:'custom',height:'21'},{phone:'custom',flash_mm:80,height:'21'},{phone:'nokia',height:'21'},{phone:'iphone17pro',height:'25'}])
  assert.equal(rigReady(rig,data),false,JSON.stringify(rig));

// the scene follows the rig, and the lamp view gets that pose with the practice discs' scale
const scene=rigScene({preset:'design',cam:[0,-70,330],follows:true},{phone:'iphone17pro',height:'40'},data,data.sets['iphone17pro@40']);
assert.deepEqual(scene.cam,[0,-28.45,398.7]);assert.equal(scene.follows,true);
const pose=materialPose(scene,28.45);
assert.deepEqual(pose.camera,[0,28.45,398.7]);assert.deepEqual(pose.flash.map(v=>+v.toFixed(2)),[0,76.35,398.7]);assert.equal(pose.delta_scale,.93);
assert.equal(materialPose({cam:[0,-70,330],follows:true},70).delta_scale,undefined,'old works keep the plain model');

// the panel: an Editor without its constructor (no fetch, no DOM), as the page has it
function editor(rig,{loaded=true,selected=1}={}){const ed=Object.create(Editor.prototype);
  const s={layers:[{id:1,kind:'image'}],selected,assignments:[],selections:[],activeMask:null,scene:{preset:'design',cam:[0,-70,330],follows:true,...(rig?{rig}:{})}};
  Object.assign(ed,{h:{state:()=>s,lang:()=>'zh',checkpoint(){},changed(){},draw(){},status(){},dom:()=>null},options:{target:'layer',fillKind:'material',pattern:'diamond',coordinates:'cartesian',pitch_mm:5,size_mm:.75,angle_deg:0,effect:'flow',y1:55,y2:100},
    palette:{swatches:Object.values(palette.swatches).map(m=>({...m,rgb:m.srgb}))},rigState:loaded?'ready':'loading',rigData:loaded?data:null,rigSets:{}});
  if(loaded)ed.addSets(data);return ed;}
const locked=html=>{assert(!html.includes('data-ed-material'),'no swatches');assert(!html.includes('ed-shown'),'no colour grid');assert(!html.includes('data-ed="fillKind"'),'no fill options');
  assert.match(html,/data-ed-action="fill" disabled/);assert(html.includes('先选手机和拍摄高度'));};
for(const rig of [null,{phone:'iphone17pro'},{phone:'custom',height:'21'},{phone:'custom',flash_mm:3,height:'21'}]){const ed=editor(rig);
  assert.equal(ed.rigOpen(),false);const html=ed.materialsHTML();locked(html);
  assert(html.includes('你的手机')&&html.includes('拍摄高度'),'the steps are offered');}
{const ed=editor(null);const html=ed.materialsHTML();assert(html.includes('<svg class="ed-rig-figure"'),'the figure explains first');assert(!/δ|周期|纹理 ID/.test(html.split('ed-rig-step')[0]),'no inner words in the explanation');
  assert.match(html,/data-ed-rig="height"[^>]*disabled/,'height waits for the phone');}
locked(editor({phone:'iphone17pro',height:'21'},{loaded:false}).materialsHTML());
{const ed=editor({phone:'custom',flash_mm:31.6,height:'30'});assert.equal(ed.rigOpen(),false,'custom grid not fetched yet');locked(ed.materialsHTML());
  ed.addSets(custom);assert.equal(ed.rigOpen(),true);assert.equal(ed.light({id:ids[0]}).rgb.join(),decodeSet(data.order,custom.sets['32@30'])[ids[0]].rgb.join());}
{const ed=editor({phone:'iphone17pro',height:'21'});assert.equal(ed.rigOpen(),true);const html=ed.materialsHTML();
  assert(html.includes('ed-shown')&&html.includes('全部材质')&&html.includes('iPhone 17 Pro · 21 cm'));assert.doesNotMatch(html,/data-ed-action="fill" disabled/);
  assert(html.includes('<details class="ed-rig-why">'),'the explanation folds away once chosen');
  const a=ed.light({id:ids[0]});ed.s.scene.rig.height='70';ed.rigDecoded=null;const b=ed.light({id:ids[0]});
  const at=k=>decodeSet(data.order,data.sets[k])[ids[0]];assert.deepEqual(a,at('iphone17pro@21'));assert.deepEqual(b,at('iphone17pro@70'));
  ed.rigSync();assert.deepEqual(ed.s.scene.cam,[0,-28.45,698.7]);assert.equal(ed.s.lookY,28.45);
  assert.equal(ed.poseNote(),'iPhone 17 Pro · 70 cm · 模型预测');}
assert.equal(editor(null).poseNote(),'还没选手机和高度 · 按旧的默认机位（33 cm）');
{const ex=example(data,{'iphone17pro@21':decodeSet(data.order,data.sets['iphone17pro@21']),'iphone17pro@40':decodeSet(data.order,data.sets['iphone17pro@40'])});assert(ex&&ex.low.join()!==ex.high.join(),'the figure shows a real change');}
assert(Object.values(decodeSet(data.order,custom.sets['10@70'])).every(l=>l.dark),'a 10 mm flash at 70 cm shows nothing (the panel says so)');
assert(rigSteps({},null,'en',{state:'error',error:'404'}).includes('did not load: 404'));
console.log('editor rig: locked until phone and height; 5 + 255 palettes load; scene and lamp pose follow the rig');
