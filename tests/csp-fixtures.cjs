// Opt-in CSP for the existing file-URL browser fixtures. frame-ancestors is checked
// separately over HTTP: fixture wrappers intentionally embed the test document.
const fs = require('node:fs');
const crypto = require('node:crypto');
const {syncBuiltinESMExports} = require('node:module');
const {fileURLToPath, pathToFileURL} = require('node:url');
const {dirname, join} = require('node:path');
const originalWrite = fs.writeFileSync;
const monitor = `<script>
window.cspViolations=[];
addEventListener('securitypolicyviolation',e=>{
  const message=e.effectiveDirective+': '+e.blockedURI;
  cspViolations.push(message); window.errors?.push('CSP '+message);
  window.reviewErrors?.push('CSP '+message);
  try { if(parent!==window)parent.cspViolations?.push(message); } catch {}
  console.error('CSP '+message);
});
new MutationObserver(()=>{
  if(!cspViolations.length)return;
  const r=document.getElementById('result');
  if(r&&!r.textContent.startsWith('FAIL: CSP'))r.textContent='FAIL: CSP '+cspViolations.join('; ');
}).observe(document.documentElement,{childList:true,subtree:true,characterData:true});
</script>`;
function protect(html) {
  if (/Content-Security-Policy/i.test(html)) return html;
  html = html.replace(/\r\n?/g, '\n');
  const head=html.indexOf('<head>'), script=html.search(/<script\b/i);
  html = head>=0 && (script<0 || head<script) ? html.replace('<head>', '<head>'+monitor) : html.replace(/(<(?:!doctype[^>]*|html[^>]*|meta[^>]*?)>)/i, '$1'+monitor);
  const hashes = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)]
    .filter(m => !/\bsrc\s*=/.test(m[1]))
    .map(m => "'sha256-"+crypto.createHash('sha256').update(m[2]).digest('base64')+"'");
  const policy = ["default-src 'self'", "script-src 'self' "+hashes.join(' '),
    "style-src 'self' 'unsafe-inline'", "connect-src 'self'", "img-src 'self' data: blob:",
    "font-src 'self'", "worker-src 'self'", "object-src 'none'", "base-uri 'self'", "form-action 'self'"].join('; ');
  // Put the policy before all scripts and styles, including the monitor itself.
  return html.replace(/<script>/, '<meta http-equiv="Content-Security-Policy" content="'+policy+'"><script>');
}
fs.writeFileSync = function(path, data, ...args) {
  if (String(path).endsWith('.html') && typeof data === 'string') {
    // Some browser tests embed a real repository preview instead of a generated fixture.
    data = data.replace(/(<iframe\b[^>]*\bsrc=")(file:[^"]+\.html(?:\?[^"]*)?)(")/gi, (all, before, href, after) => {
      const url = new URL(href), target = fileURLToPath(url);
      if (/b[l]ind/i.test(target)) throw Error('Excluded fixture path');
      const original = fs.readFileSync(target, 'utf8');
      if (/Content-Security-Policy/i.test(original)) return all;
      const copied = join(dirname(String(path)), 'csp-frame-'+crypto.randomUUID()+'.html');
      const base = '<base href="'+new URL('.',url).href+'">';
      originalWrite(copied, protect(original.replace('<head>', '<head>'+base)), 'utf8');
      const next=pathToFileURL(copied);next.search=url.search;
      return before+next.href+after;
    });
    data = protect(data);
  }
  return originalWrite.call(this, path, data, ...args);
};
syncBuiltinESMExports();
