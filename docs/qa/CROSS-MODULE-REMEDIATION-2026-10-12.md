# Texa 跨模块整改 · 2026-10-12

本轮以原有工作区及其checkpoint `c53e78b` 为基线；既有移动网络、候选校对、笔记冲突、图片裁剪及来源 Inspector 改动保留。26项按用户条目拆分登记，不能把源码修改等同于实际验收。UI/自动化运行使用隔离合成资料；正式错题库仅进行只读聚合诊断（0条）。另按用户明确授权发送4类合成题，尝试8次外部模型调用，全部鉴权失败。

本轮交付：**21项已修复、4项部分完成（01/07/18/21）、1项暂缓（16）**。真实模型Teaching Prompt比较未获有效答案；不得据此宣称教学效果提升。

基线构建 `/tmp/texa-cross-module-before`；原图位于 [before](evidence/cross-module/before)。浏览器素材使用现有 qa-pages 工具；合成状态不能证明真实模型质量。Astra集中设计已冻结，见设计规范。

|ID|问题|代码/组件|状态|根因与验证|
|---|---|---|---|---|
|01|Gate放行但待核验/未完整|[chat.py](/Users/jichengqian/Documents/ChatGPT/texa/backend/api/chat.py); [answer_verification.py](/Users/jichengqian/Documents/ChatGPT/texa/backend/services/answer_verification.py); [answerVerification.ts](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/utils/answerVerification.ts)|部分完成|确认Gate与答案核验不同；修复兜底核验只进task未进done事件的实际映射问题，39项回归通过；保留真实unverified；线上频率与教学质量因鉴权失败未验证|
|02|无实际意义的执行步骤|[chat.py](/Users/jichengqian/Documents/ChatGPT/texa/backend/api/chat.py); [ExecutionTrace.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/components/chat/ExecutionTrace.tsx); [chatActivities.ts](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/utils/chatActivities.ts)|已修复|稳定摘要+按需真实详情；过滤pending占位，完成不折叠；发现message_id换key重建，改稳定turn身份，Electron流式验收通过|
|03|选中文字添加到对话|[ChatMessage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/components/ChatMessage.tsx); [ChatPage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/ChatPage.tsx)|已修复|选区引用追加原输入，不自动发送；Electron保留原草稿通过|
|04|移除学科通用标签|[ChatMessage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/components/ChatMessage.tsx)|已修复|仅移除subject_general标签；模式与显式放宽动作保留|
|05|移除点赞点踩入口|[ChatMessage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/components/ChatMessage.tsx)|已修复|删除点赞点踩UI，历史数据/API保持兼容；Electron无入口|
|06|输入框高度自适应|[ChatPage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/ChatPage.tsx); [StudyDesk.css](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/layouts/StudyDesk.css)|已修复|响应input与窗口变化统一高度，修正StudyDesk128px覆盖；Electron长文增长/短文收缩通过|
|07|桌面拍照功能|[ChatPage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/ChatPage.tsx)|部分完成|桌面及精确指针浏览器隐藏HTML拍照入口，保留图片上传；移动粗指针保留capture入口（移动相机未实测）|
|08|错题展开LaTeX|[ChatPage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/ChatPage.tsx)|已修复|错题选择展开采用现有Markdown/KaTeX；Electron公式可见|
|09|错题展开外部关闭|[ChatPage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/ChatPage.tsx)|已修复|pointerdown外部关闭；不影响触发按钮和内部选择，Electron通过|
|10|错题展开Esc|[ChatPage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/ChatPage.tsx)|已修复|Esc关闭并返回触发焦点，Electron通过|
|11|P0连续继续执行|[GoalsPage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/GoalsPage.tsx); [execution.py](/Users/jichengqian/Documents/ChatGPT/texa/backend/services/goals/execution.py)|已修复|同步actionBusy准入 + 后端重复恢复返回同run；SQLite10项通过，Electron连续12次点击1次POST且同task新run|
|12|原始Runtime Event|[GoalsPage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/GoalsPage.tsx)|已修复|使用受控状态映射，原事件留在Runtime诊断；Electron展开确认无raw lifecycle|
|13|英文异常|[GoalsPage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/GoalsPage.tsx); [runtimePresentation.ts](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/features/goals/runtimePresentation.ts)|已修复|中文业务提示保留，英文异常映射；runtimePresentation回归|
|14|macOS全屏预留空间|[DesktopTitleBar.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/components/DesktopTitleBar.tsx); [main.cjs](/Users/jichengqian/Documents/ChatGPT/texa/desktop/main.cjs); [index.css](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/index.css)|已修复|Electron原生fullscreen IPC，Mac身份保留且取消留白；真实进出全屏通过|
|15|目标信息层级和控制|[GoalsPage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/GoalsPage.tsx)|已修复|完成条件默认可见、本次任务包含执行控制；Electron运行态截图已读|
|16|跨页目标入口/计时价值|未新增代码；复用现有导航|暂缓|Astra评估决定不新增计时器/全局任务中心，复用现有导航|
|17|目标/task/Session/定时关系|[GoalsPage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/GoalsPage.tsx)|已修复|保留同Runtime/task，跨页读取同task；定时说明本地后端运行|
|18|相似错题重复入队|[mistake_lifecycle.py](/Users/jichengqian/Documents/ChatGPT/texa/memory/mistake_lifecycle.py); [test_mistake_lifecycle.py](/Users/jichengqian/Documents/ChatGPT/texa/tests/test_mistake_lifecycle.py)|部分完成|33项回归含重复ID拒绝、相同题干不同来源保留；本机正式库0条，原现场未验证，未合并数据|
|19|复习文字对齐层级|[LearningPage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/LearningPage.tsx); [LearningPage.css](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/LearningPage.css)|已修复|合并今日/恢复入口、移除重复状态；Electron三种宽度截图检查通过|
|20|复习资产行动价值|[LearningPage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/LearningPage.tsx)|已修复|展开真实教材片段/近期问题，不自动写复习；明确记录1次POST，学习记录折叠；无新增指标系统|
|21|自动整理/自主记录区分|[DraftWorkspace.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/features/notes/DraftWorkspace.tsx); [NotesPage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/NotesPage.tsx)|部分完成|生成与手动/编辑模式明确；独立空白记录缺少来源合同，本轮暂不伪造来源或迁移|
|22|生成成功直接阅读|[DraftWorkspace.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/features/notes/DraftWorkspace.tsx); [NotePreflight.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/features/notes/NotePreflight.tsx); [jobs.py](/Users/jichengqian/Documents/ChatGPT/texa/backend/services/session_notes/jobs.py)|已修复|生成成功默认直接阅读，入口消除审阅要求；Electron真实发布/KaTeX/编辑/保存/刷新通过|
|23|自主编辑保存/恢复再编辑|[DraftWorkspace.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/features/notes/DraftWorkspace.tsx); [useNoteEditor.ts](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/features/notes/hooks/useNoteEditor.ts); 原有CAS恢复|已修复|保留已有编辑/自动保存/冲突恢复；47项后端通过，Electron生成转编辑保存刷新通过；Electron深层503、草稿/正式CAS409、归档与复制失败恢复通过|
|24|标准答案异步状态/重试|[useExerciseAnswerJob.ts](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/features/exercises/hooks/useExerciseAnswerJob.ts); [ExercisesPage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/ExercisesPage.tsx)|已修复|状态放在正文前；断连503可见并恢复轮询，首次失败/重试成功，8次点击1个任务，明确保存才写题库；Electron通过|
|25|答案解析长文公式|[ExercisesPage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/ExercisesPage.tsx)|已修复|答案/解析单列max800，渲染Markdown/KaTeX；24段答案与20段解析滚动到尾部及三尺寸通过|
|26|练习抽题布局/维护分离|[ExercisesPage.tsx](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/pages/ExercisesPage.tsx); [usePracticeSession.ts](/Users/jichengqian/Documents/ChatGPT/texa/frontend/src/features/exercises/hooks/usePracticeSession.ts); [exercises.py](/Users/jichengqian/Documents/ChatGPT/texa/backend/api/exercises.py); [schemas.py](/Users/jichengqian/Documents/ChatGPT/texa/backend/schemas.py); [exercise_bank.py](/Users/jichengqian/Documents/ChatGPT/texa/memory/exercise_bank.py)|已修复|范围/顺序明确，小题库默认2题；搜索真正传入抽题，空结果保留已有session；单题不覆盖暂停会话；维护为次要折叠入口，候选校对/导入/回滚复验通过|

