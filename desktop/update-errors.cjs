function updateErrorMessage(error) {
  const message = String(error?.message || error || '');
  if (error?.statusCode === 429 || /rate limit|x-ratelimit-remaining["'\s:]*0/i.test(message)) {
    return '更新服务请求额度暂时用完，请稍后重试。';
  }
  if (/ENOTFOUND|EAI_AGAIN|ETIMEDOUT|ECONN|ERR_NETWORK|ERR_INTERNET|ERR_PROXY|ERR_CONNECTION|net::/i.test(message)) {
    return '无法连接更新服务，请检查网络后重试。';
  }
  if (error?.statusCode === 403) return '更新服务暂时拒绝访问，请稍后重试。';
  // Keep application errors useful; HTTP diagnostics and response bodies stay
  // in the updater log instead of being rendered in the settings page.
  if (/[\u4e00-\u9fff]/.test(message) && message.length <= 120 && !/[\n{}]|https?:\/\//i.test(message)) return message;
  return '更新失败，请稍后重试。';
}

module.exports = { updateErrorMessage };
