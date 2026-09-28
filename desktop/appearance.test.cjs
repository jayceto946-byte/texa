const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { readStartupAppearance, sanitizeStartupAppearance, writeStartupAppearance } = require('./appearance.cjs');

const tokens = {
  '--color-bg-primary': '#f4f2ef',
  '--color-bg-card': '#ffffff',
  '--color-text-primary': '#25272d',
  '--color-text-secondary': '#686b74',
  '--color-border': '#e0dfdb',
  '--color-accent': '#8a5142',
  '--color-accent-hover': '#713f34',
  '--accent-soft': 'rgba(138, 81, 66, 0.095)',
};

test('startup appearance caches the existing theme tokens without storing unrelated data', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'texa-appearance-'));
  try {
    const file = path.join(directory, 'startup-appearance.json');
    const selected = { id: 'clay', tokens: { ...tokens, '--extra': 'ignored' } };
    assert.deepEqual(writeStartupAppearance(file, selected), { id: 'clay', tokens });
    assert.deepEqual(readStartupAppearance(file), { id: 'clay', tokens });
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test('startup appearance rejects invalid theme IDs and unsafe or incomplete colors', () => {
  assert.equal(sanitizeStartupAppearance({ id: '../unknown', tokens }), null);
  assert.equal(sanitizeStartupAppearance({ id: 'clay', tokens: { ...tokens, '--color-accent': 'url(https://example.com)' } }), null);
  assert.equal(sanitizeStartupAppearance({ id: 'clay', tokens: { ...tokens, '--color-accent': undefined } }), null);
});

test('startup window controls are exposed for Windows and hidden by default on macOS', () => {
  const html = fs.readFileSync(path.join(__dirname, 'loading.html'), 'utf8');
  assert.match(html, /\.loading-window-controls\s*\{[^}]*display:\s*none/s);
  assert.match(html, /html\[data-platform="win32"\] \.loading-window-controls,[\s\S]*?display:\s*flex/);
  assert.match(html, /document\.documentElement\.dataset\.platform = startupDesktop\?\.platform/);
});
