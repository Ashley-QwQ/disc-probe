"""Same single-material ring in both editor views, both themes and languages."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence/editor/lamp'
OUT.mkdir(parents=True,exist_ok=True)
plan=[]
for theme,lang in [('light','zh'),('dark','zh'),('light','en'),('dark','en')]:
    prefix=f'{theme}-{lang}'
    steps=[dict(eval=f"localStorage.setItem('dp-theme','{theme}');localStorage.setItem('dp-lang','{lang}');location.reload()"),dict(wait=1500),dict(eval="document.querySelector('#lobby-new').click()"),dict(wait=400),dict(eval="document.querySelector('#next').click()"),dict(wait=1800),dict(eval="""(async()=>{
globalThis.A=(await import('./design.js')).editorActions();
const e=A.editor,m=e.palette.swatches.find(m=>m.period_um>1.5&&m.period_um<1.7);e.material=m.id;
e.h.tool('ring');e.select({tool:'ring',inner:32,outer:46});e.options.fillKind='material';e.options.target='mask';e.fill();
A.state().activeMask=null;e.h.changed();e.panels();e.h.draw();
if(A.state().view!=='proj')throw Error('Design must be the default');
globalThis.originalDocument=JSON.stringify(e.document());
const c=e.preview(),data=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
for(let j=0;j<c.height;j++)for(let i=0;i<c.width;i++){const r=Math.hypot((i+.5)*120/c.width-60,60-(j+.5)*120/c.height);if(r<33||r>=45)continue;const at=(j*c.width+i)*4;if(data[at]!==data[at+1]||data[at]!==data[at+2])throw Error('Design map must be neutral');}
return {defaultView:A.state().view,material:m.id,period:m.period_um,neutral:true};})()""",print=True),dict(shot=prefix+'-ring-design'),dict(eval="document.querySelector('[data-v=lamp]').click()"),dict(wait=200),dict(eval="""(()=>{
const e=A.editor,c=e.preview(),data=c.getContext('2d').getImageData(0,0,c.width,c.height).data,colours=new Set();let dark=0,colour=0;
for(let j=0;j<c.height;j++)for(let i=0;i<c.width;i++){const x=(i+.5)*120/c.width-60,y=60-(j+.5)*120/c.height,r=Math.hypot(x,y);if(r<32||r>=46)continue;const at=(j*c.width+i)*4,rgb=[...data.slice(at,at+3)];colours.add(rgb.join(','));if(Math.max(...rgb)<60)dark++;if(Math.max(...rgb)-Math.min(...rgb)>15)colour++;}
if(colours.size<100||!dark||!colour)throw Error('Ring must have colour sweep and dark sectors');
if(originalDocument!==JSON.stringify(e.document()))throw Error('View switching changed the work');
const same=e.preview();if(same!==c)throw Error('Preview not cached');
const poseCount=e.deltaCache.maps.size;A.state().scene.cam[0]+=20;e.preview();if(e.deltaCache.maps.size!==poseCount+1)throw Error('Pose cache not refreshed');A.state().scene.cam[0]-=20;e.preview();e.h.draw();
return {passed:true,colours:colours.size,darkPixels:dark,colourPixels:colour,poseCache:e.deltaCache.maps.size};})()""",print=True,save=prefix+'-checks.json'),dict(shot=prefix+'-ring-lamp'),dict(eval="document.querySelector('[data-v=proj]').click();if(originalDocument!==JSON.stringify(A.editor.document()))throw Error('Return changed the work')")]
    # Wait for the canvas' scheduled paint after the pose-cache check restores pose.
    shot=next(i for i,s in enumerate(steps) if s.get('shot','').endswith('-ring-lamp'))
    steps.insert(shot,dict(wait=200))
    steps.insert(shot+2,dict(eval="A.editor.document()",save=prefix+'-ring-work.json'))
    plan.append(dict(url='http://127.0.0.1:8796/home/index.html',theme=theme,steps=steps))
(OUT/'capture-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf8')
