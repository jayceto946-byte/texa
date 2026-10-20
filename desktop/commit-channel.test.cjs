const { test } = require('node:test');
const assert = require('node:assert/strict');
const { commitVersion, validCommitUpdate, configureCommitChannel } = require('./commit-channel.cjs');
test('commit channel rejects older releases using the real updater version comparison', async () => {
  const { NsisUpdater } = require('electron-updater');
  const updater = new NsisUpdater(null, { version: '1.0.1-commit.232.aaaaaaaa', name: 'Texa', isPackaged: true });
  configureCommitChannel(updater);
  assert.equal(updater.channel, 'commit');
  assert.equal(updater.allowPrerelease, true);
  assert.equal(updater.allowDowngrade, false);
  assert.equal(await updater.isUpdateAvailable({ version: '1.0.1-commit.231.bbbbbbbb' }), false);
  assert.equal(await updater.isUpdateAvailable({ version: '1.0.1-commit.233.cccccccc' }), true);
});
test('commit builds order by history count and bind the source identity', () => {
  const sha = 'a'.repeat(40);
  assert.equal(commitVersion('1.0.0', 82, sha), '1.0.1-commit.82.aaaaaaaa');
  assert.equal(validCommitUpdate({ version: '1.0.1-commit.82.aaaaaaaa', sourceCommit: sha, sourceBranch: 'Texa_MacOS' }, 'Texa_MacOS'), true);
  assert.equal(validCommitUpdate({ version: '1.0.1', sourceCommit: sha, sourceBranch: 'Texa_MacOS' }, 'Texa_MacOS'), false);
  assert.equal(validCommitUpdate({ version: '1.0.1-commit.82.aaaaaaaa', sourceCommit: sha, sourceBranch: 'other' }, 'Texa_MacOS'), false);
  assert.throws(() => commitVersion('1.0.0', -1, sha));
});
