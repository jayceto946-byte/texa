# Mobile visual audit — 2026-10-11

## Evidence boundary

Applied `.agents/skills/texa-ui-system/SKILL.md` and its states reference. Reviewed actual rendered screenshots, not DOM labels alone. Capture environment is browser 390×844 with fixture backend; native iOS/Android, software keyboard, safe-area insets, screen reader, keyboard tab order and physical touch were NOT RUN. Following screenshot evidence, the lead authorized minimal error-state fixes in NotesPage and ReviewSessionPage only.

The first accepted populated capture manifest is `evidence/pages/results.json`, started **2026-10-11T08:00:42.217Z**. Earlier onboarding/fallback captures are excluded. The manifest records `bodyWidth=viewport=390` for all nineteen populated phone routes. This confirms document width only, not absence of internal overflow. The runner's attempted `编辑正文` click timed out and four unhandled fixture endpoints were recorded: `GET /api/system/settings/subjects`, `/api/exercises/answer/jobs/latest`, `/api/review/sessions`, `/api/books/import-capabilities`. Those failures cannot by themselves establish product defects.

Corrected state capture completed with manifest started **2026-10-11T08:03:53.092Z**; snapshot preserved as [mobile-reviewed-manifest.json](evidence/pages/mobile-reviewed-manifest.json). All 21 empty/loading/error captures were actually reviewed after lazy route mounting. This later runner's `逐块编辑` interaction timed out; four unhandled endpoints remain. Modal interaction acceptance is outside this phone audit.

## Explicitly reviewed populated files

All files below were viewed using actual image tools through contact sheets. Suspicious captures were also viewed full size.

- `390-chat.png`, `390-goals.png`, `390-notes.png`, `390-note.png`, `390-draft.png`, `390-mistakes.png`, `390-diagnosis.png`, `390-intake.png` — [sheet 1](evidence/pages/mobile-sheet-1.jpg).
- `390-intake-draft.png`, `390-mistake.png`, `390-exercises.png`, `390-learning.png`, `390-review-start.png`, `390-review.png`, `390-weekly.png`, `390-books.png` — [sheet 2](evidence/pages/mobile-sheet-2.jpg).
- `390-book-import.png`, `390-highlights.png`, `390-settings.png` — [last populated sheet](evidence/pages/mobile-populated-last.jpg).
- Full-size review: `390-mistakes.png`, `390-draft.png`, `390-review.png`, `390-learning.png`, `390-exercises.png`, `390-intake.png`, `390-diagnosis.png`, `390-settings.png`.

## Spatial composition, density and hierarchy

The populated phone pages retain comfortable 20–22 px side gutters. Notes, mistake detail, redo and highlights separate page identity, primary content and supporting metadata; most Chinese text wraps within the phone width. The note reader and redo page typeset the mathematical fixture clearly, with enough separation around the question. Long note titles use two lines naturally. Editing is denser but fields are full-width and vertically arranged; metadata disclosure keeps the article area readable.

The review page clearly states “先写下本次答案，再查看参考与反馈” above a large answer field and a prominent submission action. The exercise page's large empty lower area is consistent with the selected “练习” setup tab; a hidden question-bank tab must not be misreported as missing library data. Textbook import presents ordered source/file/parameters sections; the file choice is easily discoverable. Settings is a narrow two-column dialog: the navigation occupies roughly 140 px, leaving theme descriptions visibly ellipsized. Theme names, swatches and selection check remain legible, but detailed descriptions require another way to read them on a phone.

## Initial evidenced visual findings (before repair)

| Finding | Evidence | Severity / confidence | Recommended verification/fix direction |
|---|---|---|---|
| Raw mathematical source is displayed in compact learning assets | `390-learning.png` queue shows literal `$\\lim_{x\\to0}{x-\\sin x}/{x^3}$`; `390-intake.png` continued-draft title and `empty-weekly.png` recent-question card also show `$...$` and commands. Same question is typeset in `390-mistakes.png`/`390-review.png`. | P2; visually confirmed. This materially changes readability for formula-heavy assets. | Use the established bounded math renderer in these reading snippets; exercise long formulas, line wrapping and titles without side overflow. Do not render raw user HTML. |
| Page identity competes with scope/header controls | `390-mistakes.png`: “错题” splits into vertical two lines at left; `390-learning.png`: “复习计划” becomes two lines beside “目标与任务” and scope selector. | P3; visually confirmed, actions remain visible. | Reserve a stable title footprint; stack secondary controls or collapse scope caption at phone breakpoint. Verify 360/390/430 px and long subject/book names. |
| Small visual targets in primary and editing actions | `390-review.png` submission and `390-mistakes.png` actions have approximately 28 px visible button height; `390-draft.png` reorder/delete icons are small and closely grouped. | Accessibility/touch concern; screenshot alone does **not** prove actual clickable hit-box size or a standards failure. | Measure rendered hit boxes and spacing; verify reliable finger activation and focus, particularly reorder/delete. Increase mobile hit areas where needed without making desktop controls bulky. |
| Lazy-load recovery page lacks normal page hierarchy | `390-diagnosis.png` displays “页面文件未能加载，桌面更新后请刷新以读取当前版本。” plus refresh button; workspace icon visually crowds the message near top. | Capture observed; cause unconfirmed. Treat route acceptance as BLOCKED, not a diagnosed backend failure. | Reproduce with a supported fresh bundle; inspect chunk-load error. Verify the recovery message has its own margin and usable refresh action. |

