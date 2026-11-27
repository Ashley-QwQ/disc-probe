from pathlib import Path
p=Path('discprobe/web/home/design.js');s=p.read_text(encoding='utf8')
s=s.replace('import { processingWorker }', 'import { Editor } from "./design/editor-ui.mjs";\nimport * as EditorOps from "./design/editor-ops.mjs";\n\nimport { processingWorker }',1)
s=s.replace('let S = null;', 'let editor = null;\nlet S = null;',1)
s=s.replace('return { layers: S.layers.map', 'return { editor: structuredClone({selections:S.selections, assignments:S.assignments, activeMask:S.activeMask, maskGrid:S.maskGrid, materials:S.materials}), layers: S.layers.map',1)
s=s.replace('  S.selected = snap.selected;', '  Object.assign(S, snap.editor ?? {});\n  editor?.invalidate();\n  S.selected = snap.selected;',1)
s=s.replace('  if (!/^image\\/(png|jpeg|webp|bmp)$/.test(f.type))', '  if (!/^image\\/(png|jpeg|webp|bmp|svg\\+xml)$/.test(f.type))',1)
s=s.replace('    let bmp;\n    try { bmp = await createImageBitmap(f); }', '''    let bmp, svg;
    try {
      if (f.type === "image/svg+xml" || /\\.svg$/i.test(f.name)) {
        svg = await f.text();
        const parsed = new DOMParser().parseFromString(svg, "image/svg+xml");
        if (parsed.querySelector("parsererror,script,foreignObject") || [...parsed.querySelectorAll("*")].some(n => [...n.attributes].some(a => /^on/i.test(a.name) || /(?:https?:|file:|javascript:)/i.test(a.value)))) throw Error("SVG must be self-contained");
        const url = URL.createObjectURL(new Blob([svg], {type:"image/svg+xml"}));
        try { bmp = await new Promise((ok,no)=>{const im=new Image();im.onload=()=>ok(im);im.onerror=no;im.src=url;}); } finally { URL.revokeObjectURL(url); }
      } else bmp = await createImageBitmap(f);
    }'''.replace('\n+','\n'),1)
s=s.replace('    if (L) L.file = f;', '    if (L) { L.file = f; L.sourceKind = svg ? "svg" : "bitmap"; if(svg)L.svg=svg; }',1)
s=s.replace('  draw(); queueCompose();','  editor?.invalidate();\n  draw(); queueCompose();',1)
s=s.replace('function compose() {','function compose() {',1) # async declaration unchanged
s=s.replace('  if (composing) { composeAgain', '  if (editor) { comp = null; draw(); return; }\n  if (composing) { composeAgain',1)
s=s.replace('  // selected pixels, inverted','  editor?.paint(g);\n  // selected pixels, inverted',1)
s=s.replace('  if (!S) return;\n  W.canvas.setPointerCapture', '  if (!S) return;\n  if (e.button===0 && !spaceDown && editor?.pointer("down",e,toMm(...canvasPoint(e)))) {e.preventDefault();return;}\n  W.canvas.setPointerCapture',1)
s=s.replace('function onMove(e) {\n  if (!S) return;', 'function onMove(e) {\n  if (!S) return;\n  if(editor?.pointer("move",e,toMm(...canvasPoint(e))))return;',1)
s=s.replace('function onUp(e) {', 'function onUp(e) {\n  if(editor?.pointer(e.type==="pointercancel"?"cancel":"up",e,toMm(...canvasPoint(e))))return;',1)
s=s.replace('  const L = sel(), k = e.key;', '''  const L = sel(), k = e.key;
  if (k === "Escape" && editor?.drag) {editor.drag=null;draw();return;}
  if (k === "Escape" && S.activeMask) {checkpoint();S.activeMask=null;editor.invalidate();changed();editor.panels();return;}
  if (k === "F2" && L) {e.preventDefault();W.left.querySelector('[data-ed-layer-name]')?.focus();return;}
  if (e.altKey && ["ArrowUp","ArrowDown"].includes(k) && L && !L.locked) {e.preventDefault();editor.click({target:{closest:()=>({dataset:{edAction:k==="ArrowUp"?"up":"down"}})},preventDefault(){},stopPropagation(){}});return;}
'''.replace('\n+','\n'),1)
s=s.replace('  S.tool = t;', '  S.tool = t;\n  if(editor)editor.tool=t;',1)
s=s.replace('  W.left.innerHTML =', '  W.left.innerHTML =',1)
s=s.replace('\nfunction refreshLayerRows()', '\nfunction refreshLayerRows()',1)
s=s.replace('    if (L.kind === "image") li.querySelector(".th").replaceWith(thumb(L));\n  }\n}', '    if (L.kind === "image") li.querySelector(".th").replaceWith(thumb(L));\n  }\n  editor?.left();\n}',1)
s=s.replace('function buildRight() {', 'function buildRight() {\n  if(editor){editor.right();return;}',1)
s=s.replace('FILE_VERSION = 1','FILE_VERSION = 2',1)
s=s.replace('  return JSON.stringify({\n    format: FILE_KIND,', '  const portable = editor?.document();\n  return JSON.stringify({\n    ...portable,\n    format: FILE_KIND,',1)
s=s.replace('lookY: S.lookY, layers,','lookY: S.lookY, layers: layers.map((l,i)=>({...l,...portable?.layers[i]})),',1)
s=s.replace('  const layers = [];\n  for (const e of data.layers)', '  const layers = [];\n  for (const e of data.layers)',1)
s=s.replace('id: nextId++, kind: e.kind === "fx"', 'id: e.id ?? nextId++, kind: e.kind === "fx"',1)
s=s.replace('      if (typeof e.original', '      Object.assign(L,{sourceKind:e.sourceKind,shape:e.shape,svg:e.svg});\n      if (typeof e.original',1)
s=s.replace('  S.layers = layers.slice(0, 16);', '''  S.layers = layers.slice(0, 16);
  nextId=Math.max(nextId,...S.layers.map(l=>Number(l.id)+1));
  for(const k of ["selections","assignments","materials","maskGrid","activeMask"])if(k in data)S[k]=structuredClone(data[k]);
  editor?.init();editor?.invalidate();'''.replace('\n+','\n'),1)
