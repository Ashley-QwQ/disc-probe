// Pose first, colour second (walk W3, 2026-11-14). A texture's colour holds for one phone and one viewing height
// only, so the colour panel opens after both are chosen. The palettes are precomputed per phone x height by
// tools/editor_pose_swatches.py (pose-swatches.json; pose-swatches-custom.json for a distance the person measured);
// nothing here models light. The rig lives in the work's scene (scene.rig), so a saved work keeps its pose.
import { DESIGN_RULER_CM } from './focal-geometry.mjs';
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export const RIG_WORDS={
  zh:{title:'颜色',
    intro:['盘上的颜色，是刻出来的细纹把闪光灯的光反射进镜头形成的。同一块地方，手机举高一点、挪开一点，看到的颜色就变了。',
      '所以先说好用哪台手机、从多高拍，色板才会显示你那样拍时看到的颜色。手机的前后左右由摆放纸定。只刻黑白图不用选。'],
    why:'为什么要先选手机和高度',figLow:'这样拍',figHigh:'高一点',figSame:'同一块地方',
    phone:'你的手机',iphoneSub:'闪光灯离 1× 镜头 47.9 mm · 实测过',custom:'其他手机',customSub:'自己量闪光灯到 1× 镜头的距离 · 未验证',
    distance:'闪光灯中心到 1× 镜头中心（mm）',distanceNote:d=>`按 ${d} mm 算。没在这款手机上验证过，颜色可能对不上。`,distanceBad:'填 10 到 60 之间的毫米数。',
    height:'拍摄高度',heightPick:'先选手机，再选高度。',
    heightNote:'1× 镜头离桌面的高度。'+DESIGN_RULER_CM+' cm 是摆放纸的新设计高度，焦距待两高度复测，用新版高度尺；30–70 cm 也拍过，但色板是模型预测，还没逐块对照。',
    heightNoteCustom:'1× 镜头离桌面的高度。你的手机没验证过，每一档的颜色都只是模型预测。',
    pose:label=>`下面是用 ${label} 拍时，盘面右侧（3 点钟方向、离圆心 4 cm）的颜色。盘上别处颜色不同，点画布下面的“灯下”看整张盘。`,
    model:'颜色是模型预测，机位已按实测焦距更新，待复拍对照。如果用了彩色图片填充，默认输出彩色纹理。只用材质、图案或特效时，默认按黑白输出，也可以在预览选择实验效果。',
    hidden:n=>`另有 ${n} 种在这个机位下看不出颜色，收在“全部材质”里。`,none:'这个机位下预测哪种材质都看不出颜色。换低一点的高度试试。',all:'全部材质',
    locked:'先选手机和拍摄高度',loading:'正在载入色板…',failed:'色板没载入：',
    lampNote:label=>`${label} · 模型预测`,lampNone:'还没选手机和高度 · 按旧的默认机位（33 cm）'},
  en:{title:'Colour',
    intro:['The colours on a disc are the flash light that the burned fine lines throw into the lens. Hold the phone a little higher or further over and the same spot shows another colour.',
      'So first say which phone you shoot with and from how high; the palette then shows the colours you will see shooting that way. The placement sheet fixes where the phone sits. Black-and-white pictures need none of this.'],
    why:'Why the phone and height come first',figLow:'Lower',figHigh:'Higher',figSame:'Same spot',
    phone:'Your phone',iphoneSub:'Flash 47.9 mm from the 1× lens · measured',custom:'Another phone',customSub:'Measure the flash to the 1× lens yourself · unverified',
    distance:'Flash centre to 1× lens centre (mm)',distanceNote:d=>`Using ${d} mm. Not checked on this phone; the colours may be off.`,distanceBad:'Enter a whole number of mm from 10 to 60.',
    height:'Shooting height',heightPick:'Choose the phone first, then the height.',
    heightNote:'Height of the 1× lens above the table. '+DESIGN_RULER_CM+' cm is the updated placement height; focal length awaits two-height measurement; use the new ruler. 30–70 cm were photographed too, but their palettes are the model\'s prediction, not yet compared swatch by swatch.',
    heightNoteCustom:'Height of the 1× lens above the table. Your phone is not verified; every height is the model\'s prediction only.',
    pose:label=>`Below: the colours at the disc's right side (3 o'clock, 4 cm from the centre) shot with ${label}. Elsewhere on the disc they differ; use Under the lamp under the canvas to see the whole disc.`,
    model:'These colours are model predictions using updated camera geometry, with a new photo comparison pending. A colour picture fill exports colour textures by default. Material, pattern and effect fills alone export in black and white by default. Preview also offers an experimental export mode.',
    hidden:n=>`${n} more show no colour at this position; they are under All materials.`,none:'At this position no material is predicted to show colour. Try a lower height.',all:'All materials',
    locked:'Choose the phone and the shooting height first',loading:'Loading the palette…',failed:'The palette did not load: ',
    lampNote:label=>`${label} · model prediction`,lampNone:'No phone and height chosen · old default position (33 cm)'}
};
export const rigWords=lang=>RIG_WORDS[lang]??RIG_WORDS.zh;

