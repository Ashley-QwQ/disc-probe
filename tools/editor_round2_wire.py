"""Apply the scoped round-two editor integration; run once while developing."""
from pathlib import Path
p=Path('discprobe/web/home/design/editor-ui.mjs');s=p.read_text(encoding='utf8')
s=s.replace("import * as O from './editor-ops.mjs';", "import * as O from './editor-ops.mjs';\nimport {controls,TOOL_KEYS} from './editor-controls.mjs';")
a=s.index('  left(){');b=s.index('  input(e){',a);s=s[:a]+s[b:]
s=s.replace("    if(el.matches('[data-ed-search]'))", "    if(el.matches('[data-ed-shape]')){this.options.shape=el.value;this.h.tool(el.value);return;}\n    if(el.matches('[data-ed-search]'))")
s=s.replace("{...current,id:crypto.randomUUID(),name:this.maskName?.trim()||this.t.selection}", "{...current,id:crypto.randomUUID(),named:true,name:this.maskName?.trim()||this.t.selection+' '+(this.s.selections.filter(m=>m.named!==false).length+1)}")
s=s.replace("this.h.dom().left.querySelector('[data-ed-layer-name]')?.focus()", "this.h.rename(l.id)")
s=s.replace("bits:O.base64(bits),definition:def", "bits:O.base64(bits),named:false,definition:def")
s=s.replace("if(e.key===' '){this.pointer(this.drag?'move':'down',e,this.cursor);this.h.draw();return true;}", "")
s=s.replace("const ctx=canvas.getContext('2d'),im=ctx.createImageData(size,size);", "const ctx=canvas.getContext('2d'),im=ctx.createImageData(size,size),colours=d.materials.map(m=>this.light(m).rgb);")
s=s.replace("const m=d.materials[labels[i]],rgb=m?.rgb??[60,60,60]", "const rgb=colours[labels[i]]??[60,60,60]")
s=s.replace("stripe=(i+j)%12<3;if(edge||stripe)im.data.set(edge?[255,255,255,255]:[25,25,25,180]", "stripe=(i+j)%20;if(edge||stripe<2)im.data.set(edge?(Math.floor((i+j)/7)%2?[255,255,255,255]:[18,18,18,255]):stripe===0?[255,255,255,36]:[18,18,18,36]")
s += '\nObject.assign(Editor.prototype,controls);\n'
p.write_text(s,encoding='utf8')

p=Path('discprobe/web/home/design.js');s=p.read_text(encoding='utf8')
s=s.replace('const DOCK = 56;', 'const TOP_DOCK = 64;\nconst DOCK = 96;')
s=s.replace('V.s = Math.min(V.w, V.h - DOCK) * 0.92 / 120;', 'V.s = Math.min(V.w - 64, V.h - TOP_DOCK - DOCK) * 0.92 / 120;')
s=s.replace('V.cx = V.w / 2; V.cy = (V.h - DOCK) / 2;', 'V.cx = V.w / 2 + 20; V.cy = TOP_DOCK + (V.h - TOP_DOCK - DOCK) / 2;')
s=s.replace('if (L && S.tool === "move")', 'if (L && S.tool === "move" && !spaceDown)')
s=s.replace('if (!L || !L.visible) { bar.hidden = true; return; }', 'if (!L || !L.visible || S.tool !== "move" || spaceDown) { bar.hidden = true; return; }')
s=s.replace('const top = V.h - bh - tilt - Math.max(0, (DOCK - bh) / 2 - 4);', 'const top = 4;')
s=s.replace('const left = Math.min(Math.max(V.w / 2 - bw / 2, 4), V.w - bw - 4);', 'const left = 56;')
s=s.replace('if(editor?.key(e)){e.preventDefault();return;}', 'if(!spaceDown&&editor?.key(e)){e.preventDefault();return;}')
s=s.replace("W.left.querySelector('[data-ed-layer-name]')?.focus()", "editor.h.rename(L.id)")
s=s.replace('  S.tool = t;\n  if(editor)editor.tool=t==="wand"?"colour":t;', '  t=t==="shape"?(editor?.options.shape??"rectangleShape"):t==="wand"?"colour":t;\n  S.tool = t;\n  if(editor){editor.tool=t;editor.toolbar();editor.optionsBar();}')
# Existing layer rows retain import/history and inline rename; only add row actions.
s=s.replace('${L.locked ? I.lock : I.unlock}</button></li>', '${L.locked ? I.lock : I.unlock}</button><button class="ib row-action" data-a="up" aria-label="${api.lang()==="zh"?"上移图层":"Raise layer"}" title="Alt+↑" ${L.locked?"disabled":""}><svg viewBox="0 0 24 24"><path d="M6 14l6-6 6 6M12 8v12"/></svg></button><button class="ib row-action" data-a="down" aria-label="${api.lang()==="zh"?"下移图层":"Lower layer"}" title="Alt+↓" ${L.locked?"disabled":""}><svg viewBox="0 0 24 24"><path d="M6 10l6 6 6-6M12 4v12"/></svg></button><button class="ib row-action" data-a="del" aria-label="${t.remove}" title="Delete" ${L.locked?"disabled":""}>${I.trash}</button></li>')
s=s.replace('  if (a === "import") return W.file.click();', '''  if (a === "import") return W.file.click();
  if(L && ["up","down","del"].includes(a)){S.selected=L.id;editor.click({target:{closest:()=>({dataset:{edAction:a==="del"?"remove":a}})},preventDefault(){},stopPropagation(){}});return;}'''.replace('\n+','\n'),1)
