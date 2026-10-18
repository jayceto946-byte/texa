# P1-ABC Integration & Acceptance

2026-10-18 · 最新结论：**HOLD（教学发布验收）**。工程组合回归仍为 PASS；用户随后授权的真实教学测试发现工具协议、结构化输出与联合交付失败。详见 [真实教学报告](docs/qa/p1-abc-integration/real-teaching-2026-10-18/REPORT.md)。

## A. Git

| 项目 | 结果 |
|---|---|
| Worktree | `/Users/jichengqian/Documents/ChatGPT/texa-p1-integration` |
| Branch | `integration/p1-abc` |
| Base（含 P0） | `ac071baca0382bdfefece0c1a2b693105dced8a7` |
| P1-A 原提交 / merge | `c75695c77d7f6b2f6d7deb53f0ab6b360993212b` / `e80c318` |
| P1-B 原提交 / merge | `0c2f07389198c53e4879d305590b3a9be3611a3d` / `caf56a3` |
| 候选合同独立提交 | `eadc350` |
| P1-C 原提交 / merge | `bfe4933ef8b24a49a347d88392062dd4d49b3ba8` / `ba7b55d` |
| 兼容修复 | `61a453d`、`83add10` |
| 最终受测代码 HEAD SHA | `83add1087ed557e8fe93802fbc15bf70f8663f30` |
| 交付 HEAD | 本报告所在提交：`git rev-parse integration/p1-abc`；完整交付 SHA 另见交付消息。报告提交仅增加文档，避免把自引用 SHA 写为虚假值 |
| 未提交修改 | 无（交付后 `git status --porcelain` 为空；ignored 构建/截图不入 Git） |

主目录仍为 `Texa_MacOS/ac071ba`；开始/结束 Git 状态一致，记录的原修改文件 hash 不变，三个功能分支 SHA 不变。没有切换/清理/stash/merge 主目录、复制生产学习库、修改凭据、push 或合入稳定分支。

## B. 集成结果

| 能力 | 状态 | 实际边界 |
|---|---|---|
| P1-A | PASS | 完整块预算、Final EvidencePack、模型消息可见性、公式/图片状态与来源版本保持一致 |
| P1-B | PASS | verify v3、可信结构化原题、依赖步骤、valid/invalid/unknown、隔离运算及局部证明范围保留 |
| 候选题合同 | PASS（隔离快照） | 原来无独立提交；提取13个 tracked 文件补丁及12个新文件，独立测试/提交/撤销；排除侧栏、共享布局和私有数据 |
| P1-C | PASS | 旧 JSON/未知字段、Canonical ID、同次响应 metadata、保存、attempt 证据、确认幂等/失效及弱项隔离 |

候选来源及文件 SHA：[candidate-provenance.json](docs/qa/p1-abc-integration/candidate-provenance.json)。设计、合成结构样本与原开发报告保留供审查；其中历史108题/91项等结果**不是本轮集成结果**。本轮未重新抽取108份冻结私有来源。原工作区候选项目仍未提交；集成分支使用 `eadc350` 的明确快照，后续新增改动需另审。

三次合入只有 `patch_notes.md` 内容冲突，全部真实记录按功能保留；共享代码由 Git 合并后逐项核对，未整文件覆盖。必要兼容修复：

- `ExerciseRecord.extra_fields.visual_ir` 纳入题目版本；旧带此扩展的分类可正确过期，无数据库迁移。
- 通用 `update` 修改参考答案/解析时令旧分类 stale；导入时确认回执只保留历史事实。
- 已有原生消息的恢复先复核教材 version/schema/index；bounded 各入口在模型调用前复核冻结工具 version/schema，覆盖 finish-only。旧任务不改写，拒绝后提示重新发起。
- 两项旧测试对齐合同：索引变更准确报告 scope_changed；标签+旧SM-2自评不能替代已确认作答证据。原复习行为断言保留。

没有新增路由模型、Adaptive Tool Scoping、Agent Loop、数学工具或分类 UI；没有放宽验证或证据门槛。

## C. 本轮实测

环境：macOS arm64，现有 venv310/Python 3.10.21，Electron 37.10.3；未重装依赖；ignored目录仅链接既有Python/Node依赖。

| 层级 | 结果 | 本轮实际执行 |
|---|---|---|
| A 合入后 | PASS | 原 A 回归353项 |
| A+B 合入后 | PASS | 原 B 14文件257项 |
| 候选独立快照 | PASS | 后端90项；前端234项、TypeScript/Vite |
| A+B+候选+C | PASS | C原19文件+候选合同247项 |
| **最终组合全量 Python** | **PASS** | **1874项**；含教材、P0数学、Verify v3、题库/错题/SM-2、Registry、FixedRunner、Native/SSE、取消/恢复/版本及失败恢复 |
| 最终前端 | PASS | 234项、ESLint、TypeScript/Vite；既有大chunk提示保留 |
| Electron壳 | PASS | 24项、check |
| 实际 Electron：P1-C | PASS | 16项：保存/同考点、证据建议与确认重放、弱项、编辑失效；三尺寸 |
| 实际 Electron：候选 | PASS | 14项：真实renderer/API/临时SQLite、合成来源分离、缺图保留、子集提交与回执；三尺寸 |
| 确定性联合链路 | PASS | 10项组合探针；教材上下文+数学回执在下一模型轮均保留；候选→正式题→Job分类保存→改答案失效；JSON扩展与旧合同拒绝 |
| 真实模型及联合教学 | **FAIL / HOLD** | 授权后12任务（11真实模型+1本地编辑），17请求、73167 tokens；逐项6 PASS/5 FAIL/1 NOT VERIFIED，不能换算一般准确率 |
| 实机聊天断线/暂停恢复、Windows、安装包升级/回滚 | **NOT VERIFIED** | Python恢复合同通过不等同于桌面完整教学恢复验收 |