s=s.replace('image/png,image/jpeg,image/webp,image/bmp','image/png,image/jpeg,image/webp,image/bmp,image/svg+xml',1)
s=s.replace('  new ResizeObserver(resize).observe(W.cv);', '''  editor = new Editor({state:()=>S,dom:()=>W,lang:()=>api.lang(),view:()=>V,colour:cssVar,
    checkpoint, changed, draw, annulus, error:toast,tool:setTool,rebuild:()=>{buildLeft();buildRight();},
    raster:g=>rasterise(-60,-60,60,60,g.width/120,false),
    shape:(kind,points)=>{
      const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]),x0=Math.min(...xs),y0=Math.min(...ys),width=Math.max(.5,Math.max(...xs)-x0),height=Math.max(.5,Math.max(...ys)-y0);
      const local=points.map(([x,y])=>[(x-x0)/width-.5,(y-y0)/height-.5]);
      const type=kind==="rectangleShape"?"rectangle":kind==="pen"?"stroke":kind;
      const shape={type,points:type==="line"?[local[0],local.at(-1)]:local,stroke:.035};
      const c=document.createElement("canvas");c.width=Math.max(1,Math.ceil(width*8));c.height=Math.max(1,Math.ceil(height*8));const g=c.getContext("2d");const px=g.createImageData(c.width,c.height);
      for(let j=0;j<c.height;j++)for(let i=0;i<c.width;i++)if(EditorOps.shapeHit(shape,(i+.5)/c.width-.5,(j+.5)/c.height-.5))px.data.set([30,30,30,255],4*(j*c.width+i));
      g.putImageData(px,0,0);const l=addImageLayer(editor.t[kind]??kind,c,c.width,c.height);if(l){Object.assign(l,{x:x0+width/2,y:y0+height/2,width,sourceKind:kind==="pen"?"stroke":"shape",shape});changed();}
    }});
  W.canvas.tabIndex=0;W.canvas.setAttribute("aria-label","Disc editor canvas");
  new ResizeObserver(resize).observe(W.cv);'''.replace('\n+','\n'),1)
s=s.replace('function projection(ppm) {', 'function projection(ppm) {\n  if(editor)return editor.preview(Math.min(1200,Math.round(120*ppm)));',1)
s=s.replace('  const { bits, rMax } = await designBits((stage) => onProgress({ stage, fraction: null }));', '''  let saved, rMax;
  if(editor){
    onProgress({stage:t.drawing,fraction:null});
    const response=await fetch("/api/compose",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(editor.document()),signal});
    saved=await response.json();if(!response.ok)throw Error(saved.error??t.failed);rMax=pictureRange()[1];
  }else{
  const { bits, rMax:rm } = await designBits((stage) => onProgress({ stage, fraction: null }));rMax=rm;'''.replace('\n+','\n'),1)
s=s.replace('  const saved = await up.json().catch(() => ({}));', '  saved = await up.json().catch(() => ({}));',1)
s=s.replace('  if (!up.ok) throw new Error(saved.error ?? t.failed);', '  if (!up.ok) throw new Error(saved.error ?? t.failed);\n  }',1)
s=s.replace('design_npy: saved.design_npy, output, r_max: rMax','design_npy: saved.design_npy, ...(saved.textures?{textures:saved.textures}:{}), output, r_max: rMax',1)
s=s.replace('  buildLeft(); buildRight(); draw();\n}\n\nlet toastT', '  buildLeft(); buildRight(); editor?.panels(); draw();\n}\n\nlet toastT',1)
s += '''
// Public automation/export surface uses the same actions and document serializer as the UI.
export const editorDocument = () => editor.document();
export const editorActions = () => ({editor, importFiles, openProject, projectText, undo, redo, state:()=>S});
'''.replace('\n+','\n')
p.write_text(s,encoding='utf8')
