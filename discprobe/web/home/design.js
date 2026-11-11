// The design page: put pictures on the disc and set the tone. A mode of the home page, like
// calibrate.js. Brief: docs/goals/gui-pages/design.md.
//
// Each disc keeps its project while the page lives; "Save project" writes it to a .discdesign file
// (pictures embedded) and closing the page with unsaved work asks first. `makeBurnFile` draws the
// whole disc and has the webui back end run `image --design-npy` on it.
// Tone, dither and export bit packing run in a module worker.
import { processRGBA, renderOutput, autoLevels } from "./design/processing.mjs";

import { processingWorker } from "./design/worker-client.mjs";

let api, $;
const root = document.documentElement;
const isOn = () => root.dataset.mode === "design";

// ---------------------------------------------------------------- words
const STR = {
  zh: {
    untitled: "未命名工程", next: "下一步：预览",
    burnNoDrive: "没找到光驱。接好光驱后再回到这一页。", burnNoDisc: (why) => `读不了光驱里的盘：${why || "可能没放盘"}。放一张空白盘再回到这一页。`,
    burnNotBlank: "光驱里这张不是空白盘。换一张同一批的空白盘，再回到这一页。", burnTooBig: "刻录文件比这张盘放得下的大。",
    burnNotBlankSwap: (what) => `光驱里这张${what ? ` ${what} ` : ""}已经刻过了。按光驱上的弹出键把它取出来。`,
    burnPutBlank: (mid) => `放一张空白的 ${mid || "同一批"} 盘，把托盘推回去。推回后会自动检查。`,
    burnOtherBatch: (got, want) => `这张是 ${got}，几何是在 ${want} 上测的。取出它，换一张 ${want} 空白盘。`,
    burnChecking: "正在检查这张盘（只读）…", burnTrayOpen: "托盘开着。放一张空白盘，再推回去。",
    burnFailed: "刻录没有完成。这张盘可能已经写了一部分，不要再用。详细原因在任务日志里。",
    open: "打开工程", save: "保存工程", saveAs: "另存为", saved: (n) => `已保存：${n}`, opened: (n) => `已打开：${n}`,
    notProject: (n) => `${n} 不是 disc-probe 的工程文件。`, newer: (n) => `${n} 是新版本存的，这一版读不了。`,
    changeDiscs: "换一批盘（打开盘库）", noDiscYet: "还没选盘", otherMedia: (a, b) => `这份工程是给 ${a} 做的，现在打开在 ${b} 上；可刻范围按 ${b} 算。`,
    unsaved: "工程还没保存，关掉页面会丢失。",
    exp: {
      drawing: "正在画整张盘的设计图…", sending: "正在交给后端…", making: "正在生成刻录文件…",
      noBackend: "生成刻录文件要由 disc-probe 打开这个页面：在命令行运行 python -m discprobe webui，再用它给的网址。",
      noGeo: "这种盘还没有测好的盘面几何，先校准。",
      failed: "生成失败。", empty: "盘上还没有图。", four: "4 级灰阶还不能导出：先用 2 级。",
    },
    layers: "图层", undo: "撤销（Ctrl+Z）", redo: "重做（Ctrl+Shift+Z）", import: "导入图片", noLayers: "还没有图层。",
    show: "显示", hide: "隐藏", lock: "锁定", unlock: "解锁", remove: "删除",
    files: "随盘文件", pickFolder: "选择文件夹", inner: "内圈", outer: "外圈", clear: "清除",
    filesN: (n, size) => `${n} 个文件 · ${size}`, filesRing: (a, b) => `占半径 ${a}–${b} mm，这一圈放文件，不刻图。`,
    filesNone: "不带文件时，整个可刻范围都给图。", cdFiles: "CD：不带文件就刻音轨，带文件就刻数据盘。",
    tone: "影调", dither: "抖动强度", bright: "亮度", levels: "灰阶档位", lv: (n) => n === 4 ? '4 级（仅预览）' : `${n} 级`, lv4: "4 级仅供 CD 预览，导出请选 2 级",
    lin: "sRGB 线性化", inv: "反转 3T/6T 映射",
    more: "更多", auto: "自动色阶", autoOff: "取消自动色阶", autoOn: (b, w) => `黑点 ${b} · 白点 ${w}`,
    contrast: "对比度", hi: "高光", sh: "阴影", mode: "抖动方式",
    modes: { "floyd-steinberg": "误差扩散", "blue-noise": "蓝噪声", ordered: "有序", clustered: "网点", threshold: "不抖动" },
    reset: "恢复默认",
    tools: { move: "选择（V）", wand: "选区（W）", pan: "平移（H，或按住空格）" },
    proj: "投影", orig: "原图", viewAria: "画布显示", zoomAria: "在适应盘面和 100% 之间切换",
    empty: "把图片拖到这里，或者按导入图片", sample: "用示例图试试", drop: "松手，放到盘上",
    outside: "有一部分在可刻范围外，压暗的地方会被裁掉。",
    tooBig: (n) => `${n} 太大了：单张最多 3600 万像素、24 MiB。先缩小再导入。`, badType: (n) => `${n} 不是能读的图片（PNG、JPEG、WebP、BMP）。`,
    tooMany: "最多 16 个图层。",
    fb: { x: "X", y: "Y", w: "宽", h: "高", rot: "旋转", op: "不透明" },
    sel: { tol: "容差", feather: "柔化", cut: "删掉选区", keep: "只留选区", cancel: "取消", hint: "Shift 加选 · Alt 减选" },
    pro: "PRO-Experimental", proAria: "打开实验功能",
    proNote: "实验功能：只在一台光驱（GH70N）、一种盘（RITEKF1 DVD-R）、一部手机（iPhone 17 Pro）上实刻过。",
    colour: "颜色", colourEv: "实刻：红、蓝、紫",
    colourNote: "红色在设计位置接近红，手机差约 1 cm 会变橙或变绿；蓝色暗，偏蓝紫；玫瑰盘拍出过整片紫，还不统一。",
    chartNote: "挑纹理要先刻一张纹路表、拍一组照片实测。现在没有纹路表，预测是按光栅方程粗算的，只看色相。",
    preset: "机位", presets: { design: "我们的设计机位", flash: "手机闪光灯，正上方", lamp: "台灯 + 手机" },
    phone: "手机", lamp: "灯", sceneHint: "拖动挪位置；按住 Shift 拖动改高度。",
    target: "选中图层的颜色", pickLayer: "先在画布上选一个图层。",
    colours: { none: "不上色", red: "红", green: "绿", blue: "蓝", purple: "紫（红蓝交织）" },
    look: "从这个机位看（粗略）",
    fx: "特效", fxEv: "实刻验证过",
    fxNote: "每个位置写“手机移到 y mm 时这里亮”。手机一动，亮的地方按设计跑。放在盘心左右两侧（3 点、9 点方向）最明显：那里轨道是上下走的，和手机移动的方向一致。",
    fxAdd: "加一个特效区域",
    fxKinds: {
      flow: ["流光", "手机移约 4 cm，亮带走约 16 mm（两条可反向）。实刻通过。"],
      ox: ["O/X 切换", "20 mm 时 O 亮 8–9 倍、X 亮约 3 倍。实刻通过；8 mm 的 X 没过。"],
      merge: ["两点合成环", "两点、连接、开环，顺序对。实刻通过。"],
      sync: ["整片同时亮", "玫瑰盘实拍：轻晃时整片一起换色。"],
    },
    fxY: (a, b) => `手机 y：${a} → ${b} mm`, fxY1: "从", fxY2: "到", swap: "反向",
    look2: "看的位置", phoneY: (y) => `手机 y ${y} mm`, design: "（设计位置）", play: "来回播放", stop: "停",
    precision: "雕刻精度", precEv: "实刻：LTVA1 显微镜",
    prec: { 20: "20 µm（默认）", 10: "10 µm", 5: "5 µm" },
    precNote: {
      20: "默认刻录格子。DIS 的 8192 像素约 14 µm。",
      10: "显微镜下线条和棋盘格都清楚。",
      5: "线条能分开但带颗粒，棋盘格是临界失败。",
    },
    precCost: (n) => `整盘 ${n} × ${n} 格，由后端导出。支持 20、10、5 µm；格子更小会多用内存和时间。`,
    loupe: "放大镜", loupeHint: (c, f) => `1 格 = ${c} µm · 视野 ${f} mm`,
    sampleName: "示例：山和太阳",
    fit: "适应", hundred: "100%",
  },
  en: {
    untitled: "Untitled project", next: "Next: preview",
    burnNoDrive: "No drive found. Connect the drive and come back to this page.", burnNoDisc: (why) => `Couldn't read the disc in the drive: ${why || "maybe there is none"}. Put in a blank disc and come back to this page.`,
    burnNotBlank: "The disc in the drive isn't blank. Put in a blank from the same batch and come back to this page.", burnTooBig: "The burn file is bigger than this disc can hold.",
    burnNotBlankSwap: (what) => `The disc in the drive${what ? ` (${what})` : ""} has already been written. Press the drive's eject button and take it out.`,
    burnPutBlank: (mid) => `Put in a blank ${mid || "disc from the same batch"} and push the tray in. It is checked as soon as the tray closes.`,
    burnOtherBatch: (got, want) => `This disc is ${got}; the geometry was measured on ${want}. Take it out and put in a blank ${want}.`,
    burnChecking: "Checking this disc (read-only)…", burnTrayOpen: "The tray is open. Put in a blank disc and push it in.",
    burnFailed: "The burn didn't finish. The disc may be partly written; don't use it. The job log has the details.",
    open: "Open project", save: "Save project", saveAs: "Save as", saved: (n) => `Saved: ${n}`, opened: (n) => `Opened: ${n}`,
    notProject: (n) => `${n} isn't a disc-probe project file.`, newer: (n) => `${n} was saved by a newer version; this one can't read it.`,
    changeDiscs: "Use other discs (opens the disc library)", noDiscYet: "No discs chosen yet", otherMedia: (a, b) => `This project was made for ${a} and is now open on ${b}; the burnable range is ${b}'s.`,
    unsaved: "The project isn't saved; closing the page loses it.",
    exp: {
      drawing: "Drawing the whole disc…", sending: "Handing it to the back end…", making: "Making the burn file…",
      noBackend: "Making the burn file needs disc-probe to serve this page: run python -m discprobe webui and open the address it prints.",
      noGeo: "No measured disc geometry for this disc type yet. Calibrate first.",
      failed: "Making the file failed.", empty: "There's no picture on the disc yet.", four: "4 grey levels can't be exported yet: use 2 for now.",
    },
    layers: "Layers", undo: "Undo (Ctrl+Z)", redo: "Redo (Ctrl+Shift+Z)", import: "Import picture", noLayers: "No layers yet.",
    show: "Show", hide: "Hide", lock: "Lock", unlock: "Unlock", remove: "Delete",
    files: "Files on the disc", pickFolder: "Choose folder", inner: "Inner", outer: "Outer", clear: "Clear",
    filesN: (n, size) => `${n} files · ${size}`, filesRing: (a, b) => `Radius ${a}–${b} mm holds the files; no picture there.`,
    filesNone: "Without files, the whole burnable range is the picture's.", cdFiles: "CD: without files it burns an audio track; with files, a data disc.",
    tone: "Tone", dither: "Dither strength", bright: "Brightness", levels: "Grey levels", lv: (n) => n === 4 ? '4 levels (preview only)' : `${n} levels`, lv4: "4 levels are for CD preview only; choose 2 to export",
    lin: "sRGB linearisation", inv: "Swap the 3T/6T mapping",
    more: "More", auto: "Auto levels", autoOff: "Undo auto levels", autoOn: (b, w) => `Black ${b} · white ${w}`,
    contrast: "Contrast", hi: "Highlights", sh: "Shadows", mode: "Dither method",
    modes: { "floyd-steinberg": "Error diffusion", "blue-noise": "Blue noise", ordered: "Ordered", clustered: "Halftone", threshold: "No dither" },
    reset: "Reset",
    tools: { move: "Select (V)", wand: "Selection (W)", pan: "Pan (H, or hold Space)" },
    proj: "Projection", orig: "Original", viewAria: "Canvas shows", zoomAria: "Switch between fit and 100%",
    empty: "Drop a picture here, or use Import picture", sample: "Try a sample picture", drop: "Let go to put it on the disc",
    outside: "Part of it is outside the burnable range; the dimmed part will be cut off.",
    tooBig: (n) => `${n} is too large: at most 36 megapixels and 24 MiB. Shrink it first.`, badType: (n) => `${n} isn't a picture this can read (PNG, JPEG, WebP, BMP).`,
    tooMany: "At most 16 layers.",
    fb: { x: "X", y: "Y", w: "W", h: "H", rot: "Rotate", op: "Opacity" },
    sel: { tol: "Tolerance", feather: "Feather", cut: "Delete selection", keep: "Keep selection", cancel: "Cancel", hint: "Shift adds · Alt removes" },
    pro: "PRO-Experimental", proAria: "Turn on experimental features",
    proNote: "Experimental: burned and photographed with one drive (GH70N), one disc (RITEKF1 DVD-R) and one phone (iPhone 17 Pro).",
    colour: "Colour", colourEv: "Burned: red, blue, purple",
    colourNote: "Red is close to red at the design position and turns orange or green about 1 cm away; blue is dim and leans violet; the rose disc showed a purple patch, not yet even.",
    chartNote: "Choosing textures needs a texture chart burned and photographed first. Without one, the prediction is a rough grating-equation estimate of hue only.",
    preset: "Setup", presets: { design: "Our design position", flash: "Phone flash, straight above", lamp: "Desk lamp + phone" },
    phone: "Phone", lamp: "Lamp", sceneHint: "Drag to move; hold Shift and drag to change height.",
    target: "Colour of the selected layer", pickLayer: "Select a layer on the canvas first.",
    colours: { none: "None", red: "Red", green: "Green", blue: "Blue", purple: "Purple (red + blue)" },
    look: "See it from this position (rough)",
    fx: "Effects", fxEv: "Verified on a burned disc",
    fxNote: "Each spot says “light up when the phone is at y mm”. Move the phone and the lit parts move as designed. It shows most left and right of the centre (3 and 9 o'clock), where the track runs the way the phone moves.",
    fxAdd: "Add an effect area",
    fxKinds: {
      flow: ["Flowing band", "Phone moves ~4 cm, band moves ~16 mm (two can run opposite). Passed."],
      ox: ["O/X switch", "At 20 mm: O 8–9× brighter, X ~3×. Passed; the 8 mm X did not."],
      merge: ["Spots into a ring", "Two spots, join, open into a ring, in order. Passed."],
      sync: ["Whole area at once", "Rose disc: the whole patch changes colour together when tilted."],
    },
    fxY: (a, b) => `Phone y: ${a} → ${b} mm`, fxY1: "From", fxY2: "To", swap: "Reverse",
    look2: "Seen from", phoneY: (y) => `phone y ${y} mm`, design: " (design)", play: "Play back and forth", stop: "Stop",
    precision: "Engraving grid", precEv: "Burned: LTVA1 microscope",
    prec: { 20: "20 µm (default)", 10: "10 µm", 5: "5 µm" },
    precNote: {
      20: "Default burn grid. DIS's 8192 pixels are about 14 µm.",
      10: "Lines and checkerboards both clear under the microscope.",
      5: "Lines separate but grainy; the checkerboard is a borderline fail.",
    },
    precCost: (n) => `${n} × ${n} cells for the whole disc; the back end exports it. 20, 10 and 5 µm are supported; finer grids need more memory and time.`,
    loupe: "Loupe", loupeHint: (c, f) => `1 cell = ${c} µm · ${f} mm across`,
    sampleName: "Sample: hills and sun",
    fit: "Fit", hundred: "100%",
  },
};
const T = () => STR[api.lang()] ?? STR.zh;

