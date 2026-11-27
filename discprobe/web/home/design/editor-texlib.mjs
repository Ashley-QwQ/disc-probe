// Presentation policy only. Core/CLI remain unrestricted by these defaults.
export const HELD_MAX_CHANGE=15, MIN_VISIBLE_Y=.04, MERGE_DISTANCE=2;

export function lab(rgb){
  const v=rgb.map(c=>{c/=255;return c<=.04045?c/12.92:((c+.055)/1.055)**2.4;});
  const xyz=[(.4124564*v[0]+.3575761*v[1]+.1804375*v[2])/.95047,
    .2126729*v[0]+.7151522*v[1]+.0721750*v[2],(.0193339*v[0]+.1191920*v[1]+.9503041*v[2])/1.08883];
  const f=xyz.map(t=>t>(6/29)**3?Math.cbrt(t):t/(3*(6/29)**2)+4/29);
  return [116*f[1]-16,500*(f[0]-f[1]),200*(f[1]-f[2])];
}
export function visible(m){return Number.isFinite(m.y)&&m.y>=MIN_VISIBLE_Y;}
export function held(m,threshold=HELD_MAX_CHANGE){return visible(m)&&m.fades===false&&Number.isFinite(m.stability)&&m.stability<=threshold;}
export function warning(m,zh=true){
  if(!visible(m)||m.fades===true)return zh?'一斜就看不见':'May disappear when tilted';
  if(!held(m))return zh?'手持时会变色':'Changes colour when held';
  return '';
}
export function curated(entries,mode='held',threshold=HELD_MAX_CHANGE){
  const ranked=entries.filter(({m})=>mode==='camera'?visible(m):held(m,threshold)).map(v=>({...v,lab:lab(v.light.rgb)}));
  ranked.sort((a,b)=>(a.m.stability??Infinity)-(b.m.stability??Infinity)||(b.m.purity??0)-(a.m.purity??0)||a.m.id.localeCompare(b.m.id));
  const groups=[];
  for(const v of ranked){const g=groups.find(g=>Math.hypot(...v.lab.map((c,i)=>c-g.lab[i]))<MERGE_DISTANCE);
    if(g)g.count++;else groups.push({...v,count:1});}
  return groups.sort((a,b)=>a.light.hue-b.light.hue||a.m.id.localeCompare(b.m.id));
}
