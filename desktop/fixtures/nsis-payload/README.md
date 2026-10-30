# NSIS payload listing fixtures

- `windows-run-40.txt`: verbatim header and six selected complete records from
  [Windows job 124067888622, run 41057257905](https://github.com/jayceto946-byte/texa/actions/runs/41057257905/job/124067888622).
  Only Actions timestamps and unselected file records were removed. The installer,
  archive, offset and tail are 260703061, 260072255, 207548 and 423258 bytes.
- `named-archive.txt`: header and application archive records from the actual
  production-hook NSIS fixture compiled on macOS with electron-builder's bundled
  NSIS/7-Zip toolsets. Only the temporary installer path is normalized. Both names
  reference one stored archive (the same Offset), so adding their sizes is wrong.
- `duplicate-7098ec0b.txt`: header and application archive records obtained with
  bundled 7-Zip 24.09 from the retained real Windows release for `7098ec0b`.
  The installer is 520725286 bytes; the two records have distinct offsets.

The original synthetic test assumed every tool exposed NSIS file entries. Windows
uses standalone 7za (the `(a)` banner), whereas the macOS toolset uses full 7zz
(`(z)`). The standalone build has no NSIS handler and finds the embedded 7z:
[7-Zip 24.09 build](https://github.com/ip7z/7zip/blob/24.09/CPP/7zip/Bundles/Alone/makefile).
[Physical Size calculation](https://github.com/ip7z/7zip/blob/24.09/CPP/7zip/Archive/7z/7zIn.cpp#L1593)
excludes the prefix and tail; neither is an application file Size.
