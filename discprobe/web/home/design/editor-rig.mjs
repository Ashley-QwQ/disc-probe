// Pose first, colour second (walk W3, 2026-11-14). A texture's colour holds for one phone and one viewing height
// only, so the colour panel opens after both are chosen. The palettes are precomputed per phone x height by
// tools/editor_pose_swatches.py (pose-swatches.json; pose-swatches-custom.json for a distance the person measured);
// nothing here models light. The rig lives in the work's scene (scene.rig), so a saved work keeps its pose.
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export const RIG_WORDS={
  zh:{title:'颜色',
    intro:['盘上的颜色，是刻出来的细纹把闪光灯的光反射进镜头形成的。同一块地方，手机举高一点、挪开一点，看到的颜色就变了。',
      '所以先说好用哪台手机、从多高拍，色板才会显示你那样拍时看到的颜色。手机的前后左右由摆放纸定。只刻黑白图不用选。'],
    why:'为什么要先选手机和高度',figLow:'这样拍',figHigh:'高一点',figSame:'同一块地方',
    phone:'你的手机',iphoneSub:'闪光灯离 1× 镜头 47.9 mm · 实测过',custom:'其他手机',customSub:'自己量闪光灯到 1× 镜头的距离 · 未验证',
    distance:'闪光灯中心到 1× 镜头中心（mm）',distanceNote:d=>`按 ${d} mm 算。没在这款手机上验证过，颜色可能对不上。`,distanceBad:'填 10 到 60 之间的毫米数。',
    height:'拍摄高度',heightPick:'先选手机，再选高度。',
    heightNote:'1× 镜头离桌面的高度。21 cm 是摆放纸的设计高度，实拍对照过，用打印的高度尺；30–70 cm 也拍过，但色板是模型预测，还没逐块对照。',
    heightNoteCustom:'1× 镜头离桌面的高度。你的手机没验证过，每一档的颜色都只是模型预测。',
    pose:label=>`下面是用 ${label} 拍时，盘面右侧（3 点钟方向、离圆心 4 cm）的颜色。盘上别处颜色不同，点画布下面的“灯下”看整张盘。`,
    model:'颜色是模型预测，比例按 6 张实践盘的录像校过。刻录默认仍按黑白刻，上了颜色、彩色图案和特效的地方刻成深色。',
    hidden:n=>`另有 ${n} 种在这个机位下看不出颜色，收在“全部材质”里。`,none:'这个机位下预测哪种材质都看不出颜色。换低一点的高度试试。',all:'全部材质',
    locked:'先选手机和拍摄高度',loading:'正在载入色板…',failed:'色板没载入：',
    lampNote:label=>`${label} · 模型预测`,lampNone:'还没选手机和高度 · 按旧的默认机位（33 cm）'},
  en:{title:'Colour',
    intro:['The colours on a disc are the flash light that the burned fine lines throw into the lens. Hold the phone a little higher or further over and the same spot shows another colour.',
      'So first say which phone you shoot with and from how high; the palette then shows the colours you will see shooting that way. The placement sheet fixes where the phone sits. Black-and-white pictures need none of this.'],
    why:'Why the phone and height come first',figLow:'Shot like this',figHigh:'A little higher',figSame:'Same spot',
    phone:'Your phone',iphoneSub:'Flash 47.9 mm from the 1× lens · measured',custom:'Another phone',customSub:'Measure the flash to the 1× lens yourself · unverified',
    distance:'Flash centre to 1× lens centre (mm)',distanceNote:d=>`Using ${d} mm. Not checked on this phone; the colours may be off.`,distanceBad:'Enter a whole number of mm from 10 to 60.',
    height:'Shooting height',heightPick:'Choose the phone first, then the height.',
    heightNote:'Height of the 1× lens above the table. 21 cm is the placement sheet\'s design height, checked against photos; use the printed height ruler. 30–70 cm were photographed too, but their palettes are the model\'s prediction, not yet compared swatch by swatch.',
    heightNoteCustom:'Height of the 1× lens above the table. Your phone is not verified; every height is the model\'s prediction only.',
    pose:label=>`Below: the colours at the disc's right side (3 o'clock, 4 cm from the centre) shot with ${label}. Elsewhere on the disc they differ; use Under the lamp under the canvas to see the whole disc.`,
    model:'The colours are a model prediction, scaled from videos of 6 practice discs. The burn is still black and white by default; coloured, colour-patterned and effect areas burn dark.',
    hidden:n=>`${n} more show no colour at this position; they are under All materials.`,none:'At this position no material is predicted to show colour. Try a lower height.',all:'All materials',
    locked:'Choose the phone and the shooting height first',loading:'Loading the palette…',failed:'The palette did not load: ',
    lampNote:label=>`${label} · model prediction`,lampNone:'No phone and height chosen · old default position (33 cm)'}
};
export const rigWords=lang=>RIG_WORDS[lang]??RIG_WORDS.zh;

