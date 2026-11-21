// Run from the repository root with Node 22+ and headless Edge installed.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, readFile, realpath, rm, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { once } from 'node:events';

const requested = resolve(process.argv[2]);
await mkdir(requested, { recursive: true });
const root = await realpath(requested);
const profile = await realpath(await mkdtemp(join(root, 'colour-audit-edge-')));
assert.equal(dirname(profile), root);
const server = spawn(process.env.PYTHON || 'python', [
  '-B', '-X', 'utf8', 'tools/audit_colour_solver.py', 'serve', root,
], { stdio: ['pipe', 'pipe', 'inherit'], windowsHide: true });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let edge, socket, ready = '';
const pending = new Map();
let seq = 0;
server.stdout.on('data', chunk => { ready += chunk; });
async function until(probe, name, seconds = 30) {
  const deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    const result = await probe();
    if (result) return result;
    await pause(100);
  }
  throw Error('Timed out waiting for ' + name);
}
async function cdp(method, params = {}) {
  const id = ++seq;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(Error(method)); }, 420000);
    pending.set(id, message => {
      clearTimeout(timer);
      if (message.error) reject(Error(JSON.stringify(message.error)));
      else resolve(message.result);
    });
    socket.send(JSON.stringify({ id, method, params }));
  });
}
async function js(expression) {
  const result = await cdp('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  assert(!result.exceptionDetails, result.exceptionDetails?.exception?.description);
  return result.result.value;
}
async function click(selector) {
  await until(() => js(`(() => { const node = document.querySelector(${JSON.stringify(selector)});
    return !!node && !node.disabled; })()`), selector);
  await js(`document.querySelector(${JSON.stringify(selector)}).click()`);
}
try {
  await until(() => ready.includes('\n'), 'loopback server');
  const { port, geo } = JSON.parse(ready.split('\n')[0]);
  edge = spawn(process.env.KIT_TEST_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', [
    '--headless=new', '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
    '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank',
  ], { stdio: 'ignore', windowsHide: true });
  const cdpPort = await until(async () => {
    try { return (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
  }, 'Edge CDP');
  const tabs = await (await fetch('http://127.0.0.1:' + cdpPort + '/json/list')).json();
  socket = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
  await once(socket, 'open');
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data), handler = pending.get(message.id);
    if (handler) { pending.delete(message.id); handler(message); }
  };
  await cdp('Page.enable');
  await cdp('Runtime.enable');
  await cdp('Page.navigate', { url: `http://127.0.0.1:${port}/home/` });
  await until(() => js('document.documentElement.dataset.handshake === "ready"'), 'GUI handshake');
  await js(`(async () => {
    window.design = await import('/home/design.js');
    const item = { id: 'audit', kind: 'saved', name: 'Audit DVD', s: 'good', geo: ${JSON.stringify(geo)} };
    const { setWorksForTest } = await import('/home/pastworks/works.mjs');
    setWorksForTest({ mock: true });  // work-library bookkeeping is outside the image comparison
    const backend = { state: () => fetch('/api/state').then(r => r.json()),
      request: (path, data) => fetch(path, { method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify(data) }).then(r => r.json()) };
    design.start({ $: id => document.getElementById(id), lang: () => 'en', T: () => ({}),
      current: () => ({ col: 'dvd', item }), focusDisc: () => null, reduce: true, nextWhy() {}, backend },
      { newPlan: true, fly: false, name: 'Colour audit' });
    window.actions = design.editorActions();
    window.auditHTTP = [];
    const original = window.fetch;
    window.fetch = async (path, ...args) => {
      const response = await original(path, ...args);
      if (path === '/api/compose' || path === '/api/run') auditHTTP.push({
        path, status: response.status, response: await response.clone().json(),
        ...(path === '/api/run' ? {request:JSON.parse(args[0].body)} : {})
      });
      return response;
    };
    const file = new File([Uint8Array.from(atob(${JSON.stringify((await readFile(join(root, 'source.png'))).toString('base64'))}),
      c => c.charCodeAt(0))], 'source.png', { type: 'image/png' });
    const transfer = new DataTransfer(); transfer.items.add(file);
    const input = document.querySelector('.f-img');
    input.files = transfer.files; input.dispatchEvent(new Event('change', { bubbles:true }));
    return true;
  })()`);
  await until(() => js('actions.state().layers.length === 1'), 'imported image');
  await click('[data-ed-tab=colour]');
  await click('[data-ed-rig=phone][data-value=iphone17pro]');
  await click('[data-ed-rig=height][data-value="21"]');
  await click('[data-ed-choice=fillKind][data-value=colour]');
  await click('.ed-apply');
  await until(() => js('actions.state().assignments.some(a => a.colour)'), 'colour assignment');
  console.log('Source imported and filled; starting image generation.');
  await js(`void (async () => {
    try {
      const work = actions.editor.document();
      const result = await design.makeBurnFile(progress => { window.auditProgress = progress; });
      window.auditResult = { placement: {width:work.layers[0].width, height:work.layers[0].height},
        storedScene:work.scene, result, http:auditHTTP };
    } catch (error) { window.auditResult = { error:error.stack, http:auditHTTP }; }
  })()`);
  const result = await until(async () => {
    const state = await js('({ result:window.auditResult, progress:window.auditProgress, http:auditHTTP })');
    await writeFile(join(root, 'web-live.json'), JSON.stringify(state, null, 2));
    if (!state.result) await pause(1000);
    return state.result;
  }, 'image generation', 360);
  await writeFile(join(root, 'web.json'), JSON.stringify(result, null, 2));
  assert(!result.error, result.error);
  console.log(JSON.stringify(result.result));
} finally {
  socket?.close();
  if (edge && edge.exitCode === null) { const exited = once(edge, 'exit'); edge.kill(); await exited; }
  if (server.exitCode === null) { const exited = once(server, 'exit'); server.stdin.end(); await exited; }
  await rm(profile, { recursive: true, force: true, maxRetries: 8, retryDelay: 250 });
}