各阶段计数有重叠，不相加。最终日志：[full-final.txt](docs/qa/p1-abc-integration/full-final.txt)。初次组合探针及全量失败也保留；修复缺陷后未删除负例。首轮全量1870 PASS/2 FAIL分别是上述旧错误码/标签弱项预期；收尾又以两项负例补上bounded finish-only版本门槛。

Electron 辅助配置/readiness为显式fixture，抽取边界使用合成Canonical IR，未验证启动预热或真实模型。实际查看1280×820、1024×768、760×820的候选及诊断六张截图，无对应状态裁切；不冒充Astra设计签核。首次候选QA夹具缺 providers/models 引起启动TypeError，补齐夹具后通过，未为此改产品UI。证据：[Electron候选](docs/qa/p1-abc-integration/electron-candidate.json)、[Electron P1-C](docs/qa/p1-abc-integration/electron-p1c.json)、[截图hash](docs/qa/p1-abc-integration/visual-checks.json)。

集成阶段只检查了活动Flash方案，真实模型部分原为NOT VERIFIED。用户随后明确授权，进一步核对已保存profiles，找到有专用凭证的 `default` Qwen3.7 Plus；仅在隔离进程内使用该既有方案，未切生产活动profile。真实验收实际 **17请求、输入52136/输出21031/总73167 tokens**，10次已执行工具（4教材准备+6数学），无SDK重试、无付费样本重跑、无第二评委。12任务逐项PASS/FAIL/NOT VERIFIED、每项用量/延迟和全部失败回执见 [summary.json](docs/qa/p1-abc-integration/real-teaching-2026-10-18/summary.json)。

主要FAIL：B1 v3参数错误导致unknown；B3将computed称为工具核验；C2 metadata标签及证据span错误；C3分类遗漏status且教学泛化漏条件；AB两次参数错误后恢复求导，但在既定工具预算下以native_loop_failed结束、正式答案为空。C1/AC真实分类保存成功；ABC分类修改stale通过，因C2无合法诊断，其确认后的失效链路仍NOT VERIFIED。没有以更多工具调用数、正确阶段推导或Mock补写掩盖失败。

本轮样本完全自编、临时SQL，检索锚点由夹具选择；真实Provider/Runtime/SSE/数学及存储边界被执行。未验证生产混合检索、聊天入口分流/关键输入准入、实际视觉或Electron真实模型完整交互。配置/凭据文件hash不变，未输出/复制密钥，测试产物无已知凭证值；没有更改生产代码或放宽任何门槛。

## D. 保留风险

- 教材缺图：资源/图注可取不等于模型已读，必要图仍阻止 complete；真实视觉教学未测。
- 普通自然语言数学条件仍可能 unknown；显式 math-context 不是通用题干可信解析，不把局部 valid 升为整题通过。
- 结构化 JSON/Schema/Canonical ID/span 合法不证明语义正确；本轮已观察到metadata协议、span、status及一般数学条件遗漏，真实分类/诊断不能宣称稳定。
- 旧工具合同已通过拒绝/重新发起探针；未改旧任务数据，也不保证任意版本都可恢复。
- 题目/图片/visual_ir/参考答案版本失效保持；导入确认、分类及错因确认互不替代。最终答案样本没有捏造用户具体错误原因，未确认原因不计入弱项；真实有效诊断的完整确认/失效仍未验。
- Native Loop模型自主工具候选仍限数学；教材是既有准备步骤，P1-C结构只接既有习题/错题响应。没有任意跨领域自主组合或主聊天自动写知识metadata的能力；未解除allowlist。
- 候选旧legacy准入、去重D03/D04、复杂边界/公式/原图人工核对等历史限制仍在；本次未重新证明108题内容质量。

## E. 三项独立判断

**HOLD（教学发布）**

1. **代码能否集成稳定分支：工程集成仍可作为审查候选，不能据此扩大P1能力启用。** 真实教学缺陷应单独修复/复验；本任务未自动合入 `Texa_MacOS`，主目录仍运行原检出。
2. **能否进入真实用户测试：仅限有人工复核、失败可见及明确限制的诊断性试用。** 真实教学普通发布门槛未通过；不能把本轮少量正确答案当稳定教学能力。
3. **是否具备完整生产教学上线条件：否，HOLD。** 已观察的工具参数、核验归因、结构化输出和联合失败交付需先修复并独立复验；真实视觉和实机聊天恢复仍 NOT VERIFIED。
