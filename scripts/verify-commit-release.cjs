const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { validCommitUpdate } = require('../desktop/commit-channel.cjs');

function verifyRelease(directory, commit, version) {
  const yaml = require('../desktop/node_modules/js-yaml');
  const verified = [];
  for (const [manifestName, required] of [['commit.yml', ['.exe']], ['commit-mac.yml', ['.zip', '.dmg']]]) {
    const info = yaml.load(fs.readFileSync(path.join(directory, manifestName), 'utf8'));
    if (!validCommitUpdate(info, 'Texa_MacOS') || info.sourceCommit !== commit || info.version !== version || info.channel !== 'commit') {
      throw new Error(`${manifestName}: release identity mismatch`);
    }
    if (!Array.isArray(info.files) || !info.files.length) throw new Error(`${manifestName}: no update files`);
    const extensions = new Set();
    for (const file of info.files) {
      if (typeof file.url !== 'string' || file.url !== path.basename(file.url) || /[\\/]/.test(file.url)) throw new Error('Unsafe update asset path');
      const bytes = fs.readFileSync(path.join(directory, file.url));
      if (crypto.createHash('sha512').update(bytes).digest('base64') !== file.sha512 || bytes.length !== file.size) {
        throw new Error(`${file.url}: update asset checksum/size mismatch`);
      }
      extensions.add(path.extname(file.url));
      verified.push(file.url);
    }
    if (!required.every(ext => extensions.has(ext))) throw new Error(`${manifestName}: missing platform update asset`);
    const primary = info.files.find(file => file.url === info.path);
    if (!primary || primary.sha512 !== info.sha512) throw new Error(`${manifestName}: primary asset mismatch`);
  }
  return verified;
}
if (require.main === module) {
  const [directory, commit, version] = process.argv.slice(2);
  console.log(JSON.stringify({ commit, version, files: verifyRelease(directory, commit, version) }));
}
module.exports = { verifyRelease };
