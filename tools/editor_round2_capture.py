"""Second-round screenshot matrix; uses the same editor actions and controls."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence/editor/round2';OUT.mkdir(parents=True,exist_ok=True)
items=[]
imports="""(async()=>{
const svg='<svg xmlns="http://www.w3.org/2000/svg" width="240" height="160"><path fill="#232323" d="M20 140V20h100v25H50v30h60v25H50v40z"/><circle fill="#be1414" cx="172" cy="76" r="46"/></svg>';
const c=document.createElement('canvas');c.width=220;c.height=140;const g=c.getContext('2d');g.fillStyle='#202020';g.fillRect(10,10,200,120);g.clearRect(35,35,150,70);g.fillStyle='#888';g.fillRect(70,55,80,30);
const blob=await new Promise(r=>c.toBlob(r));await A.importFiles([new File([svg],'Letter F.svg',{type:'image/svg+xml'}),new File([blob],'Frame.png',{type:'image/png'})]);
A.state().layers[0].x=-10;A.state().layers[0].y=-10;A.state().layers[1].x=17;A.state().layers[1].y=15;A.state().layers[1].width=56;A.editor.h.changed();A.editor.h.rebuild();return A.state().layers.map(l=>({name:l.name,kind:l.sourceKind}));})()"""
checks=(ROOT/'tools/editor_round2_browser.mjs').read_text(encoding='utf8').replace('export async function verify','async function verify')
for theme,lang in [('light','zh'),('dark','zh'),('light','en'),('dark','en')]:
    prefix=f'{theme}-{lang}'
    steps=[dict(eval=f"localStorage.setItem('dp-theme','{theme}');localStorage.setItem('dp-lang','{lang}');location.reload()"),dict(wait=1600),dict(eval="document.querySelector('#lobby-new').click()"),dict(wait=500),dict(eval="document.querySelector('#next').click()"),dict(wait=2100),dict(eval="(async()=>{globalThis.A=(await import('./design.js')).editorActions();return {mode:document.documentElement.dataset.mode,tools:document.querySelectorAll('.tools-v button').length}})()",print=True),dict(shot=prefix+'-empty'),dict(eval=imports,print=True),dict(wait=250),dict(shot=prefix+'-imports')]
    tools=[('select','move',None),('rectangle','rectangle',dict(tool='rectangle',a=[-46,-33],b=[8,20])),('lasso','lasso',dict(tool='lasso',points=[[-50,-20],[-20,-48],[10,-28],[35,12],[-25,35]])),('ring','ring',dict(tool='ring',inner=32,outer=46)),('sector','sector',dict(tool='sector',inner=28,outer=52,start=300,end=70)),('colour','colour',None),('shape','shape',None),('pen','pen',None),('hand','pan',None)]
    for name,tool,definition in tools:
        script=f"A.editor.h.tool('{tool}');"
        if definition:script+=f"A.editor.select({json.dumps(definition)});"
        if name=='select':script+="A.state().activeMask=null;A.editor.h.changed();"
        if name=='colour':script+="{const g=A.state().maskGrid,{g:c}=A.editor.h.raster(g);A.editor.select({tool:'colour',seed:[310,310],tolerance:18,contiguous:true},'replace',c.getImageData(0,0,600,600).data)};"
        if name=='pen':script+="A.editor.pointer('down',{},[-43,3]);A.editor.pointer('move',{},[-35,12]);A.editor.pointer('move',{},[-28,2]);A.editor.h.draw();"
        steps += [dict(eval=script),dict(wait=180),dict(shot=prefix+'-tool-'+name)]
        if name=='pen':steps += [dict(eval="A.editor.pointer('cancel',{},[0,0]);A.editor.h.draw()")]
    steps += [dict(eval="A.editor.h.tool('ring');A.editor.select({tool:'ring',inner:32,outer:46});A.editor.options.fillKind='material';A.editor.options.target='mask';A.editor.fill();A.state().activeMask=null;A.editor.h.changed();A.editor.panels()"),dict(wait=180),dict(shot=prefix+'-ring-material')]
    steps += [dict(eval="A.editor.select({tool:'ring',inner:28,outer:54});A.editor.options.fillKind='pattern';A.editor.options.pattern='diamond';A.editor.fill();A.state().activeMask=null;A.editor.h.changed();A.editor.panels();{const n=document.querySelector('.ed-material-scroll');n.scrollTop=n.scrollHeight}"),dict(wait=180),dict(shot=prefix+'-diamond')]
    steps += [dict(eval="A.editor.options.fillKind='material';A.editor.right();document.querySelector('.ed-material-scroll').scrollTop=0"),dict(wait=180),dict(shot=prefix+'-materials')]
    steps += [dict(eval="A.editor.h.shape('ellipse',[[-47,-6],[-25,16]]);A.state().layers.at(-1).name='Ellipse';A.editor.select({tool:'ring',inner:32,outer:46});document.querySelector('[data-ed-action=save-mask]').click();A.state().selections.find(m=>m.id===A.state().activeMask).name=A.editor.h.lang()==='zh'?'圆环蒙版':'Ring mask';A.editor.select({tool:'sector',inner:28,outer:52,start:300,end:70});document.querySelector('[data-ed-action=save-mask]').click();A.state().selections.find(m=>m.id===A.state().activeMask).name=A.editor.h.lang()==='zh'?'扇形蒙版':'Sector mask';A.editor.h.tool('sector');A.editor.h.changed();A.editor.h.rebuild();A.editor.h.dom().left.scrollTop=0"),dict(wait=180),dict(shot=prefix+'-layers-selections')]
    steps += [dict(eval='(async()=>{'+checks+';return await verify(A)})()',print=True)]
    items.append(dict(url='http://127.0.0.1:8796/home/index.html',theme=theme,steps=steps))
target='capture-plan.json'
if '--select' in sys.argv:
    target='capture-select-plan.json'
    for item in items:
        stop=next(i for i,s in enumerate(item['steps']) if s.get('shot','').endswith('-tool-select'))
        item['steps']=[s for s in item['steps'][:stop+1] if not s.get('shot','').endswith('-empty')]
        item['steps'].append(dict(eval="""(()=>{const bar=A.editor.h.dom().bar,c=document.createElement('canvas').getContext('2d');const fields=[...bar.querySelectorAll('input[type=number]')].map(i=>{const s=getComputedStyle(i);c.font=s.font;return {key:i.dataset.k,value:i.value,width:i.clientWidth,textWidth:c.measureText(i.value).width,inner:i.clientWidth-parseFloat(s.paddingLeft)-parseFloat(s.paddingRight)}});if(fields.some(f=>f.textWidth+2>f.inner))throw Error('numeric field clipping');return {passed:true,fields};})()""",print=True))
(OUT/target).write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf8')
