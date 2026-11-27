"""Small source updates kept out of shell quoting."""
from pathlib import Path
p=Path('discprobe/web/home/design/editor-ui.mjs');s=p.read_text(encoding='utf8')
s=s.replace("height:l.width*l.h/l.w,rot:l.rot", "height:l.kind==='fx'?l.height:l.width*l.h/l.w,rot:l.rot")
s=s.replace("sourceKind:l.sourceKind??'bitmap',shape:l.shape", "sourceKind:l.sourceKind??(l.kind==='fx'?'shape':'bitmap'),fxKind:l.fxKind,y1:l.y1,y2:l.y2,shape:l.shape")
s=s.replace("draw:'拖动绘制；多边形松手闭合'", "draw:'拖动绘制，多边形松手闭合。画布上用方向键移动、空格起笔、Enter 完成。'")
s=s.replace("draw:'Drag to draw; polygons close on release'", "draw:'Drag to draw; polygons close on release. On canvas: arrows move, Space starts, Enter finishes.'")
s=s.replace("this.palette?.swatches.find(m=>m.period_um>1.6)?.id", "this.palette?.swatches.find(m=>m.rgb[1]>200&&m.rgb[0]<100)?.id")
p.write_text(s,encoding='utf8')