// ---------------------------------------------------------------- icons (one line weight)
const I = {
  undo: '<svg viewBox="0 0 24 24"><path d="M9 7L4.5 11.5 9 16"/><path d="M5 11.5h9a5 5 0 010 10h-2"/></svg>',
  redo: '<svg viewBox="0 0 24 24"><path d="M15 7l4.5 4.5L15 16"/><path d="M19 11.5h-9a5 5 0 000 10h2"/></svg>',
  eye: '<svg viewBox="0 0 24 24"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/></svg>',
  eyeOff: '<svg viewBox="0 0 24 24"><path d="M4 4l16 16"/><path d="M9.9 6A9.6 9.6 0 0112 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 01-2.6 3.4M6.5 7.6C4 9.4 2.5 12 2.5 12S6 18.5 12 18.5c1.6 0 3-.4 4.2-1"/></svg>',
  lock: '<svg viewBox="0 0 24 24"><rect x="5" y="10.5" width="14" height="10" rx="1"/><path d="M8 10.5V7.5a4 4 0 018 0v3"/></svg>',
  unlock: '<svg viewBox="0 0 24 24"><rect x="5" y="10.5" width="14" height="10" rx="1"/><path d="M8 10.5V7.5a4 4 0 017.6-1.8"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13"/></svg>',
  move: '<svg viewBox="0 0 24 24"><path d="M5 3.5l13 7.2-5.6 1.6-2.4 5.4z"/></svg>',
  wand: '<svg viewBox="0 0 24 24"><path d="M4 20L14.5 9.5"/><path d="M15.5 3.5v3M15.5 12.5v-1M19.5 7.5h-3M11.5 7.5h1M18.4 4.6l-1.6 1.6M18.4 10.4l-1.6-1.6"/></svg>',
  pan: '<svg viewBox="0 0 24 24"><path d="M8.5 12V5.8a1.5 1.5 0 013 0V11M11.5 10.5V4.5a1.5 1.5 0 013 0v6M14.5 10.5V6a1.5 1.5 0 013 0v7.5c0 4-2.5 6.5-6 6.5-2.6 0-4-1.2-5.4-3.3L4 13.4a1.4 1.4 0 012.3-1.6l2.2 2.7"/></svg>',
  image: '<svg viewBox="0 0 24 24"><rect x="3.5" y="4.5" width="17" height="15" rx="1"/><circle cx="9" cy="10" r="1.6"/><path d="M4 18l5-5 4 4 3-3 4 4"/></svg>',
  folder: '<svg viewBox="0 0 24 24"><path d="M3.5 6.5a1 1 0 011-1h4.6l2 2h8.4a1 1 0 011 1V18a1 1 0 01-1 1H4.5a1 1 0 01-1-1z"/></svg>',
  fx: '<svg viewBox="0 0 24 24"><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/><circle cx="12" cy="12" r="2.5"/></svg>',
  loupe: '<svg viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5M8 10.5h5M10.5 8v5"/></svg>',
  swap: '<svg viewBox="0 0 24 24"><path d="M7 4L3.5 7.5 7 11M3.5 7.5h14M17 13l3.5 3.5L17 20M20.5 16.5h-14"/></svg>',
  save: '<svg viewBox="0 0 24 24"><path d="M5 4.5h11l3 3V19a.5.5 0 01-.5.5h-13A.5.5 0 015 19z"/><path d="M8 4.5v4.5h7V4.5M8 19.5v-6h8v6"/></svg>',
  open: '<svg viewBox="0 0 24 24"><path d="M3.5 18.5V6a1 1 0 011-1h4.6l2 2h7.4a1 1 0 011 1v2.5"/><path d="M3.5 18.5l2.8-7.2a1 1 0 01.9-.6h13.6l-2.9 7.8H3.5z"/></svg>',
};

// ---------------------------------------------------------------- the project
const RANGE = { dvd: [24, 58], cd: [23, 58], bd: [24, 58] };          // burnable radii, mm
const CAPACITY = { dvd: 4.7e9, cd: 0.7e9, bd: 25e9 };
const DEFAULT_TONE = { dither: 100, bright: 0, levels: 2, lin: false, inv: false, contrast: 0, hi: 0, sh: 0, mode: "floyd-steinberg", auto: null };
const MAX_SIDE = 2048;                       // the mock keeps a working copy; export would use the original
const COLOURS = { red: 0.62, green: 0.53, blue: 0.46 };   // target wavelengths, µm
const FLASH = [-43.66, 19.79];               // iPhone 17 Pro flash relative to the lens (drawing values)
const FWHM = 0.08;                           // measured peak width in δ (the model said 0.04)

let S = null;                                // the project on screen
// The plans (works) made or opened while the page lives, newest first. A plan is a work, not a disc:
// one batch of discs can carry many plans (docs/goals/gui-flow.md 1.1).
const plans = [];
const projects = new Map();                  // the shelf's old way in: one plan per shelf disc
export const recentPlans = () => plans.filter((P) => P.layers.length || P.name);
let W = null;                                // the workspace's DOM
const V = { s: 5, cx: 0, cy: 0, w: 0, h: 0, dpr: 1 };   // canvas view: px per mm and the disc centre
let nextId = 1;

function newProject(item, media) {
  return {
    item, media, layers: [], selected: null, tool: "move", view: "proj",
    tone: { ...DEFAULT_TONE }, files: null, dirty: false, name: null, handle: null,
    pro: false, cell: 0.02, loupe: false, lookColour: false, lookY: 70, playing: 0,
    scene: { preset: "design", cam: [0, -70, 330], lamp: [0, 0, 0], follows: true },
    past: [], future: [],
  };
}
const imageLayers = () => S.layers.filter((L) => L.kind === "image");
const sel = () => S.layers.find((L) => L.id === S.selected) ?? null;
const range = () => RANGE[S.media] ?? RANGE.dvd;
const lampPos = () => S.scene.follows ? [S.scene.cam[0] + FLASH[0], S.scene.cam[1] - FLASH[1], S.scene.cam[2]] : S.scene.lamp;
const heightOf = (L) => L.kind === "image" ? L.width * L.h / L.w : L.height;

// the part of the disc that holds files, if any: [from, to] radius in mm
function filesRing() {
  if (!S.files?.bytes) return null;
  const [r0, r1] = range(), f = Math.min(0.95, S.files.bytes / CAPACITY[S.media] + 0.002);
  if (S.files.where === "outer") return [Math.sqrt(r1 * r1 - (r1 * r1 - r0 * r0) * f), r1];
  return [r0, Math.sqrt(r0 * r0 + (r1 * r1 - r0 * r0) * f)];
}
// where the picture may go: [inner, outer]
function pictureRange() {
  const [r0, r1] = range(), fr = filesRing();
  if (!fr) return [r0, r1];
  return S.files.where === "outer" ? [r0, fr[0]] : [fr[1], r1];
}

// ---------------------------------------------------------------- history (undo / redo)
// A snapshot is the layer list with each layer's properties; pixels are immutable ImageData, so a
// snapshot only holds references to them.
const PROPS = ["name", "x", "y", "width", "height", "rot", "opacity", "visible", "locked", "px", "colour", "y1", "y2", "fxKind"];
function snapshot() {
  return { layers: S.layers.map((L) => ({ obj: L, props: Object.fromEntries(PROPS.map((k) => [k, L[k]])) })), selected: S.selected };
}
let lastMark = { key: "", t: 0 };
function checkpoint(key = "") {
  const now = Date.now();
  if (key && key === lastMark.key && now - lastMark.t < 700) { lastMark.t = now; return; }   // one step per burst
  lastMark = { key, t: now };
  S.past.push(snapshot());
  if (S.past.length > 80) S.past.shift();
  S.future = [];
  S.dirty = true;
}
function restore(snap) {
  S.layers = snap.layers.map(({ obj, props }) => {
    const pxChanged = obj.px !== props.px;
    Object.assign(obj, props);
    if (pxChanged) pixelsChanged(obj);
    return obj;
  });
  S.selected = snap.selected;
  for (const L of S.layers) clearSelection(L);
  changed();
  buildLeft();
}
function undo() { if (!S.past.length) return; S.future.push(snapshot()); restore(S.past.pop()); }
function redo() { if (!S.future.length) return; S.past.push(snapshot()); restore(S.future.pop()); }

// ---------------------------------------------------------------- layers
function pixelsChanged(L) {
  const c = L.src ?? document.createElement("canvas");
  c.width = L.px.width; c.height = L.px.height;
  c.getContext("2d").putImageData(L.px, 0, 0);
  L.src = c;
  L.version = (L.version ?? 0) + 1;
  L.thumb = null;
}
function addImageLayer(name, source, w, h) {
  if (S.layers.length >= 16) { toast(T().tooMany); return null; }
  const k = Math.min(1, MAX_SIDE / Math.max(w, h));
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(w * k)); c.height = Math.max(1, Math.round(h * k));
  const g = c.getContext("2d", { willReadFrequently: true });
  g.drawImage(source, 0, 0, c.width, c.height);
  const [, r1] = pictureRange();
  // the whole picture fits inside the burnable circle at first (its diagonal is the diameter)
  const width = 2 * r1 * 0.98 / Math.sqrt(1 + (c.height / c.width) ** 2);
  checkpoint();
  const L = {
    id: nextId++, kind: "image", name: name.replace(/\.[a-z0-9]+$/i, ""), w: c.width, h: c.height,
    x: 0, y: 0, width, rot: 0, opacity: 1, visible: true, locked: false, colour: "none",
    px: g.getImageData(0, 0, c.width, c.height), src: c, version: 1,
  };
  S.layers.push(L);
  S.selected = L.id;
  changed(); buildLeft(); buildRight();
  return L;
}
function addEffect(kind) {
  checkpoint();
  const size = { flow: [24, 30], ox: [20, 20], merge: [22, 22], sync: [30, 30] }[kind];
  const ys = { flow: [55, 100], ox: [55, 90], merge: [72, 100], sync: [70, 70] }[kind];
  // Left and right of the centre (3 and 9 o'clock) the track runs top to bottom, the way the phone
  // moves, so that is where a moving phone changes δ most; the burned flows sat there too.
  const [p0, p1] = pictureRange(), r = (p0 + p1) / 2;
  const n = S.layers.filter((L) => L.kind === "fx").length, a = [0, 180, -28, 208, 28, 152][n % 6] * Math.PI / 180;
  const L = {
    id: nextId++, kind: "fx", fxKind: kind, name: T().fxKinds[kind][0],
    x: r * Math.cos(a), y: r * Math.sin(a), width: size[0], height: size[1], rot: 0, opacity: 1,
    visible: true, locked: false, y1: ys[0], y2: ys[1],
  };
  S.layers.push(L);
  S.selected = L.id;
  changed(); buildLeft(); buildRight();
}
async function importFiles(files) {
  const t = T();
  for (const f of files) {
    if (!/^image\/(png|jpeg|webp|bmp)$/.test(f.type)) { toast(t.badType(f.name)); continue; }
    if (f.size > 24 * 1024 * 1024) { toast(t.tooBig(f.name)); continue; }
    let bmp;
    try { bmp = await createImageBitmap(f); } catch { toast(t.badType(f.name)); continue; }
    if (bmp.width * bmp.height > 36e6) { toast(t.tooBig(f.name)); continue; }
    const L = addImageLayer(f.name, bmp, bmp.width, bmp.height);
    if (L) L.file = f;                       // the original, for export at full size and for saving
    bmp.close?.();
  }
}
// a picture for trying the page: a flat white ground (good for the selection tool), hills and a sun
function sampleLayer() {
  const c = document.createElement("canvas"), w = 1600, h = 1200;
  c.width = w; c.height = h;
  const g = c.getContext("2d");
  g.fillStyle = "#ffffff"; g.fillRect(0, 0, w, h);
  const sun = g.createRadialGradient(1060, 380, 20, 1060, 380, 230);
  sun.addColorStop(0, "#f6c453"); sun.addColorStop(1, "#d9822b");
  g.fillStyle = sun; g.beginPath(); g.arc(1060, 380, 220, 0, Math.PI * 2); g.fill();
  const hill = (pts, col) => { g.fillStyle = col; g.beginPath(); g.moveTo(0, h); for (const [x, y] of pts) g.lineTo(x, y); g.lineTo(w, h); g.fill(); };
  hill([[0, 760], [260, 560], [520, 720], [820, 520], [1180, 760], [1600, 600]], "#7c8c9c");
  hill([[0, 920], [340, 720], [700, 900], [1040, 740], [1380, 880], [1600, 800]], "#3d4a57");
  hill([[0, 1060], [420, 930], [880, 1080], [1300, 960], [1600, 1020]], "#1d242b");
  g.strokeStyle = "#1d242b"; g.lineWidth = 9; g.lineCap = "round";
  for (const [x, y, s] of [[420, 300, 1], [520, 250, 0.8], [600, 330, 0.65]]) {
    g.beginPath(); g.moveTo(x - 40 * s, y); g.quadraticCurveTo(x - 18 * s, y - 24 * s, x, y); g.quadraticCurveTo(x + 18 * s, y - 24 * s, x + 40 * s, y); g.stroke();
  }
  addImageLayer(T().sampleName, c, w, h);
}

// ---------------------------------------------------------------- the selection tool
// Click a spot: everything of a similar colour that touches it is selected (tolerance in % of the
// RGB cube's diagonal). Shift adds, Alt removes. Selected pixels are drawn inverted on the canvas.
function flood(px, sx, sy, tol) {
  const { width: w, height: h, data: d } = px, out = new Uint8Array(w * h);
  const i0 = (sy * w + sx) * 4;
  if (!d[i0 + 3]) return out;
  const r0 = d[i0], g0 = d[i0 + 1], b0 = d[i0 + 2], lim = (tol / 100 * 441.673) ** 2;
  const ok = (i) => {
    if (out[i]) return false;
    const j = i * 4;
    if (!d[j + 3]) return false;
    const dr = d[j] - r0, dg = d[j + 1] - g0, db = d[j + 2] - b0;
    return dr * dr + dg * dg + db * db <= lim;
  };
  const stack = [sx, sy];
  while (stack.length) {
    const y = stack.pop(), x = stack.pop();
    if (!ok(y * w + x)) continue;
    let l = x, r = x;
    while (l > 0 && ok(y * w + l - 1)) l--;
    while (r < w - 1 && ok(y * w + r + 1)) r++;
    for (let k = l; k <= r; k++) out[y * w + k] = 1;
    for (const ny of [y - 1, y + 1]) {
      if (ny < 0 || ny >= h) continue;
      let open = false;
      for (let k = l; k <= r; k++) {
        const c = ok(ny * w + k);
        if (c && !open) { stack.push(k, ny); open = true; } else if (!c) open = false;
      }
    }
  }
  return out;
}
function runSelection(L) {
  const n = L.w * L.h;
  let mask = new Uint8Array(n);
  for (const s of L.seeds) {
    const f = flood(L.px, s.x, s.y, S.selTol);
    if (s.mode === "sub") for (let i = 0; i < n; i++) mask[i] &= 1 - f[i];
    else for (let i = 0; i < n; i++) mask[i] |= f[i];
  }
  L.sel = mask;
  // the inverted view of the selected pixels
  const img = new ImageData(L.w, L.h), d = L.px.data, o = img.data;
  const grey = S.view === "proj";
  for (let i = 0; i < n; i++) {
    if (!mask[i]) continue;
    const j = i * 4;
    if (grey) { const v = 255 - Math.round(d[j] * 0.299 + d[j + 1] * 0.587 + d[j + 2] * 0.114); o[j] = o[j + 1] = o[j + 2] = v; }
    else { o[j] = 255 - d[j]; o[j + 1] = 255 - d[j + 1]; o[j + 2] = 255 - d[j + 2]; }
    o[j + 3] = 255;
  }
  const c = L.selCanvas ?? document.createElement("canvas");
  c.width = L.w; c.height = L.h;
  c.getContext("2d").putImageData(img, 0, 0);
  L.selCanvas = c;
  L.selCount = mask.reduce((a, b) => a + b, 0);
  draw();
  placeBar();
}
function clearSelection(L) { if (!L) return; L.sel = null; L.seeds = []; L.selCanvas = null; L.selCount = 0; }
function wandAt(L, mm, mode) {
  const [u, v] = toLocal(L, mm);
  const px = Math.floor((u / L.width + 0.5) * L.w), py = Math.floor((v / heightOf(L) + 0.5) * L.h);
  if (px < 0 || py < 0 || px >= L.w || py >= L.h) return;
  if (mode === "new" || !L.seeds?.length) L.seeds = [];
  L.seeds.push({ x: px, y: py, mode: mode === "sub" ? "sub" : "add" });
  runSelection(L);
}
function boxBlur(src, w, h, r) {
  const a = Float32Array.from(src), b = new Float32Array(w * h);
  if (r < 1) return a;
  const pass = (from, to, len, count, step, lineStep) => {
    for (let line = 0; line < count; line++) {
      const base = line * lineStep;
      let sum = 0;
      for (let k = -r; k <= r; k++) sum += from[base + Math.min(len - 1, Math.max(0, k)) * step];
      for (let i = 0; i < len; i++) {
        to[base + i * step] = sum / (2 * r + 1);
        sum += from[base + Math.min(len - 1, i + r + 1) * step] - from[base + Math.max(0, i - r) * step];
      }
    }
  };
  pass(a, b, w, h, 1, w);
  pass(b, a, h, w, w, 1);
  return a;
}
function applySelection(L, keep) {
  if (!L?.sel) return;
  checkpoint();
  const m = boxBlur(L.sel, L.w, L.h, Math.round(S.selFeather ?? 0));
  const out = new ImageData(new Uint8ClampedArray(L.px.data), L.w, L.h);
  for (let i = 0; i < m.length; i++) out.data[i * 4 + 3] = Math.round(out.data[i * 4 + 3] * (keep ? m[i] : 1 - m[i]));
  L.px = out;
  L.alphaEdited = true;
  pixelsChanged(L);
  clearSelection(L);
  changed(); buildLeft();
}

