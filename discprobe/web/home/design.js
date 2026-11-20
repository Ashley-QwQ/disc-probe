import { isActionEnter, observeActivity, dataURLBlob } from "./kit/shared.js";
// The design page: put pictures on the disc and set the tone. A mode of the home page, like
// calibrate.js. Brief: docs/goals/gui-pages/design.md.
//
// Each disc keeps its project while the page lives; "Save project" writes it to a .discdesign file
// (pictures embedded) and closing the page with unsaved work asks first. `makeBurnFile` draws the
// whole disc and has the webui back end run `image --design-npy` on it.
// Tone, dither and export bit packing run in a module worker.
import { processRGBA, renderOutput, autoLevels } from "./design/processing.mjs";

import { selectionPixels, uniqueLayerName } from "./design/selection-edit.mjs";
import { Editor } from "./design/editor-ui.mjs";
import * as EditorOps from "./design/editor-ops.mjs";
import { updateDesk } from "./design/editor-desk.mjs";

import { processingWorker } from "./design/worker-client.mjs";
import { downloadTemplate } from "./design/template-download.mjs";
import { mountFilesStep, occupiedRings, filePictureRange, fileArguments, refreshFiles, drawFileGuides, fileDisplay } from "./design/disc-files.mjs";
import { hasCapability } from "./handshake.mjs";
import { CELLS, COST, geoChoice, measuredRing, burnDocument, checkTextures, experimentalContent, hasColourPicture, pictureSampling } from "./design/export-rules.mjs";
import directionArrow from "./design/direction-arrow.json" with {type: "json"};
import { calibratedBatch, discDisplayKind } from "./batches.mjs";

let api, $;
const root = document.documentElement;
const isOn = () => root.dataset.mode === "design";

