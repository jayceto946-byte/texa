const { test } = require('node:test');
const assert = require('node:assert/strict');
const yaml = require('js-yaml');
const { NsisUpdater } = require('electron-updater');
const { CommitProvider } = require('./commit-provider.cjs');
const { configureCommitChannel } = require('./commit-channel.cjs');

function release(count, sha, extra = {}) {
  return { tag_name: `v1.0.1-commit.${count}.${sha.repeat(8)}`, draft: false,
    assets: [{ name: 'commit.yml' }, { name: 'Texa.exe' }], ...extra };
}

test('unordered releases, drafts and unrelated releases select the highest complete commit directly', async () => {
  const updater = new NsisUpdater(null, { version: '1.0.1-commit.232.dddddddd', name: 'Texa', isPackaged: true });
  configureCommitChannel(updater);
  const provider = new CommitProvider({ owner: 'owner', repo: 'repo', sourceBranch: 'Texa_MacOS' }, updater, { platform: 'win32', executor: {} });
  const urls = [];
  provider.httpRequest = async url => {
    urls.push(url.href);
    if (url.hostname === 'api.github.com') return JSON.stringify([
      release(267, 'b'), release(270, 'c', { draft: true }), release(269, 'c', { assets: [] }),
      release(268, 'a'), { tag_name: 'v9.0.0', assets: [] },
    ]);
    return yaml.dump({ version: '1.0.1-commit.268.aaaaaaaa', sourceCommit: 'a'.repeat(40),
      sourceBranch: 'Texa_MacOS', files: [{ url: 'Texa.exe', sha512: 'fixture' }] });
  };
  const info = await provider.getLatestVersion();
  assert.equal(info.version, '1.0.1-commit.268.aaaaaaaa');
  assert.equal(await updater.isUpdateAvailable(info), true, 'skip all intermediate versions');
  assert.match(urls[1], /download\/v1.0.1-commit.268.aaaaaaaa\/commit.yml$/);
  assert.match(provider.resolveFiles(info)[0].url.href, /download\/v1.0.1-commit.268.aaaaaaaa\/Texa.exe$/);
});

test('release pagination and manifest identity are checked before offering an update', async () => {
  const updater = { channel: 'commit' };
  const provider = new CommitProvider({ owner: 'owner', repo: 'repo', sourceBranch: 'Texa_MacOS' }, updater, { platform: 'win32', executor: {} });
  let pages = 0;
  provider.httpRequest = async url => {
    if (url.hostname === 'api.github.com') {
      pages++;
      return JSON.stringify(pages === 1 ? Array.from({ length: 100 }, () => ({ tag_name: 'other' })) : [release(268, 'a')]);
    }
    return yaml.dump({ version: '1.0.1-commit.268.aaaaaaaa', sourceCommit: 'a'.repeat(40), sourceBranch: 'other' });
  };
  await assert.rejects(provider.getLatestVersion(), /源码分支不一致/);
  assert.equal(pages, 2);
});
