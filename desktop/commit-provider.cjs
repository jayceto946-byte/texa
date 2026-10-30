const { GitHubProvider } = require('electron-updater/out/providers/GitHubProvider');
const { parseUpdateInfo } = require('electron-updater/out/providers/Provider');
const { valid, rcompare } = require('semver');
const { validCommitUpdate } = require('./commit-channel.cjs');

// GitHub's default provider takes the first matching Atom entry. A delayed
// publication of an old build must not hide a newer, already published build.
class CommitProvider extends GitHubProvider {
  async getLatestVersion() {
    const releases = [];
    for (let page = 1; ; page++) {
      const url = new URL(this.computeGithubBasePath(`/repos/${this.options.owner}/${this.options.repo}/releases`), this.baseApiUrl);
      url.search = `per_page=100&page=${page}`;
      const batch = JSON.parse(await this.httpRequest(url, { Accept: 'application/vnd.github+json', 'Cache-Control': 'no-cache' }));
      releases.push(...batch);
      if (batch.length < 100) break;
    }
    const channelFile = `${this.channel}.yml`;
    const release = releases.filter(item => !item.draft && valid(item.tag_name)
      && /-commit\.\d+\.[a-fg0-9]+$/.test(item.tag_name)
      && item.assets.some(asset => asset.name === channelFile)
      && item.assets.some(asset => asset.name.endsWith('.exe')))
      .sort((a, b) => rcompare(a.tag_name, b.tag_name))[0];
    if (!release) throw new Error('尚无已发布的 Windows 更新安装包。');
    const url = new URL(this.getBaseDownloadPath(release.tag_name, channelFile), this.baseUrl);
    const info = parseUpdateInfo(await this.httpRequest(url, { 'Cache-Control': 'no-cache' }), channelFile, url);
    if (!validCommitUpdate(info, this.options.sourceBranch) || valid(release.tag_name) !== info.version) {
      throw new Error('更新清单与发布版本或源码分支不一致。');
    }
    return { ...info, tag: release.tag_name, releaseName: info.releaseName || release.name, releaseNotes: info.releaseNotes || release.body };
  }
}

module.exports = { CommitProvider };
