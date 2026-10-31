const { GitHubProvider } = require('electron-updater/out/providers/GitHubProvider');
const { parseUpdateInfo } = require('electron-updater/out/providers/Provider');
const { valid, rcompare } = require('semver');
const { validCommitUpdate } = require('./commit-channel.cjs');
const { parseXml } = require('builder-util-runtime');

const isCommitTag = tag => valid(tag) && /-commit\.\d+\.[a-fg0-9]+$/.test(tag);

// GitHub's default provider takes the first matching Atom entry. A delayed
// publication of an old build must not hide a newer, already published build.
class CommitProvider extends GitHubProvider {
  async apiReleases() {
    const releases = [];
    for (let page = 1; ; page++) {
      const url = new URL(this.computeGithubBasePath(`/repos/${this.options.owner}/${this.options.repo}/releases`), this.baseApiUrl);
      url.search = `per_page=100&page=${page}`;
      const batch = JSON.parse(await this.httpRequest(url, { Accept: 'application/vnd.github+json', 'Cache-Control': 'no-cache' }));
      releases.push(...batch);
      if (batch.length < 100) break;
    }
    return releases;
  }

  async feedReleases() {
    const url = new URL(`${this.basePath}.atom`, this.baseUrl);
    const feed = parseXml(await this.httpRequest(url, { Accept: 'application/atom+xml', 'Cache-Control': 'no-cache' }));
    return feed.getElements('entry').map(entry => ({
      tag_name: /\/tag\/([^/]+)$/.exec(entry.element('link').attribute('href'))?.[1],
      name: entry.elementValueOrEmpty('title'), body: '',
    })).filter(item => isCommitTag(item.tag_name));
  }

  async getLatestVersion() {
    const channelFile = `${this.channel}.yml`;
    const extension = this.runtimeOptions.platform === 'darwin' ? '.zip' : '.exe';
    let releases, fromFeed = false;
    try {
      releases = await this.apiReleases();
    } catch (error) {
      if (![403, 429].includes(error.statusCode)) throw error;
      // The public Atom endpoint is also used by electron-updater itself and
      // does not consume the anonymous REST API quota. Never require a PAT.
      releases = await this.feedReleases();
      fromFeed = true;
    }
    const candidates = releases.filter(item => !item.draft && isCommitTag(item.tag_name)
      && (fromFeed || (item.assets.some(asset => asset.name === channelFile)
        && item.assets.some(asset => asset.name.endsWith(extension)))))
      .sort((a, b) => rcompare(a.tag_name, b.tag_name));
    for (const release of candidates) {
      const url = new URL(this.getBaseDownloadPath(release.tag_name, channelFile), this.baseUrl);
      let raw;
      try {
        raw = await this.httpRequest(url, { 'Cache-Control': 'no-cache' });
      } catch (error) {
        if (fromFeed && error.statusCode === 404) continue;
        throw error;
      }
      const info = parseUpdateInfo(raw, channelFile, url);
      if (!validCommitUpdate(info, this.options.sourceBranch) || valid(release.tag_name) !== info.version) {
        throw new Error('更新清单与发布版本或源码分支不一致。');
      }
      if (!info.files?.some(file => file.url.toLowerCase().endsWith(extension))) throw new Error('更新清单缺少对应平台的安装包。');
      return { ...info, tag: release.tag_name, releaseName: info.releaseName || release.name, releaseNotes: info.releaseNotes || release.body };
    }
    throw new Error('尚无已发布的对应平台安装包。');
  }
}

module.exports = { CommitProvider };
