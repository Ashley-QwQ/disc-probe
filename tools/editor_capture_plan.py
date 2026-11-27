import json
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
items=[]
for theme,lang in [('light','zh'),('dark','zh'),('light','en'),('dark','en')]:
    prefix=f'{theme}-{lang}'
    steps=[dict(eval=f"localStorage.setItem('dp-theme','{theme}');localStorage.setItem('dp-lang','{lang}');location.reload()"),dict(wait=2200),dict(eval="document.querySelector('#lobby-new').click()"),dict(wait=750),dict(eval="document.querySelector('#next').click()"),dict(wait=2400),
           dict(eval="(async()=>{globalThis.A=(await import('./design.js')).editorActions();return {mode:document.documentElement.dataset.mode,layers:A.state().layers.length}})()",print=True),dict(shot=prefix+'-empty')]
    steps += [dict(eval="""(async()=>{
      const svg='<svg xmlns="http://www.w3.org/2000/svg" width="240" height="160"><path fill="#232323" d="M20 140V20h100v25H50v30h60v25H50v40z"/><circle fill="#be1414" cx="172" cy="76" r="46"/></svg>';
      const c=document.createElement('canvas');c.width=220;c.height=140;const g=c.getContext('2d');g.fillStyle='#202020';g.fillRect(10,10,200,120);g.clearRect(35,35,150,70);g.fillStyle='#888';g.fillRect(70,55,80,30);
      const blob=await new Promise(r=>c.toBlob(r));await A.importFiles([new File([svg],'Letter F.svg',{type:'image/svg+xml'}),new File([blob],'Frame.png',{type:'image/png'})]);
      A.state().layers[0].x=-10;A.state().layers[0].y=-10;A.state().layers[1].x=17;A.state().layers[1].y=15;A.state().layers[1].width=56;
      A.editor.invalidate();A.editor.h.changed();return A.state().layers.map(l=>({name:l.name,kind:l.sourceKind}));})()""",print=True),dict(wait=700),dict(shot=prefix+'-imports')]
    defs=[('rectangle',dict(tool='rectangle',a=[-46,-33],b=[8,20])),('lasso',dict(tool='lasso',points=[[-50,-20],[-20,-48],[10,-28],[35,12],[-25,35]])),('ring',dict(tool='ring',inner=32,outer=45)),('sector',dict(tool='sector',inner=27,outer=53,start=300,end=70))]
    for name,d in defs:
        steps += [dict(eval=f"A.editor.tool='{name}';A.editor.select({json.dumps(d)});A.editor.h.dom().left.scrollTop=110"),dict(wait=200),dict(shot=prefix+'-'+name)]
    steps += [dict(eval="A.editor.tool='colour';{const g=A.state().maskGrid,{g:c}=A.editor.h.raster(g);A.editor.select({tool:'colour',seed:[310,310],tolerance:20,contiguous:true},'replace',c.getImageData(0,0,600,600).data)}"),dict(wait=200),dict(shot=prefix+'-colour')]
    steps += [dict(eval="A.editor.tool='ring';A.editor.select({tool:'ring',inner:32,outer:45});A.editor.options.fillKind='material';A.editor.options.target='mask';A.editor.fill();A.state().activeMask=null;A.editor.invalidate();A.editor.h.changed();A.editor.panels()"),dict(wait=200),dict(shot=prefix+'-ring-material')]
    steps += [dict(eval="A.editor.select({tool:'ring',inner:28,outer:54});A.editor.options.fillKind='pattern';A.editor.options.pattern='diamond';A.editor.fill();A.state().activeMask=null;A.editor.invalidate();A.editor.h.changed();A.editor.panels()"),dict(wait=200),dict(shot=prefix+'-diamond')]
    steps += [dict(eval="A.editor.options.fillKind='material';A.editor.right();A.editor.h.dom().left.scrollTop=0;A.editor.h.dom().right.scrollTop=0"),dict(wait=150),dict(shot=prefix+'-materials')]
    steps += [dict(eval="A.editor.select({tool:'sector',inner:24,outer:58,start:40,end:160});A.undo()"),dict(wait=150),dict(shot=prefix+'-undo')]
    steps += [dict(eval="(async()=>{const text=await A.projectText();const n=A.state().layers.length;await A.openProject(new File([text],'Round trip.discdesign',{type:'application/json'}));return {roundtripLayers:A.state().layers.length,expected:n,selections:A.state().selections.length,assignments:A.state().assignments.length,svg:A.state().layers[0].svg?.slice(0,4),version:JSON.parse(await A.projectText()).version}})()",print=True)]
    check=(root/'tools/editor_browser_checks.mjs').read_text(encoding='utf8').replace('export async function verify','async function verify')
    steps.append(dict(eval='(async()=>{'+check+';return await verify(A)})()',print=True))
    if theme=='light' and lang=='zh' and '--visual' not in sys.argv:
        steps.append(dict(eval="""(async()=>{const O=await import('./design/editor-ops.mjs'),document=A.editor.document(),labels=O.compose(document,O.grid(6000));const digest=await crypto.subtle.digest('SHA-256',labels);const page_sha256=[...new Uint8Array(digest)].map(v=>v.toString(16).padStart(2,'0')).join('');const r=await fetch('/api/compose',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(document)});const saved=await r.json();if(!r.ok)throw Error(JSON.stringify(saved));return {document,page_sha256,saved};})()""",save='browser-compose.json'))
    items.append(dict(url='http://127.0.0.1:8796/home/index.html',theme=theme,steps=steps))
target=root/'evidence/editor/capture-plan.json';target.write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf8')
