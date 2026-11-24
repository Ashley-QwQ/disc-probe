import {once} from 'node:events';
import {readFile} from 'node:fs/promises';
import {createServer} from 'node:http';
import {extname, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const web = fileURLToPath(new URL('../discprobe/web', import.meta.url));
const types = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.woff2': 'font/woff2',
  '.png': 'image/png', '.webp': 'image/webp', '.ico': 'image/x-icon',
};

export async function serveBrowserFixture(routes) {
  const server = createServer(async (request, response) => {
    try {
      const path = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname);
      if (routes.has(path)) {
        const [type, body] = routes.get(path);
        response.setHeader('Content-Type', type);
        return response.end(body);
      }
      const file = resolve(web, '.' + path);
      if (!file.startsWith(web + sep) || /b[l]ind/i.test(file)) throw Error('Outside the fixture');
      const body = await readFile(file);
      response.setHeader('Content-Type', types[extname(file)] ?? 'application/octet-stream');
      response.end(body);
    } catch {
      response.writeHead(404).end();
    }
  }).listen(0, '127.0.0.1');
  await once(server, 'listening');
  const {port} = server.address();
  const close = () => new Promise(done => {
    server.close(done);
    server.closeAllConnections();
  });
  if (port === 8765) {
    await close();
    throw Error('Fixture requires an isolated port');
  }
  return {origin: `http://127.0.0.1:${port}`, close};
}
