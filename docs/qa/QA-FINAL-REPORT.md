# Texa 全系统质量审计：阶段验收报告

2026-10-11 · Lead Sol · `codex/mobile-s2-a2` · 整改检查点 `35107fc` · 报告/证据检查点 `1b16502`

## 质量结论

完成了代码驱动的系统盘点、独立模块审计、第一批根因整改及隔离回归。当前可以作为下一轮整改的可重复基线，但**尚不能宣布达到 S3 Android App 产品化质量门槛**。旧直接练习接口的持久幂等性仍有确认风险；真实 Android/Tailscale、Windows 打包生命周期、真实教材与模型验收尚未完成。全量离线测试通过不等于所有业务链路、模型答案与设备环境全部通过。

既有 Mobile S2 未提交改动保留。本次没有修改用户学习数据、迁移 schema、安装依赖、付费调用模型、改变冻结评测数据或门槛。

## 实际范围与结果

|范围|结果|证据|
|---|---|---|
|实际页面/入口盘点|18 个渲染 Route pattern，另有 settings 弹窗重定向；自动遍历19 URLs，识别2兼容别名及无正式入口的历史 API|QA-INVENTORY.md、frontend-inventory.md|
|模块与链路|15个跨功能模块，19条页面入口→状态→API→服务→存储→UI链路；205个API handler静态盘点|API-ENDPOINTS.md、api-inventory.json；静态盘点不是执行 PASS|
|页面渲染与视觉审查|119个有效状态检查：76个四视口正常页面、20主题状态、21空/加载/失败状态、2重试恢复状态；均由 Sol 或其限定模块 Subagent 实际读取|evidence/accepted-pages.json逐项指向截图；旧Fixture失败图已明确排除|
|交互|9种 Fixture 交互：笔记筛选/草稿阅读编辑、5设置Tab、笔记/复习读取失败后重试|evidence/pages-repeat/results.json|
|真实API/SQLite E2E|5种核心旅程×桌面1280/手机390，共10项 PASS|evidence/live-e2e/results.json；均使用真实 FastAPI 服务与临时数据库|
|重启/权威数据核对|6条最新资产/会话记录恢复，API与SQLite单行/正文/复习结果一致；新错题各仅1次复习记录；6数据库integrity/foreign_key检查 PASS|evidence/restart-persistence.json；测试后端停止后重启|
|后端全量|1532 PASS，6条既有扩展弃用警告；增加23条有针对性的回归|evidence/latest/backend/backend.log|
|前端全量|42文件/191测试 PASS|evidence/latest/frontend/frontend.log|
|快速 Smoke|117 PASS，约5秒测试执行时间|evidence/latest/smoke/backend.log；不同层日志隔离|
|Desktop单元|15/15 PASS；socket权限获准后执行|evidence/platform-desktop-tests-escalated.log|
|真实macOS Electron壳|启动/preload、笔记导航→设置→Escape、正常关闭，3项 PASS|evidence/electron/results.json及实际读取的完整截图；使用隔离userData与外部Fixture后端|
|类型/静态检查/构建|PASS；保留大型数学输入chunk警告，未无依据优化|evidence/latest/build/{types,lint,build}.log|
|视觉回归体系|审阅后固定8张基准，重复生成比较8/8 PASS|baselines/、evidence/visual-comparison.json；像素相似不替代审美审查|

典型视口为1280×820、1024×768、760×820、390×844。使用真实现有 mineral/graphite/clay/notebook/codex 主题；dark media preference 已运行，但没有将现有浅色主题冒称为深色主题。当前代码未发现 manifest/service worker，移动入口应按远程响应式浏览器验收，不能宣称已验证离线 PWA 安装。

## 缺陷与共同根因

确认11项：P0=0、P1=1、P2=8、P3=2。10项 FIXED；1项 FAIL 已做风险收敛。优先级是本次审计判断，不代表未检查处不存在其他高风险问题。

