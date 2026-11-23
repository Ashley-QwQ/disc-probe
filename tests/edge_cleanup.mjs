import {spawnSync} from 'node:child_process';
import {once} from 'node:events';
import {realpathSync, rmSync} from 'node:fs';
import {dirname} from 'node:path';
import {setTimeout as delay} from 'node:timers/promises';

export async function stopEdge(browser, socket) {
  try {
    if (!browser?.pid || browser.exitCode !== null || browser.signalCode !== null) return;
    const exited = once(browser, 'exit');
    if (socket?.readyState === WebSocket.OPEN) {
      // Let Edge close its profile files and child processes before deleting the profile.
      socket.send(JSON.stringify({id: Number.MAX_SAFE_INTEGER, method: 'Browser.close'}));
      await Promise.race([exited, delay(3000, undefined, {ref: false})]);
    }
    if (browser.exitCode === null && browser.signalCode === null) {
      // On Windows a plain kill stops only the main process; its renderer and GPU children can
      // live on and keep the profile's lockfile open. End the whole tree instead.
      if (process.platform === 'win32') spawnSync('taskkill', ['/T', '/F', '/PID', String(browser.pid)], {windowsHide: true, stdio: 'ignore'});
      else browser.kill();
    }
    await exited;
  } finally {
    socket?.close();
  }
}

// Node backs off linearly: about 11 s in all before giving up.
export const PROFILE_RM = {recursive: true, force: true, maxRetries: 10, retryDelay: 200};

export function removeProfile(profile, parent) {
  const path = realpathSync(profile), root = realpathSync(parent);
  if (dirname(path) !== root) throw Error('Profile is outside its test directory');
  try { rmSync(path, PROFILE_RM); }
  catch (error) {
    if (process.platform !== 'win32' || error.code !== 'EPERM') throw error;
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

// After Browser.close the main process can exit while renderer/GPU children stay behind
// holding the profile's lockfile. End any Edge process still using this profile.
export function endProfileProcesses(profile) {
  if (process.platform !== 'win32') return;
  const needle = String(profile).replaceAll('/', '\\').toLowerCase().replaceAll("'", "''");
  const script = "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Where-Object { $_.CommandLine -and " +
    `$_.CommandLine.Replace('/', '\\').ToLower().Contains('${needle}') } | ` +
    'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }';
  spawnSync('powershell', ['-NoProfile', '-NonInteractive', '-Command', script], {windowsHide: true, stdio: 'ignore', timeout: 30000});
}
