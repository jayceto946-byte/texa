// CI-only integration check. It installs real NSIS packages in a disposable runner.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const http = require('node:http');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const { app } = require('electron');
const { NsisUpdater } = require('../desktop/node_modules/electron-updater');
const { ElectronHttpExecutor } = require('../desktop/node_modules/electron-updater/out/electronHttpExecutor');
const asar = require('../desktop/node_modules/@electron/asar');
const yaml = require('../desktop/node_modules/js-yaml');
const { configureCommitChannel, validCommitUpdate } = require('../desktop/commit-channel.cjs');
const { verifyRelease } = require('./verify-commit-release.cjs');
const run = promisify(execFile);
const sha256 = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');

async function main() {
  if (process.platform !== 'win32' || process.env.GITHUB_ACTIONS !== 'true') throw new Error('Requires a disposable Windows Actions runner');
  const root = path.resolve(process.env.TEXA_UPGRADE_ROOT || '');
  const relative = path.relative(path.resolve(process.env.RUNNER_TEMP), root);
  if (!relative || relative.startsWith('..') || path.isAbsolute(relative) || fs.existsSync(root)) throw new Error('Upgrade root must be a new directory inside RUNNER_TEMP');
  const baseline = path.resolve(process.env.TEXA_UPGRADE_BASELINE);
  if (sha256(baseline) !== '3255575d6d1dad2803e2890eeedbbfb96eb30cf69de3bf7f1d6d176033da1bb3') throw new Error('Previous inspection installer checksum mismatch');
  const release = path.resolve(__dirname, '../release');
  const expected = JSON.parse(fs.readFileSync(path.join(release, 'commit-build.json'), 'utf8'));
  verifyRelease(release, expected.sourceCommit, expected.version, 'windows');
  fs.mkdirSync(root, { recursive: true });
  app.setPath('userData', path.join(root, 'electron-user-data'));
  await app.whenReady();

  const installRoot = path.join(root, 'installed');
  const archive = path.join(installRoot, 'resources/app.asar');
  const readPackage = () => {
    asar.uncache(archive);
    return JSON.parse(asar.extractFile(archive, 'package.json').toString());
  };
  await run(baseline, ['/S', '/currentuser', `/D=${installRoot}`], { timeout: 180000, windowsHide: true });
  const previous = readPackage();
  if (previous.texaBuild?.sourceCommit !== '0411aa5e594464069a8d652c9d7b9f1f538fbd07') throw new Error('Installed baseline identity mismatch');

  const userData = path.join(process.env.APPDATA, '考研智能辅助系统');
  fs.mkdirSync(path.join(userData, 'data'), { recursive: true });
  const marker = path.join(userData, 'data/upgrade-preservation-fixture.json');
  fs.writeFileSync(marker, JSON.stringify({ fixture: true, note: 'Preserve existing user files during upgrade' }));
  const markerHash = sha256(marker);
  const manifest = yaml.load(fs.readFileSync(path.join(release, 'commit.yml'), 'utf8'));
  const served = new Set(['commit.yml', ...manifest.files.map(file => file.url)]);
  const server = http.createServer((request, response) => {
    const name = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname.slice(1));
    if (!served.has(name)) { response.writeHead(404); response.end(); return; }
    const file = path.join(release, name);
    response.setHeader('Content-Length', fs.statSync(file).size);
    fs.createReadStream(file).on('error', () => response.destroy()).pipe(response);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const updater = new NsisUpdater(null, {
      version: previous.version, name: 'Texa-upgrade-check', isPackaged: true,
      userDataPath: app.getPath('userData'), baseCachePath: path.join(root, 'cache'),
      appUpdateConfigPath: path.join(installRoot, 'resources/app-update.yml'),
      whenReady: () => app.whenReady(), onQuit: () => {},
    });
    updater.httpExecutor = new ElectronHttpExecutor();
    updater.autoDownload = false;
    updater.autoInstallOnAppQuit = false;
    updater.disableDifferentialDownload = true;
    updater.disableWebInstaller = true;
    configureCommitChannel(updater);
    updater.setFeedURL({ provider: 'generic', url: `http://127.0.0.1:${server.address().port}/` });
    const result = await updater.checkForUpdates();
    if (!validCommitUpdate(result?.updateInfo, 'Texa_MacOS') || result.updateInfo.sourceCommit !== expected.sourceCommit) throw new Error('Updater returned an incorrect commit');
    const [downloaded] = await updater.downloadUpdate();
    if (sha256(downloaded) !== sha256(path.join(release, manifest.path))) throw new Error('Updater downloaded incorrect bytes');
    if (await updater.verifySignature(downloaded) !== null) throw new Error('Unsigned update was rejected');
    updater.installDirectory = installRoot;
    // Preserve the updater's actual NSIS command and wait for its child to finish.
    let installation;
    updater.spawnLog = (file, args) => (installation = run(file, args, { timeout: 180000, windowsHide: true }));
    if (!updater.install(true, false) || !installation) throw new Error('Updater refused to start NSIS');
    await installation;
    const current = readPackage();
    if (current.version !== expected.version || current.texaBuild?.sourceCommit !== expected.sourceCommit) throw new Error('NSIS did not install the target commit');
    if (sha256(marker) !== markerHash) throw new Error('NSIS changed the existing user-data fixture');
    const config = yaml.load(fs.readFileSync(path.join(installRoot, 'resources/app-update.yml'), 'utf8'));
    if (config.publisherName != null || config.channel !== 'commit') throw new Error('Installed update configuration mismatch');
    const report = { baselineCommit: previous.texaBuild.sourceCommit, baselineVersion: previous.version,
      sourceCommit: expected.sourceCommit, version: current.version, artifact: manifest.path,
      sha256: sha256(downloaded), unsigned: true, actualUpdaterDownload: true, actualNsisUpgrade: true,
      userDataFixturePreserved: true, feed: 'loopback served from actual release files',
      nativeUiAcceptance: 'not performed', githubPublicFeedCheck: 'required after publication' };
    fs.writeFileSync(path.join(release, 'upgrade-verification.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report));
  } finally { await new Promise(resolve => server.close(resolve)); }
}
main().then(() => app.exit(0)).catch(error => { console.error(error); app.exit(1); });
