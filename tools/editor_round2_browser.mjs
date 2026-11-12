export async function verify(A){
  const assert=(ok,message)=>{if(!ok)throw Error(message);},e=A.editor,s=A.state(),w=e.h.dom(),cv=w.canvas;
  assert(w.tools.querySelectorAll('button').length===9,'nine icon tools');
  assert(!w.left.querySelector('[data-ed-layer-name],.ed-toolgrid,[data-ed=operation]'),'list-only left panel');
  assert(w.left.querySelectorAll('.lay').length===3,'three layer rows');assert(w.left.querySelectorAll('.ed-mask').length===2,'two saved masks');
  assert(!w.right.querySelector('.ed-dark').open,'dark materials collapsed');
  const visible=[...w.right.querySelectorAll('.ed-material-scroll > .ed-swatches button')];assert(visible.length>0,'visible colour palette');
  assert(visible.every(b=>!e.light(e.palette.swatches.find(m=>m.id===b.dataset.edMaterial)).dark),'no dark swatches in first group');
  for(const [key,tool] of Object.entries({v:'move',r:'rectangle',f:'lasso',c:'ring',g:'sector',w:'colour',y:'rectangleShape',n:'pen',h:'pan'})){
    cv.dispatchEvent(new KeyboardEvent('keydown',{key,bubbles:true,cancelable:true}));assert(s.tool===tool,'shortcut '+key);
  }
  e.h.tool('ring');const count=s.selections.length;cv.dispatchEvent(new KeyboardEvent('keydown',{key:' ',bubbles:true,cancelable:true}));assert(s.tool==='pan','Space temporarily selects hand');cv.dispatchEvent(new KeyboardEvent('keyup',{key:' ',bubbles:true,cancelable:true}));assert(s.tool==='ring'&&s.selections.length===count,'Space restores ring without making a mask');
  document.querySelector('[data-ed-op=intersect]').click();assert(e.options.operation==='intersect','mask toggle icons');e.options.operation='replace';
  const id=s.activeMask;e.select({tool:'ring',inner:34,outer:47});const next=s.activeMask;A.undo();assert(s.activeMask===id,'selection undo');A.redo();assert(s.activeMask===next,'selection redo');
  e.h.tool('sector');await new Promise(r=>setTimeout(r,200));assert(w.bar.hidden,'transform bar hidden for selection tools');assert(e.overlayCache?.id===s.activeMask,'selection outline rendered');
  const view=e.h.view(),rect=w.cv.getBoundingClientRect(),discTop=rect.top+view.cy-60*view.s,discBottom=rect.top+view.cy+60*view.s;
  const bar=w.cv.querySelector('.ed-options').getBoundingClientRect();assert(bar.bottom<=discTop+1,'options bar off disc');
  if(!w.note.hidden)assert(w.note.getBoundingClientRect().top>=discBottom-1,'warning below disc');
  const panel=w.right.getBoundingClientRect(),action=w.right.querySelector('.ed-apply').getBoundingClientRect();assert(action.bottom<=panel.bottom+1&&action.top>=panel.top,'fill action visible');
  const scroll=w.right.querySelector('.ed-material-scroll');scroll.scrollTop=scroll.scrollHeight;assert(w.right.querySelector('.ed-apply').getBoundingClientRect().bottom<=panel.bottom+1,'fill remains visible after scrolling');
  const name=s.layers[0].name;s.selected=s.layers[0].id;e.h.rebuild();e.h.rename(s.selected);const input=w.left.querySelector('.lay input');assert(input,'inline rename');input.value=name+' renamed';input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));assert(s.layers[0].name===name+' renamed','inline rename commits');A.undo();assert(s.layers[0].name===name,'inline rename undo');
  return {passed:true,checks:['nine tool icons and shortcuts','Space temporary hand','compact layer/mask lists','hue palette and collapsed dark group','mask operation toggles','selection undo/redo','selection outline','options and warning off disc','pinned fill action','inline rename undo']};
}
