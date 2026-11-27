// Keep the existing offline test guard. Node/Windows can fail to remove a lab
// directory after the test has already closed its own browser and server.
const fs = require('node:fs');
const path = require('node:path');
const childProcess = require('node:child_process');
const {syncBuiltinESMExports} = require('node:module');
const rmSync = fs.rmSync;
const spawnSync = childProcess.spawnSync;

// A headless snapshot can end before the iframe posts its result on a busy host.
// Wait for the actual fixture in the same browser when that happens.
childProcess.spawnSync = function (command, args, ...options) {
  const snapshot = path.basename(command).toLowerCase() === 'chrome-headless-shell.exe' &&
                   args?.includes('--dump-dom') && args.at(-1).startsWith('file:');
  const result = spawnSync(command, args, ...options);
  if (snapshot && !result.error && /<pre id="result"[^>]*>PENDING<\/pre>/.test(result.stdout?.toString())) {
    console.log('Waiting for the headless fixture after an early virtual-time snapshot');
    const retry = path.join(__dirname, 'browser-snapshot.mjs');
    return spawnSync(process.execPath, [retry, command, ...args], ...options);
  }
  return result;
};

fs.rmSync = function (target, options) {
  try {
    return rmSync(target, options);
  } catch (error) {
    if (process.platform !== 'win32' || error.code !== 'EPERM' ||
        !options?.recursive || typeof target !== 'string') throw error;
    const resolved = fs.realpathSync(target);
    const temp = fs.realpathSync(process.env.TEMP);
    const relative = path.relative(temp, resolved);
    if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) throw error;
    const removal = spawnSync(process.env.PYTHON ?? 'python', ['-c', `
from pathlib import Path
import shutil
import sys
target, root = (Path(p).resolve(strict=True) for p in sys.argv[1:])
if target == root or not target.is_relative_to(root):
    raise ValueError('Outside the test temp directory')
shutil.rmtree(target)
`, resolved, temp], {windowsHide: true, encoding: 'utf8'});
    if (removal.status !== 0) throw error;
    console.log('Removed test directory with Python after Windows EPERM:', relative);
  }
};
syncBuiltinESMExports();
