const { randomUUID } = require('node:crypto');

// One bounded handshake. Only the target renderer and nonce can settle it.
function createClosePreparation({ timeoutMs = 8000 } = {}) {
  let pending = null;
  const prepare = (contents) => {
    if (!contents || contents.isDestroyed()) return Promise.resolve(true);
    if (pending) return pending.promise;
    const nonce = randomUUID();
    let resolve;
    const promise = new Promise((done) => { resolve = done; });
    const finish = (ready) => {
      if (!pending || pending.nonce !== nonce) return;
      clearTimeout(pending.timer);
      pending = null;
      resolve(ready === true);
    };
    const timer = setTimeout(() => finish(false), timeoutMs);
    pending = { nonce, senderId: contents.id, promise, timer, finish };
    try { contents.send('window:prepare-close', nonce); }
    catch { finish(false); }
    return promise;
  };
  const acknowledge = (senderId, nonce, ready) => {
    if (!pending || pending.senderId !== senderId || pending.nonce !== nonce) return false;
    pending.finish(ready);
    return true;
  };
  return { prepare, acknowledge };
}
module.exports = { createClosePreparation };
