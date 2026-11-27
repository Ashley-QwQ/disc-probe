import json
from pathlib import Path
p=Path('evidence/editor/round2')
plan=json.loads((p/'capture-select-plan.json').read_text(encoding='utf8'))[:1]
plan[0]['steps'].append(dict(eval="""(()=>{const i=document.querySelector('.fbar input'),s=getComputedStyle(i);return {matches:i.matches('.ws .fbar input'),style:i.getAttribute('style'),width:s.width,min:s.minWidth,max:s.maxWidth,flex:s.flex,font:s.font,fontSize:s.fontSize,box:s.boxSizing,sheets:[...document.styleSheets].filter(s=>s.href?.includes('design.css')).map(s=>({href:s.href,rules:[...s.cssRules].filter(r=>r.selectorText?.includes('.fbar input')).map(r=>r.cssText)}))}})()""",print=True))
(p/'style-probe-plan.json').write_text(json.dumps(plan),encoding='utf8')
