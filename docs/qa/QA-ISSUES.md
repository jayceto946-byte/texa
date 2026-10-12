# QA issues — 2026-10-11

Priority: P0=data loss/security catastrophe; P1=critical exposed boundary/core blocker; P2=incorrect behavior/recoverability; P3=visual/usability inconsistency. FIXED requires regression evidence. A containment is not a full fix.

后续执行优先级另见 [整改策略](QA-REMEDIATION-STRATEGY.md)：A4 与核心闭环 E2E 优先作为 P0 工作，全部页面视觉/交互作为 P1 工作；不改写下表历史缺陷严重度或状态。

|ID|Priority|Issue / common root|Status|Evidence / remediation|
|---|---|---|---|---|
|R1|P2|Stream close callback failure skips producer cleanup; state transition assumes fence cannot fail|FIXED|owned_stream.py cleanup finally preserves primary fence error; 10 new regressions /55 affected tests in runtime-fixed-pytest.log|
|R2|P1|Raw exceptions enter preflight SSE/generation checkpoints, disclose synthetic credentials/path|FIXED|chat.py reuses existing diagnostic redactor; tests assert SSE and persisted checkpoints omit synthetic secrets; arbitrary unknown token formats remain redaction limit|
|A1|P2|Weekly report ignores subject for mistakes/exercises/concepts|FIXED|subject hierarchy filter; tests/test_weekly_report_regressions.py; isolated scopes|
|A2|P2|Weekly report counts bounded JSON projection instead of append-only authority|FIXED|learning_reports.py uses cursor pages;230 user turns counted with JSON absent;36 DB integrity checks|
|A3|P3|Report advertises requested days but silently counts bounded31days|FIXED|effective days normalized once and returned; boundary tests|
|A4|P2|Legacy direct practice commits primary DB before secondary error; retry can duplicate practice|FIXED|operation_id + atomic primary receipt + stable secondary/event keys + frozen request/source + explicit partial recovery;12 SQLite regressions; real lost response→reload→recover count1; see P0-P1-EXECUTION-2026-10-11.md. Historical contained finding retained in legacy-practice-partial-result.md.|
|U1|P2|Reading summaries render raw LaTeX while detail pages typeset math|FIXED|review queue, related/recent questions, intake continued-draft titles; actual390/760/1280screenshots; reuse SimpleMarkdown|
|U2|P3|Compact headers compress titles into per-character wrapping|FIXED|390mistakes andlearning; scope control consumes title width; local sizing|
|U3|P2|Failed notes load simultaneously says no saved notes|FIXED|error-notes.png503 plus confident empty; suppress unconfirmed empty|
|U4|P2|Failed due-list load says0due and lacks retry|FIXED|error-review-start.png; reset load state/suppress count/add retry|
|U5|P2|Manual exercise entry only exists while bank empty; after first record users cannot add manually|FIXED|ExercisesPage.tsx header entry, local nowrap controls; real1280/390 validation→save→refresh, four viewport screenshots; before live-e2e/failure.png|
|G1|N/A|PWA label exceeds current implementation|NOT_TESTED (capability absent)|No manifest/service worker found. Remote browser responsive access exists. Offline install behavior not implemented, don't test fictional feature|
|G2|N/A|All small controls touch/focus and long-session resources|NOT_TESTED|Some compact controls visuallysmall; measure hitboxes/task context before changes; real device acceptance pending|

Fixture errors excluded from product defects: initial setup flag absent; screenshots taken before lazy load; diagnosis fixture missing required fields; draft defaults to editing so action name differs; test Origin rejected correctly by API guard. Evidence is retained, but these attempts do not count as page PASS.

Final acceptance: U1/U2 verified in pages-repeat learning/exercises at all four widths; intake/mistakes and weekly in final/supplement. U3/U4 actual error→retry→success assertions and screenshots in pages-repeat. The earlier eight learning fallback captures in pages-final are invalid Fixture evidence, replaced in accepted-pages.json. Confirmed defects: P0=0, P1=1, P2=8, P3=2;10 FIXED,1 FAIL contained. Capability gaps G1/G2 are not counted as confirmed defects.

## 本轮新增共同问题 · 已整改

|ID|Priority|共同问题|结果/证据|
|---|---|---|---|
|U6|P3|长表单保存入口重复、行动区不一致，无图录入空列占宽|FIXED；共享 WorkspaceActionBar、无图单列、字段分组；Astra 原图抽查及保存 E2E|
|U7|P2|目标启用状态与任务运行状态含混|FIXED；目标已启用/暂停目标与Runtime独立；Astra样本及Goal暂停栅栏E2E|
|U8|P3|步骤父标题弱于参数子标题|FIXED；PDF/zip18px/16px；Astra源码核对+最末端原图|
|U9|P2|390设置侧栏挤压正文；Sol只按无溢出误判|FIXED；共享单栏导航/详情，原图复查与字段/焦点/键盘验证|
|U10|P2|教材真实Job支持取消，但导入页面没有入口|FIXED；明确 cancelling/cancelled，实际取消确认与失败重试E2E|

首轮表末计数属于历史快照；本轮关闭A4并新增上述5项，不能把历史119渲染检查升级为全部子状态审美通过。

## 2026-10-12 · 指定复杂交互域

|ID|Priority|共同问题|结果/证据|
|---|---|---|---|
|U11|P1|正式笔记冲突无正确最新版本编辑恢复，草稿保存与正式提交含混|FIXED；区分失败种类、禁用旧正式保存、先复制后新建最新revision编辑草稿、已归档只阅读、失败保留；浏览器/Electron真实CAS|
|U12|P2|图片裁剪Escape不取消；替换取消会丢旧附件；同文件无法再次选择|FIXED；复用Dialog焦点/inert，保留旧附件到应用、重置文件input；实际取消/返回焦点验证|
|U13|P2|候选准备/确认主动作竞争、窄屏校对空间不足，填写后字段用途不明|FIXED；分阶段保留状态、页底唯一导入、八类可见label；真实提取/校对/入库回滚与Astra抽查|
|U14|P2|窄屏来源覆盖正文后仍可操作背景，关闭焦点缺乏合同|FIXED；窄屏Dialog与宽屏并排分工，Tab/inert/Escape/触发焦点/输入保留验证|

[复杂交互验收](COMPLEX-INTERACTIONS-2026-10-12.md)。原加载中阅读截图为证据时机缺口，已等待目标正文后重拍，不作为额外产品故障。关闭本批不等于所有P1或S3清关。
