// Native checks run only on the disposable Windows CI host. Reuse the staged
// installer's tiny payload; do not install Texa or access real learning data.
const fs = require('node:fs/promises');
const path = require('node:path');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const run = promisify(execFile);
const exists = file => fs.stat(file).then(() => true, () => false);
const quote = value => `'${value.replaceAll("'", "''")}'`;

async function verifyUserMigration({ root, installers, installed }) {
  if (process.platform !== 'win32' || process.env.GITHUB_ACTIONS !== 'true') throw Error('Migration checks require disposable Windows CI');
  const product = 'Texa Update Fixture';
  const executable = `${product}.exe`;
  const uninstaller = `Uninstall ${product}.exe`;
  const key = 'Software\\9d623f84-9cb2-5fad-9974-6dcfbd9c6b6d';
  const machine = path.join(root, 'machine installation');
  const user = path.join(process.env.LOCALAPPDATA, 'Programs', product);
  const data = path.join(process.env.APPDATA, product);
  const marker = path.join(data, 'migration-learning-data.txt');
  // NSIS /D= and _?= consume the unquoted remainder of the command line.
  // Node must not add quotes around these last arguments when paths have spaces.
  const nsis = (file, args) => run(file, args, { timeout: 60000, windowsVerbatimArguments: true });
  const ps = async source => (await run('pwsh.exe', ['-NoProfile', '-Command', source])).stdout.trim();
  const readLocation = hive => ps(`$v=Get-ItemProperty -LiteralPath ${quote(`${hive}:\\${key}`)} -Name InstallLocation -ErrorAction SilentlyContinue; if($v){$v.InstallLocation}; exit 0`);
  const uninstall = async (directory, mode) => {
    const copy = path.join(root, `cleanup-${mode}.exe`);
    await fs.copyFile(path.join(directory, uninstaller), copy);
    await nsis(copy, ['/S', '/KEEP_APP_DATA', `/${mode}`, '--updated', `_?=${directory}`]);
  };
  if (await exists(user) || await exists(data)) throw Error('Fixture user directories already exist; refusing to reuse them');
  // The earlier staged-replacement checks registered this user fixture.
  await uninstall(installed, 'currentuser');
  await fs.mkdir(data);
  await fs.writeFile(marker, 'fixture learning data must stay in the original user profile');
  let originalUninstaller;
  try {
    await nsis(installers.valid, ['/S', '/allusers', `/D=${machine}`]);
    await fs.writeFile(path.join(machine, executable), 'old machine application');
    let rejected = false;
    try { await nsis(installers.incomplete, ['/S', '--updated', '/allusers', `/D=${machine}`]); }
    catch (error) { if (error.code !== 1603) throw error; rejected = true; }
    if (!rejected || await fs.readFile(path.join(machine, executable), 'utf8') !== 'old machine application'
      || await exists(user) || await readLocation('HKCU')) throw Error('Incomplete migration did not leave the machine installation intact');

    // /D deliberately points at the old machine directory. It must not leak
    // through to the current-user destination.
    await nsis(installers.valid, ['/S', '--updated', '/allusers', `/D=${machine}`]);
    if (await readLocation('HKCU') !== user || await readLocation('HKLM') || await exists(path.join(machine, executable))) {
      throw Error('Migration did not switch registration and remove the old machine application');
    }
    const shortcut = await ps(`$p=Join-Path ([Environment]::GetFolderPath('Desktop')) '${product}.lnk'; (New-Object -ComObject WScript.Shell).CreateShortcut($p).TargetPath`);
    if (shortcut !== path.join(user, executable)) throw Error('User desktop shortcut does not point at the migrated application');
    if (await fs.readFile(marker, 'utf8') !== 'fixture learning data must stay in the original user profile') throw Error('Migration modified user learning data');
    const uninstallString = await ps(`(Get-ItemProperty -LiteralPath 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\9d623f84-9cb2-5fad-9974-6dcfbd9c6b6d').UninstallString`);
    if (!uninstallString.includes(user) || !uninstallString.endsWith('/currentuser')) throw Error('Migrated uninstaller has the wrong scope');

    await uninstall(user, 'currentuser');
    await nsis(installers.valid, ['/S', '/allusers', `/D=${machine}`]);
    originalUninstaller = await fs.readFile(path.join(machine, uninstaller));
    await fs.writeFile(path.join(machine, uninstaller), 'unavailable cleanup fixture; never execute');
    await nsis(installers.valid, ['/S', '--updated', '/allusers', `/D=${machine}`]);
    if (await readLocation('HKCU') !== user || await readLocation('HKLM') !== machine || !await exists(path.join(user, executable))) {
      throw Error('Cleanup failure did not preserve the usable user installation');
    }
    const pending = await ps(`(Get-ItemProperty -LiteralPath ${quote(`HKCU:\\${key}`)}).MigrationMachinePath`);
    if (pending !== machine) throw Error('Pending machine cleanup was not recorded');
    // With both registrations present, an ordinary later update must select
    // HKCU. It must not execute the deliberately broken machine uninstaller.
    await fs.writeFile(path.join(user, executable), 'old user application');
    await nsis(installers.valid, ['/S', '--updated']);
    if (await fs.readFile(path.join(user, executable), 'utf8') !== 'new fixture executable; never launch'
      || await readLocation('HKLM') !== machine) throw Error('Subsequent update did not stay in user scope');
    if (await fs.readFile(marker, 'utf8') !== 'fixture learning data must stay in the original user profile') throw Error('User update modified learning data');
    return { migrationPreservesData: true, userShortcutsRegistered: true, machineRegistrationRemoved: true,
      incompleteMigrationPreservesOld: true, cleanupFailureKeepsUserInstall: true, subsequentUpdateUsesUserScope: true,
      uacInteraction: 'not measured; runner already has administrative privileges' };
  } finally {
    if (originalUninstaller && await exists(machine)) await fs.writeFile(path.join(machine, uninstaller), originalUninstaller);
    if (await readLocation('HKLM') === machine) await uninstall(machine, 'allusers');
    if (await readLocation('HKCU') === user) await uninstall(user, 'currentuser');
    await fs.unlink(marker);
    await fs.rmdir(data);
  }
}

module.exports = { verifyUserMigration };