// ---------------------------------------------------------------- geometry helpers
const toScreen = (x, y) => [V.cx + x * V.s, V.cy + y * V.s];
const toMm = (sx, sy) => [(sx - V.cx) / V.s, (sy - V.cy) / V.s];
function toLocal(L, [x, y]) {
  const a = -L.rot * Math.PI / 180, dx = x - L.x, dy = y - L.y;
  return [dx * Math.cos(a) - dy * Math.sin(a), dx * Math.sin(a) + dy * Math.cos(a)];
}
function corners(L) {
  const hw = L.width / 2, hh = heightOf(L) / 2, a = L.rot * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
  return [[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]].map(([u, v]) => toScreen(L.x + u * c - v * s, L.y + u * s + v * c));
}
function rotHandle(L) {
  const cs = corners(L), top = [(cs[0][0] + cs[1][0]) / 2, (cs[0][1] + cs[1][1]) / 2];
  const a = L.rot * Math.PI / 180;
  return [top[0] + 28 * Math.sin(a), top[1] - 28 * Math.cos(a)];
}
function hitLayer(mm, kinds = ["image", "fx"]) {
  for (let i = S.layers.length - 1; i >= 0; i--) {
    const L = S.layers[i];
    if (!L.visible || L.locked || !kinds.includes(L.kind)) continue;
    const [u, v] = toLocal(L, mm);
    if (Math.abs(u) <= L.width / 2 && Math.abs(v) <= heightOf(L) / 2) return L;
  }
  return null;
}
function fit() {
  V.s = Math.min(V.w, V.h) * 0.92 / 120;
  V.cx = V.w / 2; V.cy = V.h / 2;
  draw(); queueCompose();
}
function zoomAt(f, sx, sy) {
  const s = Math.min(Math.max(V.s * f, Math.min(V.w, V.h) * 0.2 / 120), 4 / S.cell);
  const k = s / V.s;
  V.cx = sx - (sx - V.cx) * k; V.cy = sy - (sy - V.cy) * k; V.s = s;
  draw(); queueCompose();
}
const zoomPct = () => Math.round(V.s * S.cell * 100);

// ---------------------------------------------------------------- the picture after tone (the projection)
function toneOptions() {
  const t = S.tone;
  const adjustments = {
    brightness: t.bright / 64 * 50, contrast: t.contrast, highlights: t.hi, shadows: t.sh,
    gamma: t.lin ? 1 / 2.2 : 1, invert: !!t.inv && S.media === "bd",
    ...(t.auto ? { blackPoint: t.auto[0], whitePoint: t.auto[1] } : {}),
  };
  const four = t.levels === 4 && S.media === "cd";
  const output = four ? { mode: "grayscale", levels: 4 } : { mode: t.mode, strength: t.dither / 100, levels: 256 };
  return { adjustments, output };
}
// Draw the picture layers (not the effects) into a canvas covering [x0, x1] × [y0, y1] mm at ppm.
// With `originals` (layer → full-size bitmap), each picture is drawn from its original file; where the
// selection tool removed parts, the working copy's alpha cuts the same parts out of it.
function rasterise(x0, y0, x1, y1, ppm, white = true, originals = null, layers = imageLayers()) {
  const pw = Math.max(1, Math.round((x1 - x0) * ppm)), ph = Math.max(1, Math.round((y1 - y0) * ppm));
  const c = document.createElement("canvas");
  c.width = pw; c.height = ph;
  const g = c.getContext("2d", { willReadFrequently: true });
  if (white) { g.fillStyle = "#fff"; g.fillRect(0, 0, pw, ph); }
  g.setTransform(ppm, 0, 0, ppm, -x0 * ppm, -y0 * ppm);
  for (const L of layers) {
    if (!L.visible) continue;
    g.save();
    g.globalAlpha = L.opacity;
    g.translate(L.x, L.y); g.rotate(L.rot * Math.PI / 180);
    const hh = heightOf(L), full = originals?.get(L);
    if (full && L.alphaEdited) {
      // the original with the working copy's alpha, put together at the size it lands on the canvas
      const k = Math.min(1, ppm * L.width / full.width), t = document.createElement("canvas");
      t.width = Math.max(1, Math.round(full.width * k)); t.height = Math.max(1, Math.round(full.height * k));
      const tg = t.getContext("2d");
      tg.drawImage(full, 0, 0, t.width, t.height);
      tg.globalCompositeOperation = "destination-in";
      tg.drawImage(L.src, 0, 0, t.width, t.height);
      g.drawImage(t, -L.width / 2, -hh / 2, L.width, hh);
    } else g.drawImage(full ?? L.src, -L.width / 2, -hh / 2, L.width, hh);
    g.restore();
  }
  return { c, g, pw, ph };
}
let comp = null, composeT = 0, composeKey = "";
let composeRevision = 0, composing = false, composeAgain = false, previewWorker = null;
function queueCompose() { composeRevision++; clearTimeout(composeT); composeT = setTimeout(compose, 40); }
async function compose() {
  if (composing) { composeAgain = true; return; }
  if (!S || !isOn() || !imageLayers().length) { comp = null; draw(); return; }
  const [, r1] = pictureRange();
  const [ax, ay] = toMm(0, 0), [bx, by] = toMm(V.w, V.h);
  const x0 = Math.max(ax, -r1), y0 = Math.max(ay, -r1), x1 = Math.min(bx, r1), y1 = Math.min(by, r1);
  if (x1 <= x0 || y1 <= y0) return;
  let ppm = Math.min(V.s * V.dpr, 1 / S.cell);
  ppm = Math.min(ppm, Math.sqrt(1.2e6 / ((x1 - x0) * (y1 - y0))));
  const key = JSON.stringify([x0.toFixed(1), y0.toFixed(1), x1.toFixed(1), y1.toFixed(1), ppm.toFixed(2), S.tone, S.media,
    imageLayers().map((L) => [L.id, L.version, L.x, L.y, L.width, L.rot, L.opacity, L.visible])]);
  if (key === composeKey && comp) return;
  const revision = composeRevision, project = S;
  const { c, g, pw, ph } = rasterise(x0, y0, x1, y1, ppm);
  const { adjustments, output } = toneOptions();
  composing = true;
  try {
    previewWorker ??= processingWorker();
    const image = g.getImageData(0, 0, pw, ph);
    const { image: out } = await previewWorker.run({ kind: "preview", image, adjustments, output,
      context: { previewScale: ppm * S.cell } }, [image.data.buffer]);
    if (revision !== composeRevision || project !== S || !isOn()) return;
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.putImageData(new ImageData(out.data, pw, ph), 0, 0);
    composeKey = key;
    comp = { c, x0, y0, x1, y1, ppm };
    draw();
  } catch (e) {
    console.warn("tone", e);
    previewWorker?.close(); previewWorker = null;
  } finally {
    composing = false;
    if (composeAgain) { composeAgain = false; compose(); }
  }
}

// ---------------------------------------------------------------- PRO: what the disc shows from a position
// First-order grating: λ = P·δ, δ = (unit vector to the lamp + unit vector to the camera) along the track.
function delta(x, y, cam, lamp) {
  const r = Math.hypot(x, y) || 1e-6, tx = -y / r, ty = x / r;
  const u = (p) => { const dx = p[0] - x, dy = p[1] - y, dz = p[2], n = Math.hypot(dx, dy, dz); return [dx / n, dy / n]; };
  const a = u(cam), b = u(lamp);
  return Math.abs((a[0] + b[0]) * tx + (a[1] + b[1]) * ty);
}
// the camera (and a lamp that rides on the phone) moved so the phone's offset toward the top is y
function poseAt(y) {
  const cam = [S.scene.cam[0], -y, S.scene.cam[2]];
  const lamp = S.scene.follows ? [cam[0] + FLASH[0], cam[1] - FLASH[1], cam[2]] : S.scene.lamp;
  return [cam, lamp];
}
function wavelengthRGB(nm) {
  let r = 0, g = 0, b = 0;
  if (nm >= 380 && nm < 440) { r = -(nm - 440) / 60; b = 1; }
  else if (nm < 490) { g = (nm - 440) / 50; b = 1; }
  else if (nm < 510) { g = 1; b = -(nm - 510) / 20; }
  else if (nm < 580) { r = (nm - 510) / 70; g = 1; }
  else if (nm < 645) { r = 1; g = -(nm - 645) / 65; }
  else if (nm <= 700) { r = 1; }
  const edge = nm < 420 ? 0.3 + 0.7 * (nm - 380) / 40 : nm > 680 ? 0.3 + 0.7 * (700 - nm) / 20 : 1;
  return nm < 380 || nm > 700 ? null : [r * edge, g * edge, b * edge];
}
// the target pose (phone y, mm) at local spot (u, v) ∈ [−½, ½]² of an effect area, or NaN outside it
function effectY(L, u, v, cellParity) {
  const lerp = (t) => L.y1 + (L.y2 - L.y1) * t;
  if (L.fxKind === "sync") return L.y1;
  if (L.fxKind === "flow") return lerp(0.5 - v);
  if (L.fxKind === "ox") {
    const w = 3.5 / 20 / 2;                          // stroke 3.5 mm on a 20 mm mark
    const inO = Math.abs(Math.hypot(u, v) - (0.5 - w)) <= w;
    const inX = Math.max(Math.abs(u), Math.abs(v)) <= 0.5 - w && Math.min(Math.abs(u - v), Math.abs(u + v)) / Math.SQRT2 <= w;
    if (inO && inX) return cellParity ? L.y1 : L.y2;
    return inO ? L.y1 : inX ? L.y2 : NaN;
  }
  if (L.fxKind === "merge") {                        // Cassini field: two minima and a saddle
    const xi = u * 5, eta = v * 5;
    const rho = Math.sqrt(((xi - 1) ** 2 + eta ** 2) * ((xi + 1) ** 2 + eta ** 2));
    return rho > 2.2 ? NaN : lerp(rho);
  }
  return NaN;
}
let lookCanvas = null, lookKey = "";
function lookOverlay() {
  const fx = S.layers.filter((L) => L.kind === "fx" && L.visible);
  const coloured = imageLayers().filter((L) => L.visible && L.colour !== "none");
  if (!S.pro || (!fx.length && !(S.lookColour && coloured.length))) return null;
  const key = JSON.stringify([S.lookY, S.scene, S.lookColour, fx.map((L) => PROPS.map((k) => L[k])), coloured.map((L) => [L.id, L.version, L.x, L.y, L.width, L.rot, L.colour])]);
  if (key === lookKey && lookCanvas) return lookCanvas;
  lookKey = key;
  const N = 240, mm = 120 / N, imgC = new ImageData(N, N), imgF = new ImageData(N, N);
  const [camP, lampP] = poseAt(S.lookY);
  const [camD, lampD] = poseAt(-S.scene.cam[1]);   // the design position: what the textures were chosen for
  // where each coloured layer is: its alpha on the same grid
  const masks = coloured.map((L) => {
    const one = { ...L };
    const { g } = rasterise(-60, -60, 60, 60, N / 120, false);
    g.clearRect(-60, -60, 120, 120);
    g.save(); g.translate(one.x, one.y); g.rotate(one.rot * Math.PI / 180);
    const hh = heightOf(one); g.drawImage(one.src, -one.width / 2, -hh / 2, one.width, hh); g.restore();
    return { L, a: g.getImageData(0, 0, N, N).data };
  });
  for (let j = 0; j < N; j++) for (let i = 0; i < N; i++) {
    const x = -60 + (i + 0.5) * mm, y = -60 + (j + 0.5) * mm, k = (j * N + i) * 4;
    let rgb = null, B = 0, o = imgC.data;
    for (const { L, a } of masks) {
      if (a[k + 3] < 20) continue;
      const dD = delta(x, y, camD, lampD), dP = delta(x, y, camP, lampP);
      const at = (want) => wavelengthRGB(want * 1000 * dP / Math.max(dD, 1e-6)) ?? [0, 0, 0];
      // purple is red and blue cells side by side: the eye adds them
      rgb = L.colour === "purple" ? at(COLOURS.red).map((v, c) => Math.min(1, (v + at(COLOURS.blue)[c]) * 0.8)) : at(COLOURS[L.colour]);
      B = Math.exp(-4 * Math.LN2 * ((dP - dD) / FWHM) ** 2) * 0.75 + 0.25;
    }
    if (rgb) {                                       // multiplied onto the projection: dark stays dark
      o[k] = 255 * (1 - B + B * rgb[0]); o[k + 1] = 255 * (1 - B + B * rgb[1]); o[k + 2] = 255 * (1 - B + B * rgb[2]); o[k + 3] = 255;
    }
    rgb = null; B = 0; o = imgF.data;
    for (const L of fx) {
      const [u, v] = toLocal(L, [x, y]);
      const lu = u / L.width, lv = v / L.height;
      if (Math.abs(lu) > 0.5 || Math.abs(lv) > 0.5) continue;
      const yt = effectY(L, lu, lv, (i + j) % 2);
      if (Number.isNaN(yt)) continue;
      const [camT, lampT] = poseAt(yt);
      const dT = delta(x, y, camT, lampT), dP = delta(x, y, camP, lampP);
      const b = Math.exp(-4 * Math.LN2 * ((dP - dT) / FWHM) ** 2);
      if (b < 0.04) { rgb = rgb ?? [0, 0, 0]; B = Math.max(B, 0.0001); continue; }
      rgb = wavelengthRGB(550 * dP / Math.max(dT, 1e-6)) ?? [1, 1, 1];
      B = b;
    }
    if (!rgb) continue;
    o[k] = 255 * Math.min(1, rgb[0] * B + 0.06); o[k + 1] = 255 * Math.min(1, rgb[1] * B + 0.06); o[k + 2] = 255 * Math.min(1, rgb[2] * B + 0.08);
    o[k + 3] = 235;
  }
  const put = (img) => { const c = document.createElement("canvas"); c.width = N; c.height = N; c.getContext("2d").putImageData(img, 0, 0); return c; };
  lookCanvas = { colour: put(imgC), fx: put(imgF) };
  return lookCanvas;
}

