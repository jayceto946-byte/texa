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

test('REST rate limit falls back to public Atom, sorts versions and skips missing manifests', async () => {
  const updater = new NsisUpdater(null, { version: '1.0.1-commit.267.dddddddd', name: 'Texa', isPackaged: true });
  configureCommitChannel(updater);
  const provider = new CommitProvider({ owner: 'owner', repo: 'repo', sourceBranch: 'Texa_MacOS' }, updater, { platform: 'win32', executor: {} });
  const urls = [];
  provider.httpRequest = async url => {
    urls.push(url.href);
    if (url.hostname === 'api.github.com') throw Object.assign(new Error('API rate limit exceeded'), { statusCode: 403 });
    if (url.pathname.endsWith('.atom')) return '<feed>' + [release(266, 'b'), release(269, 'c'), release(268, 'a')]
      .map(r => `<entry><title>Build</title><link href="https://github.com/owner/repo/releases/tag/${r.tag_name}"/></entry>`).join('') + '</feed>';
    if (url.pathname.includes('commit.269.')) throw Object.assign(new Error('missing'), { statusCode: 404 });
    return yaml.dump({ version: '1.0.1-commit.268.aaaaaaaa', sourceCommit: 'a'.repeat(40), sourceBranch: 'Texa_MacOS',
      files: [{ url: 'Texa.exe', sha512: 'fixture' }] });
  };
  const info = await provider.getLatestVersion();
  assert.equal(info.version, '1.0.1-commit.268.aaaaaaaa');
  assert.equal(await updater.isUpdateAvailable(info), true);
  assert.match(urls[1], /github.com\/owner\/repo\/releases.atom$/);
  assert.match(provider.resolveFiles(info)[0].url.href, /commit.268.aaaaaaaa\/Texa.exe$/);
  assert.equal(urls.length, 4);
});

test('Atom fallback retains branch validation and does not hide invalid manifests', async () => {
  const provider = new CommitProvider({ owner: 'owner', repo: 'repo', sourceBranch: 'Texa_MacOS' }, { channel: 'commit' }, { platform: 'win32', executor: {} });
  provider.httpRequest = async url => {
    if (url.hostname === 'api.github.com') throw Object.assign(new Error('too many requests'), { statusCode: 429 });
    if (url.pathname.endsWith('.atom')) return '<feed><entry><title>Build</title><link href="https://github.com/owner/repo/releases/tag/v1.0.1-commit.268.aaaaaaaa"/></entry></feed>';
    return yaml.dump({ version: '1.0.1-commit.268.aaaaaaaa', sourceCommit: 'a'.repeat(40), sourceBranch: 'other', files: [{ url: 'Texa.exe' }] });
  };
  await assert.rejects(provider.getLatestVersion(), /源码分支不一致/);
});

test('updater errors show readable actions instead of HTTP bodies and headers', () => {
  const { updateErrorMessage } = require('./update-errors.cjs');
  const error = Object.assign(new Error('403 method: GET https://api.github.com/ Headers: { "x-ratelimit-remaining": "0" } API rate limit exceeded'), { statusCode: 403 });
  assert.equal(updateErrorMessage(error), '更新服务请求额度暂时用完，请稍后重试。');
  assert.equal(updateErrorMessage(new Error('net::ERR_CONNECTION_RESET https://github.com')), '无法连接更新服务，请检查网络后重试。');
  assert.equal(updateErrorMessage(new Error('更新清单与发布版本或源码分支不一致。')), '更新清单与发布版本或源码分支不一致。');
  assert.equal(updateErrorMessage(new Error('500 url https://example.com response {body}')), '更新失败，请稍后重试。');
});

test('macOS uses commit-mac and ZIP assets without selecting the Windows channel', async () => {
  const provider = new CommitProvider({ owner: 'owner', repo: 'repo', sourceBranch: 'Texa_MacOS' }, { channel: 'commit' }, { platform: 'darwin', executor: {} });
  const urls = [];
  provider.httpRequest = async url => {
    urls.push(url.href);
    if (url.hostname === 'api.github.com') return JSON.stringify([release(269, 'b'), release(268, 'a', {
      assets: [{name:'commit-mac.yml'}, {name:'Texa-mac.zip'}, {name:'Texa-mac.dmg'}],
    })]);
    return yaml.dump({ version: '1.0.1-commit.268.aaaaaaaa', sourceCommit: 'a'.repeat(40), sourceBranch: 'Texa_MacOS', files: [{url:'Texa-mac.zip',sha512:'fixture'}, {url:'Texa-mac.dmg',sha512:'fixture'}] });
  };
  const info = await provider.getLatestVersion();
  assert.match(urls[1], /commit-mac.yml$/);
  assert.equal(info.version, '1.0.1-commit.268.aaaaaaaa');
  assert.match(provider.resolveFiles(info)[0].url.href, /Texa-mac.zip$/);
});