## Checkpoint与验收记录

各模块完成后记录实际检查、Git身份及前后图；后续共享改动回归此前模块。Teaching Prompt比较须覆盖概念、推导、应用、追问纠错；无真实模型比较不得宣布教学效果提升。

目标模块阶段验收：后端10项、桌面15项通过；Electron 3类检查通过（目标重复恢复/聊天复验/macOS全屏），[结果](evidence/cross-module/goals-electron/results.json)。动态截图已直接读取；待输入、待确认的后端合同有回归覆盖，目标页这两种专属交互未做逐态Electron验收；不以运行态截图冒充全部状态。Astra规范：[集中设计](CROSS-MODULE-ASTRA-DESIGN-2026-10-12.md)。

问答checkpoint：后端55项、前端198项（新增状态映射检查）、类型/lint/build通过；Electron4类检查通过，目标/全屏同步回归。Prompt合成代表集已建立并按授权调用8次，全部AuthenticationError，无真实答案/质量结论。[脱敏结果](evidence/cross-module/teaching-comparison.json)。

复习checkpoint `662aa73`（问答追加 `e9b731d`）：后端33项、前端199项通过；Electron5类通过，[结果](evidence/cross-module/review-electron/results.json)。复习资料视觉使用合成summary，提交使用真实API/SQLite；1280/1024/760截图已读取检查。后端删除无独立执行的reason步骤，前端未收到阶段完成回执标为跳过；Electron确认未显示假推理或假检索完成。

