// Deterministic editor raster operations. Cell centres, mm, x right/y down.
import {render as pattern} from './pattern.mjs';
import {tone,table,luminance,Diffusion,matrixDark} from './tone.mjs';
export const q = v => Math.floor(v * 1e6 + .5) / 1e6;
const COVERAGE=[0,8,2,10,12,4,14,6,3,11,1,9,15,7,13,5];
export const grid = (size=600) => ({width:size,height:size,left_mm:-60,top_mm:-60,cell_mm:120/size,annulus_mm:[24,58]});
export const bytes = s => Uint8Array.from(atob(s), c=>c.charCodeAt(0));
export function base64(a) { let s=''; for(let i=0;i<a.length;i+=8192)s+=String.fromCharCode(...a.subarray(i,i+8192));return btoa(s); }
export function polygon(x,y,ps) {
  let inside=false;
  for(let i=0,j=ps.length-1;i<ps.length;j=i++) {
    const [a,b]=ps[i],[c,d]=ps[j];
    if((b>y)!==(d>y) && x<(c-a)*(y-b)/(d-b)+a) inside=!inside;
  } return inside;
}
export function booleanMask(a,b,op='replace') {
  if(a.length!==b.length)throw Error('mask dimensions');
  return Uint8Array.from(b,(v,i)=>+(op==='add'?(a[i]||v):op==='subtract'?(a[i]&&!v):op==='intersect'?(a[i]&&v):v));
}
export function selection(d,g,rgba=null) {
  const {width:w,height:h,cell_mm:c}=g, out=new Uint8Array(w*h);
  if(d.tool==='colour') {
    if(!rgba||rgba.length!==w*h*4)throw Error('colour source dimensions');
    const sx=Math.floor(d.seed[0]),sy=Math.floor(d.seed[1]);
    if(sx<0||sx>=w||sy<0||sy>=h)return out;
    const seed=(sy*w+sx)*4,t=d.tolerance??18;
    for(let i=0;i<w*h;i++)out[i]=+([0,1,2,3].every(k=>Math.abs(rgba[4*i+k]-rgba[seed+k])<=t));
    if(d.contiguous!==false) {
      const found=new Uint8Array(w*h), todo=[sy*w+sx];found[todo[0]]=1;
      for(let at=0;at<todo.length;at++){const i=todo[at],x=i%w,y=Math.floor(i/w);
        for(const n of [x>0?i-1:-1,x<w-1?i+1:-1,y>0?i-w:-1,y<h-1?i+w:-1])if(n>=0&&out[n]&&!found[n]){found[n]=1;todo.push(n);}}
      return found;
    }return out;
  }
  for(let j=0;j<h;j++)for(let i=0;i<w;i++){
    const x=q(g.left_mm+(i+.5)*c),y=q(g.top_mm+(j+.5)*c),r=q(Math.hypot(x,y));let v=false;
    if(d.tool==='rectangle')v=x>=Math.min(d.a[0],d.b[0])&&x<Math.max(d.a[0],d.b[0])&&y>=Math.min(d.a[1],d.b[1])&&y<Math.max(d.a[1],d.b[1]);
    if(d.tool==='lasso')v=polygon(x,y,d.points);
    if(d.tool==='ring'||d.tool==='sector'){
      v=r>=(d.inner??0)&&r<(d.outer??60);
      if(d.tool==='sector'){const span=((d.end-d.start)%360+360)%360,ang=((Math.atan2(y,x)*180/Math.PI-d.start)%360+360)%360;v=v&&(Math.abs(d.end-d.start)>=360||q(ang)<q(span));}
    }out[j*w+i]=+v;
  }return out;
}
export function migrate(input) {
  const d=structuredClone(input);
  if(!d||!Array.isArray(d.layers)||![1,2].includes(d.version??1))throw Error('unsupported editor document');
  d.format='disc-probe design';d.version=2;d.selections??=[];d.assignments??=[];d.materials??=[{id:'background',spec:'B9',rgb:[205,200,190]},{id:'dark',spec:'A5',rgb:[40,40,40]}];
  d.maskGrid??=grid();d.annulus_mm??=d.media==='cd'?[26,58]:[24,58];d.cell??=.02;
  d.layers.forEach((l,i)=>{l.id??=i+1;l.visible??=true;l.locked??=false;l.opacity??=1;l.x??=0;l.y??=0;l.width??=80;l.rot??=0;l.sourceKind??=l.kind==='image'?'bitmap':l.kind;
    if(l.kind==='fx'){l.shape??={type:'rectangle'};const id=`legacy-fx-${l.id}`;if(!d.assignments.some(a=>a.id===id))d.assignments.push({id,layer:l.id,effect:{kind:l.fxKind,y1:l.y1,y2:l.y2}});}
  });
  return d;
}
export function local(l,x,y){const a=l.rot*Math.PI/180,c=Math.cos(a),s=Math.sin(a),dx=x-l.x,dy=y-l.y;return [q((dx*c+dy*s)/l.width),q((-dx*s+dy*c)/(l.height??l.width*l.h/l.w))];}
export function shapeHit(s,u,v){
  if(s.type==='rectangle')return Math.abs(u)<.5&&Math.abs(v)<.5;
  if(s.type==='ellipse')return u*u+v*v<.25;
  if(s.type==='polygon')return polygon(u,v,s.points);
  const points=s.points??[[-.5,-.5],[.5,.5]],half=(s.stroke??.03)/2;
  for(let i=1;i<points.length;i++){const [a,b]=points[i-1],[c,d]=points[i],dx=c-a,dy=d-b,t=Math.max(0,Math.min(1,((u-a)*dx+(v-b)*dy)/(dx*dx+dy*dy||1)));if((u-a-t*dx)**2+(v-b-t*dy)**2<half*half)return true;}return false;
}
export function sampleMask(m,mg,x,y){const i=Math.floor((x-mg.left_mm)/mg.cell_mm),j=Math.floor((y-mg.top_mm)/mg.cell_mm);return i>=0&&j>=0&&i<mg.width&&j<mg.height?m[j*mg.width+i]:0;}
export function effectPose(e,u,v,parity){
  const a=e.y1??55,b=e.y2??100,lerp=t=>a+(b-a)*t;
  if(e.kind==='sync')return a;
  if(e.kind==='flow')return lerp(.5-v);
  if(e.kind==='ox'){const w=3.5/20/2,o=Math.abs(Math.hypot(u,v)-(.5-w))<=w,x=Math.max(Math.abs(u),Math.abs(v))<=.5-w&&Math.min(Math.abs(u-v),Math.abs(u+v))/Math.SQRT2<=w;return o&&x?(parity?a:b):o?a:x?b:NaN;}
  if(e.kind==='merge'){const x=u*5,y=v*5,r=Math.sqrt(((x-1)**2+y*y)*((x+1)**2+y*y));return r>2.2?NaN:lerp(r);}return NaN;
}
// Same grating equation and default pose as the existing page. Prediction, not photo validation.
export function delta(x,y,phone=70){const cam=[0,-phone,330],lamp=[-43.66,-phone-19.79,330],r=Math.max(Math.hypot(x,y),1e-9);let v=0;for(const p of [cam,lamp]){const n=Math.hypot(p[0]-x,p[1]-y,p[2]);v+=(-(p[0]-x)*y+(p[1]-y)*x)/n/r;}return Math.abs(v);}
// rows: [r0, r1) of the grid only (the canvas's exact view of a window); the result then holds those rows. Error
// diffusion still starts at each picture's first row, so the cells are the ones the whole grid has.
export function compose(input,g=grid(600),{rows=null}={}) {
  const d=migrate(input),w=g.width,h=g.height,[r0,r1]=rows??[0,h],out=new Uint8Array(w*(r1-r0)),mats=new Map(d.materials.map((m,i)=>[m.id,i]));
  if(d.materials.length>256)throw Error('at most 256 material slots');
  const masks=new Map(d.selections.map(s=>[s.id,bytes(s.bits)]));
  const patterns=new Map(),band={...g,height:r1-r0,top_mm:g.top_mm+r0*g.cell_mm,annulus_mm:d.annulus_mm};
  for(const a of d.assignments)if(a.pattern)patterns.set(a,pattern({...a.pattern,materials:a.pattern.materials.map(id=>mats.get(id))},band));
  const shade=(a,j,i,x,y,u,v)=>{
    if(a.pattern)return patterns.get(a)[(j-r0)*w+i];
    if(a.effect){const pose=effectPose(a.effect,u,v,(i+j)%2);if(!Number.isFinite(pose))return -1;const dt=delta(x,y,pose),wave=a.effect.wavelength_um??.53;let best=Infinity,slot=-1;d.materials.forEach((m,k)=>{if(m.period_um){const err=Math.abs(m.period_um*dt-wave);if(err<best){best=err;slot=k;}}});return slot;}
    if(!mats.has(a.material))throw Error('unknown material');return mats.get(a.material);
  };
  const decoded=new Map(d.layers.filter(l=>l.raster).map(l=>[l,bytes(l.raster.rgba)]));
  const key=(r,gg,b)=>(r<<16)|(gg<<8)|b;
  // a template's colours only (editor_ops.compose): the palette's import colours repeat across swatches
  const colourSlots=new Map();d.materials.forEach((m,i)=>{if(m.template_name&&m.rgb&&!colourSlots.has(key(...m.rgb)))colourSlots.set(key(...m.rgb),i);});
  const dark=mats.get('dark')??d.materials.findIndex(m=>m.spec==='A5');
  const cx=i=>q(g.left_mm+(i+.5)*g.cell_mm),cy=j=>q(g.top_mm+(j+.5)*g.cell_mm);
  // the grid cells a layer's frame can touch, with a margin: nothing outside it is inside the layer
  const span=l=>{const a=l.rot*Math.PI/180,c=Math.cos(a),s=Math.sin(a),W=l.width,H=l.height??l.width*l.h/l.w;
    const xs=[],ys=[];for(const u of [-.5,.5])for(const v of [-.5,.5]){xs.push(l.x+u*W*c-v*H*s);ys.push(l.y+u*W*s+v*H*c);}
    const at=(mm,o)=>Math.floor((mm-o)/g.cell_mm);
    return [Math.max(0,at(Math.min(...xs),g.left_mm)-2),Math.min(w-1,at(Math.max(...xs),g.left_mm)+2),Math.max(0,at(Math.min(...ys),g.top_mm)-2),Math.min(h-1,at(Math.max(...ys),g.top_mm)+2)];};
  const P=new Int32Array(w),M=new Int16Array(w),G=new Int32Array(w),T=new Uint8Array(w),D=new Uint8Array(w),U=new Float64Array(w),V=new Float64Array(w);
  for(const l of d.layers){if(!l.visible)continue;const r=l.raster,px=decoded.get(l),assign=d.assignments.filter(a=>a.layer===l.id);if(!r&&!l.shape)continue;
    const [i0,i1,j0,j1]=span(l);
    if(r){
      // a picture: template colours where they match, else its toned grey dithered on this grid (tone.mjs)
      const tn=tone(l.tone),lut=table(tn),fs=tn.dither==='floyd-steinberg'?new Diffusion(w,tn.strength):null;
      for(let j=fs?j0:Math.max(j0,r0);j<=Math.min(j1,r1-1);j++){const y=cy(j);
        P.fill(-1);T.fill(0);
        for(let i=i0;i<=i1;i++){const x=cx(i),[u,v]=local(l,x,y);U[i]=u;V[i]=v;
          const sx=Math.floor((u+.5)*r.width),sy=Math.floor((v+.5)*r.height);
          if(sx<0||sy<0||sx>=r.width||sy>=r.height)continue;
          const p=4*(sy*r.width+sx),match=colourSlots.get(key(px[p],px[p+1],px[p+2]));
          P[i]=p;M[i]=match??-1;G[i]=lut[luminance(px[p],px[p+1],px[p+2])];T[i]=px[p+3]>0&&M[i]<0?1:0;}
        if(fs)fs.row(j,G,T,D);else for(let i=i0;i<=i1;i++)D[i]=T[i]&&matrixDark(tn.dither,tn.strength,i,j,G[i])?1:0;
        if(j<r0)continue;
        for(let i=i0;i<=i1;i++){if(P[i]<0)continue;
          if(px[P[i]+3]*l.opacity<=255*(COVERAGE[(j%4)*4+i%4]+.5)/16)continue;
          let slot=M[i]>=0?M[i]:D[i]?(dark>=0?dark:1):0;
          if(assign.length){const x=cx(i);for(const a of assign){const s=shade(a,j,i,x,y,U[i],V[i]);if(s>=0)slot=s;}}
          out[(j-r0)*w+i]=slot;}
      }
      continue;
    }
    for(let j=Math.max(j0,r0);j<=Math.min(j1,r1-1);j++)for(let i=i0;i<=i1;i++){
      const x=cx(i),y=cy(j),[u,v]=local(l,x,y);let slot=dark>=0?dark:1;
      if(!shapeHit(l.shape,u,v))continue;
      if(255*l.opacity<=255*(COVERAGE[(j%4)*4+i%4]+.5)/16)continue;
      for(const a of assign){const s=shade(a,j,i,x,y,u,v);if(s>=0)slot=s;}out[(j-r0)*w+i]=slot;
    }
  }
  for(const a of d.assignments.filter(a=>a.selection)){
    const m=masks.get(a.selection);if(!m)throw Error('unknown selection');
    for(let j=r0;j<r1;j++)for(let i=0;i<w;i++){const x=cx(i),y=cy(j);if(sampleMask(m,d.maskGrid,x,y)){const s=shade(a,j,i,x,y,x/120,y/120);if(s>=0)out[(j-r0)*w+i]=s;}}
  }
  for(let j=r0;j<r1;j++)for(let i=0;i<w;i++){const rr=q(Math.hypot(cx(i),cy(j)));if(rr<d.annulus_mm[0]||rr>=d.annulus_mm[1])out[(j-r0)*w+i]=0;}
  return out;
}
