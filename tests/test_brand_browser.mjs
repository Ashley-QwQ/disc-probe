// Real Edge glyph selection and requested screenshots; local synthetic data, no drives.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createServer} from 'node:http';
import {existsSync, readFileSync, writeFileSync, mkdirSync, mkdtempSync} from 'node:fs';
import {rm} from 'node:fs/promises';
import {resolve, join, extname, sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = fileURLToPath(new URL('../discprobe/web/', import.meta.url));
const edge = process.env.BRAND_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const tempRoot = process.env.BRAND_TEST_TEMP || 'D:/dp-dev/tmp/brand/browser';
const shots = process.env.BRAND_SCREENSHOTS;
mkdirSync(tempRoot, {recursive:true});
if (shots) mkdirSync(shots, {recursive:true});
const profile = mkdtempSync(join(tempRoot, 'edge-'));
const manifest = JSON.parse(readFileSync(join(root, 'gui.json'), 'utf8'));
const types = {'.html':'text/html; charset=utf-8', '.js':'text/javascript', '.mjs':'text/javascript',
  '.css':'text/css', '.json':'application/json', '.woff2':'font/woff2', '.png':'image/png',
  '.webp':'image/webp', '.svg':'image/svg+xml', '.ico':'image/x-icon'};
const server = createServer((req,res) => {
  const path = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  if (path === '/api/version') {
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({api_version:'1.0', capabilities:[...manifest.required_capabilities, ...manifest.optional_capabilities]}));
    return;
  }
  if (path === '/api/photos') {
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({photos:[], now:0, computer_open:true})); return;
  }
  let target = resolve(root, '.' + path + (path.endsWith('/') ? 'index.html' : ''));
  if (path === '/phone/brand-test') target = join(root, 'phone/index.html');
  if (!target.startsWith(resolve(root) + sep) || target.toLowerCase().includes('b'+'lind') || !existsSync(target)) {
    res.writeHead(404); res.end(); return;
  }
  res.setHeader('Content-Type', types[extname(target)] || 'application/octet-stream');
  let data = readFileSync(target);
  if (path === '/phone/brand-test') data = data.toString('utf8').replace('__PHOTO_CONFIG__', JSON.stringify({run:'brand-test',token:'brand-test'}));
  res.end(data);
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const origin = `http://127.0.0.1:${server.address().port}`;
const child = spawn(edge, ['--headless=new','--remote-debugging-port=0',`--user-data-dir=${profile}`,
  '--disable-gpu','--disable-background-networking','--no-first-run','--hide-scrollbars','about:blank'],
  {stdio:'ignore',windowsHide:true});
const sleep = ms => new Promise(r => setTimeout(r,ms));
let ws, seq = 0;
const pending = new Map(), evidence = [];
const send = (method,params={}) => new Promise((resolve,reject) => {
  const id = ++seq;
  const timer = setTimeout(() => {pending.delete(id);reject(Error(`CDP timeout: ${method}`));},20000);
  pending.set(id,{resolve,reject,timer}); ws.send(JSON.stringify({id,method,params}));
});
const evaluate = async expression => {
  const result = await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
  assert.ok(!result.exceptionDetails,JSON.stringify(result.exceptionDetails));
  return result.result.value;
};
async function fontsFor(selector) {
  const {root} = await send('DOM.getDocument');
  const {nodeId} = await send('DOM.querySelector',{nodeId:root.nodeId,selector});
  assert.ok(nodeId,selector);
  return (await send('CSS.getPlatformFontsForNode',{nodeId})).fonts;
}
try {
  for (let i=0;i<80 && !existsSync(join(profile,'DevToolsActivePort'));i++) await sleep(100);
  const port = readFileSync(join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];
  const tabs = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  ws = new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((r,j)=>{ws.addEventListener('open',r,{once:true});ws.addEventListener('error',j,{once:true});});
  ws.addEventListener('message',event=>{
    const message=JSON.parse(event.data), call=pending.get(message.id);
    if (!call) return;
    clearTimeout(call.timer);pending.delete(message.id);
    if(message.error)call.reject(Error(JSON.stringify(message.error))); else call.resolve(message.result);
  });
  await send('Runtime.enable'); await send('DOM.enable'); await send('CSS.enable');
  await send('Network.enable');
  await send('Network.setExtraHTTPHeaders',{headers:{'Accept-Language':'zh-CN'}});
  await send('Emulation.setLocaleOverride',{locale:'zh-CN'});
  await send('Page.addScriptToEvaluateOnNewDocument',{source:`Object.defineProperty(navigator,'language',{get:()=> 'zh-CN'});localStorage.setItem('dp-lang','zh');localStorage.setItem('dp-motion','off');localStorage.removeItem('dp-theme');`});
  for (const variant of [
    {name:'home-paper',theme:'light',width:1360,height:1000,path:'/home/?mock',title:'.lb-label[data-target]'},
    {name:'home-ink',theme:'dark',width:1360,height:1000,path:'/home/?mock',title:'.lb-label[data-target]'},
    {name:'phone',theme:'light',width:390,height:844,path:'/phone/brand-test',title:'#title'},
  ]) {
    await send('Emulation.setDeviceMetricsOverride',{width:variant.width,height:variant.height,deviceScaleFactor:1,mobile:false});
    await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-color-scheme',value:variant.theme},{name:'prefers-reduced-motion',value:'reduce'}]});
    await send('Page.navigate',{url:origin+variant.path});
    let ready=false;
    for(let i=0;i<100;i++) {
      ready = await evaluate(`document.querySelector(${JSON.stringify(variant.title)})?.textContent?.trim().length > 0 && document.documentElement.lang === 'zh-CN'`);
      if(ready)break; await sleep(100);
    }
    assert.ok(ready,variant.name+' mounted');
    await evaluate('document.fonts.ready.then(()=>true)');
    await sleep(500);
    const titleFonts=await fontsFor(variant.title);
    assert.ok(titleFonts.some(f=>f.familyName==='Disc Title SC' && f.isCustomFont && f.glyphCount>0),JSON.stringify(titleFonts));
    const titleFamily=await evaluate(`getComputedStyle(document.querySelector(${JSON.stringify(variant.title)})).fontFamily`);
    const bodyFamily=await evaluate('getComputedStyle(document.body).fontFamily');
    assert.ok(titleFamily.indexOf('Archivo') < titleFamily.indexOf('Disc Title SC'));
    assert.ok(!bodyFamily.includes('Disc Title SC'),'body family unchanged');
    const latinFonts=await fontsFor(variant.name==='phone'?'.mark':'.wm-p');
    assert.ok(latinFonts.some(f=>f.familyName.startsWith('Archivo') && f.isCustomFont && f.glyphCount>0),JSON.stringify(latinFonts));
    for(const rel of ['icon','apple-touch-icon']) {
      assert.equal(await evaluate(`fetch(document.querySelector('link[rel="${rel}"]').href).then(r=>r.status)`),200);
    }
    const entry={...variant,titleFamily,bodyFamily,titleFonts,latinFonts};
    evidence.push(entry);
    if(shots) {
      const {data}=await send('Page.captureScreenshot',{format:'png'});
      writeFileSync(join(shots,variant.name+'.png'),Buffer.from(data,'base64'));
    }
  }
  if(shots)writeFileSync(join(shots,'font-evidence.json'),JSON.stringify(evidence,null,2));
  console.log('PASS: Edge Chinese title glyphs use Disc Title SC Heavy; Latin uses Archivo; body unchanged; 3 viewports/icons verified');
} finally {
  ws?.close(); child.kill(); server.closeAllConnections(); await new Promise(r=>server.close(r));
  await sleep(800);
  assert.ok(resolve(profile).startsWith(resolve(tempRoot)+sep));
  await rm(profile,{recursive:true,force:true,maxRetries:8,retryDelay:300});
}