笔记阶段：47项后端、类型/lint/build通过；Electron6类全部通过，[结果](evidence/cross-module/notes-electron/results.json)。生成输入为合成资料，冻结来源、JobManager、草稿发布、明确保存和刷新均走真实API/SQLite；不证明真实模型文章质量。

练习阶段：28项针对性后端通过，类型/lint/build与前端回归通过；最终Electron7组主路径全部通过，[结果](evidence/cross-module/final-electron/results.json)。其中验证了读取后台状态503→自动恢复、失败重试、草稿明确保存、查看答案不写作答、自评只记一次、暂停会话不覆盖单题、连续练习遵守搜索筛选。

## Astra决策、偏差与未验证项

集中规范见 [Astra设计](CROSS-MODULE-ASTRA-DESIGN-2026-10-12.md)。已实施紧凑连续过程条、完成条件与当前任务层级、复习资产展开后明确行动、生成笔记直接阅读、练习单列与可见范围。复用既有Runtime、Notes CAS、SM-2与候选导入服务，没有数据库/索引迁移。

- 不新增全局计时器、悬浮任务球或第二套任务系统。Astra判断现有导航足以支持当前使用场景，新增常驻组件的学习收益尚无证据。
- 答案维护保留在练习阅读区的次要折叠入口，未额外构建题库专属编辑状态；生成状态与阅读默认模式已独立。属于工程实施偏差，Astra最终复核接受，不要求新状态机。
- 独立空白自主笔记无现有合法来源合同。手动整理、自由编辑、保存与恢复已有能力通过，但完全无会话记录入口未新增。
- 最终Astra复核首次因用量限制中断，恢复后直接读取24张原图，并复验2张修正图。要求的“参考答案草稿”标题及可见暂停影响已落实，M1/M2关闭，本批有限通过。详见 [Astra视觉复核](CROSS-MODULE-ASTRA-VISUAL-REVIEW-2026-10-12.md)；不替代功能、全部Goal状态或真实模型质量验收。

Teaching Prompt采用问题类型、理解障碍与教材上下文适配，不规定固定回答模板。代表集 [cases](../../evaluation/fixtures/teaching-ux/cases.json) 覆盖概念/推导/应用/追问纠错；[比较脚本](../../scripts/teaching-ux-compare.py)限制4题×前后2版本=8次，已按授权尝试，结果全为AuthenticationError。准确性、可理解性、冗余与教学效果均**未获真实答案验证**。不重试超出预算，不声称提升。

## 前后截图与证据边界

