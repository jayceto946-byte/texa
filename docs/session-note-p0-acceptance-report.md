# Session → Note P0 验收报告

验收时间：2026-10-02 至 2026-10-03（北京时间）。执行者：Codex Sol。依据：Astra handoff、项目 AGENTS.md 和 Texa UI skill。

## 结论

macOS Electron 三尺寸、核心笔记流程、退出保护、后台中断恢复、发布候选包离线读写及 DMG/ZIP 完整性检查已完成。P0 仍不能标为全部验收通过：Windows 实机与 12 份输出的人工签审未完成，真实模型输出还发现来源之外的扩展，需要语义复核。

本轮真实模型结果与逐份审阅见下方；代理审阅不是人工签审，也不是生产模型准确率。

## 工程与桌面验收

| 项目 | 结果与范围 |
| --- | --- |
| 后端 | Python 3.10.21；109 项 Notes、会话引用、Job、来源、备份、迁移相关测试通过 |
| 前端 | 29 文件、134 项测试；TypeScript、全量 ESLint、Vite 生产构建通过 |
| Electron | 14 项测试通过，包括关闭握手和首次配置完成标志 |
| 原生窗口 | 1280×820、1024×768、760×820 均实看长中文、长标题、公式、矩阵、表格；760px 抽屉及编辑可用，没有发现横向溢出 |
| 笔记生命周期 | 预检、生成预览、自动保存、确认警告后正式保存、同来源第二份笔记、归档/恢复、历史版本只读通过 |
| 来源导航 | 冻结来源 Inspector、超过最近 40 条窗口的原消息定点跳转、后续分页、返回笔记通过 |
| 退出保护 | 注入草稿保存失败后 Cmd+Q 保留窗口及当前文字；解除故障后重试、退出、重启及正式保存通过 |
| 后端恢复 | 仅在隔离 Job 确认为 running 后中断测试后端；恢复为 interrupted、活跃任务为 0，来源保留，不自动重跑模型 |
| 打包应用 | 真实 PyInstaller 后端启动；离线列表、阅读、公式/矩阵/表格、编辑自动保存和 revision 5 正式提交通过 |
| 候选包 | DMG checksum VALID；ZIP 全文件 CRC 通过；ZIP 内 ASAR 与实测应用 hash 一致，六个桌面模块与源码一致 |

原生交互验收使用隔离数据和确定性模型替身；真实模型检查单独走生产生成函数。没有宣称每种状态在三个尺寸均重复覆盖。构建保留既有 Markdown 动态导入及大 chunk 警告。

## 本轮修正

1. 来源跳转保留返回笔记及历史 revision，返回目标校验防止外部地址与路径穿越。
2. 警告未确认不再显示为版本冲突；保存失败保留文字和恢复动作，修改内容清除过时错误。
3. 预检保留 scope 排除轮次，避免再次冻结时误报来源变化；增加对应回归。
4. 桌面首次配置完成标志原子写入不含凭证的 setup-complete.json，避免动态端口改变后重复引导；IPC sender 校验及打包清单已覆盖。
5. 取消、中断和候选恢复错误显示中文状态与明确恢复入口。

## 真实模型与语义审阅

用户明确授权最多 12 次真实调用，零自动重试，仅发送 12 份合成会话。采用已配置的 Qwen qwen3.7-plus；prompt=session-note-structure-v1，policy=session-note-bounded-v1。真实学习记录未发送，凭证未写入产物或报告。

原始合成输入位于 tests/fixtures/session_notes/representative-v1.json；冻结快照、过滤 thinking 后的模型首次输出、归一化文档和机器报告保存在 artifacts/session-note-p0-acceptance/real-model-2026-10-02/。各样本 human_review 保持 not_run。

实际完成 **12/12 次调用，零重试**；12/12 通过结构、引用命名空间与覆盖合同。代理逐份核对为 **10 份未发现目标检查项缺失、1 份需裁决、1 份违反无新增事实边界**。这些是本小样本的来源保留审阅结果，不能视为模型准确率。

