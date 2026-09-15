const net = require('node:net');
const path = require('node:path');

function resolveUserDataPath({ override = '', appDataPath, isPackaged }) {
  const explicit = String(override || '').trim();
  if (explicit) return path.resolve(explicit);
  const directoryName = isPackaged ? '考研智能辅助系统' : 'kaoyan-assistant-desktop';
  return path.join(appDataPath, directoryName);
}

function portFromUrl(value) {
  if (!value) return 0;
  try {
    const parsed = new URL(value);
    if (parsed.port) return Number(parsed.port);
    return parsed.protocol === 'https:' ? 443 : 80;
  } catch {
    return 0;
  }
}

function findAvailablePort(host = '127.0.0.1') {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once('error', reject);
    server.listen(0, host, () => {
      const address = server.address();
      const port = typeof address === 'object' && address ? address.port : 0;
      server.close((error) => {
        if (error) reject(error);
        else if (!port) reject(new Error('未能分配本地服务端口'));
        else resolve(port);
      });
    });
  });
}

module.exports = { findAvailablePort, portFromUrl, resolveUserDataPath };
