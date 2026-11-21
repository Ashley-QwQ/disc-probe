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
    if (browser.exitCode === null && browser.signalCode === null) browser.kill();
    await exited;
  } finally {
    socket?.close();
  }
}
