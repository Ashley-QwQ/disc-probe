import {spawn, spawnSync} from 'node:child_process';
import {once} from 'node:events';
import {mkdirSync, readFileSync, realpathSync, rmdirSync, rmSync, statSync} from 'node:fs';
import {basename, delimiter, dirname, join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';

const windows = process.platform === 'win32';
const localShell = 'D:/20261001film/tools/browsers/chrome-headless-shell/win64-154.0.8037.57/chrome-headless-shell-win64/chrome-headless-shell.exe';
const edgeExe = 'msedge.exe';
const launches = new WeakMap();

function findExecutable(value) {
  if (!value) return;
  const candidates = /[\\/]/.test(value) ? [value] :
    (process.env.PATH ?? '').split(delimiter).filter(Boolean).map(folder => join(folder, value));
  const path = candidates.find(candidate => statSync(candidate, {throwIfNoEntry: false})?.isFile());
  if (path) return realpathSync(path);
}

export function selectBrowser({legacy = [], explicit, edgeOnly = false, optional = false} = {}) {
  const env = process.env;
  const old = legacy.find(name => env[name]);
  let executable;
  if (env.DP_TEST_BROWSER || explicit || old) {
    if (!env.DP_TEST_BROWSER && !explicit && old) console.warn(`${old} is deprecated. Use DP_TEST_BROWSER.`);
    const requested = env.DP_TEST_BROWSER || explicit || env[old];
    executable = findExecutable(requested);
    if (!executable && !optional) throw Error(`Browser executable not found: ${requested}`);
  } else if (windows) {
    // A nonempty override replaces the machine default, so fallback can be exercised explicitly.
    if (!edgeOnly) executable = findExecutable(env.DP_HEADLESS_SHELL || localShell);
    executable ??= [env['ProgramFiles(x86)'], env.ProgramFiles, env.LOCALAPPDATA]
      .filter(Boolean).map(dir => join(dir, 'Microsoft', 'Edge', 'Application', edgeExe))
      .map(findExecutable).find(Boolean) ?? findExecutable(edgeExe);
  } else if (!edgeOnly) {
    executable = ['chromium', 'chromium-browser', 'google-chrome'].map(findExecutable).find(Boolean);
  }

  if (!executable) {
    if (optional) return null;
    throw Error('Browser executable not found. Set DP_TEST_BROWSER.');
  }
  const name = basename(executable).toLowerCase();
  const shell = /^chrome-headless-shell(?:\.exe)?$/.test(name);
  if (edgeOnly && name !== edgeExe) throw Error('This test requires Edge. Set DP_TEST_BROWSER to Edge.');
  let fixedProfile;
  if (windows && !shell) {
    if (!env.LOCALAPPDATA) throw Error('LOCALAPPDATA is required for the fixed browser profile');
    const profileName = name === edgeExe ? 'edge-profile' : name.replace(/\.exe$/, '') + '-profile';
    fixedProfile = resolve(env.LOCALAPPDATA, 'disc-probe-test-browser', profileName);
  }
  return {executable, shell, fixedProfile};
}

function prepare(browser, temporaryProfile, args, {headless = true, disableGpu = false}) {
  const profile = browser.fixedProfile ?? resolve(temporaryProfile);
  if (!headless && browser.shell) throw Error('chrome-headless-shell requires headless mode');
  if (args.some(arg => /^--(?:user-data-dir|headless)(?:=|$)/.test(arg))) {
    throw Error('Specify the browser profile and headless mode through the launcher');
  }
  const flags = ['--disable-background-networking'];
  if (disableGpu) flags.push('--disable-gpu');
  if (!browser.shell) {
    if (headless) flags.push('--headless=new');
    flags.push('--no-first-run', '--no-default-browser-check');
  }
  const argv = [...flags, `--user-data-dir=${profile}`, ...args];
  let lock;
  if (browser.fixedProfile) {
    mkdirSync(profile, {recursive: true});
    lock = profile + '.lock';
    try {
      mkdirSync(lock);
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      throw Error(`Fixed browser profile is already reserved: ${lock}`);
    }
    try {
      rmSync(join(profile, 'DevToolsActivePort'), {force: true});
    } catch (error) {
      rmdirSync(lock);
      throw error;
    }
  }
  return {browser, profile, argv, lock};
}

export function launchBrowser(browser, profile, args, {headless, disableGpu, ...options} = {}) {
  const launch = prepare(browser, profile, args, {headless, disableGpu});
  try {
    const child = spawn(browser.executable, launch.argv, {windowsHide: true, ...options});
    launches.set(child, launch);
    return child;
  } catch (error) {
    if (launch.lock) rmdirSync(launch.lock);
    throw error;
  }
}

export function devToolsPortFile(child) {
  return join(launches.get(child).profile, 'DevToolsActivePort');
}

export function runBrowser(browser, profile, args, {disableGpu, ...options} = {}) {
  const launch = prepare(browser, profile, args, {disableGpu});
  try {
    const result = spawnSync(browser.executable, launch.argv, {windowsHide: true, ...options});
    if (result.error || launch.lock) endProfileProcesses(launch);
    return result;
  } finally {
    if (launch.lock) rmdirSync(launch.lock);
  }
}

export async function stopBrowser(child, socket) {
  const launch = launches.get(child);
  try {
    if (!child?.pid || child.exitCode !== null || child.signalCode !== null) return;
    const exited = once(child, 'exit');
    if (socket?.readyState === WebSocket.OPEN) {
      // Let Chromium flush its profile and close its children before deleting files.
      try { socket.send(JSON.stringify({id: Number.MAX_SAFE_INTEGER, method: 'Browser.close'})); }
      catch (error) { if (socket.readyState === WebSocket.OPEN) throw error; }
      await Promise.race([exited, delay(3000, undefined, {ref: false})]);
    }
    if (child.exitCode === null && child.signalCode === null) {
      const killed = windows && spawnSync('taskkill', ['/T', '/F', '/PID', String(child.pid)],
        {windowsHide: true, stdio: 'ignore', timeout: 15000}).status === 0;
      if (!killed) child.kill();
    }
    await exited;
  } finally {
    socket?.close();
    if (launch) {
      launches.delete(child);
      try { endProfileProcesses(launch); }
      finally { if (launch.lock) rmdirSync(launch.lock); }
    }
  }
}

// After Browser.close, a renderer or GPU child can outlive the main process on Windows.
function endProfileProcesses({browser, profile}) {
  if (!windows) return;
  const quote = value => value.replaceAll("'", "''");
  const image = quote(basename(browser.executable));
  const path = quote(profile.replaceAll('/', '\\'));
  const script = `$path = [regex]::Escape('${path}'); ` +
    `$pattern = '(?:^|\\s)(?:"--user-data-dir=' + $path + '"|--user-data-dir="' + $path + ` +
    `'"|--user-data-dir=' + $path + ')(?=\\s|$)'; ` +
    `Get-CimInstance Win32_Process -Filter "Name='${image}'" | Where-Object { $_.CommandLine -and ` +
    '$_.CommandLine.Replace(\'/\', \'\\\') -match $pattern } | ' +
    'ForEach-Object { $p = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue; ' +
    'if ($p -and [math]::Abs(($p.StartTime - $_.CreationDate).TotalSeconds) -lt 1) { ' +
    'Stop-Process -InputObject $p -Force -ErrorAction SilentlyContinue } }';
  spawnSync('powershell', ['-NoProfile', '-NonInteractive', '-Command', script],
    {windowsHide: true, stdio: 'ignore', timeout: 30000});
}

// Node backs off linearly: about 11 s in all before giving up.
export const PROFILE_RM = {recursive: true, force: true, maxRetries: 10, retryDelay: 200};

export function removeProfile(profile, parent) {
  const path = realpathSync(profile), root = realpathSync(parent);
  if (dirname(path) !== root) throw Error('Profile is outside its test directory');
  try { rmSync(path, PROFILE_RM); }
  catch (error) {
    if (!windows || error.code !== 'EPERM') throw error;
    const script = `
from pathlib import Path
import shutil
import sys
path, root = [Path(value).resolve(strict=True) for value in sys.argv[1:]]
if path.parent != root:
    raise ValueError('Profile is outside its test directory')
shutil.rmtree(path)
`;
    const result = spawnSync(process.env.PYTHON ?? 'python', ['-c', script, path, root], {windowsHide:true, encoding:'utf8'});
    if (result.status !== 0) throw Error(result.error?.message || result.stderr || error.message);
  }
}

// Python tools use the same selection, launch arguments, and profile lifecycle.
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const {explicit, profile, args, timeout, disableGpu} = JSON.parse(readFileSync(0, 'utf8'));
  const result = runBrowser(selectBrowser({explicit}), profile, args, {disableGpu, timeout, maxBuffer: 64 * 1024 * 1024});
  if (result.stdout) process.stdout.write(result.stdout);
  if (result.stderr) process.stderr.write(result.stderr);
  if (result.error) console.error(result.error.message);
  process.exitCode = result.status ?? 1;
}
