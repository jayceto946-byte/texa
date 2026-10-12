# Texa QA Inventory

**本轮执行更新**：A4 已修复并通过故障/重试回归；浏览器22项与实际Electron11项离线闭环通过。全路由视觉初筛与首批 Astra 共同问题整改已完成，完整范围和未验收项见 [P0/P1 执行记录](P0-P1-EXECUTION-2026-10-11.md)。下文首轮统计保留历史范围。

2026-10-11 · code baseline branch `codex/mobile-s2-a2` · offline audit, no real learning data or paid model calls.

## Status semantics and evidence

后续执行优先级见 [P0/P1 整改策略](QA-REMEDIATION-STRATEGY.md)，精选视觉素材见 [Visual Review Board](VISUAL-REVIEW-BOARD.md)。历史 rendering PASS 保留其快照范围；新一轮全页面审美验收需要 Sol 初筛、Astra 关键设计决策及抽查，不能仅凭历史截图/像素比较关闭。真实 Tailscale 设备与正式安装包生命周期延后。

PASS=executed at named layer; FAIL=confirmed defect; FIXED=repair+regression; BLOCKED=environment/external dependency; NOT_TESTED=unexecuted. Static discovery never means PASS. Baseline tests passing does not validate probabilistic model correctness. See [issues](QA-ISSUES.md), [progress](QA-PROGRESS.md), [API index](API-ENDPOINTS.md) (205 handlers, AST evidence includes hidden/legacy routes), [frontend inventory](frontend-inventory.md), [runtime](runtime-data-audit.md), [assets](assets-workflows-audit.md), [platform](platform-audit.md).

## Actual page inventory and user→data chains

18 rendered route patterns, `/settings` modal redirect, `/kg` and `/mistakes/review` aliases. Direct old queries also reachable. Page matrix exercises19 URLs (including settings redirect), four viewports1280×820,1024×768,760×820,390×844. Every final screenshot must be read; initial invalid harness attempts excluded. Browser matrix checks rendering with Fixture, not business persistence. Detailed tab/menu/action list in frontend-inventory.md.