s=s.replace('  const done = (ok) => { if (ok &&', '  let finished=false;\n  const done = (ok) => { if(finished)return;finished=true;if (ok &&',1)
a=s.index('  W.tools.innerHTML = ["move", "wand", "pan"]');b=s.index('  const [p, o] = W.view.children;',a)
s=s[:a]+'  editor?.toolbar();editor?.optionsBar();\n'+s[b:]
s=s.replace('checkpoint, changed, draw, annulus, error:toast,tool:setTool,rebuild:', 'checkpoint, changed, draw, annulus, fit, rename:id=>{const row=W.left.querySelector(`[data-id="${id}"]`);if(row)leftDbl({target:row.querySelector(".nm")});}, error:toast,tool:setTool,rebuild:')
s=s.replace('  W.canvas.addEventListener("keydown",e=>{if(editor.key(e))', '  W.canvas.addEventListener("keydown",e=>{if(!spaceDown&&e.key!==" "&&editor.key(e))')
# Capture editor tool keys before the shell shortcuts, without changing other routes.
s=s.replace('  addEventListener("keydown", onKey);', '''  let temporaryTool=null;
  addEventListener("keydown",e=>{
    if(!isOn()||!S||e.isComposing||e.ctrlKey||e.metaKey||e.altKey||e.target.closest?.("input,select,textarea,[contenteditable=true]"))return;
    if(e.key===" "){if(!e.repeat&&temporaryTool===null){temporaryTool=S.tool;editor.drag=null;spaceDown=true;setTool("pan");}e.preventDefault();e.stopPropagation();return;}
    const t=({v:"move",r:"rectangle",f:"lasso",c:"ring",g:"sector",w:"colour",y:"shape",n:"pen",h:"pan"})[e.key.toLowerCase()];
    if(t&&!e.shiftKey){if(!e.repeat){editor.drag=null;setTool(t);}e.preventDefault();e.stopPropagation();}
  },true);
  addEventListener("keyup",e=>{if(e.key===" "&&temporaryTool!==null){const t=temporaryTool;temporaryTool=null;spaceDown=false;setTool(t);e.preventDefault();e.stopPropagation();}},true);
  addEventListener("blur",()=>{if(temporaryTool!==null){const t=temporaryTool;temporaryTool=null;spaceDown=false;setTool(t);}});
  addEventListener("keydown", onKey);'''.replace('\n+','\n'))
p.write_text(s,encoding='utf8')
