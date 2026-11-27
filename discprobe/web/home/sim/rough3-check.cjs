// Additional round-3 scientific/appearance regression checks. Loopback only.
const fs = require('node:fs'), path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async () => {
 const browser = await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true,
  args:['--disable-background-networking','--disable-component-update','--no-first-run']});
 try {
  const context=await browser.newContext({serviceWorkers:'block'}), blocked=[], errors=[];
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():(blocked.push(r.request().url()),r.abort()));
  const page=await context.newPage(); page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:18746/home/dev-preview.html');
  const result=await page.evaluate(async()=>{
   const {apertureRGB, RADIAL_APERTURE: p, radialMismatch, reflectionPoint, photoSurface}=await import('./sim/surface.mjs');
   const pose={tilt:30,cx:-27,cy:-164,lx:-22,ly:-159,cz:330,lz:330};
   const mirror=reflectionPoint(pose), qAtMirror=radialMismatch(...mirror,pose);
   function profile(params) {
    const mass=[0,0,0], first=[0,0,0], second=[0,0,0]; let symmetryError=0;
    for(let i=-1000;i<=1000;i++) {const q=i*.0001, a=apertureRGB(q,params), b=apertureRGB(-q,params);
     for(let c=0;c<3;c++){mass[c]+=a[c];first[c]+=a[c]*q;second[c]+=a[c]*q*q;symmetryError=Math.max(symmetryError,Math.abs(a[c]-b[c]));}}
    return {centroid:first.map((v,c)=>v/mass[c]),sigma:second.map((v,c)=>Math.sqrt(v/mass[c]-(first[c]/mass[c])**2)),symmetryError};
   }
   const zero=profile({...p,zeroGain:1,orderGain:0,sourceFwhm:0});
   const narrower=profile({...p,widthUm:p.widthUm*2,zeroGain:1,orderGain:0,sourceFwhm:0});
   const outward=profile({...p,zeroGain:0,orderGain:1,oppositeOrder:0});
   const unblazed=profile({...p,zeroGain:0,orderGain:1,oppositeOrder:1});
   // A controlled uniform RGB source isolates binary material identity from
   // optical texture brightness. Rotate only the design: world reflections stay.
   const size=160, source=new Uint8ClampedArray(size*size*4);
   for(let i=0;i<source.length;i+=4){source[i]=source[i+1]=source[i+2]=90;source[i+3]=255;}
   const width=100, design=new Uint8Array(width*width);
   for(let y=0;y<width;y++)for(let x=0;x<width/2;x++)design[y*width+x]=1;
   const material={design,width};
   const a=await photoSurface(source,size,{rotate:0,flash:0,wear:0},()=>false,()=>Promise.resolve(),material);
   const b=await photoSurface(source,size,{rotate:180,flash:0,wear:0},()=>false,()=>Promise.resolve(),material);
   const sample=(v,x,y)=>{const i=(Math.round((60-y)/120*size)*size+Math.round((x+60)/120*size))*4;return .2126*v[i]+.7152*v[i+1]+.0722*v[i+2];};
   const materialSamples=[[-38,0],[38,0]].map(([x,y])=>({x,y,rotate0:sample(a,x,y),rotate180:sample(b,x,y)}));
   return {qAtMirror,zero,narrower,outward,unblazed,materialSamples};
  });
  const failures=[];
  if(result.qAtMirror.some(v=>Math.abs(v)>1e-10))failures.push('mirror mismatch');
  if(result.zero.sigma[0]<=result.zero.sigma[2])failures.push('red must spread wider than blue');
  if(result.zero.sigma.some((s,c)=>Math.abs(s/result.narrower.sigma[c]-2)>.02))failures.push('aperture width scaling');
  if(!(result.outward.centroid[0]<result.outward.centroid[2]&&result.outward.centroid[2]<0))failures.push('red must peak farther outward');
  if(result.unblazed.symmetryError>1e-5)failures.push('unblazed symmetry');
  if(result.materialSamples[0].rotate180<result.materialSamples[0].rotate0*3||result.materialSamples[1].rotate0<result.materialSamples[1].rotate180*3)failures.push('A5 mask rotation');
  if(blocked.length||errors.length)failures.push('browser errors/external requests');
  fs.writeFileSync(path.join(__dirname,'evidence/rough3/optics-checks.json'),JSON.stringify({result,blocked,errors,failures},null,2));
  if(failures.length)throw Error(failures.join('; '));
  console.log('PASS: mirror geometry, wavelength/width scaling, spectral order, explicit blaze, rotated material selection; loopback only.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
