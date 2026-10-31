const { gt } = require('semver');
const { validCommitUpdate } = require('./commit-channel.cjs');
const { updateErrorMessage } = require('./update-errors.cjs');

async function refreshDownloadedUpdate({ updater, downloaded, branch, emit }) {
  let replacing = false;
  try {
    emit({ status: 'checking', message: '正在确认最新版本…', progress: null });
    const result = await updater.checkForUpdates();
    const latest = result?.updateInfo;
    if (!latest || (branch && !validCommitUpdate(latest, branch))) throw new Error('未取得有效的最新更新信息。');
    if (latest.version !== downloaded.version && !gt(latest.version, downloaded.version)) {
      throw new Error('更新源返回了更旧的版本，请稍后重试。');
    }
    if (gt(latest.version, downloaded.version)) {
      replacing = true;
      emit({ status: 'downloading', message: '发现更新版本，正在下载最新安装包…', updateInfo: latest, progress: null });
      await updater.downloadUpdate();
    }
    emit({ status: 'downloaded', message: '最新版本已就绪，准备重启安装', updateInfo: latest, progress: null });
    return true;
  } catch (error) {
    emit({ status: replacing ? 'available' : 'downloaded', message: `未能准备最新版本：${updateErrorMessage(error)}`, progress: null,
      ...(replacing ? {} : { updateInfo: downloaded }) });
    return false;
  }
}

module.exports = { refreshDownloadedUpdate };
