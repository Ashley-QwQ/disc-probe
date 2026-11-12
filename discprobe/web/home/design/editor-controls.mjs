import * as O from './editor-ops.mjs';
import {colourWord} from './editor-materials.mjs';
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const paths={
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
  toolbar(){const w=this.h.dom();if(!w)return;w.tools.innerHTML=Object.entries(TOOL_KEYS).map(([key,k])=>{
      const active=k==='shape'?['rectangleShape','ellipse','polygon','line'].includes(this.tool):this.tool===k;
      return `<button class="tb" type="button" data-ed-tool="${k}" title="${this.toolName(k)} (${key.toUpperCase()})" aria-label="${this.toolName(k)}" aria-keyshortcuts="${key.toUpperCase()}" aria-pressed="${active}">${icon(k)}<span class="ed-tip">${this.toolName(k)} <kbd>${key.toUpperCase()}</kbd></span></button>`;}).join('');
    w.tools.onclick=e=>this.click(e);
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
    bar.innerHTML=options;bar.hidden=tool==='move';bar.setAttribute('aria-label',this.toolName(['rectangleShape','ellipse','polygon','line'].includes(tool)?'shape':tool));
  },
  optionClick(e){const b=e.target.closest('button');if(!b)return;
    if(b.dataset.edOp){this.options.operation=b.dataset.edOp;this.optionsBar();return;}
    if(b.hasAttribute('data-ed-fit')){this.h.fit();return;}this.click(e);
  },
  left(){const w=this.h.dom(),t=this.t;if(!w)return;this.init();w.left.querySelector('.ed-selections')?.remove();w.left.querySelectorAll('.ed-layer-actions').forEach(n=>n.remove());
    const masks=this.s.selections.filter(s=>s.named!==false);
    w.left.insertAdjacentHTML('beforeend',`<section class="ed-selections"><h3><span class="grow">${this.h.lang()==='zh'?'选区':'Selections'}</span><button class="ib" data-ed-action="save-mask" title="${t.saveMask}" aria-label="${t.saveMask}" ${this.s.activeMask?'':'disabled'}>${icon('save')}</button><button class="ib" data-ed-action="clear" title="${t.clear}" aria-label="${t.clear}" ${this.s.activeMask?'':'disabled'}>${icon('clear')}</button></h3><ul class="ed-mask-list" role="listbox" aria-label="${t.choose}">${masks.map(m=>`<li role="option" tabindex="0" class="ed-mask" data-mask-id="${m.id}" aria-selected="${m.id===this.s.activeMask}"><canvas width="32" height="32"></canvas><span class="mask-name">${esc(m.name)}</span><button class="ib" data-delete-mask="${m.id}" title="${t.removeMask}" aria-label="${t.removeMask}">${icon('remove')}</button></li>`).join('')}</ul>${masks.length?'':`<p class="note quiet">${this.h.lang()==='zh'?'保存的选区会列在这里。':'Saved selections appear here.'}</p>`}</section>`);
    for(const row of w.left.querySelectorAll('.ed-mask')){const mask=masks.find(m=>m.id===row.dataset.maskId),bits=O.bytes(mask.bits),g=this.s.maskGrid,c=row.querySelector('canvas').getContext('2d'),im=c.createImageData(32,32);for(let y=0;y<32;y++)for(let x=0;x<32;x++){const hit=bits[Math.min(g.height-1,Math.floor(y*g.height/32))*g.width+Math.min(g.width-1,Math.floor(x*g.width/32))];im.data.set(hit?[60,60,60,255]:[205,200,190,255],4*(y*32+x));}c.putImageData(im,0,0);}
    if(!w.left.dataset.edBound){w.left.dataset.edBound='yes';w.left.addEventListener('click',e=>{if(e.target.closest('[data-ed-action]'))this.click(e);else this.maskClick(e);});w.left.addEventListener('dblclick',e=>this.maskRename(e));w.left.addEventListener('keydown',e=>this.listKey(e),true);}
    for(const li of w.left.querySelectorAll('.lay'))li.tabIndex=0;
    this.toolbar();this.optionsBar();
  },
  maskClick(e){const row=e.target.closest('[data-mask-id]');if(!row||e.target.closest('input'))return;
    const id=row.dataset.maskId;
    if(e.target.closest('[data-delete-mask]')){this.mutate(()=>{this.s.selections=this.s.selections.filter(s=>s.id!==id);this.s.assignments=this.s.assignments.filter(a=>a.selection!==id);if(this.s.activeMask===id)this.s.activeMask=null;});return;}
    const m=this.s.selections.find(s=>s.id===id);this.selectionOptions(m.definition);this.mutate(()=>{this.s.activeMask=id;this.options.target='mask';});this.h.tool(['rectangle','lasso','ring','sector','colour'].includes(m.definition?.tool)?m.definition.tool:'rectangle');
  },
  maskRename(e){const row=e.target.closest('[data-mask-id]');if(!row||e.target.closest('button,input'))return;
    const m=this.s.selections.find(s=>s.id===row.dataset.maskId),input=document.createElement('input');input.value=m.name;input.className='num';row.querySelector('.mask-name').replaceWith(input);input.focus();input.select();let done=false;
    const finish=ok=>{if(done)return;done=true;if(ok&&input.value.trim()!==m.name)this.mutate(()=>{m.name=input.value.trim()||m.name;});else this.left();};input.onkeydown=e=>{e.stopPropagation();if(e.key==='Enter')finish(true);if(e.key==='Escape')finish(false);};input.onblur=()=>finish(true);
  },
  listKey(e){if(e.target.closest('input'))return;const row=e.target.closest('[data-mask-id]');if(row){if(e.key==='Enter'){e.preventDefault();e.stopPropagation();this.maskClick(e);}if(e.key==='F2'){e.preventDefault();e.stopPropagation();this.maskRename(e);}if(e.key==='Delete'){e.preventDefault();e.stopPropagation();row.querySelector('button').click();}return;}this.layerKey(e);},
  right(){const w=this.h.dom(),t=this.t;if(!w)return;this.init();const s=this.s,scroll=w.right.querySelector('.ed-material-scroll')?.scrollTop??0;
    w.right.innerHTML=`<section class="ed-materials"><div class="ed-material-scroll"><h3>${t.materials}</h3><p class="ed-model-note">${t.model}</p><label>${t.target}<select data-ed="target"><option value="layer" ${this.options.target==='layer'?'selected':''}>${t.layer}</option><option value="mask" ${this.options.target==='mask'?'selected':''}>${t.mask}</option></select></label><input data-ed-search type="search" aria-label="${this.h.lang()==='zh'?'查找材质':'Find a material'}" placeholder="${this.h.lang()==='zh'?'查找材质':'Find a material'}" value="${esc(this.search??'')}"><div class="ed-swatches" role="group" aria-label="${t.materials}"></div><details class="ed-dark"><summary>${this.h.lang()==='zh'?'此视角下不显色':'Dark at this pose'} <span></span></summary><div class="ed-dark-swatches ed-swatches"></div></details><output class="ed-colour-name" aria-live="polite"></output><details class="ed-material-detail"><summary>${t.details}</summary><p class="note"></p></details><label>${t.pattern}<select data-ed="fillKind">${['material','pattern','effect'].map(k=>`<option value="${k}" ${this.options.fillKind===k?'selected':''}>${t[k]}</option>`).join('')}</select></label><div class="ed-pattern-options" ${this.options.fillKind==='pattern'?'':'hidden'}><select data-ed="pattern" aria-label="${t.pattern}">${['diamond','dots','stripes'].map(k=>`<option value="${k}" ${this.options.pattern===k?'selected':''}>${t[k]}</option>`).join('')}</select><select data-ed="coordinates" aria-label="${t.pattern}">${['cartesian','polar'].map(k=>`<option value="${k}" ${this.options.coordinates===k?'selected':''}>${t[k]}</option>`).join('')}</select><div class="ed-values">${this.n('pitch_mm',t.pitch,.001,50,.1)}${this.n('size_mm',t.size,.001,25,.1)}${this.n('angle_deg',t.angle,-360,360)}</div></div><div class="ed-effect-options" ${this.options.fillKind==='effect'?'':'hidden'}><select data-ed="effect" aria-label="${t.effect}">${['flow','ox','merge','sync'].map(k=>`<option value="${k}" ${this.options.effect===k?'selected':''}>${t[k]}</option>`).join('')}</select><div class="ed-values">${this.n('y1',t.y1,0,150)}${this.n('y2',t.y2,0,150)}</div></div></div><footer class="ed-fill-footer"><button class="sbtn ed-apply" data-ed-action="fill" ${s.activeMask||s.selected?'':'disabled'}>${t.fill}</button></footer></section>`;
    this.swatches();w.right.querySelector('.ed-material-scroll').scrollTop=scroll;
    if(!w.right.dataset.edBound){w.right.dataset.edBound='yes';w.right.addEventListener('click',e=>this.click(e));w.right.addEventListener('input',e=>this.input(e));w.right.addEventListener('change',e=>{if(e.target.tagName==='SELECT')this.input(e);});}
  },
  light(m){return this.poseLights?.[m.id]??this.palette?.display_colours?.[m.id]??{rgb:[105,105,105],hue:0,dark:true};
  },
  swatches(){const w=this.h.dom();if(!w?.right.querySelector('.ed-swatches'))return;
    const list=(this.palette?.swatches??this.s.materials??[]).filter(m=>!this.search||(m.name+' '+m.spec+' '+colourWord(this.light(m),this.h.lang())).toLowerCase().includes(this.search.toLowerCase())).map(m=>({m,light:this.light(m)})).sort((a,b)=>a.light.hue-b.light.hue||a.m.id.localeCompare(b.m.id));
    const button=({m,light})=>`<button type="button" data-ed-material="${m.id}" aria-label="${colourWord(light,this.h.lang())}" title="${colourWord(light,this.h.lang())}" aria-pressed="${m.id===this.material}"><svg viewBox="0 0 64 48" aria-hidden="true"><path fill="rgb(${light.rgb})" d="M5 40 A38 38 0 0 1 59 40 L45 47 A19 19 0 0 0 19 47 Z"/><path d="M8 39 A34 34 0 0 1 56 39 M11 41 A30 30 0 0 1 53 41 M14 43 A26 26 0 0 1 50 43" fill="none" stroke="currentColor" stroke-opacity=".25" stroke-width=".65"/></svg></button>`;
    w.right.querySelector('.ed-material-scroll > .ed-swatches').innerHTML=list.filter(v=>!v.light.dark).map(button).join('')||`<p class="note">${this.t.empty}</p>`;
    w.right.querySelector('.ed-dark-swatches').innerHTML=list.filter(v=>v.light.dark).map(button).join('');w.right.querySelector('.ed-dark summary span').textContent=list.filter(v=>v.light.dark).length;
    const m=(this.palette?.swatches??this.s.materials??[]).find(m=>m.id===this.material);if(m){w.right.querySelector('.ed-colour-name').textContent=colourWord(this.light(m),this.h.lang());w.right.querySelector('.ed-material-detail p').textContent=`${m.period_um??m.periods_um?.[0]} µm · ${m.spec} · ${m.risk??''}${m.period_conflict?' · period conflict':''}`;}
  }
};
