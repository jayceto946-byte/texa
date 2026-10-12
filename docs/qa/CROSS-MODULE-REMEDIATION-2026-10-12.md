# Texa 跨模块整改 · 2026-10-12

本轮以当前未提交工作区为基线；既有移动网络、候选校对、笔记冲突、图片裁剪及来源 Inspector 改动保留。26项按用户条目拆分登记，不能把源码修改等同于实际验收。所有运行使用隔离合成资料，不访问正式学习数据或外部模型。

基线构建 `/tmp/texa-cross-module-before`；原图位于 [before](evidence/cross-module/before)。浏览器素材使用现有 qa-pages 工具；合成状态不能证明真实模型质量。Astra集中设计中。

|ID|问题|代码/组件|状态|根因与验证|
|---|---|---|---|---|
|01|Gate放行但待核验/未完整|graph/generator.py; backend/services/answer_verification.py; ExecutionTrace|未完成|检索Gate与最终答案验证是不同门槛，需逐类诊断|
|02|无实际意义的执行步骤|ExecutionTrace; chatActivities|未完成|核对持久execution事件与展示|
|03|选中文字添加到对话|ChatMessage; ChatPage|未完成|需引用原文并保留输入草稿|
|04|移除学科通用标签|ChatMessage|未完成|仅移除冗余标签，不改变回答模式|
|05|移除点赞点踩入口|ChatMessage|未完成|保留已有数据及后端兼容|
|06|输入框高度自适应|ChatPage; composer样式|未完成|键入/程序引用/多轮清空/尺寸变化|
|07|桌面拍照功能|ChatPage|未完成|HTML capture不保证桌面相机能力|
|08|错题展开LaTeX|ChatPage|未完成|候选题干当前按纯文本显示|
|09|错题展开外部关闭|ChatPage|未完成|候选浮层需pointer dismissal|
|10|错题展开Esc|ChatPage|未完成|键盘关闭及焦点返回|
|11|P0连续继续执行|GoalsPage; goals/execution.py|已修复|同步actionBusy准入 + 后端重复恢复返回同run；SQLite10项通过，Electron连续12次点击1次POST且同task新run|
|12|原始Runtime Event|GoalsPage|已修复|使用受控状态映射，原事件留在Runtime诊断；Electron展开确认无raw lifecycle|
|13|英文异常|GoalsPage; goal API|已修复|中文业务提示保留，英文异常映射；runtimePresentation回归|
|14|macOS全屏预留空间|DesktopTitleBar; desktop IPC; CSS|已修复|Electron原生fullscreen IPC，Mac身份保留且取消留白；真实进出全屏通过|
|15|目标信息层级和控制|GoalsPage|已修复|完成条件默认可见、本次任务包含执行控制；Electron运行态截图已读|
|16|跨页目标入口/计时价值|Workspace; GoalsPage|暂缓|Astra评估决定不新增计时器/全局任务中心，复用现有导航|
|17|目标/task/Session/定时关系|GoalsPage|已修复|保留同Runtime/task，跨页读取同task；定时说明本地后端运行|
|18|相似错题重复入队|review服务; mistake store|未完成|区分重复ID和合法独立记录|
|19|复习文字对齐层级|LearningPage; ReviewSessionPage|未完成|Astra集中设计|
|20|复习资产行动价值|LearningPage|未完成|Astra先评估收益与复杂度|
|21|自动整理/自主记录区分|NotesPage; DraftWorkspace|未完成|保持独立资产和明确保存|
|22|生成成功直接阅读|NoteDraftPage; DraftWorkspace|未完成|generation已默认preview；检查实际类型及流程|
|23|自主编辑保存/恢复再编辑|DraftWorkspace; NotePage|未完成|复用已有CAS及失败保留|
|24|标准答案异步状态/重试|useExerciseAnswerJob; ExercisesPage|未完成|轮询重叠、错误未明确、状态仅间接文案|
|25|答案解析长文公式|ExercisesPage|未完成|双列和文本编辑区压缩阅读|
|26|练习抽题布局/维护分离|ExercisesPage; ExerciseCard|未完成|Astra集中设计|

## Checkpoint与验收记录

各模块完成后记录实际检查、Git身份及前后图；后续共享改动回归此前模块。Teaching Prompt比较须覆盖概念、推导、应用、追问纠错；无真实模型比较不得宣布教学效果提升。

目标模块阶段验收：后端10项、桌面15项通过；Electron 3类检查通过（目标重复恢复/聊天复验/macOS全屏），[结果](evidence/cross-module/goals-electron/results.json)。动态截图已直接读取；待输入、待确认等视觉状态将在最终扩展检查补齐，不以运行态截图冒充全部状态。Astra规范：[集中设计](CROSS-MODULE-ASTRA-DESIGN-2026-10-12.md)。
