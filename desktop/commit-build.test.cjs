const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { prepare, annotate } = require('../scripts/prepare-commit-update.cjs');
for (const [commit, expectedVersion] of [
  ['b'.repeat(40), '1.0.1-commit.80.bbbbbbbb'],
  ['05809045aa0dd15f75092dd22b96e31fda106af0', '1.0.1-commit.80.g05809045'],
]) test(`CI binds package, lockfiles, VERSION and update manifests to commit ${commit.slice(0, 8)}`, t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'texa-commit-build-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  fs.writeFileSync(path.join(root, 'VERSION'), '1.0.0\n');
  for (const directory of ['desktop', 'frontend']) {
    fs.mkdirSync(path.join(root, directory));
    fs.writeFileSync(path.join(root, directory, 'package.json'), JSON.stringify({ version: '1.0.0', build: { mac: { identity: null }, publish: [{}] } }));
    fs.writeFileSync(path.join(root, directory, 'package-lock.json'), JSON.stringify({ version: '1.0.0', packages: { '': { version: '1.0.0' } } }));
  }
  const identity = prepare(root, { commit, count: 80, branch: 'Texa_MacOS' });
  const pkg = JSON.parse(fs.readFileSync(path.join(root, 'desktop/package.json')));
  assert.equal(pkg.version, expectedVersion);
  assert.deepEqual(pkg.texaBuild, { sourceCommit: commit, sourceBranch: 'Texa_MacOS', channel: 'commit' });
  assert.equal(pkg.build.mac.identity, null);
  assert.equal(pkg.build.mac.notarize, undefined);
  assert.equal(pkg.build.win.verifyUpdateCodeSignature, false);
  assert.equal(JSON.parse(fs.readFileSync(path.join(root, 'frontend/package-lock.json'))).packages[''].version, identity.version);
  fs.symlinkSync(path.join(__dirname, 'node_modules'), path.join(root, 'desktop/node_modules'), process.platform === 'win32' ? 'junction' : 'dir');
  fs.mkdirSync(path.join(root, 'release'));
  const packagedVersion = require('semver').valid(identity.version, true);
  fs.writeFileSync(path.join(root, 'release/commit-mac.yml'), `version: ${packagedVersion}\nfiles:\n  - url: Texa.zip\n    sha512: example\n`);
  annotate(root);
  const yaml = require('js-yaml');
  const manifest = yaml.load(fs.readFileSync(path.join(root, 'release/commit-mac.yml'), 'utf8'));
  assert.equal(manifest.sourceCommit, commit);
  assert.equal(manifest.sourceBranch, 'Texa_MacOS');
  assert.throws(() => prepare(root, { commit, count: 80, branch: 'other' }));
});
