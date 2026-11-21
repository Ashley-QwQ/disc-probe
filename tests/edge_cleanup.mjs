import {spawnSync} from 'node:child_process';
import {once} from 'node:events';
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
