const { inc, valid } = require('semver');

function commitIdentifier(commit) {
  const prefix = commit.slice(0, 8);
  // SemVer rejects numeric prerelease identifiers with leading zeroes.
  return /^0\d{7}$/.test(prefix) ? `g${prefix}` : prefix;
}
function commitVersion(base, count, commit) {
  if (!valid(base) || !Number.isSafeInteger(count) || count < 1 || !/^[a-f0-9]{40}$/.test(commit)) throw new Error('Invalid commit build identity');
  return `${inc(base, 'patch')}-commit.${count}.${commitIdentifier(commit)}`;
}
function validCommitUpdate(info, branch) {
  return Boolean(info && /^[a-f0-9]{40}$/.test(info.sourceCommit || '') && info.sourceBranch === branch && valid(info.version) && new RegExp(`-commit\\.\\d+\\.${commitIdentifier(info.sourceCommit)}$`).test(info.version));
}
function configureCommitChannel(updater) {
  updater.channel = 'commit';
  updater.allowPrerelease = true;
  // electron-updater's channel setter enables downgrades as a side effect.
  updater.allowDowngrade = false;
}
module.exports = { commitVersion, validCommitUpdate, configureCommitChannel };
