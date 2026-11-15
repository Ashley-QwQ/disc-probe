// Sample an engineering-space selection at source pixel centres. Alpha stays continuous.
export function selectionPixels(layer, bits, grid, feather=0) {
  const {width:w,height:h}=grid;
  let mask=Float32Array.from(bits);
  const radius=Math.min(Math.max(w,h),Math.round(feather/grid.cell_mm));
  if(radius>0){
    const pass=(src,horizontal)=>{const dst=new Float32Array(w*h),len=horizontal?w:h,count=horizontal?h:w,step=horizontal?1:w;
      for(let line=0;line<count;line++){const base=horizontal?line*w:line;let sum=0;
        const at=k=>src[base+Math.max(0,Math.min(len-1,k))*step];
        for(let k=-radius;k<=radius;k++)sum+=at(k);
        for(let k=0;k<len;k++){dst[base+k*step]=sum/(radius*2+1);sum+=at(k+radius+1)-at(k-radius);}}
      return dst;};mask=pass(pass(mask,true),false);
  }
  const selected=new Uint8ClampedArray(layer.px.data),remaining=new Uint8ClampedArray(layer.px.data);
  const a=layer.rot*Math.PI/180,c=Math.cos(a),s=Math.sin(a),height=layer.width*layer.h/layer.w;
  const sample=(x,y)=>x<0||y<0||x>=w||y>=h?0:mask[y*w+x];
  for(let y=0;y<layer.h;y++)for(let x=0;x<layer.w;x++){
    const u=((x+.5)/layer.w-.5)*layer.width,v=((y+.5)/layer.h-.5)*height;
    const gx=(layer.x+u*c-v*s-grid.left_mm)/grid.cell_mm-.5,gy=(layer.y+u*s+v*c-grid.top_mm)/grid.cell_mm-.5;
    const ix=Math.floor(gx),iy=Math.floor(gy),fx=gx-ix,fy=gy-iy;
    const coverage=(sample(ix,iy)*(1-fx)+sample(ix+1,iy)*fx)*(1-fy)+(sample(ix,iy+1)*(1-fx)+sample(ix+1,iy+1)*fx)*fy;
    const i=(y*layer.w+x)*4+3,alpha=layer.px.data[i];selected[i]=Math.round(alpha*coverage);remaining[i]=alpha-selected[i];
  }
  return {selected,remaining};
}
export function uniqueLayerName(layers,filename,fallback='图片',stripExtension=true) {
  const value=String(filename??''),stem=(stripExtension?value.replace(/\.[^.]+$/u,''):value).trim(),used=new Set(layers.map(l=>l.name));
  if(!stem){let n=1;while(used.has(`${fallback} ${n}`))n++;return `${fallback} ${n}`;}
  if(!used.has(stem))return stem;let n=2;while(used.has(`${stem} ${n}`))n++;return `${stem} ${n}`;
}