// ---------------------------------------------------------------- drawing the canvas
let drawQueued = false;
function draw() {
  if (drawQueued) return;
  drawQueued = true;
  const run = () => { if (!drawQueued) return; drawQueued = false; paintCanvas(); };
  requestAnimationFrame(run);
  setTimeout(run, 60);                      // a hidden page gets no animation frames
}
const cssVar = (n) => getComputedStyle(root).getPropertyValue(n).trim();
function annulus(g, a, b) {
  g.beginPath();
  g.arc(V.cx, V.cy, b * V.s, 0, Math.PI * 2);
  g.arc(V.cx, V.cy, a * V.s, 0, Math.PI * 2, true);
}
function paintCanvas() {
  if (!W || !S) return;
  const cv = W.canvas, g = cv.getContext("2d");
  g.setTransform(V.dpr, 0, 0, V.dpr, 0, 0);
  g.clearRect(0, 0, V.w, V.h);
  const face = cssVar("--face"), face2 = cssVar("--face-2"), dim = cssVar("--dim"), paper = cssVar("--paper");
  const [r0, r1] = range(), [p0, p1] = pictureRange(), fr = filesRing();
  // the disc, data side up
  g.fillStyle = face; g.beginPath(); g.arc(V.cx, V.cy, 60 * V.s, 0, Math.PI * 2); g.fill();
  g.fillStyle = face2; annulus(g, 7.5, 17); g.fill("evenodd");
  g.fillStyle = paper; g.beginPath(); g.arc(V.cx, V.cy, 7.5 * V.s, 0, Math.PI * 2); g.fill();
  // the pictures as they are (grey in the projection), everywhere, so what falls outside still shows
  const grey = S.view === "proj";
  for (const L of imageLayers()) {
    if (!L.visible) continue;
    g.save();
    g.globalAlpha = L.opacity;
    if (grey) g.filter = "grayscale(1)";
    g.translate(V.cx + L.x * V.s, V.cy + L.y * V.s); g.rotate(L.rot * Math.PI / 180);
    const hh = heightOf(L) * V.s;
    g.drawImage(L.src, -L.width * V.s / 2, -hh / 2, L.width * V.s, hh);
    g.restore();
  }
  // the projection (after tone and dithering) inside the burnable ring
  if (grey && comp) {
    g.save(); annulus(g, p0, p1); g.clip("evenodd");
    g.imageSmoothingEnabled = comp.ppm < V.s * V.dpr * 0.95 ? false : true;
    g.drawImage(comp.c, V.cx + comp.x0 * V.s, V.cy + comp.y0 * V.s, (comp.x1 - comp.x0) * V.s, (comp.y1 - comp.y0) * V.s);
    g.restore();
  }
  // PRO: how it looks from the chosen position
  const look = lookOverlay();
  if (look) {
    g.save(); annulus(g, p0, p1); g.clip("evenodd");
    g.imageSmoothingEnabled = true;
    const box = [V.cx - 60 * V.s, V.cy - 60 * V.s, 120 * V.s, 120 * V.s];
    g.globalCompositeOperation = "multiply"; g.drawImage(look.colour, ...box);
    g.globalCompositeOperation = "source-over"; g.globalAlpha = 0.95; g.drawImage(look.fx, ...box);
    g.restore();
  }
  // selected pixels, inverted
  const L = sel();
  if (L?.selCanvas) {
    g.save(); g.translate(V.cx + L.x * V.s, V.cy + L.y * V.s); g.rotate(L.rot * Math.PI / 180);
    const hh = heightOf(L) * V.s;
    g.drawImage(L.selCanvas, -L.width * V.s / 2, -hh / 2, L.width * V.s, hh);
    g.restore();
  }
  // everything outside the burnable ring is dimmed, not hidden (as DiscImageStudio does)
  g.fillStyle = dim;
  g.beginPath(); g.rect(0, 0, V.w, V.h); g.arc(V.cx, V.cy, r1 * V.s, 0, Math.PI * 2, true); g.fill();
  g.beginPath(); g.arc(V.cx, V.cy, r0 * V.s, 0, Math.PI * 2); g.fill();
  // the ring that holds files: light diagonal lines
  if (fr) {
    g.save(); annulus(g, fr[0], fr[1]); g.clip("evenodd");
    g.fillStyle = dim; g.fillRect(0, 0, V.w, V.h);
    g.strokeStyle = cssVar("--ink-3"); g.globalAlpha = 0.45; g.lineWidth = 1;
    const R = fr[1] * V.s;
    for (let k = -2 * R; k < 2 * R; k += 9) { g.beginPath(); g.moveTo(V.cx + k - R, V.cy + R); g.lineTo(V.cx + k + R, V.cy - R); g.stroke(); }
    g.restore();
  }
  // the edges of the burnable range
  g.strokeStyle = cssVar("--rule-strong"); g.lineWidth = 1;
  for (const r of [r0, r1, 60]) { g.beginPath(); g.arc(V.cx, V.cy, r * V.s, 0, Math.PI * 2); g.stroke(); }
  // effect areas: their outline and name
  for (const F of S.layers) {
    if (F.kind !== "fx" || !F.visible) continue;
    const cs = corners(F);
    g.save(); g.setLineDash([5, 4]); g.strokeStyle = cssVar("--copper"); g.lineWidth = 1.2;
    g.beginPath(); cs.forEach(([x, y], i) => i ? g.lineTo(x, y) : g.moveTo(x, y)); g.closePath(); g.stroke();
    g.restore();
    g.fillStyle = cssVar("--copper"); g.font = `600 13px ${cssVar("--font")}`;
    g.fillText(F.name, cs[0][0] + 4, cs[0][1] - 6);
  }
  // the selected layer's frame and handles
  if (L && S.tool === "move") {
    const cs = corners(L), acc = cssVar("--copper");
    g.strokeStyle = acc; g.lineWidth = 1.5;
    g.beginPath(); cs.forEach(([x, y], i) => i ? g.lineTo(x, y) : g.moveTo(x, y)); g.closePath(); g.stroke();
    if (!L.locked) {
      const top = [(cs[0][0] + cs[1][0]) / 2, (cs[0][1] + cs[1][1]) / 2], rh = rotHandle(L);
      g.beginPath(); g.moveTo(...top); g.lineTo(...rh); g.stroke();
      g.fillStyle = paper;
      for (const [x, y] of cs) { g.fillRect(x - 5, y - 5, 10, 10); g.strokeRect(x - 5, y - 5, 10, 10); }
      g.beginPath(); g.arc(rh[0], rh[1], 6, 0, Math.PI * 2); g.fill(); g.stroke();
    }
  }
  // words over the canvas
  W.zoom.textContent = `${zoomPct()}%`;
  const out = imageLayers().some((L) => L.visible && cornersOutside(L, p0, p1));
  W.note.hidden = !out;
  W.note.textContent = T().outside;
  W.empty.hidden = S.layers.length > 0;
  placeBar();
}
function cornersOutside(L, p0, p1) {
  const hw = L.width / 2, hh = heightOf(L) / 2, a = L.rot * Math.PI / 180;
  for (const [u, v] of [[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]]) {
    const x = L.x + u * Math.cos(a) - v * Math.sin(a), y = L.y + u * Math.sin(a) + v * Math.cos(a);
    if (Math.hypot(x, y) > p1) return true;
  }
  return false;                              // the centre hole is cut from every picture; not worth a warning
}

// ---------------------------------------------------------------- the floating bar under the selected layer
function placeBar() {
  const L = sel(), bar = W?.bar;
  if (!bar) return;
  if (!L || !L.visible) { bar.hidden = true; return; }
  const mode = L.sel && L.selCount ? "sel" : "props";
  if (bar.dataset.mode !== mode || bar.dataset.id !== String(L.id) || bar.dataset.lang !== api.lang()) fillBar(L, mode);
  else syncBar(L);
  bar.hidden = false;
  const cs = corners(L), xs = cs.map((p) => p[0]), ys = cs.map((p) => p[1]);
  const bw = bar.offsetWidth, bh = bar.offsetHeight;
  // under the layer; above it if there is no room; at the bottom of the canvas if neither fits
  let top = Math.max(...ys) + 14;
  if (top + bh > V.h - 44) {
    top = Math.min(...ys) - 14 - bh - (S.tool === "move" ? 30 : 0);
    if (top < 48) top = V.h - bh - 44;
  }
  const left = Math.min(Math.max((Math.min(...xs) + Math.max(...xs)) / 2 - bw / 2, 52), V.w - bw - 4);
  bar.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
}
function fillBar(L, mode) {
  const t = T(), bar = W.bar;
  bar.dataset.mode = mode; bar.dataset.id = String(L.id); bar.dataset.lang = api.lang();
  if (mode === "sel") {
    bar.innerHTML = `<label>${t.sel.tol}<input class="rng" type="range" min="0" max="60" step="1" data-k="tol"></label>` +
      `<label>${t.sel.feather}<input class="short" type="number" min="0" max="20" step="1" data-k="feather"></label><span class="sep"></span>` +
      `<button class="sbtn" type="button" data-a="cut">${t.sel.cut}</button><button class="sbtn" type="button" data-a="keep">${t.sel.keep}</button>` +
      `<button class="sbtn" type="button" data-a="cancel">${t.sel.cancel}</button><span class="k">${t.sel.hint}</span>`;
  } else {
    const f = t.fb, fx = L.kind === "fx";
    bar.innerHTML = `<label>${f.x}<input type="number" step="0.1" data-k="x"></label><label>${f.y}<input type="number" step="0.1" data-k="y"></label>` +
      `<label>${f.w}<input type="number" step="0.5" min="1" data-k="width"></label>` + (fx ? `<label>${f.h}<input type="number" step="0.5" min="1" data-k="height"></label>` : "") +
      `<label>${f.rot}<input class="short" type="number" step="1" data-k="rot"></label>` + (fx ? "" : `<label>${f.op}<input class="short" type="number" step="5" min="0" max="100" data-k="opacity"></label>`) +
      `<span class="sep"></span><button class="ib" type="button" data-a="lock" aria-label="${L.locked ? t.unlock : t.lock}" title="${L.locked ? t.unlock : t.lock}" aria-pressed="${L.locked}">${L.locked ? I.lock : I.unlock}</button>` +
      `<button class="ib" type="button" data-a="del" aria-label="${t.remove}" title="${t.remove}">${I.trash}</button>`;
  }
  syncBar(L);
}
function syncBar(L) {
  for (const inp of W.bar.querySelectorAll("input[data-k]")) {
    if (document.activeElement === inp) continue;
    const k = inp.dataset.k;
    const v = k === "tol" ? S.selTol : k === "feather" ? S.selFeather : k === "opacity" ? Math.round(L.opacity * 100) : L[k];
    inp.value = typeof v === "number" ? String(Math.round(v * 10) / 10) : v;
  }
}
function barInput(e) {
  const L = sel(), inp = e.target.closest("input[data-k]");
  if (!L || !inp) return;
  const k = inp.dataset.k, v = Number(inp.value);
  if (!Number.isFinite(v)) return;
  if (k === "tol") { S.selTol = v; runSelection(L); return; }
  if (k === "feather") { S.selFeather = Math.max(0, Math.min(20, v)); return; }
  checkpoint(`bar-${k}-${L.id}`);
  if (k === "opacity") L.opacity = Math.max(0, Math.min(1, v / 100));
  else if (k === "width" || k === "height") L[k] = Math.max(1, v);
  else L[k] = v;
  changed();
}
function barClick(e) {
  const b = e.target.closest("button[data-a]"), L = sel();
  if (!b || !L) return;
  const a = b.dataset.a;
  if (a === "cut") applySelection(L, false);
  else if (a === "keep") applySelection(L, true);
  else if (a === "cancel") { clearSelection(L); draw(); }
  else if (a === "lock") { checkpoint(); L.locked = !L.locked; W.bar.dataset.mode = ""; changed(); buildLeft(); }
  else if (a === "del") removeLayer(L);
}
function removeLayer(L) {
  checkpoint();
  S.layers = S.layers.filter((x) => x !== L);
  if (S.selected === L.id) S.selected = null;
  changed(); buildLeft(); buildRight();
}

// a change to the project: redraw, recompute the projection, mark unsaved
function changed() {
  S.dirty = true;
  W?.dirty.classList.toggle("on", S.dirty);
  if (W) W.dirty.title = T().unsaved;
  draw(); queueCompose();
  refreshLayerRows();
  $("next").disabled = !imageLayers().length;
}

