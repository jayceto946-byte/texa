const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { applicationPayloadBytes, verifyPayloadListing } = require('../scripts/verify-nsis-payload-size.cjs');

const fixture = name => fs.readFileSync(path.join(__dirname, 'fixtures/nsis-payload', name), 'utf8');
const embedded = fixture('windows-run-40.txt');
const named = fixture('named-archive.txt');
const duplicate = fixture('duplicate-7098ec0b.txt');
const installerBytes = 260703061;

test('real Windows run #40 identifies the embedded application, excluding stub and tail', () => {
  for (const newline of ['\n', '\r\n', '\r\r\n']) {
    const listing = embedded.replace(/\r?\n/g, newline);
    assert.deepEqual(verifyPayloadListing(listing, installerBytes), {
      installerBytes, payloadBytes: 260072255, overheadBytes: 630806,
    });
  }
});

test('real named NSIS records support aliases, both separators and no blank lines', () => {
  const size = Number(named.match(/1 file, (\d+) bytes/)[1]);
  const payload = Number(named.match(/Path = .*app-64\.7z\r?\nSize = (\d+)/)[1]);
  for (const listing of [named, named.replace(/\//g, '\\'), named.replace(/\n+/g, '\r\n')]) {
    assert.equal(verifyPayloadListing(listing, size).payloadBytes, payload);
    assert.ok(payload < size);
  }
});

test('missing and invalid Physical Size never use the EXE size as a fallback', () => {
  for (const value of ['', '0', '-1', 'NaN', 'Infinity', '260072255oops', '2.6e8', '9007199254740992']) {
    assert.throws(() => verifyPayloadListing(embedded.replace('Physical Size = 260072255', `Physical Size = ${value}`), installerBytes), /Physical Size/);
  }
  assert.throws(() => verifyPayloadListing(embedded.replace(/^Physical Size = .*\n/m, ''), installerBytes), /Physical Size/);
});

test('embedded byte ranges must exactly account for the actual installer', () => {
  for (const [before, after] of [
    ['Offset = 207548', 'Offset = 0'],
    ['Offset = 207548', 'Offset = invalid'],
    ['Tail Size = 423258', 'Tail Size = -1'],
    ['Tail Size = 423258', 'Tail Size = 423259'],
    ['Physical Size = 260072255', 'Physical Size = 260703061'],
  ]) {
    assert.throws(() => verifyPayloadListing(embedded.replace(before, after), installerBytes));
  }
  assert.throws(() => verifyPayloadListing(embedded, installerBytes - 1), /byte range/);
});

test('real duplicated release payload and duplicates outside a directly opened archive are rejected', () => {
  assert.equal(applicationPayloadBytes(duplicate), 260068415);
  assert.throws(() => verifyPayloadListing(duplicate, 520725286), /excessive payload overhead/);
  // A second archive in either the prefix or tail is outside Physical Size.
  for (const field of ['Offset = 207548', 'Tail Size = 423258']) {
    const extra = 260072255;
    const expanded = embedded.replace(field, field.replace(/\d+$/, n => Number(n) + extra));
    assert.throws(() => verifyPayloadListing(expanded, installerBytes + extra), /excessive payload overhead/);
  }
});

test('unrecognized, unrelated and malformed archives block release', () => {
  for (const listing of [
    '',
    'Path = Texa.exe\nPhysical Size = 999999999\nPath = unrelated.7z\nSize = 888888888',
    embedded.replace('Type = 7z', 'Type = PE'),
    embedded.replace('Path = Texa.exe', 'Path = Other.exe'),
    embedded.replace('Path = resources\\app.asar', 'Path = unrelated.asar'),
    named.replace(/(?:app-64|texa-app)\.7z/g, 'unrelated.7z'),
    named.replace(/^(?:Packed )?Size = .*/gm, 'Size = invalid'),
  ]) {
    assert.throws(() => verifyPayloadListing(listing, installerBytes));
  }
  assert.throws(() => verifyPayloadListing(named, 1), /exceeds the installer size/);
});
