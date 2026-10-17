# R1/R2 Post-Approval Engineering Closure

2026-10-17 · `Texa_MacOS` · macOS Electron 37.10.3 · Python 3.10.21

工程收尾完成，已批准构图未改变。真实模型、OCR、生产写入、Windows 与安装包生命周期未验证，不扩大 Astra 的 DESIGN APPROVED 范围。

## Git checkpoint 与归属

- 起始 HEAD：`1824fcc7d7f33c7a08faef9cd285d566f5b3ac79`；起始暂存区为空。
- Checkpoint：`510f0d6`，`checkpoint(ui): finalize R1 R2 design-approved integration`。37个文件，含正式 React 阅读/导入集成、相关测试、R1/R2/Astra/Sol 文档、参考包与证据索引，只暂存 patch_notes 对应段落。
- [文件归属清单](docs/qa/r1-r2-post-approval/checkpoint-ownership.json)逐项列出纳入文件与受保护的其他任务文件及 hash。依据既有 implementation/delivery 文档归属，没有把所有未提交修改当成本任务。
- 其他任务的 AppRail、LearningContextSidebar、OverflowMenu、conversations.css、MainLayout、ApprovedWorkspace.css、StudyDesk.css、历史 patch_notes 段落，以及两份10月15日设计审计文档均未纳入。
- 14.4MB `electron-evidence-r1-r2.zip` 留在本地未跟踪；ignored `artifacts/` 原型/初审/整改/settled-regression 截图不批量提交。Git 保留既有 SHA256 索引、2.4MB参考包及本次少量合成数据截图。真实副本、私有截图、构建产物、依赖和凭证均不提交。
- SSH fetch 连接失败；HTTPS fetch 成功，起始 HEAD 与刷新后的 `origin/Texa_MacOS` ahead/behind 为0/0。其他设备尚未推送的提交无法观察。本次不 push、不合并、不切分支、不改写历史。
- 凭证模式扫描（含参考 ZIP 内文本）未发现密钥；三个既有 CSS 文件的末尾多余空行在后续修复提交清理。

## N1–N4

| 项目 | 状态 | 处理与验证 |
|---|---|---|
| N1 | PASS / CLOSED | 当前基线已用“公式”占位，未重复修复旧截图中的全删问题；新增本域确定性 preview，保留≤32字符短公式、长式/多行式用明确占位，80字符预算不截断数学 token。原题不变，无模型摘要。5项单测覆盖行内、独立、长式、中英混排、多公式与普通文本；Electron 预览实际生成 KaTeX。 |
| N2 | PASS / CLOSED | 移除重复完成提示，保存操作旁统一为“未保存草稿 · 保存后成为题库答案；关闭题目、刷新或退出会丢失编辑”。已生成原稿可能可从 job 恢复，但本地人工编辑没有自动保存承诺；跨页面保持挂载不等于关闭题目。 |
| N3 | PASS / CLOSED | Astra 已确认显著性改善，保留原局部 warning 样式。补充分支语义：明确 `success:false` 为保存失败；异常/无完整回执为保存未确认。两者均保稿，不自动重写；503不被当成确定失败。 |
| N4 | PASS / CLOSED | 使用既有只读 `/system/remote-ready` 的结构化 ready。确切 false 时提供配置入口与重新检查，移除不可执行生成操作；查询失败/非法响应保留 unknown，不从错误文案推断未配置。入口复用主布局 openSettings 状态合同，在当前题目上打开设置，避免把旧 `/settings` 重定向放进持久页面缓存。未改 Provider/Settings 体系。 |

本轮局部画面由 Sol 直接检查，未开启新设计审计。I1–I4、D1、E1–E2、F1 的既有设计结论保持有效。

## 环境与数据保护

真实数据源为本机桌面数据目录；SQLite 使用 `mode=ro` + backup 形成独立一致性副本，复制教材 Canonical IR 与托管图片，副本中的绝对图片引用重定位到副本根。只导入副本后的正式应用模块；`.env` 不复制，清除 API 凭证环境项。原始数据库逻辑 dump SHA256 在测试前后相同。

真实题库有16条记录、最长题干470字符；正式教材 IR 确定性抽出108道候选。真实错题2条，均有原图，其中1条有旧复习历史；题库原记录无 image_path。另用220条合成记录测试真实 API 存储，用240条合成候选检查界面规模；不能把它们称为真实题库规模。

