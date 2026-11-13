import * as O from './editor-ops.mjs';
import {controls,TOOL_KEYS} from './editor-controls.mjs';
import {materialPose,identityRGB} from './editor-materials.mjs';
import {LampPreview} from './editor-lamp.mjs';
import {ExactView} from './exact-view.mjs';

const WORDS={
  zh:{selection:'选区',rectangle:'矩形选区',lasso:'套索',ring:'圆环',sector:'扇形',colour:'按颜色',shape:'简单形状',rectangleShape:'矩形',ellipse:'椭圆',polygon:'多边形',line:'直线',pen:'手绘',materials:'材质',model:'仅预览实验：颜色是模型预测，没有照片验证。刻录默认按黑白刻，上了颜色、彩色图案和特效的地方刻成深色。',target:'填充对象',layer:'当前图层',mask:'当前选区',material:'单材质',pattern:'图案填充',effect:'特效',diamond:'菱格',dots:'点阵',stripes:'条纹',cartesian:'直角坐标',polar:'绕盘心',inner:'内半径',outer:'外半径',start:'起始角',end:'结束角',tolerance:'颜色容差',contiguous:'只选相连部分',apply:'建立选区',clear:'取消选区',name:'选区名称',saveMask:'保存命名选区',restore:'恢复选区',removeMask:'删除选区',hint:'Shift 加 · Alt 减 · Shift+Alt 交',snap:'吸附盘心和半径尺',rename:'重命名图层',up:'上移图层',down:'下移图层',remove:'删除图层',pitch:'间距 mm',size:'线宽 / 点径 mm',angle:'旋转 °',fill:'应用填充',flow:'流光',ox:'O/X 切换',merge:'两点合成环',sync:'整片同时亮',y1:'手机起点 mm',y2:'手机终点 mm',history:'选区和填充均可撤销',none:'先选图层或建立选区',swatch:'筛选材质：周期或纹理',details:'材质详情',empty:'没有匹配的材质',draw:'拖动绘制，多边形松手闭合。画布上用方向键移动、空格起笔、Enter 完成。',operation:'选区运算',replace:'替换',add:'相加',subtract:'相减',intersect:'相交',radiusNote:'选区蒙版 0.2 mm；刻录格子 20 / 10 / 5 µm。',gesture:'拖动选取；也可填写数值',choose:'选区记录',layerName:'图层名称',opacity:'不透明度',busy:'正在合成…',toneH:'影调',dither:'抖动方式',modes:{'floyd-steinberg':'误差扩散','blue-noise':'蓝噪声',ordered:'有序',clustered:'网点',threshold:'不抖动'},strength:'抖动强度',brightness:'亮度',contrast:'对比度',highlights:'高光',shadows:'阴影',toneReset:'恢复默认',toneNote:um=>`灰度在 ${um} µm 刻录格子上抖动成深浅两种纹理。放大到 100% 以上，画布上就是刻进去的那些格子。`},
  en:{selection:'Selection',rectangle:'Rectangle selection',lasso:'Lasso',ring:'Ring',sector:'Sector',colour:'By colour',shape:'Basic shapes',rectangleShape:'Rectangle',ellipse:'Ellipse',polygon:'Polygon',line:'Line',pen:'Freehand',materials:'Materials',model:'Preview experiment only: the colours are a model prediction, not checked against photos. The burn is black and white by default; coloured, colour-patterned and effect areas burn dark.',target:'Fill target',layer:'Selected layer',mask:'Active selection',material:'Single material',pattern:'Pattern fill',effect:'Effect',diamond:'Diamond grid',dots:'Dot matrix',stripes:'Stripes',cartesian:'Cartesian',polar:'Around disc',inner:'Inner radius',outer:'Outer radius',start:'Start angle',end:'End angle',tolerance:'Colour tolerance',contiguous:'Contiguous only',apply:'Create selection',clear:'Clear selection',name:'Selection name',saveMask:'Save named selection',restore:'Restore selection',removeMask:'Delete selection',hint:'Shift adds · Alt subtracts · Shift+Alt intersects',snap:'Snap to centre and radius ruler',rename:'Rename layer',up:'Raise layer',down:'Lower layer',remove:'Delete layer',pitch:'Pitch mm',size:'Width / diameter mm',angle:'Rotation °',fill:'Apply fill',flow:'Flowing band',ox:'O/X switch',merge:'Two spots into ring',sync:'Whole area at once',y1:'Phone start mm',y2:'Phone end mm',history:'Selections and fills can be undone',none:'Select a layer or create a selection first',swatch:'Filter: period or texture',details:'Material details',empty:'No matching materials',draw:'Drag to draw; polygons close on release. On canvas: arrows move, Space starts, Enter finishes.',operation:'Mask operation',replace:'Replace',add:'Add',subtract:'Subtract',intersect:'Intersect',radiusNote:'Selection masks: 0.2 mm; burn cells: 20 / 10 / 5 µm.',gesture:'Drag to select, or enter values',choose:'Saved selections',layerName:'Layer name',opacity:'Opacity',busy:'Composing…',toneH:'Tone',dither:'Dither',modes:{'floyd-steinberg':'Error diffusion','blue-noise':'Blue noise',ordered:'Ordered',clustered:'Halftone',threshold:'No dither'},strength:'Dither strength',brightness:'Brightness',contrast:'Contrast',highlights:'Highlights',shadows:'Shadows',toneReset:'Reset',toneNote:um=>`Greys are dithered into the two textures on the ${um} µm burn grid. Zoomed to 100% or more, the canvas shows the cells that are burned.`}
};
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export class Editor {
  constructor(host){this.h=host;this.palette=null;this.tool='move';this.options={inner:30,outer:46,start:15,end:120,tolerance:18,contiguous:true,operation:'replace',snap:true,fillKind:'material',pattern:'diamond',coordinates:'cartesian',pitch_mm:5,size_mm:.75,angle_deg:0,effect:'flow',y1:55,y2:100,target:'layer'};this.revision=0;
    fetch(new URL('./swatches.json',import.meta.url)).then(r=>r.json()).then(p=>{p.swatches=Object.entries(p.swatches).map(([name,m])=>({...m,name:name.split(' ')[0],rgb:m.srgb,period_um:m.periods_um[0]}));this.palette=p;this.lightCache=new Map();this.init();this.panels();this.invalidate();this.h.draw();}).catch(e=>this.h.error(String(e)));
  }
  get s(){return this.h.state();} get t(){return WORDS[this.h.lang()]??WORDS.zh;}
  init(){const s=this.s;if(!s)return;s.maskGrid??=O.grid();s.selections??=[];s.assignments??=[];
    if(!s.materials&&this.palette)s.materials=[{id:'background',spec:'B9',rgb:[205,200,190]},...this.palette.swatches];
    s.activeMask??=null;this.material??=this.palette?.swatches.find(m=>m.rgb[1]>200&&m.rgb[0]<100)?.id??s.materials?.[1]?.id;
  }
  invalidate(){this.revision++;this.previewCache=null;this.overlayCache=null;}
  mutate(fn){this.h.checkpoint();fn();this.invalidate();this.h.changed();this.panels();}
  document(){this.init();const s=this.s;return O.migrate({format:'disc-probe design',version:2,media:s.media,cell:s.cell,annulus_mm:s.media==='cd'?[26,58]:[24,58],maskGrid:s.maskGrid,selections:s.selections,activeMask:s.activeMask,assignments:s.assignments,materials:s.materials,
      layers:s.layers.map(l=>({id:l.id,kind:l.kind,name:l.name,visible:l.visible,locked:l.locked,opacity:l.opacity,x:l.x,y:l.y,width:l.width,height:l.kind==='fx'?l.height:l.width*l.h/l.w,rot:l.rot,w:l.w,h:l.h,sourceKind:l.sourceKind??(l.kind==='fx'?'shape':'bitmap'),fxKind:l.fxKind,y1:l.y1,y2:l.y2,shape:l.shape,svg:l.svg,raster:l.px&&!l.shape?{width:l.px.width,height:l.px.height,rgba:O.base64(l.px.data)}:undefined,tone:l.px&&!l.shape&&l.tone?l.tone:undefined}))});}
  panels(){if(!this.s)return;this.init();this.left();this.right();}
  n(key,label,min,max,step=1){return `<label>${label}<input data-ed="${key}" type="number" min="${min}" max="${max}" step="${step}" value="${this.options[key]}" class="num"></label>`;}
  input(e){const el=e.target;
    if(el.matches('[data-tone]')){this.toneInput(el);return;}
    if(el.matches('[data-ed-shape]')){this.options.shape=el.value;this.h.tool(el.value);return;}
    if(el.matches('[data-ed-search]')){this.search=el.value;this.swatches();return;}
    if(el.matches('[data-ed-name]')){this.maskName=el.value;return;}
    if(el.matches('[data-ed-layer-name]')){const l=this.s.layers.find(l=>l.id===this.s.selected);if(l&&!l.locked)this.mutate(()=>{l.name=el.value.trim()||l.name;this.h.rebuild();});return;}
    if(!el.dataset.ed)return;
    this.options[el.dataset.ed]=el.type==='checkbox'?el.checked:el.type==='number'?+el.value:el.value;
    if(['fillKind','target'].includes(el.dataset.ed))this.right();
  }
  click(e){const b=e.target.closest('[data-ed-tool],[data-ed-action],[data-ed-material]');if(!b)return;e.preventDefault();e.stopPropagation();
    if(b.dataset.edTool){this.tool=b.dataset.edTool;this.h.tool(this.tool);this.left();this.h.dom().canvas.focus();return;}
    if(b.dataset.edMaterial){this.material=b.dataset.edMaterial;this.swatches();return;}
    const a=b.dataset.edAction,l=this.s.layers.find(l=>l.id===this.s.selected);
    if(a==='fill')return this.fill();
    if(a==='tone-reset'){const l=this.pictureLayer();if(l&&!l.locked)this.mutate(()=>{l.tone=undefined;});return;}
    if(a==='select'){const tool=['rectangle','ring','sector'].includes(this.tool)?this.tool:'ring';return this.select({tool,...this.options,a:[-30,-30],b:[30,30]},this.options.operation);}
    if(a==='clear')return this.mutate(()=>{this.s.activeMask=null;});
    if(a==='save-mask'){const current=this.s.selections.find(s=>s.id===this.s.activeMask);if(current)this.mutate(()=>{this.s.selections.push({...current,id:crypto.randomUUID(),named:true,name:this.maskName?.trim()||this.t.selection+' '+(this.s.selections.filter(m=>m.named!==false).length+1)});this.s.activeMask=this.s.selections.at(-1).id;});return;}
    const id=this.h.dom().left.querySelector('[data-ed-mask]')?.value;
    if(a==='restore-mask'&&id)return this.mutate(()=>{this.s.activeMask=id;this.options.target='mask';});
    if(a==='delete-mask'&&id)return this.mutate(()=>{this.s.selections=this.s.selections.filter(s=>s.id!==id);this.s.assignments=this.s.assignments.filter(a=>a.selection!==id);if(this.s.activeMask===id)this.s.activeMask=null;});
    if(l&&!l.locked&&['up','down','remove'].includes(a))this.mutate(()=>{const i=this.s.layers.indexOf(l);if(a==='remove'){this.s.layers.splice(i,1);this.s.assignments=this.s.assignments.filter(a=>a.layer!==l.id);this.s.selected=null;}else{const j=Math.max(0,Math.min(this.s.layers.length-1,i+(a==='up'?1:-1)));this.s.layers.splice(i,1);this.s.layers.splice(j,0,l);}this.h.rebuild();});
  }
  layerKey(e){const li=e.target.closest('.lay');if(!li||e.target.closest('button,input'))return;const l=this.s.layers.find(l=>String(l.id)===li.dataset.id);
    if(e.key==='Enter'||e.key===' '){e.preventDefault();li.click();return;}
    if(e.key==='F2'){e.preventDefault();this.s.selected=l.id;this.h.rebuild();this.h.rename(l.id);return;}
    if(e.altKey&&['ArrowUp','ArrowDown'].includes(e.key)&&!l.locked){e.preventDefault();e.stopPropagation();this.s.selected=l.id;const action=e.key==='ArrowUp'?'up':'down';this.click({target:{closest:()=>({dataset:{edAction:action}})},preventDefault(){},stopPropagation(){}});this.h.dom().left.querySelector(`[data-id="${l.id}"]`)?.focus();}
  }
  select(def,op='replace',rgba=null){this.init();this.selectionOptions(def);const mask=O.selection(def,this.s.maskGrid,rgba),prior=this.s.selections.find(s=>s.id===this.s.activeMask);this.mutate(()=>{const bits=O.booleanMask(prior?O.bytes(prior.bits):new Uint8Array(mask.length),mask,op),id=crypto.randomUUID();this.s.selections.push({id,name:this.maskName?.trim()||this.t[def.tool],bits:O.base64(bits),named:false,definition:def});this.s.activeMask=id;this.options.target='mask';});}
  fill(){this.init();const o=this.options,target=o.target==='mask'&&this.s.activeMask?{selection:this.s.activeMask}:{layer:this.s.selected},l=this.s.layers.find(l=>l.id===target.layer);if(!target.selection&&(!l||l.locked)){this.h.error(this.t.none);return;}
    if(!this.s.materials.some(m=>m.id===this.material)){const m=this.palette?.swatches.find(m=>m.id===this.material);if(!m||this.s.materials.length>=256){this.h.error('Material slot limit: 256');return;}this.s.materials.push(m);}
    const a={id:crypto.randomUUID(),...target};
    if(o.fillKind==='pattern'){if(!(o.size_mm>0&&o.size_mm<=o.pitch_mm/2)){this.h.error('0 < size ≤ pitch / 2');return;}a.pattern={version:1,pattern:o.pattern,coordinates:o.coordinates,pitch_mm:o.pitch_mm,size_mm:o.size_mm,angle_deg:o.angle_deg,origin_mm:[0,0],phase_mm:[0,0],reference_radius_mm:40,materials:[this.material,'background']};}
    else if(o.fillKind==='effect')a.effect={kind:o.effect,y1:o.y1,y2:o.y2,wavelength_um:.53};else a.material=this.material;
    this.mutate(()=>{this.s.assignments.push(a);});
  }
  snap(p){if(!this.options.snap)return p;const v=this.h.view(),tol=7/v.s;let [x,y]=p;if(Math.abs(x)<tol)x=0;if(Math.abs(y)<tol)y=0;const r=Math.hypot(x,y),near=[7.5,17,...(this.s.media==='cd'?[26,58]:[24,58]),30,40,50,60].find(n=>Math.abs(r-n)<tol);if(near&&r){x*=near/r;y*=near/r;}return [O.q(x),O.q(y)];}
  pointer(type,e,mm){if(!['rectangle','lasso','ring','sector','colour','rectangleShape','ellipse','polygon','line','pen'].includes(this.tool))return false;
    const p=this.snap(mm),o=this.options;
    if(type==='down'){
      this.drag={points:[p],start:p,op:e.shiftKey&&e.altKey?'intersect':e.altKey?'subtract':e.shiftKey?'add':o.operation};if(e.pointerId!==undefined)this.h.dom().canvas.setPointerCapture(e.pointerId);
      if(this.tool==='colour'){const g=this.s.maskGrid,{g:ctx}=this.h.raster(g);this.select({tool:'colour',seed:[Math.floor((p[0]+60)/g.cell_mm),Math.floor((p[1]+60)/g.cell_mm)],tolerance:o.tolerance,contiguous:o.contiguous},this.drag.op,ctx.getImageData(0,0,g.width,g.height).data);this.drag=null;}
    }else if(type==='move'&&this.drag){this.drag.points.push(p);this.h.draw();}
    else if(type==='up'&&this.drag){const d=this.drag;this.drag=null;d.points.push(p);
      if(['rectangleShape','ellipse','polygon','line','pen'].includes(this.tool)){this.h.shape(this.tool,d.points);return true;}
      const def={tool:this.tool};if(this.tool==='rectangle')Object.assign(def,{a:d.start,b:p});
      if(this.tool==='lasso')def.points=d.points;
      if(this.tool==='ring'){const radii=[Math.hypot(...d.start),Math.hypot(...p)].sort((a,b)=>a-b);Object.assign(def,{inner:O.q(radii[0]),outer:O.q(radii[1])});this.options.inner=def.inner;this.options.outer=def.outer;}
      if(this.tool==='sector')Object.assign(def,{inner:o.inner,outer:o.outer,start:Math.atan2(d.start[1],d.start[0])*180/Math.PI,end:Math.atan2(p[1],p[0])*180/Math.PI});
      this.select(def,d.op);
    }else if(type==='cancel')this.drag=null;
    return true;
  }
  key(e){if(e.target!==this.h.dom().canvas)return false;
    if(!['rectangle','lasso','ring','sector','colour','rectangleShape','ellipse','polygon','line','pen'].includes(this.tool))return false;
    this.cursor??=[-40,-20];
    if(e.key.startsWith('Arrow')){const n=e.shiftKey?5:1;if(e.key==='ArrowLeft')this.cursor[0]-=n;if(e.key==='ArrowRight')this.cursor[0]+=n;if(e.key==='ArrowUp')this.cursor[1]-=n;if(e.key==='ArrowDown')this.cursor[1]+=n;this.cursor=this.cursor.map(v=>Math.max(-60,Math.min(60,v)));if(this.drag)this.pointer('move',e,this.cursor);this.h.draw();return true;}
    
    if(e.key==='Enter'){this.pointer(this.drag?'up':'down',e,this.cursor);this.h.draw();return true;}
    if(e.key==='Escape'&&this.drag){this.drag=null;this.h.draw();return true;}return false;
  }
  preview(size=420,identityOnly=false){const pose=materialPose(this.s.scene,this.s.lookY),lamp=!identityOnly&&this.s.view==='lamp',dark=document.documentElement.dataset.theme==='dark',key=JSON.stringify([size,this.revision,dark]);
    this.lamp??=new LampPreview({onChange:()=>{if(this.h.active?.()===false)return;this.h.status?.();this.h.draw();}});
    if(lamp){const lampKey=JSON.stringify([size,this.revision,pose]),result=this.lamp.key===lampKey?this.lamp.image:this.lamp.schedule(lampKey,{document:this.document(),pose,size});this.h.status?.();if(result)return result;}else if(!identityOnly)this.lamp.pause();
    if(this.previewCache?.key===key)return this.previewCache.canvas;
    const labelKey=`${size}:${this.revision}`;if(this.labelCache?.key!==labelKey){const d=this.document();this.labelCache={key:labelKey,materials:d.materials,labels:O.compose(d,O.grid(size))};}
    const {labels,materials}=this.labelCache,canvas=document.createElement('canvas');canvas.width=canvas.height=size;const ctx=canvas.getContext('2d'),im=ctx.createImageData(size,size);
    for(let i=0;i<labels.length;i++){const m=materials[labels[i]]??materials[0],rgb=identityRGB(m,i%size,Math.floor(i/size),dark);im.data.set([...rgb,255],i*4);}ctx.putImageData(im,0,0);this.previewCache={key,canvas};return canvas;
  }
  // At a cell a pixel or more, the burn cells on screen, from the composer the core uses (exact-view.mjs).
  exactCells(v){const s=this.s,cell=s.cell||.02;
    if(v.s*cell<1){this.exact?.off();return null;}
    const side=Math.round(120/cell),at=(px,c)=>Math.floor((((px-c)/v.s)+60)/cell),clamp=n=>Math.max(0,Math.min(side,n));
    const cols=[clamp(at(0,v.cx)),clamp(at(v.w,v.cx)+1)],rows=[clamp(at(0,v.cy)),clamp(at(v.h,v.cy)+1)];
    if(cols[1]<=cols[0]||rows[1]<=rows[0])return null;
    this.exact??=new ExactView(()=>{this.h.status?.();this.h.draw();});
    const dark=document.documentElement.dataset.theme==='dark';
    const paint=(labels,w,h)=>{const mats=this.labelCache?.materials??s.materials??[],c=document.createElement('canvas');c.width=w;c.height=h;const g=c.getContext('2d'),im=g.createImageData(w,h);
      const light=dark?[58,64,62]:[218,214,205],ink=dark?[200,198,190]:[62,60,56];
      for(let i=0;i<labels.length;i++){const m=mats[labels[i]];im.data.set([...(labels[i]===0?light:m&&m.id!=='background'&&m.spec!=='A5'&&m.id!=='dark'?identityRGB(m,1,0,dark):ink),255],i*4);}
      g.putImageData(im,0,0);return c;};
    return this.exact.request(JSON.stringify([this.revision,side,rows,cols,dark]),()=>this.document(),{side,rows,cols},paint);
  }
  requestLights(pose){const key=JSON.stringify(pose);if(this.lightPose===key)return;this.lightPose=key;clearTimeout(this.lightTimer);this.lightTimer=setTimeout(async()=>{
    try{const r=await fetch('/api/editor-swatches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pose})});if(!r.ok)return;const result=await r.json();if(this.lightPose===key){this.poseLights=result.colours;this.swatches();}}catch{}},220);
  }
  paint(ctx){const s=this.s,v=this.h.view(),g=s.maskGrid;if(!g)return;
    this.requestLights(materialPose(s.scene,s.lookY));
    if(s.layers.length||s.assignments.length||s.view==='lamp'){ctx.save();this.h.annulus(ctx,...(s.media==='cd'?[26,58]:[24,58]));ctx.clip('evenodd');const size=s.view==='lamp'?Math.max(200,Math.min(2048,Math.round(120*v.s*v.dpr))):420;ctx.drawImage(this.preview(size),v.cx-60*v.s,v.cy-60*v.s,120*v.s,120*v.s);
      const exact=s.view!=='lamp'&&s.layers.length?this.exactCells(v):null;if(exact){ctx.imageSmoothingEnabled=false;ctx.drawImage(exact.canvas,v.cx+(exact.cols[0]*s.cell-60)*v.s,v.cy+(exact.rows[0]*s.cell-60)*v.s,(exact.cols[1]-exact.cols[0])*s.cell*v.s,(exact.rows[1]-exact.rows[0])*s.cell*v.s);}
      ctx.restore();}else this.lamp?.pause();
    const m=s.selections.find(mask=>mask.id===s.activeMask);if(m){if(this.overlayCache?.id!==m.id){const b=O.bytes(m.bits),canvas=document.createElement('canvas');canvas.width=g.width;canvas.height=g.height;const c=canvas.getContext('2d'),im=c.createImageData(g.width,g.height);
        for(let j=0;j<g.height;j++)for(let i=0;i<g.width;i++)if(b[j*g.width+i]){const edge=!b[j*g.width+i-1]||!b[j*g.width+i+1]||!b[(j-1)*g.width+i]||!b[(j+1)*g.width+i],stripe=(i+j)%20;if(edge||stripe<2)im.data.set(edge?(Math.floor((i+j)/7)%2?[255,255,255,255]:[18,18,18,255]):stripe===0?[255,255,255,36]:[18,18,18,36],4*(j*g.width+i));}c.putImageData(im,0,0);this.overlayCache={id:m.id,canvas};}
      ctx.save();ctx.imageSmoothingEnabled=false;ctx.drawImage(this.overlayCache.canvas,v.cx-60*v.s,v.cy-60*v.s,120*v.s,120*v.s);ctx.restore();}
    if(this.drag){const ps=this.drag.points;ctx.save();ctx.strokeStyle=this.h.colour('--ink');ctx.lineWidth=1.5;ctx.setLineDash([4,4]);ctx.beginPath();ps.forEach(([x,y],i)=>i?ctx.lineTo(v.cx+x*v.s,v.cy+y*v.s):ctx.moveTo(v.cx+x*v.s,v.cy+y*v.s));ctx.stroke();ctx.restore();}
    if(this.cursor&&document.activeElement===this.h.dom().canvas){const [x,y]=this.cursor,xx=v.cx+x*v.s,yy=v.cy+y*v.s;ctx.save();ctx.strokeStyle=this.h.colour('--ink');ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(xx-8,yy);ctx.lineTo(xx+8,yy);ctx.moveTo(xx,yy-8);ctx.lineTo(xx,yy+8);ctx.stroke();ctx.restore();}
  }
}

Object.assign(Editor.prototype,controls);
