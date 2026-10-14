const fs = require('node:fs');
const path = require('node:path');

const STARTUP_TOKENS = [
  '--color-bg-primary', '--color-bg-card', '--color-text-primary',
  '--color-text-secondary', '--color-border', '--color-accent',
  '--color-accent-hover', '--accent-soft',
];
const COLOR_VALUE = /^(?:#[0-9a-f]{6}|rgba\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*(?:0|1|0?\.\d+)\s*\))$/i;

function sanitizeStartupAppearance(value) {
  if (!value || typeof value.id !== 'string' || !/^[a-z][a-z0-9_-]{0,31}$/.test(value.id) || !value.tokens || typeof value.tokens !== 'object') return null;
  const tokens = {};
  for (const name of STARTUP_TOKENS) {
    const color = value.tokens[name];
    if (typeof color !== 'string' || !COLOR_VALUE.test(color)) return null;
    tokens[name] = color;
  }
  return { id: value.id, tokens };
}

function readStartupAppearance(filePath) {
  try {
    return sanitizeStartupAppearance(JSON.parse(fs.readFileSync(filePath, 'utf8')));
  } catch {
    return null;
  }
}

function writeStartupAppearance(filePath, value) {
  const appearance = sanitizeStartupAppearance(value);
  if (!appearance) return null;
  try {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    const temporaryPath = `${filePath}.tmp`;
    fs.writeFileSync(temporaryPath, JSON.stringify(appearance), 'utf8');
    fs.renameSync(temporaryPath, filePath);
    return appearance;
  } catch {
    return null;
  }
}

module.exports = { sanitizeStartupAppearance, readStartupAppearance, writeStartupAppearance };