| 样本 | 合同 | 代理审阅 | 观察 |
| --- | --- | --- | --- |
| concept-direction | contract_pass | pass | 同一点、可导推出连续、绝对值零点左右导数反例均保留。 |
| concept-matrix | contract_pass | pass | 方阵限制、行列式和秩判据保留，非方阵广义逆维持未讨论。 |
| derivation-product | contract_pass | pass | 可导前提、差商分解、连续性取极限与结论保留；补写完整差商左侧属于原式展开。 |
| derivation-integral | contract_pass | pass | 连续可微、区间、端点项与省略条件完整保留。 |
| problem-linear-system | contract_pass | pass | 矩阵题干、相加求解和两式代入检验保留。 |
| problem-missing-figure | contract_pass | pass | 缺少附图和边界维持未决，没有新增精确面积。 |
| comparison-series | contract_pass | pass | 两类定义、单向蕴含和交错调和反例保留。 |
| comparison-table | contract_pass | pass | 原表两行三列信息和有限极限条件保留；转换为列表，未保留表格版式。 |
| correction-sign | contract_pass | needs_review | 错误与正确结果及不泛化错因保留；正文未显式标明错因为用户确认，且新增展开求导检验式，需人工裁决是否属于允许的整理。 |
| correction-determinant | contract_pass | fail | 原矩阵及换行前后计算保留，但新增“两列”性质，原会话仅讨论两行，违反无新增事实边界。 |
| review-mixed | contract_pass | pass | 按导数/矩阵分段，保留独立条件及非整章覆盖声明。 |
| review-historical | contract_pass | pass | 旧证据片段缺失维持 unknown/待核查；没有用当前教材冒充旧证据。 |

行列式新增性质虽然挂有合法来源 ID，仍不在该来源正文中；当前确定性检查只提示 needs_review，并不能识别所有语义扩展。符号订正样本应显式保留“用户确认”的归因。12 份首次输出均保留，没有改写失败结果或再调用模型；人工审阅字段保持 not_run。

机器记录、代理审阅和 SHA-256 清单分别是 report.json、agent-review.json、sha256-manifest.json。

## 发布候选及数据影响

可保留的 DMG/ZIP 位于 artifacts/session-note-p0-acceptance/release-macos-arm64/。沿用项目 identity=null：未签名、公证、发布或安装到 Applications，未验证升级器和 Windows 包。独立目录中的 Texa.app 是本次实测应用，候选不是正式发行版。

| 产物 | SHA-256 |
| --- | --- |
| Texa-1.0.0-mac-arm64.zip | dd7d291e39556bf5059f7e0def7c2a93d2d7cdfae0a924302d5abe01d5f6282b |
| Texa-1.0.0-mac-arm64.dmg | 9b80e98df7e3c38510f30112f938574a983dda78d6d7dff041bc9913cde35f7e |
| app.asar | 9156e4b36bd3757d6e201c8d38db3dc129697b2808a7855b9b9056d85fddabbd |

所有验收写入隔离目录，未迁移真实会话、教材、错题或学习记录。新增 Notes schema 1 独立库由首次访问创建并纳入备份；已有数据影响和回退规则见 session-note-p0-implementation.md。没有重装项目依赖；缺失 npm 仅使用临时官方 npm 构建工具补足。

## 待完成门槛

- Windows 原生应用、相同尺寸与恢复流程、Windows 发布包。
- 人工逐份核对 12 份真实输出，特别是条件、来源边界、纠错归因和未决问题；代理发现项须裁决。
- 针对来源外扩展收紧生成行为，并在另行授权的真实模型回归中验证；本轮不超出 12 次预算重跑。
- 如需正式发布，再进行签名、公证、安装和升级验证。

本轮工作和失败证据已保存，不把合同通过或测试数量换算为数学正确率。

## 验收后的两项处理（2026-10-03）

用户指定执行收紧规则和明确归因，源码 prompt 已升级至 session-note-structure-v2。新增明确边界：来源未讨论的性质和步骤不可补充；用户确认的错因明确标注并引用确认消息，模型推测保持未经用户确认。规则同时适用于抽取与合并。

现有 42 项 Notes 离线测试通过。本次没有新增真实模型调用，也未重新打包；上方 12 次调用、证据及发布包仍对应 v1。v2 尚未真实语义复验，因此原来的语义问题不能记为已通过验收。