|根因批次|问题/文件/修复|实际验证与回归范围|
|---|---|---|
|错误路径假设清理与脱敏不会失败|R1：owned_stream.py在fence异常时仍关闭producer，保留主错误及清理错误；R2：chat.py对预处理SSE、生成错误、checkpoint统一复用既有诊断脱敏|10条新增故障注入；55项相关测试；检查返回SSE和真实临时SQLite checkpoint不含合成凭证/路径。未保证任意无标签秘密都可识别|
|报表读取兼容投影而非权威历史，范围/天数合同分散|A1/A2/A3：reports.py按subject层级过滤资产/概念，新增learning_reports.py游标读取SQLite权威历史，days统一归一并如实返回|9条新增测试；21相关测试；230 user turns、无JSON、legacy导入、父子scope、日期边界；36隔离DB检查，原消息数量未变|
|跨库副作用没有同一提交语义|A4：exercises.py仅对主practice已保存后的附属失败返回partial/practice_saved/unconfirmed警告，主写失败仍失败，不补偿、不自动重试|4条真实临时DB测试，含附属写前失败/写后抛错；practice计数与已提交link核对。**丢响应/手动重试仍可重复，未标FIXED**。Astra只收到Sol结构化文字并提出收敛原则|
|学习摘要与正文使用不同渲染/局部CSS压缩|U1/U2：LearningPage、MistakeIntakePage、WeeklyReportPage复用SimpleMarkdown；局部CSS避免破坏KaTeX内部span，紧凑header控制收缩与换行|前后截图保存在ui-before、pages-final/supplement/repeat；四视口、主题及长公式实际读取。类型/构建/191前端回归通过|
|加载失败与“确实为空”混为一谈|U3/U4：NotesPage抑制错误时未经确认的空提示；ReviewSessionPage拆分读取/操作错误、重置loading/items、阻止失败后开始、提供重试|真实Fixture503→点击重试→恢复列表/开始按钮，自动断言与前后截图；正常空、loading、已有内容仍呈现；191前端回归通过|
|操作入口依赖空态|U5：ExercisesPage把手动录入入口放在始终可访问的header，保留现有dialog；局部nowrap保证手机Tab不逐字换行|发现图live-e2e/failure.png；修复后四视口实际读取；两视口真实API空输入阻止保存→填入→保存→刷新→SQLite唯一行。已存在习题时仍能新增|

详细问题状态、证据与根因边界见 [QA-ISSUES.md](QA-ISSUES.md)。UI 改动保持现有学习工作区视觉语言，未统一成泛化Dashboard，未进行大规模信息架构重构。

## 已通过的核心端到端任务

- 手动错题草稿保存→刷新→恢复。
- 草稿校对→明确保存为错题→独立档案读取。
- 复习会话作答草稿保存→刷新→恢复。
- 展示参考→用户自评→复习完成→刷新保持完成；后端重启保持结果与一次作答记录。
- 手动习题输入校验→保存→刷新→唯一持久行；已有题库仍可操作。

这些流程实际经过 UI、API、领域服务和 SQLite；模型/OCR 未参与，因此不构成 OCR 或模型准确率证明。完整笔记保存、教材摄取发布和主聊天停止/恢复目前主要由确定性存储/Runtime测试覆盖，尚不是本轮完整真实模型浏览器 E2E。

## 未完成、阻塞与人工验收

|状态|范围|原因/下一项验收|
|---|---|---|
|FAIL contained|A4旧直接练习重复请求|需要稳定operation identity/receipt与跨库最终状态合同；涉及兼容/持久设计，先形成明确方案再实施，不用HTTP200掩盖缺口|
|NOT_TESTED|每个弹窗/菜单/抽屉全部状态、键盘焦点与触摸命中、每条链路全部10种异常组合|119截图和已命名旅程不是穷举。继续从frontend-inventory逐项扩展Fixture及操作断言|
|NOT_TESTED|长session内存/泄漏、真实大教材处理和SSE首事件性能基准|没有足够基准，未擅自重构或声称优化完成|
|BLOCKED Requires Real Device|Android前后台、软件键盘、安全区、弱网、真实Tailscale Direct↔DERP/断线恢复|Playwright网络模拟不能证明真实隧道路径；需真实设备与网络证据|
|BLOCKED environment|Windows/macOS正式包后端托管、更新回滚、异常退出恢复|macOS壳Fixture smoke只验证已列动作，不能替代正式发布包全生命周期|
|BLOCKED external acceptance|当前真实教材索引黄金集、OCR数学/表格正确性、线上模型答案/Policy评估|无付费/数据出境批准，未发起；冻结benchmark/门槛保持原样。离线合同结果不是概率性模型质量|
|NOT_TESTED capability absent|离线PWA安装/缓存/推送|当前未实现相应资源，不把规划功能计为PASS|

可以继续 S2 整合和质量整改；进入 S3 产品化前，应至少关闭 A4 的重复提交合同风险，完成目标设备/正式包核心学习闭环和真实教材/模型验收，并补齐核心弹窗/取消/跨页面恢复测试。

## 可维护测试入口

参见 [RUN-QA.md](RUN-QA.md)。所有写入测试使用临时目录，日志与截图落盘；后端/前端/桌面/构建按层运行，常规修改先Smoke，受影响领域回归后再全量。已有Playwright/Vitest/Pytest/Electron工具复用，没有新增大型平台。基准仅在实际审阅后确认，不能自动更新来消除失败。