|页面|前|后（实测或fixture标注）|
|---|---|---|
|学习回答|[基线](evidence/cross-module/before/1280-chat.png)|[过程](evidence/cross-module/final-electron/1280-chat-process.png)、[错题公式](evidence/cross-module/final-electron/1280-chat-mistakes.png)；离线流输入，真实SSE/task|
|目标|[基线](evidence/cross-module/before/1280-goals.png)|[正在执行](evidence/cross-module/final-electron/1280-goal-running.png)、[全屏](evidence/cross-module/final-electron/macos-fullscreen.png)；真实Runtime，合成模型动作|
|复习|[基线](evidence/cross-module/before/1280-learning.png)|[1280](evidence/cross-module/final-electron/1280-review-assets.png)、[760](evidence/cross-module/final-electron/760-review-assets.png)；summary合成，记录真实API|
|笔记|[基线编辑状态](evidence/cross-module/before/1280-draft.png)|[直接阅读](evidence/cross-module/final-electron/1280-note-generated-read.png)、[保存](evidence/cross-module/final-electron/1280-note-saved.png)；不同状态对照，非同文前后质量比较|
|练习|[基线首页](evidence/cross-module/before/1280-exercises.png)|[首页](evidence/cross-module/after/1280-exercises.png)、[答案](evidence/cross-module/final-electron/1280-exercise-reference.png)、[解析末尾](evidence/cross-module/final-electron/1280-exercise-analysis-feedback.png)、[断连恢复](evidence/cross-module/final-electron/1280-exercise-poll-unavailable.png)；合成长内容，真实job/save/作答|

最终页面矩阵包含正常、空数据、加载、错误/重试、长内容、1280/1024/760/390与四种主题；[结果](evidence/cross-module/after/results.json)。故障注入503会产生预期console日志，需与实际未处理错误区分。长内容采用合成压力资料，不能证明真实模型公式准确率。

深层Electron回归 [13项结果](evidence/cross-module/deep-electron/results.json) 复验笔记503/CAS/归档、复制失败、候选合并拆分与校对、Word/文本PDF导入及回滚、图片附件、来源Inspector与阅读器；真实数据库/文件操作均位于/tmp，不触碰正式学习记录。

剩余风险：未验证真实模型答案与线上“待核验”频率；原重复错题现场缺失；移动相机未实测；独立空白笔记未实施；目标待输入/待确认专属Electron交互和生产桌面打包/升级未覆盖。Vite保留原有mathlive大chunk提示，本轮不重构依赖。所有已修复状态以列明的验证范围为准。

## 最终自动化结果与Git checkpoint

|层级|结果|证据|
|---|---|---|
|Python 3.10完整后端|1544通过，6条现有依赖弃用warning|[日志](evidence/latest/backend/backend.log)|
|前端Vitest|199通过|[日志](evidence/latest/frontend/frontend.log)|
|桌面Node测试|15通过；沙盒socket测试需外层许可|[日志](evidence/latest/desktop/desktop.log)|
|类型/lint/生产构建|全部通过；保留mathlive chunk提示|[构建日志](evidence/cross-module/final-build.log)|
|最终Electron|7组主路径通过，0 pageerror|[结果](evidence/cross-module/final-electron/results.json)|
|深层Electron|13项通过|[结果](evidence/cross-module/deep-electron/results.json)|
|页面矩阵|119项；0横向溢出、0未处理路由、0失败；11条console为主动注入的503|[结果](evidence/cross-module/after/results.json)|
|Teaching Prompt真实比较|8次均AuthenticationError，未得有效答案|[脱敏结果](evidence/cross-module/teaching-comparison.json)|
|Astra视觉复核|26次原图读取，本批有限通过；两项必须修改关闭|[复核](CROSS-MODULE-ASTRA-VISUAL-REVIEW-2026-10-12.md)|

分支 `codex/cross-module-remediation`，基线 `c53e78b`。模块checkpoint：

|模块|commit|
|---|---|
|目标P0/桌面全屏|`cde805e`|
|问答/引用/Prompt|`831eb51`|
|过程真实性追加|`e9b731d`|
|复习|`662aa73`|
|笔记|`bb6b158`|
|练习|`d6c8d43`|
|最终核验映射|`10c8724`|
|Astra要求两处修正|`f04f2c1`|

页面矩阵在最终文案小修正之前采集；这两处运行态文案通过最终Electron原图、交互和Astra最小复验补验。构建与当前源码身份记录于 [manifest](evidence/cross-module/manifest.json)。未推送或创建PR，未改正式学习数据、模型配置或依赖。
