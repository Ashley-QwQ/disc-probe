// Test-runner guard: permit loopback fixtures, suppress Chromium background traffic.
// Loaded only for verification children via NODE_OPTIONS; production/tests stay intact.
const cp = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const {syncBuiltinESMExports} = require('node:module');
// The shipped CSP/flow tests hard-code output-only D: paths and expose no env knob.
// Redirect those two artifact destinations; reads, assertions and product code stay intact.
const redirect = value => {
  if (typeof value !== 'string') return value;
  const normalized = value.replaceAll('\\', '/');
  const shots = path.resolve('.impeccable').replaceAll('\\', '/');
  if (normalized.toLowerCase() === shots.toLowerCase() || normalized.toLowerCase().startsWith(shots.toLowerCase() + '/'))
    return path.join(process.env.TEMP, 'screenshots-from-worktree', normalized.slice(shots.length));
  for (const name of ['webguide', 'flownav']) {
    const prefix = 'D:/dp-dev/tmp/' + name;
    if (normalized.toLowerCase() === prefix.toLowerCase() || normalized.toLowerCase().startsWith(prefix.toLowerCase() + '/'))
      return path.join(process.env.TEMP, 'fixed-output', name, normalized.slice(prefix.length));
  }
  return value;
};
for (const name of ['writeFileSync', 'mkdirSync']) {
  const original = fs[name];
  fs[name] = function(file, ...args) {
    const target = redirect(file);
    if (name === 'writeFileSync' && target !== file) fs.mkdirSync(path.dirname(target), {recursive:true});
    return original.call(this, target, ...args);
  };
}
for (const name of ['spawn', 'spawnSync', 'execFile', 'execFileSync']) {
  const original = cp[name];
  cp[name] = function(command, args, ...rest) {
    if (typeof command === 'string' && /(?:msedge|chrome|chromium)\.exe$/i.test(command)) {
      args = [...(args || []), '--disable-background-networking', '--disable-component-update',
        '--disable-sync', '--no-pings', '--disable-domain-reliability', '--no-proxy-server',
        '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1'];
    }
    return original.call(this, command, args, ...rest);
  };
}
const nativeFetch = globalThis.fetch;
globalThis.fetch = function(input, ...rest) {
  const u = new URL(typeof input === 'string' || input instanceof URL ? input : input.url);
  if (['http:', 'https:'].includes(u.protocol) && !['localhost', '127.0.0.1', '[::1]'].includes(u.hostname)) {
    throw Error('Offline verification rejects external fetch');
  }
  return nativeFetch(input, ...rest);
};
syncBuiltinESMExports();
