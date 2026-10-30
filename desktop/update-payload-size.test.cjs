const { test } = require('node:test');
const assert = require('node:assert/strict');
const { applicationPayloadBytes } = require('../scripts/verify-nsis-payload-size.cjs');

const fields = [
  'Path = Texa-Setup.exe', 'Type = Nsis', 'Physical Size = 270000000', '',
  'Path = $PLUGINSDIR\\texa-app.7z', 'Size = 260000000', 'Packed Size = 260000000', '',
  'Path = $PLUGINSDIR\\app-64.7z', 'Size = 260000000', '',
  'Path = Uninstall Texa.exe', 'Size = 160000', '',
];

test('application archives are found in Windows and Unix 7-Zip listings', () => {
  for (const newline of ['\n', '\r\n', '\r\r\n']) {
    assert.equal(applicationPayloadBytes(fields.join(newline)), 260000000);
  }
});

test('record boundaries follow Path fields even without empty lines', () => {
  const listing = fields.filter(Boolean).join('\r\n');
  assert.equal(applicationPayloadBytes(listing), 260000000);
});

test('unrelated archives and installer metadata do not become the payload', () => {
  assert.equal(applicationPayloadBytes('Path = Texa.exe\r\nPhysical Size = 999999999\r\nPath = unrelated.7z\r\nSize = 888888888'), 0);
});
