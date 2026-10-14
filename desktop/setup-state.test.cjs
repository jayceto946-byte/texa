const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { readSetupComplete, writeSetupComplete } = require('./setup-state.cjs');

test('desktop completion survives restart independently of the backend origin', t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'texa-setup-test-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'user-data', 'setup-complete.json');
  assert.equal(readSetupComplete(file), false);
  assert.equal(writeSetupComplete(file), true);
  assert.equal(readSetupComplete(file), true);
  assert.deepEqual(JSON.parse(fs.readFileSync(file, 'utf8')), { version: 3, complete: true });
  assert.equal(fs.existsSync(`${file}.tmp`), false);
});

test('corrupt, old and non-boolean flags do not complete setup', t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'texa-setup-test-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'setup.json');
  for (const value of ['broken', '{"version":2,"complete":true}', '{"version":3,"complete":"true"}']) {
    fs.writeFileSync(file, value);
    assert.equal(readSetupComplete(file), false);
  }
});

test('an unwritable completion target reports failure', t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'texa-setup-test-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  assert.equal(writeSetupComplete(dir), false);
});
