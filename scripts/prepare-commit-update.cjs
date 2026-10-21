const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { commitVersion, validCommitUpdate } = require('../desktop/commit-channel.cjs');

function prepare(root, { commit, branch, count }) {
  if (branch !== 'Texa_MacOS') throw new Error('Commit updates must come from Texa_MacOS');
  const version = commitVersion(fs.readFileSync(path.join(root, 'VERSION'), 'utf8').trim(), count, commit);
  const identity = { sourceCommit: commit, sourceBranch: branch, channel: 'commit' };
  for (const directory of ['frontend', 'desktop']) {
    const file = path.join(root, directory, 'package.json'); const data = JSON.parse(fs.readFileSync(file, 'utf8'));
    data.version = version;
    if (directory === 'desktop') {
      data.texaBuild = identity;
      data.build.win = { ...data.build.win, verifyUpdateCodeSignature: false };
      data.build.publish[0].releaseType = 'prerelease';
      data.build.publish[0].channel = 'commit';
    }
    fs.writeFileSync(file, JSON.stringify(data, null, 2) + '\n');
    const lockFile = path.join(root, directory, 'package-lock.json'); const lock = JSON.parse(fs.readFileSync(lockFile, 'utf8'));
    lock.version = version; lock.packages[''].version = version;
    fs.writeFileSync(lockFile, JSON.stringify(lock, null, 2) + '\n');
  }
  fs.writeFileSync(path.join(root, 'VERSION'), version + '\n');
  return { version, ...identity };
}
function annotate(root) {
  const yaml = require(path.join(root, 'desktop/node_modules/js-yaml'));
  const metadata = JSON.parse(fs.readFileSync(path.join(root, 'desktop/package.json'), 'utf8'));
  const identity = { version: metadata.version, ...metadata.texaBuild };
  if (!validCommitUpdate(identity, 'Texa_MacOS')) throw new Error('Missing commit identity');
  const directory = path.join(root, 'release');
  const manifests = fs.readdirSync(directory).filter(name => /^commit(?:-mac)?\.yml$/.test(name));
  if (!manifests.length) throw new Error('Missing commit update manifest');
  for (const name of manifests) {
    const file = path.join(directory, name); const manifest = yaml.load(fs.readFileSync(file, 'utf8'));
    if (manifest.version !== identity.version || !manifest.files?.length) throw new Error('Manifest version/files mismatch');
    Object.assign(manifest, identity, { releaseName: `Texa 修复 ${identity.sourceCommit.slice(0, 8)}` });
    fs.writeFileSync(file, yaml.dump(manifest));
  }
  fs.writeFileSync(path.join(directory, 'commit-build.json'), JSON.stringify(identity, null, 2) + '\n');
}
if (require.main === module) {
  const root = path.resolve(__dirname, '..');
  if (process.argv[2] === 'annotate') annotate(root);
  else {
    const git = (...args) => execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim();
    const identity = prepare(root, { commit: git('rev-parse', 'HEAD'), branch: process.env.GITHUB_REF_NAME || git('branch', '--show-current'), count: Number(git('rev-list', '--count', 'HEAD')) });
    if (process.env.GITHUB_OUTPUT) fs.appendFileSync(process.env.GITHUB_OUTPUT, `version=${identity.version}\n`);
    console.log(JSON.stringify(identity));
  }
}
module.exports = { prepare, annotate };