const DOCS = 'https://github.com/Ashley-QwQ/disc-probe/blob/main/docs/';
const COLOUR_PICTURE_UI = {
  zh: {
    introTitle:'彩色刻图怎么拍', start:'开始设置',
    intro:[
      '盘上的细纹把闪光灯的光分成不同颜色。',
      '挪动手机或转动盘就会变色，只有在选定的拍摄位置附近，颜色才接近预览。',
      '拍摄时关掉室内灯，打开手机闪光灯。',
      '把盘的数据面朝上，按对准纸摆放盘和手机，把箭头对到 12 点。',
    ],
    colourDoc:'彩色刻图与对准纸', tutorial:'光盘怎么变成图',
    phone:'1. 你的手机', distance:'1× 镜头到闪光灯的距离（mm）', useDistance:'确认距离',
    measure:'用尺量两个中心之间的直线距离，填 10–60 mm。', lookup:'按手机型号查距离',
    used:mm=>`按 ${mm} mm 生成预览。`,
    height:'2. 拍摄高度', heightNote:'从桌面量到 1× 镜头。用对准纸上的参考位置可先试 22.3 cm。',
    heightPick:'先确认镜头到闪光灯的距离。',
    chosenHeight:cm=>`当前高度为 ${cm} cm。`,
    preview:'3. 生成预览', generate:'生成颜色预览',
    needsPose:'先确认手机距离，再选拍摄高度。',
    poseLoading:'正在载入拍摄位置…', poseFailed:'拍摄位置没载入。请再次确认距离。',
    needsPicture:'导入一张图片，或用画布上的示例。', pickPicture:'在图层列表中选中要上色的图片。',
    lockedPicture:'请先解锁选中的图片图层。',
    validation:'目前只在 RITEKF1 DVD-R 和 GH70N 的组合上实拍验证过。换盘颜色可能偏。',
    prediction:'这是在你选的机位下的模型预测。实盘会更暗、颜色更淡。',
    advanced:'高级 · 手动配色',
  },
  en: {
    introTitle:'How to photograph a colour disc', start:'Set up my phone',
    intro:[
      'Fine grooves on the disc split the flash light into different colours.',
      'Colours shift when you move the phone or turn the disc, so stay near the shooting position you chose.',
      'Turn off the room lights and turn on the phone flash.',
      'Use the placement sheet to position the phone and the disc data-side up, with the arrow at 12 o’clock.',
    ],
    colourDoc:'Colour guide and placement sheet', tutorial:'How a disc becomes a picture',
    phone:'1. Your phone', distance:'1× lens to flash distance (mm)', useDistance:'Confirm distance',
    measure:'Use a ruler to measure straight from centre to centre. Enter 10–60 mm.', lookup:'Look up a phone model',
    used:mm=>`The preview uses ${mm} mm.`,
    height:'2. Shooting height', heightNote:'Measure from the table to the 1× lens. Start with 22.3 cm if using the reference on the placement sheet.',
    heightPick:'First confirm the lens-to-flash distance.',
    chosenHeight:cm=>`The current height is ${cm} cm.`,
    preview:'3. Generate a preview', generate:'Generate colour preview',
    needsPose:'Confirm the phone distance, then choose a shooting height.',
    poseLoading:'Loading this shooting position…', poseFailed:'Could not load this shooting position. Confirm the distance again.',
    needsPicture:'Import a picture or use the sample on the canvas.', pickPicture:'Select the picture to colour in the layer list.',
    lockedPicture:'Unlock the selected picture layer first.',
    validation:'Physical colour has been verified only on RITEKF1 DVD-R with a GH70N. Other discs may show different colours.',
    prediction:'This is a model prediction at your chosen shooting position. The disc will look darker and less saturated.',
    advanced:'Advanced · Manual colour',
  },
};
export const colourPictureWords=lang=>COLOUR_PICTURE_UI[lang]??COLOUR_PICTURE_UI.zh;
const modelDistance=mm=>Number.isFinite(mm)?Number(mm.toFixed(1)):null;
export const shownDistance=(rig,data)=>rig?.phone==='custom'?rig.flash_mm??null:modelDistance(flashMM(rig,data));

