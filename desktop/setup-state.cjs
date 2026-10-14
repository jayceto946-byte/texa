const fs = require('node:fs');
const path = require('node:path');

function readSetupComplete(filePath) {
  try {
    const value = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    return value.version === 3 && value.complete === true;
  } catch { return false; }
}

function writeSetupComplete(filePath) {
  try {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(`${filePath}.tmp`, JSON.stringify({ version: 3, complete: true }), 'utf8');
    fs.renameSync(`${filePath}.tmp`, filePath);
    return true;
  } catch { return false; }
}

module.exports = { readSetupComplete, writeSetupComplete };
