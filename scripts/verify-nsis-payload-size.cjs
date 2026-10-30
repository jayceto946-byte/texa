// Inspect packaging overhead without extracting or rehashing application files.
const fs = require('node:fs');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const { getPath7za } = require('../desktop/node_modules/app-builder-lib/out/toolsets/7zip');
const run = promisify(execFile);

function byteCount(value, field, minimum = 1) {
  const bytes = Number(value);
  if (!/^\d+$/.test(value || '') || !Number.isSafeInteger(bytes) || bytes < minimum) {
    throw new Error(`Invalid or missing ${field} in 7-Zip listing`);
  }
  return bytes;
}

function applicationPayloadBytes(listing, installerBytes) {
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
  const [archive, ...files] = entries;
  if (archive?.Type === 'Nsis') {
    const payloads = files.filter(entry => /(?:^|[\\/])(?:app-(?:32|64|arm64)|texa-app)\.7z$/i.test(entry.Path));
    if (payloads.length) {
      // A compressed NSIS record can omit Size; Packed Size still describes
      // its stored bytes. Aliased paths may reference the same data block.
      return Math.max(...payloads.map(entry => byteCount(entry.Size || entry['Packed Size'], 'application archive size')));
    }
  }
  if (archive?.Type === '7z') {
    // Windows' standalone 7za has no NSIS handler: it scans past the EXE
    // stub and opens the uncompressed embedded 7z itself. Physical Size is
    // that archive's length, excluding both Offset and Tail Size.
    const paths = new Set(files.filter(entry => Number(entry.Size) > 0).map(entry => entry.Path.replace(/\\/g, '/')));
    if (!paths.has('Texa.exe') || !paths.has('resources/app.asar')) {
      throw new Error('Embedded 7z does not contain the Texa application');
    }
    const payloadBytes = byteCount(archive['Physical Size'], 'Physical Size');
    const offset = byteCount(archive.Offset, 'Offset');
    const tail = byteCount(archive['Tail Size'] ?? '0', 'Tail Size', 0);
    if (!Number.isSafeInteger(installerBytes) || offset + payloadBytes + tail !== installerBytes) {
      throw new Error('Embedded 7z byte range does not match the installer size');
    }
    return payloadBytes;
  }
  throw new Error('NSIS application archive not found in 7-Zip listing');
}

function verifyPayloadListing(listing, installerBytes) {
  const payloadBytes = applicationPayloadBytes(listing, installerBytes);
  if (!Number.isSafeInteger(installerBytes) || installerBytes < payloadBytes) {
    throw new Error('Application archive size exceeds the installer size');
  }
  // Current Windows x64 releases embed one archive plus NSIS plugins/UI and
  // an uninstaller. Two archive-sized data blocks must never be published.
  if (installerBytes > payloadBytes * 1.1 + 8 * 1024 * 1024) {
    throw new Error(`NSIS installer has excessive payload overhead: installer=${installerBytes}, app archive=${payloadBytes}`);
  }
  return { installerBytes, payloadBytes, overheadBytes: installerBytes - payloadBytes };
}

async function verifyPayloadSize(installer) {
  const { stdout } = await run(await getPath7za(), ['l', '-slt', installer], { maxBuffer: 8 * 1024 * 1024 });
  return verifyPayloadListing(stdout, fs.statSync(installer).size);
}

if (require.main === module) verifyPayloadSize(process.argv[2]).then(result => console.log(JSON.stringify(result)))
  .catch(error => { console.error(error); process.exitCode = 1; });
module.exports = { verifyPayloadSize, applicationPayloadBytes, verifyPayloadListing };
