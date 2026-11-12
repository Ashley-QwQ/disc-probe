// Display identities and pose conversion only. All optical colours are computed
// by discprobe.simulate on the server (also bundled in swatches.json for startup).
export function colourWord(light,lang='en'){
  const words=lang==='zh'?['偏红','偏橙','偏黄','偏绿','偏青','偏蓝','偏紫']:['reddish','orange','yellowish','greenish','cyan','bluish','violet'];
  if(light.dark)return lang==='zh'?'不显色':'dark';
  const h=light.hue;return words[h<20||h>=340?0:h<45?1:h<75?2:h<165?3:h<200?4:h<265?5:6];
}
export function materialPose(scene,lookY){
  const base=scene?.cam??[0,-70,330],cam=[base[0],Number.isFinite(lookY)?-lookY:base[1],base[2]],lamp=scene?.follows?[cam[0]-43.66,cam[1]-19.79,cam[2]]:scene?.lamp??[-43.66,-89.79,330];
  return {camera:[cam[0],-cam[1],cam[2]],flash:[lamp[0],-lamp[1],lamp[2]]};
}
export function identityRGB(material,x,y,dark=false){
  if(material.id==='background')return dark?[58,64,62]:[218,214,205];
  let hash=2166136261;for(const c of material.id??material.spec??'material')hash=Math.imul(hash^c.charCodeAt(0),16777619)>>>0;
  const spacing=5+hash%4,diagonal=(hash&8)?x+y:x-y,mark=((diagonal%spacing)+spacing)%spacing===0;
  const value=dark?(mark?184:105+(hash%4)*9):(mark?60:119+(hash%4)*12);
  return [value,value,value];
}