|Page entry|Frontend interaction/state→API→backend/store→result/UI|Normal / edge / failure cases|
|---|---|---|
|`/`|ChatProvider creates/loads session→chat conversations + stream→Resolver/ContextPack/Planner/tool/EvidencePack/generate→LearningTask & append-only conversation/execution events→SSE deltas, cited answer/checkpoint|new/existing session, history cursors, image/figure attachments, current scope, late event fence, stop/resume, disconnect, unknown input, model error, no evidence, source inspector|
|`/goals`|proposal/filter/select/detail/run/pause/schedule→goals API→GoalService/ExecutionService/Runtime→goal SQLite, task/run/events & receipts→contract, required inputs, progress|summarize failure/manual contract, user confirmed start, multiple tabs, revision conflict, pause while executing, local scheduling/restart, approval|
|`/notes`|saved/draft/archived/filter/menu/undo→notes list/filter/status→SessionNoteService/Store→session_notes.db revisions/receipts→list/pagination/error|empty/missing filters, rapid search/tab, archive/undo duplicate, list failure versus empty, deleted source|
|`/notes/:noteId`|read/expand/history/edit/archive→notes detail/revisions/createDraft→immutable revision + CAS→reader/draft|long math, historicalreadonly, archived edit disabled, stale revision, unknown origins, source missing|
|`/notes/drafts/:draftId`|prepare/poll/cancel/retry/manual/edit/autosave/save→notes/jobs→frozen same-transaction conversation sources + JobManager→draft/source/revision DB→preview/editor/saved note|editing during autosave, publish hash mismatch, cancel, restart no paid rerun, retained failed editor, crosspage/close fencing|
|`/mistakes`|query/filter/search/candidates/accept/dismiss→mistake lifecycle APIs→MistakeBook/LifecycleStore→SQLite records/source links/candidate receipts→typeset list/status|list auxiliary failure, stale revisions, candidate校对, duplicates, manual additions, archivedrestore, scope|
|`/mistakes/:id`|read/edit/archive/contentconfirm/mastered/redo→mistake CRUD/actions→CAS lifecycle+learning events→record/attempt/review DB→detail/actions|badid, incompletecondition, save failure, CAS conflict, repeat action, original image auth|
|`/mistakes/diagnosis`|scope→diagnosis API→scoped attempts/records→comparison facts→four sections|no tags/reasons, insufficient denominator, unknown legacy selfscores, failures/retry|
|`/mistakes/intake`|manual/image create/continue→draft APIs→lifecycle SQLite→saved draft→editor|nodrafts, list fail, repeatedstart, missing image, create error|
|`/mistakes/intake/:draftId`|load/edit/save/OCRconfirm/publish→draft/attachment/recognize/save→image store+draft CAS→mistakecandidate/record/receipt→revieweligible detail|early edit beforeload, incomplete input, simultaneous autosave/attachment, OCR failure, refresh, repeatsave, apprestart|
|`/exercises`|practice/browse/import/manual/dialog/PDFpagepicker→exercise overview/session/answers/importcandidate APIs→ExerciseBank/PracticeAnswerService/JobManager→practice SQLite/attempts/outbox→feedback/mistakecandidate|cancel parse, candidate manualcheck, submit twice, cancel/reveal/next, stale state, optional linkedwrite fail, import bounds|
|`/learning`|scope/due/recommended/expand/activity→kg summary + review sessions→learning projections/ConceptMemory/MistakeBook→aggregated facts→review queue and activity|auxfailure isolation, mixedscope, math summary, norecords, switchscope races, active review continuation|
|`/learning/review`|due list/start→review create→fixed ordered session→SQLite CAS→redo run|empty vsfailed list, repeatstart, readretry, scopechange|
|`/learning/review/:sessionId`|answerdraft/reveal/selfgrade/next→session PATCH/results→attempt evidence+SM2/state→SQLite session/results/receipts→next/completion|empty independent answer gate, twice submit, revisionconflict, return/refresh/restart, failureaftercommit|
|`/weekly`|load/stats/refresh→report weekly→learning_reports + asset stores + ConceptMemory→authoritative eventcursor & scopedrecords→facts/suggestions|>40messages, SQLiteonly history, daybounds, parent/childscope, errors, stale refresh, rawmath|
|`/books`|subjecttree/activearchived/roles/menu/reprepare→systemsubjects/books lifecycle/chapter APIs→book registry/CanonicalIR/staged release→book lifecycle/index manifest→readiness and list|noindex, partialcollection, archive duringjob, delete guard, duplicate names, longtitles, rolereorder|
|`/books/import`|PDF/MinerUoutput pick/options/start/cancel/job→import/job API→source adapter→CanonicalIR/report→staged Chroma/lexical/manifest→progress/review/result|invalidzip/pdf, filesize, missingbody, OCRwarnings, cancellation, failedquality retainsactive, restartjob|
|`/highlights`|book/chapter/section URL→chapter-highlights/assets→generated persisted markdown/meta→TOC/typesetreader/print|missingparams, notgenerated, longmath, HTMLauthfailure, noautomatic regeneration|
|`/settings`modal|tabs/preferences/profiles/backup/diagnostics/remote→system/backups/assets APIs+ElectronIPC→role registry/envprofiles/backup manifests/userprefs→connection/status/dialog|split/native, missingkey, error redaction, rejectunsavedclose, provider timeout, backuprestore deferred, tokenexpired|

## Global and non-page execution surfaces

