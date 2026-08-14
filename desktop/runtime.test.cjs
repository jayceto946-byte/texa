const assert = require('node:assert/strict');
const fs = require('node:fs');
const net = require('node:net');
const path = require('node:path');
const test = require('node:test');
const { findAvailablePort, portFromUrl } = require('./runtime.cjs');

test('Texa branding preserves the existing desktop identity and userData paths', () => {
  const packageJson = JSON.parse(fs.readFileSync(path.join(__dirname, 'package.json'), 'utf8'));
  const mainSource = fs.readFileSync(path.join(__dirname, 'main.cjs'), 'utf8');

  assert.equal(packageJson.name, 'texa-desktop');
  assert.equal(packageJson.build.productName, 'Texa');
  assert.equal(packageJson.build.artifactName, 'Texa-Setup-${version}.${ext}');
  assert.equal(packageJson.build.appId, 'local.kaoyan.assistant');
  assert.match(mainSource, /app\.setName\('Texa'\)/);
  assert.match(mainSource, /'考研智能辅助系统' : 'kaoyan-assistant-desktop'/);
  assert.match(mainSource, /app\.setPath\('userData'/);
});

test('portFromUrl resolves explicit and default HTTP ports', () => {
  assert.equal(portFromUrl('http://127.0.0.1:8123'), 8123);
  assert.equal(portFromUrl('https://example.com'), 443);
  assert.equal(portFromUrl('not a url'), 0);
});

test('findAvailablePort releases a bindable loopback port', async () => {
  const port = await findAvailablePort('127.0.0.1');
  assert.ok(Number.isInteger(port) && port > 0 && port <= 65535);

  await new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(port, '127.0.0.1', () => server.close(resolve));
  });
});
