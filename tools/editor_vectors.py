"""Shared, small test inputs, kept in the repository for independent runners."""
import base64
import json
from pathlib import Path
from discprobe.editor_ops import grid
root=Path(__file__).resolve().parents[1]
g=grid(96)
defs=[dict(tool='rectangle',a=[-43,-31],b=[22,28]),dict(tool='rectangle',a=[22,28],b=[-43,-31]),
      dict(tool='rectangle',a=[0,0],b=[0,12]),dict(tool='lasso',points=[[-52,0],[-9,-54],[45,12],[5,42]]),
      dict(tool='lasso',points=[[-40,-40],[40,40],[-40,40],[40,-40]]),
      dict(tool='ring',inner=24,outer=58),dict(tool='ring',inner=0,outer=7.5),
      dict(tool='sector',inner=24,outer=58,start=310,end=45),dict(tool='sector',inner=0,outer=60,start=90,end=450),
      dict(tool='sector',inner=24,outer=40,start=15,end=15),dict(tool='sector',inner=30,outer=50,start=-60,end=85)]
colour_grid={**g,'width':9,'height':7}
rgba=[]
for j in range(7):
    for i in range(9):
        rgba.extend([230,230,230,255] if i==4 else [80+i%3,90,110,0 if j==6 else 255])
vectors=[dict(name=f'{d["tool"]}-{i}',definition=d,grid=g) for i,d in enumerate(defs)]
for tol in (0,2,255):
    for contiguous in (False,True):
        vectors.append(dict(name=f'colour-{tol}-{contiguous}',definition=dict(tool='colour',seed=[1,2],tolerance=tol,contiguous=contiguous),grid=colour_grid,rgba=rgba))
vectors.append(dict(name='colour-outside',definition=dict(tool='colour',seed=[-1,0]),grid=colour_grid,rgba=rgba))
target=root/'tests/fixtures/editor-vectors.json';target.parent.mkdir(exist_ok=True)
target.write_text(json.dumps(vectors,indent=2)+'\n',encoding='utf8')