|Module|Chain / storage / boundaries|Executed evidence|Outstanding acceptance|
|---|---|---|---|
|Onboarding|remote gate or local3step modelprofile→settingspersist→credentialfree setupmarker→workspace|frontend startup/storage/gate tests PASS|complete model-save browserjourney NOT_TESTED; real credential/model BLOCKED|
|APIsecurity/uploads/assets|token/capture scope/origin/bodylimits/asset containment→middleware/services→authenticated assets|backendfull security/mobile/upload/asset tests PASS|actualremote HTTPS/401 reconnect browser NOT_TESTED|
|Modelregistry/roles/prompt|explicit profile/env/defaults→registry/clientfactory→thinkingfilter→answer|backendfull configuration/prompt/capability deterministic tests PASS|realprovider failure/accuracy/fee/dataexit eval BLOCKED|
|Request/Runtime/policy/tools|contract/inputgate/policy/router→budgeted whitelist tool→verification→checkpoint/receipt/outbox|runtime-data baseline119 andfix55 PASS; fullsuite1532 PASS|longrunning realprovider and exhaustive interleavings NOT_TESTED|
|Context/retrieval/citations|bounded Ledger/context→same-scope hybridrecall→FinalEvidencePack→required-output verification|fullsuite Resolver/context/retrieval offline contracts PASS|real current index golden set/semantic answers BLOCKED; frozen benchmark unchanged|
|Images/visual learning|camera/file/figurecatalog/crop→visualassets/CanonicalIR/provenance→rolebridge→samechat Runtime|fullsuite figure/visual/mistakeimage tests PASS|camera realdevice/OCR correctness/missingpage human golden BLOCKED|
|Controlled write confirmation|pending action→userdecision→whitelist/write service→idempotentreceipt→learningassets|fullsuite approval/write/outbox tests PASS|every browser dialog/confirmation NOT_TESTED|
|Sessionmanagement|pin/archive/trash/restore→runfence/metadataCAS/receipt→conversationSQLite→paginatedcatalog|fullsuite conversationmanagement/history tests PASS|multiclientDesktop↔Mobile browser interaction NOT_TESTED|
|Backups/migrations|backup/check/prepare restore→manifest/integrity/pending restore→nextstart→independentstores|fullsuite backup/migration/crash tests PASS|packaged liveupgrade/restore BLOCKED; never tested on userdata|
|ConceptMemory/learningstate|exposures/attempts/userconfirmed review→events/reducer/projection→SM2 reminders|fullsuite learning-state/concurrency/memory tests PASS|learningprogress validity realuserdata NOT_TESTED|
|Legacy reachablelogic|direct /chat/ask, /exercises/practice/to-mistake, oldkg/review/query routes|APIappendix + legacypractice4 tests PASS (partial containment)|directpractice durable requestid/receipt FAIL; standalone KnowledgeGraphPage unmounted excluded|
|Desktop|singleinstance→token/identity/backendlifecycle→preloadIPC/windowstate/update/closefence→local workspace|desktop15/15 + syntax PASS|actual macOS Electronfixture startup/navigation/exit3checks PASS; Windows/package/autoupdate BLOCKED|
|Remote/mobile|HTTPS sameorigin token→backendremote-ready→readonlycache/compressedassets/recovernetwork→sameSQLite|fullsuite S0/S1/remote reads + frontend tests PASS|realAndroid/Tailscale Direct↔DERP/weaknetwork/background BLOCKED Requires Real Device|
|PWA|No manifest/service worker in actual code|static capability absence confirmed|offlineinstall/push NOT_TESTED (not implemented); don't classify as workingPWA|
|Performance/resources|lazyfeatures/deadlines/cache/concurrency/pagedhistory|build/lint/test baselines PASS; large mathchunks recorded|heap/leaks/longsession/largeimport TTFT benchmark NOT_TESTED; no unjustified optimization|

## Mandatory per-chain scenario matrix

Apply to each chain above; statuses are layer-specific in evidence, no aggregate PASS substitutes for missing checks:
1. normal execution and authoritative stored result;
2. invalid/empty/missingrequired input;
3. repeatedsameaction/idempotency receipt;
4. cancellation before/after transition;
5. failure before/after durablewrite;
6. page refresh/deeplink;
7. application/backend restart;
8. concurrent/interleavedclients and staleCAS;
9. recovery and lateevent fencing;
10. persisted UI/API/runtime identity consistency.

Existing deterministic tests cover many1–5/7–10 scenarios with temporary DBs; browser coverage must be tracked separately. Full UIstate coverage for every dialog and each scenario remainsNOT_TESTED until a named run exists. Read-only AST inventory of services/storage operations is in api-inventory.json; SQLschema/integrity is proven only on isolated test artifacts, not on user databases.

