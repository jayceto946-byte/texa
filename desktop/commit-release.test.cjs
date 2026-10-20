const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const yaml = require('js-yaml');
const { verifyRelease } = require('../scripts/verify-commit-release.cjs');

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'texa-release-check-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const sha = 'a'.repeat(40); const version = '1.0.1-commit.240.aaaaaaaa';
  for (const [manifest, names] of [['commit.yml', ['Texa.exe']], ['commit-mac.yml', ['Texa.zip', 'Texa.dmg']]]) {
    const files = names.map(url => {
      const data = Buffer.from(`test package ${url}`);
      fs.writeFileSync(path.join(root, url), data);
      return { url, size: data.length, sha512: crypto.createHash('sha512').update(data).digest('base64') };
    });
    fs.writeFileSync(path.join(root, manifest), yaml.dump({ version, sourceCommit: sha, sourceBranch: 'Texa_MacOS', channel: 'commit', files, path: files[0].url, sha512: files[0].sha512 }));
  }
  return { root, sha, version };
}
test('release gate verifies both platform manifests and actual package bytes', t => {
  const { root, sha, version } = fixture(t);
  assert.deepEqual(verifyRelease(root, sha, version), ['Texa.exe', 'Texa.zip', 'Texa.dmg']);
  fs.appendFileSync(path.join(root, 'Texa.zip'), 'corrupted');
  assert.throws(() => verifyRelease(root, sha, version), /checksum\/size mismatch/);
});
test('release gate rejects mixed commits and absent platform packages', t => {
  const { root, sha, version } = fixture(t);
  assert.throws(() => verifyRelease(root, 'b'.repeat(40), version), /identity mismatch/);
  const macPath = path.join(root, 'commit-mac.yml');
  const mac = yaml.load(fs.readFileSync(macPath, 'utf8'));
  mac.files.pop();
  fs.writeFileSync(macPath, yaml.dump(mac));
  assert.throws(() => verifyRelease(root, sha, version), /missing platform update asset/);
});