Screenshots do not show horizontal document clipping in the reviewed captures, composer covering article content, or overlapping native windows. This limited visual observation is not mobile release approval.

## Initial empty, loading and error states (before repair)

Reviewed [empty sheet](evidence/pages/mobile-empty-sheet.jpg), [loading sheet](evidence/pages/mobile-loading-sheet.jpg), [error sheet](evidence/pages/mobile-error-sheet.jpg). Each contains seven captures, explicitly: `{empty,loading,error}-{goals,notes,mistakes,intake,review-start,weekly,book-import}.png`. Full-size follow-up: `error-notes.png`, `error-review-start.png`, `error-goals.png`, `error-mistakes.png`, `loading-intake.png`, `empty-weekly.png`.

| Route | Empty | Loading | Error/recovery |
|---|---|---|---|
| Goals | Clear “新建目标” form and disabled organize action while blank; no overflowing columns. | Clear “正在读取目标...” text. | Clear “目标暂时无法读取”, explanation and “重试读取”. Visual PASS. |
| Notes | Clear “还没有保存的笔记”, explanation to organize from conversation and “回到学习”. | Clear “正在读取笔记...”. | **P2 / FAIL state semantics:** 503 retry banner and confident empty-library claim coexist. Failure to read does not establish absence of notes. Keep retry/error visible and suppress the empty-state claim until a successful empty response. |
| Mistakes | Clear “还没有错题”, explanation and practice/intake alternatives; tabs remain navigable. | Inline spinner/text “正在更新档案...”; contextual controls remain. | Clear pink error box, title, retry; empty-state body is appropriately absent. Visual PASS. |
| Intake | No continued drafts; picture/manual actions remain clear. | Looks identical to no drafts: no draft-read loading text; local new-intake actions remain available. **Observation:** saved-draft availability is ambiguous, but no false numeric claim. | “草稿列表暂时无法读取，仍可新建草稿。” discloses limited failure and preserves local entry. No in-place retry visible. |
| Review start | “0道到期错题” and “查看错题档案” is appropriate after the fixture empty response. | “正在读取到期错题...”. | **P2 / FAIL state semantics:** confident “当前范围有0道到期错题” is shown alongside 503, and no retry control appears. Replace count with unavailable state until successfully loaded; offer retry independently of opening archive. |
| Weekly | **Harness gap:** `empty-weekly.png` is a populated report, not an empty report fixture. It cannot validate empty-state design. | Dedicated spinner card “正在整理学习周报”; refresh appears disabled. | Clear error title, text, “重新整理” and diagnostic disclosure. Visual PASS for captured failure. |
| Book import | A new file-selection form is valid without library items; no file uploaded in this audit. | “正在检查MinerU连接...” is visible lower in parameters; PDF choice stays available. | Explicit MinerU connection failure preserves local text extraction. The unhandled import-capabilities fixture means this does not prove real MinerU capability detection. |

Visual PASS above means inspected rendered state communication, not successful retry/submit behavior. No phone taps, virtual keyboard, draft scroll/footer save, long-text/table overflow interaction, focus traversal or native accessibility tree was verified. All forty accepted phone captures were reviewed; the rejected early-state images were not used for conclusions.

## Minimal state repair and verification

Before images preserved in [mobile-error-notes.png](evidence/ui-before/mobile-error-notes.png) and [mobile-error-review-start.png](evidence/ui-before/mobile-error-review-start.png). Root causes: NotesPage rendered the zero-item empty claim regardless of its read error; ReviewSessionStart used default/stale item count after failed reads and had no read retry path.

`frontend/src/pages/NotesPage.tsx` now suppresses the empty claim when no records are available and an error is present, while preserving populated lists for action errors. `frontend/src/pages/ReviewSessionPage.tsx` separates read errors from start-action errors, resets read loading/error/items on scope/retry, retains the active effect cleanup, offers a reload-key retry, and hides count/empty/start controls after read failure. Existing ReviewSessionRun was untouched. No shared CSS, note hook, API or storage contract changes.