## Test layers and repeatability

- `venv310/bin/python scripts/qa-check.py smoke`: fast core persisted contracts; no models, isolated directories/credentials.
- `... qa-check.py backend|frontend|desktop|build|all`: broader tier; logs evidence/latest/<layer>; desktop loopback requires execution permission.
- bundledNode + bundled `NODE_PATH` → `scripts/qa-pages.mjs <dist> <out>`: synthetic route/state/theme screenshots and interactions. Existing Playwright reused, no new dependency.
- `scripts/qa-live-server.py` + `scripts/qa-live-e2e.mjs`: real FastAPI/SQLite browser writejourneys; explicit testorigin and disposable root. Provider/network disabled.
- `scripts/qa-visual-compare.py baseline current output.json`: dimensions/missing/pixelratio; numerical match not aesthetic acceptance. Baseline promotion after actual image review only.

Themeidentity mineral/graphite/clay/notebook/codex is real; no invented dark theme. Dark media preference exercised against existing stored themes, not proof of a nonexistent dark palette.

## Final executed page coverage

[accepted-pages.json](evidence/accepted-pages.json) names each reviewed image and exact captured state.119 accepted route/state checks =76 normal captures (19URLs×4viewports),20 stored-theme captures,21 empty/loading/error captures (7routes×3states),2 retry-success captures. All119 were actually read by Sol or a scoped Sol subagent; obsolete Fixture failures remain archived but are superseded. Rendering PASS is scoped to the snapshot; interactive/persistence PASS is separately named below.

|Page group|Rendering status|Executed business/interaction status|
|---|---|---|
|All19 URLs listed above|PASS at four fixed viewports, synthetic API fixture|NOT_TESTED for all actions per route; see cases below|
|notes/draft/settings|PASS; notes empty/loading/error+retry, five settings tabs|PASS fixture filter expansion, draft tab→preview→block editor, error→retry; actual Electron notes→settings→Escape PASS; real note generation/publish browser NOT_TESTED|
|intake/draft/mistake|PASS normal and intake three states|PASS real API draft save→refresh→restore→publish; SQLite matched and backend restart verified at1280/390; realOCR BLOCKED|
|review-start/review|PASS normal/empty/loading/error/retry|PASS due read retry; real answer save→refresh→restore→reveal→selfgrade→complete→refresh, persisted results and one attempt per latest record verified at1280/390|
|exercises|PASS fixed manual entry/nowrap controls|PASS real empty input disabled→manual save→refresh→unique SQLite row, including populated bank at1280/390; import/model answer browser NOT_TESTED|
|learning/weekly/mistakes summaries|PASS typeset math and scoped header sizing|FIXED corresponding UI/report defects; report230-turn/scoped data regression PASS; all learning controls browser NOT_TESTED|
|goals/books/import/highlights/chat|PASS rendered fixture states listed in manifest|Deterministic backend contracts PASS; paid model execution/current production index E2E BLOCKED; every menu/import lifecycle browser NOT_TESTED|

15 cross-cutting modules plus19 entry chains are inventoried;205 API handlers are discovered statically, not205 endpoint E2E passes. No total test count is an all-system acceptance claim.

## 2026-10-12 复杂交互补验（覆盖旧NOT_TESTED中的指定子状态）

本批按用户选择补验笔记冲突恢复、习题候选导入、聊天附件与来源浮层；[详细记录](COMPLEX-INTERACTIONS-2026-10-12.md)、[VRB-02](VISUAL-REVIEW-BOARD.md)。笔记503/草稿CAS/正式CAS/复制与读取失败/已归档恢复；真实Word+答案及textPDF候选提取、合并/拆分/校对/对照/确认入库/回滚；图片裁剪/旋转/增强/附件替换取消/Escape；来源宽屏并排、窄屏模态与焦点/输入保留均通过。四宽52项、Electron13项；Astra3次14图，补标签与正文捕获时机后有限关闭。历史表和119渲染检查保留为历史，不代表新代码全部状态自动通过；动态导入进度、其他复杂浮层及真实模型/OCR仍单独验收。