// ---------------------------------------------------------------- canvas input
const pointers = new Map();
let drag = null, spaceDown = false;
function canvasPoint(e) { const r = W.canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }
function onDown(e) {
  if (!S) return;
  W.canvas.setPointerCapture(e.pointerId);
  const p = canvasPoint(e);
  pointers.set(e.pointerId, p);
  if (pointers.size === 2) {                // two fingers: pinch and pan
    const [a, b] = [...pointers.values()];
    drag = { kind: "pinch", d0: Math.hypot(a[0] - b[0], a[1] - b[1]), s0: V.s, c0: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], cx: V.cx, cy: V.cy };
    return;
  }
  if (e.button === 1 || spaceDown || S.tool === "pan") {
    drag = { kind: "pan", p0: p, cx: V.cx, cy: V.cy };
    W.cv.classList.add("panning");
    e.preventDefault();
    return;
  }
  if (e.button !== 0) return;
  const mm = toMm(...p);
  if (S.tool === "wand") {
    const L = hitLayer(mm, ["image"]);
    if (!L) return;
    if (S.selected !== L.id) { for (const x of S.layers) clearSelection(x); S.selected = L.id; buildLeft(); }
    wandAt(L, mm, e.shiftKey ? "add" : e.altKey ? "sub" : "new");
    return;
  }
  const L = sel();
  if (L && !L.locked) {
    const rh = rotHandle(L);
    if (Math.hypot(p[0] - rh[0], p[1] - rh[1]) < 11) {
      checkpoint();
      drag = { kind: "rot", L, a0: Math.atan2(p[1] - (V.cy + L.y * V.s), p[0] - (V.cx + L.x * V.s)), rot0: L.rot };
      return;
    }
    for (const c of corners(L)) {
      if (Math.abs(p[0] - c[0]) < 9 && Math.abs(p[1] - c[1]) < 9) {
        checkpoint();
        const cx = V.cx + L.x * V.s, cy = V.cy + L.y * V.s;
        drag = { kind: "scale", L, d0: Math.hypot(p[0] - cx, p[1] - cy), w0: L.width, h0: L.height };
        return;
      }
    }
  }
  const hit = hitLayer(mm);
  if (hit) {
    if (S.selected !== hit.id) { for (const x of S.layers) clearSelection(x); S.selected = hit.id; buildLeft(); buildRight(); }
    checkpoint();
    drag = { kind: "move", L: hit, m0: mm, x0: hit.x, y0: hit.y };
  } else {
    if (S.selected !== null) { S.selected = null; buildLeft(); buildRight(); }
    drag = { kind: "pan", p0: p, cx: V.cx, cy: V.cy, soft: true };
  }
  draw();
}
function onMove(e) {
  if (!S) return;
  const p = canvasPoint(e);
  if (pointers.has(e.pointerId)) pointers.set(e.pointerId, p);
  if (S.loupe) loupeAt(p);
  if (!drag) return;
  if (drag.kind === "pinch" && pointers.size === 2) {
    const [a, b] = [...pointers.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]), c = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    const s = Math.min(Math.max(drag.s0 * d / drag.d0, Math.min(V.w, V.h) * 0.2 / 120), 4 / S.cell), k = s / drag.s0;
    V.s = s; V.cx = c[0] - (drag.c0[0] - drag.cx) * k; V.cy = c[1] - (drag.c0[1] - drag.cy) * k;
    draw(); queueCompose();
  } else if (drag.kind === "pan") {
    V.cx = drag.cx + p[0] - drag.p0[0]; V.cy = drag.cy + p[1] - drag.p0[1];
    draw(); queueCompose();
  } else if (drag.kind === "move") {
    const mm = toMm(...p);
    let dx = mm[0] - drag.m0[0], dy = mm[1] - drag.m0[1];
    if (e.shiftKey) { if (Math.abs(dx) > Math.abs(dy)) dy = 0; else dx = 0; }
    drag.L.x = drag.x0 + dx; drag.L.y = drag.y0 + dy;
    changed();
  } else if (drag.kind === "scale") {
    const L = drag.L, cx = V.cx + L.x * V.s, cy = V.cy + L.y * V.s, k = Math.max(0.02, Math.hypot(p[0] - cx, p[1] - cy) / drag.d0);
    L.width = Math.max(1, drag.w0 * k);
    if (L.kind === "fx") L.height = Math.max(1, drag.h0 * k);
    changed();
  } else if (drag.kind === "rot") {
    const L = drag.L, a = Math.atan2(p[1] - (V.cy + L.y * V.s), p[0] - (V.cx + L.x * V.s));
    let r = drag.rot0 + (a - drag.a0) * 180 / Math.PI;
    if (e.shiftKey) r = Math.round(r / 15) * 15;
    L.rot = ((r % 360) + 540) % 360 - 180;
    changed();
  }
}
function onUp(e) {
  pointers.delete(e.pointerId);
  if (drag?.kind === "pan") W.cv.classList.remove("panning");
  if (pointers.size < 2 && drag?.kind === "pinch") drag = null;
  if (!pointers.size) drag = null;
}
function onWheel(e) {
  e.preventDefault();
  const p = canvasPoint(e);
  // a pinch on a touchpad arrives as a wheel with Ctrl; a mouse wheel moves in whole notches
  const mouse = e.deltaMode === 1 || (e.deltaX === 0 && Math.abs(e.deltaY) >= 50 && Number.isInteger(e.deltaY));
  if (e.ctrlKey) zoomAt(Math.exp(-e.deltaY * 0.01), ...p);
  else if (mouse) zoomAt(e.deltaY < 0 ? 1.18 : 1 / 1.18, ...p);
  else { V.cx -= e.deltaX; V.cy -= e.deltaY; draw(); queueCompose(); }
}
function onKey(e) {
  if (!isOn() || !S) return;
  if (e.target.closest?.("input, select, textarea")) return;
  const L = sel(), k = e.key;
  if (k === " " && !spaceDown) { spaceDown = true; W.cv.classList.add("pan"); e.preventDefault(); return; }
  if ((e.ctrlKey || e.metaKey) && (k === "z" || k === "Z")) { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
  if ((e.ctrlKey || e.metaKey) && (k === "y")) { e.preventDefault(); redo(); return; }
  if ((e.ctrlKey || e.metaKey) && (k === "s" || k === "S")) { e.preventDefault(); saveProject(e.shiftKey); return; }
  if ((e.ctrlKey || e.metaKey) && (k === "o" || k === "O")) { e.preventDefault(); pickProject(); return; }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (k === "0") { fit(); return; }
  if (k === "1") { zoomAt(1 / S.cell / V.s, V.w / 2, V.h / 2); return; }
  if (k === "v" || k === "V") setTool("move");
  else if (k === "w" || k === "W") setTool("wand");
  else if (k === "h" || k === "H") setTool("pan");
  else if (k === "Escape") {
    if (L?.sel) { clearSelection(L); draw(); }
    else if (L) { S.selected = null; buildLeft(); buildRight(); draw(); }
    else leave();
  } else if ((k === "Delete" || k === "Backspace") && L) {
    if (L.sel && L.selCount) applySelection(L, false); else removeLayer(L);
  } else if (k.startsWith("Arrow") && L && !L.locked) {
    e.preventDefault();
    const step = e.shiftKey ? 1 : 0.1;
    checkpoint(`nudge-${L.id}`);
    if (k === "ArrowLeft") L.x -= step; if (k === "ArrowRight") L.x += step;
    if (k === "ArrowUp") L.y -= step; if (k === "ArrowDown") L.y += step;
    changed();
  }
}
function onKeyUp(e) { if (e.key === " ") { spaceDown = false; W?.cv.classList.remove("pan"); } }
function setTool(t) {
  S.tool = t;
  W.cv.dataset.tool = t;
  for (const b of W.tools.querySelectorAll("[data-tool]")) b.setAttribute("aria-pressed", String(b.dataset.tool === t));
  W.cv.classList.toggle("pan", t === "pan");
  draw();
}

// ---------------------------------------------------------------- PRO: the loupe
let loupeT = 0;
function loupeAt(p) {
  clearTimeout(loupeT);
  W.loupe.style.transform = `translate(${p[0] - 100}px, ${p[1] - 100}px)`;
  loupeT = setTimeout(() => {
    const [x, y] = toMm(...p), n = 50, half = n * S.cell / 2;
    const { c, g, pw, ph } = rasterise(x - half, y - half, x + half, y + half, 1 / S.cell);
    const { adjustments, output } = toneOptions();
    try {
      const out = renderOutput(processRGBA(g.getImageData(0, 0, pw, ph), adjustments, { previewScale: 1 }), output);
      const lc = W.loupe.querySelector("canvas");
      lc.width = pw; lc.height = ph;
      lc.getContext("2d").putImageData(new ImageData(out.data, pw, ph), 0, 0);
    } catch (e) { console.warn(e); }
    W.loupe.querySelector("small").textContent = T().loupeHint(Math.round(S.cell * 1000), (n * S.cell).toFixed(2));
    void c;
  }, 40);
}

// ---------------------------------------------------------------- the left column
function thumb(L) {
  if (L.thumb) return L.thumb;
  const c = document.createElement("canvas");
  c.width = 88; c.height = 88;
  const g = c.getContext("2d"), k = Math.min(88 / L.w, 88 / L.h);
  g.drawImage(L.src, (88 - L.w * k) / 2, (88 - L.h * k) / 2, L.w * k, L.h * k);
  L.thumb = c;
  return c;
}
function buildLeft() {
  if (!W) return;
  const t = T();
  const rows = [...S.layers].reverse();
  W.left.innerHTML = `<section><h3><span class="grow">${t.layers}</span>` +
    `<button class="ib" type="button" data-a="undo" aria-label="${t.undo}" title="${t.undo}" ${S.past.length ? "" : "disabled"}>${I.undo}</button>` +
    `<button class="ib" type="button" data-a="redo" aria-label="${t.redo}" title="${t.redo}" ${S.future.length ? "" : "disabled"}>${I.redo}</button></h3>` +
    (rows.length ? `<ul class="lays" role="listbox" aria-label="${t.layers}">${rows.map((L) => `<li class="lay${L.visible ? "" : " hid"}" role="option" draggable="true" data-id="${L.id}" aria-selected="${L.id === S.selected}">` +
      (L.kind === "fx" ? `<span class="fxmark">${I.fx}</span>` : `<span class="th"></span>`) +
      `<span class="nm">${esc(L.name)}${L.kind === "fx" ? `<small>${t.fxY(L.y1, L.y2)}</small>` : ""}</span>` +
      `<button class="ib" type="button" data-a="vis" aria-label="${L.visible ? t.hide : t.show}" title="${L.visible ? t.hide : t.show}">${L.visible ? I.eye : I.eyeOff}</button>` +
      `<button class="ib" type="button" data-a="lock" aria-label="${L.locked ? t.unlock : t.lock}" title="${L.locked ? t.unlock : t.lock}">${L.locked ? I.lock : I.unlock}</button></li>`).join("")}</ul>`
      : `<p class="empty-l">${t.noLayers}</p>`) +
    `<button class="sbtn wide" type="button" data-a="import">${I.image}${t.import}</button></section>` +
    `<section><h3>${t.files}</h3>` +
    (S.files ? `<p class="note">${t.filesN(S.files.count, size(S.files.bytes))}</p>` +
      `<div class="seg" role="group" aria-label="${t.files}"><button type="button" data-a="inner" aria-pressed="${S.files.where === "inner"}">${t.inner}</button><button type="button" data-a="outer" aria-pressed="${S.files.where === "outer"}">${t.outer}</button></div>` +
      `<p class="note quiet">${t.filesRing(...filesRing().map((r) => r.toFixed(1)))}</p>`
      : `<p class="note quiet">${t.filesNone}</p>`) +
    (S.media === "cd" ? `<p class="note quiet">${t.cdFiles}</p>` : "") +
    `<div class="row2"><button class="sbtn" type="button" data-a="folder">${I.folder}${t.pickFolder}</button>` +
    `<button class="sbtn" type="button" data-a="nofiles" ${S.files ? "" : "disabled"}>${t.clear}</button></div></section>`;
  for (const li of W.left.querySelectorAll(".lay")) {
    const L = S.layers.find((x) => x.id === Number(li.dataset.id));
    if (L.kind === "image") li.querySelector(".th").replaceWith(thumb(L));
  }
}
function refreshLayerRows() {
  for (const li of W?.left.querySelectorAll(".lay") ?? []) {
    const L = S.layers.find((x) => x.id === Number(li.dataset.id));
    if (!L) continue;
    li.setAttribute("aria-selected", String(L.id === S.selected));
    const small = li.querySelector("small");
    if (small && L.kind === "fx") small.textContent = T().fxY(L.y1, L.y2);
  }
  const u = W?.left.querySelector('[data-a="undo"]'), r = W?.left.querySelector('[data-a="redo"]');
  if (u) u.disabled = !S.past.length;
  if (r) r.disabled = !S.future.length;
}
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const size = (b) => b > 1e9 ? `${(b / 1e9).toFixed(2)} GB` : b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.ceil(b / 1e3)} KB`;
function leftClick(e) {
  const b = e.target.closest("[data-a]"), li = e.target.closest(".lay");
  const L = li ? S.layers.find((x) => x.id === Number(li.dataset.id)) : null;
  const a = b?.dataset.a;
  if (a === "undo") return undo();
  if (a === "redo") return redo();
  if (a === "import") return W.file.click();
  if (a === "folder") return W.folder.click();
  if (a === "nofiles") { S.files = null; changed(); buildLeft(); return; }
  if (a === "inner" || a === "outer") { S.files.where = a; changed(); buildLeft(); return; }
  if (L && a === "vis") { checkpoint(); L.visible = !L.visible; changed(); buildLeft(); return; }
  if (L && a === "lock") { checkpoint(); L.locked = !L.locked; if (W.bar) W.bar.dataset.mode = ""; changed(); buildLeft(); return; }
  if (L) { for (const x of S.layers) if (x !== L) clearSelection(x); S.selected = L.id; refreshLayerRows(); buildRight(); draw(); }
}
function leftDbl(e) {
  const li = e.target.closest(".lay");
  if (!li || e.target.closest("button")) return;
  const L = S.layers.find((x) => x.id === Number(li.dataset.id)), nm = li.querySelector(".nm");
  const inp = document.createElement("input");
  inp.value = L.name; inp.className = "num"; inp.style.textAlign = "left";
  nm.replaceWith(inp); inp.focus(); inp.select();
  const done = (ok) => { if (ok && inp.value.trim() && inp.value !== L.name) { checkpoint(); L.name = inp.value.trim(); } buildLeft(); };
  inp.addEventListener("keydown", (ev) => { if (ev.key === "Enter") done(true); if (ev.key === "Escape") done(false); ev.stopPropagation(); });
  inp.addEventListener("blur", () => done(true));
}
// drag a row to change the stacking order (top of the list is drawn on top)
let dragRow = null;
function leftDrag(e) {
  const li = e.target.closest?.(".lay");
  if (e.type === "dragstart" && li) { dragRow = Number(li.dataset.id); li.classList.add("drag"); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", li.dataset.id); }
  else if (e.type === "dragover" && li && dragRow !== null) { e.preventDefault(); for (const x of W.left.querySelectorAll(".over")) x.classList.remove("over"); li.classList.add("over"); }
  else if (e.type === "drop" && li && dragRow !== null) {
    e.preventDefault();
    const from = S.layers.findIndex((L) => L.id === dragRow), target = S.layers.findIndex((L) => L.id === Number(li.dataset.id));
    if (from >= 0 && target >= 0 && from !== target) {
      checkpoint();
      const [moved] = S.layers.splice(from, 1);
      S.layers.splice(target, 0, moved);
      changed();
    }
    dragRow = null; buildLeft();
  } else if (e.type === "dragend") { dragRow = null; buildLeft(); }
}

// ---------------------------------------------------------------- the right column: tone, then PRO
function slider(id, label, min, max, step, value) {
  return `<div class="ctl"><label for="${id}">${label}</label><input class="num" id="${id}-n" type="number" min="${min}" max="${max}" step="${step}" value="${value}" data-k="${id}">` +
    `<input class="rng" id="${id}" type="range" min="${min}" max="${max}" step="${step}" value="${value}" data-k="${id}"></div>`;
}
function buildRight() {
  if (!W) return;
  const t = T(), tone = S.tone, L = sel();
  const proSw = `<div class="pro-sw"><span class="lbl"><span class="pr">PRO</span>-Experimental</span>` +
    `<button class="sw" type="button" role="switch" aria-checked="${S.pro}" aria-label="${t.proAria}" data-a="pro"></button></div>`;
  const toneS = `<section><h3>${t.tone}</h3>` +
    slider("dither", t.dither, 0, 100, 1, tone.dither) + slider("bright", t.bright, -64, 64, 1, tone.bright) +
    `<div class="ctl-line"><span>${t.levels}</span><div class="seg" role="group" aria-label="${t.levels}">` +
    `<button type="button" data-lv="2" aria-pressed="${tone.levels === 2}">${t.lv(2)}</button>` +
    `<button type="button" data-lv="4" aria-pressed="${tone.levels === 4}" ${S.media === "cd" ? "" : `disabled title="${t.lv4}"`}>${t.lv(4)}</button></div></div>` +
    (S.media === "cd" ? "" : `<p class="note quiet">${t.lv4}</p>`) +
    `<label class="chk"><input type="checkbox" data-k="lin" ${tone.lin ? "checked" : ""}>${t.lin}</label>` +
    (S.media === "bd" ? `<label class="chk"><input type="checkbox" data-k="inv" ${tone.inv ? "checked" : ""}>${t.inv}</label>` : "") +
    `<details class="more"><summary>${t.more}</summary><div>` +
    `<div class="ctl-line"><button class="sbtn" type="button" data-a="auto">${tone.auto ? t.autoOff : t.auto}</button><span class="note quiet">${tone.auto ? t.autoOn(...tone.auto) : ""}</span></div>` +
    slider("contrast", t.contrast, -100, 100, 1, tone.contrast) + slider("hi", t.hi, -100, 100, 1, tone.hi) + slider("sh", t.sh, -100, 100, 1, tone.sh) +
    `<div class="ctl-line"><label for="dmode">${t.mode}</label><select class="sel" id="dmode" data-k="mode">` +
    Object.entries(t.modes).map(([k, v]) => `<option value="${k}" ${tone.mode === k ? "selected" : ""}>${v}</option>`).join("") + `</select></div>` +
    `</div></details><button class="sbtn" type="button" data-a="reset">${t.reset}</button></section>`;

  // PRO: colour
  const sc = S.scene;
  const colourS = `<section class="pro-only"><h3><span class="grow">${t.colour}</span><span class="ev">${t.colourEv}</span></h3>` +
    `<p class="note">${t.colourNote}</p>` +
    `<div class="ctl-line"><label for="preset">${t.preset}</label><select class="sel" id="preset" data-k="preset">` +
    Object.entries(t.presets).map(([k, v]) => `<option value="${k}" ${sc.preset === k ? "selected" : ""}>${v}</option>`).join("") + `</select></div>` +
    sceneSVG() +
    `<p class="note quiet">${t.sceneHint}</p>` +
    `<div class="xyz"><span>${t.phone}</span>${sc.cam.map((v, i) => `<input type="number" step="5" data-cam="${i}" value="${Math.round(i === 1 ? -v : v)}" aria-label="${t.phone} ${"XYZ"[i]}">`).join("")}</div>` +
    `<div class="xyz"><span>${t.lamp}</span>${lampPos().map((v, i) => `<input type="number" step="5" data-lamp="${i}" value="${Math.round(i === 1 ? -v : v)}" aria-label="${t.lamp} ${"XYZ"[i]}" ${sc.follows ? "disabled" : ""}>`).join("")}</div>` +
    `<div><p class="note" style="margin-bottom:8px">${t.target}</p>` +
    (L?.kind === "image" ? `<div class="sw-row">${["none", "red", "green", "blue", "purple"].map((c) =>
      `<button class="swatch ${c === "none" ? "none" : ""}" type="button" data-colour="${c}" aria-pressed="${L.colour === c}" aria-label="${t.colours[c]}" title="${t.colours[c]}" style="${c === "none" ? "" : `background:${{ red: "#d2453b", green: "#4f9a52", blue: "#3f5fcf", purple: "linear-gradient(135deg,#d2453b 50%,#3f5fcf 50%)" }[c]}`}"></button>`).join("")}</div>`
      : `<p class="note quiet">${t.pickLayer}</p>`) + `</div>` +
    `<label class="chk"><input type="checkbox" data-k="lookColour" ${S.lookColour ? "checked" : ""}>${t.look}</label>` +
    `<p class="note quiet">${t.chartNote}</p></section>`;

  // PRO: effects
  const fxS = `<section class="pro-only"><h3><span class="grow">${t.fx}</span><span class="ev">${t.fxEv}</span></h3><p class="note">${t.fxNote}</p>` +
    (L?.kind === "fx" ? `<div class="ctl-line"><span>${t.fxKinds[L.fxKind][0]}</span><button class="ib" type="button" data-a="swap" title="${t.swap}" aria-label="${t.swap}">${I.swap}</button></div>` +
      `<div class="row2"><div class="ctl"><label>${t.fxY1}</label><input class="num" type="number" step="1" data-fx="y1" value="${L.y1}"></div>` +
      `<div class="ctl"><label>${t.fxY2}</label><input class="num" type="number" step="1" data-fx="y2" value="${L.y2}"></div></div>` : "") +
    `<p class="note quiet">${t.fxAdd}</p><div class="fx-add">` +
    Object.entries(t.fxKinds).map(([k, [name, note]]) => `<button class="fx-opt" type="button" data-fx-add="${k}"><b>${name}</b><span>${note}</span></button>`).join("") + `</div></section>`;

  // PRO: engraving grid
  const um = Math.round(S.cell * 1000), cells = Math.round(GRID_MM / S.cell);
  const precS = `<section class="pro-only"><h3><span class="grow">${t.precision}</span><span class="ev">${t.precEv}</span></h3>` +
    `<div class="seg" role="group" aria-label="${t.precision}">${[20, 10, 5].map((u) => `<button type="button" data-um="${u}" aria-pressed="${um === u}">${t.prec[u]}</button>`).join("")}</div>` +
    `<p class="note">${t.precNote[um]}</p>` + (um < 20 ? `<p class="note quiet">${t.precCost(cells)}</p>` : "") +
    `<label class="chk"><input type="checkbox" data-k="loupe" ${S.loupe ? "checked" : ""}>${t.loupe}</label></section>`;

  W.right.innerHTML = proSw + toneS + `<p class="note quiet pro-only" style="padding:0 0 12px">${t.proNote}</p>` + colourS + fxS + precS;
  W.ws.classList.toggle("pro-on", S.pro);
  bindScene();
  updateTilt();
}
function rightInput(e) {
  const el = e.target, k = el.dataset.k;
  if (el.dataset.cam !== undefined || el.dataset.lamp !== undefined) {
    const i = Number(el.dataset.cam ?? el.dataset.lamp), v = Number(el.value) * (i === 1 ? -1 : 1);
    if (!Number.isFinite(v)) return;
    if (el.dataset.cam !== undefined) S.scene.cam[i] = i === 2 ? Math.max(40, v) : v;
    else { S.scene.lamp = lampPos(); S.scene.lamp[i] = i === 2 ? Math.max(40, v) : v; }
    if (i === 1 && el.dataset.cam !== undefined) S.lookY = -S.scene.cam[1];
    drawScene(); updateTilt(); draw();
    return;
  }
  if (el.dataset.fx) {
    const L = sel(), v = Number(el.value);
    if (!L || !Number.isFinite(v)) return;
    checkpoint(`fx-${el.dataset.fx}-${L.id}`);
    L[el.dataset.fx] = v; changed();
    return;
  }
  if (!k) return;
  if (k === "lookColour") { S.lookColour = el.checked; updateTilt(); draw(); return; }
  if (k === "loupe") { S.loupe = el.checked; W.loupe.classList.toggle("on", S.loupe); return; }
  if (k === "preset") { setPreset(el.value); return; }
  const v = el.type === "checkbox" ? el.checked : el.tagName === "SELECT" ? el.value : Number(el.value);
  S.tone[k] = v;
  // keep the number box and the slider of one control together
  for (const twin of W.right.querySelectorAll(`[data-k="${k}"]`)) if (twin !== el && twin.type !== "checkbox") twin.value = v;
  S.dirty = true; W.dirty.classList.add("on");
  queueCompose();
}
function rightClick(e) {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.a === "pro") { S.pro = !S.pro; buildRight(); draw(); return; }
  if (b.dataset.lv) { S.tone.levels = Number(b.dataset.lv); buildRight(); queueCompose(); return; }
  if (b.dataset.a === "reset") { S.tone = { ...DEFAULT_TONE }; buildRight(); queueCompose(); return; }
  if (b.dataset.a === "auto") {
    if (S.tone.auto) S.tone.auto = null;
    else {
      const { g, pw, ph } = rasterise(-60, -60, 60, 60, 4);
      const r = autoLevels(g.getImageData(0, 0, pw, ph));
      S.tone.auto = [r.blackPoint, r.whitePoint];
    }
    buildRight(); queueCompose(); return;
  }
  if (b.dataset.colour) { const L = sel(); if (!L) return; checkpoint(); L.colour = b.dataset.colour; if (L.colour !== "none") S.lookColour = true; buildRight(); changed(); return; }
  if (b.dataset.fxAdd) { addEffect(b.dataset.fxAdd); return; }
  if (b.dataset.a === "swap") { const L = sel(); checkpoint(); [L.y1, L.y2] = [L.y2, L.y1]; buildRight(); changed(); return; }
  if (b.dataset.um) {
    const before = zoomPct();
    S.cell = Number(b.dataset.um) / 1000;
    void before;
    buildRight(); draw(); queueCompose(); return;
  }
}
function setPreset(p) {
  S.scene.preset = p;
  if (p === "design") { S.scene.cam = [0, -70, 330]; S.scene.follows = true; }
  if (p === "flash") { S.scene.cam = [0, 0, 300]; S.scene.follows = true; }
  if (p === "lamp") { S.scene.cam = [0, -70, 330]; S.scene.follows = false; S.scene.lamp = [-260, -220, 420]; }
  S.lookY = -S.scene.cam[1];
  buildRight(); draw();
}

// the little scene: a disc on a table, the phone and the lamp, true isometric like the home page
const SK = 0.3, SO = [150, 168];
const proj = ([x, y, z]) => [SO[0] + (x - y) * 0.866 * SK, SO[1] + (x + y) * 0.5 * SK - z * SK];
function sceneSVG() { return `<svg class="scene" viewBox="0 0 300 196" role="img" aria-label="${T().sceneHint}"></svg>`; }
function drawScene() {
  const svg = W?.right.querySelector(".scene");
  if (!svg) return;
  const t = T(), cam = S.scene.cam, lamp = lampPos();
  const line = (a, b, cls) => { const [x1, y1] = proj(a), [x2, y2] = proj(b); return `<line class="${cls}" x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}"/>`; };
  let s = "";
  for (let k = -300; k <= 300; k += 100) { s += line([k, -300, 0], [k, 300, 0], "flr") + line([-300, k, 0], [300, k, 0], "flr"); }
  const [dx, dy] = proj([0, 0, 0]);
  s += `<ellipse class="disc" cx="${dx}" cy="${dy}" rx="${(60 * SK * 1.2247).toFixed(1)}" ry="${(60 * SK * 0.7071).toFixed(1)}"/>`;
  s += `<ellipse class="hole" cx="${dx}" cy="${dy}" rx="${(7.5 * SK * 1.2247).toFixed(1)}" ry="${(7.5 * SK * 0.7071).toFixed(1)}"/>`;
  const [ux, uy] = proj([0, -60, 0]);
  s += `<circle class="up" cx="${ux.toFixed(1)}" cy="${uy.toFixed(1)}" r="2.6"/>`;
  for (const p of [cam, lamp]) {
    s += line([p[0], p[1], 0], p, "stem");
    const [fx, fy] = proj([p[0], p[1], 0]);
    s += `<circle class="dot" cx="${fx.toFixed(1)}" cy="${fy.toFixed(1)}" r="2"/>`;
    s += line(p, [0, 0, 0], "ray");
  }
  const [cx, cy] = proj(cam), [lx, ly] = proj(lamp);
  s += `<g class="grab" data-drag="cam" transform="translate(${cx.toFixed(1)} ${cy.toFixed(1)})"><rect class="body" x="-7" y="-12" width="14" height="24" rx="2"/><circle class="lens" cx="0" cy="-6" r="2.4"/><text x="11" y="-8">${t.phone}</text></g>`;
  s += `<g class="grab" data-drag="lamp" transform="translate(${lx.toFixed(1)} ${ly.toFixed(1)})" style="${S.scene.follows ? "opacity:.6;pointer-events:none" : ""}"><circle class="bulb" r="6"/><text x="9" y="${S.scene.follows ? 14 : -8}">${t.lamp}</text></g>`;
  svg.innerHTML = s;
  // the number boxes follow
  for (const inp of W.right.querySelectorAll("[data-cam]")) if (document.activeElement !== inp) { const i = Number(inp.dataset.cam); inp.value = Math.round(i === 1 ? -cam[i] : cam[i]); }
  for (const inp of W.right.querySelectorAll("[data-lamp]")) if (document.activeElement !== inp) { const i = Number(inp.dataset.lamp); inp.value = Math.round(i === 1 ? -lamp[i] : lamp[i]); }
}
function bindScene() {
  const svg = W.right.querySelector(".scene");
  if (!svg) return;
  drawScene();
  let d = null;
  svg.addEventListener("pointerdown", (e) => {
    const g = e.target.closest("[data-drag]");
    if (!g) return;
    svg.setPointerCapture(e.pointerId);
    const which = g.dataset.drag, p = which === "cam" ? S.scene.cam : (S.scene.lamp = lampPos());
    d = { which, p, y0: e.clientY, z0: p[2] };
  });
  svg.addEventListener("pointermove", (e) => {
    if (!d) return;
    const r = svg.getBoundingClientRect(), k = 300 / r.width;
    const sx = (e.clientX - r.left) * k, sy = (e.clientY - r.top) * k;
    if (e.shiftKey) d.p[2] = Math.max(40, Math.min(900, d.z0 - (e.clientY - d.y0) * k / SK));
    else {
      const A = (sx - SO[0]) / (0.866 * SK), B = (sy - SO[1] + d.p[2] * SK) / (0.5 * SK);
      d.p[0] = Math.round((A + B) / 2); d.p[1] = Math.round((B - A) / 2);
    }
    if (d.which === "cam") S.lookY = -S.scene.cam[1];
    drawScene(); updateTilt(); draw();
  });
  const end = () => { d = null; };
  svg.addEventListener("pointerup", end); svg.addEventListener("pointercancel", end);
}