[Build log](evidence/mobile-state-fix-build.log): TypeScript project check and Vite production build PASS, with existing large-chunk warning. [Relevant test log](evidence/mobile-state-fix-tests.log): four existing files, **10 tests PASS** (`reviewSession`, note rendering/navigation/autosave). These tests check adjacent contracts; they are not substitutes for verifying the new rendered failure/retry behavior.

## Final screenshot review — 08:13:31 capture

Manifest `evidence/pages-final/results.json` started **2026-10-11T08:13:31.291Z**, 117 checks, no reported runner errors; only unhandled fixture endpoints are `/api/system/backups` and `/api/system/network-diagnostics`. This phone audit actually viewed **all forty new images**, including fresh states, through five contact sheets and seven full-size follow-ups. No product files changed during this after review.

Explicit reviewed new files:

- [Final sheet 1](evidence/pages-final/mobile-final-sheet-1.jpg): `390-book-import.png`, `390-books.png`, `390-chat.png`, `390-diagnosis.png`, `390-draft.png`, `390-exercises.png`, `390-goals.png`, `390-highlights.png`.
- [Final sheet 2](evidence/pages-final/mobile-final-sheet-2.jpg): `390-intake-draft.png`, `390-intake.png`, `390-learning.png`, `390-mistake.png`, `390-mistakes.png`, `390-note.png`, `390-notes.png`, `390-review-start.png`.
- [Final sheet 3](evidence/pages-final/mobile-final-sheet-3.jpg): `390-review.png`, `390-settings.png`, `390-weekly.png`, `empty-book-import.png`, `empty-goals.png`, `empty-intake.png`, `empty-mistakes.png`, `empty-notes.png`.
- [Final sheet 4](evidence/pages-final/mobile-final-sheet-4.jpg): `empty-review-start.png`, `empty-weekly.png`, `loading-book-import.png`, `loading-goals.png`, `loading-intake.png`, `loading-mistakes.png`, `loading-notes.png`, `loading-review-start.png`.
- [Final sheet 5](evidence/pages-final/mobile-final-sheet-5.jpg): `loading-weekly.png`, `error-book-import.png`, `error-goals.png`, `error-intake.png`, `error-mistakes.png`, `error-notes.png`, `error-review-start.png`, `error-weekly.png`.
- Full-size follow-ups: final `error-notes.png`, `error-review-start.png`, `390-learning.png`, `390-chat.png`, `390-mistakes.png`, `390-intake.png`, `390-weekly.png`.

| Before/after item | Final observed conclusion |
|---|---|
| U3 Notes error/empty semantics | **Visual PASS:** [after notes error](evidence/pages-final/error-notes.png) retains the error/reload banner and no longer displays “还没有保存的笔记”. Normal populated notes, actual empty notes and loading notes remain legible. |
| U4 Review read error/0-count semantics | **Visual PASS:** [after review error](evidence/pages-final/error-review-start.png) shows error + “重试读取”, with no count, empty-link substitute or start button. Normal one-item review, successful zero-item state and loading message remain intact. Actual retry success is lead-owned E2E, not established by this still image. |
| Raw math in continued-draft/weekly snippets | **Visual PASS in captured routes:** final intake and weekly cards typeset the fixture formula. Learning queue verification remains blocked by the capture below, so not all original raw-math locations are certified. |
| Mistakes title wrap | **Visual PASS:** final mistakes header keeps “错题” on one line beside scope selector. Learning header cannot be accepted from current fallback image. |
| Diagnosis route | **Visual PASS:** diagnosis now renders its full sectioned cohort/failure/mastery description; initial fallback was resolved by fixture/run correction. |
| Populated chat | **Visual PASS for screenshot:** long Chinese explanation, section headings and displayed formulas render within width; composer is visible. End-of-content scroll, software keyboard and focus behavior remain NOT RUN. |
| Learning route | **BLOCKED capture:** final `390-learning.png` is the lazy-module failure/refresh fallback. Actual image inspection disagrees with a blanket “no runner errors means all routes render” conclusion. Lead notified to recapture/diagnose; cause is not established by this screenshot. |
| Touch/compact controls | Remaining concern: existing small visual action buttons and editing icons; physical targets/accessibility tree not measured. No new clipping/overlap introduced by the two error-state repairs in the reviewed captures. |

The final empty-weekly fixture remains a populated report; true no-data weekly design is still NOT RUN. Settings theme descriptions remain ellipsized in the narrow two-column dialog. Phone visual acceptance is partial pending a valid learning-route capture and actual interaction/native checks.

## Lead final supplement

Sol实际读取pages-supplement全部34图、pages-validated19图、pages-repeat39图；learning现在正常并在四视口/五主题呈现清晰公式和单行标题。empty-weekly现为无数据。Notes/review-start真实Fixture503→retry→success断言通过，读到恢复截图；U1/U2/U3/U4由FAIL改FIXED。新U5手动习题入口已修复并两视口真实持久化通过。最终接受图见accepted-pages.json，旧Fixture fallback不计成功。