API 使用正式 FastAPI 路由/SQLite/JobManager。真实数据 Electron 测试中，生成 producer 与配置就绪为明确受控适配；首次运行标记和健康就绪由隔离环境提供，lifespan 工人/调度/warmup 关闭。无真实向量库召回质量或启动恢复结论。禁用模型辅助修复、远程 OCR 及其他付费入口。本次无新增付费/出境授权预算，因此未调用真实模型/OCR，也未向外部测试平台上传任何数据。

## 测试结果

| 类别 | 测试 | 结果 | 可推导的结论 |
|---|---|---|---|
| 工程 | 全量前端单测 | PASS，51文件/227项 | 含新增preview5项；相关领域状态测试通过 |
| 工程 | 全量 ESLint、TypeScript、Vite build | PASS | 既有>500KB chunk警告仍存在，未重构打包 |
| 工程 | 后端相关测试 | PASS，66项 | 习题库、Word/PDF解析、教材候选、错题生命周期/API/图片；使用临时数据及模拟模型 |
| 工程 | desktop 单测与语法检查 | PASS，24项 | 一次沙箱端口 EPERM 后在允许本机监听的环境复跑 |
| 固定 Fixture | 正式 Electron 全状态和跨页面 | PASS，156检查/94图 | macOS 1280×820、1024×768；760×820冒烟。题库/AI保存/练习/导入/错题/笔记/聊天阅读；真实渲染不等于真实业务数据 |
| 固定 Fixture | N1–N4、配置入口、迟到响应、240候选 | PASS | 详见版本化测试证据；原构图、未保存状态与未知回执栅栏保持 |
| 真实数据隔离 | 原16条题目 API/正文一致性 | PASS | API与存储的完整题干逐条比较，不对OCR语义正确性背书 |
| 真实数据隔离 | 正式教材抽取108候选 | PASS | Canonical IR→候选→正式UI，未运行新OCR |
| 真实数据隔离 | 真实例题题干/解答结构化分离 | FAIL / D-01 OPEN | 已观察首个例题把“解”留在题干且答案字段为空；正文保留，仍须人工拆分校对。本轮不改解析体系 |
| 真实数据隔离 | 选范围→两题练习→暂停/继续→作答/自评→完成 | PASS | 同一session，重复作答不重复增加计数；完成后能读取持久结果，统计刷新 |
| 真实数据隔离 | 学习→练习→学习/练习 | PASS | 挂载期间作答草稿保留；聊天正文样式另由Fixture A→B→A检查 |
| 真实数据 + 受控生成 | 创建/复用job→读取完成→编辑→明确保存→参考答案→题库 | PASS | 正式job API/持久化/前端hook生效；completed不会自动写答案；生成和配置适配不算真实模型 |
| 真实数据隔离 | 候选人工编辑→单题确认入库→真实批次回执 | PASS | Electron完成；仅写副本 |
| 合成数据 + 真实API | 空批次、错误字段、220条批量存储 | PASS | 错误格式422；空结果明确；不证明部分提交有事务回执 |
| 固定 Fixture | 长答案/矩阵、图片降级、零/200以上候选、分析失败保留、重复项跳过、未知提交不重发 | PASS | 来源仍为固定API；文件选择不是实际源文件解析 |
| 固定 Fixture | 网络断开→查询同job恢复、明确失败/保存未确认、跨题迟到响应 | PASS | 未因切面板自动创建job；不代表真实服务中断/进程崩溃恢复 |
| 固定 Fixture + 后端临时库 | 错题读取/原始作答/参考答案/错因/来源/原图/历史、归档恢复、独立重做四结果 | PASS | 保持既有领域语义；F1不接入 |
| 真实数据隔离 | 真实错题读取/原图、归档恢复、独立重做 | PASS | 2条实际记录的正式API验证；Electron从详情重做到返回同一详情，F1继续不接入 |
| 真实数据隔离 | 题库path-only图片 | NOT TESTED | 源习题无image_path；错题图片成功不等于题库图片能力完成 |
| 真实文件 | 用户原始Word/PDF导入、真实OMML/图片/公式正确性 | NOT TESTED | 桌面数据中没有可用原始Word/PDF；已有Canonical IR及MinerU结果不等于原文件重跑 |
| 真实OCR | 扫描PDF、识别异常、远程MinerU | NOT TESTED | 无本轮模型/OCR授权环境；合成解析失败仅证明界面保留逻辑 |
| 真实模型API | 模型参数/质量/实际queued运行、真实生成失败 | NOT TESTED | 无本轮付费/出境预算，受控结果不替代 |
| 生命周期 | 完整重启/崩溃后未提交练习草稿与AI人工编辑恢复 | NOT TESTED | 本轮验证挂载保留及数据库结果重读；本地编辑为内存状态 |
| 生产环境 | 用户生产记录写入、升级/回滚/安装包/Windows | NOT TESTED | 未执行，保持原验收边界 |

