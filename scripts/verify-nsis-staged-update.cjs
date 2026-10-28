// Compile the production NSIS hook with tiny disposable payloads on macOS/Linux;
// on Windows CI, also exercise real staged replacement and candidate rejection.
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const run = promisify(execFile);
const { build, Platform, Arch } = require('../desktop/node_modules/electron-builder');
const { writeManifest } = require('../desktop/update-manifest.cjs');

async function main() {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'texa-nsis-stage-'));
  const results = [];
  const installers = {};
  for (const scenario of ['valid', 'incomplete']) {
    const app = path.join(root, scenario, 'app');
    await fs.mkdir(path.join(app, 'resources'), { recursive: true });
    await fs.writeFile(path.join(app, 'Texa Update Fixture.exe'), 'new fixture executable; never launch');
    await fs.writeFile(path.join(app, 'resources', 'fixture.txt'), 'candidate complete');
    await fs.writeFile(path.join(app, 'resources', 'movie.mp4'), 'new precompressed asset');
    const files = await build({
      projectDir: path.resolve(__dirname, '../desktop'),
      targets: Platform.WINDOWS.createTarget('nsis', Arch.x64), prepackaged: app,
      config: {
        extends: null, appId: 'local.texa.staged-update-fixture', productName: 'Texa Update Fixture',
        extraMetadata: { version: '1.0.1' },
        directories: { output: path.join(root, scenario, 'release') },
        afterPack: null, afterSign: null,
        artifactBuildStarted: async () => {
          await writeManifest(app);
          if (scenario === 'incomplete') await fs.unlink(path.join(app, 'resources', 'fixture.txt'));
        },
        publish: null,
        // The legacy macOS compiler is Intel-only. Use the bundled native
        // toolset for cross-compilation; Windows CI keeps production defaults.
        ...(process.platform === 'darwin' ? { toolsets: { nsis: '1.2.1' } } : {}),
        win: { target: ['nsis'], icon: path.resolve(__dirname, '../desktop/assets/texa-taskbar.ico'), signAndEditExecutable: false },
        nsis: { include: path.resolve(__dirname, '../desktop/installer-update.nsh'), oneClick: false,
          createDesktopShortcut: false, createStartMenuShortcut: false },
      },
      publish: 'never',
    });
    installers[scenario] = files.find(file => file.endsWith('.exe'));
    if (!installers[scenario]) throw Error('No compiled NSIS fixture');
    results.push({ scenario, compiled: true });
  }
  if (process.platform === 'win32') {
    if (process.env.GITHUB_ACTIONS !== 'true') throw Error('Native installation checks require disposable Windows CI');
    const installed = path.join(root, 'installed');
    await run(installers.valid, ['/S', '/currentuser', `/D=${installed}`], { timeout: 60000 });
    const executable = path.join(installed, 'Texa Update Fixture.exe');
    await fs.writeFile(executable, 'old executable');
    await fs.writeFile(path.join(installed, 'resources/movie.mp4'), 'old precompressed asset');
    await fs.writeFile(path.join(installed, 'obsolete.txt'), 'old dependency');
    let rejected = false;
    try { await run(installers.incomplete, ['/S', '--updated', '/currentuser', `/D=${installed}`], { timeout: 60000 }); }
    catch (error) { if (error.code !== 1603) throw error; rejected = true; }
    if (!rejected || await fs.readFile(executable, 'utf8') !== 'old executable') throw Error('Incomplete candidate did not preserve the old program');
    if (await fs.readFile(path.join(installed, 'resources/movie.mp4'), 'utf8') !== 'old precompressed asset') throw Error('Preparing a candidate overwrote a live precompressed asset');
    const lockScript = path.join(root, 'hold-file.ps1');
    const locked = path.join(root, 'locked');
    const releaseLock = path.join(root, 'release-lock');
    await fs.writeFile(lockScript, 'param($Target,$Ready,$Release)\n$h=[IO.File]::Open($Target,"Open","Read","None")\ntry { Set-Content $Ready locked; while (-not (Test-Path $Release)) { Start-Sleep -Milliseconds 100 } } finally { $h.Dispose() }\n');
    const holding = run('pwsh.exe', ['-NoProfile', '-File', lockScript, executable, locked, releaseLock], { timeout: 90000 });
    holding.catch(() => {}); // Awaited in finally, including launch errors.
    // Observe a real file lock before asking the installer to replace it.
    try {
      const deadline = Date.now() + 15000;
      while (!await fs.stat(locked).then(() => true, () => false)) {
        if (Date.now() > deadline) throw Error('File lock witness timed out');
        await new Promise(resolve => setTimeout(resolve, 50));
      }
      let refusedBusyFiles = false;
      try { await run(installers.valid, ['/S', '--updated', '/currentuser', `/D=${installed}`], { timeout: 60000 }); }
      catch (error) { if (error.code !== 1603) throw error; refusedBusyFiles = true; }
      if (!refusedBusyFiles) throw Error('Installer did not refuse busy files');
    } finally {
      await fs.writeFile(releaseLock, 'release');
      await holding;
    }
    if (await fs.readFile(executable, 'utf8') !== 'old executable') throw Error('Busy installation was not preserved');
    // Force a real failure AFTER the directory swap by denying only SetValue
    // on this fixture's uninstall key. The exact original ACL is restored.
    const aclScript = path.join(root, 'metadata-access.ps1');
    const aclBackup = path.join(root, 'metadata-acl.txt');
    await fs.writeFile(aclScript, `param($Backup,$Restore)
$ErrorActionPreference='Stop'
$key='Registry::HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\9d623f84-9cb2-5fad-9974-6dcfbd9c6b6d'
$acl=Get-Acl $key
if ($Restore -eq 'restore') {
  $acl.SetSecurityDescriptorSddlForm((Get-Content $Backup -Raw).Trim())
} else {
  Set-Content $Backup $acl.Sddl
  $identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name
  $rule=New-Object Security.AccessControl.RegistryAccessRule($identity,'SetValue','Deny')
  $acl.AddAccessRule($rule)
}
Set-Acl $key $acl
`);
    // Keep the CI host's PowerShell edition and inherited module path aligned.
    await run('pwsh.exe', ['-NoProfile', '-File', aclScript, aclBackup, 'deny']);
    try {
      let rolledBack = false;
      try { await run(installers.valid, ['/S', '--updated', '/currentuser', `/D=${installed}`], { timeout: 60000 }); }
      catch (error) { if (error.code !== 1603) throw error; rolledBack = true; }
      if (!rolledBack || await fs.readFile(executable, 'utf8') !== 'old executable') throw Error('Post-swap failure did not restore the old program');
      const ini = await fs.readFile(path.join(process.env.LOCALAPPDATA, 'texa-desktop-updater', 'installer.exe.transaction.ini'));
      if (!ini.toString(ini[0] === 0xff ? 'utf16le' : 'utf8').includes('phase=rolled_back')) throw Error('Rollback did not record its actual transaction path');
    } finally {
      await run('pwsh.exe', ['-NoProfile', '-File', aclScript, aclBackup, 'restore']);
    }
    await run(installers.valid, ['/S', '--updated', '/currentuser', `/D=${installed}`], { timeout: 60000 });
    if (await fs.readFile(executable, 'utf8') !== 'new fixture executable; never launch') throw Error('Prepared candidate was not published');
    if (await fs.readFile(path.join(installed, 'resources/movie.mp4'), 'utf8') !== 'new precompressed asset') throw Error('Precompressed candidate asset missing');
    if (await fs.stat(path.join(installed, 'obsolete.txt')).then(() => true, () => false)) throw Error('Obsolete old dependencies survived replacement');
    results.push({ nativeReplacement: true, incompleteCandidatePreservesOld: true, busyInstallationPreserved: true,
      postSwapFailureRestoresOld: true, obsoleteFilesRemoved: true });
  }
  const report = { platform: process.platform, nativeWindows: process.platform === 'win32', results };
  const output = process.argv[2] || path.resolve('nsis-staged-update-verification.json');
  await fs.writeFile(output, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report));
}
main().catch(error => { console.error(error); process.exit(1); });
