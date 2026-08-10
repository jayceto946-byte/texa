const assert = require('node:assert/strict');
const net = require('node:net');
const test = require('node:test');
const { findAvailablePort, portFromUrl } = require('./runtime.cjs');

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
