// DP pattern reference v1. No canvas or npm dependencies. mm; y down.

const Q=1000000, tick=x=>Math.floor(x*Q+.5), mod=(x,p)=>((x%p)+p)%p;
function validate(d){
 if(d.version!==1||!['diamond','dots','stripes'].includes(d.pattern)||!['cartesian','polar'].includes(d.coordinates))throw Error('pattern/version/coordinates');
 for(const k of ['pitch_mm','size_mm','angle_deg'])if(typeof d[k]!=='number'||!Number.isFinite(d[k]))throw Error(k);
 if(Math.abs(d.angle_deg)>360000)throw Error('angle out of range');
 if(!(d.size_mm>0&&d.size_mm<=d.pitch_mm/2&&d.pitch_mm>=1e-5&&d.pitch_mm<=50))throw Error('size/pitch out of range');
 for(const k of ['origin_mm','phase_mm'])if(!Array.isArray(d[k])||d[k].length!==2||!d[k].every(x=>typeof x==='number'&&Number.isFinite(x)&&Math.abs(x)<=120))throw Error(k);
 if(!Array.isArray(d.materials)||d.materials.length!==2||!d.materials.every(x=>Number.isInteger(x)&&x>=0&&x<=65534))throw Error('material slots');
 if(d.coordinates==='polar'&&!(Number.isFinite(d.reference_radius_mm)&&d.reference_radius_mm>0&&d.reference_radius_mm<=60))throw Error('reference radius');
 if('segments'in d&&!(Number.isInteger(d.segments)&&d.segments>=1&&d.segments<=100000))throw Error('segments');
}
function render(d,g){
 validate(d);const {width:w,height:h,cell_mm:cell}=g;
 if(!(Number.isInteger(w)&&Number.isInteger(h)&&w>0&&h>0&&w<=24000&&h<=24000&&Number.isFinite(cell)&&cell>0))throw Error('grid');
 for(const k of ['left_mm','top_mm'])if(!(Number.isFinite(g[k])&&Math.abs(g[k])<=120))throw Error('grid origin');
 if(!(Array.isArray(g.annulus_mm)&&g.annulus_mm.length===2&&g.annulus_mm.every(Number.isFinite)&&g.annulus_mm[0]>=0&&g.annulus_mm[0]<g.annulus_mm[1]&&g.annulus_mm[1]<=60))throw Error('annulus');
 const out=new Uint16Array(w*h),p=tick(d.pitch_mm),a=d.angle_deg*Math.PI/180,c=Math.cos(a),s=Math.sin(a),half=tick(d.size_mm/2),dh=tick(d.size_mm*Math.SQRT2/2);
 const seg=d.segments??Math.max(1,Math.floor(2*Math.PI*(d.reference_radius_mm??40)/d.pitch_mm+.5));
 const distance=v=>{const r=mod(v,p);return Math.min(r,p-r)},ri=tick(g.annulus_mm[0]),ro=tick(g.annulus_mm[1]);
 const xs=Array.from({length:w},(_,i)=>tick(g.left_mm+(i+.5)*cell)/Q);
 for(let j=0;j<h;j++){
  const y=tick(g.top_mm+(j+.5)*cell)/Q;
  for(let i=0;i<w;i++){
   const x=xs[i],dx=x-d.origin_mm[0],dy=y-d.origin_mm[1];let u,v;
   if(d.coordinates==='cartesian'){u=tick(dx*c+dy*s-d.phase_mm[0]);v=tick(-dx*s+dy*c-d.phase_mm[1]);}
   else{const theta=mod(Math.atan2(dy,dx)-a,2*Math.PI);u=tick(Math.hypot(dx,dy)-d.phase_mm[0]);v=tick(theta*seg*d.pitch_mm/(2*Math.PI)-d.phase_mm[1]);}
   let mask=d.pattern==='stripes'?distance(u)<half:d.pattern==='dots'?distance(u)**2+distance(v)**2<half**2:distance(u+v)<dh||distance(u-v)<dh;
   const r=tick(Math.hypot(x,y)),val=r>=ri&&r<ro?d.materials[mask?0:1]:65535;
   out[j*w+i]=val;
  }
 }
 return out;
}
export {render,validate};
