// Inspect packaging overhead without extracting or rehashing application files.
const fs = require('node:fs');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const { getPath7za } = require('../desktop/node_modules/app-builder-lib/out/toolsets/7zip');
const run = promisify(execFile);

async function verifyPayloadSize(installer) {
  const { stdout } = await run(await getPath7za(), ['l', '-slt', installer]);
  const entries = stdout.split(/\r?\n\r?\n/).map(block => Object.fromEntries(
    block.split(/\r?\n/).filter(line => line.includes(' = ')).map(line => {
      const split = line.indexOf(' = ');
      return [line.slice(0, split), line.slice(split + 3)];
    })));
  const payloadBytes = Math.max(0, ...entries.filter(entry => /(?:app-(?:32|64|arm64)|texa-app)\.7z$/.test(entry.Path || '')).map(entry => Number(entry.Size)));
  if (!payloadBytes) throw new Error('NSIS application archive not found');
  const installerBytes = fs.statSync(installer).size;
  // Current Windows x64 releases embed one archive plus NSIS plugins/UI and
  // an uninstaller. Two archive-sized data blocks must never be published.
  if (installerBytes > payloadBytes * 1.1 + 8 * 1024 * 1024) {
    throw new Error(`NSIS installer has excessive payload overhead: installer=${installerBytes}, app archive=${payloadBytes}`);
  }
  return { installerBytes, payloadBytes, overheadBytes: installerBytes - payloadBytes };
}

if (require.main === module) verifyPayloadSize(process.argv[2]).then(result => console.log(JSON.stringify(result)))
  .catch(error => { console.error(error); process.exitCode = 1; });
module.exports = { verifyPayloadSize };