真实数据API最终24项 PASS；真实数据Electron21项 PASS/10张私有截图。直接阅读额外发现D-01结构化分离FAIL，与API合同通过分开记录。断言项数不等于独立场景或准确率。

## 失败、分类与剩余问题

- C / 已关闭：首轮 Fixture 未补 remote-ready，出现404；补齐接口后复跑。初次 npm/Playwright 未在 PATH/module 搜索路径；使用已安装运行时，无依赖重装。端口监听由沙箱拒绝后经现有授权复跑。
- C / 已关闭：隔离后端禁用 lifespan 导致 health pending、受控producer首次配置门槛、真实教材学科选择、隐藏参考区公式定位、测试依赖Fixture的完成文案。均修正测试适配/断言，没有为测试更改正式服务或降低工作流断言。
- C / 已关闭：首轮快照的 `*bank*.db` 错误漏掉 `mistake_book`，导致错题数据不足的错误初判；改为两类明确文件名、完整四库重新快照。默认错题库的WAL只读连接需要沙箱外协调SQLite元数据；通过 mode=ro backup 获得一致性副本后重跑。真实 action 回执仅含 revision，测试改为再次GET读取完整档案；不将Fixture的全记录回执当真实合同。
- B / 记录：真实完成会话不返回 active overview，旧有“上轮完成”条件块不能稳定保留；当前“本轮完成：2题…”状态及持久作答正常。此行为在R1/R2前hook与后台已存在，后续如需“最近一轮”卡片应建立明确读取合同，本轮不扩展。
- A / 已关闭：N4 初版使用 `/settings` Link，真实点击验证发现持久页面缓存保留 Navigate，关闭后导航可能重开设置。改为当前路由的既有 openSettings 状态合同；补充“打开→关闭→返回同题→重新检查配置”断言。没有重写全局缓存或Settings。其余本轮UI回归未发现尚未关闭项。D / 大功能缺口：见三个独立待办。
- 未提交草稿跨刷新/重启持久化没有实现承诺；不能把本轮暂停/继续与切页通过说成重启恢复通过。真实材料的OCR、公式及人工作答金标仍需后续验收。
- [独立集成问题记录](docs/qa/r1-r2-post-approval/integration-findings.md)：D-01教材题干/解答分离、B-01完成摘要。真实108候选中93条需注意、16条重复；不是108道已校对可直接练习的题目。不自动修复或批量写入生产库。

## F1–F3 独立待办

推荐顺序按收益与依赖：

1. [F3 安全图片资源读取](docs/qa/r1-r2-post-approval/F3-exercise-images.md)：P1；缺图直接阻断完整题意，约3–5工程日。
2. [F2 题干编辑与历史内容版本](docs/qa/r1-r2-post-approval/F2-exercise-editing.md)：P2；约5–8工程日，附件编辑依赖F3。
3. [F1 错题AI草稿/CAS/幂等保存](docs/qa/r1-r2-post-approval/F1-mistake-ai.md)：P2；约5–8工程日，加独立真实模型验收。可与F2分开规划。

每份待办含当前API/字段、阻断、模块、风险、最小方案、估算和验收条件；均未实施。数据库/架构变更须按仓库约定另行批准，估算不构成交付工期。

## 证据与最终Git状态

- [Astra原始最终批准](docs/design/exercises-production-r1-r2/astra-review-2026-10-17.md)；既有 `evidence-register.json` 保留初审/整改/settled-regression 的身份与hash。
- 本轮版本化证据在 `docs/qa/r1-r2-post-approval/`，合成截图与脱敏结果另见该目录 evidence 索引。原始日志、完整Fixture截图、真实副本与私有截图只在 ignored `artifacts/r1-r2-post-approval/`。
- 本报告与定向修复作为独立后续提交：`fix(ui): polish exercise integration and real-data QA`；不混入前述checkpoint。提交身份可用 `git log -2 --oneline` 核对，本文件不自嵌自身commit hash。
- 最终暂存区为空，本轮文件均提交；工作区只剩归属清单中的其他任务修改、历史patch_notes段落、两份既有设计审计文档与刻意未纳入的大截图ZIP。它们完整保留，不以清理之名删除。无push/merge/history rewrite。