// ---------------------------------------------------------------- words
const STR = {
  zh: {
    untitled: "未命名作品", next: "下一步：预览", whyNoPicture: "先放一张图",
    burnLooking: "正在看光驱里的盘…",
    burnCdWindows: "这台电脑上还不能从页面刻 CD。放一张这批的空白 CD，在 PowerShell 里运行下面这条命令：它用仓库里的刻录脚本以 8x 刻。Windows 自带的“刻录光盘映像”会用 40x，在 GH70N 上刻便宜的 CD-R 失败过。",
    burnCdWindowsNoDrive: "这台电脑上还不能从页面刻 CD，而且没找到光驱。接好光驱后回到这一页，这里会给出刻录命令。",
    burnNoDrive: "没找到光驱。接好光驱后再回到这一页。", burnNoDisc: (why) => `读不了光驱里的盘：${why || "可能没放盘"}。放一张空白盘再回到这一页。`,
    burnNotBlank: "光驱里这张不是空白盘。换一张同一批的空白盘，再回到这一页。", burnTooBig: "刻录文件比这张盘放得下的大。",
    burnNotBlankSwap: (what) => `光驱里这张${what ? ` ${what} ` : ""}已经刻过了。按光驱上的弹出键把它取出来。`,
    burnPutBlank: (mid) => `放一张空白的 ${mid || "同一批"} 盘，把托盘推回去。推回后会自动检查。`,
    burnOtherBatch: (got, want) => `这张是 ${got}，几何是在 ${want} 上测的。取出它，换一张 ${want} 空白盘。`,
    burnChecking: "正在检查这张盘（只读）…", burnTrayOpen: "托盘开着。放一张空白盘，再推回去。",
    burnFailed: "刻录没有完成。这张盘可能已经写了一部分，不要再用。详细原因在任务日志里。",
    burnNotStarted: "刻录没有开始，盘没有被写过，还能用。",
    open: "打开作品", save: "保存作品", saveAs: "另存为", saved: (n) => `已保存：${n}`, opened: (n) => `已打开：${n}`,
    notProject: (n) => `${n} 不是 disc-probe 的作品文件。`, newer: (n) => `${n} 是新版本存的，这一版读不了。`,
    changeDiscs: "换一批盘（打开盘库）", noDiscYet: "还没选盘", otherMedia: (a, b) => `这件作品是给 ${a} 做的，现在打开在 ${b} 上；可刻范围按 ${b} 算。`,
    unsaved: "作品还没保存，关掉页面会丢失。",
    exp: {
      drawing: "正在画整张盘的设计图…", sending: "正在交给后端…", making: "正在生成刻录文件…",
      noBackend: "生成刻录文件前请启动 disc-probe。Windows 完整包双击“开始 Start (Windows).bat”，Linux 完整包运行 bash start-linux.sh。用源码时运行 python -m discprobe webui --open。",
      noGeo: "这种盘还没有测好的盘面几何，先校准。",
      failed: "生成失败。", empty: "盘上还没有图。", four: "4 级灰阶还不能导出：先用 2 级。",
    },
    layers: "图层", undo: "撤销（Ctrl+Z）", redo: "重做（Ctrl+Shift+Z）", import: "导入图片", noLayers: "还没有图层。",
    show: "显示", hide: "隐藏", lock: "锁定", unlock: "解锁", remove: "删除",
    files: "随盘文件", pickFolder: "选择文件夹", inner: "内圈", outer: "外圈", clear: "清除",
    filesN: (n, size) => `${n} 个文件 · ${size}`, filesRing: (a, b) => `占半径 ${a}–${b} mm，这一圈放文件，不刻图。`,
    filesNone: "不带文件时，整个可刻范围都给图。",
    filesLater: "还不能把文件一起刻进盘：核心还没有这项功能。现在整个可刻范围都给图。", cdFiles: "CD：不带文件就刻音轨，带文件就刻数据盘。",
    tone: "影调", dither: "抖动强度", bright: "亮度", levels: "灰阶", lv: (n) => n === 4 ? '4 级 · 只能预览' : `${n} 级`, lv4: "4 级仅供 CD 预览，导出请选 2 级",
    lin: "sRGB 线性化", inv: "反转 3T/6T 映射",
    more: "更多", auto: "自动色阶", autoOff: "取消自动色阶", autoOn: (b, w) => `黑点 ${b} · 白点 ${w}`,
    contrast: "对比度", hi: "高光", sh: "阴影", mode: "抖动方式",
    modes: { "floyd-steinberg": "误差扩散", "blue-noise": "蓝噪声", ordered: "有序", clustered: "网点", threshold: "不抖动" },
    reset: "恢复默认",
    tools: { move: "选择（V）", wand: "选区（W）", pan: "平移（H，或按住空格）" },
    proj: "设计", burnView: "刻出来", orig: "灯下", viewAria: "画布显示", zoomAria: "在适应盘面和 100% 之间切换",
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
    precCost: (n) => `整盘 ${n} × ${n} 格，由后端导出。10 / 5 µm：DVD 和 BD 沿轨、半径两个方向都更细；CD 沿轨最细约 80 µm，只有半径方向更细。格子更小会多用内存和时间。彩色材质需要成片的区域，单个 5 µm 小格看不出颜色。`,
    loupe: "放大镜", loupeHint: (c, f) => `1 格 = ${c} µm · 视野 ${f} mm`,
    sampleName: "示例：山和太阳",
    fit: "适应", hundred: "100%",
    grid: "刻录格子",
    cellCost: (um, c) => (um === 20 ? `默认。生成约 ${c.minutes} 分钟。` : `生成约 ${c.minutes} 分钟，要 ${c.gb} GB 左右内存。10 / 5 µm：DVD 和 BD 沿轨、半径两个方向都更细；CD 沿轨最细约 80 µm，只有半径方向更细。${um === 5 ? "显微镜下 5 µm 棋盘格是临界失败。" : ""}`) + "彩色材质需要成片的区域，单个 5 µm 小格看不出颜色。",
    coarse: (um) => `图片本身每像素约 ${um} µm，比格子粗：格子再细，图也不会更清楚。`,
    limits: "随盘文件目前支持 DVD±R 单层。颜色、彩色图案和特效只是预览实验，默认按黑白刻。",
    cdLimit: "CD 只刻深浅两级，四级灰度和颜色都还不能刻。",
    lost: (names) => `这些图层没能读出来，已跳过：${names}。其余照原样打开；再保存就不带它们了。`,
    tooLarge: (n, mb) => `${n} 有 ${mb} MB，超过这一版能打开的 400 MB。`,
    bigWork: (mb) => `这件作品有 ${mb} MB，超过一次能交给后端的 384 MB：删掉几个图层或换小一点的图再试。`,
    exp2: { bwOnly: (s) => `刻录文件里出现了黑白以外的纹理（${s}），没有生成。`, noCell: "格子只能是 20、10 或 5 µm。" },
  },
  en: {
    untitled: "Untitled work", next: "Next: preview", whyNoPicture: "Add a picture first",
    burnLooking: "Looking at the disc in the drive…",
    burnCdWindows: "This computer cannot burn CDs from the page yet. Put in a blank CD from this batch and run the command below in PowerShell: it burns at 8x with the repo's script. Windows' own Burn disc image picks 40x, which failed on a GH70N with cheap CD-R.",
    burnCdWindowsNoDrive: "This computer cannot burn CDs from the page yet, and no drive was found. Connect the drive and come back to this page for the burn command.",
    burnNoDrive: "No drive found. Connect the drive and come back to this page.", burnNoDisc: (why) => `Couldn't read the disc in the drive: ${why || "maybe there is none"}. Put in a blank disc and come back to this page.`,
    burnNotBlank: "The disc in the drive isn't blank. Put in a blank from the same batch and come back to this page.", burnTooBig: "The burn file is bigger than this disc can hold.",
    burnNotBlankSwap: (what) => `The disc in the drive${what ? ` (${what})` : ""} has already been written. Press the drive's eject button and take it out.`,
    burnPutBlank: (mid) => `Put in a blank ${mid || "disc from the same batch"} and push the tray in. It is checked as soon as the tray closes.`,
    burnOtherBatch: (got, want) => `This disc is ${got}; the geometry was measured on ${want}. Take it out and put in a blank ${want}.`,
    burnChecking: "Checking this disc (read-only)…", burnTrayOpen: "The tray is open. Put in a blank disc and push it in.",
    burnFailed: "The burn didn't finish. The disc may be partly written; don't use it. The job log has the details.",
    burnNotStarted: "The burn did not start: nothing was written, and the disc can still be used.",
    open: "Open work", save: "Save work", saveAs: "Save as", saved: (n) => `Saved: ${n}`, opened: (n) => `Opened: ${n}`,
    notProject: (n) => `${n} isn't a disc-probe work file.`, newer: (n) => `${n} was saved by a newer version; this one can't read it.`,
    changeDiscs: "Use other discs (opens the disc library)", noDiscYet: "No discs chosen yet", otherMedia: (a, b) => `This work was made for ${a} and is now open on ${b}; the burnable range is ${b}'s.`,
    unsaved: "The work isn't saved; closing the page loses it.",
    exp: {
      drawing: "Drawing the whole disc…", sending: "Handing it to the back end…", making: "Making the burn file…",
      noBackend: "Start disc-probe before making a burn file. Double-click “开始 Start (Windows).bat” in the Windows full package or run bash start-linux.sh in the Linux full package. From source, run python -m discprobe webui --open.",
      noGeo: "No measured disc geometry for this disc type yet. Calibrate first.",
      failed: "Making the file failed.", empty: "There's no picture on the disc yet.", four: "4 grey levels can't be exported yet: use 2 for now.",
    },
    layers: "Layers", undo: "Undo (Ctrl+Z)", redo: "Redo (Ctrl+Shift+Z)", import: "Import picture", noLayers: "No layers yet.",
    show: "Show", hide: "Hide", lock: "Lock", unlock: "Unlock", remove: "Delete",
    files: "Files on the disc", pickFolder: "Choose folder", inner: "Inner", outer: "Outer", clear: "Clear",
    filesN: (n, size) => `${n} files · ${size}`, filesRing: (a, b) => `Radius ${a}–${b} mm holds the files; no picture there.`,
    filesNone: "Without files, the whole burnable range is the picture's.",
    filesLater: "Files can't be burned onto the disc yet: the core does not do it. The whole burnable range is the picture's.", cdFiles: "CD: without files it burns an audio track; with files, a data disc.",
    tone: "Tone", dither: "Dither strength", bright: "Brightness", levels: "Grey", lv: (n) => n === 4 ? '4 · preview only' : `${n} levels`, lv4: "4 levels are for CD preview only; choose 2 to export",
    lin: "sRGB linearisation", inv: "Swap the 3T/6T mapping",
    more: "More", auto: "Auto levels", autoOff: "Undo auto levels", autoOn: (b, w) => `Black ${b} · white ${w}`,
    contrast: "Contrast", hi: "Highlights", sh: "Shadows", mode: "Dither method",
    modes: { "floyd-steinberg": "Error diffusion", "blue-noise": "Blue noise", ordered: "Ordered", clustered: "Halftone", threshold: "No dither" },
    reset: "Reset",
    tools: { move: "Select (V)", wand: "Selection (W)", pan: "Pan (H, or hold Space)" },
    proj: "Design", burnView: "As burned", orig: "Under the lamp", viewAria: "Canvas shows", zoomAria: "Switch between fit and 100%",
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
    precCost: (n) => `${n} × ${n} cells for the whole disc; the back end exports it. At 10 / 5 µm, DVD and BD are finer both along the track and radially; CD stays about 80 µm along the track and is finer only radially. Finer grids need more memory and time. Coloured textures need broad areas: a single 5 µm cell cannot show colour.`,
    loupe: "Loupe", loupeHint: (c, f) => `1 cell = ${c} µm · ${f} mm across`,
    sampleName: "Sample: hills and sun",
    fit: "Fit", hundred: "100%",
    grid: "Burn grid",
    cellCost: (um, c) => (um === 20 ? `Default. Takes about ${c.minutes} min to make.` : `Takes about ${c.minutes} min and ${c.gb} GB of memory to make. At 10 / 5 µm, DVD and BD are finer both along the track and radially; CD stays about 80 µm along the track and is finer only radially.${um === 5 ? " A 5 µm checkerboard is a borderline fail under the microscope." : ""}`) + " Coloured textures need broad areas: a single 5 µm cell cannot show colour.",
    coarse: (um) => `The picture itself has about ${um} µm per pixel, coarser than the grid: a finer grid won't make it sharper.`,
    limits: "Files on the disc currently support single-layer DVD±R. Colours, coloured patterns and effects are a preview experiment; they burn in black and white by default.",
    cdLimit: "A CD burns two levels, dark and light; four grey levels and colours can't be burned yet.",
    lost: (names) => `These layers couldn't be read and were left out: ${names}. The rest opened as saved; saving again drops them.`,
    tooLarge: (n, mb) => `${n} is ${mb} MB, more than the 400 MB this version can open.`,
    bigWork: (mb) => `This work is ${mb} MB, more than the 384 MB the back end takes at once: remove a few layers or use smaller pictures.`,
    exp2: { bwOnly: (s) => `The burn file had textures other than black and white (${s}); nothing was made.`, noCell: "The grid can only be 20, 10 or 5 µm." },
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
// files burned beside the picture: off until the core writes them (image takes no files, the ISO gets no entries)
const FILES_READY = false;
const RANGE = { dvd: [24, 58], cd: [23, 58], bd: [24, 58] };          // burnable radii, mm
const CAPACITY = { dvd: 4.7e9, cd: 0.7e9, bd: 25e9 };
const DEFAULT_TONE = { dither: 100, bright: 0, levels: 2, lin: false, inv: false, contrast: 0, hi: 0, sh: 0, mode: "floyd-steinberg", auto: null };
const MAX_SIDE = 4096;                       // the working copy a picture is edited and exported from (export-rules pictureSampling)
const COLOURS = { red: 0.62, green: 0.53, blue: 0.46 };   // target wavelengths, µm
const FLASH = [-43.66, 19.79];               // iPhone 17 Pro flash relative to the lens (drawing values)
const FWHM = 0.08;                           // measured peak width in δ (the model said 0.04)

let editor = null;
let S = null;                                // the project on screen
// The plans (works) made or opened while the page lives, newest first. A plan is a work, not a disc:
// one batch of discs can carry many plans (docs/goals/gui-flow.md 1.1).
const plans = [];
const projects = new Map();                  // the shelf's old way in: one plan per shelf disc
export const recentPlans = () => plans.filter((P) => P.layers.length || P.name);
let W = null;                                // the workspace's DOM
const V = { s: 5, cx: 0, cy: 0, w: 0, h: 0, dpr: 1 };   // canvas view: px per mm and the disc centre
let followFit = true;
let focus = { x: 0, y: 0, w: 0, h: 0 };
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
const layerRow = (row) => S.layers.find((L) => String(L.id) === row.dataset.id);
function newLayerId() {
  while (S.layers.some(L => String(L.id) === String(nextId))) nextId++;
  return nextId++;
}
// The ring a picture may use: the disc kind's burnable ring, cut to what this plan's geometry measured
// (S.ring, set by useMeasured). Outside it the core refuses to place a picture: an unmeasured radius is a guess.
const range = () => S?.ring ?? RANGE[S.media] ?? RANGE.dvd;
function useMeasured(geo) {
  if (!S) return;
  const limit = geo?.nominal && S.media === "cd" ? [26, 58] : RANGE[S.media] ?? RANGE.dvd;
  const ring = measuredRing(geo?.measured ?? geo?.nominal, limit);
  if (String(ring) === String(S.ring ?? null)) return;
  S.ring = ring; comp = null; editor?.invalidate(); draw();
}
const flashOff = (scene) => scene.flashOffset ?? FLASH;   // the chosen phone (editor-rig.mjs), else iPhone 17 Pro turned as before
const lampPos = () => S.scene.follows ? [S.scene.cam[0] + flashOff(S.scene)[0], S.scene.cam[1] - flashOff(S.scene)[1], S.scene.cam[2]] : S.scene.lamp;
const heightOf = (L) => L.kind === "image" ? L.width * L.h / L.w : L.height;

// the part of the disc that holds files, if any: [from, to] radius in mm
function filesRing() {
  return occupiedRings(S.files)[0] ?? null;
}
// where the picture may go: [inner, outer]
function pictureRange() {
  return filePictureRange(S.files, range());
}

// ---------------------------------------------------------------- history (undo / redo)
// A snapshot is the layer list with each layer's properties; pixels are immutable ImageData, so a
// snapshot only holds references to them.
const PROPS = ["name", "x", "y", "width", "height", "rot", "opacity", "visible", "locked", "px", "colour", "y1", "y2", "fxKind", "tone", "alphaEdited", "shape", "sourceKind"];
function snapshot() {
  return { editor: structuredClone({selections:S.selections, assignments:S.assignments, activeMask:S.activeMask, maskGrid:S.maskGrid, materials:S.materials, cell:S.cell, scene:S.scene, lookY:S.lookY}), layers: S.layers.map((L) => ({ obj: L, props: Object.fromEntries(PROPS.map((k) => [k, L[k]])) })), selected: S.selected };
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
  Object.assign(S, snap.editor ?? {});
  editor?.invalidate();
  editor?.selectionOptions(S.selections?.find(m=>m.id===S.activeMask)?.definition);
  S.selected = snap.selected;
  changed();
  buildLeft();
  editor?.panels();
}
function undo() { if(editor?.drag){editor.cancelGesture();return;}if (!S.past.length) return; S.future.push(snapshot()); restore(S.past.pop()); }
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
function drawShape(g, shape, rgb = [30, 30, 30]) {
  const {width, height} = g.canvas;
  const px = g.createImageData(width, height), rgba = [...rgb, 255];
  for (let j = 0; j < height; j++) for (let i = 0; i < width; i++) {
    if (EditorOps.shapeHit(shape, (i + .5) / width - .5, (j + .5) / height - .5)) px.data.set(rgba, 4 * (j * width + i));
  }
  g.putImageData(px, 0, 0);
  return px;
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
    id: newLayerId(), kind: "image", name: uniqueLayerName(S.layers, name, api.lang()==="zh"?"图片":"Image"), w: c.width, h: c.height,
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
    id: newLayerId(), kind: "fx", fxKind: kind, name: T().fxKinds[kind][0],
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
    if (!/^image\/(png|jpeg|webp|bmp|svg\+xml)$/.test(f.type)) { toast(t.badType(f.name)); continue; }
    if (f.size > 24 * 1024 * 1024) { toast(t.tooBig(f.name)); continue; }
    let bmp, svg;
    try {
      if (f.type === "image/svg+xml" || /\.svg$/i.test(f.name)) {
        svg = await f.text();
        const parsed = new DOMParser().parseFromString(svg, "image/svg+xml");
        if (parsed.querySelector("parsererror,script,foreignObject") || [...parsed.querySelectorAll("*")].some(n => [...n.attributes].some(a => /^on/i.test(a.name) || (!a.name.startsWith("xmlns") && /(?:https?:|file:|javascript:)/i.test(a.value))))) throw Error("SVG must be self-contained");
        const url = URL.createObjectURL(new Blob([svg], {type:"image/svg+xml"}));
        try { bmp = await new Promise((ok,no)=>{const im=new Image();im.onload=()=>ok(im);im.onerror=no;im.src=url;}); } finally { URL.revokeObjectURL(url); }
      } else bmp = await createImageBitmap(f);
    } catch { toast(t.badType(f.name)); continue; }
    if (bmp.width * bmp.height > 36e6) { toast(t.tooBig(f.name)); continue; }
    const L = addImageLayer(f.name, bmp, bmp.width, bmp.height);
    if (L) { L.file = f; L.sourceKind = svg ? "svg" : "bitmap"; if(svg)L.svg=svg; }                       // the original, for export at full size and for saving
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

// Current selections live in the document; source pixels are immutable for history.
function selectionEdit(action) {
  const L=sel(),m=S.selections?.find(m=>m.id===S.activeMask);
  if(!L?.px||L.locked||!m)return null;
  const split=action==='copy'||action==='cut';
  if(split&&S.layers.length>=16){toast(T().tooMany);return null;}
  const {selected,remaining}=selectionPixels(L,EditorOps.bytes(m.bits),S.maskGrid,editor.options.feather??0);
  checkpoint();
  let next=null;
  if(split){next={...L,id:newLayerId(),name:uniqueLayerName(S.layers,L.name,api.lang()==='zh'?'图片':'Image',false),px:new ImageData(selected,L.w,L.h),alphaEdited:true,shape:undefined,sourceKind:'bitmap',thumb:null,src:null};
    pixelsChanged(next);S.layers.splice(S.layers.indexOf(L)+1,0,next);S.selected=next.id;
    S.assignments.push(...S.assignments.filter(a=>a.layer===L.id).map(a=>({...structuredClone(a),id:crypto.randomUUID(),layer:next.id})));}
  if(action!=='copy'){L.px=new ImageData(action==='keep'?selected:remaining,L.w,L.h);L.alphaEdited=true;L.shape=undefined;L.sourceKind='bitmap';pixelsChanged(L);}
  S.activeMask=null;changed();buildLeft();buildRight();return next;
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
const TOP_DOCK = 64;
const DOCK = 96;                             // the canvas's bottom strip, where the number bar docks
function fit() {
  followFit = true;
  V.s = Math.max(1, Math.min(focus.w - 64, focus.h - TOP_DOCK - DOCK)) * 0.92 / 120;
  V.cx = focus.x + focus.w / 2 + 20; V.cy = focus.y + TOP_DOCK + (focus.h - TOP_DOCK - DOCK) / 2;
  settleView();editor?.invalidate();
  draw(); queueCompose();
}
let motion=null,motionTimer;
function settleView(){clearTimeout(motionTimer);if(!motion)return;motion=null;W.canvas.style.transform='';W.canvas.style.willChange='';draw();queueCompose();}
function viewChanged(){
  if(S.view!=='burn'||!paintedView){draw();queueCompose();return;}
  motion??={...paintedView};clearTimeout(motionTimer);motionTimer=setTimeout(settleView,150);
  draw();
}
let paintedView=null;
function zoomAt(f, sx, sy) {
  followFit = false;
  const s = Math.min(Math.max(V.s * f, Math.min(focus.w, focus.h) * 0.2 / 120), 4 / S.cell);
  const k = s / V.s;
  V.cx = sx - (sx - V.cx) * k; V.cy = sy - (sy - V.cy) * k; V.s = s;
  viewChanged();
}
const zoomPct = () => Math.round(V.s * S.cell * 100);

// ---------------------------------------------------------------- the picture after tone (the projection)
function toneOptions(plan = S) {
  const t = plan.tone;
  const adjustments = {
    brightness: t.bright / 64 * 50, contrast: t.contrast, highlights: t.hi, shadows: t.sh,
    gamma: t.lin ? 1 / 2.2 : 1, invert: !!t.inv && plan.media === "bd",
    ...(t.auto ? { blackPoint: t.auto[0], whitePoint: t.auto[1] } : {}),
  };
  const four = t.levels === 4 && plan.media === "cd";
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
// Archive thumbnails use the editor's rasteriser, tone processing and measured drawing range.
// They never select a project, touch the editor's canvas, or start its worker/device flows.
const planThumbs = new WeakMap();
export function planThumbnail(plan, px = 256) {
  px = Math.max(32, Math.min(512, Math.round(px)));
  const dark = root.dataset.theme === "dark";
  const key = JSON.stringify([px, dark, plan.media, plan.view, plan.tone, plan.pro, plan.lookColour, plan.lookY, plan.scene,
    plan.past?.length, plan.future?.length,
    (plan.layers || []).map((L) => [L.kind, L.w, L.h, L.version, ...PROPS.filter((k) => k !== "px").map((k) => L[k])])]);
  const sources = (plan.layers || []).flatMap((L) => [L.src, L.px]);
  const cached = planThumbs.get(plan);
  if (cached?.key === key && sources.every((src, i) => src === cached.sources[i])) return cached.url;
  const face = dark ? "#ebe7e0" : "#d6d1c8", hub = dark ? "#e4dfd7" : "#c9c3b9";
  const c = document.createElement("canvas"); c.width = c.height = px;
  const g = c.getContext("2d"), ppm = px / 120, centre = px / 2;
  const ring = (a, b) => { g.beginPath(); g.arc(centre, centre, b * ppm, 0, 2 * Math.PI); g.arc(centre, centre, a * ppm, 0, 2 * Math.PI, true); };
  g.fillStyle = face; ring(7.5, 60); g.fill("evenodd");
  g.fillStyle = hub; ring(7.5, 17); g.fill("evenodd");
  const layers = (plan.layers || []).filter((L) => L.kind === "image");
  if (layers.some((L) => L.visible)) {
    const raster = rasterise(-60, -60, 60, 60, ppm, true, null, layers);
    if (plan.view !== "orig") {
      const { adjustments, output } = toneOptions({ ...plan, tone: { ...DEFAULT_TONE, ...plan.tone } });
      const out = renderOutput(processRGBA(raster.g.getImageData(0, 0, px, px), adjustments, { previewScale: ppm * (plan.cell || .02) }), output);
      raster.g.setTransform(1, 0, 0, 1, 0, 0); raster.g.putImageData(new ImageData(out.data, px, px), 0, 0);
    }
    const [r0, r1] = RANGE[plan.media] || RANGE.dvd;
    g.save(); ring(r0, r1); g.clip("evenodd"); g.drawImage(raster.c, 0, 0);
    if (plan.view !== "orig") { g.globalCompositeOperation = "multiply"; g.fillStyle = face; g.fillRect(0, 0, px, px); }
    g.restore();
  }
  const look = lookOverlay(plan);
  if (look) {
    const [r0, r1] = RANGE[plan.media] || RANGE.dvd;
    g.save(); ring(r0, r1); g.clip("evenodd");
    g.globalCompositeOperation = "multiply"; g.drawImage(look.colour, 0, 0, px, px);
    g.globalCompositeOperation = "source-over"; g.globalAlpha = .95; g.drawImage(look.fx, 0, 0, px, px); g.restore();
  }
  g.strokeStyle = "#1d1b18"; g.globalAlpha = .25; g.lineWidth = .7;
  for (const r of [7.5, 17, 60]) { g.beginPath(); g.arc(centre, centre, r * ppm - .4, 0, 2 * Math.PI); g.stroke(); }
  const url = c.toDataURL("image/png");
  planThumbs.set(plan, { key, sources, url });
  return url;
}
let comp = null, composeT = 0, composeKey = "";
let composeRevision = 0, composing = false, composeAgain = false, previewWorker = null;
function queueCompose() { composeRevision++; clearTimeout(composeT); composeT = setTimeout(compose, 40); }
async function compose() {
  if (editor) { comp = null; draw(); return; }
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
function poseAt(y, plan = S) {
  const cam = [plan.scene.cam[0], -y, plan.scene.cam[2]];
  const lamp = plan.scene.follows ? [cam[0] + flashOff(plan.scene)[0], cam[1] - flashOff(plan.scene)[1], cam[2]] : plan.scene.lamp;
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
function lookOverlay(plan = S) {
  const fx = plan.layers.filter((L) => L.kind === "fx" && L.visible);
  const coloured = plan.layers.filter((L) => L.kind === "image" && L.visible && L.colour !== "none");
  if (!plan.pro || (!fx.length && !(plan.lookColour && coloured.length))) return null;
  const key = JSON.stringify([plan.lookY, plan.scene, plan.lookColour, fx.map((L) => PROPS.map((k) => L[k])), coloured.map((L) => [L.id, L.version, L.x, L.y, L.width, L.rot, L.colour])]);
  if (plan === S && key === lookKey && lookCanvas) return lookCanvas;
  const N = 240, mm = 120 / N, imgC = new ImageData(N, N), imgF = new ImageData(N, N);
  const [camP, lampP] = poseAt(plan.lookY, plan);
  const [camD, lampD] = poseAt(-plan.scene.cam[1], plan);   // the design position: what the textures were chosen for
  // where each coloured layer is: its alpha on the same grid
  const masks = coloured.map((L) => {
    const one = { ...L };
    const { g } = rasterise(-60, -60, 60, 60, N / 120, false, null, []);
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
      const [camT, lampT] = poseAt(yt, plan);
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
  const result = { colour: put(imgC), fx: put(imgF) };
  if (plan === S) { lookKey = key; lookCanvas = result; }
  return result;
}

// ---------------------------------------------------------------- drawing the canvas
let drawQueued = false, canvasActive = true;
function draw() {
  if (drawQueued || !canvasActive || document.hidden || !isOn()) return;
  drawQueued = true;
  const run = () => { if (!drawQueued) return; drawQueued = false; if (canvasActive && !document.hidden && isOn()) paintCanvas(); };
  requestAnimationFrame(run);
  setTimeout(run, 60);                      // a hidden page gets no animation frames
}
const cssVar = (n) => getComputedStyle(root).getPropertyValue(n).trim();
function annulus(g, a, b) {
  g.beginPath();
  g.arc(V.cx, V.cy, b * V.s, 0, Math.PI * 2);
  g.arc(V.cx, V.cy, a * V.s, 0, Math.PI * 2, true);
}
// 45° hatching in the ring a..b mm: 0.75 px ink at 40 %, a fixed screen pitch so it reads as a drawing at any zoom
function hatch(g, a, b, ink) {
  if (b <= a) return;
  g.save(); annulus(g, a, b); g.clip("evenodd");
  g.strokeStyle = ink; g.globalAlpha = 0.4; g.lineWidth = 0.75;
  const R = b * V.s;
  g.beginPath();
  for (let k = -2 * R; k < 2 * R; k += 7) { g.moveTo(V.cx + k - R, V.cy + R); g.lineTo(V.cx + k + R, V.cy - R); }
  g.stroke(); g.restore();
}
// a faint scale along one radius (to the right): ticks every 5 mm, the burnable range's ends numbered
function ruler(g, r0, r1, ink) {
  const px = (mm) => V.cx + mm * V.s, y = V.cy;
  if (V.s * 5 < 6) return;                    // too small to read
  g.save(); g.strokeStyle = ink; g.fillStyle = ink; g.globalAlpha = 0.4; g.lineWidth = 0.75;
  g.beginPath(); g.moveTo(px(r0), y); g.lineTo(px(r1), y);
  for (let mm = Math.ceil(r0 / 5) * 5; mm <= r1; mm += 5) { const h = mm % 10 ? 3 : 5; g.moveTo(px(mm), y - h); g.lineTo(px(mm), y + h); }
  for (const mm of [r0, r1]) { g.moveTo(px(mm), y - 7); g.lineTo(px(mm), y + 7); }
  g.stroke();
  g.globalAlpha = 0.7; g.font = `11px ${cssVar("--mono")}`; g.textAlign = "center"; g.textBaseline = "top";
  // the ring's ends may be measured radii (S.ring): one decimal, never the raw float
  for (const mm of [r0, r1]) g.fillText(String(Math.round(mm * 10) / 10), px(mm), y + 9);
  g.restore();
}
function paintCanvas() {
  if (!W || !S) return;
  updateDesk(W, V, focus);
  const cv = W.canvas, g = cv.getContext("2d");
  if(motion&&S.view==='burn'){
    const k=V.s/motion.s;cv.style.transformOrigin='0 0';cv.style.willChange='transform';
    cv.style.transform=`translate(${V.cx-motion.cx*k}px,${V.cy-motion.cy*k}px) scale(${k})`;return;
  }
  if(motion)settleView();
  paintedView={...V};
  g.setTransform(V.dpr, 0, 0, V.dpr, 0, 0);
  g.clearRect(0, 0, V.w, V.h);
  const face = cssVar("--face"), face2 = cssVar("--face-2"), dim = cssVar("--dim"), paper = cssVar("--paper");
  const [r0, r1] = range(), [p0, p1] = pictureRange(), fr = filesRing();
  // the disc, data side up
  g.fillStyle = face; g.beginPath(); g.arc(V.cx, V.cy, 60 * V.s, 0, Math.PI * 2); g.fill();
  g.fillStyle = face2; annulus(g, 7.5, 17); g.fill("evenodd");
  // the pictures as they are (grey in the projection), everywhere, so what falls outside still shows
  const grey = S.view !== "orig";
  for (const L of imageLayers()) {
    if (!L.visible) continue;
    if (S.view === "lamp") continue;       // this view shows only the core's disc image
    g.save();
    g.globalAlpha = L.opacity;
    if (grey && !(S.view === "proj" && S.assignments?.some(a => a.colour && a.layer === L.id))) g.filter = "grayscale(1)";
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
    g.globalCompositeOperation = "multiply"; g.fillStyle = face; g.fillRect(0, 0, V.w, V.h);   // the disc's own face colour
    g.restore();
  }
  // PRO: how it looks from the chosen position
  const look = editor ? null : lookOverlay();
  if (look) {
    g.save(); annulus(g, p0, p1); g.clip("evenodd");
    g.imageSmoothingEnabled = true;
    const box = [V.cx - 60 * V.s, V.cy - 60 * V.s, 120 * V.s, 120 * V.s];
    g.globalCompositeOperation = "multiply"; g.drawImage(look.colour, ...box);
    g.globalCompositeOperation = "source-over"; g.globalAlpha = 0.95; g.drawImage(look.fx, ...box);
    g.restore();
  }
  editor?.paint(g);
  const L = sel();
  // everything outside the burnable ring stays in sight at about a quarter, with its outline (as DIS does)
  // Reveal the continuous desk under the out-of-disc picture at 25% opacity.
  g.save(); g.globalCompositeOperation = "destination-out"; g.fillStyle = "rgb(0 0 0 / .75)";
  g.beginPath(); g.rect(0, 0, V.w, V.h); g.arc(V.cx, V.cy, 60 * V.s, 0, Math.PI * 2, true); g.fill();
  g.restore();
  g.fillStyle = cssVar("--face-dim");                       // the disc where nothing is burned
  annulus(g, r1, 60); g.fill("evenodd");
  g.beginPath(); g.arc(V.cx, V.cy, r0 * V.s, 0, Math.PI * 2); g.fill();
  const ink = cssVar("--face-ink");
  g.save(); g.strokeStyle = cssVar("--ink-3"); g.globalAlpha = 0.8; g.lineWidth = 0.75;
  for (const P of imageLayers()) {
    if (S.tool !== "move" || !P.visible || !cornersOutside(P, p0, p1)) continue;
    const cs = corners(P); g.beginPath(); cs.forEach(([x, y], i) => i ? g.lineTo(x, y) : g.moveTo(x, y)); g.closePath(); g.stroke();
  }
  g.restore();
  // what is not yours to draw on, as on a drawing: fine 45° hatching on the clamp ring and the rim
  hatch(g, 7.5, r0, ink); hatch(g, r1, 60, ink);
  // the hole shows the page through it
  // the ring that holds files: light diagonal lines
  if (fr) {
    g.save(); annulus(g, fr[0], fr[1]); g.clip("evenodd");
    g.fillStyle = dim; g.fillRect(0, 0, V.w, V.h);
    g.strokeStyle = cssVar("--ink-3"); g.globalAlpha = 0.45; g.lineWidth = 1;
    const R = fr[1] * V.s;
    for (let k = -2 * R; k < 2 * R; k += 9) { g.beginPath(); g.moveTo(V.cx + k - R, V.cy + R); g.lineTo(V.cx + k + R, V.cy - R); g.stroke(); }
    g.restore();
  }
  drawFileGuides(g, V, occupiedRings(S.files).slice(1), cssVar);
  g.save(); g.globalCompositeOperation = "destination-out"; g.fillStyle = "#000";
  g.beginPath(); g.arc(V.cx, V.cy, 7.5 * V.s, 0, Math.PI * 2); g.fill(); g.restore();
  // Screen-only thickness: a fine 1 px dark outer edge; structure stays at 70%.
  g.save(); g.strokeStyle = ink;
  g.lineWidth = 1; g.beginPath(); g.arc(V.cx, V.cy, 60 * V.s, 0, Math.PI * 2); g.stroke();
  g.lineWidth = 1; g.globalAlpha = 0.7;
  for (const r of [7.5, r0, r1]) { g.beginPath(); g.arc(V.cx, V.cy, r * V.s, 0, Math.PI * 2); g.stroke(); }
  g.restore();
  ruler(g, r0, r1, ink);
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
  if (L && S.tool === "move" && !spaceDown) {
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
  W.empty.hidden = S.layers.length > 0 || !!S.assignments?.length;
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
  if (S.activeMask || !L || !L.visible || S.tool !== "move" || spaceDown) { bar.hidden = true; return; }
  const mode = "props";
  if (bar.dataset.mode !== mode || bar.dataset.id !== String(L.id) || bar.dataset.lang !== api.lang()) fillBar(L, mode);
  else syncBar(L);
  bar.hidden = false;
  // docked: the middle of the canvas's bottom strip, under the disc, the same place whatever is selected
  // (above the tilt bar when that one is out)
  const bw = bar.offsetWidth, bh = bar.offsetHeight, tilt = W.tilt?.offsetParent ? W.tilt.offsetHeight + 8 : 0;
  const top = 4;
  const left = 56;
  bar.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
}
function fillBar(L, mode) {
  const t = T(), bar = W.bar;
  bar.dataset.mode = mode; bar.dataset.id = String(L.id); bar.dataset.lang = api.lang();
    const f = t.fb, fx = L.kind === "fx";
    bar.innerHTML = `<label>${f.x}<input type="number" step="0.1" data-k="x"></label><label>${f.y}<input type="number" step="0.1" data-k="y"></label>` +
      `<label>${f.w}<input type="number" step="0.5" min="1" data-k="width"></label>` + (fx ? `<label>${f.h}<input type="number" step="0.5" min="1" data-k="height"></label>` : "") +
      `<label>${f.rot}<input class="short" type="number" step="1" data-k="rot"></label>` + (fx ? "" : `<label>${f.op}<input class="short" type="number" step="5" min="0" max="100" data-k="opacity"></label>`) +
      `<span class="sep"></span><button class="ib" type="button" data-a="lock" aria-label="${L.locked ? t.unlock : t.lock}" title="${L.locked ? t.unlock : t.lock}" aria-pressed="${L.locked}">${L.locked ? I.lock : I.unlock}</button>` +
      `<button class="ib" type="button" data-a="del" aria-label="${t.remove}" title="${t.remove}">${I.trash}</button>`;
  syncBar(L);
}
function syncBar(L) {
  for (const inp of W.bar.querySelectorAll("input[data-k]")) {
    if (document.activeElement === inp) continue;
    const k = inp.dataset.k;
    const v = k === "opacity" ? Math.round(L.opacity * 100) : L[k];
    inp.value = typeof v === "number" ? String(Math.round(v * 10) / 10) : v;
  }
}
function barInput(e) {
  const L = sel(), inp = e.target.closest("input[data-k]");
  if (!L || !inp) return;
  const k = inp.dataset.k, v = Number(inp.value);
  if (!Number.isFinite(v)) return;
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
  if (a === "lock") { checkpoint(); L.locked = !L.locked; W.bar.dataset.mode = ""; changed(); buildLeft(); }
  else if (a === "del") removeLayer(L);
}
function removeLayer(L) {
  if(L.locked)return;
  checkpoint();
  S.layers = S.layers.filter((x) => x !== L);
  S.assignments = (S.assignments??[]).filter(a=>a.layer!==L.id);
  if (S.selected === L.id) S.selected = null;
  changed(); buildLeft(); buildRight();
}

// a change to the project: redraw, recompute the projection, mark unsaved
function changed() {
  settleView();
  if(S.view==='burn'&&(drag&&['move','scale','rot'].includes(drag.kind)||editor?.drag?.kind==='pixels'))editor?.deferPreview();
  S.dirty = true;
  W?.dirty.classList.toggle("on", S.dirty);
  if (W) W.dirty.title = T().unsaved;
  editor?.invalidate();
  draw(); queueCompose();
  refreshLayerRows();
  $("next").disabled = !imageLayers().length && !S.assignments?.length; api.nextWhy?.(T().whyNoPicture);
}

// ---------------------------------------------------------------- canvas input
const pointers = new Map();
let drag = null, spaceDown = false;
function canvasPoint(e) { const r = W.surface.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }
const insideFocus = ([x, y]) => x >= focus.x && y >= focus.y && x <= focus.x + focus.w && y <= focus.y + focus.h;
function onDown(e) {
  if (!S) return;
  const p = canvasPoint(e), inside = insideFocus(p);
  pointers.set(e.pointerId, p);
  if (pointers.size === 2) {                // two fingers take over an unfinished selection/drawing
    editor?.cancelGesture();
    W.canvas.setPointerCapture(e.pointerId);
    const [a, b] = [...pointers.values()];
    drag = { kind: "pinch", d0: Math.hypot(a[0] - b[0], a[1] - b[1]), s0: V.s, c0: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], cx: V.cx, cy: V.cy };
    return;
  }
  if (inside && e.button===0 && !spaceDown && editor?.pointer("down",e,toMm(...p))) {e.preventDefault();return;}
  W.canvas.setPointerCapture(e.pointerId);
  if (e.button === 1 || spaceDown || S.tool === "pan" || !inside && e.button === 0) {
    drag = { kind: "pan", p0: p, cx: V.cx, cy: V.cy };
    W.cv.classList.add("panning");
    e.preventDefault();
    return;
  }
  if (e.button !== 0) return;
  const mm = toMm(...p);
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
    if (S.selected !== hit.id) { S.selected = hit.id; buildLeft(); buildRight(); }
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
  if(!drag&&!spaceDown&&editor?.pointer("move",e,toMm(...p)))return;
  if (S.loupe) loupeAt(p);
  if (!drag) return;
  if (drag.kind === "pinch" && pointers.size === 2) {
    followFit = false;
    const [a, b] = [...pointers.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]), c = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    const s = Math.min(Math.max(drag.s0 * d / drag.d0, Math.min(focus.w, focus.h) * 0.2 / 120), 4 / S.cell), k = s / drag.s0;
    V.s = s; V.cx = c[0] - (drag.c0[0] - drag.cx) * k; V.cy = c[1] - (drag.c0[1] - drag.cy) * k;
    viewChanged();
  } else if (drag.kind === "pan") {
    followFit = false;
    V.cx = drag.cx + p[0] - drag.p0[0]; V.cy = drag.cy + p[1] - drag.p0[1];
    viewChanged();
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
  if(!drag&&editor?.pointer(e.type==="pointercancel"?"cancel":"up",e,toMm(...canvasPoint(e))))return;
  if (drag?.kind === "pan") W.cv.classList.remove("panning");
  if (pointers.size < 2 && drag?.kind === "pinch") drag = null;
  if (!pointers.size) drag = null;
}
function onWheel(e) {
  e.preventDefault();
  followFit = false;
  const p = canvasPoint(e);
  // a pinch on a touchpad arrives as a wheel with Ctrl; a mouse wheel moves in whole notches
  const mouse = e.deltaMode === 1 || (e.deltaX === 0 && Math.abs(e.deltaY) >= 50 && Number.isInteger(e.deltaY));
  if (e.ctrlKey) zoomAt(Math.exp(-e.deltaY * 0.01), ...p);
  else if (mouse) zoomAt(e.deltaY < 0 ? 1.18 : 1 / 1.18, ...p);
  else { V.cx -= e.deltaX; V.cy -= e.deltaY; viewChanged(); }
}
function onKey(e) {
  if (!isOn() || !S) return;
  if (e.key === "Escape" && editor?.closeLayerActions()) { e.preventDefault(); e.stopPropagation(); return; }
  if (e.target.closest?.("input, select, textarea")) return;
  if (e.target.closest?.(".lay button") && (e.key === " " || isActionEnter(e))) return;
  if(!spaceDown&&editor?.key(e)){e.preventDefault();return;}
  const L = sel(), k = e.key;
  if (k === "Escape" && editor?.drag) {editor.cancelGesture();return;}
  if (k === "Escape" && S.activeMask) {checkpoint();S.activeMask=null;editor.invalidate();changed();editor.panels();return;}
  if (k === "F2" && L) {e.preventDefault();editor.h.rename(L.id);return;}
  if (e.altKey && ["ArrowUp","ArrowDown"].includes(k) && L && !L.locked) {e.preventDefault();editor.click({target:{closest:()=>({dataset:{edAction:k==="ArrowUp"?"up":"down"}})},preventDefault(){},stopPropagation(){}});return;}

  if (k === " " && !spaceDown) { spaceDown = true; W.cv.classList.add("pan"); e.preventDefault(); return; }
  if ((e.ctrlKey || e.metaKey) && (k === "z" || k === "Z")) { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
  if ((e.ctrlKey || e.metaKey) && (k === "y")) { e.preventDefault(); redo(); return; }
  if ((e.ctrlKey || e.metaKey) && (k === "s" || k === "S")) { e.preventDefault(); saveProject(e.shiftKey); return; }
  if ((e.ctrlKey || e.metaKey) && (k === "o" || k === "O")) { e.preventDefault(); pickProject(); return; }
  if ((e.ctrlKey || e.metaKey) && k.toLowerCase()==="j") {e.preventDefault();selectionEdit(e.shiftKey?"cut":"copy");return;}
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (k === "0") { fit(); return; }
  const zoomCentre = [focus.x + focus.w / 2, focus.y + focus.h / 2];
  if (k === "1") { zoomAt(1 / S.cell / V.s, ...zoomCentre); return; }
  if (k === "+" || k === "=") { e.preventDefault(); zoomAt(1.18, ...zoomCentre); return; }
  if (k === "-" || k === "_") { e.preventDefault(); zoomAt(1 / 1.18, ...zoomCentre); return; }
  if (k === "v" || k === "V") setTool("move");
  else if (k === "w" || k === "W") setTool("wand");
  else if (k === "h" || k === "H") setTool("pan");
  else if (k === "Escape") {
    if (L) { S.selected = null; buildLeft(); buildRight(); draw(); }
    else leave();
  } else if ((k === "Delete" || k === "Backspace") && L) {
    e.preventDefault();if(S.activeMask)selectionEdit("delete");else removeLayer(L);
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
  t=t==="shape"?(editor?.options.shape??"rectangleShape"):t==="wand"?"colour":t;
  if(editor?.drag&&editor.tool!==t)editor.cancelGesture();
  S.tool = t;
  if(editor){editor.tool=t;editor.toolbar();editor.optionsBar();}
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
  const rows = [...S.layers].reverse(), panel = editor?.panelState();
  if(panel?.layerActions!=null&&!S.layers.some(L=>L.id===panel.layerActions))panel.layerActions=null;
  const layerActions = panel?.layerActions;
  W.left.innerHTML = `<section><h3><span class="grow">${t.layers}</span>` +
    `</h3>` +
    (rows.length ? `<ul class="lays" role="listbox" aria-label="${t.layers}">${rows.map((L) => {
      const id = esc(L.id);
      return `<li class="lay${L.visible ? "" : " hid"}" role="option" draggable="true" data-id="${id}" aria-selected="${L.id === S.selected}">` +
      (L.kind === "fx" ? `<span class="fxmark">${I.fx}</span>` : `<span class="th"></span>`) +
      `<span class="nm"><span class="ed-layer-label">${esc(L.name)}${L.kind === "fx" ? `<small>${t.fxY(L.y1, L.y2)}</small>` : ""}</span>${L.locked?`<span class="ed-lock-mark" role="img" aria-label="${api.lang()==="zh"?"已锁定":"Locked"}" title="${api.lang()==="zh"?"已锁定":"Locked"}">${I.lock}</span>`:""}</span>` +
      `<button class="ib" type="button" data-a="vis" aria-label="${L.visible ? t.hide : t.show}" title="${L.visible ? t.hide : t.show}">${L.visible ? I.eye : I.eyeOff}</button>` +
      `<button class="ib" type="button" data-a="more" aria-label="${api.lang()==="zh"?"图层操作":"Layer actions"}" title="${api.lang()==="zh"?"图层操作":"Layer actions"}" aria-expanded="${layerActions===L.id}" aria-controls="ed-layer-actions-${id}"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></svg></button>` +
      `<div class="ed-layer-more" id="ed-layer-actions-${id}" role="group" aria-label="${api.lang()==="zh"?"图层操作":"Layer actions"}" ${layerActions===L.id?"":"hidden"}>` +
      `<button class="ib" type="button" data-a="lock" aria-label="${L.locked ? t.unlock : t.lock}" title="${L.locked ? t.unlock : t.lock}">${L.locked ? I.lock : I.unlock}</button><button class="ib" data-a="up" aria-label="${api.lang()==="zh"?"上移图层":"Raise layer"}" title="Alt+↑" ${L.locked?"disabled":""}><svg viewBox="0 0 24 24"><path d="M6 14l6-6 6 6M12 8v12"/></svg></button><button class="ib" data-a="down" aria-label="${api.lang()==="zh"?"下移图层":"Lower layer"}" title="Alt+↓" ${L.locked?"disabled":""}><svg viewBox="0 0 24 24"><path d="M6 10l6 6 6-6M12 4v12"/></svg></button><button class="ib" data-a="del" aria-label="${t.remove}" title="Delete" ${L.locked?"disabled":""}>${I.trash}</button></div></li>`;
    }).join("")}</ul>`
      : `<p class="empty-l">${t.noLayers}</p>`) +
    `<button class="sbtn wide" type="button" data-a="import">${I.image}${t.import}</button>` +
    `<button class="sbtn wide template-download" type="button" data-a="template" data-capability="templates" ${hasCapability('templates') ? '' : 'hidden'}>${api.lang() === "en" ? "Download template" : "下载模板"}</button></section>` +
    burnSection() +
    // files on the disc: the core cannot write them yet (`image` has no files, the ISO no entries), so the page
    // does not show them at all until it does (a column explaining a missing feature is noise)
    (!FILES_READY ? "" : `<section><h3>${t.files}</h3>` +
    (S.files ? `<p class="note">${esc(t.filesN(S.files.count, size(S.files.bytes)))}</p>` +
      `<div class="seg" role="group" aria-label="${t.files}"><button type="button" data-a="inner" aria-pressed="${S.files.where === "inner"}">${t.inner}</button><button type="button" data-a="outer" aria-pressed="${S.files.where === "outer"}">${t.outer}</button></div>` +
      `<p class="note quiet">${t.filesRing(...filesRing().map((r) => r.toFixed(1)))}</p>`
      : `<p class="note quiet">${t.filesNone}</p>`) +
    (S.media === "cd" ? `<p class="note quiet">${t.cdFiles}</p>` : "") +
    `<div class="row2"><button class="sbtn" type="button" data-a="folder">${I.folder}${t.pickFolder}</button>` +
    `<button class="sbtn" type="button" data-a="nofiles" ${S.files ? "" : "disabled"}>${t.clear}</button></div></section>`);
  for (const li of W.left.querySelectorAll(".lay")) {
    const L = layerRow(li);
    if (L.kind === "image") li.querySelector(".th").replaceWith(thumb(L));
  }
  editor?.left();
  mountFilesStep(W.left, {getFiles:()=>S.files, setFiles:value=>{S.files=value;queueMicrotask(refreshFilesHelp);},
    context:async()=>{const state=await api.backend.state();return {media:S.media,geo:planGeo(state).path,r_max:range()[1]};},
    onChange:changed, lang:api.lang(), media:S.media});
  refreshFilesHelp();
}
// Keep all original file guidance, showing the teaching sentence only while empty.
function refreshFilesHelp() {
  const section=W?.left.querySelector('.disc-files-step');if(!section)return;
  let help=section.querySelector('.ed-files-help');
  if(!help){help=document.createElement('details');help.className='ed-help ed-files-help';
    const summary=document.createElement('summary');summary.textContent=api.lang()==='en'?'About':'说明';help.append(summary);
    const limits=document.createElement('p');limits.className='note quiet';limits.textContent=T().limits+(S.media==='cd'?' '+T().cdLimit:'');help.append(limits);section.append(help);}
  const teaching=section.querySelector('.ed-files-teaching')??section.querySelector(':scope > p.note:not([data-files])');
  if(teaching){teaching.classList.add('ed-files-teaching');if(S.files)help.querySelector('summary').after(teaching);else section.querySelector('h3').after(teaching);}
}
// What the burn file will be: the grid (20 µm unless chosen), what a finer one costs, whether the pictures are
// fine enough for it, and what can't be burned yet. Said where the work is made, not only at the burn.
function burnKey() {
  const um = Math.round(S.cell * 1000), px = pictureSampling(S.layers);
  return [um, um < 20 && px && px > um * 1.05 ? Math.round(px) : 0, S.media, api.lang()].join("|");
}
function burnSection() {
  const t = T(), um = Math.round(S.cell * 1000), px = pictureSampling(S.layers);
  return `<section class="burnset" data-key="${burnKey()}"><h3>${t.grid}</h3>` +
    `<div class="seg" role="group" aria-label="${t.grid}">` +
    Object.keys(CELLS).map(Number).sort((a, b) => b - a).map((u) => `<button type="button" data-um="${u}" aria-pressed="${um === u}">${u} µm</button>`).join("") +
    `</div><p class="note quiet">${um === 20 ? (api.lang() === "en" ? "Default, about 2 min to make" : "默认，约 2 分钟生成") : t.cellCost(um, COST[um]).split(api.lang() === "en" ? ". " : "。")[0] + (api.lang() === "en" ? "." : "。")}</p>` +
    `<details class="ed-help"><summary>${api.lang() === "en" ? "About" : "说明"}</summary><p class="note quiet">${t.cellCost(um, COST[um])}</p>` +
    (um < 20 && px && px > um * 1.05 ? `<p class="note quiet">${t.coarse(Math.round(px))}</p>` : "") +
    `</details></section>`;
}
function refreshLayerRows() {
  for (const li of W?.left.querySelectorAll(".lay") ?? []) {
    const L = layerRow(li);
    if (!L) continue;
    li.setAttribute("aria-selected", String(L.id === S.selected));
    const small = li.querySelector("small");
    if (small && L.kind === "fx") small.textContent = T().fxY(L.y1, L.y2);
  }
  const burn = W?.left.querySelector(".burnset");
  if (burn && burn.dataset.key !== burnKey()) burn.outerHTML = burnSection();      // the picture's sampling follows its size
  const u = W?.tools.querySelector('[data-history="undo"]'), r = W?.tools.querySelector('[data-history="redo"]');
  if (u) u.disabled = !S.past.length;
  if (r) r.disabled = !S.future.length;
}
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const size = (b) => b > 1e9 ? `${(b / 1e9).toFixed(2)} GB` : b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.ceil(b / 1e3)} KB`;
function leftClick(e) {
  const b = e.target.closest("[data-a]"), li = e.target.closest(".lay");
  const L = li ? layerRow(li) : null;
  const a = b?.dataset.a;
  if (a === "undo") return undo();
  if (a === "redo") return redo();
  if (a === "import") return W.file.click();
  if (a === "template" && hasCapability('templates')) return downloadTemplate(S, b, toast);
  const um = Number(e.target.closest("[data-um]")?.dataset.um);
  if (CELLS[um] && um !== Math.round(S.cell * 1000)) { checkpoint(); S.cell = um / 1000; changed(); buildLeft(); buildRight(); return; }
  if(L && a === "more") { editor.toggleLayerActions(L.id); return; }
  if(L && ["up","down","del"].includes(a)){S.selected=L.id;editor.click({target:{closest:()=>({dataset:{edAction:a==="del"?"remove":a}})},preventDefault(){},stopPropagation(){}});return;}
  if (a === "folder") return W.folder.click();
  if (a === "nofiles") { S.files = null; changed(); buildLeft(); return; }
  if (a === "inner" || a === "outer") { S.files.where = a; changed(); buildLeft(); return; }
  if (L && a === "vis") { checkpoint(); L.visible = !L.visible; changed(); buildLeft(); return; }
  if (L && a === "lock") { checkpoint(); L.locked = !L.locked; if (W.bar) W.bar.dataset.mode = ""; changed(); buildLeft(); return; }
  if (L) { S.selected = L.id; refreshLayerRows(); buildRight(); draw(); }
}
function leftDbl(e) {
  const li = e.target.closest(".lay");
  if (!li || e.target.closest("button")) return;
  const L = layerRow(li), nm = li.querySelector(".nm");
  const inp = document.createElement("input");
  inp.value = L.name; inp.className = "num"; inp.style.textAlign = "left";
  nm.replaceWith(inp); inp.focus(); inp.select();
  let finished=false;
  const done = (ok) => { if(finished)return;finished=true;if (ok && inp.value.trim() && inp.value !== L.name) { checkpoint(); L.name = inp.value.trim(); } buildLeft(); };
  inp.addEventListener("keydown", (ev) => { if (isActionEnter(ev)) { ev.preventDefault(); done(true); } if (ev.key === "Escape") done(false); ev.stopPropagation(); });
  inp.addEventListener("blur", () => done(true));
}
// drag a row to change the stacking order (top of the list is drawn on top)
let dragRow = null;
function leftDrag(e) {
  const li = e.target.closest?.(".lay");
  if(e.type==="dragstart"&&li&&S.layers.find(l=>String(l.id)===li.dataset.id)?.locked){e.preventDefault();return;}
  if (e.type === "dragstart" && li) { dragRow = layerRow(li); li.classList.add("drag"); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", li.dataset.id); }
  else if (e.type === "dragover" && li && dragRow !== null) { e.preventDefault(); for (const x of W.left.querySelectorAll(".over")) x.classList.remove("over"); li.classList.add("over"); }
  else if (e.type === "drop" && li && dragRow !== null) {
    e.preventDefault();
    const from = S.layers.indexOf(dragRow), target = S.layers.indexOf(layerRow(li));
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
  return `<div class="ctl"><label for="${id}">${label}</label><input class="num" id="${id}-n" type="number" min="${min}" max="${max}" step="${step}" value="${esc(value)}" data-k="${id}">` +
    `<input class="rng" id="${id}" type="range" min="${min}" max="${max}" step="${step}" value="${esc(value)}" data-k="${id}"></div>`;
}
function buildRight() {
  if(editor){editor.right();return;}
  if (!W) return;
  const t = T(), tone = S.tone, L = sel();
  const proSw = `<div class="pro-sw"><span class="lbl"><span class="pr">PRO</span>-Experimental</span>` +
    `<button class="sw" type="button" role="switch" aria-checked="${S.pro}" aria-label="${t.proAria}" data-a="pro"></button></div>`;
  const toneS = `<section><h3>${t.tone}</h3>` +
    slider("dither", t.dither, 0, 100, 1, tone.dither) + slider("bright", t.bright, -64, 64, 1, tone.bright) +
    `<div class="ctl-line"><span>${t.levels}</span><div class="seg" role="group" aria-label="${t.levels}">` +
    `<button type="button" data-lv="2" aria-pressed="${tone.levels === 2}">${t.lv(2)}</button>` +
    `<button type="button" data-lv="4" aria-pressed="${tone.levels === 4}" ${S.media === "cd" ? "" : `disabled title="${t.lv4}"`}>${t.lv(4)}</button></div></div>` +
    // the rule is in the button's own words now ("4 · preview only"); its title says the rest
    `<label class="chk"><input type="checkbox" data-k="lin" ${tone.lin ? "checked" : ""}>${t.lin}</label>` +
    (S.media === "bd" ? `<label class="chk"><input type="checkbox" data-k="inv" ${tone.inv ? "checked" : ""}>${t.inv}</label>` : "") +
    `<details class="more"><summary>${t.more}</summary><div>` +
    `<div class="ctl-line"><button class="sbtn" type="button" data-a="auto">${tone.auto ? t.autoOff : t.auto}</button><span class="note quiet">${Array.isArray(tone.auto) ? esc(t.autoOn(...tone.auto)) : ""}</span></div>` +
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
function stopPlay() { clearInterval(S?.playing); if (S) { S.playing = 0; S.playPaused = false; S.playTick = null; } }
function togglePlay() {
  if (S.playing || S.playPaused) { stopPlay(); updateTilt(); return; }
  let dir = 1, n = 0;
  S.playTick = () => {
    S.lookY += dir * 1.5;
    if (S.lookY > 115 || S.lookY < 45) { dir = -dir; n++; }
    if (n >= 6) stopPlay();
    updateTilt(); draw();
  };
  S.playing = setInterval(S.playTick, 60);
  updateTilt();
}

// ---------------------------------------------------------------- saving and opening a project
// One JSON file holds everything: each picture as the working copy (with what the selection tool
// removed) and, when it came from a file, the original file too, so export can use full size.
const FILE_KIND = "disc-probe design", FILE_VERSION = 2, FILE_EXT = ".discdesign";
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
  const portable = editor?.document();
  return JSON.stringify({
    ...portable,
    format: FILE_KIND, version: FILE_VERSION, media: S.media, disc: S.item?.name ?? null, geo: S.geo ?? null,
    batch: S.item?.kind !== "new" ? S.item?.id ?? null : null,
    tone: S.tone, files: fileDisplay(S.files), pro: S.pro, cell: S.cell, scene: S.scene, lookColour: S.lookColour, lookY: S.lookY, layers: layers.map((l,i)=>({...l,...portable?.layers[i]})),
  });
}
const baseName = (n) => n.replace(/\.discdesign$/i, "").replace(/\.json$/i, "");
// Ctrl+S files the design in the core's works library (pastworks/save.mjs: made on the first save, a 409
// asks overwrite or keep both). Undefined when this core keeps no works: the file picker below saves it.
async function saveToWorks() {
  const client = await (await import("./pastworks/works.mjs")).worksFor(api, { capable: hasCapability("works") });
  if (!client) return undefined;
  const { saveToLibrary, sayings } = await import("./pastworks/save.mjs");
  const plan = S, name = S.name ?? T().untitled;
  try {
    const r = await saveToLibrary({ client, plan, name, lang: api.lang(), text: await projectText(),
      thumb: async () => dataURLBlob(planThumbnail(plan, 512)) });
    if (!r) return false;
    plan.name = r.work.name ?? name; plan.dirty = false;
    if (plan === S) { W.dirty.classList.remove("on"); W.pname.textContent = S.name; }
    toast(r.note);
    return true;
  } catch (e) { toast(sayings(api.lang()).failed + (e?.message ?? e)); return false; }
}
// An ISO belongs to a library work: the plan is saved first (made on its first save; unsaved edits filed) so
// the work's design is what the disc carries; the image job then takes its id and the core records the ISO
// and sets iso_ready when the job succeeds. Null when this core keeps no works.
async function workForISO() {
  const client = await (await import("./pastworks/works.mjs")).worksFor(api, { capable: hasCapability("works") });
  if (!client || client.mock) return null;                  // the demo's library cannot hear the core's job
  const plan = S;
  if (!plan.work?.id || plan.dirty) {
    if (!await saveToWorks()) throw new Error(T().failed);
    document.dispatchEvent(new Event("dp-image-work-saved"));
  }
  return plan.work?.id ? { id: plan.work.id, before: plan.work.updated_at, plan } : null;
}
// after a successful ISO: the geometry it was made with, and the stamps the core moved (pastworks/save.mjs)
async function afterWorkISO(link, geo) {
  try {
    const client = await (await import("./pastworks/works.mjs")).worksFor(api, { capable: hasCapability("works") });
    await (await import("./pastworks/save.mjs")).afterISO({ client, plan: link.plan, before: link.before, geo });
  } catch { /* the ISO is made; the record is the core's */ }
}
async function saveProject(as = false) {
  const t = T();
  if (!S.layers.length && !S.assignments?.length) { toast(t.exp.empty); return false; }
  if (!as) { const saved = await saveToWorks(); if (saved !== undefined) return saved; }
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
// work: { id, updated_at } when the text came from the works library; a file opened from disk is no library work
async function openProject(file, handle = null, work = null, dirty = false) {
  const t = T();
  let data;
  // a work with a few photos is tens of MB (each layer keeps its pixels, its PNG and the original file)
  if (file.size > OPEN_LIMIT) { toast(t.tooLarge(file.name, Math.round(file.size / 2 ** 20)), 8000); return; }
  try { data = JSON.parse(await file.text()); } catch { toast(t.notProject(file.name)); return; }
  if (data?.format !== FILE_KIND || !Array.isArray(data.layers)) { toast(t.notProject(file.name)); return; }
  if (data.version > FILE_VERSION) { toast(t.newer(file.name)); return; }
  if (data.layers.length > 16) { toast(t.notProject(file.name)); return; }
  const layers = [], lost = [], layerIds = new Map(), usedIds = new Set();
  const validId = (id) => (typeof id === "string" || Number.isSafeInteger(id)) && /^[A-Za-z0-9_-]{1,64}$/.test(String(id));
  const reservedIds = new Set(data.layers.map(e => e?.id).filter(validId).map(String));
  for (const e of data.layers) {
    if (!e || typeof e !== "object") { lost.push({}); continue; }
    let id = e.id;
    if (!validId(id) || usedIds.has(String(id))) {
      while (reservedIds.has(String(nextId)) || usedIds.has(String(nextId))) nextId++;
      id = nextId++;
    }
    usedIds.add(String(id));
    const base = { id, kind: e.kind === "fx" ? "fx" : "image", name: String(e.name ?? ""), x: +e.x || 0, y: +e.y || 0,
      width: Math.max(1, +e.width || 1), rot: +e.rot || 0, opacity: Math.min(1, Math.max(0, e.opacity ?? 1)), visible: e.visible !== false, locked: !!e.locked };
    if (base.kind === "fx") {
      if (!["flow", "ox", "merge", "sync"].includes(e.fxKind)) continue;
      layers.push({ ...base, fxKind: e.fxKind, height: Math.max(1, +e.height || 1), y1: +e.y1 || 70, y2: +e.y2 || 70 });
      if (e.id != null && !layerIds.has(e.id)) layerIds.set(e.id, id);
      continue;
    }
    try {
      const c = document.createElement("canvas");
      let bmp;
      if(e.raster){c.width=e.raster.width;c.height=e.raster.height;}
      else if(e.shape&&!e.picture){
        const exact = e.shape.directionArrow === true && [e.w, e.h].every(n => Number.isInteger(n) && n > 0 && n <= MAX_SIDE);
        c.width=exact?e.w:512;c.height=exact?e.h:Math.max(1,Math.round(512*(e.height??e.width)/e.width));
      }
      else {bmp=await createImageBitmap(dataURLBlob(e.picture));c.width=bmp.width;c.height=bmp.height;}
      const g = c.getContext("2d", { willReadFrequently: true });
      if(e.raster)g.putImageData(new ImageData(new Uint8ClampedArray(EditorOps.bytes(e.raster.rgba)),c.width,c.height),0,0);
      else if(bmp){g.drawImage(bmp,0,0);bmp.close?.();}
      else drawShape(g, e.shape, e.shape.directionArrow === true ? directionArrow.material.rgb : undefined);
      const L = { ...base, w: c.width, h: c.height, colour: e.colour ?? "none", alphaEdited: !!e.alphaEdited, px: g.getImageData(0, 0, c.width, c.height), src: c, version: 1 };
      Object.assign(L,{sourceKind:e.sourceKind,shape:e.shape,svg:e.svg,tone:e.tone});
      if (typeof e.original === "string" && e.original.startsWith("data:image/")) L.file = dataURLBlob(e.original);
      layers.push(L);
      if (e.id != null && !layerIds.has(e.id)) layerIds.set(e.id, id);
    } catch { lost.push(e); }               // one unreadable picture: open the rest and say which
  }
  if (data.layers.length && lost.length === data.layers.length) { toast(t.notProject(file.name)); return; }
  checkpoint();
  S.layers = layers.slice(0, 16);
  S.selections=structuredClone(data.selections??[]);S.activeMask=data.activeMask??null;
  // fills of a layer that is gone would make the export refuse the whole work
  const kept = new Set(S.layers.map((l) => l.id));
  S.assignments = (data.assignments ?? []).filter(a => a && typeof a === "object")
    .map(a => a.layer === undefined ? a : {...a, layer:layerIds.get(a.layer) ?? null})
    .filter(a => a.layer === undefined || kept.has(a.layer));
  S.maskGrid=structuredClone(data.maskGrid??EditorOps.grid());S.materials=data.materials?structuredClone(data.materials):null;
  editor?.init();editor?.invalidate();
  S.selected = null;
  S.files = fileDisplay(data.files);
  for (const k of ["pro", "lookColour"]) if (k in data) S[k] = !!data[k];
  if (data.tone) S.tone = { ...DEFAULT_TONE, ...data.tone };
  if (data.scene) S.scene = { ...S.scene, ...data.scene };
  if (data.media === S.media && Array.isArray(data.annulus_mm) && editor?.hasColour()) S.ring = data.annulus_mm;
  S.cell = [0.02, 0.01, 0.005].includes(data.cell) ? data.cell : 0.02;      // the work's grid, else the default
  if (typeof data.geo === "string" && data.media === S.media) S.geo = data.geo;      // checked against the catalogue at export
  if (Number.isFinite(data.lookY)) S.lookY = data.lookY;
  else if (editor?.hasColour() && editor.rigSet()) S.lookY = editor.rigSet().camera[1];
  if (editor?.hasColour()) editor.rigSync();
  S.name = baseName(file.name); S.handle = handle; S.work = work;
  changed();
  S.dirty = dirty; W.dirty.classList.toggle("on", dirty);
  W.ws.classList.toggle("pro-on", S.pro);
  W.pname.textContent = S.name;
  buildLeft(); buildRight(); updateTilt();
  fit();
  if (lost.length) { S.dirty = true; W.dirty.classList.add("on"); }
  toast([data.media && data.media !== S.media ? t.otherMedia(data.media.toUpperCase(), S.media.toUpperCase()) : t.opened(work ? S.name : file.name),
    lost.length ? t.lost(lost.map((e) => `“${String(e.name ?? "?")}”`).join(api.lang() === "en" ? ", " : "、")) : ""].filter(Boolean).join(" "), lost.length ? 12000 : 2600);
}
const OPEN_LIMIT = 400 * 2 ** 20;
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
  // let the stage show first; a page in a background tab gets no frames, so a timer goes on without one
  await new Promise((r) => { let go = () => { go = () => {}; setTimeout(r, 0); }; requestAnimationFrame(() => go()); setTimeout(() => go(), 100); });
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
// The burn file's name from the plan's: letters of any script, digits, _ and -, joined by -; never starting
// with - (the core refuses such a path, and the default Chinese plan name begins with one once spaces go)
export function isoStem(name) {
  return String(name ?? "").replace(/[^\p{L}\p{N}_-]+/gu, "-").replace(/^-+|-+$/g, "").slice(0, 40).replace(/-+$/, "") || "design";
}
// Draw the design, hand it to the back end and run `image`; resolves with the ISO's path and size.
// onProgress({ stage, fraction }) — fraction is null while unknown.
// effects: "bw" (default) burns colours, colour patterns and effects as plain dark areas; "experimental" (DVD
// only) burns the textures the model chose. Either way the result says which, and which geometry it used.
export async function makeBurnFile(onProgress = () => {}, { signal, effects } = {}) {
  const t = T().exp, t2 = T();
  const plan = S;
  const stop = () => { if (signal?.aborted) throw new DOMException("cancelled", "AbortError"); };
  let files = plan.files;
  if (files?.folder && !files.token) throw Error(api.lang() === "en" ? "Check and confirm the files list before exporting." : "请先检查并确认随盘文件清单。");
  let state;
  try { const r = await fetch(`/api/state?media=${S.media}`, { signal }); if (!r.ok) throw 0; state = await r.json(); }
  catch (e) { if (e?.name === "AbortError") throw e; throw new Error(t.noBackend); }
  if (S !== plan) throw new DOMException("cancelled", "AbortError");
  const geo = planGeo(state), geoPath = geo.path;
  if (!geoPath) throw Object.assign(new Error(t.noGeo), { code: "nogeo" });
  useMeasured(geo);                                    // the burn file keeps the picture inside the measured ring
  if (files?.folder) {
    const current = await refreshFiles(files,{media:S.media,geo:geoPath,r_max:range()[1]});
    if (S !== plan || plan.files !== files) throw Error(api.lang() === "en" ? "The files selection changed." : "随盘文件选择已改变。");
    plan.files=files=current;
    buildLeft(); draw();
  }
  const um = Math.round(S.cell * 1000);
  if (!CELLS[um]) throw new Error(t2.exp2.noCell);
  let saved, rMax, burn = null;
  if(editor){
    onProgress({stage:t.drawing,fraction:null});
    burn = burnDocument(editor.document(), S.media, effects);
    const body = JSON.stringify(burn.doc);
    if (body.length > COMPOSE_LIMIT) throw new Error(t2.bigWork(Math.round(body.length / 2 ** 20)));
    const response=await fetch("/api/compose",{method:"POST",headers:{"Content-Type":"application/json"},body,signal});
    saved=await response.json().catch(()=>({}));if(!response.ok)throw Error(localImageError(saved.error)||t.failed);rMax=pictureRange()[1];
    // what the composed array really holds: in black and white, nothing but the two textures
    const extra = checkTextures(saved.textures_used ?? saved.textures, S.media, burn.mode);
    if (extra.length) throw new Error(t2.exp2.bwOnly(extra.join(" ")));
  }else{
  const { bits, rMax:rm } = await designBits((stage) => onProgress({ stage, fraction: null }));rMax=rm;
  stop();
  onProgress({ stage: t.sending, fraction: null });
  const up = await fetch("/api/design", { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: bits });
  saved = await up.json().catch(() => ({}));
  if (!up.ok) throw new Error(saved.error ?? t.failed);
  }
  stop();
  if (S !== plan) throw new DOMException("cancelled", "AbortError");
  const stamp = new Date().toISOString().replace(/\D/g, "").slice(0, 14);
  const output = `iso/${isoStem(plan.name)}-${um}um-${stamp}-${crypto.randomUUID().slice(0, 8)}${burn?.mode === "experimental" ? "-exp" : ""}.iso`;
  const link = await workForISO();
  stop();
  if (files?.token && (S !== plan || plan.files !== files))
    throw Error(api.lang() === "en" ? "The files selection changed." : "随盘文件选择已改变。");
  onProgress({ stage: t.making, fraction: 0 });
  const filesToken = files?.token;
  if (filesToken) {
    delete files.token;
    delete files.layout.review;
    buildLeft();
  }
  const run = await fetch("/api/run", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "image", media: plan.media, ...(link ? { work: link.id } : {}), ...(filesToken ? {files_token:filesToken} : {}), args: { geo: geoPath, design_npy: saved.design_npy, ...(saved.textures?{textures:saved.textures}:{}), ...fileArguments(files), output, r_max: rMax } }),
  });
  const job = await run.json().catch(() => ({}));
  if (!run.ok) throw new Error(localImageError(job.error) || t.failed);
  onProgress({ stage: t.making, fraction: 0, jobId: job.job });
  let why = "", lastLine = "";
  const exit = await new Promise((resolve, reject) => {
    const es = new EventSource("/api/events");
    signal?.addEventListener("abort", () => {          // stop the back end's job too
      es.close();
      fetch(`/api/jobs/${job.job}/cancel`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).catch(() => {});
      reject(new DOMException("cancelled", "AbortError"));
    }, { once: true });
    const mine = (e) => { const d = JSON.parse(e.data); return d.job === job.job ? d : null; };
    es.addEventListener("progress", (e) => { const d = mine(e); if (d) onProgress({ stage: t.making, fraction: d.fraction ?? null }); });
    // what the core said last, so a failure says why (the error event if there is one, else its last line)
    es.addEventListener("error", (e) => { if (!e.data) return; const d = mine(e); if (d?.message) why = d.message; });
    es.addEventListener("log", (e) => { const d = mine(e); if (d?.text && !/^\s*$/.test(d.text)) lastLine = d.text; });
    es.addEventListener("done", (e) => { const d = mine(e); if (d) { es.close(); resolve(d.exit); } });
  });
  if (exit !== 0) {
    const said = why || lastLine || (await jobWords(job.job)).why;
    // the core's coverage gate, said in the page's words (it should not happen: the ring is cut to the measurement)
    if (/EXTRAPOLATION|outside measured intervals|外推/.test(said ?? "")) throw new Error(api.lang() === "zh"
      ? "图有一部分超出这批盘实测到的范围，那里的位置不可信。把图缩进圈内，或者重测这张盘、把范围测宽；不用重刻。"
      : "Part of the picture is outside the range this batch was measured over, where positions are a guess. Shrink it inside the ring, or measure this disc again over a wider range; no new burn is needed.");
    throw new Error([t.failed, localImageError(said)].filter(Boolean).join(" "));
  }
  stop();
  const info = await (await fetch(`/api/iso?path=${encodeURIComponent(output)}`)).json().catch(() => ({}));
  if (!(info.bytes > 0) || !(info.sectors > 0)) throw new Error(t.failed);
  plan.geo = geoPath;                                  // the project keeps the geometry it was made with
  if (link) await afterWorkISO(link, geoPath);
  return { path: info.path ?? output, bytes: info.bytes, sectors: info.sectors, job: job.job, geo: geoPath,
    geoSource: geo.source, geoName: geo.name, cellUm: um, effects: burn?.mode ?? "bw", experimental: burn?.mode === "experimental",
    textures: saved.textures_used ?? null };
}
function localImageError(message) {
  if (!message) return "";
  const bilingual = String(message).split(" / ");
  if (bilingual.length === 2 && /[\u3400-\u9fff]/.test(bilingual[0])) return bilingual[api.lang() === "en" ? 1 : 0];
  return api.lang() === "en" || /^\s*[\u3400-\u9fff]/.test(message) ? message : "";
}
// The check disc (checkdisc.py): the photo target, laid out with this plan's measured geometry and without any
// photo correction, since its photos are what measure it. Burned, photographed, then the picture's own file is
// made again and the core applies the along-track correction from those photos.
async function makeCheckFile(onProgress, { signal } = {}) {
  const t = T();
  const state = await api.backend.state().catch(() => null);
  const geo = planGeo(state), geoPath = geo.path;
  if (!geoPath) throw Object.assign(new Error(t.noGeo), { code: "nogeo" });
  const stamp = new Date().toISOString().replace(/\D/g, "").slice(0, 14);
  const output = `iso/check-${stamp}.iso`;
  onProgress({ stage: t.making, fraction: 0 });
  const run = await fetch("/api/run", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "checkdisc", media: S.media, args: { geo: geoPath, output } }) });
  const job = await run.json().catch(() => ({}));
  if (!run.ok) throw new Error(job.error ?? t.failed);
  let why = "", lastLine = "";
  const exit = await new Promise((resolve, reject) => {
    const es = new EventSource("/api/events");
    signal?.addEventListener("abort", () => {
      es.close();
      fetch(`/api/jobs/${job.job}/cancel`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).catch(() => {});
      reject(new DOMException("cancelled", "AbortError"));
    }, { once: true });
    const mine = (e) => { const d = JSON.parse(e.data); return d.job === job.job ? d : null; };
    es.addEventListener("progress", (e) => { const d = mine(e); if (d) onProgress({ stage: t.making, fraction: d.fraction ?? null }); });
    es.addEventListener("error", (e) => { if (!e.data) return; const d = mine(e); if (d?.message) why = d.message; });
    es.addEventListener("log", (e) => { const d = mine(e); if (d?.text && !/^\s*$/.test(d.text)) lastLine = d.text; });
    es.addEventListener("done", (e) => { const d = mine(e); if (d) { es.close(); resolve(d.exit); } });
  });
  if (exit !== 0) throw new Error([t.failed, why || lastLine || (await jobWords(job.job)).why].filter(Boolean).join(" "));
  const info = await (await fetch(`/api/iso?path=${encodeURIComponent(output)}`)).json().catch(() => ({}));
  if (!(info.bytes > 0) || !(info.sectors > 0)) throw new Error(t.failed);
  return { path: info.path ?? output, bytes: info.bytes, sectors: info.sectors, job: job.job, geo: geoPath,
    geoSource: geo.source, geoName: geo.name, target: true, effects: "bw" };
}
const COMPOSE_LIMIT = 384 * 2 ** 20;                   // webui.COMPOSE_BYTES
// Which measured geometry this plan's burn file is made from (export-rules.geoChoice): its batch's own
// measurement, an imported preset, or, only for a plan with no batch, its earlier one or the newest, named.
const latestGeo = (state) => { const x = state?.steps?.find((s) => s.id === "geo"); return x?.done && x.result ? x.result : null; };
const planGeo = (state, plan = S) => geoChoice(plan, state?.catalogue?.[plan.media] ?? [], latestGeo(state));
export const projectGeo = (state, plan = S) => planGeo(state, plan).path;

// ---------------------------------------------------------------- building the page
function viewNote(){
  const lamp=S.view==='lamp',zh=api.lang()==='zh';
  const phase=editor?.lamp?.phase,note=W.cv.querySelector('.ed-view-note');
  const colour=editor?.hasColour(),compare=W.view.querySelector('[data-colour-compare]');
  compare.hidden=!(lamp&&colour);
  compare.textContent=zh?'对照':'Compare';
  compare.title=zh?'左边原图，右边预测':'Original on the left, prediction on the right';
  compare.setAttribute('aria-pressed',String(!!(colour&&editor.panelState().compare)));
  if(colour&&(lamp||S.view==='burn')){
    const preview=editor.colourRenderer,ready=preview?.phase==='ready'&&preview.frame?.view===S.view&&preview.frame.rev===editor.revision;
    note.textContent=preview?.phase==='error'?(zh?'预览未完成：':'Preview failed: ')+preview.error:
      ready?(lamp?(editor.panelState().compare?compare.title:editor.poseNote()):(zh?'刻出来 · 纹理分布':'As burned · texture placement')):
        lamp?(zh?'正在按机位预测颜色…':'Predicting colours for this shooting position…'):(zh?'正在合成刻录纹理…':'Composing burn textures…');
    if(ready&&lamp&&S.assignments.some(a=>a.colour?.table?.fitted))note.textContent+=` · ${editor.colourWords.unseen}`;
    note.setAttribute('aria-busy',String(!ready&&preview?.phase!=='error'));
    return;
  }
  const exact=S.view==='burn'&&editor?.exact?.phase;
  if(colour&&S.view==='proj'){
    note.textContent=zh?'设计 · 原图；到“灯下”看机位预测':'Design · original picture. See Under the lamp for the prediction.';
    note.setAttribute('aria-busy','false');return;
  }
  if(exact&&exact!=='off'){note.textContent=exact==='computing'?(zh?'正在算刻录格子…':'Working out the burn cells…'):exact==='error'?(zh?'刻录格子没算出来：':'Burn cells failed: ')+(editor.exact.error??''):(zh?'刻录格子 · 这里就是刻进去的格子':'Burn cells · these are the cells that are burned');note.setAttribute('aria-busy',String(exact==='computing'));return;}
  note.textContent=lamp?(phase==='ready'?(editor?.poseNote?.()??(zh?'模型预测':'Model prediction')):phase==='error'?(zh?'预览未完成 · 再点“灯下”重试':'Preview failed · click Under the lamp to retry'):phase==='refining'?(zh?'低清预览 · 正在计算细采样…':'Quick preview · rendering fine samples…'):(zh?'正在计算灯下预览…':'Rendering under the lamp…')):S.view==='burn'?(zh?'刻出来 · 哪里刻哪种纹理，细格子按肉眼混合；放大看刻录格子，真实颜色看“灯下”':'As burned · which texture goes where, fine cells mixed as the eye sees them; zoom in for the cells, Under the lamp for the colours'):(zh?'设计 · 原图（灰度），刻录区外压暗；看刻出来的样子点“刻出来”':'Design · the picture itself (grey); outside the burnable ring dimmed. See the burned result under As burned');
  note.setAttribute('aria-busy',String(lamp&&!['ready','error'].includes(phase)));
}
function build() {
  const t = T();
  const css = document.createElement("link");
  css.rel = "stylesheet"; css.href = new URL("./design.css", import.meta.url).href;
  document.head.append(css);
  const ws = document.createElement("div");
  ws.className = "ws";
  ws.innerHTML = `<div class="ws-title"><svg class="work-bag" viewBox="0 0 20 24" width="16" height="20" style="flex-shrink:0;fill:none;stroke:currentColor;stroke-width:1.3" role="img" aria-label="作品存在往期作品里 / Saved in past works"><title>作品存在往期作品里 / Saved in past works</title><path d="M3 5h14v17H3zM3 5l3-3h8l3 3M7 9h6M7 12h6"/></svg><b class="pname"></b><button class="sub" type="button"></button><span class="dirty" aria-hidden="true"></span>` +
    `<span class="filebtns"><button class="sbtn" type="button" data-a="open"></button><button class="sbtn" type="button" data-a="save"></button></span></div>` +
    `<div class="ed-panel-picker"><button class="sbtn" type="button" aria-expanded="false" aria-controls="ed-left ed-files" data-panel="layers"></button><button class="sbtn" type="button" aria-expanded="false" aria-controls="ed-right" data-panel="tone"></button></div>` +
    `<aside class="col col-l" id="ed-left"></aside><aside class="col col-r" id="ed-right"></aside>` +
    `<div class="cv"><div class="ed-desk" aria-hidden="true"></div><div class="ed-surface"><div class="ed-disc-shadow" aria-hidden="true"></div><canvas class="main"></canvas></div>` +
    `<div class="tools-v" role="toolbar"></div>` +
    `<div class="seg viewsw" role="group"><button type="button" data-v="proj"></button><button type="button" data-v="burn"></button><button type="button" data-v="lamp"></button><button type="button" data-colour-compare hidden></button></div><p class="ed-view-note" aria-live="polite"></p>` +
    `<p class="cv-note warn" hidden></p>` +
    `<div class="empty-c"><p></p><div class="row"><button class="sbtn" type="button" data-a="sample"></button><button class="sbtn" type="button" data-a="import"></button></div></div>` +
    `<div class="fbar" hidden></div>` +
    `<div class="tilt"><span class="lbl"></span><input class="rng" type="range" min="40" max="120" step="1"><output></output><button class="sbtn" type="button"></button></div>` +
    `<div class="loupe"><canvas></canvas><small></small></div>` +
    `<button class="zoomr" type="button"></button><div class="dropzone"></div></div>` +
    `<input type="file" accept="image/png,image/jpeg,image/webp,image/bmp,image/svg+xml" multiple hidden class="f-img"><input type="file" webkitdirectory multiple hidden class="f-dir">` +
    `<input type="file" accept="${FILE_EXT},.json,application/json" hidden class="f-proj">`;
  document.body.append(ws);
  const q = (s) => ws.querySelector(s);
  W = {
    ws, left: q(".col-l"), right: q(".col-r"), cv: q(".cv"), canvas: q("canvas.main"), tools: q(".tools-v"), view: q(".viewsw"),
    desk: q(".ed-desk"), surface: q(".ed-surface"), shadow: q(".ed-disc-shadow"),
    note: q(".cv-note"), empty: q(".empty-c"), bar: q(".fbar"), tilt: q(".tilt"), loupe: q(".loupe"), zoom: q(".zoomr"),
    drop: q(".dropzone"), file: q(".f-img"), folder: q(".f-dir"), dirty: q(".dirty"), pname: q(".pname"), sub: q(".ws-title .sub"), proj: q(".f-proj"), filebtns: q(".filebtns"),
  };
  // open and save belong to the work's tools, above the layers, not to its title (the header keeps only the
  // work's name and its discs)
  ws.append(W.filebtns);
  W.filebtns.id = "ed-files";
  W.panelPicker = q(".ed-panel-picker");
  W.panelPicker.addEventListener("click", e => {
    const button = e.target.closest("[data-panel]");
    if (!button) return;
    ws.dataset.panel = ws.dataset.panel === button.dataset.panel ? "" : button.dataset.panel;
    for (const b of W.panelPicker.children) b.setAttribute("aria-expanded", String(b.dataset.panel === ws.dataset.panel));
  });
  // Keep the existing glass panel's shadow beneath the picture, as it was before the canvas
  // extended behind the panels. Its opaque face alone belongs above the picture.
  ws.prepend(W.desk);
  const panelShadow = document.createElement("div");
  panelShadow.className = "ed-panel-shadow"; panelShadow.setAttribute("aria-hidden", "true");
  ws.prepend(panelShadow);
  // canvas input
  const cvs = W.canvas;
  observeActivity(cvs, active => {
    canvasActive = active;
    if (!active) {
      editor?.lamp?.pause();
      if (S?.playing) { clearInterval(S.playing); S.playing = 0; S.playPaused = true; }
    } else {
      if (S?.playPaused && S.playTick) { S.playPaused = false; S.playing = setInterval(S.playTick, 60); }
      draw();
    }
  });
  cvs.addEventListener("pointerdown", onDown);
  cvs.addEventListener("pointermove", onMove);
  cvs.addEventListener("pointerup", onUp);
  cvs.addEventListener("pointercancel", onUp);
  cvs.addEventListener("pointerleave", () => W.loupe.classList.remove("on"));
  cvs.addEventListener("pointerenter", () => W.loupe.classList.toggle("on", !!S?.loupe));
  cvs.addEventListener("wheel", onWheel, { passive: false });
  let temporaryTool=null;
  addEventListener("keydown",e=>{
    if(!isOn()||!S||e.isComposing||e.ctrlKey||e.metaKey||e.altKey||e.target.closest?.("input,select,textarea,[contenteditable=true]"))return;
    if(e.key===" "&&e.target.closest?.(".lay button"))return;
    if(e.key===" "){if(!e.repeat&&temporaryTool===null){temporaryTool=S.tool;editor.cancelGesture();spaceDown=true;setTool("pan");}e.preventDefault();e.stopPropagation();return;}
    const t=({v:"move",r:"rectangle",f:"lasso",c:"ring",g:"sector",w:"colour",y:"shape",n:"pen",h:"pan"})[e.key.toLowerCase()];
    if(t&&!e.shiftKey){if(!e.repeat){editor.cancelGesture();setTool(t);}e.preventDefault();e.stopPropagation();}
  },true);
  addEventListener("keyup",e=>{if(e.key===" "&&temporaryTool!==null){const t=temporaryTool;temporaryTool=null;spaceDown=false;setTool(t);e.preventDefault();e.stopPropagation();}},true);
  addEventListener("blur",()=>{if(temporaryTool!==null){const t=temporaryTool;temporaryTool=null;spaceDown=false;setTool(t);}});
  addEventListener("keydown", onKey);
  addEventListener("keyup", onKeyUp);
  W.zoom.addEventListener("click", () => { if (!followFit) fit(); else zoomAt(1 / S.cell / V.s, focus.x + focus.w / 2, focus.y + focus.h / 2); });
  W.view.addEventListener("click", (e) => {
    if(e.target.closest('[data-colour-compare]')){
      const state=editor.panelState();state.compare=!state.compare;viewNote();draw();return;
    }
    const b = e.target.closest("[data-v]");
    if (!b) return;
    S.view = b.dataset.v;
    editor?.colourRenderer?.retry();
    if(S.view==='lamp'&&editor?.lamp?.phase==='error')editor.lamp.retry();
    for (const x of W.view.querySelectorAll('[data-v]')) x.setAttribute("aria-pressed", String(x.dataset.v === S.view));
    viewNote();
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
  addEventListener("paste",e=>{if(!isOn()||e.target.closest?.('input,textarea,[contenteditable=true]'))return;const files=[...(e.clipboardData?.items??[])].filter(i=>i.kind==='file'&&i.type.startsWith('image/')).map(i=>i.getAsFile()).filter(Boolean);if(files.length){e.preventDefault();importFiles(files.map(f=>new File([f],'',{type:f.type})));}});
  W.file.addEventListener("change", () => { importFiles([...W.file.files]); W.file.value = ""; });
  W.proj.addEventListener("change", () => { const f = W.proj.files[0]; if (f) openProject(f); W.proj.value = ""; });
  W.filebtns.addEventListener("click", (e) => {
    const a = e.target.closest("[data-a]")?.dataset.a;
    if (a === "open") pickProject();
    if (a === "save") saveProject(e.shiftKey);
  });
  // closing or reloading the page loses what isn't saved
  addEventListener("beforeunload", (e) => { if (plans.some((p) => p.dirty && (p.layers.length||p.assignments?.length))) { e.preventDefault(); e.returnValue = ""; } });
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
  editor = new Editor({state:()=>S,dom:()=>W,lang:()=>api.lang(),view:()=>V,colour:cssVar,active:isOn,
    checkpoint, changed, draw, status:viewNote, annulus, fit, undo, redo, selectionEdit, rollback:history=>{const snap=S.past.pop();if(snap)restore(snap);Object.assign(S,history);W.dirty.classList.toggle('on',S.dirty);refreshLayerRows();}, rename:id=>{const row=W.left.querySelector(`[data-id="${id}"]`);if(row)leftDbl({target:row.querySelector(".nm")});}, error:toast,tool:setTool,rebuild:()=>{buildLeft();buildRight();},
    raster:g=>rasterise(-60,-60,60,60,g.width/120,false),
    shapeLayer:(name, geometry, rgb)=>{
      const c=document.createElement("canvas");c.width=geometry.w;c.height=geometry.h;
      const px=drawShape(c.getContext("2d"),geometry.shape,rgb);
      return {id:newLayerId(),kind:"image",name,sourceKind:"shape",...geometry,rot:0,opacity:1,
        visible:true,locked:false,colour:"none",px,src:c,version:1};
    },
    shape:(kind,points)=>{
      const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]),x0=Math.min(...xs),y0=Math.min(...ys),width=Math.max(.5,Math.max(...xs)-x0),height=Math.max(.5,Math.max(...ys)-y0);
      const local=points.map(([x,y])=>[(x-x0)/width-.5,(y-y0)/height-.5]);
      const type=kind==="rectangleShape"?"rectangle":kind==="pen"?"stroke":kind;
      const shape={type,points:type==="line"?[local[0],local.at(-1)]:local,stroke:.035};
      const c=document.createElement("canvas");c.width=Math.max(1,Math.ceil(width*8));c.height=Math.max(1,Math.ceil(height*8));
      drawShape(c.getContext("2d"),shape);const l=addImageLayer(editor.t[kind]??kind,c,c.width,c.height);if(l){Object.assign(l,{x:x0+width/2,y:y0+height/2,width,sourceKind:kind==="pen"?"stroke":"shape",shape});changed();}
    }});
  W.canvas.tabIndex=0;W.canvas.setAttribute("aria-label","Disc editor canvas");
  W.canvas.addEventListener("keydown",e=>{if(!spaceDown&&e.key!==" "&&editor.key(e)){e.preventDefault();e.stopPropagation();}});
  const observer = new ResizeObserver(resize); observer.observe(W.cv); observer.observe(W.ws);
  $("back").addEventListener("click", () => { if (isOn()) leave(); });
  $("next").addEventListener("click", () => { if (isOn() && (imageLayers().length || S.assignments?.length)) toPreview(); });
  addEventListener("dp-lang", () => { if (isOn()) words(); });
  new MutationObserver(() => { if (isOn()) { draw(); drawScene(); } }).observe(root, { attributes: true, attributeFilter: ["data-theme"] });
}
function resize() {
  const r = W.cv.getBoundingClientRect(), stage = W.surface.getBoundingClientRect();
  const ox = V.cx - focus.x - focus.w / 2, oy = V.cy - focus.y - focus.h / 2;
  focus = {x: r.left - stage.left, y: r.top - stage.top, w: r.width, h: r.height};
  V.w = stage.width; V.h = stage.height; V.dpr = devicePixelRatio || 1;
  W.canvas.width = Math.round(V.w * V.dpr); W.canvas.height = Math.round(V.h * V.dpr);
  settleView();
  if (followFit) fit();
  else { V.cx = focus.x + focus.w / 2 + ox; V.cy = focus.y + focus.h / 2 + oy; draw(); queueCompose(); }
}
// all the words, in the current language
function words() {
  const t = T();
  W.panelPicker.children[0].textContent = t.layers;
  W.panelPicker.children[1].textContent = t.tone;
  W.pname.textContent = S.name ?? t.untitled;
  W.dirty.classList.toggle("on", S.dirty);
  W.dirty.title = S.dirty ? t.unsaved : "";
  const [bo, bs] = W.filebtns.children;
  bo.innerHTML = `${I.open}<span>${t.open}</span>`; bo.title = `${t.open} (Ctrl+O)`;
  bs.innerHTML = `${I.save}<span>${t.save}</span>`; bs.title = `${t.save} (Ctrl+S) · ${t.saveAs} (Ctrl+Shift+S)`;
  W.sub.textContent = api.T().brand?.(S.item.name) ?? S.item.name;
  W.sub.title = t.changeDiscs;
  W.sub.onclick = chooseBatch;
  editor?.toolbar();editor?.optionsBar();
  const [p, b, o] = W.view.children;
  if(!['proj','burn','lamp'].includes(S.view))S.view='proj';
  p.textContent = t.proj; b.textContent = t.burnView; o.textContent = t.orig;
  viewNote();
  W.view.setAttribute("aria-label", t.viewAria);
  for (const x of W.view.querySelectorAll('[data-v]')) x.setAttribute("aria-pressed", String(x.dataset.v === S.view));
  W.zoom.setAttribute("aria-label", t.zoomAria); W.zoom.title = `${t.fit} / ${t.hundred} (0 / 1)`;
  W.empty.querySelector("p").textContent = t.empty;
  W.empty.querySelector('[data-a="import"]').innerHTML = `${I.image}${t.import}`;
  W.empty.querySelector('[data-a="sample"]').textContent = t.sample;
  W.drop.textContent = t.drop;
  $("next-text").textContent = t.next;
  if (W.bar) W.bar.dataset.lang = "";
  buildLeft(); buildRight(); editor?.panels(); draw();
}

let toastT = 0, toastEl = null;
function toast(text, ms = 2600) {
  if (!toastEl) { toastEl = document.createElement("div"); toastEl.className = "toast"; toastEl.setAttribute("role", "status"); document.body.append(toastEl); }
  toastEl.textContent = text; toastEl.classList.add("on");
  clearTimeout(toastT); toastT = setTimeout(() => toastEl.classList.remove("on"), ms);
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
//   work: a work from the library ({ id, name, media, updated_at, text }: its .discdesign, null if never saved).
export function start(homeApi, { fly = true, plan = null, newPlan = false, file = null, projectFile = null, pick = false,
                                  name = null, noDisc = false, dropIn = false, work = null } = {}) {
  composeRevision++;
  api = homeApi; $ = api.$;
  const { col, item } = api.current();
  let fromWork = null;
  if (plan) S = plan;
  else if (work) {
    // the plan already open for this work, unless the library has a newer save and this one has no edits
    const open = plans.find((P) => P.work?.id === work.id);
    if (open && (open.dirty || open.work.updated_at === work.updated_at)) { S = open; S.name = work.name; }
    else {
      const media = work.media in RANGE ? work.media : col, [c, last] = api.lastBatch?.() ?? [];
      const savedBatch = work.batch && api.catalogue?.(media)?.find(x => x.id === work.batch);
      S = newProject(savedBatch || (c === media ? last : col === media ? item : { kind: "unset", name: T().noDiscYet, mid: "", s: "none" }), media);
      S.name = work.name; S.work = { id: work.id, updated_at: work.updated_at };
      if (work.text != null) fromWork = new File([work.text], `${work.name}.discdesign`, { type: "application/json" });
    }
  }
  else if (newPlan) {
    // "decide later" in the form: a plan with no disc batch yet (the kind still sets the drawable range)
    const it = noDisc ? { kind: "unset", name: T().noDiscYet, mid: "", s: "none" } : item;
    S = newProject(it, col); S.selTol = 18; S.selFeather = 1;
    if (name) S.name = name;
  }
  else {
    S = projects.get(item);
    if (!S) { S = newProject(item, col); projects.set(item, S); }
  }
  plans.splice(0, plans.length, S, ...plans.filter((P) => P !== S));
  api.rememberBatch?.(S.item);
  useMeasured(geoChoice(S, api.catalogue?.(S.media) ?? [], null));
  if (!W) build();
  const from = api.focusDisc()?.getBoundingClientRect();
  root.dataset.mode = "design";
  $("back").hidden = false;
  $("next").disabled = !imageLayers().length && !S.assignments?.length; api.nextWhy?.(T().whyNoPicture);
  W.ws.classList.add("on");
  W.ws.classList.toggle("pro-on", S.pro);
  followFit = true;
  words();
  setTool(S.tool);
  requestAnimationFrame(() => {
    resize();
    if (fly) flight(from, { x: V.cx, y: V.cy, d: 120 * V.s }, false);
  });
  const entrance = dropIn && !api.reduce ? W.ws.animate([{ transform: "translateY(-40px)", opacity: 0 }, { transform: "none", opacity: 1 }],
    { duration: 420, easing: "cubic-bezier(.2, .8, .2, 1)" }) : null;       // the next sheet comes down from above
  if (file) importFiles([file]);
  if (projectFile) openProject(projectFile);
  if (fromWork) openProject(fromWork, null, S.work);
  if (pick) pickProject();
  return entrance?.finished.catch(() => {});       // the opener keeps its desk until this sheet has arrived
}
// The library handed back a batch for this plan: switch its discs (the disc kind too, if it changed).
export function useBatch(homeApi, plan, item, col) {
  const before = plan.media;
  plan.item = item; plan.media = col;
  plan.geo = null;                       // a geometry is for one batch: the new one's own measurement decides
  start(homeApi, { plan, fly: false });
  if (before !== col) toast(T().otherMedia(before.toUpperCase(), col.toUpperCase()));
}

// ---------------------------------------------------------------- on to preview and burn
// The projection of the whole disc (120 mm square, centre in the middle) at ppm px per mm.
function projection(ppm) {
  if(editor)return editor.preview(Math.min(1200,Math.round(120*ppm)),true);
  ppm = Math.min(ppm, 20);
  const { c, g, pw, ph } = rasterise(-GRID_MM / 2, -GRID_MM / 2, GRID_MM / 2, GRID_MM / 2, ppm);
  const { adjustments, output } = toneOptions();
  const out = renderOutput(processRGBA(g.getImageData(0, 0, pw, ph), adjustments, { previewScale: ppm * S.cell }), output);
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.putImageData(new ImageData(out.data, pw, ph), 0, 0);
  return c;
}
// Whether the work holds colour, colour-pattern or effect content (export-rules.experimentalContent), from the
// label slots of the editor's own composed preview; remembered per edit.
let expMemo = null;
function experimentalNow(P = S) {
  if (!editor) return { any: false, colours: [], effects: 0 };
  const key = `${editor.revision}|${P.media}`;
  if (expMemo?.key === key) return expMemo.value;
  if (!editor.labelCache?.key?.endsWith(`:${editor.revision}`)) editor.preview(600, true);
  const { materials, labels } = editor.labelCache, seen = new Uint8Array(256);
  for (let i = 0; i < labels.length; i++) seen[labels[i]] = 1;
  const slots = [...seen.keys()].filter((k) => seen[k]);
  const value = experimentalContent({ materials, assignments: P.assignments ?? [], layers: P.layers }, P.media, slots);
  expMemo = { key, value };
  return value;
}
function hideDesign() {
  editor?.lamp?.pause();
  editor?.colourRenderer?.pause();
  composeRevision++;
  stopPlay();
  W.ws.classList.remove("on");
  W.loupe.classList.remove("on");
}
let previewOpening = false;
async function toPreview() {
  if (previewOpening) return;
  previewOpening = true;
  try { await openPreview(); }
  finally { previewOpening = false; }
}
async function openPreview() {
  const P = S, preview = await import("./preview.js");
  // the newest finished geo run, for a plan with no batch (named in the checklist, never used silently)
  const served = await fetch(`/api/state?media=${P.media}`).then((r) => r.ok ? r.json() : null).catch(() => null);
  if (!isOn() || S !== P) return;
  const catalogue = () => api.catalogue?.(P.media) ?? served?.catalogue?.[P.media] ?? [];
  function connectBatch(item) {
    if (P.item?.id !== item.id || P.geo !== item.geo) P.dirty = true;
    P.item = ctx.item = item;
    api.rememberBatch?.(item);
    useMeasured(geoChoice(P, catalogue()));
  }
  const ctx = {
    media: P.media, item: P.item, alongTrackMeasured: false,
    // what a file being made belongs to (preview.js jobs): this plan while open, and its saved work once it has one
    keys: () => P.work?.id ? (P.dirty ? [] : [P, `work:${P.work.id}`]) : [P],
    imageWork: () => !P.dirty && hasCapability("image-job-recovery") ? P.work?.id : null,
    project: { name: P.name ?? P.item?.name, cellMm: P.cell, render: projection, lamp: editor?.lampProject() ?? null,
      fileRegions:()=>occupiedRings(P.files) },
    // colours and effects burn in black and white unless the person asks for the experiment (DVD only)
    effects: hasColourPicture(P) && P.media === "dvd" ? "experimental" : "bw",
    setEffects(mode) { ctx.effects = mode === "experimental" && P.media === "dvd" ? "experimental" : "bw"; },
    // the check disc for the phone photos: DVD only for now (checkdisc.py)
    exportCheck: P.media === "dvd" ? (onProgress, opts) => makeCheckFile(onProgress, opts) : null,
    exportIso: (onProgress, opts) => makeBurnFile(onProgress,
      { ...opts, effects: experimentalNow(P).any ? ctx.effects : "bw" }),
    // what the preview's checklist reads before burning; each answer is what is known now, never a guess
    checks: () => {
      const d = api.driveDisc?.();
      const geo = geoChoice(P, catalogue(), latestGeo(served));
      if (S === P) useMeasured(geo);
      const exp = experimentalNow(P);
      return {
        geo: geo.source, geoName: geo.name, geoWhen: geo.when ?? "",
        inRange: !imageLayers().some((L) => L.visible && cornersOutside(L, ...pictureRange())),
        ring: geo.nominal ? null : P.files?.layout ? pictureRange() : P.ring ?? null,
        nominal: !!geo.nominal || geo.source.startsWith("imported"),
        importProblem: geo.importProblem,
        levels: 2,                                    // the editor burns two textures; tone levels no longer apply
        disc: !d?.present ? "none" : d.media !== P.media ? "kind" : P.item?.mid && d.mid && d.mid !== P.item.mid ? "other" : d.blank === true ? "blank" : "written",
        discName: d?.mid || (d?.present ? discDisplayKind(d, api.lang()) : ""),
        cellUm: Math.round(P.cell * 1000),
        effects: !exp.any ? "none" : ctx.effects,
        canExperiment: P.media === "dvd",
      };
    },
    back: () => start(api, { plan: P, fly: false }),           // the same work, not the shelf disc's own plan
    next: (iso) => toBurn(iso, () => preview.start(api, ctx)),   // the same context keeps the file it made
    calibrate: async (stillHere) => {
      await api.syncState?.();
      if (!stillHere()) return;
      const disc = api.driveDisc?.();
      const known = calibratedBatch(catalogue(), P.item, disc?.media === P.media ? disc : null);
      if (known) {
        connectBatch(known);
        await preview.continueToBurn(api, ctx);
        return;
      }
      if ((!P.work?.id || P.dirty) && !await saveToWorks()) return;
      if (!stillHere()) return;
      document.dispatchEvent(new Event("dp-image-work-saved"));
      const cal = await import("./calibrate.js");
      if (!stillHere()) return;
      api.useForPlan?.(P.media, P.item?.kind === "new" ? null : P.item ?? null);
      const batch = P.item && P.item.kind !== "unset" ? P.item : api.current().item;
      preview.leave(false);
      cal.start(api, { item: batch, returnLabel: () => api.lang() === "en" ? "Return to this work" : "回到这件作品",
        returnTo: async ({ done, batch: saved }) => {
        if (S !== P) start(api, { plan: P, fly: false });
        if (done) {
          const item = saved || calibratedBatch(catalogue(), batch, disc);
          if (item) {
            connectBatch(item);
            if (await saveToWorks()) {
              hideDesign();
              await preview.continueToBurn(api, ctx);
              return;
            }
          }
        }
        hideDesign();
        preview.start(api, ctx);
      } });
    },
  };
  preview.start(api, ctx);
  // Keep the design underneath until the new sheet is opaque, including its first module load.
  const sheet = document.querySelector(".ws.pv");
  if (sheet) {
    getComputedStyle(sheet).opacity;
    await Promise.all(sheet.getAnimations().map(a => a.finished.catch(() => {})));
  }
  if (root.dataset.mode === "preview" && S === P) hideDesign();
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
  const t = T();
  // the drive is looked at first (a few seconds on a real one): meanwhile this is the burn page, not the
  // lobby, so Next must not read "new work"
  root.dataset.mode = "burn"; $("next").disabled = true; $("next-text").textContent = t.burnLooking; api.nextWhy?.("");
  const burn = await import("./burn.js");
  const mock = new URLSearchParams(location.search).has("mockburn");
  // Which drive: the one this project's geometry was measured on (geo-H-…), else the first one listed.
  let drive = { id: "", name: "", speeds: mock ? (S.media === "cd" ? [4, 8, 16] : [4, 8]) : [] }, problem = "", needSwap = false;
  // a CD on Windows: the core has no CD writer there yet (burner.WindowsDVD); the page says how, and does not try
  const otherOnly = !mock && S.media === "cd" && api.platform?.() === "win32";
  let otherCommand = "";
  if (otherOnly) {
    // the core's own command for this ISO and drive (burner.imapi_cd_command), shown to copy
    try {
      const s = await api.backend.request(`/api/state?media=cd`), d = s.drives?.[0];
      if (d) otherCommand = (await api.backend.request(`/api/burn-command?drive=${encodeURIComponent(d.id)}&media=cd&iso=${encodeURIComponent(iso.path)}`)).command;
    } catch { /* no drive or no backend: said below */ }
    problem = otherCommand ? t.burnCdWindows : t.burnCdWindowsNoDrive;
  }
  else if (!mock) {
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
    media: S.media, item: S.item, iso, drive, back, driveProblem: problem, needSwap, otherOnly, otherCommand,
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
    // after a write: read the disc again (read-only) to see whether it was closed. The home page reads the
    // drive at the same moment (refreshFinishedDisc), so a busy answer waits and asks again.
    checkDisc: mock ? null : async () => {
      for (let i = 0; i < 4; i++) {
        try { return await api.readDisc(drive.id); }
        catch (e) { if (e?.status !== 409) throw e; await new Promise((r) => setTimeout(r, 1500)); }
      }
      return null;
    },
    // the check disc is burned: photograph it with the phone against the geometry it was made from; the
    // result stays with that geometry, so the next burn file made here applies it. Then back to the preview.
    // only a check (target) disc: the photo reader reads the target's rings and code, not a picture
    photograph: mock || !iso.target ? null : async () => {
      // the burn page steps aside first: its panel and its Next ("done: back to the desk") must not stay
      // under the photo page
      burn.leave();
      const cal = await import("./calibrate.js");
      cal.photograph(api, { item: S.item, media: S.media, geo: iso.geo ?? S.geo, burnCheck: iso.burnResult ?? null,
        returnTo: async () => { await api.syncState?.(); back?.(); } });
    },
    // the work is done: back to the desk (the plan stays in its recent list)
    done: () => { root.dataset.mode = ""; $("back").hidden = true; $("next").disabled = false; api.toLobby ? api.toLobby() : api.goTo(...api.locate(S.item)); },
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
  drive.rewritable=!!disc.rewritable;drive.eraseRequired=disc.rewritable && disc.blank===false;
  if (disc.blank !== true && !drive.eraseRequired) return { problem: t.burnNotBlankSwap(disc.mid || discDisplayKind(disc, api.lang())), swap: true };
  const want = S.item?.mid;
  if (want && disc.mid && disc.mid !== want) return { problem: t.burnOtherBatch(disc.mid, want), swap: true };
  const r = await fetch(`/api/burn-speeds?drive=${encodeURIComponent(drive.id)}&media=${S.media}`);
  const m = await r.json().catch(() => ({}));
  if (!r.ok) return { problem: t.burnNoDisc(m.error ?? ""), swap: true };
  if (m.blank !== true && !(drive.eraseRequired && m.rewritable)) return { problem: t.burnNotBlankSwap(disc.mid || ""), swap: true };
  if (iso.sectors && m.free_sectors && iso.sectors > m.free_sectors) return { problem: t.burnTooBig, swap: false };
  drive.speeds = m.speeds_x ?? [];
  return { problem: "", swap: false };
}
// What a finished job said last, from its saved events (the event stream replays only "done" to a page that
// connected after the job ended): its error, else its last line; and whether it reached the disc.
async function jobWords(id) {
  try {
    const events = (await (await fetch(`/api/jobs/${id}`)).json()).events ?? [];
    const last = (type, key) => [...events].reverse().find((e) => e.type === type && String(e[key] ?? "").trim())?.[key] ?? "";
    return { why: last("error", "message") || last("log", "text"),
      cancelled:events.some(e=>e.type==='cancelled'&&e.by==='user'),
      wrote: events.some((e) => e.type === "burn_result" || (e.type === "progress" && e.fraction > 0)) };
  } catch { return { why: "", wrote: false }; }
}
// Burn through the back end: a one-time token, the `burn` job, its progress over the event stream.
// Returns a handle at once; failures arrive as a "failed" status with the reason.
function realBurn(iso, drive, onProgress, { speed, erase=false } = {}) {
  // wrote: the drive reported progress, or the core logged a burn result (it does once writing began); without
  // either, a failed job never wrote, and the disc is still good
  let job = null, es = null, closed = false, cancelled = false, burnResult = null, wrote = false, why = "";
  let stopRequested=false;
  const sendStop=async()=>{
    if(!job||closed)return;
    const response=await fetch(`/api/jobs/${job}/cancel`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    if(!response.ok)throw new Error('Could not stop the burn.');
    cancelled=true;
  };
  // started: whether the drive may have begun writing (after the job was accepted)
  const fail = (error, started = !!job) => { if (closed) return; closed = true; es?.close(); onProgress({ status: "failed", error, started }); };
  (async () => {
    try {
      // look at the disc again right before writing (read-only): it may have been changed, and the server only
      // accepts a burn within two minutes of such a look, however long the person stayed on this page
      const look = await fetch(`/api/burn-speeds?drive=${encodeURIComponent(drive.id)}&media=${S.media}`);
      const seen = await look.json().catch(() => ({}));
      if (!look.ok || (seen.blank !== true && !(erase && seen.rewritable))) { fail(look.ok ? T().burnNotBlank : T().burnNoDisc(seen.error ?? ""), false); return; }
      const request = {action:"burn", drive:drive.id, media:S.media, args:{iso:iso.path, ...(speed ? {speed} : {}), ...(erase ? {erase:true} : {})}};
      const tok = await api.backend.request("/api/burn-token", request);
      // the plan's library work: the core records the burn in it (status burned) when the burn succeeds
      const link = S.work?.id ? { id: S.work.id, before: S.work.updated_at, plan: S } : null;
      const r = await fetch("/api/run", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...request, ...(link ? { work: link.id } : {}), burn_token: tok.token }),
      });
      const out = await r.json().catch(() => ({}));
      if (!r.ok) { fail(out.error ?? T().exp.failed); return; }
      job = out.job;
      if(stopRequested)await sendStop();
      es = new EventSource("/api/events");
      const mine = (e) => { const d = JSON.parse(e.data); return d.job === job ? d : null; };
      es.addEventListener('cancelled',e=>{const d=mine(e);if(d?.by==='user')cancelled=true;});
      es.addEventListener('erase_progress',e=>{const d=mine(e);if(d)onProgress({erasing:true,progress:d.fraction,elapsed:d.elapsed_s,remaining:d.eta_s});});
      es.addEventListener('erase_result',e=>{const d=mine(e);if(d)onProgress({erasing:false,progress:0});});
      es.addEventListener("progress", (e) => {
        const d = mine(e); if (!d) return;
        if (d.fraction > 0) wrote = true;
        onProgress({ progress: d.fraction, elapsed: d.elapsed_s, remaining: d.eta_s });
      });
      // the core's own reason; the job's end (done) decides what it means for the disc
      es.addEventListener("error", (e) => { if (e.data) { const d = mine(e); if (d?.message) why = d.message; } });
      es.addEventListener("burn_speed", (e) => {
        const d = mine(e); if (d) onProgress({ speedReport: d });
      });
      es.addEventListener("verify_progress", (e) => {
        const d = mine(e); if (d) onProgress({ verifying: true });
      });
      es.addEventListener("burn_result", (e) => {
        const d = mine(e); if (d) { burnResult = d; iso.burnResult = d; onProgress({ burnResult: d }); }
      });
      es.addEventListener("done", async (e) => {
        const d = mine(e); if (!d || closed) return;
        closed = true; es.close();
        if (d.exit !== 0) { const said = await jobWords(job); why ||= said.why; wrote ||= said.wrote; cancelled ||= said.cancelled; }
        const started = wrote || !!burnResult;
        const v = burnResult?.verification;
        const checked = (!burnResult?.result || burnResult.result === "completed") && burnResult?.disc_state?.status !== "failed" &&
          (!v || v.status === "skipped" || (v.status === "completed" && !v.differing && !v.unreadable && !v.untested));
        if (d.exit === 0 && checked && link) await afterWorkISO(link, null);     // follow the stamp the core's burn record moved
        onProgress(d.exit === 0 && checked ? { status: "success", progress: 1, burnResult } : cancelled ? { status: "cancelled" }
          : { status: "failed", burnResult, error: [started ? T().burnFailed : T().burnNotStarted, burnResult?.reason || why].filter(Boolean).join(" "), started });
      });
    } catch { fail(T().exp.noBackend); }
  })();
  return {
    async cancel() {
      // The burn component calls this only after the locked stop slider completes.
      // The two preview-render /cancel calls above are read-only and stay immediate.
      if(closed)return;
      stopRequested=true;
      await sendStop();
    },
  };
}

function leave() {
  settleView();editor?.lamp?.pause();
  clearTimeout(editor?.lightTimer);
  composeRevision++;
  stopPlay();
  const to = { x: V.cx, y: V.cy, d: 120 * V.s };
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

// Public automation/export surface uses the same actions and document serializer as the UI.
export const editorDocument = () => editor.document();
export const editorActions = () => ({editor, importFiles, openProject, projectText, undo, redo, state:()=>S});
