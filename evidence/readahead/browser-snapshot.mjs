// Wait for a file-URL fixture to finish in real time when a virtual-time dump
// ended early. The test still evaluates the reported result and screenshots.
import {readFileSync, rmSync, writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';
import {launchBrowser, selectBrowser, stopBrowser} from '../../tests/browser.mjs';

const [executable, ...args] = process.argv.slice(2);
const value = name => args.find(arg => arg.startsWith(name + '='))?.slice(name.length + 1);
const profile = value('--user-data-dir');
const screenshot = value('--screenshot');
const url = args.at(-1);
if (!profile || !url.startsWith('file:')) throw Error('Expected a local file-URL test fixture');
rmSync(join(profile, 'DevToolsActivePort'), {force: true});
const launchArgs = args.slice(0, -1).filter(arg => !/^--(?:user-data-dir|virtual-time-budget|screenshot|dump-dom)(?:=|$)/.test(arg));
const browser = selectBrowser({explicit: executable});
const child = launchBrowser(browser, profile, [...launchArgs, '--remote-debugging-port=0', 'about:blank'],
                            {stdio: 'ignore'});
let socket, seq = 0;
const pending = new Map();

function cdp(method, params) {
  const id = ++seq;
  return new Promise((resolve, reject) => {
    pending.set(id, {resolve, reject});
    socket.send(JSON.stringify({id, method, params}));
  });
}

try {
  let port;
  for (let wait = 0; !port && wait < 100; wait++) {
    try { port = Number(readFileSync(join(profile, 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0]); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (!port) await delay(60);
  }
  if (!port || port === 8765) throw Error('The fixture browser lacks its own DevTools port');
  const tabs = await fetch(`http://127.0.0.1:${port}/json/list`).then(response => response.json());
  socket = new WebSocket(tabs.find(tab => tab.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.onopen = resolve;
    socket.onerror = reject;
  });
  socket.onmessage = ({data}) => {
    const {id, result, error} = JSON.parse(data);
    const request = pending.get(id);
    if (!request) return;
    pending.delete(id);
    if (error) request.reject(Error(error.message));
    else request.resolve(result);
  };
  await cdp('Page.navigate', {url});
  const deadline = Date.now() + 45_000;
  while (Date.now() < deadline) {
    const {result} = await cdp('Runtime.evaluate', {
      expression: 'document.querySelector("#result")?.textContent', returnByValue: true,
    });
    if (/^(?:PASS|FAIL):/.test(result.value)) break;
    await delay(80);
  }
  if (screenshot) {
    const {data} = await cdp('Page.captureScreenshot', {format: 'png'});
    writeFileSync(screenshot, Buffer.from(data, 'base64'));
  }
  const {result} = await cdp('Runtime.evaluate', {expression: 'document.documentElement.outerHTML', returnByValue: true});
  process.stdout.write(result.value);
} finally {
  await stopBrowser(child, socket);
}
