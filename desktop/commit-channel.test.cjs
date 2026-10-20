const { test } = require('node:test');
const assert = require('node:assert/strict');
const { commitVersion, validCommitUpdate } = require('./commit-channel.cjs');
test('commit builds order by history count and bind the source identity', () => {
  const sha = 'a'.repeat(40);
  assert.equal(commitVersion('1.0.0', 82, sha), '1.0.1-commit.82.aaaaaaaa');
  assert.equal(validCommitUpdate({ version: '1.0.1-commit.82.aaaaaaaa', sourceCommit: sha, sourceBranch: 'Texa_MacOS' }, 'Texa_MacOS'), true);
  assert.equal(validCommitUpdate({ version: '1.0.1', sourceCommit: sha, sourceBranch: 'Texa_MacOS' }, 'Texa_MacOS'), false);
  assert.equal(validCommitUpdate({ version: '1.0.1-commit.82.aaaaaaaa', sourceCommit: sha, sourceBranch: 'other' }, 'Texa_MacOS'), false);
  assert.throws(() => commitVersion('1.0.0', -1, sha));
});
