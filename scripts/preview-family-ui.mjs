#!/usr/bin/env node
// Local UI preview. Streams Windows API/media through an existing SSH tunnel;
// never stores media or forwards editing/maintenance requests.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const port = Number(process.env.PHOTOHOUSE_PREVIEW_PORT || 18003);
const upstream = new URL(process.env.PHOTOHOUSE_PREVIEW_API || 'http://127.0.0.1:18002');
if (upstream.hostname !== '127.0.0.1' || upstream.protocol !== 'http:') {
  throw new Error('Use an existing loopback SSH tunnel as the preview API.');
}
const assets = {
  '/ui': ['index.html', 'text/html; charset=utf-8'],
  '/ui/': ['index.html', 'text/html; charset=utf-8'],
  '/ui/app.js': ['app.js', 'text/javascript; charset=utf-8'],
  '/ui/styles.css': ['styles.css', 'text/css; charset=utf-8'],
};
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1');
  const local = assets[url.pathname];
  if (local && ['GET', 'HEAD'].includes(req.method)) {
    try {
      const data = await readFile(fileURLToPath(new URL(`../backend/app/ui/${local[0]}`, import.meta.url)));
      res.writeHead(200, { 'Content-Type': local[1], 'Cache-Control': 'no-store' });
      res.end(req.method === 'HEAD' ? undefined : data);
    } catch (_) { res.writeHead(500); res.end('UI file unavailable'); }
    return;
  }
  const readSearch = req.method === 'POST' && ['/search/smart', '/search/captions'].includes(url.pathname);
  if (!['GET', 'HEAD'].includes(req.method) && !readSearch) {
    res.writeHead(403, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ detail: 'This design preview is read-only. Editing is available in the live PhotoHouse tab.' }));
    return;
  }
  // Pass only a relative path to keep this from becoming an arbitrary proxy.
  const request = http.request({ hostname: upstream.hostname, port: upstream.port,
    path: url.pathname + url.search, method: req.method,
    headers: { ...req.headers, host: upstream.host } }, (response) => {
    res.writeHead(response.statusCode, { ...response.headers, 'Cache-Control': 'no-store' });
    response.pipe(res);
  });
  request.setTimeout(60000, () => request.destroy(new Error('Upstream timeout')));
  request.on('error', () => {
    if (!res.headersSent) res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ detail: 'PhotoHouse tunnel unavailable. Check the localhost API connection.' }));
  });
  res.on('close', () => request.destroy());
  req.pipe(request);
});
server.listen(port, '127.0.0.1', () => console.log(`PhotoHouse design preview: http://127.0.0.1:${port}/ui`));
