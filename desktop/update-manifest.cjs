const fs = require('node:fs/promises');
const path = require('node:path');

const windowsOutputs = new Map();
const manifestName = 'resources/texa-update-files.txt';

function afterPack(context) {
  if (context.electronPlatformName === 'win32') windowsOutputs.set(context.arch, context.appOutDir);
}

async function writeManifest(directory) {
  const files = [];
  async function visit(relative) {
    const entries = await fs.readdir(path.join(directory, relative), { withFileTypes: true });
    for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      const name = relative ? `${relative}/${entry.name}` : entry.name;
      // electron-builder adds/signs this optional helper later, in packArch.
      if (name === manifestName || name === 'resources/elevate.exe') continue;
      if (entry.isDirectory()) await visit(name);
      else {
        if (!entry.isFile() || /[\r\n]/.test(name)) throw new Error(`Unsupported Windows update entry: ${name}`);
        const { size } = await fs.stat(path.join(directory, name));
        if (size > 0x7fffffff) throw new Error(`Windows update file exceeds NSIS size support: ${name}`);
        files.push([name.replaceAll('/', '\\'), size]);
      }
    }
  }
  await visit('');
  // Written at artifactBuildStarted, after executable editing/signing and before
  // NSIS packs the app. This detects missing/truncated extraction, without
  // repeating the updater's archive checksum over thousands of installed files.
  const lines = ['TEXA-UPDATE-FILES-1', String(files.length), ...files.flatMap(([name, size]) => [name, String(size)]), 'END', ''];
  await fs.writeFile(path.join(directory, manifestName), Buffer.from(lines.join('\r\n'), 'utf16le'));
  return files;
}

async function artifactBuildStarted(event) {
  if (event.targetPresentableName !== 'nsis') return;
  const outputs = event.arch === null ? [...windowsOutputs.values()] : [windowsOutputs.get(event.arch)];
  if (!outputs.length || outputs.some(directory => !directory)) throw new Error('NSIS update manifest requires a normal Windows packaging run (afterPack).');
  for (const directory of outputs) await writeManifest(directory);
}

module.exports = { afterPack, artifactBuildStarted, writeManifest };
