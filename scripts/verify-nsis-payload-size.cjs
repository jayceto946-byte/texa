// Inspect packaging overhead without extracting or rehashing application files.
const fs = require('node:fs');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const { getPath7za } = require('../desktop/node_modules/app-builder-lib/out/toolsets/7zip');
const run = promisify(execFile);

function applicationPayloadBytes(listing) {
  const entries = [];
  let entry;
  // A Path field starts a record. Windows 7za output must not depend on the
  // Unix tool's blank-line separators or on one particular CR/LF sequence.
  for (const line of listing.split(/[\r\n]+/)) {
    const split = line.indexOf(' = ');
    if (split < 0) continue;
    const key = line.slice(0, split).trim();
    if (key === 'Path') { entry = {}; entries.push(entry); }
    if (entry) entry[key] = line.slice(split + 3).trim();
  }
  return Math.max(0, ...entries.filter(entry => /(?:app-(?:32|64|arm64)|texa-app)\.7z$/.test(entry.Path || '')).map(entry => Number(entry.Size)));
}

async function verifyPayloadSize(installer) {
  const { stdout } = await run(await getPath7za(), ['l', '-slt', installer]);
  const payloadBytes = applicationPayloadBytes(stdout);
  if (!payloadBytes) throw new Error(`NSIS application archive not found in 7-Zip listing:\n${stdout}`);
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
module.exports = { verifyPayloadSize, applicationPayloadBytes };
