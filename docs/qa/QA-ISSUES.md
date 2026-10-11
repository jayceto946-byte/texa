# QA issues — 2026-10-11

Priority: P0=data loss/security catastrophe; P1=critical exposed boundary/core blocker; P2=incorrect behavior/recoverability; P3=visual/usability inconsistency. FIXED requires regression evidence. A containment is not a full fix.

|ID|Priority|Issue / common root|Status|Evidence / remediation|
|---|---|---|---|---|
|R1|P2|Stream close callback failure skips producer cleanup; state transition assumes fence cannot fail|FIXED|owned_stream.py cleanup finally preserves primary fence error; 10 new regressions /55 affected tests in runtime-fixed-pytest.log|
|R2|P1|Raw exceptions enter preflight SSE/generation checkpoints, disclose synthetic credentials/path|FIXED|chat.py reuses existing diagnostic redactor; tests assert SSE and persisted checkpoints omit synthetic secrets; arbitrary unknown token formats remain redaction limit|
|A1|P2|Weekly report ignores subject for mistakes/exercises/concepts|FIXED|subject hierarchy filter; tests/test_weekly_report_regressions.py; isolated scopes|
|A2|P2|Weekly report counts bounded JSON projection instead of append-only authority|FIXED|learning_reports.py uses cursor pages;230 user turns counted with JSON absent;36 DB integrity checks|
|A3|P3|Report advertises requested days but silently counts bounded31days|FIXED|effective days normalized once and returned; boundary tests|
|A4|P2|Legacy direct practice commits primary DB before secondary error; retry can duplicate practice|FAIL (contained)|exercises.py returns saved practice + unconfirmed linkage warning after secondary failure.4 tests include error after commit. No automatic retry/compensation. Lost response/manual duplicate retry still lacks operation identity. Astra structured decision documented in legacy-practice-partial-result.md|
|U1|P2|Reading summaries render raw LaTeX while detail pages typeset math|FIXED|review queue, related/recent questions, intake continued-draft titles; actual390/760/1280screenshots; reuse SimpleMarkdown|
|U2|P3|Compact headers compress titles into per-character wrapping|FIXED|390mistakes andlearning; scope control consumes title width; local sizing|
|U3|P2|Failed notes load simultaneously says no saved notes|FIXED|error-notes.png503 plus confident empty; suppress unconfirmed empty|
|U4|P2|Failed due-list load says0due and lacks retry|FIXED|error-review-start.png; reset load state/suppress count/add retry|
|U5|P2|Manual exercise entry only exists while bank empty; after first record users cannot add manually|FIXED|ExercisesPage.tsx header entry, local nowrap controls; real1280/390 validation→save→refresh, four viewport screenshots; before live-e2e/failure.png|
|G1|N/A|PWA label exceeds current implementation|NOT_TESTED (capability absent)|No manifest/service worker found. Remote browser responsive access exists. Offline install behavior not implemented, don't test fictional feature|
|G2|N/A|All small controls touch/focus and long-session resources|NOT_TESTED|Some compact controls visuallysmall; measure hitboxes/task context before changes; real device acceptance pending|

Fixture errors excluded from product defects: initial setup flag absent; screenshots taken before lazy load; diagnosis fixture missing required fields; draft defaults to editing so action name differs; test Origin rejected correctly by API guard. Evidence is retained, but these attempts do not count as page PASS.

Final acceptance: U1/U2 verified in pages-repeat learning/exercises at all four widths; intake/mistakes and weekly in final/supplement. U3/U4 actual error→retry→success assertions and screenshots in pages-repeat. The earlier eight learning fallback captures in pages-final are invalid Fixture evidence, replaced in accepted-pages.json. Confirmed defects: P0=0, P1=1, P2=8, P3=2;10 FIXED,1 FAIL contained. Capability gaps G1/G2 are not counted as confirmed defects.