// HSV hue in degrees, as colorsys.rgb_to_hsv (what simulate_a3.swatches reports)
export function hueOf([r,g,b]){const mx=Math.max(r,g,b),mn=Math.min(r,g,b),d=mx-mn;if(!d)return 0;
  const h=mx===r?((g-b)/d)%6:mx===g?(b-r)/d+2:(r-g)/d+4;return ((h/6)%1+1)%1*360;}

// one packed set -> {id:{rgb,hue,dark}} in the palette's order
export function decodeSet(order,set){const out={};
  order.forEach((id,i)=>{const rgb=[0,1,2].map(c=>parseInt(set.rgb.substr(i*6+c*2,2),16));
    const dark=!!(parseInt(set.dark[i>>2],16)>>(3-(i&3))&1);out[id]={rgb,hue:hueOf(rgb),dark};});
  return out;}

// a whole mm in the custom grid, or null
export function customMM(value,data){const d=Math.round(Number(value));return Number.isFinite(d)&&data?.custom?.flash_mm?.includes(d)?d:null;}
// the phone's flash-to-lens distance in mm, or null
export function flashMM(rig,data){if(!rig?.phone)return null;if(rig.phone==='custom')return customMM(rig.flash_mm,data);
  return data?.phones?.find(p=>p.id===rig.phone)?.flash_mm??null;}
// the key of the chosen set, or null while the pose is not complete
export function setKey(rig,data){if(!data||!rig?.phone||!data.heights?.some(h=>h.id===rig.height))return null;
  if(rig.phone==='custom'){const d=customMM(rig.flash_mm,data);return d==null?null:`${d}@${rig.height}`;}
  return data.phones?.some(p=>p.id===rig.phone)?`${rig.phone}@${rig.height}`:null;}
export const rigReady=(rig,data)=>setKey(rig,data)!=null;
// which file holds the chosen set
export const needsCustom=rig=>rig?.phone==='custom';

export function rigLabel(rig,data,lang='zh'){const w=rigWords(lang),h=data?.heights?.find(h=>h.id===rig?.height);
  const phone=rig?.phone==='custom'?`${w.custom}（${flashMM(rig,data)??'?'} mm）`:data?.phones?.find(p=>p.id===rig?.phone)?.name??'';
  return h?`${phone} · ${h.ruler_cm} cm`:phone;}

// The work's scene for this rig: design.js's frame (y down on screen; the phone's offset toward 12 o'clock is -y),
// the flash riding on the phone at its own offset, and the practice discs' scale for the lamp view.
export function rigScene(scene,rig,data,set){const base={...(scene??{}),rig:{...rig}};if(!set)return base;
  const [,lensY,z]=set.camera,flash=set.flash;
  return {...base,preset:'rig',cam:[set.camera[0],-lensY,z],follows:true,flashOffset:[flash[0]-set.camera[0],flash[1]-lensY],deltaScale:data.model.delta_scale};}

// a material that changes most between the design height and 40 cm, for the figure (both colours from the data)
export function example(data,sets){const a=sets?.['iphone17pro@21'],b=sets?.['iphone17pro@40'];if(!a||!b)return null;let best=null;
  for(const id of data.order){const p=a[id],q=b[id];if(p.dark||q.dark)continue;const d=Math.abs(((p.hue-q.hue)%360+540)%360-180);
    const score=d*Math.min(Math.max(...p.rgb),Math.max(...q.rgb));if(!best||score>best.score)best={score,low:p.rgb,high:q.rgb};}
  return best;}