// the "seen from" strip under the canvas: move the phone along the top-bottom line
function updateTilt() {
  if (!W) return;
  const t = T(), show = S.pro && (S.layers.some((L) => L.kind === "fx") || (S.lookColour && imageLayers().some((L) => L.colour !== "none")));
  W.tilt.classList.toggle("on", show);
  if (!show) { stopPlay(); return; }
  const r = W.tilt.querySelector("input"), o = W.tilt.querySelector("output"), b = W.tilt.querySelector("button");
  W.tilt.querySelector(".lbl").textContent = t.look2;
  r.value = S.lookY;
  o.textContent = t.phoneY(Math.round(S.lookY)) + (Math.round(S.lookY) === Math.round(-S.scene.cam[1]) ? t.design : "");
  b.textContent = S.playing ? t.stop : t.play;
}
function stopPlay() { clearInterval(S?.playing); if (S) S.playing = 0; }
function togglePlay() {
  if (S.playing) { stopPlay(); updateTilt(); return; }
  let dir = 1, n = 0;
  S.playing = setInterval(() => {
    S.lookY += dir * 1.5;
    if (S.lookY > 115 || S.lookY < 45) { dir = -dir; n++; }
    if (n >= 6) stopPlay();
    updateTilt(); draw();
  }, 60);
  updateTilt();
}

// ---------------------------------------------------------------- saving and opening a project
// One JSON file holds everything: each picture as the working copy (with what the selection tool
// removed) and, when it came from a file, the original file too, so export can use full size.
const FILE_KIND = "disc-probe design", FILE_VERSION = 1, FILE_EXT = ".discdesign";
const blobURL = (blob) => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = no; r.readAsDataURL(blob); });
const canvasBlob = (c) => new Promise((ok) => c.toBlob(ok, "image/png"));
async function projectText() {
  const layers = [];
  for (const L of S.layers) {
    const e = { kind: L.kind, name: L.name, x: L.x, y: L.y, width: L.width, rot: L.rot, opacity: L.opacity, visible: L.visible, locked: L.locked };
    if (L.kind === "image") {
      Object.assign(e, { colour: L.colour, w: L.w, h: L.h, alphaEdited: !!L.alphaEdited, picture: await blobURL(await canvasBlob(L.src)) });
      if (L.file) e.original = await blobURL(L.file);
    } else Object.assign(e, { fxKind: L.fxKind, height: L.height, y1: L.y1, y2: L.y2 });
    layers.push(e);
  }
  return JSON.stringify({
    format: FILE_KIND, version: FILE_VERSION, media: S.media, disc: S.item?.name ?? null, geo: S.geo ?? null,
    tone: S.tone, files: S.files, pro: S.pro, cell: S.cell, scene: S.scene, lookColour: S.lookColour, lookY: S.lookY, layers,
  });
}
const baseName = (n) => n.replace(/\.discdesign$/i, "").replace(/\.json$/i, "");
async function saveProject(as = false) {
  const t = T();
  if (!S.layers.length) { toast(t.exp.empty); return false; }
  const text = await projectText();
  let name = (S.name ?? t.untitled) + FILE_EXT;
  if (window.showSaveFilePicker) {
    try {
      if (!S.handle || as) S.handle = await showSaveFilePicker({ suggestedName: name, types: [{ description: "disc-probe", accept: { "application/json": [FILE_EXT] } }] });
      const w = await S.handle.createWritable();
      await w.write(text); await w.close();
      name = S.handle.name;
    } catch (e) { if (e?.name !== "AbortError") toast(String(e?.message ?? e)); return false; }
  } else {                                   // no file handles: download a copy
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([text], { type: "application/json" })), download: name });
    a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }
  S.name = baseName(name); S.dirty = false;
  W.dirty.classList.remove("on"); W.pname.textContent = S.name;
  toast(t.saved(name));
  return true;
}
async function openProject(file, handle = null) {
  const t = T();
  let data;
  try { data = JSON.parse(await file.text()); } catch { toast(t.notProject(file.name)); return; }
  if (data?.format !== FILE_KIND || !Array.isArray(data.layers)) { toast(t.notProject(file.name)); return; }
  if (data.version > FILE_VERSION) { toast(t.newer(file.name)); return; }
  const layers = [];
  for (const e of data.layers) {
    const base = { id: nextId++, kind: e.kind === "fx" ? "fx" : "image", name: String(e.name ?? ""), x: +e.x || 0, y: +e.y || 0,
      width: Math.max(1, +e.width || 1), rot: +e.rot || 0, opacity: Math.min(1, Math.max(0, e.opacity ?? 1)), visible: e.visible !== false, locked: !!e.locked };
    if (base.kind === "fx") {
      if (!["flow", "ox", "merge", "sync"].includes(e.fxKind)) continue;
      layers.push({ ...base, fxKind: e.fxKind, height: Math.max(1, +e.height || 1), y1: +e.y1 || 70, y2: +e.y2 || 70 });
      continue;
    }
    try {
      const bmp = await createImageBitmap(await (await fetch(e.picture)).blob());
      const c = document.createElement("canvas");
      c.width = bmp.width; c.height = bmp.height;
      const g = c.getContext("2d", { willReadFrequently: true });
      g.drawImage(bmp, 0, 0); bmp.close?.();
      const L = { ...base, w: c.width, h: c.height, colour: e.colour ?? "none", alphaEdited: !!e.alphaEdited, px: g.getImageData(0, 0, c.width, c.height), src: c, version: 1 };
      if (typeof e.original === "string" && e.original.startsWith("data:image/")) L.file = await (await fetch(e.original)).blob();
      layers.push(L);
    } catch { /* a picture that can't be read is left out */ }
  }
  checkpoint();
  S.layers = layers.slice(0, 16);
  S.selected = null;
  for (const k of ["files", "pro", "lookColour"]) if (k in data) S[k] = data[k];
  if (data.tone) S.tone = { ...DEFAULT_TONE, ...data.tone };
  if (data.scene) S.scene = { ...S.scene, ...data.scene };
  if ([0.02, 0.01, 0.005].includes(data.cell)) S.cell = data.cell;
  if (typeof data.geo === "string" && data.media === S.media) S.geo = data.geo;      // checked against the catalogue at export
  if (Number.isFinite(data.lookY)) S.lookY = data.lookY;
  S.name = baseName(file.name); S.handle = handle;
  changed();
  S.dirty = false; W.dirty.classList.remove("on");
  W.ws.classList.toggle("pro-on", S.pro);
  W.pname.textContent = S.name;
  buildLeft(); buildRight(); updateTilt();
  toast(data.media && data.media !== S.media ? t.otherMedia(data.media.toUpperCase(), S.media.toUpperCase()) : t.opened(file.name));
}
async function pickProject() {
  if (window.showOpenFilePicker) {
    try {
      const [h] = await showOpenFilePicker({ types: [{ description: "disc-probe", accept: { "application/json": [FILE_EXT, ".json"] } }] });
      await openProject(await h.getFile(), h);
    } catch (e) { if (e?.name !== "AbortError") toast(String(e?.message ?? e)); }
  } else W.proj.click();
}