export function colourIntro(lang, ex, open) {
  const w=colourPictureWords(lang), suffix=lang==='en'?'.md':'.zh.md';
  return `<details class="ed-colour-intro" ${open?'open':''}>
    <summary>${w.introTitle}</summary>
    ${figure(lang,ex)}
    ${w.intro.map(p=>`<p class="ed-model-note">${p}</p>`).join('')}
    <p class="ed-colour-links"><a href="${DOCS}colour${suffix}" target="_blank" rel="noopener">${w.colourDoc}</a>
      <a href="${DOCS}how-disc-images-work${suffix}" target="_blank" rel="noopener">${w.tutorial}</a></p>
    <button class="sbtn" type="button" data-ed-dismiss-colour-intro>${w.start}</button>
  </details>`;
}

export function colourRigSteps(rig,data,lang,{distanceDraft,state,error}){
  const w=colourPictureWords(lang), status=rigWords(lang);
  if(!data)return `<p class="note quiet" role="status">${esc(state==='error'?status.failed+error:status.loading)}</p>`;
  const mm=flashMM(rig,data);
  const distance=distanceDraft??shownDistance(rig,data)??'';
  const savedHeight=mm!=null&&Number.isFinite(rig.height_cm)&&!data.heights.some(h=>h.id===rig.height);
  return `<section class="ed-rig-step">
    <h3>${w.phone}</h3>
    <form class="ed-rig-distance">
      <label for="ed-flash-distance">${w.distance}</label>
      <p id="ed-distance-help" class="note quiet">${w.measure}</p>
      <div><input id="ed-flash-distance" type="number" inputmode="decimal" min="10" max="60" step="any" required
        data-ed-distance aria-describedby="ed-distance-help" value="${esc(distance)}">
        <button class="sbtn" type="submit">${w.useDistance}</button></div>
    </form>
    <details class="ed-help">
      <summary>${w.lookup}</summary>
      ${data.phones.map(p=>`<button class="sbtn" type="button" data-ed-rig="phone" data-value="${esc(p.id)}">${esc(p.name)} · ${modelDistance(p.flash_mm)} mm</button>`).join('')}
    </details>
    ${mm==null?'':`<p class="note quiet" role="status">${w.used(modelDistance(mm))}</p>`}
  </section>
  <section class="ed-rig-step">
    <h3>${w.height}</h3>
    <p class="note quiet">${mm==null?w.heightPick:w.heightNote}</p>
    ${savedHeight?`<p class="note quiet">${w.chosenHeight(rig.height_cm)}</p>`:''}
    ${heightButtons(rig,data,status.height,mm!=null)}
  </section>`;
}

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
export const rigReady=(rig,data)=>setKey(rig,data)!=null || (flashMM(rig,data)!=null && Number.isFinite(rig?.height_cm) && rig.height_cm*10>data.rig.disc_and_sheet_mm);
// which file holds the chosen set
export const needsCustom=rig=>rig?.phone==='custom';

