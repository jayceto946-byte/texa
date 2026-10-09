/* Package already-built macOS resources with the installed Electron distribution.
 * Requires installed dependencies and cached builder helpers; no downloads.
 * Dependency traversal reads installed
 * package.json files. The traversal marker exists only in the staging manifest.
 */
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');

async function main() {
  if (process.platform !== 'darwin' || process.arch !== 'arm64') {
    throw new Error('This packaging entry requires macOS arm64.');
  }
  const args = process.argv.slice(2);
  const option = name => {
    const index = args.indexOf(name);
    if (index < 0 || !args[index + 1] || args[index + 1].startsWith('--')) {
      throw new Error(`Required option: ${name}`);
    }
    return path.resolve(args[index + 1]);
  };
  const targetIndex = args.indexOf('--target');
  const targets = targetIndex < 0 ? ['dmg', 'zip'] : [args[targetIndex + 1]];
  if (targets.some(target => !['dmg', 'zip'].includes(target))) throw new Error('Target must be dmg or zip.');
  const backend = option('--backend');
  const output = option('--output');
  if (fs.existsSync(output) && fs.readdirSync(output).length) {
    throw new Error('Output directory must be empty; existing candidates are preserved.');
  }
  const root = path.resolve(__dirname, '..');
  const desktop = path.join(root, 'desktop');
  const electronDist = path.join(desktop, 'node_modules/electron/dist');
  const embedding = path.join(root, 'assets/embedding-runtime');
  for (const required of [path.join(backend, 'backend_server/backend_server'),
    path.join(electronDist, 'Electron.app'), embedding]) {
    if (!fs.existsSync(required)) throw new Error(`Missing prebuilt resource: ${required}`);
  }
  if (targets.includes('dmg')) {
    // Pin an existing helper explicitly so electron-builder cannot download it.
    let helper = process.env.CUSTOM_DMGBUILD_PATH;
    if (!helper) {
      const cache = process.env.ELECTRON_BUILDER_CACHE || path.join(os.homedir(), 'Library/Caches/electron-builder');
      const releaseDir = path.join(cache, 'dmg-builder@1.2.5');
      const names = fs.existsSync(releaseDir) ? fs.readdirSync(releaseDir).sort() : [];
      helper = names.filter(name => name.startsWith('dmgbuild-bundle-arm64-'))
        .map(name => path.join(releaseDir, name, 'dmgbuild'))
        .find(file => fs.existsSync(file) && fs.statSync(file).isFile());
    }
    if (!helper || !fs.existsSync(helper) || !fs.statSync(helper).isFile()) {
      throw new Error('Cached dmgbuild helper missing; set CUSTOM_DMGBUILD_PATH to an existing helper.');
    }
    process.env.CUSTOM_DMGBUILD_PATH = path.resolve(helper);
  }
  const staging = fs.mkdtempSync(path.join(os.tmpdir(), 'texa-offline-package-'));
  const pkg = JSON.parse(fs.readFileSync(path.join(desktop, 'package.json'), 'utf8'));
  const config = { ...pkg.build, directories: { output },
    electronDist, npmRebuild: false,
    extraResources: [{ from: backend, to: 'backend', filter: ['**/*'] },
      { from: embedding, to: 'embedding-runtime', filter: ['**/*'] }],
  };
  // electron-builder 26 includes a traversal collector for installed modules.
  // This avoids invoking an absent npm CLI and preserves source package/lock files.
  pkg.packageManager = 'traversal@0';
  delete pkg.build;
  fs.writeFileSync(path.join(staging, 'package.json'), JSON.stringify(pkg, null, 2));
  for (const name of fs.readdirSync(desktop)) {
    if (name === 'package.json' || name === 'node_modules' || name.endsWith('.test.cjs')) continue;
    const source = path.join(desktop, name);
    if (fs.statSync(source).isFile() || name === 'assets') {
      fs.cpSync(source, path.join(staging, name), { recursive: true });
    }
  }
  fs.symlinkSync(path.join(desktop, 'node_modules'), path.join(staging, 'node_modules'), 'dir');
  const builder = require(path.join(desktop, 'node_modules/electron-builder'));
  const artifacts = await builder.build({ projectDir: staging, config,
    targets: builder.Platform.MAC.createTarget(targets, builder.Arch.arm64),
    publish: 'never',
  });
  console.log(JSON.stringify({ artifacts, staging, backend, electronDist }, null, 2));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
