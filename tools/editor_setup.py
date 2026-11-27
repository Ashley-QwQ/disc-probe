"""One-time offline adaptation of the project's pattern prototype and dev launcher."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=root/'discprobe/web/home/design/pattern.mjs'
s=p.read_text(encoding='utf8').replace("const fs=require('node:fs');",'')
s=s.replace('const out=Buffer.alloc(w*h*2)','const out=new Uint16Array(w*h)').replace('out.writeUInt16LE(val,2*(j*w+i));','out[j*w+i]=val;')
s=s[:s.index('module.exports=')]+'export {render,validate};\n'
p.write_text(s,encoding='utf8')
p=root/'devserve.py'
s=p.read_text(encoding='utf8').replace('MAIN = HERE.parents[2]','MAIN = Path("D:/disc-probe")')
s=s.replace('GEO_GOOD = HERE /','GEO_GOOD = MAIN /')
p.write_text(s,encoding='utf8')
