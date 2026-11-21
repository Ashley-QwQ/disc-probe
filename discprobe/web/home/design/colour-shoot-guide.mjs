const DOCS = 'https://github.com/Ashley-QwQ/disc-probe/blob/main/docs/';
const WORDS = {
  zh: {
    title:'怎么看、怎么拍', figure:'对准纸俯视示意', twelve:'12 点箭头', lens:'1× 镜头', flash:'闪光灯',
    light:'关掉室内灯，只用手机闪光灯。观看时可把手机手电放在眼睛旁边。',
    place:h=>`数据面朝上放进对准纸的圆里，12 点箭头对齐，让 1× 镜头在十字上方、闪光灯在标点上方，${h ? `镜头离桌面 ${h} cm` : '高度按设计时的设置'}。`,
    tilt:'拍照时保持手机和盘面平行。手持观察时，慢慢倾斜盘，避开倒影来找颜色。',
    pose:'颜色只在设计机位附近接近预览，挪动手机或转盘时颜色会变。',
    mono:'黑白图用暗处的小光源观察即可。',
    colourDoc:'彩色刻图说明和对准纸', gratingDoc:'光栅卡和观察角度',
  },
  en: {
    title:'Viewing and photographing colour', figure:'Placement sheet viewed from above', twelve:'12 o’clock arrow', lens:'1× main lens', flash:'Flash',
    light:'Switch off the room lights and use only the phone flash. For viewing by eye, hold the phone torch beside your eyes.',
    place:h=>`Set the disc data-side up in the placement sheet circle, line up its 12 o’clock arrow, and place the 1× lens above the cross and the flash above the dot. ${h ? `Keep the lens ${h} cm above the table.` : 'Use the shooting height chosen in the design.'}`,
    tilt:'Keep the phone parallel to the disc for the photo. To view it by hand, slowly tilt the disc away from reflections until the colours show.',
    pose:'Colours match the preview most closely near the design position. They shift if you move the phone or turn the disc.',
    mono:'For black-and-white pictures, a small light in a dark room is enough.',
    colourDoc:'Colour guide and placement sheet', gratingDoc:'Grating card and viewing angles',
  },
};

// The geometry of tools/make_rulers.py's photo placement sheet, without its printable grid.
// For a custom phone, move the flash dot along the same 12 o'clock line.
function placementFigure(w, setup) {
  const lens = Number.isFinite(setup.lensOffset) ? setup.lensOffset : 28.45;
  const flash = Number.isFinite(setup.flashOffset) ? setup.flashOffset : 76.39;
  return `<svg viewBox="-78 -103 252 169" role="img" aria-label="${w.figure}">
    <g fill="none" stroke="currentColor" stroke-width="1.4">
      <circle r="60"/><circle r="7.5"/>
      <path d="M0 -82v15m-4 -4 4 4 4 -4M0 -55v13m-4 -9 4 -4 4 4"/>
      <path d="M-70 ${-lens}H62 M0 ${-lens-7}v14" stroke-dasharray="3 3"/>
      <path d="M-6 ${-lens}H6 M0 ${-lens-6}v12 M2 ${-flash}H12L38 -90H72 M62 ${-lens}L69 -23H72"/>
      <circle cy="${-flash}" r="2.6" fill="currentColor"/>
      <path d="M7 -53H72"/>
    </g>
    <g fill="currentColor">
      <text x="76" y="-86">${w.flash}</text>
      <text x="76" y="-49">${w.twelve}</text>
      <text x="76" y="-19">${w.lens}</text>
    </g>
  </svg>`;
}

export function colourShootGuide(setup, lang, open = false) {
  if (!setup) return '';
  const w = WORDS[lang] ?? WORDS.zh;
  const height = Number.isFinite(setup.height) ? setup.height.toLocaleString(lang) : null;
  const suffix = lang === 'en' ? '.md' : '.zh.md';
  return `<details class="colour-shoot-guide" ${open ? 'open' : ''}>
    <summary>${w.title}</summary>
    ${placementFigure(w, setup)}
    <ol>${[w.light,w.place(height),w.tilt,w.pose,w.mono].map(text=>`<li>${text}</li>`).join('')}</ol>
    <p><a href="${DOCS}colour${suffix}" target="_blank" rel="noopener">${w.colourDoc}</a>
    <a href="${DOCS}grating-card${suffix}" target="_blank" rel="noopener">${w.gratingDoc}</a></p>
  </details>`;
}

export function mountColourShootStyles() {
  const href = new URL('./colour-shoot-guide.css', import.meta.url).href;
  if (document.querySelector('link[data-colour-shoot-style]')) return;
  const css = document.createElement('link');
  css.rel = 'stylesheet';
  css.href = href;
  css.dataset.colourShootStyle = '';
  document.head.append(css);
}