// side view: the same spot seen from the design height and from higher up
export function figure(lang='zh',ex=null){const w=rigWords(lang),lo=ex?`rgb(${ex.low})`:'var(--ink-3)',hi=ex?`rgb(${ex.high})`:'var(--ink-3)';
  const phone=(y,dash)=>`<rect x="118" y="${y}" width="84" height="8" rx="2" ${dash?'fill="none" stroke-dasharray="3 3"':'fill="var(--paper-2)"'} stroke="var(--ink-2)"/><circle cx="136" cy="${y+8}" r="2.6" fill="var(--ink)"/><circle cx="160" cy="${y+8}" r="2.6" fill="var(--paper)" stroke="var(--ink-2)"/>`;
  const rays=(y,dash)=>`<path d="M160 ${y+10} L72 111 L136 ${y+10}" fill="none" stroke="var(--ink-2)" stroke-width="1" ${dash?'stroke-dasharray="3 3"':''}/>`;
  return `<svg class="ed-rig-figure" viewBox="0 0 280 140" role="img" aria-label="${esc(w.intro[0])}">`+
    `<line x1="6" y1="119" x2="274" y2="119" stroke="var(--rule-strong)"/><rect x="22" y="112" width="160" height="5" rx="1" fill="var(--paper-2)" stroke="var(--ink-3)"/>`+
    rays(14,true)+rays(62,false)+phone(14,true)+phone(62,false)+
    `<rect x="60" y="108" width="12" height="4" fill="${lo}"/><rect x="72" y="108" width="12" height="4" fill="${hi}"/>`+
    `<text x="72" y="134" text-anchor="middle">${esc(w.figSame)}</text>`+
    `<circle cx="218" cy="70" r="6" fill="${lo}"/><text x="230" y="74">${esc(w.figLow)}</text>`+
    `<circle cx="218" cy="22" r="6" fill="${hi}"/><text x="230" y="26">${esc(w.figHigh)}</text></svg>`;}

// the steps before the colours (always shown; once the pose is complete the explanation folds away)
export function rigSteps(rig,data,lang='zh',{ex=null,state='ready',error=''}={}){const w=rigWords(lang),ready=rigReady(rig,data),custom=rig?.phone==='custom';
  const why=`${figure(lang,ex)}${w.intro.map(p=>`<p class="ed-model-note">${esc(p)}</p>`).join('')}`;
  let html=`<h3>${esc(w.title)}</h3>`+(ready?`<details class="ed-rig-why"><summary>${esc(w.why)}</summary>${why}</details>`:why);
  if(state==='loading'||!data)return html+`<p class="note quiet">${esc(state==='error'?w.failed+error:w.loading)}</p>`;
  const opt=(id,name,sub)=>`<button type="button" class="ed-rig-opt" data-ed-rig="phone" data-value="${id}" aria-checked="${rig?.phone===id}" role="radio"><b>${esc(name)}</b><span>${esc(sub)}</span></button>`;
  html+=`<div class="ed-rig-step" role="radiogroup" aria-label="${esc(w.phone)}"><h4>${esc(w.phone)}</h4>`+data.phones.map(p=>opt(p.id,p.name,w.iphoneSub)).join('')+opt('custom',w.custom,w.customSub);
  if(custom){const d=customMM(rig.flash_mm,data),typed=rig.flash_mm!=null&&rig.flash_mm!=='';
    html+=`<label class="ed-rig-mm">${esc(w.distance)}<input type="number" inputmode="decimal" min="10" max="60" step="0.1" data-ed-rig-mm value="${esc(rig.flash_mm??'')}"></label>`+
      (typed?`<p class="note ${d==null?'ed-rig-bad':'quiet'}">${esc(d==null?w.distanceBad:w.distanceNote(d))}</p>`:'');}
  html+='</div>';
  const phoneOK=flashMM(rig,data)!=null;
  html+=`<div class="ed-rig-step"><h4>${esc(w.height)}</h4><div class="seg ed-rig-heights" role="radiogroup" aria-label="${esc(w.height)}">`+
    data.heights.map(h=>`<button type="button" role="radio" data-ed-rig="height" data-value="${h.id}" aria-checked="${rig?.height===h.id}" aria-pressed="${rig?.height===h.id}" ${phoneOK?'':'disabled'}>${h.ruler_cm} cm</button>`).join('')+
    `</div><p class="note quiet">${esc(phoneOK?(custom?w.heightNoteCustom:w.heightNote):w.heightPick)}</p></div>`;
  return html;}