function heightButtons(rig,data,label,enabled){
  return `<div class="seg ed-rig-heights" role="radiogroup" aria-label="${esc(label)}">
    ${data.heights.map(h=>`<button type="button" role="radio" data-ed-rig="height" data-value="${h.id}" aria-checked="${rig?.height===h.id}" aria-pressed="${rig?.height===h.id}" ${enabled?'':'disabled'}>${h.ruler_cm} cm</button>`).join('')}
  </div>`;
}

export function rigLabel(rig,data,lang='zh'){const w=rigWords(lang),h=data?.heights?.find(h=>h.id===rig?.height);
  const phone=rig?.phone==='custom'?`${w.custom}（${flashMM(rig,data)??'?'} mm）`:data?.phones?.find(p=>p.id===rig?.phone)?.name??'';
  const cm=h?.ruler_cm??rig?.height_cm;
  return Number.isFinite(cm)?`${phone} · ${cm} cm`:phone;}

// The work's scene for this rig: design.js's frame (y down on screen; the phone's offset toward 12 o'clock is -y),
// the flash riding on the phone at its own offset. Standard rigs follow the current calibration;
// arbitrary saved poses without a rig still read their explicit legacy scale via materialPose.
export function rigScene(scene,rig,data,set){const base={...(scene??{}),rig:{...rig}};if(!set)return base;delete base.deltaScale;
  const [,lensY,z]=set.camera,flash=set.flash;
  return {...base,preset:'rig',cam:[set.camera[0],-lensY,z],follows:true,flashOffset:[flash[0]-set.camera[0],flash[1]-lensY]};}

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
export function rigSteps(rig,data,lang='zh',{ex=null,state='ready',error='',expanded=false}={}){const w=rigWords(lang),ready=rigReady(rig,data),custom=rig?.phone==='custom';
  const why=`${figure(lang,ex)}${w.intro.map(p=>`<p class="ed-model-note">${esc(p)}</p>`).join('')}`;
  let html=`<h3>${esc(w.title)}</h3>`+(ready?`<details class="ed-rig-why"><summary>${esc(w.why)}</summary>${why}</details>`:why);
  if(ready){html=`<div class="ed-rig-summary"><span>${esc(rigLabel(rig,data,lang))}</span><button class="sbtn" type="button" data-ed-action="rig-change" aria-expanded="${expanded}" aria-controls="ed-rig-choices">${lang==='en'?'Change':'更改'}</button></div><div id="ed-rig-choices" ${expanded?'':'hidden'}>`+html;}
  if(state==='loading'||!data)return html+`<p class="note quiet">${esc(state==='error'?w.failed+error:w.loading)}</p>`;
  const opt=(id,name,sub)=>`<button type="button" class="ed-rig-opt" data-ed-rig="phone" data-value="${id}" aria-checked="${rig?.phone===id}" role="radio"><b>${esc(name)}</b><span>${esc(sub)}</span></button>`;
  html+=`<div class="ed-rig-step" role="radiogroup" aria-label="${esc(w.phone)}"><h4>${esc(w.phone)}</h4>`+data.phones.map(p=>opt(p.id,p.name,w.iphoneSub)).join('')+opt('custom',w.custom,w.customSub);
  if(custom){const d=customMM(rig.flash_mm,data),typed=rig.flash_mm!=null&&rig.flash_mm!=='';
    html+=`<label class="ed-rig-mm">${esc(w.distance)}<input type="number" inputmode="decimal" min="10" max="60" step="0.1" data-ed-rig-mm value="${esc(rig.flash_mm??'')}"></label>`+
      (typed?`<p class="note ${d==null?'ed-rig-bad':'quiet'}">${esc(d==null?w.distanceBad:w.distanceNote(d))}</p>`:'');}
  html+='</div>';
  const phoneOK=flashMM(rig,data)!=null;
  html+=`<div class="ed-rig-step"><h4>${esc(w.height)}</h4>${heightButtons(rig,data,w.height,phoneOK)}
    <p class="note quiet">${esc(phoneOK?(custom?w.heightNoteCustom:w.heightNote):w.heightPick)}</p></div>`;
  return html+(ready?'</div>':'');}