// ---------------------------------------------------------------- the whole disc, for the burn file
// The design as `image --design-npy` reads it: one bit per cell (6000², 12000² or 24000² cells of 20, 10
// or 5 µm across the 120 mm disc), row by row, dark = 1,
// seen from the data side like the canvas. Drawn from the original pictures and toned like the canvas.
const GRID = 6000, GRID_MM = 120;
export async function designBits(onStage = () => {}, { band: bandRows } = {}) {
  const t = T().exp;
  if (!S || !imageLayers().some((L) => L.visible)) throw new Error(t.empty);
  const side = Math.round(GRID_MM / S.cell);           // 6000, 12000 or 24000 cells across
  if (![6000, 12000, 24000].includes(side)) throw new Error(api.lang() === "zh" ? "请选择 20、10 或 5 µm 格子。" : "Choose a 20, 10 or 5 µm grid.");
  if (S.tone.levels === 4 && S.media === "cd") throw new Error(t.four);
  onStage(t.drawing);
  await new Promise((r) => requestAnimationFrame(() => setTimeout(r, 0)));   // let the stage show first
  // Keep the DOM canvas rasteriser: converting working canvases to bitmaps
  // or worker canvases changes sampled colours (and therefore diffused bits).
  // Tone, dither and packing own the transferred pixels entirely in the worker.
  const layers = imageLayers().map(L => ({ ...L })), originals = new Map();
  const { adjustments, output } = toneOptions();
  const [p0, p1] = pictureRange(), r0 = S.media === "cd" ? Math.max(p0, 26) : p0, rMax = Math.min(58, p1);
  for (const L of layers) if (L.visible && L.file) {
    try { originals.set(L, await createImageBitmap(L.file)); } catch { /* the working copy then */ }
  }
  let worker;
  try {
    // One band of rows at a time: a whole 5 µm disc (24000²) is more than a canvas can hold. Every band
    // but the last has one row more, where the dithering runs on into the next band (processing.mjs).
    // 20 µm stays one piece, as it was burned and checked: drawn in bands the browser resamples the picture a
    // little differently, and dithering turns that into a different (equally good) pattern.
    const ppm = side / GRID_MM, band = bandRows ?? (side <= GRID ? side : Math.max(64, Math.floor(12e6 / side)));   // bandRows: for checks
    worker = processingWorker();
    await worker.run({ kind: "export-begin", side, r0, rMax, adjustments, output });
    let pending = null;
    for (let y0 = 0; y0 < side; y0 += band) {
      const rows = Math.min(band, side - y0), more = y0 + rows < side ? 1 : 0;
      const { g } = rasterise(-GRID_MM / 2, -GRID_MM / 2 + y0 / ppm, GRID_MM / 2, -GRID_MM / 2 + (y0 + rows + more) / ppm,
        ppm, true, originals, layers);
      const image = g.getImageData(0, 0, side, rows + more);
      // Rasterize the next band while the worker processes this one. Keep at
      // most one band waiting and preserve band order for diffusion carry.
      if (pending) await pending;
      pending = worker.run({ kind: "export-strip", image, y0, rows }, [image.data.buffer]);
      // Attach a handler now, even if drawing the next band delays our await.
      pending.catch(() => {});
      if (side > GRID) onStage(`${t.drawing} ${Math.floor((100 * (y0 + rows)) / side)}%`);
    }
    await pending;
    return await worker.run({ kind: "export-end" });
  } finally {
    worker?.close();
    for (const bitmap of originals.values()) bitmap.close();
  }
}
// Draw the design, hand it to the back end and run `image`; resolves with the ISO's path and size.
// onProgress({ stage, fraction }) — fraction is null while unknown.
export async function makeBurnFile(onProgress = () => {}, { signal } = {}) {
  const t = T().exp;
  const stop = () => { if (signal?.aborted) throw new DOMException("cancelled", "AbortError"); };
  let state;
  try { const r = await fetch(`/api/state?media=${S.media}`); if (!r.ok) throw 0; state = await r.json(); } catch { throw new Error(t.noBackend); }
  const geoPath = projectGeo(state);
  if (!geoPath) throw new Error(t.noGeo);
  const { bits, rMax } = await designBits((stage) => onProgress({ stage, fraction: null }));
  stop();
  onProgress({ stage: t.sending, fraction: null });
  const up = await fetch("/api/design", { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: bits });
  const saved = await up.json().catch(() => ({}));
  if (!up.ok) throw new Error(saved.error ?? t.failed);
  stop();
  const stamp = new Date().toISOString().replace(/\D/g, "").slice(0, 14);
  const output = `iso/${(S.name ?? "design").replace(/[^\w-]+/g, "-").slice(0, 40) || "design"}-${stamp}.iso`;
  onProgress({ stage: t.making, fraction: 0 });
  const run = await fetch("/api/run", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "image", media: S.media, args: { geo: geoPath, design_npy: saved.design_npy, output, r_max: rMax } }),
  });
  const job = await run.json().catch(() => ({}));
  if (!run.ok) throw new Error(job.error ?? t.failed);
  const exit = await new Promise((resolve, reject) => {
    const es = new EventSource("/api/events");
    signal?.addEventListener("abort", () => {          // stop the back end's job too
      es.close();
      fetch(`/api/jobs/${job.job}/cancel`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).catch(() => {});
      reject(new DOMException("cancelled", "AbortError"));
    }, { once: true });
    const mine = (e) => { const d = JSON.parse(e.data); return d.job === job.job ? d : null; };
    es.addEventListener("progress", (e) => { const d = mine(e); if (d) onProgress({ stage: t.making, fraction: d.fraction ?? null }); });
    es.addEventListener("done", (e) => { const d = mine(e); if (d) { es.close(); resolve(d.exit); } });
  });
  if (exit !== 0) throw new Error(t.failed);
  const info = await (await fetch(`/api/iso?path=${encodeURIComponent(output)}`)).json();
  S.geo = geoPath;                                     // the project keeps the geometry it was made with
  return { path: info.path ?? output, bytes: info.bytes, sectors: info.sectors, job: job.job, geo: geoPath };
}
// Which measured geometry this project's burn file is made from: the one it was made with before (kept in the
// project file), else its disc batch's own measurement (the shelf entry), else the newest complete one for the
// disc type. The last is a guess about the batch, so it is only the fallback.
function projectGeo(state) {
  const known = new Set((state.catalogue?.[S.media] ?? []).filter((x) => ["good", "usable"].includes(x.s)).map((x) => x.geo));
  if (S.geo && known.has(S.geo)) return S.geo;
  if (S.item?.geo && ["good", "usable"].includes(S.item.s)) return S.item.geo;
  const latest = state.steps?.find((x) => x.id === "geo");
  return latest?.done && latest.result ? latest.result : null;
}

// ---------------------------------------------------------------- building the page
function build() {
  const t = T();
  const css = document.createElement("link");
  css.rel = "stylesheet"; css.href = new URL("./design.css", import.meta.url).href;
  document.head.append(css);
  const ws = document.createElement("div");
  ws.className = "ws";
  ws.innerHTML = `<div class="ws-title"><b class="pname"></b><button class="sub" type="button"></button><span class="dirty" aria-hidden="true"></span>` +
    `<span class="filebtns"><button class="sbtn" type="button" data-a="open"></button><button class="sbtn" type="button" data-a="save"></button></span></div>` +
    `<aside class="col col-l"></aside><aside class="col col-r"></aside>` +
    `<div class="cv"><canvas class="main"></canvas>` +
    `<div class="tools-v" role="toolbar"></div>` +
    `<div class="seg viewsw" role="group"><button type="button" data-v="proj"></button><button type="button" data-v="orig"></button></div>` +
    `<p class="cv-note warn" hidden></p>` +
    `<div class="empty-c"><p></p><div class="row"><button class="sbtn" type="button" data-a="import"></button><button class="sbtn" type="button" data-a="sample"></button></div></div>` +
    `<div class="fbar" hidden></div>` +
    `<div class="tilt"><span class="lbl"></span><input class="rng" type="range" min="40" max="120" step="1"><output></output><button class="sbtn" type="button"></button></div>` +
    `<div class="loupe"><canvas></canvas><small></small></div>` +
    `<button class="zoomr" type="button"></button><div class="dropzone"></div></div>` +
    `<input type="file" accept="image/png,image/jpeg,image/webp,image/bmp" multiple hidden class="f-img"><input type="file" webkitdirectory multiple hidden class="f-dir">` +
    `<input type="file" accept="${FILE_EXT},.json,application/json" hidden class="f-proj">`;
  document.body.append(ws);
  const q = (s) => ws.querySelector(s);
  W = {
    ws, left: q(".col-l"), right: q(".col-r"), cv: q(".cv"), canvas: q("canvas.main"), tools: q(".tools-v"), view: q(".viewsw"),
    note: q(".cv-note"), empty: q(".empty-c"), bar: q(".fbar"), tilt: q(".tilt"), loupe: q(".loupe"), zoom: q(".zoomr"),
    drop: q(".dropzone"), file: q(".f-img"), folder: q(".f-dir"), dirty: q(".dirty"), pname: q(".pname"), sub: q(".ws-title .sub"), proj: q(".f-proj"), filebtns: q(".filebtns"),
  };
  // canvas input
  const cvs = W.canvas;
  cvs.addEventListener("pointerdown", onDown);
  cvs.addEventListener("pointermove", onMove);
  cvs.addEventListener("pointerup", onUp);
  cvs.addEventListener("pointercancel", onUp);
  cvs.addEventListener("pointerleave", () => W.loupe.classList.remove("on"));
  cvs.addEventListener("pointerenter", () => W.loupe.classList.toggle("on", !!S?.loupe));
  cvs.addEventListener("wheel", onWheel, { passive: false });
  addEventListener("keydown", onKey);
  addEventListener("keyup", onKeyUp);
  W.zoom.addEventListener("click", () => { if (zoomPct() >= 99) fit(); else zoomAt(1 / S.cell / V.s, V.w / 2, V.h / 2); });
  W.view.addEventListener("click", (e) => {
    const b = e.target.closest("[data-v]");
    if (!b) return;
    S.view = b.dataset.v;
    for (const x of W.view.children) x.setAttribute("aria-pressed", String(x.dataset.v === S.view));
    const L = sel(); if (L?.seeds?.length) runSelection(L);
    draw();
  });
  W.empty.addEventListener("click", (e) => {
    const a = e.target.closest("[data-a]")?.dataset.a;
    if (a === "import") W.file.click();
    if (a === "sample") sampleLayer();
  });
  W.bar.addEventListener("input", barInput);
  W.bar.addEventListener("click", barClick);
  W.bar.addEventListener("keydown", (e) => e.stopPropagation());
  W.left.addEventListener("click", leftClick);
  W.left.addEventListener("dblclick", leftDbl);
  for (const ev of ["dragstart", "dragover", "drop", "dragend"]) W.left.addEventListener(ev, leftDrag);
  W.right.addEventListener("input", rightInput);
  W.right.addEventListener("change", (e) => { if (e.target.tagName === "SELECT") rightInput(e); });
  W.right.addEventListener("click", rightClick);
  W.tilt.querySelector("input").addEventListener("input", (e) => { S.lookY = Number(e.target.value); updateTilt(); draw(); });
  W.tilt.querySelector("button").addEventListener("click", togglePlay);
  W.file.addEventListener("change", () => { importFiles([...W.file.files]); W.file.value = ""; });
  W.proj.addEventListener("change", () => { const f = W.proj.files[0]; if (f) openProject(f); W.proj.value = ""; });
  W.filebtns.addEventListener("click", (e) => {
    const a = e.target.closest("[data-a]")?.dataset.a;
    if (a === "open") pickProject();
    if (a === "save") saveProject(e.shiftKey);
  });
  // closing or reloading the page loses what isn't saved
  addEventListener("beforeunload", (e) => { if ([...projects.values()].some((p) => p.dirty && p.layers.length)) { e.preventDefault(); e.returnValue = ""; } });
  W.folder.addEventListener("change", () => {
    const fs = [...W.folder.files];
    if (fs.length) { S.files = { count: fs.length, bytes: fs.reduce((a, f) => a + f.size, 0), where: S.files?.where ?? "inner" }; changed(); buildLeft(); }
    W.folder.value = "";
  });
  // drop pictures anywhere on the page
  let depth = 0;
  addEventListener("dragenter", (e) => { if (!isOn() || !e.dataTransfer?.types.includes("Files")) return; depth++; W.drop.classList.add("on"); });
  addEventListener("dragleave", () => { if (!isOn()) return; depth = Math.max(0, depth - 1); if (!depth) W.drop.classList.remove("on"); });
  addEventListener("dragover", (e) => { if (isOn() && e.dataTransfer?.types.includes("Files")) e.preventDefault(); });
  addEventListener("drop", (e) => {
    if (!isOn() || !e.dataTransfer?.files.length) return;
    e.preventDefault(); depth = 0; W.drop.classList.remove("on");
    const files = [...e.dataTransfer.files], proj = files.find((f) => /\.(discdesign|json)$/i.test(f.name));
    if (proj) openProject(proj); else importFiles(files);
  });
  new ResizeObserver(resize).observe(W.cv);
  $("back").addEventListener("click", () => { if (isOn()) leave(); });
  $("next").addEventListener("click", () => { if (isOn() && imageLayers().length) toPreview(); });
  addEventListener("dp-lang", () => { if (isOn()) words(); });
  new MutationObserver(() => { if (isOn()) { draw(); drawScene(); } }).observe(root, { attributes: true, attributeFilter: ["data-theme"] });
}
function resize() {
  const r = W.cv.getBoundingClientRect(), first = !V.w;
  const ox = V.cx - V.w / 2, oy = V.cy - V.h / 2;
  V.w = r.width; V.h = r.height; V.dpr = devicePixelRatio || 1;
  W.canvas.width = Math.round(V.w * V.dpr); W.canvas.height = Math.round(V.h * V.dpr);
  if (first) fit();
  else { V.cx = V.w / 2 + ox; V.cy = V.h / 2 + oy; draw(); queueCompose(); }
}
// all the words, in the current language
function words() {
  const t = T();
  W.pname.textContent = S.name ?? t.untitled;
  W.dirty.classList.toggle("on", S.dirty);
  W.dirty.title = S.dirty ? t.unsaved : "";
  const [bo, bs] = W.filebtns.children;
  bo.innerHTML = `${I.open}<span>${t.open}</span>`; bo.title = `${t.open} (Ctrl+O)`;
  bs.innerHTML = `${I.save}<span>${t.save}</span>`; bs.title = `${t.save} (Ctrl+S) · ${t.saveAs} (Ctrl+Shift+S)`;
  W.sub.textContent = api.T().brand?.(S.item.name) ?? S.item.name;
  W.sub.title = t.changeDiscs;
  W.sub.onclick = chooseBatch;
  W.tools.innerHTML = ["move", "wand", "pan"].map((k) => `<button class="tb" type="button" data-tool="${k}" aria-label="${t.tools[k]}" title="${t.tools[k]}" aria-pressed="${S.tool === k}">${I[k]}</button>`).join("");
  W.tools.onclick = (e) => { const b = e.target.closest("[data-tool]"); if (b) setTool(b.dataset.tool); };
  const [p, o] = W.view.children;
  p.textContent = t.proj; o.textContent = t.orig;
  W.view.setAttribute("aria-label", t.viewAria);
  for (const x of W.view.children) x.setAttribute("aria-pressed", String(x.dataset.v === S.view));
  W.zoom.setAttribute("aria-label", t.zoomAria); W.zoom.title = `${t.fit} / ${t.hundred} (0 / 1)`;
  W.empty.querySelector("p").textContent = t.empty;
  W.empty.querySelector('[data-a="import"]').innerHTML = `${I.image}${t.import}`;
  W.empty.querySelector('[data-a="sample"]').textContent = t.sample;
  W.drop.textContent = t.drop;
  $("next-text").textContent = t.next;
  if (W.bar) W.bar.dataset.lang = "";
  buildLeft(); buildRight(); draw();
}

