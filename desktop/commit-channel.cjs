const { inc, valid } = require('semver');

function commitVersion(base, count, commit) {
  if (!valid(base) || !Number.isSafeInteger(count) || count < 1 || !/^[a-f0-9]{40}$/.test(commit)) throw new Error('Invalid commit build identity');
  return `${inc(base, 'patch')}-commit.${count}.${commit.slice(0, 8)}`;
}
function validCommitUpdate(info, branch) {
  return Boolean(info && /^[a-f0-9]{40}$/.test(info.sourceCommit || '') && info.sourceBranch === branch && valid(info.version) && new RegExp(`-commit\\.\\d+\\.${info.sourceCommit.slice(0, 8)}$`).test(info.version));
}
module.exports = { commitVersion, validCommitUpdate };
