const assert = require('node:assert/strict');
const test = require('node:test');
const { createClosePreparation } = require('./window-close.cjs');

test('close waits for its renderer and coalesces concurrent close/quit', async () => {
  const preparation = createClosePreparation(); let token;
  const target = { id: 10, isDestroyed: () => false, send: (_channel, nonce) => { token = nonce; } };
  const result = preparation.prepare(target);
  assert.equal(preparation.prepare(target), result);
  assert.equal(preparation.acknowledge(11, token, true), false);
  assert.equal(preparation.acknowledge(10, 'old-token', true), false);
  assert.equal(preparation.acknowledge(10, token, true), true);
  assert.equal(await result, true);
});
test('failed draft flush vetoes closure without stopping backend', async () => {
  const preparation = createClosePreparation(); let token;
  const result = preparation.prepare({ id: 10, isDestroyed: () => false, send: (_channel, nonce) => { token = nonce; } });
  preparation.acknowledge(10, token, false);
  assert.equal(await result, false);
});
test('unresponsive renderer times out safely and stale acknowledgements do not revive it', async () => {
  const preparation = createClosePreparation({ timeoutMs: 5 }); let token;
  const result = preparation.prepare({ id: 10, isDestroyed: () => false, send: (_channel, nonce) => { token = nonce; } });
  assert.equal(await result, false);
  assert.equal(preparation.acknowledge(10, token, true), false);
});
test('startup without a window can quit and send failure vetoes safely', async () => {
  const preparation = createClosePreparation();
  assert.equal(await preparation.prepare(null), true);
  assert.equal(await preparation.prepare({ id: 1, isDestroyed: () => false, send: () => { throw new Error('closed'); } }), false);
});