let toastT = 0, toastEl = null;
function toast(text) {
  if (!toastEl) { toastEl = document.createElement("div"); toastEl.className = "toast"; toastEl.setAttribute("role", "status"); document.body.append(toastEl); }
  toastEl.textContent = text; toastEl.classList.add("on");
  clearTimeout(toastT); toastT = setTimeout(() => toastEl.classList.remove("on"), 2600);
}

// ---------------------------------------------------------------- coming in, going out
// Forward always moves to the right, back to the left (DESIGN.md): going in, the chosen disc slides
// off the shelf to the right and the canvas disc comes in from the left; going out, the canvas disc
// leaves to the left and the shelf disc comes back from the right. Any input skips it.
function flight(fromRect, toCircle, back, done) {
  const D = toCircle.d, shift = Math.min(innerWidth * 0.3, 460);
  const flat = `translate(${toCircle.x - D / 2}px, ${toCircle.y - D / 2}px)`;
  let iso = null;
  if (fromRect?.width) {
    const k = fromRect.width / (1.2247 * D);
    iso = `translate(${fromRect.left + fromRect.width / 2 - D / 2}px, ${fromRect.top + fromRect.height * 0.3 - D / 2}px) matrix(${0.866 * k}, ${0.5 * k}, ${-0.866 * k}, ${0.5 * k}, 0, 0)`;
  }
  const by = (dx, t) => `translate(${dx}px, 0px) ${t}`;
  // each leg: [from, to, fading out?]
  const legs = (back
    ? [[flat, by(-shift, flat), true], iso && [by(shift, iso), iso, false]]
    : [iso && [iso, by(shift, iso), true], [by(-shift, flat), flat, false]]).filter(Boolean);
  const els = [], anims = [];
  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    removeEventListener("pointerdown", finish, true); removeEventListener("keydown", finish, true);
    for (const a of anims) a.cancel();
    for (const el of els) el.remove();
    done?.();
  };
  if (api.reduce) { finish(); return; }
  let at = 0;
  for (const [a, b, out] of legs) {
    const el = document.createElement("div");
    el.className = "dflyer";
    el.style.width = el.style.height = `${D}px`;
    el.style.background = `radial-gradient(circle, transparent 0 12.5%, var(--face-2) 12.5% 28%, var(--face) 28% 100%)`;
    el.style.boxShadow = "0 0 0 1px var(--rule-strong)";
    el.style.transition = "none";
    el.style.transform = a; el.style.opacity = out ? "1" : "0";
    document.body.append(el);
    els.push(el);
    const anim = el.animate([{ transform: a, opacity: out ? 1 : 0 }, { transform: b, opacity: out ? 0 : 1 }],
      { duration: 300, delay: at, easing: out ? "cubic-bezier(.5,0,.75,0)" : "cubic-bezier(.2,.8,.2,1)", fill: "both" });
    anims.push(anim);
    at += out ? 200 : 300;                  // the second disc starts while the first is still fading
  }
  anims.at(-1).finished.then(finish, () => {});
  addEventListener("pointerdown", finish, true); addEventListener("keydown", finish, true);
}

// start(api): the shelf's way in (the disc in focus, its plan). Options:
//   plan: open this plan; newPlan: a new plan on the disc in focus, then
//   file: a picture to put in it, projectFile: a .discdesign to load into it, pick: ask for a .discdesign.
export function start(homeApi, { fly = true, plan = null, newPlan = false, file = null, projectFile = null, pick = false,
                                  name = null, noDisc = false, dropIn = false } = {}) {
  composeRevision++;
  api = homeApi; $ = api.$;
  const { col, item } = api.current();
  if (plan) S = plan;
  else if (newPlan) {
    // "decide later" in the form: a plan with no disc batch yet (the kind still sets the drawable range)
    const it = noDisc ? { kind: "unset", name: T().noDiscYet, mid: "", s: "none" } : item;
    S = newProject(it, col); S.selTol = 18; S.selFeather = 1;
    if (name) S.name = name;
  }
  else {
    S = projects.get(item);
    if (!S) { S = newProject(item, col); S.selTol = 18; S.selFeather = 1; projects.set(item, S); }
  }
  plans.splice(0, plans.length, S, ...plans.filter((P) => P !== S));
  api.rememberBatch?.(S.item);
  if (!W) build();
  const from = api.focusDisc()?.getBoundingClientRect();
  root.dataset.mode = "design";
  $("back").hidden = false;
  $("next").disabled = !imageLayers().length;
  W.ws.classList.add("on");
  W.ws.classList.toggle("pro-on", S.pro);
  words();
  setTool(S.tool);
  requestAnimationFrame(() => resize());
  setTimeout(() => {
    resize();
    const r = W.cv.getBoundingClientRect();
    if (fly) flight(from, { x: r.left + V.cx, y: r.top + V.cy, d: 120 * V.s }, false);
  }, 30);
  if (dropIn && !api.reduce) W.ws.animate([{ transform: "translateY(-40px)", opacity: 0 }, { transform: "none", opacity: 1 }],
    { duration: 420, easing: "cubic-bezier(.2, .8, .2, 1)" });       // the next sheet comes down from above
  if (file) importFiles([file]);
  if (projectFile) openProject(projectFile);
  if (pick) pickProject();
}
// The library handed back a batch for this plan: switch its discs (the disc kind too, if it changed).
export function useBatch(homeApi, plan, item, col) {
  const before = plan.media;
  plan.item = item; plan.media = col;
  if (plan.geo && before !== col) plan.geo = null;          // a geometry is for one disc kind
  start(homeApi, { plan, fly: false });
  if (before !== col) toast(T().otherMedia(before.toUpperCase(), col.toUpperCase()));
}

// ---------------------------------------------------------------- on to preview and burn
// The projection of the whole disc (120 mm square, centre in the middle) at ppm px per mm.
function projection(ppm) {
  ppm = Math.min(ppm, 20);
  const { c, g, pw, ph } = rasterise(-GRID_MM / 2, -GRID_MM / 2, GRID_MM / 2, GRID_MM / 2, ppm);
  const { adjustments, output } = toneOptions();
  const out = renderOutput(processRGBA(g.getImageData(0, 0, pw, ph), adjustments, { previewScale: ppm * S.cell }), output);
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.putImageData(new ImageData(out.data, pw, ph), 0, 0);
  return c;
}
function hideDesign() {
  composeRevision++;
  stopPlay();
  W.ws.classList.remove("on");
  W.loupe.classList.remove("on");
}
async function toPreview() {
  hideDesign();
  const P = S, preview = await import("./preview.js");
  const ctx = {
    media: P.media, item: P.item, alongTrackMeasured: false,
    project: { name: P.name ?? P.item?.name, cellMm: P.cell, render: projection },
    exportIso: (onProgress, opts) => makeBurnFile((p) => onProgress({ fraction: p.fraction, stage: p.stage }), opts),
    back: () => start(api, { fly: false }),
    next: (iso) => toBurn(iso, () => preview.start(api, ctx)),   // the same context keeps the file it made
  };
  preview.start(api, ctx);
}
function mockBurn(onProgress) {
  const total = 40, t0 = performance.now();
  const id = setInterval(() => {
    const s = (performance.now() - t0) / 1000, p = Math.min(1, s / total);
    onProgress({ progress: p, elapsed: s * 20, remaining: (total - s) * 20, status: p >= 1 ? "success" : undefined });
    if (p >= 1) clearInterval(id);
  }, 250);
  return { cancel() { clearInterval(id); onProgress({ status: "cancelled" }); } };
}
// ?mockburn: the burn page can be opened straight from the console, to look at its animations
if (new URLSearchParams(location.search).has("mockburn")) globalThis.dpToBurn = (iso, back = () => {}) => toBurn(iso, back);
async function toBurn(iso, back) {
  const burn = await import("./burn.js");
  const t = T();
  const mock = new URLSearchParams(location.search).has("mockburn");
  // Which drive: the one this project's geometry was measured on (geo-H-…), else the first one listed.
  let drive = { id: "", name: "", speeds: mock ? (S.media === "cd" ? [4, 8, 16] : [4, 8]) : [] }, problem = "", needSwap = false;
  if (!mock) {
    try {
      const s = await (await fetch(`/api/state?media=${S.media}`)).json();
      const letter = /geo-([A-Z])-/i.exec(S.geo ?? projectGeo(s) ?? "")?.[1];
      const d = s.drives?.find((x) => letter && x.id.toUpperCase() === `${letter.toUpperCase()}:`) ?? s.drives?.[0];
      if (d) drive = { id: d.id, name: d.name && d.name !== d.id ? d.name : d.id, speeds: [] };
      if (d) ({ problem, swap: needSwap } = await inspectDisc(drive, iso)); else problem = t.burnNoDrive;
    } catch { problem = t.exp.noBackend; }
  }
  // ?mockburn&mockswap: the drive holds a written disc; a pretend person changes it (open, empty, closed)
  const mockSwap = mock && new URLSearchParams(location.search).has("mockswap");
  if (mockSwap) { problem = t.burnNotBlankSwap(S.item?.mid || "RITEKF1"); needSwap = true; drive = { id: "H:", name: "H:", speeds: [] }; }
  const ctx = {
    media: S.media, item: S.item, iso, drive, back, driveProblem: problem, needSwap,
    swapWords: { open: t.burnTrayOpen, checking: t.burnChecking, put: t.burnPutBlank(S.item?.mid || S.item?.name || "") },
    // the disc in the drive is the wrong one: wait (read-only) while it is changed, then look again
    swap: mockSwap ? async (onTray) => {
      for (const [ms, state] of [[2500, "open"], [3000, "empty"], [3000, "loading"], [1500, "ready"]]) {
        await new Promise((r) => setTimeout(r, ms)); onTray(state);
      }
    } : mock ? null : (onTray) => api.backend.job({ action: "swap", drive: drive.id, media: S.media, args: { minutes: 15 } },
      (e) => { if (e.type === "tray") onTray(e.state); if (e.type === "started") ctx.swapJob = e.job; }),
    stopSwap: () => { if (ctx.swapJob) api.backend.cancel(ctx.swapJob).catch(() => {}); },
    recheck: mockSwap ? async () => { await new Promise((r) => setTimeout(r, 1200)); Object.assign(ctx, { driveProblem: "", needSwap: false }); drive.speeds = [4, 8]; return ctx; }
      : async () => { ({ problem: ctx.driveProblem, swap: ctx.needSwap } = await inspectDisc(drive, iso)); return ctx; },
    // ?mockburn plays a pretend burn (a timer, no drive) so the page's animation can be looked at.
    burn: mock ? mockBurn : (onProgress, opts) => realBurn(iso, drive, onProgress, opts),
  };
  burn.start(api, ctx);
}
// A read-only look at the disc in the drive, asked for by coming to the burn page: `info` for what it is
// (blank? which maker code?), then the burner's own inspection for room and speeds. A blank disc found
// here opens the burn for two minutes. swap: the disc has to come out for a blank one of this batch.
async function inspectDisc(drive, iso) {
  const t = T();
  let disc;
  try { disc = (await api.backend.job({ action: "info", drive: drive.id, media: S.media }))?.disc; }
  catch (e) { return { problem: t.burnNoDisc(e?.message ?? ""), swap: true }; }
  if (!disc?.present) return { problem: t.burnPutBlank(S.item?.mid || S.item?.name || ""), swap: true };
  if (disc.blank !== true) return { problem: t.burnNotBlankSwap(disc.mid || disc.kind || ""), swap: true };
  const want = S.item?.mid;
  if (want && disc.mid && disc.mid !== want) return { problem: t.burnOtherBatch(disc.mid, want), swap: true };
  const r = await fetch(`/api/burn-speeds?drive=${encodeURIComponent(drive.id)}&media=${S.media}`);
  const m = await r.json().catch(() => ({}));
  if (!r.ok) return { problem: t.burnNoDisc(m.error ?? ""), swap: true };
  if (m.blank !== true) return { problem: t.burnNotBlankSwap(disc.mid || ""), swap: true };
  if (iso.sectors && m.free_sectors && iso.sectors > m.free_sectors) return { problem: t.burnTooBig, swap: false };
  drive.speeds = m.speeds_x ?? [];
  return { problem: "", swap: false };
}
// Burn through the back end: a one-time token, the `burn` job, its progress over the event stream.
// Returns a handle at once; failures arrive as a "failed" status with the reason.
function realBurn(iso, drive, onProgress, { speed } = {}) {
  let job = null, es = null, closed = false, cancelled = false, burnResult = null;
  // started: whether the drive may have begun writing (after the job was accepted)
  const fail = (error, started = !!job) => { if (closed) return; closed = true; es?.close(); onProgress({ status: "failed", error, started }); };
  (async () => {
    try {
      const tok = await (await fetch("/api/burn-token")).json();
      const r = await fetch("/api/run", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "burn", drive: drive.id, media: S.media, args: { iso: iso.path, ...(speed ? { speed } : {}) }, burn_token: tok.token }),
      });
      const out = await r.json().catch(() => ({}));
      if (!r.ok) { fail(out.error ?? T().exp.failed); return; }
      job = out.job;
      es = new EventSource("/api/events");
      const mine = (e) => { const d = JSON.parse(e.data); return d.job === job ? d : null; };
      es.addEventListener("progress", (e) => {
        const d = mine(e); if (!d) return;
        onProgress({ progress: d.fraction, elapsed: d.elapsed_s, remaining: d.eta_s });
      });
      es.addEventListener("error", (e) => { if (e.data) { const d = mine(e); if (d?.message) fail(d.message); } });
      es.addEventListener("burn_speed", (e) => {
        const d = mine(e); if (d) onProgress({ speedReport: d });
      });
      es.addEventListener("verify_progress", (e) => {
        const d = mine(e); if (d) onProgress({ verifying: true });
      });
      es.addEventListener("burn_result", (e) => {
        const d = mine(e); if (d) { burnResult = d; onProgress({ burnResult: d }); }
      });
      es.addEventListener("done", (e) => {
        const d = mine(e); if (!d || closed) return;
        closed = true; es.close();
        onProgress(d.exit === 0 ? { status: "success", progress: 1, burnResult } : cancelled ? { status: "cancelled" } : { status: "failed", error: T().burnFailed, started: true });
      });
    } catch { fail(T().exp.noBackend); }
  })();
  return {
    cancel() {
      cancelled = true;
      if (job) fetch(`/api/jobs/${job}/cancel`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).catch(() => {});
    },
  };
}

function leave() {
  composeRevision++;
  stopPlay();
  const r = W.cv.getBoundingClientRect(), to = { x: r.left + V.cx, y: r.top + V.cy, d: 120 * V.s };
  root.dataset.mode = "";
  W.ws.classList.remove("on");
  W.loupe.classList.remove("on");
  $("back").hidden = true;
  $("next").disabled = false;
  void to;
  api.toLobby ? api.toLobby() : api.goTo(...api.locate(S.item));      // back to the desk (the plan is in its recent list)
}
// the disc batch in the title: pick other discs for this plan in the library
function chooseBatch() {
  if (!api.chooseBatch) return;
  composeRevision++;
  stopPlay();
  root.dataset.mode = "";
  W.ws.classList.remove("on");
  W.loupe.classList.remove("on");
  $("next").disabled = false;               // the library's own button now (an empty plan had it off)
  api.goTo(...api.locate(S.item));
  api.chooseBatch(S);
}
