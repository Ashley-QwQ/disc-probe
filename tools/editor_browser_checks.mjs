// Runs inside the screenshot browser through Runtime.evaluate; no fake drive writes.
export async function verify(A) {
  const assert=(ok,msg)=>{if(!ok)throw Error(msg);};
  const {editor:e}=A,s=A.state();
  s.selected=s.layers[0].id;e.h.rebuild();
  assert(document.querySelectorAll('.ed-layer-actions').length===1,'one layer property group');
  const old=s.activeMask;
  e.select({tool:'ring',inner:34,outer:47});const selected=s.activeMask;
  await new Promise(r=>setTimeout(r,200));assert(e.overlayCache?.id===selected,'selection overlay is rendered');
  assert(selected!==old,'new selection');A.undo();assert(s.activeMask===old,'undo selection restores mask');A.redo();assert(s.activeMask===selected,'redo selection restores mask');
  const l=s.layers.find(l=>l.id===s.selected)??s.layers[0];s.selected=l.id;
  const before=l.visible;document.querySelector(`[data-id="${l.id}"] [data-a="vis"]`).click();assert(l.visible!==before,'toggle visibility');A.undo();assert(l.visible===before,'undo visibility');
  const order=s.layers.map(l=>l.id).join(',');e.click({target:{closest:()=>({dataset:{edAction:'up'}})},preventDefault(){},stopPropagation(){}});A.undo();assert(s.layers.map(l=>l.id).join(',')===order,'undo reorder');
  e.h.shape('rectangleShape',[[-40,-22],[-15,-2]]);assert(s.layers.at(-1).shape.type==='rectangle','shape creation');A.undo();assert(s.layers.length===2,'undo shape');
  e.h.shape('pen',[[-42,5],[-35,10],[-32,2],[-26,12]]);assert(s.layers.at(-1).sourceKind==='stroke','freehand creation');A.undo();
  const n=s.layers.length;
  const text=await A.projectText();await A.openProject(new File([text],'checked.discdesign',{type:'application/json'}));
  assert(s.layers.length===n,'work round trip layers');assert(s.layers[0].svg?.startsWith('<svg'),'SVG source retained');
  const portable=e.document();await A.openProject(new File([JSON.stringify(portable)],'portable.json',{type:'application/json'}));assert(s.layers.length===n,'portable RGBA document opens');
  const canvas=e.h.dom().canvas;canvas.focus();e.tool='rectangle';e.h.tool('rectangle');e.cursor=[-42,-24];
  canvas.dispatchEvent(new KeyboardEvent('keydown',{key:' ',bubbles:true}));
  for(let i=0;i<12;i++)canvas.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
  for(let i=0;i<12;i++)canvas.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}));
  canvas.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  assert(s.activeMask,'keyboard rectangle');assert(document.documentElement.dataset.mode==='design','canvas Enter keeps editing');
  return {passed:true,checks:['panel uniqueness','selection undo/redo','visibility undo','reorder undo','shape undo','pen undo','work round trip','portable RGBA open','keyboard rectangle']};
}
