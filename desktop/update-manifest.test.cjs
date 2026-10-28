const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { afterPack, artifactBuildStarted } = require('./update-manifest.cjs');

test('NSIS manifest measures final edited files, includes Unicode paths and excludes itself', async t => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'texa-update-manifest-'));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  await fs.mkdir(path.join(root, 'resources'));
  await fs.writeFile(path.join(root, 'Texa.exe'), 'before signing');
  await fs.writeFile(path.join(root, 'resources', '中文.txt'), 'text');
  afterPack({ electronPlatformName: 'win32', arch: 1, appOutDir: root });
  await fs.writeFile(path.join(root, 'Texa.exe'), 'final executable after resource editing/signing');
  const event = { targetPresentableName: 'nsis', arch: 1 };
  await artifactBuildStarted(event);
  await artifactBuildStarted(event);
  const text = await fs.readFile(path.join(root, 'resources/texa-update-files.txt'), 'utf16le');
  assert.match(text, /TEXA-UPDATE-FILES-1\r\n2\r\n/);
  assert.match(text, /Texa\.exe\r\n47\r\n/);
  assert.match(text, /resources\\中文\.txt\r\n4\r\n/);
  assert.ok(text.endsWith('END\r\n'));
  assert.ok(!text.includes(root));
  assert.ok(!text.includes('texa-update-files.txt'));
});
