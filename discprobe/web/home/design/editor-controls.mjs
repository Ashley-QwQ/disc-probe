import { isActionEnter } from "../kit/shared.js";
import * as O from './editor-ops.mjs';
import {colourWord} from './editor-materials.mjs';
import {curated,held,warning,visible} from './editor-texlib.mjs';
import {tone as toneOf} from './tone.mjs';
import {rigSteps,rigWords,rigLabel} from './editor-rig.mjs';
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const paths={
  undo:'<path d="M9 5L4 10l5 5M4 10h10a5 5 0 0 1 0 10"/>',redo:'<path d="M15 5l5 5-5 5M20 10H10a5 5 0 0 0 0 10"/>',
  move:'<path d="M5 3l13 8-6 1-3 6z"/>',rectangle:'<rect x="4" y="5" width="16" height="14" rx="1" stroke-dasharray="3 2"/>',
  lasso:'<path d="M8 18C-1 14 3 4 12 4c10 0 12 11 3 14-6 3-11-1-8-4 2-2 5 2 2 7"/>',
  ring:'<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/>',
  sector:'<path d="M12 12l8-5A10 10 0 0 1 1 16z"/><path d="M12 12l-3 2a4 4 0 0 0 6 0z"/>',
  colour:'<path d="M4 20L17 7M13 5v-3M18 12h3M17 3l2-2M20 7h3M8 9H5"/>',
  shape:'<rect x="3" y="3" width="12" height="12" rx="1"/><circle cx="15" cy="15" r="6"/>',
  pen:'<path d="M4 20l2-7L16 3l5 5-10 10zM6 13l5 5M14 5l5 5M3 21h7"/>',
  pan:'<path d="M8 12V6a1.5 1.5 0 0 1 3 0v4-6a1.5 1.5 0 0 1 3 0v6-4a1.5 1.5 0 0 1 3 0v7-5a1.5 1.5 0 0 1 3 0v6c0 5-3 8-7 8-3 0-5-2-7-5l-3-4a1.5 1.5 0 0 1 2-2l3 3"/>',
  up:'<path d="M6 14l6-6 6 6M12 8v12M5 4h14"/>',down:'<path d="M6 10l6 6 6-6M12 4v12M5 20h14"/>',
  remove:'<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6M14 11v6"/>',
  save:'<path d="M12 4v16M4 12h16"/>',clear:'<path d="M6 6l12 12M18 6L6 18"/>',
  replace:'<rect x="4" y="4" width="16" height="16" rx="1"/>',
  add:'<rect x="3" y="3" width="12" height="12" rx="1"/><path d="M9 15v6h12V9h-6M15 12v6M12 15h6"/>',
  subtract:'<rect x="3" y="3" width="12" height="12" rx="1"/><path d="M9 15v6h12V9h-6M12 15h6"/>',
  intersect:'<rect x="3" y="3" width="12" height="12" rx="1"/><rect x="9" y="9" width="12" height="12" rx="1"/><path d="M9 9h6v6H9z" fill="currentColor"/>'
};
export const icon=k=>`<svg viewBox="0 0 24 24" aria-hidden="true">${paths[k]??paths.move}</svg>`;
export const TOOL_KEYS={v:'move',r:'rectangle',f:'lasso',c:'ring',g:'sector',w:'colour',y:'shape',n:'pen',h:'pan'};
export const controls={
  selectionOptions(def){if(!def)return;for(const k of ['inner','outer','start','end','tolerance'])if(Number.isFinite(def[k]))this.options[k]=def[k];if(typeof def.contiguous==='boolean')this.options.contiguous=def.contiguous;},
  toolName(k){return ({move:this.h.lang()==='zh'?'选择':'Select',pan:this.h.lang()==='zh'?'手形':'Hand',shape:this.t.shape})[k]??this.t[k];},
  toolHint(k){const zh=this.h.lang()==='zh',name=this.toolName(k);
    if(k==='colour')return zh?'按颜色选区：点一下选中相近的颜色；按住左右拖调范围':'Select similar colours; hold and drag sideways to change tolerance';
    if(['rectangle','lasso','ring','sector'].includes(k))return zh?`${name}：拖动建立选区；选完可拷贝、剪切或拖动里面的内容`:`${name}: drag to select, then copy, cut or drag the contents`;
    return zh?({move:'选择：移动、缩放或旋转图层；在选区内拖动可移动内容',pan:'手形：拖动画面；用滚轮缩放',shape:'简单形状：拖动绘制；建立选区后可裁剪',pen:'手绘：拖动绘制；建立选区后可裁剪'})[k]:({move:'Select: move, scale or rotate layers; drag inside a selection to move its contents',pan:'Hand: drag the view; wheel to zoom',shape:'Shapes: drag to draw, then select to crop',pen:'Freehand: drag to draw, then select to crop'})[k];
  },
  toolbar(){const w=this.h.dom();if(!w)return;const mod=/Mac|iPhone|iPad/.test(navigator.platform)?'⌘':'Ctrl',zh=this.h.lang()==='zh';
    w.tools.innerHTML=['undo','redo'].map(a=>{const title=(a==='undo'?(zh?'撤销':'Undo')+` ${mod}+Z`:(zh?'重做':'Redo')+` ${mod}+Shift+Z / ${mod}+Y`);return `<button class="tb" type="button" data-history="${a}" title="${title}" aria-label="${title}" ${this.s[a==='undo'?'past':'future'].length?'':'disabled'}>${icon(a)}<span class="ed-tip">${title}</span></button>`;}).join('')+'<span class="ed-tool-separator" role="separator"></span>'+Object.entries(TOOL_KEYS).map(([key,k])=>{
      const active=k==='shape'?['rectangleShape','ellipse','polygon','line'].includes(this.tool):this.tool===k;
      return `<button class="tb" type="button" data-ed-tool="${k}" title="${this.toolHint(k)} (${key.toUpperCase()})" aria-label="${this.toolName(k)}" aria-keyshortcuts="${key.toUpperCase()}" aria-pressed="${active}">${icon(k)}<span class="ed-tip">${this.toolHint(k)} <kbd>${key.toUpperCase()}</kbd></span></button>`;}).join('');
    w.tools.onclick=e=>{const a=e.target.closest('[data-history]')?.dataset.history;if(a){this.h[a]();return;}this.click(e);};
  },
  optionsBar(){const w=this.h.dom(),t=this.t;if(!w)return;
    let bar=w.cv.querySelector('.ed-options');if(!bar){bar=document.createElement('div');bar.className='ed-options';bar.setAttribute('role','toolbar');w.cv.append(bar);bar.addEventListener('input',e=>this.input(e));bar.addEventListener('change',e=>{if(e.target.tagName==='SELECT')this.input(e);});bar.addEventListener('click',e=>this.optionClick(e));}
    const tool=this.tool,selection=['rectangle','lasso','ring','sector','colour'].includes(tool);
    let options='';
    if(tool==='ring'||tool==='sector')options+=this.n('inner',t.inner,0,60,.1)+this.n('outer',t.outer,0,60,.1);
    if(tool==='sector')options+=this.n('start',t.start,-360,360)+this.n('end',t.end,-360,720);
    if(tool==='colour')options+=this.n('tolerance',t.tolerance,0,255)+`<label class="ed-inline"><input data-ed="contiguous" type="checkbox" ${this.options.contiguous?'checked':''}>${t.contiguous}</label>`;
    if(['rectangleShape','ellipse','polygon','line'].includes(tool))options+=`<label>${t.shape}<select data-ed-shape>${['rectangleShape','ellipse','polygon','line'].map(k=>`<option value="${k}" ${tool===k?'selected':''}>${t[k]}</option>`).join('')}</select></label>`;
    if(selection)options+=`<span class="ed-ops" role="group" aria-label="${t.operation}">${['replace','add','subtract','intersect'].map((op,i)=>`<button class="ib" data-ed-op="${op}" title="${t[op]}${['',' (Shift)',' (Alt)',' (Shift+Alt)'][i]}" aria-label="${t[op]}" aria-pressed="${this.options.operation===op}">${icon(op)}</button>`).join('')}</span>`;
    if(['rectangle','lasso','ring','sector','rectangleShape','ellipse','polygon','line','pen'].includes(tool))options+=`<label class="ed-inline"><input data-ed="snap" type="checkbox" ${this.options.snap?'checked':''}>${this.h.lang()==='zh'?'吸附':'Snap'}</label>`;
    if(tool==='pen')options+=`<span class="ed-option-hint">${this.h.lang()==='zh'?'拖动绘制 · Enter 完成 · Esc 取消':'Drag to draw · Enter finishes · Esc cancels'}</span>`;
    if(tool==='pan')options+=`<button class="sbtn" data-ed-fit>${this.h.lang()==='zh'?'适应整盘':'Fit disc'}</button>`;
    if(['ring','sector'].includes(tool))options+=`<button class="ib" data-ed-action="select" aria-label="${t.apply}" title="${t.apply}">${icon('save')}</button>`;
    if(this.s.activeMask){const zh=this.h.lang()==='zh',l=this.s.layers.find(l=>l.id===this.s.selected),off=!l?.px||l.locked;
      const actions=[['copy',zh?'拷贝到新图层':'Copy to new layer','Ctrl+J'],['cut',zh?'剪切到新图层':'Cut to new layer','Ctrl+Shift+J'],['delete',zh?'删掉选区里的内容':'Delete selected contents','Delete'],['keep',zh?'只留选区里的内容':'Keep selected contents','']];
      options=`<div class="ed-selection-actions">${actions.map(([a,label,key])=>`<button class="sbtn" type="button" data-ed-action="${a}" title="${label}${key?' ('+key+')':''}" ${off||(['copy','cut'].includes(a)&&this.s.layers.length>=16)?'disabled':''}>${label}</button>`).join('')}<button class="sbtn" data-ed-action="clear">${t.clear}</button></div>`+options+this.n('feather',zh?'柔化 mm':'Feather mm',0,4,.2)+`<span class="ed-option-hint">${t.hint}</span>`;
    }
    bar.innerHTML=options;bar.hidden=tool==='move'&&!this.s.activeMask;bar.setAttribute('aria-label',this.toolName(['rectangleShape','ellipse','polygon','line'].includes(tool)?'shape':tool));
  },
  optionClick(e){const b=e.target.closest('button');if(!b)return;
    if(b.dataset.edOp){this.options.operation=b.dataset.edOp;this.optionsBar();return;}
    if(b.hasAttribute('data-ed-fit')){this.h.fit();return;}this.click(e);
  },
  left(){const w=this.h.dom(),t=this.t;if(!w)return;this.init();w.left.querySelector('.ed-selections')?.remove();w.left.querySelectorAll('.ed-layer-actions').forEach(n=>n.remove());
    const masks=this.s.selections.filter(s=>s.named!==false);
    w.left.insertAdjacentHTML('beforeend',`<section class="ed-selections"><h3><span class="grow">${this.h.lang()==='zh'?'选区':'Selections'}</span><button class="ib" data-ed-action="save-mask" title="${t.saveMask}" aria-label="${t.saveMask}" ${this.s.activeMask?'':'disabled'}>${icon('save')}</button><button class="ib" data-ed-action="clear" title="${t.clear}" aria-label="${t.clear}" ${this.s.activeMask?'':'disabled'}>${icon('clear')}</button></h3><ul class="ed-mask-list" role="listbox" aria-label="${t.choose}">${masks.map(m=>`<li role="option" tabindex="0" class="ed-mask" data-mask-id="${esc(m.id)}" aria-selected="${m.id===this.s.activeMask}"><canvas width="32" height="32"></canvas><span class="mask-name">${esc(m.name)}</span><button class="ib" data-delete-mask="${esc(m.id)}" title="${t.removeMask}" aria-label="${t.removeMask}">${icon('remove')}</button></li>`).join('')}</ul>${masks.length?'':`<p class="note quiet">${this.h.lang()==='zh'?'保存的选区会列在这里。':'Saved selections appear here.'}</p>`}</section>`);
    for(const row of w.left.querySelectorAll('.ed-mask')){const mask=masks.find(m=>m.id===row.dataset.maskId),bits=O.bytes(mask.bits),g=this.s.maskGrid,c=row.querySelector('canvas').getContext('2d'),im=c.createImageData(32,32);for(let y=0;y<32;y++)for(let x=0;x<32;x++){const hit=bits[Math.min(g.height-1,Math.floor(y*g.height/32))*g.width+Math.min(g.width-1,Math.floor(x*g.width/32))];im.data.set(hit?[60,60,60,255]:[205,200,190,255],4*(y*32+x));}c.putImageData(im,0,0);}
    if(!w.left.dataset.edBound){w.left.dataset.edBound='yes';w.left.addEventListener('click',e=>{if(e.target.closest('[data-ed-action]'))this.click(e);else this.maskClick(e);});w.left.addEventListener('dblclick',e=>this.maskRename(e));w.left.addEventListener('keydown',e=>this.listKey(e),true);}
    for(const li of w.left.querySelectorAll('.lay'))li.tabIndex=0;
    this.toolbar();this.optionsBar();
  },
  toggleLayerActions(id){const state=this.panelState();state.layerActions=state.layerActions===id?null:id;this.syncLayerActions();},
  syncLayerActions(){const left=this.h.dom()?.left;if(!left)return;
    for(const row of left.querySelectorAll('.lay')){const open=String(this.panelState().layerActions)===row.dataset.id;
      row.querySelector('[data-a="more"]')?.setAttribute('aria-expanded',String(open));const panel=row.querySelector('.ed-layer-more');if(panel)panel.hidden=!open;}
  },
  closeLayerActions(){const id=this.panelState().layerActions;if(id==null)return false;this.panelState().layerActions=null;this.syncLayerActions();
    this.h.dom()?.left.querySelector(`[data-id="${id}"] [data-a="more"]`)?.focus({preventScroll:true});return true;
  },
  maskClick(e){const row=e.target.closest('[data-mask-id]');if(!row||e.target.closest('input'))return;
    const id=row.dataset.maskId;
    if(e.target.closest('[data-delete-mask]')){this.mutate(()=>{this.s.selections=this.s.selections.filter(s=>s.id!==id);this.s.assignments=this.s.assignments.filter(a=>a.selection!==id);if(this.s.activeMask===id)this.s.activeMask=null;});return;}
    const m=this.s.selections.find(s=>s.id===id);this.selectionOptions(m.definition);this.mutate(()=>{this.s.activeMask=id;this.options.target='mask';});this.h.tool(['rectangle','lasso','ring','sector','colour'].includes(m.definition?.tool)?m.definition.tool:'rectangle');
  },
  maskRename(e){const row=e.target.closest('[data-mask-id]');if(!row||e.target.closest('button,input'))return;
    const m=this.s.selections.find(s=>s.id===row.dataset.maskId),input=document.createElement('input');input.value=m.name;input.className='num';row.querySelector('.mask-name').replaceWith(input);input.focus();input.select();let done=false;
    const finish=ok=>{if(done)return;done=true;if(ok&&input.value.trim()!==m.name)this.mutate(()=>{m.name=input.value.trim()||m.name;});else this.left();};input.onkeydown=e=>{e.stopPropagation();if(isActionEnter(e)){e.preventDefault();finish(true);}if(e.key==='Escape')finish(false);};input.onblur=()=>finish(true);
  },
  listKey(e){if(e.target.closest('input'))return;const row=e.target.closest('[data-mask-id]');if(row){if(isActionEnter(e)){e.preventDefault();e.stopPropagation();this.maskClick(e);}if(e.key==='F2'){e.preventDefault();e.stopPropagation();this.maskRename(e);}if(e.key==='Delete'){e.preventDefault();e.stopPropagation();row.querySelector('button').click();}return;}this.layerKey(e);},
  right(){const w=this.h.dom();if(!w)return;this.init();this.rigSync?.();const scroll=w.right.querySelector('.ed-material-scroll')?.scrollTop??0;
    w.right.innerHTML=this.materialsHTML();
    if(this.rigOpen?.())this.swatches();w.right.querySelector('.ed-material-scroll').scrollTop=scroll;
    if(!w.right.dataset.edBound){w.right.dataset.edBound='yes';w.right.addEventListener('click',e=>this.click(e));w.right.addEventListener('input',e=>this.input(e));w.right.addEventListener('change',e=>{if(e.target.tagName==='SELECT'||e.target.matches('[data-ed-rig-mm]'))this.input(e);});}
  },
  // The right column: the picture's tone, then colour. Colour starts with the phone and the height (editor-rig.mjs);
  // until both are chosen there are no swatches and nothing to fill with (walk W3).
  materialsHTML(){const s=this.s,t=this.t,lang=this.h.lang(),w=rigWords(lang),open=!!this.rigOpen?.(),zh=lang==='zh';
    const tab=this.panelState().tab,info=zh?'说明':'About',hasMask=this.hasFillSelection();
    const colourWords=this.colourWords,colourMode=s.media==='dvd'&&this.options.fillKind==='colour';
    const segments=(key,label,keys,disabled=()=>false)=>`<div class="ed-fill-choice"><span>${label}</span><div class="seg" role="group" aria-label="${label}">${keys.map(k=>`<button type="button" data-ed-choice="${key}" data-value="${k}" aria-pressed="${this.options[key]===k}" ${disabled(k)?'disabled aria-describedby="ed-mask-why"':''}>${k==='colour'?colourWords.label:t[k]}</button>`).join('')}</div></div>`;
    const colourButton=`<button type="button" data-ed-choice="fillKind" data-value="colour" aria-pressed="${colourMode}">${colourWords.label}</button>`;
    const modes=segments('fillKind',t.pattern,s.media==='dvd'?['material','pattern','effect','colour']:['material','pattern','effect']);
    const canFill=open&&(colourMode?(this.pictureLayer()&&!this.pictureLayer().locked&&this.colourPalette):(this.options.target==='mask'?hasMask:!!s.layers.find(l=>l.id===s.selected&&!l.locked)));
    const fill=`<button class="sbtn ed-apply" data-ed-action="fill" ${canFill?'':'disabled'} ${open?'':`title="${w.locked}"`}>${open?(zh?'填充':'Fill'):w.locked}</button>`;
    let colour=rigSteps(this.rig?.()??{},this.rigData,lang,{ex:this.rigExample?.(),state:this.rigState??'ready',error:this.rigError,expanded:this.panelState().rigExpanded});
    if(open)colour+=`<div class="ed-colour-sticky">${colourMode?'<span class="ed-current" aria-hidden="true"></span>':'<div class="ed-current"><span class="ed-current-chip" aria-hidden="true"></span><output class="ed-colour-name" aria-live="polite"></output></div>'}${fill}</div>`+
      (colourMode?'':segments('target',zh?'填到':'Fill to',['layer','mask'],k=>k==='mask'&&!hasMask)+
      (hasMask?'':`<p id="ed-mask-why" class="note quiet">${zh?'还没有选区，先在画布上建立选区。':'No selection yet. Create one on the canvas first.'}</p>`))+
      modes+
      `<div class="ed-pattern-options" ${this.options.fillKind==='pattern'?'':'hidden'}><select data-ed="pattern" aria-label="${t.pattern}">${['diamond','dots','stripes'].map(k=>`<option value="${k}" ${this.options.pattern===k?'selected':''}>${t[k]}</option>`).join('')}</select><select data-ed="coordinates" aria-label="${t.pattern}">${['cartesian','polar'].map(k=>`<option value="${k}" ${this.options.coordinates===k?'selected':''}>${t[k]}</option>`).join('')}</select><div class="ed-values">${this.n('pitch_mm',t.pitch,.001,50,.1)}${this.n('size_mm',t.size,.001,25,.1)}${this.n('angle_deg',t.angle,-360,360)}</div></div>`+
      `<div class="ed-effect-options" ${this.options.fillKind==='effect'?'':'hidden'}><select data-ed="effect" aria-label="${t.effect}">${['flow','ox','merge','sync'].map(k=>`<option value="${k}" ${this.options.effect===k?'selected':''}>${t[k]}</option>`).join('')}</select><div class="ed-values">${this.n('y1',t.y1,0,150)}${this.n('y2',t.y2,0,150)}</div></div>`;
    if(!open)colour+=(s.media==='dvd'?`<div class="seg ed-colour-locked">${colourButton}</div>`:'')+fill;
    if(colourMode){
      const assignment=s.assignments.find(a=>a.layer===s.selected&&a.colour);
      const table=this.colourPalette?.table??assignment?.colour.table;
      const reason=!open?'':!this.pictureLayer()||this.pictureLayer().locked?colourWords.picture:
        this.colourPaletteLoading?colourWords.loading:this.colourPaletteError?colourWords.unavailable:'';
      colour+=`<label class="ed-inline"><input data-ed="directionArrow" type="checkbox" ${this.panelState().directionArrow?'checked':''}>${this.arrowWords.label}</label>
        <p class="note quiet ed-colour-estimate">${colourWords.note}</p>
        <details class="ed-help"><summary>${info}</summary><p class="note quiet">${colourWords.advice}</p>
        <p class="note quiet">${colourWords.poseWarning}</p>
        ${table?.fitted?`<p class="note quiet">${colourWords.calibrated}</p><p class="note quiet">${colourWords.unseen}</p>`:''}</details>
        ${reason?`<p class="note quiet" role="status" title="${esc(this.colourPaletteError??'')}">${reason}</p>`:''}`;
    }
    if(open&&!colourMode)colour+=`<div class="ed-rig-colours"><div class="ed-colour-explanation"><span>${zh?'颜色是模型预测，还没逐块对照':'Colours are model predictions, not yet checked swatch by swatch'}</span><details class="ed-help"><summary>${info}</summary><p class="ed-model-note">${esc(w.pose(rigLabel(this.rig(),this.rigData,lang)))}</p><p class="note quiet">${esc(w.model)}</p><p class="note quiet">${esc(t.model)}</p></details></div>`+
      (this.palette?.source==='texlib'?`<div class="seg" role="group" aria-label="${zh?'观看方式':'Viewing mode'}">${['camera','held'].map(k=>`<button type="button" data-ed-choice="viewMode" data-value="${k}" aria-pressed="${(this.options.viewMode??'camera')===k}">${k==='held'?(zh?'拿在手里看':'Held in hand'):(zh?'固定机位拍照':'Fixed camera')}</button>`).join('')}</div>`:'')+
      `<input data-ed-search type="search" aria-label="${zh?'查找颜色':'Find a colour'}" placeholder="${zh?'查找颜色，如“红”':'Find a colour, e.g. red'}" value="${esc(this.search??'')}">`+
      `<div class="ed-swatches ed-shown" role="group" aria-label="${w.title}"></div><p class="note quiet ed-hidden-note"></p>`+
      `<details class="ed-all"><summary>${w.all} <span></span></summary><div class="ed-all-swatches ed-swatches"></div></details>`+
      `<details class="ed-material-detail"><summary>${t.details}</summary><p class="note"></p></details></div>`;
    return `<section class="ed-materials"><div class="seg ed-panel-tabs" role="group" aria-label="${zh?'编辑':'Edit'}"><button type="button" data-ed-tab="tone" aria-pressed="${tab==='tone'}" aria-controls="ed-tone-panel">${t.toneH}</button><button type="button" data-ed-tab="colour" aria-pressed="${tab==='colour'}" aria-controls="ed-colour-panel">${w.title}</button></div><div class="ed-material-scroll"><div id="ed-tone-panel" ${tab==='tone'?'':'hidden'}>${this.toneSection()||`<p class="note quiet">${zh?'先选一张图片，再调整影调。':'Select a picture to adjust its tone.'}</p>`}</div><section id="ed-colour-panel" class="ed-rig" aria-label="${w.title}" ${tab==='colour'?'':'hidden'}>${colour}</section></div></section>`;
  },
  // UI preferences belong to a work without changing its saved document or undo history.
  panelState(){this.panelStates??=new WeakMap();let state=this.panelStates.get(this.s);if(!state){state={tab:'tone',rigExpanded:false,directionArrow:true};this.panelStates.set(this.s,state);}return state;},
  hasFillSelection(){const mask=this.s.selections.find(m=>m.id===this.s.activeMask);return !!mask&&O.bytes(mask.bits).some(v=>v!==0);},
  // The selected picture's tone and dither (tone.mjs): what its greys become on the burn grid.
  pictureLayer(){const l=this.s.layers.find(l=>l.id===this.s.selected);return l&&l.kind==='image'&&l.px&&!l.shape?l:null;},
  toneSection(){const l=this.pictureLayer(),t=this.t;if(!l)return '';const tn=toneOf(l.tone),off=l.locked?'disabled':'';
    const slider=(k,min,max)=>`<label class="ed-tone-ctl"><span>${t[k]}</span><input type="range" style="--range-pct:${(tn[k]-min)/(max-min)*100}%" data-tone="${k}" min="${min}" max="${max}" step="1" value="${tn[k]}" ${off}><output>${tn[k]}</output></label>`;
    return `<section class="ed-tone"><h3>${t.toneH}</h3><label>${t.dither}<select data-tone="dither" ${off}>${Object.entries(t.modes).map(([k,v])=>`<option value="${k}" ${tn.dither===k?'selected':''}>${v}</option>`).join('')}</select></label>`+
      slider('strength',0,100)+slider('brightness',-100,100)+slider('contrast',-100,100)+slider('highlights',-100,100)+slider('shadows',-100,100)+
      `<button class="sbtn" type="button" data-ed-action="tone-reset" ${off}>${t.toneReset}</button><details class="ed-help"><summary>${this.h.lang()==='zh'?'说明':'About'}</summary><p class="note quiet">${t.toneNote(Math.round((this.s.cell||.02)*1000))}</p></details></section>`;},
  toneInput(el){const l=this.pictureLayer();if(!l||l.locked)return;const k=el.dataset.tone,value=k==='dither'?el.value:Math.round(+el.value);
    this.h.checkpoint(`tone-${k}-${l.id}`);l.tone={...toneOf(l.tone),[k]:value};
    if(el.type==='range')el.style.setProperty('--range-pct',((value-Number(el.min))/(Number(el.max)-Number(el.min))*100)+'%');
    const o=el.nextElementSibling;if(o?.tagName==='OUTPUT')o.textContent=value;
    this.invalidate();this.h.changed();},
  materialName(m,light=this.light(m)){if(this.palette?.source==='texlib')return [colourWord(light,this.h.lang()),m.period_um?`${Number(m.period_um.toPrecision(3))} µm`:''].filter(Boolean).join(' · ');return [m.name||m.id,colourWord(light,this.h.lang())].join(' · ');},
  light(m){return (this.palette?.source==='texlib'?this.poseLights?.[m.id]:this.rigLights?.()?.[m.id])??this.poseLights?.[m.id]??this.palette?.display_colours?.[m.id]??{rgb:[105,105,105],hue:0,dark:true};
  },
  swatches(){const w=this.h.dom();if(!w?.right.querySelector('.ed-shown'))return;const zh=this.h.lang()==='zh',rw=rigWords(this.h.lang());
    const lib=this.palette?.source==='texlib',all=(this.palette?.swatches??this.s.materials??[]).map(m=>({m,light:this.light(m)})).sort((a,b)=>a.light.dark-b.light.dark||a.light.hue-b.light.hue||a.m.id.localeCompare(b.m.id));
    const matches=({m,light})=>!this.search||(m.id+' '+m.name+' '+(m.texture_ids??[]).join(' ')+' '+m.spec+' '+colourWord(light,this.h.lang())).toLowerCase().includes(this.search.toLowerCase());
    const list=all.filter(matches);
    const button=({m,light,count=1})=>{const note=lib?warning(m,zh):'',title=[this.materialName(m,light),note,count>1?(zh?`${count} 种近似颜色`:`${count} similar colours`):''].filter(Boolean).join(' · ');return `<button type="button" data-ed-material="${esc(m.id)}" aria-label="${esc(title)}" title="${esc(title)}" aria-pressed="${m.id===this.material}"><svg viewBox="0 0 64 48" aria-hidden="true"><path fill="rgb(${light.rgb})" d="M5 40 A38 38 0 0 1 59 40 L45 47 A19 19 0 0 0 19 47 Z"/><path d="M8 39 A34 34 0 0 1 56 39 M11 41 A30 30 0 0 1 53 41 M14 43 A26 26 0 0 1 50 43" fill="none" stroke="currentColor" stroke-opacity=".25" stroke-width=".65"/></svg></button>`;};
    const shown=lib?curated(list,this.options.viewMode??'camera'):list.filter(v=>!v.light.dark),hidden=lib?all.filter(({m})=>(this.options.viewMode==='camera'?!visible(m):!held(m))).length:all.filter(v=>v.light.dark).length;
    w.right.querySelector('.ed-shown').innerHTML=shown.map(button).join('')||`<p class="note">${all.some(v=>!v.light.dark)?this.t.empty:rw.none}</p>`;
    w.right.querySelector('.ed-hidden-note').textContent=(lib&&this.options.viewMode==='held'?(zh?'拿在手里转着看时，只有这几种颜色不怎么变，适合单色调的图；彩色图要按上面的机位拍。':'Held and tilted, only these colours stay put: good for a one-tone picture. A colour picture needs the camera position above.')+' ':'')+(hidden?(lib?(zh?`${hidden} 种可在“全部材质”中查找和使用。`:`Find and use ${hidden} more in All materials.`):rw.hidden(hidden)):'');
    w.right.querySelector('.ed-all-swatches').innerHTML=list.map(button).join('');w.right.querySelector('.ed-all summary span').textContent=all.length;
    const m=[...(this.palette?.swatches??[]),...(this.s.materials??[])].find(m=>m.id===this.material);if(m){const light=this.light(m);w.right.querySelector('.ed-colour-name').textContent=this.materialName(m,light);w.right.querySelector('.ed-current-chip').style.background=`rgb(${light.rgb})`;w.right.querySelector('.ed-material-detail p').textContent=lib?`${m.tested?(zh?'实刻过':'Burned before'):(zh?'模型预测':'Model prediction')} · ${zh?'手持稳定：':'Held stability: '}${held(m)?(zh?'好':'good'):m.stability==null?(zh?'未知':'unknown'):m.stability<=25&&!m.fades?(zh?'一般':'fair'):(zh?'差':'poor')} · ${warning(m,zh)} · ${m.spec} · ${zh?'LED 灯下模型预测，实际亮度与颜色可能不同。':'LED model prediction; actual brightness and colour may differ.'}`:`${m.period_um??m.periods_um?.[0]} µm · ${m.spec} · ${m.risk??''}${m.period_conflict?' · period conflict':''}${light.dark?(zh?' · 这个机位下看不出颜色':' · no colour at this position'):''}`;}
  }
};
