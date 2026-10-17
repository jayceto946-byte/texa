# R1/R2 production integration — 2026-10-16

Baseline: Texa_MacOS, 1824fcc7d7f33c7a08faef9cd285d566f5b3ac79. Existing uncommitted AppRail, LearningContextSidebar, OverflowMenu, conversations.css, ApprovedWorkspace.css, MainLayout, StudyDesk.css and patch_notes changes are user-owned; do not replace them.

| Design | Existing owner | Implementation |
|---|---|---|
| R1 preparation / one source at a time | ExercisesPage + practice hook | Local preparation and import CSS/components; preserve scope and filters |
| R1 index + one candidate, source comparison | candidate hook + candidateOperations | CandidateReviewWorkspace; preserve full candidate objects |
| Real count / batch receipt / unknown | batch-add response | Bind exact batch_id; no latest-batch inference or automatic write retry |
| R2 focused / 40:60 / <992 content width | ExerciseDetail, current practice, mistake detail | Local QuestionReadingLayout, persistent mounted panes |
| Answer job / explicit draft save | useExerciseAnswerJob | Preserve job identity; distinguish saved reference from draft; protect unsaved changes |
| Mistake explain writes directly | /mistakes/explain | No expected_revision or operation_id in current endpoint. Astra accepted keeping the AI tab and saved explanations while showing a short unavailable state; generation writes remain disconnected in this delivery. |

R2 overrides R1 only where explicit. Versioned design references remain in artifacts/design/exercises-validation and docs/design/exercises-visual-validation; not global visual authority. No UI skill rewrite planned.

Acceptance authority: Sol implements and verifies engineering; Astra independently inspects actual Electron screenshots. Statuses: IMPLEMENTED, ENGINEERING VERIFIED, DESIGN REVIEW PENDING, DESIGN APPROVED. Only Astra can grant the last status after blockers close. Review findings use implementation deviation / design defect / functional conflict / non-blocking improvement; each fix needs new screenshots and affected-area regression.

Delivery on 2026-10-17: IMPLEMENTED / ENGINEERING VERIFIED / DESIGN APPROVED. After usage became available, Astra directly inspected the final settled chat screenshots, closed E1 and independently approved this R1/R2 visual integration within the documented scope and three accepted capability exceptions. See the [delivery report](./delivery-report.md), [screenshot index](./screenshots.md), and [independent review](./astra-review-2026-10-17.md). This is not a real-model/OCR, Windows or packaged-release approval.
