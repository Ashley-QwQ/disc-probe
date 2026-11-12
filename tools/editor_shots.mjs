// Headless Edge screenshots through the DevTools protocol.
// node cdpshot.mjs plan.json outdir
// plan: [{url, theme:"light"|"dark", steps:[{eval:"js"}|{wait:ms}|{shot:"name"}|{key:"S", shift:true}]}]
import { spawn } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { join, resolve, sep } from "node:path";

const [planPath, outDir] = process.argv.slice(2);
const plan = JSON.parse(readFileSync(planPath, "utf8"));
mkdirSync(outDir, { recursive: true });
const PORT = 9334;
const outputRoot=resolve(outDir);
const profile = resolve(outputRoot, ".edge-profile");
if(!profile.startsWith(outputRoot+sep)||profile===outputRoot)throw Error('Profile must stay inside the screenshot output directory');
const edge = spawn("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "--no-first-run",
   "--hide-scrollbars", "--window-size=1440,900", "about:blank"], { stdio: "ignore", detached: false });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let ws, seq = 0;
const pending = new Map();
async function connect() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) { ws = new WebSocket(page.webSocketDebuggerUrl); break; }
    } catch {}
    await sleep(200);
  }
  await new Promise((r) => ws.addEventListener("open", r, { once: true }));
  ws.addEventListener("message", (m) => {
    const d = JSON.parse(m.data);
    if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); }
  });
}
const send = (method, params = {}) => new Promise((r) => { const id = ++seq; pending.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
const evaluate = async (expr) => { const r=await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true }); if(r.result?.exceptionDetails)throw Error(JSON.stringify(r.result.exceptionDetails)); return r.result?.result?.value; };

try {
  await connect();
  await send('Runtime.enable');
  await send('Network.enable');
  await send('Network.setCacheDisabled',{cacheDisabled:true});
  const errors=[];ws.addEventListener('message',e=>{const d=JSON.parse(e.data);if(d.method==='Runtime.exceptionThrown')errors.push(d.params);});
  for (const item of plan) {
    await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 2, mobile: false });
    await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: item.theme || "light" }, { name: "prefers-reduced-motion", value: item.motion ? "no-preference" : "reduce" }] });
    if (item.url) { await send("Page.navigate", { url: item.url }); await sleep(item.load || 2500); }
    for (const s of item.steps || []) {
      if (s.eval) { const v = await evaluate(s.eval); if (s.print) console.log(JSON.stringify(v)); if(s.save)writeFileSync(join(outDir,s.save),JSON.stringify(v)); }
      if (s.wait) await sleep(s.wait);
      if (s.key) {
        const mods = s.shift ? 8 : 0;
        for (const type of ["keyDown", "keyUp"]) await send("Input.dispatchKeyEvent", { type, key: s.key, text: type === "keyDown" ? s.key : undefined, modifiers: mods, code: s.code });
      }
      if (s.shot) {
        const r = await send("Page.captureScreenshot", { format: "png" });
        writeFileSync(join(outDir, s.shot + ".png"), Buffer.from(r.result.data, "base64"));
        console.log("saved", s.shot);
      }
    }
  }
  writeFileSync(join(outDir,'browser-errors.json'),JSON.stringify(errors,null,2));
} finally {
  edge.kill();
  await sleep(800);
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
