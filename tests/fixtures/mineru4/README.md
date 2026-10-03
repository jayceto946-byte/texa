# MinerU 4 offline fixtures

`list_failures.json` contains 16 fixed retrieval fragments from the user-supplied
handoff, selected for the two list regressions (MAC protocol and NK-Humirel).
It retains source text, locations/IDs and section scope while omitting bulky
parent text and repeated source-location objects. It is not an OCR golden.
The tests pin the lexical header and run production reranking, support gate and
EvidencePack; synthetic fixtures separately isolate the two faults and negatives.

Source archive (optional full corpus, **not committed**):
`/Users/jichengqian/Downloads/texa-mineru-handoff.tar.gz`.
Archive SHA-256:
`09c6f3bbd9f442f72f6d7554575a476cca6eabab4f9d2134a1160a5b5f974b21`.
Original source member:
`outputs/CGQ/传感器原理及应用_middle_chunks.json`.
Source member SHA-256:
`1efda212e1d0c6a13227ee2ff3597d2087a3255dc12e0c124b3cbc6e7193c397`.
Fixture SHA-256:
`6fb5f4e28653ba1c9c1667f1cce0c7a1eccfc21208b8047122ef651a19ab5f45`.

`tests/test_mineru_structured_content.py` defines a small synthetic MinerU 4.0.8
payload following the supplied native shape. It generates tiny images in
`tmp_path`. It covers native-only formal import, source selection, numbered and
bounded unnumbered headings, local lists, formula aliases, Markdown/HTML tables,
blank header cells, captions, footnotes, normalized boxes and raw source indices.
`tests/test_document_assets.py` covers immutable crops, failures, path safety and
backup/restore. Production Chroma and learning data are never fixture targets.

For optional full-corpus validation, safely extract the checked archive into a
new directory (reject absolute/traversal paths and symlink members), point all
DATA_DIR/MINERU_OUTPUT_PATH/ENV_PATH paths at a new isolated directory, keep
embedding files local-only, and use the formal external importer on
`outputs/CGQ`. Do not rerun OCR or enable concept extraction / paid models.
See `docs/mineru-native-implementation-2026-10-03.md` for results and limits.
